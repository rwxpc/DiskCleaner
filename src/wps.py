# -*- coding: utf-8 -*-
"""WPS 缓存专清模块。"""
from __future__ import annotations
import os
from core import (
    ScanItem, get_fixed_drives, path_stats, scan_directory_names,
    is_reparse, should_skip,
)

KINGSOFT_NAMES = {"kingsoft", "wps office"}
CLOUD_NAMES = {"wps cloud files"}
BACKUP_NAMES = {"backup"}
CACHE_DIR_NAMES = {"cache", "caches", "temp", "tmp", "log", "logs", "crash"}
LABELS = {
    "backup": "本地自动备份 (office6\\backup)",
    "cloud": "云同步缓存 (WPS Cloud Files)",
    "cache": "缓存", "caches": "缓存", "temp": "临时文件", "tmp": "临时文件",
    "log": "日志", "logs": "日志", "crash": "崩溃报告",
}


def _dedup(paths):
    seen, out = set(), []
    for p in paths:
        k = p.lower()
        if k not in seen:
            seen.add(k)
            out.append(p)
    return out


def find_wps_roots(cancel) -> tuple[list[str], list[str]]:
    """返回 (Kingsoft 目录列表, WPS Cloud Files 目录列表)。"""
    user = os.environ.get("USERPROFILE", "")
    appdata = os.environ.get("APPDATA", os.path.join(user, "AppData", "Roaming"))
    local = os.environ.get("LOCALAPPDATA", os.path.join(user, "AppData", "Local"))
    k_roots: list[str] = []
    for base in (appdata, local, os.path.join(user, "Documents"), user):
        p = os.path.join(base, "Kingsoft")
        if os.path.isdir(p):
            k_roots.append(p)
    for p in scan_directory_names(get_fixed_drives(), KINGSOFT_NAMES, cancel, max_depth=5):
        k_roots.append(p)
    c_roots = list(scan_directory_names(get_fixed_drives(), CLOUD_NAMES, cancel, max_depth=6))
    return _dedup(k_roots), _dedup(c_roots)


def scan_wps(cancel, progress=None) -> list[ScanItem]:
    k_roots, c_roots = find_wps_roots(cancel)
    items: list[ScanItem] = []
    seen: set[str] = set()

    def add(path, kind, root):
        key = path.lower()
        if key in seen or not os.path.isdir(path) or cancel():
            return
        size, count = path_stats(path, cancel)
        if size <= 0 and count == 0:
            return
        seen.add(key)
        rel = os.path.relpath(path, root) if root else path
        items.append(ScanItem(
            path=path,
            name=f"WPS · {rel}",
            category=LABELS.get(kind, kind),
            size=size,
            file_count=count,
            default_checked=True,
            note=path,
            rel_base=root or os.path.dirname(path),
        ))
        if progress:
            progress(f"扫描 WPS: {rel}")

    for root in k_roots:
        if cancel():
            break
        for cur, dirs, _ in os.walk(root, topdown=True, followlinks=False):
            if cancel():
                break
            dirs[:] = [d for d in dirs
                       if not is_reparse(os.path.join(cur, d))
                       and not should_skip(os.path.join(cur, d))]
            for d in dirs:
                low = d.lower()
                full = os.path.join(cur, d)
                if low in BACKUP_NAMES:
                    add(full, "backup", root)
                elif low in CACHE_DIR_NAMES:
                    add(full, low, root)

    for root in c_roots:
        if cancel():
            break
        add(root, "cloud", os.path.dirname(root))
        for cur, dirs, _ in os.walk(root, topdown=True, followlinks=False):
            if cancel():
                break
            dirs[:] = [d for d in dirs if not is_reparse(os.path.join(cur, d))]
            for d in dirs:
                if d.lower() in CACHE_DIR_NAMES:
                    add(os.path.join(cur, d), d.lower(), root)

    items.sort(key=lambda x: x.size, reverse=True)
    return items
