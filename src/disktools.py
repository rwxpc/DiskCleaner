# -*- coding: utf-8 -*-
"""「常规清理」与「扫描大文件」的扫描实现。

「常规清理」严格只扫描设计稿列出的 7 类：用户临时文件、Gradle 缓存、系统临时文件、
pip 缓存、npm 缓存、Chrome 缓存、回收站（顺序与图2一致）。
"""
from __future__ import annotations
import os
from core import ScanItem, iter_files, path_stats


def _home() -> str:
    return os.environ.get("USERPROFILE", os.path.expanduser("~"))


def _local() -> str:
    return os.environ.get("LOCALAPPDATA", os.path.join(_home(), "AppData", "Local"))


def _roaming() -> str:
    return os.environ.get("APPDATA", os.path.join(_home(), "AppData", "Roaming"))


def _windir() -> str:
    return os.environ.get("WINDIR", r"C:\Windows")


# 7 类定义：(名称, 目录候选, 风险, 默认勾选, 说明)
JUNK_CATEGORIES = [
    ("用户临时文件", lambda: [
        os.environ.get("TEMP", ""), os.environ.get("TMP", ""),
        os.path.join(_local(), "Temp"),
    ], "低风险", True, "当前用户运行产生的临时文件，可安全清理"),
    ("Gradle 缓存", lambda: [
        os.path.join(_home(), ".gradle", "caches"),
        os.path.join(_home(), ".gradle", "daemon"),
    ], "低风险", True, "Gradle 构建依赖与守护进程缓存"),
    ("系统临时文件", lambda: [
        os.path.join(_windir(), "Temp"),
        os.path.join(_windir(), "SoftwareDistribution", "Download"),
    ], "低风险", True, "Windows 系统临时目录与更新下载缓存"),
    ("pip 缓存", lambda: [
        os.path.join(_local(), "pip", "Cache"),
        os.path.join(_home(), ".cache", "pip"),
    ], "低风险", True, "Python pip 下载的 wheel / 包缓存"),
    ("npm 缓存", lambda: [
        os.path.join(_roaming(), "npm", "cache"),
        os.path.join(_home(), ".npm", "_cacache"),
    ], "低风险", True, "Node.js npm 包下载缓存"),
    ("Chrome 缓存", lambda: [
        os.path.join(_local(), "Google", "Chrome", "User Data", "Default", "Cache"),
        os.path.join(_local(), "Google", "Chrome", "User Data", "Default", "Code Cache"),
    ], "中风险", False, "Chrome 浏览器缓存（清理后首次打开网页可能变慢）"),
]


def _unique_dirs(paths) -> list[str]:
    seen, out = set(), []
    for p in paths:
        if not p or not os.path.isdir(p):
            continue
        key = os.path.normcase(os.path.abspath(p))
        if key in seen:
            continue
        seen.add(key)
        out.append(p)
    return out


def _recycle_stats(drives, cancel) -> tuple[int, int, list[str]]:
    """统计各磁盘回收站 $Recycle.Bin 占用，返回 (大小, 文件数, 文件列表)。"""
    total = count = 0
    files: list[str] = []
    for drive in drives:
        if cancel():
            break
        root = os.path.join(drive, "$Recycle.Bin")
        if not os.path.isdir(root):
            continue
        try:
            for cur, dirs, fs in os.walk(root, topdown=True, followlinks=False):
                if cancel():
                    break
                for name in fs:
                    fp = os.path.join(cur, name)
                    try:
                        total += os.path.getsize(fp)
                        count += 1
                        files.append(fp)
                    except OSError:
                        pass
        except OSError:
            pass
    return total, count, files


def scan_junk(drives, cancel, progress=None) -> list[ScanItem]:
    """按固定 7 类聚合全盘垃圾扫描结果（顺序与图2一致）。"""
    items: list[ScanItem] = []
    for name, dirs_fn, risk, default_checked, note in JUNK_CATEGORIES:
        if cancel():
            break
        if progress:
            progress(f"正在统计：{name}")
        size = count = 0
        files: list[str] = []
        for d in _unique_dirs(dirs_fn()):
            if cancel():
                break
            s, c = path_stats(d, cancel)
            size += s
            count += c
            files.append(d)  # 保留目录本身，整体送入回收站更快
        items.append(ScanItem(
            path="", name=name, category="垃圾文件", size=size,
            file_count=count, default_checked=default_checked,
            note=note, files=files, risk=risk,
        ))

    # 回收站：高风险、默认不勾选；其中文件已在回收站，清理时需永久删除
    if progress:
        progress("正在统计：回收站")
    size, count, files = _recycle_stats(drives, cancel)
    items.append(ScanItem(
        path="", name="回收站", category="垃圾文件", size=size,
        file_count=count, default_checked=False,
        note="回收站中的已删除文件，清理后永久删除、无法还原（高风险）",
        files=files, risk="高风险", no_recycle=True,
    ))
    return items


def scan_large_files(drives, min_mb, cancel, progress=None) -> list[ScanItem]:
    """查找不小于阈值的文件，按大小降序。"""
    min_bytes = int(min_mb * 1024 * 1024)
    items: list[ScanItem] = []
    for drive in drives:
        if progress:
            progress(f"正在查找大文件：{drive}")
        for fp in iter_files(drive, cancel, max_depth=32):
            if cancel():
                return items
            try:
                sz = os.path.getsize(fp)
            except OSError:
                continue
            if sz >= min_bytes:
                items.append(ScanItem(
                    path=fp, name=os.path.basename(fp), category="大文件",
                    size=sz, file_count=1, default_checked=False, note=fp,
                ))
                if progress:
                    progress(f"大文件: {os.path.basename(fp)}")
    items.sort(key=lambda x: x.size, reverse=True)
    return items
