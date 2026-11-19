# -*- coding: utf-8 -*-
"""微信专清 / 企业微信专清 扫描模块。

类别严格按设计稿固定为 6 类：图片、视频、音频、文件、缓存、聊天记录。
其中「聊天记录」只统计不清理；「文件」默认不勾选。
"""
from __future__ import annotations
import os
from core import (
    ScanItem, get_fixed_drives, path_stats, scan_directory_names,
    is_reparse, should_skip, iter_files,
)

WECHAT_NAMES = {"wechat files", "wechat", "xwechat_files"}
WXWORK_NAMES = {"wxwork"}

# 设计稿固定 6 类：(名称, 说明, 风险, 默认勾选, 只统计不清理)
CATEGORIES = [
    ("图片", "聊天里的普通图片、表情、头像", "低风险", True, False),
    ("视频", "聊天里的视频与短视频", "低风险", True, False),
    ("音频", "语音消息与音频文件", "低风险", True, False),
    ("文件", "聊天收发的文档、压缩包（默认不勾选）", "中风险", False, False),
    ("缓存", "加密的聊天图片/视频（.dat）、缩略图与临时文件，最大的一块", "低风险", True, False),
    ("聊天记录", "微信数据库（db_storage），只统计不清理", "高风险", False, True),
]

# 目录名 -> 类别（小写匹配，覆盖新旧微信目录结构）
DIR_RULES = {
    # 图片
    "image": "图片", "images": "图片", "img": "图片", "photo": "图片",
    "emoji": "图片", "sticker": "图片", "avatar": "图片", "headimg": "图片",
    # 视频
    "video": "视频", "videos": "视频",
    # 音频
    "voice": "音频", "audio": "音频", "voices": "音频",
    # 文件
    "file": "文件", "files": "文件", "filetransfer": "文件", "attachment": "文件",
    # 缓存
    "cache": "缓存", "caches": "缓存", "temp": "缓存", "tmp": "缓存",
    "thumbnail": "缓存", "thumbnails": "缓存", "resource": "缓存",
    # 聊天记录（数据库）
    "db_storage": "聊天记录", "database": "聊天记录", "db": "聊天记录",
    "msg": "聊天记录", "message": "聊天记录",
}

# 扩展名兜底分类（当目录名无法判定）
EXT_RULES = {
    "图片": {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp"},
    "视频": {".mp4", ".avi", ".mkv", ".mov", ".webm"},
    "音频": {".mp3", ".wav", ".amr", ".silk", ".ogg", ".m4a"},
    "文件": {".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".pdf",
             ".zip", ".rar", ".7z", ".txt", ".csv"},
    "聊天记录": {".db"},
}


def find_app_roots(names: set[str], cancel) -> list[str]:
    """查找应用数据根目录：先查常见位置，未找到再全盘扫描。"""
    found: list[str] = []
    seen: set[str] = set()
    user = os.environ.get("USERPROFILE", "")
    bases = [
        os.path.join(user, "Documents"),
        os.path.join(user, "My Documents"),
        user,
        os.path.join(user, "AppData", "Roaming"),
        os.path.join(user, "AppData", "Local"),
    ]
    bases += get_fixed_drives()
    for base in bases:
        if cancel():
            return found
        if not os.path.isdir(base):
            continue
        try:
            for entry in os.listdir(base):
                if entry.lower() in names:
                    full = os.path.join(base, entry)
                    key = full.lower()
                    if key not in seen and os.path.isdir(full) and not is_reparse(full):
                        seen.add(key)
                        found.append(full)
        except OSError:
            pass
    if found:
        return found
    for p in scan_directory_names(get_fixed_drives(), names, cancel, max_depth=5):
        key = p.lower()
        if key not in seen:
            seen.add(key)
            found.append(p)
    return found


def _classify_file(path: str) -> str | None:
    """根据文件路径中的目录名与扩展名判定归属类别。"""
    low = path.lower().replace("/", "\\")
    parts = [p for p in low.split("\\") if p]
    # 目录名优先：从 deepest 往前找，缓存/聊天记录优先级更高
    for part in reversed(parts[:-1]):
        cat = DIR_RULES.get(part)
        if cat:
            return cat
    # 扩展名兜底；.dat 加密文件归缓存
    if low.endswith(".dat"):
        return "缓存"
    ext = os.path.splitext(low)[1]
    for cat, exts in EXT_RULES.items():
        if ext in exts:
            return cat
    return None


def _build_items(roots, app, cancel, progress) -> list[ScanItem]:
    """按 6 类聚合文件；每类产出一条 ScanItem（与图3逐行对应）。"""
    buckets: dict[str, dict] = {
        name: {"size": 0, "count": 0, "dirs": set()}
        for name, *_ in CATEGORIES
    }

    for root in roots:
        if cancel():
            break
        for fp in iter_files(root, cancel, max_depth=24):
            if cancel():
                break
            cat = _classify_file(fp)
            if not cat:
                continue
            try:
                sz = os.path.getsize(fp)
            except OSError:
                continue
            buckets[cat]["size"] += sz
            buckets[cat]["count"] += 1
            buckets[cat]["dirs"].add(os.path.dirname(fp))

    items: list[ScanItem] = []
    for name, desc, risk, default_checked, no_clean in CATEGORIES:
        if progress:
            progress(f"正在统计：{app} · {name}")
        b = buckets[name]
        # files 保留目录层级代表路径，便于后续 files_older_than 递归收集
        files = sorted(b["dirs"]) if b["dirs"] else []
        items.append(ScanItem(
            path=files[0] if files else "",
            name=f"{app} · {name}",
            category=name,
            size=b["size"],
            file_count=b["count"],
            default_checked=default_checked,
            note=desc,
            files=files,
            risk=risk,
            no_clean=no_clean,
        ))
    return items


def scan_wechat(cancel, progress=None) -> list[ScanItem]:
    roots = find_app_roots(WECHAT_NAMES, cancel)
    if progress:
        progress(f"微信数据目录：{roots[0] if roots else '未找到'}")
    return _build_items(roots, "微信", cancel, progress)


def scan_wxwork(cancel, progress=None) -> list[ScanItem]:
    roots = find_app_roots(WXWORK_NAMES, cancel)
    if progress:
        progress(f"企业微信数据目录：{roots[0] if roots else '未找到'}")
    return _build_items(roots, "企业微信", cancel, progress)
