# -*- coding: utf-8 -*-
"""「C盘清理」与「扫描大文件」的扫描实现。

「C盘清理」逐项列出 C 盘上 12 类可清理项（系统目录与当前用户目录），
每一项自带风险等级、删除后果、建议与表格短标注，界面可逐行标注展示。
个别只统计项（no_clean）只统计占用、不参与清理；高风险项默认不勾选，由用户自行判断。
"""
from __future__ import annotations
import glob
import os
from core import ScanItem, iter_files, path_stats


def _home() -> str:
    return os.environ.get("USERPROFILE", os.path.expanduser("~"))


def _local() -> str:
    return os.environ.get("LOCALAPPDATA", os.path.join(_home(), "AppData", "Local"))


def _windir() -> str:
    return os.environ.get("WINDIR", r"C:\Windows")


def _programdata() -> str:
    return os.environ.get("PROGRAMDATA", r"C:\ProgramData")


def _system32() -> str:
    return os.path.join(_windir(), "System32")


def _chrome_roots():
    """常见 Chromium 内核浏览器的 User Data 目录（Chrome / Edge / 360 等）。"""
    return [
        os.path.join(_local(), "Google", "Chrome", "User Data"),
        os.path.join(_local(), "Microsoft", "Edge", "User Data"),
    ]


def _browser_paths():
    out = []
    for root in _chrome_roots():
        for profile in ("Default", "*"):
            for cache in ("Cache", "Code Cache", "GPUCache"):
                out.append(os.path.join(root, profile, cache))
    # IE / 旧版 Edge 的临时网文件
    out.append(os.path.join(_local(), "Microsoft", "Windows", "INetCache", "*"))
    return out


def _install_residue_paths():
    """软件安装 / 更新残留：各类应用下载、装完就不再使用的安装包与更新缓存。

    扫描范围参考 DiskMate「更新器残留安装包」(key=updaters) 的设置：
      * 扫描根是当前用户的 %LOCALAPPDATA%（不是 C:\\Windows 或 ProgramData）；
      * 枚举其一级子目录，目录名包含 update / updater 即收录；
      * 追加 Ollama\\updates、electron\\Cache 两个应用更新缓存目录。
    在此基础上补充几个同类的「应用更新器下载缓存」（Chrome / Edge 更新器、
    SquirrelTemp），它们同样只是下载下来的安装包，装完即可删。

    **不再扫描** Windows Installer 补丁缓存 ($PatchCache$)、ProgramData\\Package
    Cache、Downloaded Program Files、ClickOnce、ClickToRun 等系统级安装缓存：
    这些是修复 / 卸载 / 回退软件时可能要用到的原始安装包，删除有副作用，
    不属于「装完就没用」的残留，故从本类别中移除。
    """
    local = _local()
    found: list[str] = []
    # ① DiskMate 主干：LocalAppData 一级目录中名字含 update 的更新器目录
    try:
        for name in os.listdir(local):
            if "update" not in name.lower():
                continue
            p = os.path.join(local, name)
            if os.path.isdir(p) and not os.path.islink(p):
                found.append(p)
    except OSError:
        pass
    # ② DiskMate 固定的两个应用更新缓存
    found.append(os.path.join(local, "Ollama", "updates"))
    found.append(os.path.join(local, "electron", "Cache"))
    # ③ 同类补充：常见更新器的下载缓存（同为「已下载的安装包」）
    found.extend([
        os.path.join(local, "Google", "Update", "Download"),
        os.path.join(local, "Microsoft", "EdgeUpdate", "Download"),
        os.path.join(local, "SquirrelTemp"),
    ])
    # 去重、只保留确实存在的目录
    seen, out = set(), []
    for p in found:
        if not p or not os.path.isdir(p):
            continue
        key = os.path.normcase(os.path.abspath(p))
        if key in seen:
            continue
        seen.add(key)
        out.append(p)
    return out


# C 盘 12 类可清理项。paths 支持 * 通配（缩略图/图标缓存是 .db 文件，不是目录）；
# content_only=True 表示只清目录内容、保留目录本身，避免破坏系统/程序依赖的关键目录；
# no_clean=True 表示只统计占用、绝不参与清理。
JUNK_CATEGORIES = [
    dict(
        name="临时文件和日志文件",
        paths=lambda: [
            os.path.join(_windir(), "Logs"),
            os.path.join(_windir(), "System32", "LogFiles"),
            os.path.join(_windir(), "debug"),
            os.path.join(_windir(), "Panther"),
        ],
        risk="低风险", checked=True,
        note="系统运行日志、安装日志（C:\\Windows\\Logs、System32\\LogFiles 等）",
        consequence="仅删除历史日志与安装记录，不影响系统运行和已安装的软件；"
                    "日后排查系统故障时会缺少历史记录。",
        advice="可放心清理；若正在排查系统问题，建议先保留日志。",
        short="仅删历史日志，无系统影响",
        content_only=True,
    ),
    dict(
        name="软件安装或更新残留文件",
        paths=_install_residue_paths,
        risk="低风险", checked=True,
        note="各类应用下载、装完就不再使用的安装包与更新缓存（%LOCALAPPDATA% 下名称含 "
             "update / updater 的更新器目录，以及 Ollama\\updates、electron\\Cache、"
             "Chrome / Edge / Squirrel 更新下载目录等）",
        consequence="只清理应用下载完成的安装包与更新缓存，已安装的软件、系统补丁与个人文件"
                    "均不受影响；日后应用需要更新时会自行重新下载。不触碰 Windows Installer "
                    "补丁缓存与程序安装包缓存，因此不影响软件的修复 / 卸载 / 回退。",
        advice="低风险，可放心清理，建议每次都勾上；若某个应用正在下载更新，"
               "被占用文件会被跳过或安排重启后清理。",
        short="删已下载安装包，可重新下载",
        content_only=True,
        show_roots=True,
    ),
    dict(
        name="预读取文件(Prefetch)",
        paths=lambda: [
            os.path.join(_windir(), "Prefetch"),
        ],
        risk="中风险", checked=False,
        note="Windows 预读取加速数据（C:\\Windows\\Prefetch）",
        consequence="删除后程序与开机首次启动会略慢，Windows 会在后续使用中自动重建"
                    "预读数据；不影响任何个人文件。",
        advice="不必频繁清理，系统会自动重建；空间紧张时再勾选。",
        short="首次启动略慢，自动重建",
        content_only=True,
    ),
    dict(
        name="缩略图缓存",
        paths=lambda: [
            os.path.join(_local(), "Microsoft", "Windows", "Explorer", "thumbcache_*.db"),
            os.path.join(_local(), "Microsoft", "Windows", "Explorer", "ThumbCache", "*"),
        ],
        risk="低风险", checked=True,
        note="资源管理器缩略图缓存数据库（thumbcache_*.db）",
        consequence="只清空缩略图缓存，首次打开含图片的文件夹时会重新生成预览、略慢；"
                    "不会删除或改动任何原始图片。",
        advice="可放心清理，系统会自动重建。",
        short="缩略图重建，原图不动",
        content_only=False,
    ),
    dict(
        name="图标缓存",
        paths=lambda: [
            os.path.join(_local(), "IconCache.db"),
            os.path.join(_local(), "Microsoft", "Windows", "Explorer", "iconcache_*.db"),
        ],
        risk="中风险", checked=False,
        note="桌面与资源管理器图标缓存（IconCache.db / iconcache_*.db）",
        consequence="桌面与资源管理器图标可能短暂显示为空白或旧图标，重启资源管理器"
                    "或重启电脑后自动重建；不影响程序功能与数据。",
        advice="仅在图标显示异常时清理；必要时重启资源管理器。",
        short="图标短暂异常，自动重建",
        content_only=False,
    ),
    dict(
        name="系统临时文件",
        paths=lambda: [
            os.path.join(_windir(), "Temp"),
        ],
        risk="低风险", checked=True,
        note="系统临时目录 C:\\Windows\\Temp 中的内容（保留目录本身）",
        consequence="只删除临时文件，程序下次运行时按需重建，不涉及个人数据；"
                    "被占用的文件会安排重启后清理。",
        advice="放心删，建议每次都勾上。",
        short="临时文件自动重建",
        content_only=True,
    ),
    dict(
        name="Windows 更新缓存",
        paths=lambda: [
            os.path.join(_windir(), "SoftwareDistribution", "Download"),
        ],
        risk="低风险", checked=True,
        note="Windows 更新下载缓存 C:\\Windows\\SoftwareDistribution\\Download（C 盘占用大头）",
        consequence="只删除已下载的更新包与分片，不影响已安装的补丁与系统运行；"
                    "若此刻正在下载更新会中断本次下载，重新检查更新即可自动补齐。",
        advice="可放心清理，通常能释放数 GB；清理后首次检查更新会重新下载。",
        short="更新包会自动重新下载",
        content_only=True,
    ),
    dict(
        name="Windows.old 残留目录",
        paths=lambda: [
            os.path.join(os.path.splitdrive(_windir())[0] + os.sep, "Windows.old"),
        ],
        risk="高风险", checked=False,
        note="升级大版本后遗留的旧系统与旧版本组件（C:\\Windows.old，常达 10–30 GB）",
        consequence="删除后无法回退到升级前的 Windows 版本，也无法再用旧系统文件修复；"
                    "虽送入回收站可还原，但目录极大、占用回收站空间且还原耗时。"
                    "刚升级完请确认新系统稳定后再处理。",
        advice="高风险：请确认新系统已稳定运行再清理。更推荐用系统自带『设置 → 系统 → "
               "存储 → 临时文件』或『磁盘清理 → 以前的 Windows 安装』清理。"
               "组件存储 (WinSxS) 不在本项内，需用 DISM 命令处理，本工具不直接删除。",
        short="删除后无法回退旧系统",
        content_only=False,
    ),
    dict(
        name="DirectX 着色器缓存",
        paths=lambda: [
            os.path.join(_local(), "Microsoft", "DirectX", "Shader Cache"),
            os.path.join(_local(), "D3DSCache"),
            os.path.join(_windir(), "System32", "D3DSCache"),
            os.path.join(_local(), "NVIDIA", "DXCache"),
            os.path.join(_local(), "AMD", "DxCache"),
        ],
        risk="低风险", checked=True,
        note="游戏与图形程序的着色器编译缓存（DirectX Shader Cache）",
        consequence="游戏与图形程序首次运行时需重新编译着色器，可能短暂卡顿；"
                    "不影响存档、设置与程序功能。",
        advice="可清理；大型游戏较多时首次加载会稍久。",
        short="着色器重建，首次略卡",
        content_only=True,
    ),
    dict(
        name="用户临时文件",
        paths=lambda: [
            os.path.join(_local(), "Temp"),
        ],
        risk="低风险", checked=True,
        note="用户临时目录 C:\\Users\\<用户名>\\AppData\\Local\\Temp 中的内容（保留目录本身）",
        consequence="只删除 Temp 文件夹内容并保留目录本身，程序下次运行时自动重建，"
                    "不涉及个人数据；被进程占用项安排重启后清理。",
        advice="放心删，建议每次都勾上。",
        short="临时文件自动重建",
        content_only=True,
    ),
    dict(
        name="浏览器缓存",
        paths=_browser_paths,
        risk="中风险", checked=False,
        note="Chrome / Edge 等浏览器的网页、代码与 GPU 缓存（含 INetCache）",
        consequence="仅清理网页缓存副本，首次打开网页略慢；账号、书签、历史记录、"
                    "扩展、Cookie 与下载文件均不受影响。",
        advice="可清理；不会删除任何个人数据。若依赖离线网页，建议先确认。",
        short="首次开网页略慢",
        content_only=True,
    ),
    dict(
        name="系统错误报告",
        paths=lambda: [
            os.path.join(_programdata(), "Microsoft", "Windows", "WER"),
            os.path.join(_local(), "Microsoft", "Windows", "WER"),
        ],
        risk="低风险", checked=True,
        note="Windows 错误报告 WER 归档（C:\\ProgramData\\Microsoft\\Windows\\WER 等）",
        consequence="只删除历史崩溃与错误报告归档，不影响系统运行；"
                    "排查程序崩溃原因时会缺少诊断记录。",
        advice="可放心清理；正在排查蓝屏或软件崩溃时建议先保留。",
        short="只删报告归档，无系统影响",
        content_only=True,
    ),
]


def _expand(patterns) -> list[str]:
    """展开路径候选（支持 * 通配），只保留确实存在的目录或文件，并去重。"""
    out: list[str] = []
    for p in patterns:
        if not p:
            continue
        if any(ch in p for ch in "*?["):
            try:
                out.extend(glob.glob(p))
            except OSError:
                pass
        elif os.path.exists(p):
            out.append(p)
    seen, uniq = set(), []
    for p in out:
        if not os.path.exists(p):
            continue
        key = os.path.normcase(os.path.abspath(p))
        if key in seen:
            continue
        seen.add(key)
        uniq.append(p)
    return uniq


def scan_junk(drives, cancel, progress=None) -> list[ScanItem]:
    """按固定 12 类逐项统计 C 盘可清理项，每项自带风险等级与删除后果。

    drives 参数保留以兼容调用方（C盘清理入口与 /scan 报告）；这些类别路径
    固定位于 C 盘系统目录与当前用户目录，与所选磁盘无关。
    """
    items: list[ScanItem] = []
    for cat in JUNK_CATEGORIES:
        if cancel():
            break
        name = cat["name"]
        if progress:
            progress(f"正在统计：{name}")
        size = count = 0
        files: list[str] = []
        paths = _expand(cat["paths"]())
        no_clean = bool(cat.get("no_clean", False))
        for p in paths:
            if cancel():
                break
            if os.path.isdir(p) and not os.path.islink(p):
                s, c = path_stats(p, cancel)
                size += s
                count += c
                if no_clean:
                    continue  # 只统计占用，不生成任何清理目标
                if cat.get("content_only", True):
                    # 只清目录「内容」，保留目录本身（系统 / 程序依赖的关键目录）
                    try:
                        children = [os.path.join(p, e) for e in os.listdir(p)]
                    except OSError:
                        children = []
                    files.extend(children or [p])
                else:
                    files.append(p)
            elif os.path.isfile(p):
                # 缩略图 / 图标缓存等缓存数据库文件本身就是清理目标
                try:
                    size += os.path.getsize(p)
                    count += 1
                except OSError:
                    pass
                if not no_clean:
                    files.append(p)
        # 只列出扫描到实际内容的类别：目录不存在、或目录下没有任何文件
        # （size 与 count 均为 0）时不进入列表，避免显示一堆 0 B 的空类别。
        if size <= 0 and count <= 0:
            continue
        items.append(ScanItem(
            path=paths[0] if paths else "", name=name, category="垃圾文件",
            size=size, file_count=count, default_checked=cat["checked"],
            note=cat["note"], files=files, risk=cat["risk"], no_clean=no_clean,
            consequence=cat["consequence"], advice=cat["advice"],
            consequence_short=cat["short"],
            # 动态发现型类别（软件安装 / 更新残留）把所有命中目录交给详情面板，
            # 「位置」逐条列出可点击目录，而不是列一堆目录下的子文件。
            roots=paths if cat.get("show_roots") else [],
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
