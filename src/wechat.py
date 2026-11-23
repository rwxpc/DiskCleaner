# -*- coding: utf-8 -*-
"""微信专清 / 企业微信专清 扫描模块。

类别固定为 7 类：图片、视频、音频、文件、文档、缓存、聊天记录。
其中「聊天记录」只统计不清理；「文件」「文档」默认不勾选。

v1.7.0 新增「文档」类别
------------------------
按扩展名优先判定常用办公文档（电子文档 / 电子表格 / 演示文档 / PDF /
WPS / CSV 等），无论文件位于 File、attachment 还是其它目录，都归入「文档」；
「文件」类别的扩展名集合已剔除这些后缀，二者严格互斥、不重复统计。

清理目标也随之精确化：「文件」「文档」两类按**具体文件路径**收集（而非
所在目录），因为这两类文件常混在同一个目录下，若按目录清理，勾选其中一类
会连带删除另一类的文件。其余 5 类仍按目录收集，保持既有清理逻辑不变。

v1.6.0 全磁盘扫描修复
----------------------
旧版 find_app_roots 只查「常见用户位置 + 各磁盘根目录第一层」，且**一旦
命中任意一个目录就立即返回**。Windows 7 的微信 / 企业微信默认数据目录恰好
是 C:\\Users\\<用户>\\Documents\\WeChat Files（WXWork 同理），于是 C 盘一命中
就直接返回，D/E/F 等其他本地磁盘上的数据目录完全不会被扫描、统计和清理。

现改为：
  * 枚举「所有可访问的本地固定磁盘」，逐个做根目录第一层快速命中 +
    有限深度目录名搜索，合并去重后返回**全部**匹配目录；
  * 7 类聚合统计与清理覆盖所有找到的目录，不再只统计 C 盘；
  * 全部数据目录经 ScanItem.roots 带出，由详情面板与日志逐条列出；
  * 不可访问磁盘（未解锁、RAW、未就绪）与无权限目录一律跳过并继续，
    单个磁盘/目录失败不影响其余磁盘，跳过的盘符写入日志提示。
"""
from __future__ import annotations
import os
from core import (
    ScanItem, DOC_EXTS, get_accessible_fixed_drives, scan_directory_names,
    is_reparse, iter_files,
)

WECHAT_NAMES = {"wechat files", "wechat", "xwechat_files"}
WXWORK_NAMES = {"wxwork"}

# v1.7.0：常用办公文档扩展名。以 core.DOC_EXTS（WPS 文档转存共用口径）为基础，
# 补充 CSV 电子表格、Office 宏/模板格式与常见版式文档，覆盖「电子文档、
# 电子表格、演示文档、PDF 等类型」。
OFFICE_EXTS = set(DOC_EXTS) | {
    ".csv", ".docm", ".dotx", ".dotm", ".dot",
    ".xlsm", ".xltx", ".xltm", ".xlt", ".xlsb",
    ".pptm", ".potx", ".potm", ".pot", ".ppsx", ".pps",
    ".xps", ".oxps", ".mht", ".mhtml", ".epub",
}

# 固定 7 类：(名称, 说明, 风险, 默认勾选, 只统计不清理)
CATEGORIES = [
    ("图片", "聊天里的普通图片、表情、头像", "低风险", True, False),
    ("视频", "聊天里的视频与短视频", "低风险", True, False),
    ("音频", "语音消息与音频文件", "低风险", True, False),
    ("文件", "聊天收发的压缩包、文本等其它文件（默认不勾选）", "中风险", False, False),
    ("文档", "聊天收发的 Word/Excel/PPT/PDF/WPS 等办公文档（默认不勾选）", "中风险", False, False),
    ("缓存", "加密的聊天图片/视频（.dat）、缩略图与临时文件，最大的一块", "低风险", True, False),
    ("聊天记录", "微信数据库（db_storage），只统计不清理", "高风险", False, True),
]

# 「文件」「文档」按精确文件路径清理，避免两类共享目录时交叉删除
FILE_LEVEL_CATS = {"文件", "文档"}

# 目录名 -> 类别（小写匹配，覆盖新旧微信目录结构）
DIR_RULES = {
    "image": "图片", "images": "图片", "img": "图片", "photo": "图片",
    "emoji": "图片", "sticker": "图片", "avatar": "图片", "headimg": "图片",
    "video": "视频", "videos": "视频",
    "voice": "音频", "audio": "音频", "voices": "音频",
    "file": "文件", "files": "文件", "filetransfer": "文件", "attachment": "文件",
    "cache": "缓存", "caches": "缓存", "temp": "缓存", "tmp": "缓存",
    "thumbnail": "缓存", "thumbnails": "缓存", "resource": "缓存",
    "db_storage": "聊天记录", "database": "聊天记录", "db": "聊天记录",
    "msg": "聊天记录", "message": "聊天记录",
}

# 扩展名兜底分类（当目录名无法判定）。
# v1.7.0：「文件」集合已移除全部办公文档后缀，办公文档一律由 OFFICE_EXTS
# 优先判定为「文档」，两类严格互斥，绝不重复统计。
EXT_RULES = {
    "图片": {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp"},
    "视频": {".mp4", ".avi", ".mkv", ".mov", ".webm"},
    "音频": {".mp3", ".wav", ".amr", ".silk", ".ogg", ".m4a"},
    "文件": {".zip", ".rar", ".7z", ".txt", ".exe", ".apk", ".msi",
             ".iso", ".dmg", ".torrent"},
    "聊天记录": {".db"},
}


def _safe_listdir(path: str) -> list[str]:
    """列目录；不可访问 / 无权限 / 不存在时返回空列表，绝不中断整体扫描。"""
    try:
        return os.listdir(path)
    except (OSError, PermissionError):
        return []


def find_app_roots(names, cancel, progress=None):
    """在「所有本地固定磁盘」中查找应用数据根目录。

    返回 (found, skipped)：found 为全部匹配目录（去重、按路径排序），
    skipped 为跳过的不可访问盘符。取消时返回已收集到的结果。
    """
    found, seen = [], set()

    def add(path):
        try:
            key = os.path.normcase(os.path.abspath(path))
            if key in seen or not os.path.isdir(path) or is_reparse(path):
                return
            seen.add(key)
            found.append(path)
        except (OSError, PermissionError):
            pass

    # 1) 常见用户位置：仅作快速命中，不再「找到即返回」
    user = os.environ.get("USERPROFILE", "")
    for base in (
        os.path.join(user, "Documents"),
        os.path.join(user, "My Documents"),
        user,
        os.path.join(user, "AppData", "Roaming"),
        os.path.join(user, "AppData", "Local"),
    ):
        if cancel():
            return found, []
        try:
            if not os.path.isdir(base):
                continue
        except (OSError, PermissionError):
            continue
        for entry in _safe_listdir(base):
            if entry.lower() in names:
                add(os.path.join(base, entry))

    # 2) 所有可访问固定磁盘：根目录第一层 + 深度目录名搜索
    #    每个磁盘独立处理，任一磁盘失败都不影响其余磁盘。
    drives, skipped = get_accessible_fixed_drives()
    low_names = {n.lower() for n in names}
    for drive in drives:
        if cancel():
            break
        for entry in _safe_listdir(drive):
            if entry.lower() in low_names:
                add(os.path.join(drive, entry))
        try:
            for p in scan_directory_names([drive], low_names, cancel, max_depth=6):
                add(p)
        except (OSError, PermissionError):
            pass
        if progress:
            progress(f"已扫描 {drive} · 累计找到 {len(found)} 个数据目录…")

    found.sort(key=lambda p: p.lower())
    return found, skipped


def _classify_file(path: str):
    """根据扩展名与路径中的目录名判定归属类别。

    v1.7.0：办公文档按扩展名**优先**判定 —— 微信把收发文件放在 File /
    attachment 等目录，若先按目录名判定会把 docx/pdf 统统算成「文件」，
    因此必须先识别 OFFICE_EXTS 归入「文档」，再走原有目录名/扩展名规则。
    """
    low = path.lower().replace("/", "\\")
    ext = os.path.splitext(low)[1]
    if ext in OFFICE_EXTS:
        return "文档"
    parts = [p for p in low.split("\\") if p]
    for part in reversed(parts[:-1]):
        cat = DIR_RULES.get(part)
        if cat:
            return cat
    if low.endswith(".dat"):
        return "缓存"
    for cat, exts in EXT_RULES.items():
        if ext in exts:
            return cat
    return None


def _build_items(roots, app, cancel, progress, scan_info=""):
    """按 7 类聚合「所有数据目录」下的文件；每类产出一条 ScanItem。

    v1.9.1 安全加固：清理目标不再一律是「整个目录」。微信数据目录里同一
    文件夹常混有多种文件（Cache 目录里同时有 .dat 缓存、.jpg 图片、
    .docx 文档，甚至 db 聊天记录），若按整目录清理，只勾选「缓存」也会
    连带删掉文档与聊天记录数据库。

    现在为每个文件把类别登记到它所在的目录及全部祖先目录，只有「该目录
    整个子树都只含本类别文件」时才整目录删除；混合目录一律改为本类别的
    精确文件路径。纯目录仍可整删，保持清理速度，同时杜绝跨类别误删。
    """
    buckets = {
        name: {"size": 0, "count": 0, "dirs": set(), "paths": []}
        for name, *_ in CATEGORIES
    }
    dir_cats = {}  # 目录 -> 该目录及其所有子目录出现过的类别（None -> "_other_"）

    def mark(dirpath, cat):
        cur = dirpath
        while cur:
            dir_cats.setdefault(cur, set()).add(cat or "_other_")
            parent = os.path.dirname(cur)
            if not parent or parent == cur:
                break
            cur = parent

    for root in roots:
        if cancel():
            break
        for fp in iter_files(root, cancel, max_depth=24):
            if cancel():
                break
            cat = _classify_file(fp)
            d = os.path.dirname(fp)
            mark(d, cat)
            if not cat:
                continue
            try:
                sz = os.path.getsize(fp)
            except OSError:
                continue
            b = buckets[cat]
            b["size"] += sz
            b["count"] += 1
            b["dirs"].add(d)
            b["paths"].append(fp)

    items = []
    for name, desc, risk, default_checked, no_clean in CATEGORIES:
        if progress:
            progress(f"正在统计：{app} · {name}")
        b = buckets[name]
        if no_clean:
            # 只统计不清理：保留目录供详情展示，_collect_files 会直接返回空
            files = sorted(b["dirs"])
        elif name in FILE_LEVEL_CATS:
            # 「文件」「文档」按精确文件路径清理，互不干扰（v1.7.0 既有规则）
            files = sorted(set(b["paths"]))
        else:
            # 图片 / 视频 / 音频 / 缓存：纯目录整删，混合目录只删本类文件
            pure, mixed = [], set()
            for d in b["dirs"]:
                if dir_cats.get(d) == {name}:
                    pure.append(d)
                else:
                    mixed.add(d)
            exact = [p for p in b["paths"] if os.path.dirname(p) in mixed]
            files = sorted(set(pure) | set(exact))
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
            roots=list(roots),
            scan_info=scan_info,
        ))
    return items


def _scan(names, app, label, cancel, progress):
    roots, skipped = find_app_roots(names, cancel, progress)
    info = ("已跳过不可访问的磁盘：" + "、".join(skipped)) if skipped else ""
    if progress:
        progress(f"{label}：共找到 {len(roots)} 个数据目录（已扫描全部本地磁盘）")
        for p in roots:
            progress("  · " + p)
        if info:
            progress(info)
    return _build_items(roots, app, cancel, progress, scan_info=info)


def scan_wechat(cancel, progress=None):
    return _scan(WECHAT_NAMES, "微信", "微信数据目录", cancel, progress)


def scan_wxwork(cancel, progress=None):
    return _scan(WXWORK_NAMES, "企业微信", "企业微信数据目录", cancel, progress)
