# -*- coding: utf-8 -*-
"""「常规清理」与「扫描大文件」的扫描实现。

「常规清理」严格只扫描 6 类系统缓存/临时文件：用户临时文件、Gradle 缓存、
系统临时文件、pip 缓存、npm 缓存、Chrome 缓存（不含回收站，顺序与图2一致）。
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


# 6 类定义：(名称, 目录候选, 风险, 默认勾选, 说明)
JUNK_CATEGORIES = [
    ("用户临时文件", lambda: [
        os.path.join(_local(), "Temp"),
    ], "低风险", True, "当前登录用户 Temp 文件夹中的临时文件，可安全清理"),
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


def scan_junk(drives, cancel, progress=None) -> list[ScanItem]:
    """按固定 6 类聚合系统缓存/临时文件扫描结果（不含回收站）。

    drives 参数保留以兼容调用方（常规清理入口与 /scan 报告）。
    """
    items: list[ScanItem] = []
    for name, dirs_fn, risk, default_checked, note in JUNK_CATEGORIES:
        if cancel():
            break
        if progress:
            progress(f"正在统计：{name}")
        size = count = 0
        files: list[str] = []
        dirs = _unique_dirs(dirs_fn())
        for d in dirs:
            if cancel():
                break
            s, c = path_stats(d, cancel)
            size += s
            count += c
            if name == "用户临时文件":
                # 只清理 Temp 文件夹「内容」，保留 Temp 目录本身，
                # 避免把当前登录用户的关键临时目录整个送进回收站。
                try:
                    children = [os.path.join(d, e) for e in os.listdir(d)]
                except OSError:
                    children = []
                files.extend(children or [d])
            else:
                files.append(d)  # 其余类别按目录整体送入回收站更快
        items.append(ScanItem(
            path=dirs[0] if dirs else "", name=name, category="垃圾文件",
            size=size, file_count=count, default_checked=default_checked,
            note=note, files=files, risk=risk,
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
