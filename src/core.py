# -*- coding: utf-8 -*-
"""DiskCleaner 公共核心模块：磁盘枚举、体积统计、回收站删除、时间过滤。"""
from __future__ import annotations

import ctypes
import os
import shutil
import time
from ctypes import wintypes
from dataclasses import dataclass, field
from typing import Callable, Iterable

FILE_ATTRIBUTE_REPARSE_POINT = 0x400
RECYCLE_FLAG = 0x0040 | 0x0004 | 0x0010 | 0x0400  # ALLOWUNDO | NOCONFIRMATION | SILENT | NOERRORUI
# v1.4.0：被占用文件改走「重启后自动删除」，需管理员权限（本程序已 requireAdministrator）
DELETE_ACCESS = 0x00010000      # 请求 DELETE 权限，用于探测占用
FILE_FLAG_BACKUP_SEMANTICS = 0x02000000  # 允许对目录打开句柄
MOVEFILE_DELAY_UNTIL_REBOOT = 0x00000004  # MoveFileExW 标志：重启时删除
ERROR_SHARING_VIOLATION = 32

DOC_EXTS = {
    ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".pdf",
    ".wps", ".et", ".dps", ".odt", ".ods", ".odp", ".rtf",
}

SKIP_DIR_NAMES = {
    "$recycle.bin", "system volume information", "$windows.~ws", "$windows.~bt",
    "windows\\winsxs", "node_modules", "__pycache__", ".git", ".svn", ".hg",
    "appdata\\local\\microsoft\\windows\\innofiles", "perflogs",
}


@dataclass
class ScanItem:
    path: str
    name: str
    category: str
    size: int = 0
    file_count: int = 0
    default_checked: bool = False
    note: str = ""
    rel_base: str = ""
    files: list[str] = field(default_factory=list)
    # 可选元数据：risk 显式风险等级（缺省时由界面按名称推断）；
    # no_clean 表示该类"只统计不清理"；no_recycle 表示直接删除不进回收站。
    risk: str = ""
    no_clean: bool = False
    no_recycle: bool = False


def human_size(n: float) -> str:
    n = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.2f} {unit}" if unit != "B" else f"{int(n)} B"
        n /= 1024
    return f"{n:.2f} PB"


def get_fixed_drives() -> list[str]:
    """返回本机固定磁盘盘符列表，如 ['C:\\', 'D:\\']。"""
    drives = []
    try:
        mask = ctypes.windll.kernel32.GetLogicalDrives()
        for i in range(26):
            if mask & (1 << i):
                letter = f"{chr(65 + i)}:\\"
                try:
                    dtype = ctypes.windll.kernel32.GetDriveTypeW(ctypes.c_wchar_p(letter))
                    if dtype == 3:  # DRIVE_FIXED
                        drives.append(letter)
                except Exception:
                    drives.append(letter)
    except Exception:
        for i in range(26):
            p = f"{chr(65 + i)}:\\"
            if os.path.isdir(p):
                drives.append(p)
    return drives


def is_reparse(path: str) -> bool:
    try:
        st = os.stat(path, follow_symlinks=False)
        return bool(getattr(st, "st_file_attributes", 0) & FILE_ATTRIBUTE_REPARSE_POINT)
    except OSError:
        return True


def should_skip(path: str) -> bool:
    low = path.lower().replace("/", "\\")
    for name in SKIP_DIR_NAMES:
        if ("\\" + name + "\\") in low or low.endswith("\\" + name):
            return True
    return False


def iter_files(path: str, cancel: Callable[[], bool] | None = None,
               max_depth: int = 24) -> Iterable[str]:
    """安全遍历目录下的文件（跳过重解析点与系统目录，避免死循环）。"""
    if os.path.isfile(path):
        yield path
        return
    base_depth = path.rstrip("\\/").count("\\")
    for root, dirs, files in os.walk(path, topdown=True, followlinks=False):
        if cancel and cancel():
            return
        dirs[:] = [
            d for d in dirs
            if not is_reparse(os.path.join(root, d))
            and not should_skip(os.path.join(root, d))
            and (root.count("\\") - base_depth) < max_depth
        ]
        for f in files:
            fp = os.path.join(root, f)
            try:
                if is_reparse(fp):
                    continue
            except OSError:
                continue
            yield fp


def path_stats(path: str, cancel: Callable[[], bool] | None = None) -> tuple[int, int]:
    """统计路径下文件总字节数与文件数。"""
    total = count = 0
    for fp in iter_files(path, cancel):
        try:
            total += os.path.getsize(fp)
            count += 1
        except OSError:
            pass
    return total, count


def cutoff_timestamp(days: int | None) -> float:
    if not days:
        return 0.0
    return time.time() - days * 86400


def files_older_than(path: str, days: int | None,
                     cancel: Callable[[], bool] | None = None) -> list[str]:
    """返回早于指定天数的文件列表（days 为 None 或 0 时返回全部）。"""
    cutoff = cutoff_timestamp(days)
    result = []
    for fp in iter_files(path, cancel):
        try:
            if not cutoff or os.path.getmtime(fp) < cutoff:
                result.append(fp)
        except OSError:
            pass
    return result


def _op_struct():
    class SHFILEOPSTRUCTW(ctypes.Structure):
        _fields_ = [
            ("hwnd", wintypes.HWND),
            ("wFunc", wintypes.UINT),
            ("pFrom", ctypes.c_wchar_p),
            ("pTo", ctypes.c_wchar_p),
            ("fFlags", ctypes.c_ushort),
            ("fAnyOperationsAborted", wintypes.BOOL),
            ("hNameMappings", ctypes.c_void_p),
            ("lpszProgressTitle", ctypes.c_wchar_p),
        ]
    return SHFILEOPSTRUCTW()


def is_file_locked(path: str) -> bool:
    """探测文件/目录是否被其他进程占用（无法以 DELETE 权限独占打开）。

    返回 True 时该文件在当前会话几乎不可能删除（SHFileOperation / os.remove
    都会因 sharing violation 失败），适合改走「重启后删除」。
    """
    try:
        k32 = ctypes.windll.kernel32
        k32.CreateFileW.restype = wintypes.HANDLE
        flags = FILE_FLAG_BACKUP_SEMANTICS if os.path.isdir(path) else 0
        handle = k32.CreateFileW(str(path), DELETE_ACCESS, 0, None, 3, flags, None)
        if handle == wintypes.HANDLE(-1).value:
            return k32.GetLastError() == ERROR_SHARING_VIOLATION
        k32.CloseHandle(handle)
        return False
    except Exception:
        return False


def schedule_delete_on_reboot(path: str) -> bool:
    """把路径登记到 Windows「重启时删除」队列，返回是否登记成功。

    调用 MoveFileExW(path, None, MOVEFILE_DELAY_UNTIL_REBOOT)。需管理员权限；
    登记成功意味着下次重启后该文件/目录会被系统自动清除，本次会话仍可见。
    """
    try:
        k32 = ctypes.windll.kernel32
        buf = ctypes.create_unicode_buffer(os.path.abspath(path))
        return bool(k32.MoveFileExW(buf, None, MOVEFILE_DELAY_UNTIL_REBOOT))
    except Exception:
        return False


def send_to_recycle_bin(paths: Iterable[str], progress=None, cancel=None,
                        reboot_on_locked: bool = False) -> tuple[int, list[str], int]:
    """将文件/目录送入系统回收站，可还原。返回 (成功数, 失败列表, 重启清理数)。

    progress(current, total, path, status) 可选回调，status ∈ {True, False, "reboot"}：
    True=已入回收站；"reboot"=被占用但已登记重启清理；False=确实失败。
    cancel() 返回 True 时提前停止，未处理项不计入失败。

    reboot_on_locked=True 时，删除失败且确认被占用的项会改走 Windows「重启后删除」
    队列（管理员权限下登记到 PendingFileRenameOperations），避免把被系统进程独占
    的临时文件误报为清理失败；登记成功计为第三种成功状态。

    关键点：Shell32.SHFileOperationW 的 pFrom 是「双 NUL 结尾」的宽字符串，
    Python 3 的 c_wchar_p 字段赋值会拒绝内嵌 NUL（ValueError: embedded null
    character）。必须改用 create_unicode_buffer 保留内嵌 NUL，再以 buffer 的地址
    赋给 c_void_p 型 pFrom，否则整个清理流程会静默失败。
    """
    valid = []
    for p in paths:
        try:
            ap = os.path.abspath(p)
            if os.path.exists(ap):
                valid.append(ap)
        except OSError:
            pass
    total = len(valid)
    if not valid:
        return 0, [], 0
    ok_count, failed, reboot_count = 0, [], 0
    # 逐个删除：既能汇报实时进度，也避免超长双 NUL 缓冲区与单次失败拖垮整批。
    for idx, p in enumerate(valid, 1):
        if cancel and cancel():
            break
        buf = ctypes.create_unicode_buffer(p + "\0\0")  # 双 NUL 结尾
        op = _op_struct()
        op.hwnd = None
        op.wFunc = 3  # FO_DELETE
        op.pFrom = ctypes.cast(buf, ctypes.c_wchar_p)
        op.pTo = None
        op.fFlags = RECYCLE_FLAG
        ret = -1
        try:
            ret = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(op))
        except Exception:
            pass
        success = ret == 0 and not op.fAnyOperationsAborted
        status = True if success else False
        if success:
            ok_count += 1
        elif reboot_on_locked and is_file_locked(p) and schedule_delete_on_reboot(p):
            reboot_count += 1
            status = "reboot"
        else:
            failed.append(p)
        if progress:
            try:
                progress(idx, total, p, status)
            except Exception:
                pass
    return ok_count, failed, reboot_count


def delete_permanent(paths: Iterable[str], progress=None, cancel=None,
                     reboot_on_locked: bool = False) -> tuple[int, list[str], int]:
    """永久删除（不进回收站），用于回收站等已在回收站中的文件。

    返回 (成功数, 失败列表, 重启清理数)；progress 状态语义同 send_to_recycle_bin。
    """
    import shutil
    ok_count, failed, reboot_count = 0, [], 0
    valid = []
    for p in paths:
        try:
            ap = os.path.abspath(p)
            if os.path.exists(ap):
                valid.append(ap)
        except OSError:
            pass
    total = len(valid)
    for idx, p in enumerate(valid, 1):
        if cancel and cancel():
            break
        done = False
        try:
            if os.path.isdir(p) and not os.path.islink(p):
                shutil.rmtree(p)
                done = True
            elif os.path.isfile(p) or os.path.islink(p):
                os.remove(p)
                done = True
        except OSError:
            done = False
        status = True if done else False
        if done:
            ok_count += 1
        elif reboot_on_locked and is_file_locked(p) and schedule_delete_on_reboot(p):
            reboot_count += 1
            status = "reboot"
        else:
            failed.append(p)
        if progress:
            try:
                progress(idx, total, p, status)
            except Exception:
                pass
    return ok_count, failed, reboot_count


def unique_dest(src: str, dest_root: str, rel_base: str = "") -> str:
    """生成不冲突的目标路径，保持原目录结构。"""
    base = rel_base or os.path.dirname(src)
    try:
        rel = os.path.relpath(src, base)
    except ValueError:
        rel = os.path.basename(src)
    if rel.startswith(".."):
        rel = os.path.basename(src)
    target = os.path.join(dest_root, rel)
    name, ext = os.path.splitext(target)
    i = 1
    while os.path.exists(target):
        target = f"{name}_{i}{ext}"
        i += 1
    return target


def move_preserving_tree(files: Iterable[str], dest_root: str,
                         rel_base: str = "") -> tuple[int, list[str]]:
    """按原目录结构移动文件到指定文件夹，返回 (成功数, 失败列表)。"""
    os.makedirs(dest_root, exist_ok=True)
    moved, failed = 0, []
    for src in files:
        try:
            target = unique_dest(src, dest_root, rel_base)
            os.makedirs(os.path.dirname(target), exist_ok=True)
            shutil.move(src, target)
            moved += 1
        except Exception:
            failed.append(src)
    return moved, failed


def is_document(path: str) -> bool:
    return os.path.splitext(path)[1].lower() in DOC_EXTS


def scan_directory_names(roots: Iterable[str], names: set[str],
                         cancel: Callable[[], bool] | None = None,
                         max_depth: int = 8) -> list[str]:
    """在给定根目录（磁盘）下按目录名查找，返回匹配目录的完整路径。"""
    found: list[str] = []
    seen: set[str] = set()
    for root in roots:
        base_depth = root.rstrip("\\/").count("\\")
        for cur, dirs, _ in os.walk(root, topdown=True, followlinks=False):
            if cancel and cancel():
                return found
            dirs[:] = [
                d for d in dirs
                if d.lower() in names
                or ((cur.count("\\") - base_depth) < max_depth
                    and not is_reparse(os.path.join(cur, d))
                    and not should_skip(os.path.join(cur, d)))
            ]
            for d in list(dirs):
                if d.lower() in names:
                    full = os.path.join(cur, d)
                    low = full.lower()
                    if low not in seen:
                        seen.add(low)
                        found.append(full)
    return found
