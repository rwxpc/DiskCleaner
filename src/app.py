# -*- coding: utf-8 -*-
"""DiskCleaner 主程序：侧边栏式 GUI + /scan 纯扫描模式（只出报告，不动文件）。"""
from __future__ import annotations
import os
import sys
import time
import queue
import shutil
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from core import (
    human_size, get_fixed_drives, cutoff_timestamp, files_older_than,
    send_to_recycle_bin, delete_permanent, move_preserving_tree,
    is_document, iter_files,
)
import wechat
import wps
import disktools
from ui import (
    C, F, VERSION, NAV_ICONS, setup_styles, flat_btn, ghost_btn, card_frame,
    RoundButton, risk_pill, Sidebar, StatCard, SweepCanvas, MagnifierCanvas,
)

APP_NAME = "DiskCleaner"
AGE_MAP = {"全部": 0, "30天前": 30, "90天前": 90, "180天前": 180, "360天前": 360}
# 支持「清理范围」时间筛选的三个专清模块（共用同一套下拉、默认值与筛选逻辑）
AGE_SCOPE_KEYS = ("wechat", "wxwork", "wps")
# 「扫描大文件」下拉选项：显示文案 -> 阈值(MB)
SIZE_CHOICES = ["100M以上", "200M以上", "500M以上", "1G以上", "2G以上", "4G以上"]
SIZE_MB_MAP = {"100M以上": 100, "200M以上": 200, "500M以上": 500,
               "1G以上": 1024, "2G以上": 2048, "4G以上": 4096}
COPYRIGHT = ["开发者：任我行电脑工作室", "微信号：RWXPC8"]
WPS_TRANSFER_DIR = r"D:\wps转存"  # WPS 文档默认转存位置

# 导航项：key, 标签, 图标
NAV = [
    ("checkup", "C盘清理", NAV_ICONS["checkup"]),
    ("wechat", "微信专清", NAV_ICONS["wechat"]),
    ("wxwork", "企业微信专清", NAV_ICONS["wxwork"]),
    ("wps", "WPS缓存专清", NAV_ICONS["wps"]),
    ("large", "扫描大文件", NAV_ICONS["large"]),
    ("log", "日志", NAV_ICONS["log"]),
]

PAGE_META = {
    "checkup": ("C盘清理", "逐项列出 C 盘 14 类可清理项：临时文件和日志文件、软件安装或更新残留文件、"
                "开发语言包缓存、字体缓存、预读取文件(Prefetch)、缩略图缓存、图标缓存、系统临时文件、"
                "Windows 更新缓存、Windows.old 残留目录、DirectX 着色器缓存、用户临时文件、"
                "浏览器缓存、系统错误报告。",
                "仅列出扫描到内容的类别；每项标注风险等级与删除后果。Windows.old 等高风险项默认不勾选。"),
    "wechat": ("微信专清", "扫描所有本地磁盘中的 WeChat Files 数据目录，按 7 类汇总（含新增「文档」）；文档与文件互不重复，聊天记录只统计不清理。", ""),
    "wxwork": ("企业微信专清", "扫描所有本地磁盘中的 WXWork 数据目录，按 7 类汇总（含新增「文档」）；文档与文件互不重复，聊天记录只统计不清理。", ""),
    "wps": ("WPS缓存专清", "枚举 Kingsoft 缓存目录，重点标注本地备份与云同步缓存；清理前可转存文档。", ""),
    "large": ("扫描大文件", "列出所选磁盘上的超大文件；双击可打开所在目录，勾选后可送入回收站。", ""),
    "log": ("日志", "所有扫描与清理动作的完整记录，同时写入本地日志文件。", ""),
}

# 各专清页对应的扫描函数
SCAN_FN = {
    "wechat": lambda cancel, progress: wechat.scan_wechat(cancel, progress),
    "wxwork": lambda cancel, progress: wechat.scan_wxwork(cancel, progress),
    "wps": lambda cancel, progress: wps.scan_wps(cancel, progress),
    "large": None,  # 运行时按所选磁盘构造
}


def resource_path(rel: str) -> str:
    if getattr(sys, "frozen", False):
        return os.path.join(getattr(sys, "_MEIPASS", os.path.dirname(sys.executable)), rel)
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), rel)


def build_report(sections) -> str:
    out = [
        f"{APP_NAME} 磁盘清理报告",
        f"开发者：任我行电脑工作室    微信号：RWXPC8",
        f"生成时间：{time.strftime('%Y-%m-%d %H:%M:%S')}",
        "=" * 72, "",
    ]
    grand = 0
    for title, items in sections:
        total = sum(i.size for i in items)
        grand += total
        out.append(f"【{title}】 {len(items)} 项，合计 {human_size(total)}")
        # v1.6.0：微信 / 企业微信报告里逐条列出所有本地磁盘上找到的数据目录
        roots, seen_roots = [], set()
        for it in items:
            for r in (getattr(it, "roots", None) or []):
                if r not in seen_roots:
                    seen_roots.add(r)
                    roots.append(r)
        if roots:
            out.append(f"  数据目录（共 {len(roots)} 个）：")
            for r in roots:
                out.append(f"    · {r}")
            out.append("")
        for it in items[:60]:
            out.append(f"  - {it.name} | {it.category} | {human_size(it.size)} | {it.file_count} 个文件")
            out.append(f"    {it.path or it.note}")
        if len(items) > 60:
            out.append(f"  ... 其余 {len(items) - 60} 项略")
        out.append("")
    out.append(f"总计：{human_size(grand)}")
    out.append("说明：本报告由扫描生成；纯扫描模式未修改或删除任何文件。")
    out.append("-" * 72)
    out.append("任我行电脑工作室  ·  微信号 RWXPC8")
    return "\n".join(out)


class ScanProgressDialog:
    """扫描中弹窗：环形动画 + 主状态 + 动态子状态 + 进度条 + 计数 + 取消。

    参考设计稿：标题「正在扫描 C 盘」、副标题「正在统计：…」、「4 / 13」、
    「取消扫描」按钮。所有扫描入口共用，互不干扰。
    """

    def __init__(self, parent, title, total, cancel_callback):
        self.total = max(int(total or 0), 1)
        self.current = 0
        self.cancel_callback = cancel_callback
        self.closed = False
        self.q = queue.Queue()

        self.top = tk.Toplevel(parent)
        self.top.title("正在扫描")
        self.top.transient(parent)
        self.top.resizable(False, False)
        self.top.configure(bg=C["page_bg"])
        self.top.protocol("WM_DELETE_WINDOW", self._on_cancel)

        box = tk.Frame(self.top, bg=C["card"], highlightbackground=C["border"],
                       highlightthickness=1)
        box.pack(padx=16, pady=16, fill="both", expand=True)

        # 运动放大镜动画（镜片沿文件带移动，扫过的文件块被放大高亮）
        self.mag = MagnifierCanvas(box, width=430, height=78)
        self.mag.pack(pady=(16, 6))

        self.title_var = tk.StringVar(value=title)
        tk.Label(box, textvariable=self.title_var, bg=C["card"], fg=C["text"],
                 font=F["title"]).pack(pady=(0, 6))

        self.sub_var = tk.StringVar(value="准备中…")
        tk.Label(box, textvariable=self.sub_var, bg=C["card"], fg=C["text_sub"],
                 font=F["body"], wraplength=400, justify="center").pack(pady=(0, 16))

        self.pb = ttk.Progressbar(box, mode="determinate", length=460,
                                  maximum=self.total, value=0)
        self.pb.pack(fill="x", padx=20)

        self.count_var = tk.StringVar(value=f"0 / {self.total}")
        tk.Label(box, textvariable=self.count_var, bg=C["card"], fg=C["text_mute"],
                 font=F["small"]).pack(anchor="e", padx=20, pady=(4, 12))

        flat_btn(box, "取消扫描", self._on_cancel,
                 bg=C["card"], fg=C["text"], active_bg=C["neutral_bg"],
                 padx=12, pady=5).pack(pady=(0, 18))

        # 居中
        self.top.update_idletasks()
        try:
            px = parent.winfo_rootx() + (parent.winfo_width() - 500) // 2
            py = parent.winfo_rooty() + (parent.winfo_height() - 320) // 2
            self.top.geometry(f"500x320+{max(px, 0)}+{max(py, 0)}")
        except Exception:
            self.top.geometry("500x320")

        self._poll()

    # --- 线程安全接口（供扫描 worker 调用）---
    def report(self, text, step=True):
        if not self.closed:
            self.q.put(("status", (text, step)))

    def finish(self):
        if not self.closed:
            self.q.put(("finish", None))

    def _on_cancel(self):
        if self.closed:
            return
        try:
            if self.cancel_callback:
                self.cancel_callback()
        finally:
            self.sub_var.set("正在取消扫描…")
            self.finish()

    def _poll(self):
        if self.closed:
            return
        try:
            while True:
                kind, payload = self.q.get_nowait()
                if kind == "status":
                    text, step = payload
                    self.sub_var.set(text)
                    if step and self.current < self.total:
                        self.current += 1
                        self.pb["value"] = self.current
                        self.count_var.set(f"{self.current} / {self.total}")
                    self.mag.set_progress(self.current / self.total)
                elif kind == "finish":
                    self.mag.finish()
                    self.top.after(320, self._close)
                    return
        except queue.Empty:
            pass
        self.top.after(80, self._poll)

    def _close(self):
        self.closed = True
        self.mag.stop()
        try:
            self.top.destroy()
        except Exception:
            pass


class DeleteProgressDialog:
    """删除实时进度小窗：显示当前正在删除的文件名与状态，完成后回调并关闭。"""

    def __init__(self, parent, title, on_finish=None):
        self.total = 0
        self.done = 0
        self.ok_count = 0
        self.reboot_count = 0
        self.failed = []
        self.reboot_on_locked = False
        self.on_finish = on_finish
        self.cancelled = threading.Event()

        self.top = tk.Toplevel(parent)
        self.top.title(title)
        self.top.resizable(False, False)
        self.top.transient(parent)
        self.top.configure(bg=C["page_bg"])
        self.top.protocol("WM_DELETE_WINDOW", self._on_close)

        box = tk.Frame(self.top, bg=C["card"], highlightbackground=C["border"],
                       highlightthickness=1)
        box.pack(padx=16, pady=16, fill="both", expand=True)

        tk.Label(box, text="正在清理文件…", bg=C["card"], fg=C["text"],
                 font=F["title"]).pack(anchor="w", padx=18, pady=(16, 4))
        # 动态扫地效果：扫把随真实清理进度推进，碎屑被扫入右侧回收桶
        self.sweep = SweepCanvas(box, width=430, height=78)
        self.sweep.pack(padx=18, pady=(0, 10))
        self.file_var = tk.StringVar(value="准备中…")
        tk.Label(box, textvariable=self.file_var, bg=C["card"], fg=C["primary"],
                 font=F["body_bold"], anchor="w", wraplength=440,
                 justify="left").pack(fill="x", padx=18, pady=(0, 10))

        self.pb = ttk.Progressbar(box, mode="determinate", length=460, maximum=100, value=0)
        self.pb.pack(fill="x", padx=18, pady=(0, 8))
        self.stat_var = tk.StringVar(value="0 / 0")
        tk.Label(box, textvariable=self.stat_var, bg=C["card"], fg=C["text_sub"],
                 font=F["body"]).pack(anchor="w", padx=18)
        self.detail_var = tk.StringVar(value="回收站 0  重启清理 0  失败 0")
        tk.Label(box, textvariable=self.detail_var, bg=C["card"], fg=C["success"],
                 font=F["small"]).pack(anchor="w", padx=18, pady=(2, 4))

        bottom = tk.Frame(box, bg=C["card"])
        bottom.pack(fill="x", padx=18, pady=(6, 16))
        flat_btn(bottom, "停止清理", self._on_close,
                 bg=C["neutral_bg"], fg=C["text"], active_bg=C["neutral_hover"],
                 padx=10, pady=4).pack(side="right")

        self.q = queue.Queue()
        # 居中显示
        self.top.update_idletasks()
        try:
            px = parent.winfo_rootx() + (parent.winfo_width() - 500) // 2
            py = parent.winfo_rooty() + (parent.winfo_height() - 350) // 2
            self.top.geometry(f"500x350+{max(px, 0)}+{max(py, 0)}")
        except Exception:
            self.top.geometry("500x350")
        self.top.after(80, self._poll)

    def start(self, items, days, collect_fn, reboot_on_locked=False):
        self.reboot_on_locked = reboot_on_locked
        self.file_var.set("正在收集待清理文件…")
        self.pb.configure(mode="indeterminate")
        self.pb.start(10)
        threading.Thread(target=self._work, args=(items, days, collect_fn),
                         daemon=True).start()

    def _work(self, items, days, collect_fn):
        def progress(i, t, path, status):
            if self.cancelled.is_set() and i < t:
                return
            self.q.put(("progress", (i, t, path, status)))

        try:
            recycle_targets, permanent_targets = [], []
            for it in items:
                paths = collect_fn(it, days)
                if getattr(it, "no_recycle", False):
                    permanent_targets.extend(paths)
                else:
                    recycle_targets.extend(paths)
            recycle_targets = list(dict.fromkeys(recycle_targets))
            permanent_targets = list(dict.fromkeys(permanent_targets))
            targets = recycle_targets + permanent_targets
            self.q.put(("collected", targets))
            if not targets:
                self.q.put(("done", (0, [], 0)))
                return

            cancel = lambda: self.cancelled.is_set()
            ok_count, failed, reboot_count = 0, [], 0
            if recycle_targets:
                ok, bad, reb = send_to_recycle_bin(
                    recycle_targets, progress=progress, cancel=cancel,
                    reboot_on_locked=self.reboot_on_locked)
                ok_count += ok
                failed.extend(bad)
                reboot_count += reb
            if permanent_targets and not self.cancelled.is_set():
                def perm_progress(i, t, path, status):
                    progress(len(recycle_targets) + i, len(targets), path, status)
                ok, bad, reb = delete_permanent(
                    permanent_targets, progress=perm_progress, cancel=cancel,
                    reboot_on_locked=self.reboot_on_locked)
                ok_count += ok
                failed.extend(bad)
                reboot_count += reb
            self.q.put(("done", (ok_count, failed, reboot_count)))
        except Exception as exc:
            self.q.put(("error", str(exc)))

    def _on_close(self):
        self.cancelled.set()

    def _poll(self):
        try:
            while True:
                kind, payload = self.q.get_nowait()
                if kind == "collected":
                    targets = payload
                    self.total = len(targets)
                    self.sweep.set_progress(0)
                    self.pb.stop()
                    self.pb.configure(mode="determinate", maximum=max(self.total, 1), value=0)
                    self.stat_var.set(f"0 / {self.total}")
                    continue
                if kind == "progress":
                    i, t, path, status = payload
                    self.done = i
                    if status == "reboot":
                        self.reboot_count += 1
                    elif status:
                        self.ok_count += 1
                    else:
                        self.failed.append(path)
                    self.file_var.set(os.path.basename(path))
                    self.pb["value"] = i
                    self.sweep.set_progress(i / max(t, 1))
                    self.stat_var.set(f"{i} / {t}")
                    self.detail_var.set(
                        f"回收站 {self.ok_count}  重启清理 {self.reboot_count}  "
                        f"失败 {len(self.failed)}")
                    try:
                        self.top.title(f"正在清理 {i}/{t} — {os.path.basename(path)}")
                    except Exception:
                        pass
                elif kind in ("done", "error"):
                    if kind == "done":
                        ok_count, failed, reboot_count = payload
                    else:
                        ok_count, failed, reboot_count = (
                            self.ok_count, self.failed, self.reboot_count)
                    self.file_var.set("清理完成" if kind == "done" else "清理出错")
                    self.detail_var.set(
                        f"回收站 {ok_count}  重启清理 {reboot_count}  失败 {len(failed)}")
                    self.pb["value"] = self.pb["maximum"]
                    self.sweep.finish()
                    self.top.after(700, lambda: self._finish(
                        ok_count, failed, reboot_count))
                    return
        except queue.Empty:
            pass
        self.top.after(80, self._poll)

    def _finish(self, ok_count, failed, reboot_count=0):
        self.sweep.stop()
        try:
            self.top.destroy()
        except Exception:
            pass
        if self.on_finish:
            self.on_finish(ok_count, failed, reboot_count)


def headless_scan():
    cancel = lambda: False

    def run(title, fn):
        try:
            return title, fn(cancel)
        except Exception:
            return title, []

    def say(msg):
        try:
            print(msg, flush=True)
        except Exception:
            pass

    drives = get_fixed_drives()
    sections = []
    for title, fn in (
        ("微信专清", wechat.scan_wechat),
        ("企业微信专清", wechat.scan_wxwork),
        ("WPS缓存专清", wps.scan_wps),
    ):
        say(f"正在扫描：{title} ...")
        sections.append(run(title, fn))
    say("正在扫描：全盘垃圾（可能较慢）...")
    try:
        junk = disktools.scan_junk(drives, cancel)
    except Exception:
        junk = []
    sections.append(("全盘垃圾扫描", junk))
    say("正在扫描：大文件 ≥4GB（可能较慢）...")
    try:
        large = disktools.scan_large_files(drives, 4096, cancel)
    except Exception:
        large = []
    sections.append(("扫描大文件(≥4GB)", large))
    report = build_report(sections)
    fname = f"DiskCleaner_扫描报告_{time.strftime('%Y%m%d_%H%M%S')}.txt"
    path = ""
    for folder in (os.getcwd(), os.path.expanduser("~")):
        candidate = os.path.join(folder, fname)
        try:
            with open(candidate, "w", encoding="utf-8") as fh:
                fh.write(report)
            path = candidate
            break
        except OSError:
            continue  # 当前目录只读 / 无权限时回退到用户目录
    try:
        print(report)
        print(f"\n报告已保存: {path}" if path
              else "\n警告：报告写入失败，以上为完整内容。")
    except Exception:
        pass
    return path, report


class App:
    def __init__(self, root):
        self.root = root
        root.title(f"{APP_NAME} v{VERSION} — 磁盘清理助手")
        root.geometry("1000x620")
        root.minsize(960, 540)
        ico = resource_path("app.ico")
        if os.path.exists(ico):
            try:
                root.iconbitmap(ico)
            except Exception:
                pass
        setup_styles(root)

        self.pages: dict[str, dict] = {}
        self.current = "checkup"
        self.log_lines: list[str] = []
        self._cleaning = False  # 防止重复点击「清理选中项」开出多个删除任务

        shell = tk.Frame(root, bg=C["bg"])
        shell.pack(fill="both", expand=True)
        logo = resource_path("logo_small.png")
        self.sidebar = Sidebar(shell, NAV, self.navigate, COPYRIGHT,
                               drives=get_fixed_drives(),
                               logo_path=logo if os.path.exists(logo) else None)
        self.sidebar.pack(side="left", fill="y")

        self.content = tk.Frame(shell, bg=C["page_bg"])
        self.content.pack(side="right", fill="both", expand=True)

        self._build_pages()
        self._build_log_data()
        self.navigate("checkup")
        self._refresh_disk_usage()
        # v1.10.0：窗口重新获得焦点时同步磁盘状态（例如用户在资源管理器
        # 清空回收站后切回程序），带 2 秒节流，避免频繁调用 Win32 API。
        self._last_disk_refresh = time.time()

        def _on_focus(_event):
            now = time.time()
            if now - self._last_disk_refresh < 2.0:
                return
            self._last_disk_refresh = now
            self._refresh_disk_usage()
        root.bind("<FocusIn>", _on_focus)
        self.root.after(120, self._poll)

    # ---------- 页面构建 ----------
    def _build_pages(self):
        for key, *_ in NAV:
            frame = tk.Frame(self.content, bg=C["page_bg"])
            self.pages[key] = dict(frame=frame, built=False)
        # C盘清理页
        self._build_checkup()
        # 功能页（全盘扫描已整合进C盘清理，不再单独建页）
        for key in ("wechat", "wxwork", "wps", "large"):
            self._build_scan_page(key)
        self._build_log_page()

    def _page_header(self, key):
        """返回页面公共头部容器（标题/副标题/右侧工具），工具区由各页填充。"""
        page = self.pages[key]["frame"]
        title, subtitle, _ = PAGE_META[key]
        hdr = tk.Frame(page, bg=C["page_bg"])
        hdr.pack(fill="x", padx=16, pady=(14, 8))
        left = tk.Frame(hdr, bg=C["page_bg"])
        left.pack(side="left", anchor="n")
        tk.Label(left, text=title, bg=C["page_bg"], fg=C["text"],
                 font=F["title"]).pack(anchor="w")
        tk.Label(left, text=subtitle, bg=C["page_bg"], fg=C["text_sub"],
                 font=F["subtitle"], wraplength=460, justify="left").pack(anchor="w", pady=(2, 0))
        # 右侧工具区
        right = tk.Frame(hdr, bg=C["page_bg"])
        right.pack(side="right", anchor="n")
        self.pages[key]["header_right"] = right
        return page

    def _header_actions(self, key, scan_command):
        """统一页面头部右侧工具栏（与「C盘清理」完全一致）。

        从左到右：取消全选 / 全选 / 清理选中项(红) / 一键扫描(蓝)。
        使用相同字体、配色、内边距与 pack 间距，保证各页布局层级一致。
        """
        right = self.pages[key]["header_right"]
        if scan_command is not None:
            flat_btn(right, "一键扫描", scan_command,
                     bg=C["primary"], fg=C["white"]).pack(side="right", padx=4)
        flat_btn(right, "清理选中项", lambda: self.clean_selected(key),
                 bg=C["danger"], fg=C["white"]).pack(side="right", padx=4)
        flat_btn(right, "全选", lambda: self.select_all(key, True),
                 bg=C["neutral_bg"], fg=C["text"], active_bg=C["neutral_hover"]).pack(side="right", padx=4)
        flat_btn(right, "取消全选", lambda: self.select_all(key, False),
                 bg=C["neutral_bg"], fg=C["text"], active_bg=C["neutral_hover"]).pack(side="right", padx=4)
        return right

    def _make_detail_panel(self, work, key):
        """右侧「项目详情」面板：内容区可滚动、底部单个按钮固定不随滚动。

        结构：detail(卡片) → actions(贴底) + scroller(可滚动内容区)
        scroller 内用 Canvas + 内部 Frame 承载全部文本，滚轮递归绑定到所有子控件。
        """
        detail = card_frame(work, width=236)
        detail.pack(side="right", fill="y", padx=(9, 0))
        detail.pack_propagate(False)  # 固定尺寸，避免空内容时塌成 1px 不可见

        # ---- 底部固定操作区（先 pack，始终贴底，不随内容滚动）----
        actions = tk.Frame(detail, bg=C["card"])
        actions.pack(side="bottom", fill="x", padx=12, pady=(4, 8))

        # v1.7.1：「位置」目录已支持点击直接打开，底部「打开所在文件夹」
        # 按钮功能重复，予以移除；底部仅保留选择/取消选择按钮。
        dtoggle = RoundButton(actions, "选择此项",
                              lambda k=key: self._toggle_detail_item(k),
                              variant="soft")
        dtoggle.pack(fill="x", ipady=0)
        dtoggle.configure(state="disabled")

        # ---- 可滚动内容区 ----
        scroller = tk.Frame(detail, bg=C["card"])
        scroller.pack(side="top", fill="both", expand=True)
        canvas = tk.Canvas(scroller, bg=C["card"], highlightthickness=0, bd=0)
        canvas.pack(side="left", fill="both", expand=True)
        vbar = tk.Scrollbar(scroller, orient="vertical", command=canvas.yview,
                            width=8, bg=C["border"], troughcolor=C["card"],
                            activebackground=C["neutral_hover"],
                            highlightthickness=0)
        vbar.pack(side="right", fill="y")
        canvas.configure(yscrollcommand=vbar.set)

        inner = tk.Frame(canvas, bg=C["card"])
        win = canvas.create_window((0, 0), window=inner, anchor="nw")
        WL = 196  # 文本换行宽度（236 - 滚动条 8 - 左右留白 24 - 余量 8）

        def _sync_scroll(_e=None):
            try:
                canvas.configure(scrollregion=canvas.bbox("all"))
            except Exception:
                pass

        def _sync_width(_e=None):
            w = canvas.winfo_width()
            if w > 1:
                canvas.itemconfigure(win, width=w)

        inner.bind("<Configure>", _sync_scroll, add="+")
        canvas.bind("<Configure>", _sync_width, add="+")

        def _on_wheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        def _bind_wheel(widget):
            widget.bind("<MouseWheel>", _on_wheel)
            for child in widget.winfo_children():
                _bind_wheel(child)

        tk.Label(inner, text="项目详情", bg=C["card"], fg=C["text_mute"],
                 font=F["small"]).pack(anchor="w", padx=12, pady=(9, 3))
        dsel = tk.Label(inner, text="点击左侧项目查看详情", bg=C["card"],
                        fg=C["text_mute"], font=F["body"], wraplength=WL,
                        justify="left")
        dsel.pack(anchor="w", padx=12, pady=(0, 8))

        meta = tk.Frame(inner, bg=C["card"])
        meta.pack(anchor="w", padx=12, pady=(0, 8), fill="x")
        dpill = tk.Canvas(meta, width=68, height=21, bg=C["card"],
                          highlightthickness=0)
        dpill.pack(side="left")
        self._draw_pill(dpill, "低风险")
        dsize = tk.Label(meta, text="—", bg=C["card"], fg=C["text"],
                         font=F["card_value"])
        dsize.pack(side="left", padx=(8, 0))

        tk.Label(inner, text="删除后果", bg=C["card"], fg=C["text_mute"],
                 font=F["small"]).pack(anchor="w", padx=12)
        dconseq = tk.Label(inner, text="—", bg=C["card"], fg=C["text_sub"],
                           font=F["body"], wraplength=WL, justify="left")
        dconseq.pack(anchor="w", padx=12, pady=(2, 6))

        tk.Label(inner, text="建议", bg=C["card"], fg=C["text_mute"],
                 font=F["small"]).pack(anchor="w", padx=12)
        dadvice = tk.Label(inner, text="—", bg=C["card"], fg=C["text_sub"],
                           font=F["body"], wraplength=WL, justify="left")
        dadvice.pack(anchor="w", padx=12, pady=(2, 6))

        tk.Label(inner, text="位置", bg=C["card"], fg=C["text_mute"],
                 font=F["small"]).pack(anchor="w", padx=12)
        # v1.7.0：位置区改为可点击的目录链接容器，由 _set_locations 动态填充。
        dpath = tk.Frame(inner, bg=C["card"])
        dpath.pack(anchor="w", padx=12, pady=(2, 6), fill="x")
        tk.Label(dpath, text="—", bg=C["card"], fg=C["text_mute"],
                 font=F["small"], wraplength=WL, justify="left").pack(anchor="w")

        if key == "wps":
            tk.Label(inner, text="长期方案：WPS → 备份中心 → 备份设置，"
                     "将本地备份目录改到 D 盘，避免 C 盘被占满。",
                     bg=C["tip_bg"], fg=C["tip_fg"], font=F["small"],
                     wraplength=WL, justify="left", padx=6, pady=4).pack(
                         fill="x", padx=12, pady=(0, 6))

        # 所有文本控件创建完成后再递归绑定滚轮，确保覆盖每个 Label
        inner.update_idletasks()
        _bind_wheel(inner)
        _sync_width()
        _sync_scroll()

        return dict(detail=detail, dsel=dsel, dpill=dpill, dsize=dsize,
                    dconseq=dconseq, dadvice=dadvice, dpath=dpath,
                    dtoggle=dtoggle,
                    detail_canvas=canvas, detail_scrollbar=vbar,
                    detail_inner=inner, detail_iid=None, detail_WL=WL)

    def _build_checkup(self):
        page = self.pages["checkup"]["frame"]
        self._page_header("checkup")
        # 提示条
        tip = tk.Frame(page, bg=C["success_bg"], highlightbackground=C["success_border"],
                       highlightthickness=1)
        tip.pack(fill="x", padx=16, pady=(0, 8))
        self.checkup_tip = tk.Label(tip, text="点击右上角「一键扫描」开始全盘扫描…",
                                    bg=C["success_bg"], fg=C["success"],
                                    font=F["body"], anchor="w", padx=10, pady=5)
        self.checkup_tip.pack(fill="x")
        # v1.5.1：14 类均为 C 盘固定路径，原「扫描磁盘」勾选栏已移除。
        # _selected_drives("checkup") 固定返回 ["C:"]，供扫描弹窗标题与进度文案使用。
        # 统计卡片
        stats = tk.Frame(page, bg=C["page_bg"])
        stats.pack(fill="x", padx=16, pady=(0, 8))
        self.stat_cards = {}
        for key, label, dot in (
            ("total", "可清理总量", C["primary"]),
            ("low", "低风险", C["success"]),
            ("mid", "中风险", C["warning"]),
            ("high", "高风险", C["danger"]),
        ):
            card = StatCard(stats, label, "0 B", "0 项", dot, width=158)
            card.pack(side="left", padx=(0, 7))
            self.stat_cards[key] = card
        # C盘清理表格区 + 项目详情面板（与其他功能页完全一致）
        work = tk.Frame(page, bg=C["page_bg"])
        work.pack(fill="both", expand=True, padx=16, pady=(0, 12))
        d = self._make_detail_panel(work, "checkup")  # 详情先占位，避免被表格挤掉
        table_card = card_frame(work)
        table_card.pack(side="left", fill="both", expand=True)
        cols = ("sel", "name", "size", "risk", "conseq")
        tree = ttk.Treeview(table_card, columns=cols, show="headings", height=14)
        for col, text, width in (
            ("sel", "", 38), ("name", "清理项目", 132),
            ("size", "大小 ▼", 68), ("risk", "风险", 56),
            ("conseq", "删除后果", 182),
        ):
            tree.heading(col, text=text)
            tree.column(col, width=width, anchor="w")
        tree.heading("size", command=lambda: self._sort_by_size("checkup"))
        vsb = ttk.Scrollbar(table_card, orient="vertical", command=tree.yview)
        # 滚动时同步重绘风险列彩色文字覆盖层
        tree.configure(yscrollcommand=lambda *a: (
            vsb.set(*a), self._redraw_risk_overlay("checkup")))
        tree.pack(side="left", fill="both", expand=True, padx=(1, 0), pady=1)
        vsb.pack(side="right", fill="y")
        tree.bind("<Button-1>", lambda e, k="checkup": self._on_tree_click(k, e))
        tree.bind("<<TreeviewSelect>>", lambda e, k="checkup": self._on_tree_select(k, e))
        tree.bind("<Configure>", lambda e: self._redraw_risk_overlay("checkup"))
        # v1.5.1：Tk 8.6.9 的 ttk.Treeview 不渲染 tag 的 foreground/background，
        # 风险列文字改由这个 Canvas 覆盖层自绘，保证低/中/高风险为绿/黄/红。
        risk_ov = tk.Canvas(table_card, bg=C["card"], highlightthickness=0, bd=0)
        risk_ov.bind("<Button-1>",
                     lambda e: self._on_risk_overlay_click("checkup", e))
        risk_ov.bind("<MouseWheel>",
                     lambda e: self._on_risk_overlay_wheel("checkup", e))
        self.pages["checkup"].update(
            built=True, tree=tree, items={}, checked={},
            risk_overlay=risk_ov, risk_header_h=None,
            queue=queue.Queue(), cancel=threading.Event(), scanning=False, **d,
        )

        # 头部工具按钮（统一样式，与其他页面一致）
        self._header_actions("checkup", lambda: self.start_checkup())

    def _build_scan_page(self, key):
        page = self.pages[key]["frame"]
        self._page_header(key)
        # 所有功能页（含「扫描大文件」）沿用完全一致的头部按钮组
        self._header_actions(key, lambda: self.start_scan(key))

        # 工具栏（磁盘/大小/时间范围等筛选项）
        bar = tk.Frame(page, bg=C["page_bg"])
        bar.pack(fill="x", padx=16, pady=(0, 6))
        if key == "large":
            # 扫描范围：下拉菜单（盘符 + 可用空间），并保留「全部磁盘」
            drives = get_fixed_drives()
            labels, mapping = [], {}
            for d in drives:
                try:
                    free = shutil.disk_usage(d).free / (1024 ** 3)
                    label = "%s  可用 %.1f GB" % (d, free)
                except Exception:
                    label = d
                labels.append(label)
                mapping[label] = d
            all_label = "全部磁盘"
            labels.insert(0, all_label)
            mapping[all_label] = "__ALL__"
            dv = tk.StringVar(value=labels[1] if len(labels) > 1 else labels[0])
            tk.Label(bar, text="扫描范围", bg=C["page_bg"], fg=C["text_sub"],
                     font=F["body"]).pack(side="left", padx=(0, 4))
            ttk.Combobox(bar, textvariable=dv, values=labels, state="readonly",
                         width=16, font=F["body"]).pack(side="left")
            self.pages[key]["drive_var"] = dv
            self.pages[key]["drive_labels"] = mapping
            self.pages[key]["all_drives"] = drives
            # 文件大小：下拉菜单式，6 档固定阈值
            # 扫描动作统一由头部「一键扫描」发起；筛选栏只保留两个下拉，
            # 不再放置与头部重复的「扫描大文件」「暂停」按钮。
            tk.Label(bar, text="文件大小", bg=C["page_bg"], fg=C["text_sub"],
                     font=F["body"]).pack(side="left", padx=(12, 4))
            sv = tk.StringVar(value="4G以上")
            ttk.Combobox(bar, textvariable=sv, values=SIZE_CHOICES,
                         state="readonly", width=10, font=F["body"]).pack(side="left")
            self.pages[key]["size_var"] = sv
        if key in AGE_SCOPE_KEYS:
            # 微信 / 企业微信 / WPS 三个专清共用同一套「清理范围」下拉：
            # 选项、默认值「全部」、只读样式与切换反馈完全一致。
            af = tk.Frame(bar, bg=C["page_bg"])
            af.pack(side="left")
            tk.Label(af, text="清理范围：", bg=C["page_bg"], fg=C["text_sub"],
                     font=F["body"]).pack(side="left")
            av = tk.StringVar(value="全部")
            ttk.Combobox(af, textvariable=av, values=list(AGE_MAP),
                         state="readonly", width=9).pack(side="left")
            self.pages[key]["age_var"] = av
            # 切换行为：与 WPS 一致，切换后立即记录并在下一次清理生效；
            # 不重扫、不改动表格（扫描结果始终展示全部命中项）。
            def _on_age_change(*_args, k=key, var=av):
                label = var.get() or "全部"
                try:
                    self.log(f"{PAGE_META[k][0]}：清理范围切换为「{label}」")
                except Exception:
                    pass
            av.trace_add("write", _on_age_change)

        # 状态提示 + 已选（操作按钮已统一放到页面头部）
        statusbar = tk.Frame(page, bg=C["page_bg"])
        statusbar.pack(fill="x", padx=16, pady=(0, 4))
        status = tk.Label(statusbar, text="等待扫描…", bg=C["page_bg"],
                          fg=C["text_sub"], font=F["small"], anchor="w")
        status.pack(side="left")
        sel_var = tk.StringVar(value="已选 0 项 / 0 B")
        tk.Label(statusbar, textvariable=sel_var, bg=C["page_bg"], fg=C["text"],
                 font=F["body_bold"]).pack(side="left", padx=12)

        # 表格 + 详情面板
        work = tk.Frame(page, bg=C["page_bg"])
        work.pack(fill="both", expand=True, padx=16, pady=(0, 12))
        table_card = card_frame(work)
        # pack 顺序关键：右侧详情面板必须先占位，否则 expand=True 的表格会
        # 先抢光横向空间，把详情面板挤成 1px 而完全不可见。
        # 因此 table_card 的实际 pack 放在详情面板创建之后。
        cols = ("sel", "cat", "name", "size", "count", "path")
        tree = ttk.Treeview(table_card, columns=cols, show="headings", height=14)
        heads = (
            ("sel", "选择", 38), ("cat", "类别", 66), ("name", "清理项", 112),
            ("size", "大小", 68), ("count", "文件数", 52), ("path", "路径 / 说明", 156),
        )
        for col, text, width in heads:
            tree.heading(col, text=text)
            tree.column(col, width=width, anchor="w")
        vsb = ttk.Scrollbar(table_card, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=vsb.set)
        tree.pack(side="left", fill="both", expand=True, padx=(1, 0), pady=1)
        vsb.pack(side="right", fill="y")
        tree.bind("<Button-1>", lambda e, k=key: self._on_tree_click(k, e))
        tree.bind("<<TreeviewSelect>>", lambda e, k=key: self._on_tree_select(k, e))
        if key == "large":
            tree.bind("<Double-1>", lambda e, k=key: self._open_location(k, e))

        d = self._make_detail_panel(work, key)
        table_card.pack(side="left", fill="both", expand=True)  # 详情先占位，再放表格

        self.pages[key].update(
            built=True, tree=tree, items={}, checked={},
            status=status, sel_var=sel_var,
            queue=queue.Queue(), cancel=threading.Event(), scanning=False, **d,
        )

    def _build_log_page(self):
        page = self.pages["log"]["frame"]
        self._page_header("log")
        right = self.pages["log"]["header_right"]
        flat_btn(right, "清空显示", lambda: self._clear_log(),
                 bg=C["neutral_bg"], fg=C["text"], active_bg=C["neutral_hover"],
                 padx=8, pady=4).pack(side="right", padx=4)
        flat_btn(right, "打开日志目录", lambda: self._open_log_dir(),
                 bg=C["neutral_bg"], fg=C["text"], active_bg=C["neutral_hover"],
                 padx=8, pady=4).pack(side="right", padx=4)
        flat_btn(right, "复制全部", lambda: self._copy_log(),
                 bg=C["neutral_bg"], fg=C["text"], active_bg=C["neutral_hover"],
                 padx=8, pady=4).pack(side="right", padx=4)

        box = card_frame(page)
        box.pack(fill="both", expand=True, padx=16, pady=(0, 12))
        self.log_text = tk.Text(box, bg=C["log_bg"], fg=C["log_fg"],
                                font=("Consolas", 8), relief="flat",
                                insertbackground=C["log_fg"], padx=9, pady=7)
        self.log_text.pack(fill="both", expand=True, padx=1, pady=1)
        self.pages["log"]["built"] = True

    def _build_log_data(self):
        self.log("构建通道：生产版 (prod)")
        self.log("开发者：任我行电脑工作室  微信号：RWXPC8")
        self.log(f"程序启动：{time.strftime('%Y-%m-%d %H:%M:%S')}")
        self.log("程序权限：已请求管理员权限")
        self.log("功能启动：clean=免登录、wechat=免登录、wps=免登录、feedback=免登录")
        self.log("安全机制：默认送入系统回收站（可还原）")

    # ---------- 导航 ----------
    def navigate(self, key):
        self.current = key
        self.sidebar.set_active(key)
        for k, pg in self.pages.items():
            if k == key:
                pg["frame"].pack(fill="both", expand=True)
            else:
                pg["frame"].pack_forget()

    # ---------- 日志 ----------
    def log(self, msg):
        line = f"[{time.strftime('%H:%M:%S')}] {msg}"
        self.log_lines.append(line)
        try:
            self.log_text.insert("end", line + "\n")
            self.log_text.see("end")
        except Exception:
            pass

    def _clear_log(self):
        self.log_text.delete("1.0", "end")
        self.log_lines.clear()

    def _copy_log(self):
        self.root.clipboard_clear()
        self.root.clipboard_append("\n".join(self.log_lines))

    def _open_log_dir(self):
        path = os.path.dirname(os.path.abspath(sys.argv[0]))
        try:
            os.startfile(path)
        except Exception:
            pass

    def _refresh_disk_usage(self):
        """重新读取各固定磁盘可用空间并同步到侧栏「本机磁盘状态」。

        v1.10.0：改为逐盘容错（单盘失败不影响其余盘）、异常不再静默吞掉；
        清理完成、延后补偿刷新与窗口重新激活时都会调用，读数同时返回供校验。
        """
        import ctypes

        def _warn(msg):
            try:
                self.log(msg)
            except Exception:
                pass

        info = {}
        try:
            drives = get_fixed_drives()
        except Exception as exc:
            _warn(f"本机磁盘状态：枚举磁盘失败 {exc}")
            drives = []
        for d in drives:
            try:
                free = ctypes.c_ulonglong(0)
                total = ctypes.c_ulonglong(0)
                ok = ctypes.windll.kernel32.GetDiskFreeSpaceExW(
                    ctypes.c_wchar_p(d), None,
                    ctypes.byref(total), ctypes.byref(free))
                if not ok or not total.value:
                    continue
                info[d[0] + ":"] = (free.value / 1024 ** 3,
                                    (1 - free.value / total.value) * 100,
                                    total.value / 1024 ** 3)
            except Exception as exc:
                _warn(f"本机磁盘状态：读取 {d} 失败 {exc}")
        try:
            self.sidebar.update_disk_usage(info)
        except Exception as exc:
            _warn(f"本机磁盘状态：刷新显示失败 {exc}")
        return info

    # ---------- 扫描 ----------
    def _risk_of(self, item):
        explicit = getattr(item, "risk", "")
        if explicit in ("低风险", "中风险", "高风险"):
            return explicit
        name = (item.name + item.category).lower()
        if any(x in name for x in ("聊天记录", "数据库", "msg")):
            return "高风险"
        if any(x in name for x in ("文件", "云", "备份")):
            return "中风险"
        return "低风险"

    def _scan_fn_for(self, key):
        if key == "large":
            pg = self.pages[key]
            drives = (pg.get("selected_drives") or pg.get("all_drives")
                      or [d for d, _ in pg.get("drive_vars", [])])
            size = pg.get("size_mb", 4096)
            return lambda cancel, progress: disktools.scan_large_files(
                drives, size, cancel, progress)
        return SCAN_FN[key]

    # 各扫描入口的预计阶段数（用于弹窗 i/total；仅影响展示，不影响扫描范围）
    SCAN_TOTAL = {
        "checkup": 14, "wechat": 8, "wxwork": 8, "wps": 8, "large": 4,
    }

    def _scan_title(self, key):
        if key == "checkup":
            drives = self._selected_drives("checkup")
            return f"正在扫描 {drives[0] if len(drives) == 1 else '全部磁盘'}"
        if key == "large":
            drives = self._selected_drives("large")
            return f"正在扫描 {drives[0] if len(drives) == 1 else '所选磁盘'}"
        if key in ("wechat", "wxwork"):
            return f"正在扫描所有本地磁盘 · {PAGE_META[key][0]}"
        return f"正在扫描 {PAGE_META[key][0]}"

    def start_scan(self, key):
        pg = self.pages[key]
        if pg.get("scanning"):
            return  # 已有扫描线程在跑，避免重复启动线程与多个进度弹窗
        pg["cancel"].clear()
        pg["scanning"] = True
        for iid in pg["tree"].get_children():
            pg["tree"].delete(iid)
        pg["items"].clear()
        pg["checked"].clear()
        pg["status"].configure(text="正在扫描…")
        # 主线程先读取 Tk 变量，避免后台线程访问导致 RuntimeError
        if key == "large":
            pg["selected_drives"] = self._selected_drives(key)
            pg["size_mb"] = SIZE_MB_MAP.get(self.pages[key]["size_var"].get(), 4096)
        dlg = ScanProgressDialog(
            self.root, self._scan_title(key), self.SCAN_TOTAL.get(key, 7),
            cancel_callback=lambda: pg["cancel"].set())
        pg["scan_dialog"] = dlg
        self.log(f"{PAGE_META[key][0]}：开始扫描")
        threading.Thread(target=self._worker, args=(key,), daemon=True).start()

    def start_checkup(self):
        """一键全盘扫描 14 类垃圾，汇总到C盘清理表格（不含其他专清模块）。"""
        pg = self.pages["checkup"]
        if pg.get("scanning"):
            return  # 已有扫描线程在跑，避免重复启动线程与多个进度弹窗
        pg["cancel"].clear()
        pg["scanning"] = True
        for iid in pg["tree"].get_children():
            pg["tree"].delete(iid)
        pg["items"].clear()
        pg["checked"].clear()
        ov = pg.get("risk_overlay")
        if ov:
            ov.delete("all")
            ov.place_forget()
        self.checkup_tip.configure(text="正在全盘扫描 14 类垃圾，请稍候…", fg=C["warning"])
        # 主线程先读取 Tk 变量
        pg["selected_drives"] = self._selected_drives("checkup")
        dlg = ScanProgressDialog(
            self.root, self._scan_title("checkup"), self.SCAN_TOTAL["checkup"],
            cancel_callback=lambda: pg["cancel"].set())
        pg["scan_dialog"] = dlg
        self.log("C盘清理：开始全盘扫描（14 类垃圾）")
        threading.Thread(target=self._checkup_worker, daemon=True).start()

    def _checkup_worker(self):
        """仅扫描图2列出的 14 类垃圾；不触碰微信/企业微信/WPS/扫描大文件等专清模块。"""
        pg = self.pages["checkup"]
        cancel = lambda: pg["cancel"].is_set()

        def report(msg):
            pg["queue"].put(("progress", msg))
            dlg = pg.get("scan_dialog")
            if dlg:
                dlg.report(msg, step=msg.startswith("正在统计："))

        all_items = []
        drives = pg.get("selected_drives") or get_fixed_drives()
        try:
            report("正在扫描 C 盘 14 类可清理项…")
            all_items = disktools.scan_junk(drives, cancel, report)
        except Exception as exc:
            pg["queue"].put(("error", f"全盘垃圾: {exc}"))
        pg["queue"].put(("done", all_items))

    def _worker(self, key):
        pg = self.pages[key]

        def report(msg):
            pg["queue"].put(("progress", msg))
            dlg = pg.get("scan_dialog")
            if dlg:
                dlg.report(msg, step=msg.startswith("正在统计："))

        try:
            items = self._scan_fn_for(key)(
                lambda: pg["cancel"].is_set(), report)
            pg["queue"].put(("done", items))
        except Exception as exc:
            pg["queue"].put(("error", str(exc)))

    def _poll(self):
        for key, pg in self.pages.items():
            q = pg.get("queue")
            if not q:
                continue
            while True:
                try:
                    kind, payload = q.get_nowait()
                except queue.Empty:
                    break
                if key == "checkup":
                    self._poll_checkup(kind, payload)
                    continue
                if kind == "progress":
                    pg["status"].configure(text=payload)
                elif kind == "done":
                    pg["scanning"] = False
                    self._close_scan_dialog(key)
                    self._fill_tree(key, payload)
                    pg["status"].configure(text=f"扫描完成：{len(payload)} 项")
                    self.log(f"{PAGE_META[key][0]}：扫描完成，{len(payload)} 项")
                    # v1.6.0：把跨磁盘找到的全部数据目录逐条写入日志与状态栏
                    if key in ("wechat", "wxwork"):
                        roots, info, seen_roots = [], "", set()
                        for it in payload:
                            info = info or getattr(it, "scan_info", "")
                            for r in (getattr(it, "roots", None) or []):
                                if r not in seen_roots:
                                    seen_roots.add(r)
                                    roots.append(r)
                        if roots:
                            letters = " ".join(sorted({r[:2].upper() for r in roots}))
                            pg["status"].configure(
                                text=f"扫描完成：{len(payload)} 项 · "
                                     f"找到 {len(roots)} 个数据目录（{letters}）")
                            self.log(f"{PAGE_META[key][0]}：共找到 {len(roots)} 个数据目录：")
                            for r in roots:
                                self.log(f"    {r}")
                        else:
                            self.log(f"{PAGE_META[key][0]}：未找到数据目录")
                        if info:
                            self.log(info)
                elif kind == "error":
                    pg["scanning"] = False
                    self._close_scan_dialog(key)
                    pg["status"].configure(text=f"扫描失败：{payload}")
                    self.log(f"{PAGE_META[key][0]}：扫描失败 {payload}")
        self.root.after(120, self._poll)

    def _close_scan_dialog(self, key):
        dlg = self.pages[key].get("scan_dialog")
        if dlg:
            dlg.finish()
            self.pages[key]["scan_dialog"] = None

    def _poll_checkup(self, kind, payload):
        pg = self.pages["checkup"]
        if kind == "progress":
            self.checkup_tip.configure(text=payload)
        elif kind == "done":
            pg["scanning"] = False
            self._close_scan_dialog("checkup")
            self._fill_tree("checkup", payload)
            total = sum(i.size for i in payload)
            self.checkup_tip.configure(
                text=f"✓ 扫描完成：发现 {len(payload)} 类可清理垃圾，合计 {human_size(total)}",
                fg=C["success"])
            self._update_stats(payload)
            self.log(f"C盘清理：扫描完成，{len(payload)} 类，合计 {human_size(total)}")
        elif kind == "error":
            pg["scanning"] = False
            self._close_scan_dialog("checkup")
            self.checkup_tip.configure(text=f"扫描出错：{payload}", fg=C["danger"])

    def _update_stats(self, items):
        risk = {"低风险": [], "中风险": [], "高风险": []}
        for it in items:
            risk[self._risk_of(it)].append(it)
        vals = {
            "total": (human_size(sum(i.size for i in items)), f"{len(items)} 项"),
            "low": (human_size(sum(i.size for i in risk["低风险"])), f"{len(risk['低风险'])} 项"),
            "mid": (human_size(sum(i.size for i in risk["中风险"])), f"{len(risk['中风险'])} 项"),
            "high": (human_size(sum(i.size for i in risk["高风险"])), f"{len(risk['高风险'])} 项"),
        }
        for key, card in self.stat_cards.items():
            # 重建数值显示
            for w in list(card.winfo_children()):
                w.destroy()
            dot = tk.Canvas(card, width=10, height=10, bg=C["card"], highlightthickness=0)
            dot.pack(anchor="w", padx=(14, 0), pady=(12, 0))
            color = {"total": C["primary"], "low": C["success"],
                     "mid": C["warning"], "high": C["danger"]}[key]
            dot.create_oval(1, 1, 9, 9, fill=color)
            label = {"total": "可清理总量", "low": "低风险", "mid": "中风险", "high": "高风险"}[key]
            tk.Label(card, text=label, bg=C["card"], fg=C["text_sub"],
                     font=F["card_label"]).pack(anchor="w", padx=14)
            row = tk.Frame(card, bg=C["card"])
            row.pack(fill="x", padx=14)
            tk.Label(row, text=vals[key][0], bg=C["card"], fg=C["text"],
                     font=F["card_value"]).pack(side="left")
            tk.Label(row, text="  " + vals[key][1], bg=C["card"],
                     fg=C["text_mute"], font=F["card_unit"]).pack(side="left")

    def _fill_tree(self, key, items):
        pg = self.pages[key]
        tree = pg["tree"]
        for iid in tree.get_children():
            tree.delete(iid)
        pg["items"].clear()
        pg["checked"].clear()
        for it in items:
            risk = self._risk_of(it)
            if getattr(it, "no_clean", False):
                mark = "—"  # 只统计不清理，禁止勾选
            else:
                mark = "☑" if it.default_checked else "☐"
            if key == "checkup":
                values = (mark, it.name, human_size(it.size), risk,
                          getattr(it, "consequence_short", "") or "—")
            else:
                desc = it.note or it.path
                # v1.6.0：微信/企业微信在「路径 / 说明」列标注跨磁盘数据目录数量，
                # 让用户一眼看到结果确实覆盖了所有本地磁盘，而非只有 C 盘。
                if key in ("wechat", "wxwork"):
                    rs = [r for r in (getattr(it, "roots", None) or []) if r]
                    if rs:
                        letters = " ".join(sorted({r[:2].upper() for r in rs}))
                        desc = "%d 个数据目录 · %s" % (len(rs), letters)
                values = (mark, it.category, it.name, human_size(it.size),
                          it.file_count, desc)
            iid = tree.insert("", "end", values=values)
            tree.item(iid, tags=(risk,))
            pg["items"][iid] = it
            pg["checked"][iid] = it.default_checked
        # 风险等级 tag：保留作数据标注（其他页面沿用）。
        # 注意：Tk 8.6.9 的 ttk.Treeview 不渲染 tag 的 foreground/background，
        # C盘清理页的彩色文字由 _redraw_risk_overlay 的 Canvas 覆盖层绘制。
        for level, fg, bg in (("低风险", C["success"], C["low_bg"]),
                              ("中风险", C["warning"], C["mid_bg"]),
                              ("高风险", C["danger"], C["high_bg"])):
            if key == "checkup":
                tree.tag_configure(level, background=bg, foreground=fg)
            else:
                tree.tag_configure(level, foreground=fg)
        self._update_selected(key)
        first = tree.get_children()
        if first:
            self._show_detail(key, first[0])
        else:
            self._clear_detail(key)
        if key == "checkup":
            self._redraw_risk_overlay(key)

    def _on_tree_click(self, key, event):
        """点击任意列都刷新详情；只有点「选择」列才切换勾选。"""
        pg, tree = self.pages[key], self.pages[key]["tree"]
        if tree.identify("region", event.x, event.y) != "cell":
            return
        iid = tree.identify_row(event.y)
        if not iid:
            return
        self._show_detail(key, iid)
        if tree.identify_column(event.x) == "#1":
            if getattr(pg["items"].get(iid), "no_clean", False):
                return  # 只统计不清理的项目不参与勾选
            new = not pg["checked"].get(iid, False)
            pg["checked"][iid] = new
            tree.set(iid, "sel", "☑" if new else "☐")
            self._update_selected(key)

    def _on_tree_select(self, key, event):
        tree = self.pages[key]["tree"]
        sel = tree.selection()
        if sel:
            self._show_detail(key, sel[0])
        if key == "checkup":
            self._redraw_risk_overlay(key)

    # ---------- v1.5.1 风险列彩色文字覆盖层 ----------
    def _redraw_risk_overlay(self, key):
        """Tk 8.6.9 下 Treeview 的 tag 前景/背景不渲染，风险列文字由 Canvas 自绘。"""
        pg = self.pages[key]
        tree, ov = pg["tree"], pg.get("risk_overlay")
        if ov is None or pg.get("_risk_redrawing"):
            return
        pg["_risk_redrawing"] = True
        try:
            tree.update_idletasks()
            rows = tree.get_children()
            if not rows:
                ov.delete("all"); ov.place_forget()
                return
            box = None
            for iid in rows:
                box = tree.bbox(iid, "risk")
                if box:
                    break
            if not box:
                ov.delete("all"); ov.place_forget()
                return
            col_x, _vy, col_w, _rh = box
            if pg.get("risk_header_h") is None:
                first = tree.bbox(rows[0], "risk")
                pg["risk_header_h"] = first[1] if first else 0
            header_h = pg["risk_header_h"]
            height = tree.winfo_height() - header_h
            if height <= 0:
                return
            ov.place(in_=tree, x=col_x, y=header_h, width=col_w, height=height)
            ov.delete("all")
            sel_bg = (ttk.Style().lookup("Treeview", "background", ["selected"])
                      or C["primary"])
            fg_map = {"低风险": C["success"], "中风险": C["warning"],
                      "高风险": C["danger"]}
            selected = set(tree.selection())
            for iid in rows:
                b = tree.bbox(iid, "risk")
                if not b:
                    continue
                it = pg["items"].get(iid)
                if it is None:
                    continue
                _x, y, _w, rh = b
                cy = y - header_h
                # 只画完全可见的行，避免部分可见行在表格底边露出彩色残影
                if cy < 0 or cy + rh > height - 2:
                    continue
                risk = self._risk_of(it)
                picked = iid in selected
                ov.create_rectangle(0, cy, col_w, cy + rh,
                                    fill=sel_bg if picked else C["card"], outline="")
                ov.create_text(8, cy + rh / 2, text=risk, anchor="w",
                               fill=fg_map.get(risk, C["text"]), font=F["body"])
        finally:
            pg["_risk_redrawing"] = False

    def _on_risk_overlay_click(self, key, event):
        """覆盖层会拦截点击，这里转发为「选中该行并刷新详情」。"""
        pg = self.pages[key]
        tree = pg["tree"]
        iid = tree.identify_row(event.y + (pg.get("risk_header_h") or 0))
        if iid:
            tree.selection_set(iid)
            tree.focus(iid)
            self._show_detail(key, iid)
            self._redraw_risk_overlay(key)

    def _on_risk_overlay_wheel(self, key, event):
        """覆盖层转发滚轮，保持表格可滚动。"""
        self.pages[key]["tree"].yview_scroll(
            -1 if event.delta > 0 else 1, "units")

    @staticmethod
    def _short_path(p, limit=96):
        return p if len(p) <= limit else p[:40] + "…" + p[-52:]

    @staticmethod
    def _draw_pill(cv, level):
        """在 Canvas 上画一枚圆角胶囊风险标签。"""
        cv.delete("all")
        bg, fg = {"低风险": (C["low_bg"], C["success"]),
                  "中风险": (C["mid_bg"], C["warning"]),
                  "高风险": (C["high_bg"], C["danger"])}.get(
                      level, (C["low_bg"], C["success"]))
        w, h = int(cv["width"]), int(cv["height"])
        cv.create_oval(0, 0, h, h, fill=bg, outline="")
        cv.create_oval(w - h, 0, w, h, fill=bg, outline="")
        cv.create_rectangle(h // 2, 0, w - h // 2, h, fill=bg, outline="")
        cv.create_text(w // 2, h // 2, text=level, fill=fg, font=F["pill"])

    def _sort_by_size(self, key):
        """点击「大小」表头在降序 / 升序间切换。"""
        pg = self.pages[key]
        tree = pg["tree"]
        desc = not pg.get("size_desc", True)
        pg["size_desc"] = desc
        rows = [(pg["items"][iid].size, iid) for iid in tree.get_children()
                if iid in pg["items"]]
        rows.sort(key=lambda t: t[0], reverse=desc)
        for idx, (_, iid) in enumerate(rows):
            tree.move(iid, "", idx)
        tree.heading("size", text="大小 " + ("▼" if desc else "▲"))

    def _toggle_detail_item(self, key):
        """详情面板底部按钮：切换当前项目的勾选状态。"""
        pg = self.pages[key]
        iid = pg.get("detail_iid")
        if not iid or iid not in pg["items"]:
            return
        new = not pg["checked"].get(iid, False)
        pg["checked"][iid] = new
        pg["tree"].set(iid, "sel", "☑" if new else "☐")
        self._update_selected(key)
        self._show_detail(key, iid)

    @staticmethod
    def _consequence(it):
        """优先使用扫描项自带的逐项文案，否则按类型推断（兼容其他模块）。"""
        custom = getattr(it, "consequence", "")
        if custom:
            return (custom, getattr(it, "advice", "") or "建议先确认内容再清理。")
        name = it.name
        if getattr(it, "no_clean", False):
            return ("该类仅用于统计，不参与清理，不会被删除。",
                    "无需操作，仅供了解占用情况。")
        if getattr(it, "no_recycle", False) or "回收站" in name:
            return ("文件将被永久删除，无法从回收站还原。",
                    "高风险：请先确认没有需要还原的文件。")
        if "临时文件" in name:
            return ("只删除临时文件，程序下次运行时会自动重建，"
                    "不涉及任何个人数据。", "放心删，建议每次都勾上。")
        if "缓存" in name or "cache" in name.lower():
            return ("仅清理缓存副本，程序下次运行时会按需重建，"
                    "不会删除账号、文档等个人数据。",
                    "可清理；清理后首次打开可能略慢。")
        return ("选中项将送入系统回收站，可随时还原。",
                "建议先确认内容再清理。")

    def _set_locations(self, pg, paths, note=""):
        """v1.7.0：把详情面板「位置」区渲染成可点击的目录链接列表。

        每个路径显示为蓝色下划线标签，点击后调用 _open_dir 打开对应本地
        文件夹（若指向文件则打开其所在文件夹）；目录不存在或无权限访问时
        由 _open_dir 弹出明确提示。内容动态重建后同步刷新滚动区域。
        """
        holder = pg["dpath"]
        for w in list(holder.winfo_children()):
            w.destroy()
        WL = pg.get("detail_WL", 196)
        link_font = (F["small"][0], F["small"][1], "underline")
        cv = pg["detail_canvas"]

        def _wheel(e):
            try:
                cv.yview_scroll(int(-1 * (e.delta / 120)), "units")
            except Exception:
                pass

        def _brief(p):
            """链接显示用紧凑路径：盘符 + … + 末两级目录名。

            点击回调仍使用完整真实路径，这里只为在 236px 窄面板里让
            多条数据目录都能一屏可读，不至于互相挤到不可见。
            """
            if len(p) <= 34:
                return p
            drive, _ = os.path.splitdrive(p)
            parent = os.path.basename(os.path.dirname(p))
            name = os.path.basename(p)
            return "%s\\…\\%s\\%s" % (drive, parent, name)

        if note:
            tk.Label(holder, text=note, bg=C["card"], fg=C["text_mute"],
                     font=F["small"], wraplength=WL, justify="left",
                     anchor="w").pack(anchor="w", fill="x")
        if not paths:
            tk.Label(holder, text="—（汇总项，暂无具体路径）", bg=C["card"],
                     fg=C["text_mute"], font=F["small"], wraplength=WL,
                     justify="left", anchor="w").pack(anchor="w", fill="x")
        else:
            for p in paths:
                lbl = tk.Label(holder, text="• " + _brief(p),
                               bg=C["card"], fg=C["primary"], font=link_font,
                               wraplength=WL, justify="left", anchor="w",
                               cursor="hand2")
                lbl.pack(anchor="w", fill="x", pady=(1, 0))
                lbl.bind("<Button-1>", lambda e, path=p: self._open_dir(path))
                lbl.bind("<Enter>",
                         lambda e, w=lbl: w.configure(fg=C["primary_hover"]))
                lbl.bind("<Leave>",
                         lambda e, w=lbl: w.configure(fg=C["primary"]))
        # 动态新建的控件不会继承滚轮绑定，统一补绑
        for w in holder.winfo_children():
            w.bind("<MouseWheel>", _wheel)
        self._refresh_detail_scroll(pg)

    def _open_dir(self, path):
        """打开「位置」列表里点击的目录；不存在 / 无权限时给出明确提示。"""
        if not path:
            messagebox.showwarning(APP_NAME, "该位置没有有效路径。")
            return
        target = path
        try:
            if os.path.isfile(target):
                target = os.path.dirname(target) or target
        except OSError:
            pass
        if not target or not os.path.exists(target):
            messagebox.showwarning(
                APP_NAME, "目录不存在或已被清理，无法打开：\n\n" + path)
            return
        if not os.path.isdir(target):
            messagebox.showwarning(
                APP_NAME, "该位置不是文件夹，无法打开：\n\n" + path)
            return
        try:
            os.listdir(target)  # 探测访问权限，避免静默失败
        except PermissionError:
            messagebox.showwarning(
                APP_NAME,
                "没有权限访问该目录，请以管理员身份运行后重试：\n\n" + path)
            return
        except OSError as exc:
            messagebox.showwarning(
                APP_NAME, "无法访问该目录：\n\n%s\n\n%s" % (path, exc))
            return
        try:
            os.startfile(target)
        except OSError as exc:
            messagebox.showwarning(
                APP_NAME, "无法打开该文件夹：\n\n%s\n\n%s" % (path, exc))
        except Exception as exc:
            messagebox.showwarning(
                APP_NAME, "打开文件夹失败：\n\n%s\n\n%s" % (path, exc))

    def _clear_detail(self, key):
        pg = self.pages[key]
        if "dsel" not in pg:
            return
        pg["detail_iid"] = None
        pg["dsel"].configure(text="点击左侧项目查看详情",
                             fg=C["text_mute"], font=F["body"])
        pg["dsize"].configure(text="—")
        self._draw_pill(pg["dpill"], "低风险")
        pg["dconseq"].configure(text="—")
        pg["dadvice"].configure(text="—")
        self._set_locations(pg, [], "")
        pg["dtoggle"].configure(text="选择此项", state="disabled")
        self._refresh_detail_scroll(pg)

    def _refresh_detail_scroll(self, pg):
        """内容变化后同步滚动区域并回到顶部，保证长文本可滚动查看。"""
        cv, inner = pg.get("detail_canvas"), pg.get("detail_inner")
        if cv is None or inner is None:
            return
        try:
            inner.update_idletasks()
            cv.configure(scrollregion=cv.bbox("all"))
            cv.yview_moveto(0)
        except Exception:
            pass

    def _show_detail(self, key, iid):
        """把选中项的名称/风险/大小/删除后果/建议/真实位置写入详情面板。"""
        pg = self.pages[key]
        it = pg["items"].get(iid)
        if not it or "dsel" not in pg:
            return
        pg["detail_iid"] = iid
        risk = self._risk_of(it)
        pg["dsel"].configure(text=it.name, fg=C["text"], font=F["detail_title"])
        pg["dsize"].configure(text=human_size(it.size))
        pg["dtoggle"].configure(
            state="disabled" if getattr(it, "no_clean", False) else "normal")
        self._draw_pill(pg["dpill"], risk)
        conseq, advice = self._consequence(it)
        pg["dconseq"].configure(text=conseq, fg=C["text_sub"])
        pg["dadvice"].configure(text=advice, fg=C["text_sub"])
        # v1.7.0：位置区改为可点击目录列表，点击直接打开对应本地文件夹。
        roots = [r for r in (getattr(it, "roots", None) or []) if r]
        paths = [p for p in (it.files or []) if p]
        if roots:
            note = "共找到 %d 个数据目录，点击可打开：" % len(roots)
            locs = list(roots)
        else:
            # 线性去重：旧实现用 `p not in locs` 逐条查找，目录内容成千上万时
            # 是 O(n²) 卡顿；这里用 set 计数，只保留前 8 条用于展示。
            seen, locs = set(), []
            for p in ([it.path] if it.path else []) + list(paths):
                if not p or p in seen:
                    continue
                seen.add(p)
                locs.append(p)
            note = "点击路径可打开所在文件夹：" if locs else ""
            hidden = max(0, len(locs) - 8)
            locs = locs[:8]
            if hidden:
                note += "\n另有 %d 个位置未列出" % hidden
        self._set_locations(pg, locs, note)
        pg["dtoggle"].configure(
            text="取消选择此项" if pg["checked"].get(iid) else "选择此项")
        self._refresh_detail_scroll(pg)

    def _open_location(self, key, event):
        pg, tree = self.pages[key], self.pages[key]["tree"]
        iid = tree.identify_row(event.y)
        if not iid:
            return
        it = pg["items"].get(iid)
        if it and it.path:
            folder = it.path if os.path.isdir(it.path) else os.path.dirname(it.path)
            try:
                os.startfile(folder)
            except Exception:
                pass

    def _selected_drives(self, key):
        pg = self.pages[key]
        if key == "checkup":
            # v1.5.1：勾选栏已移除，14 类均为 C 盘固定路径，固定返回 C:。
            return ["C:"]
        if key == "large" and "drive_labels" in pg:
            d = pg["drive_labels"].get(pg["drive_var"].get())
            if d == "__ALL__":
                return list(pg.get("all_drives") or [])
            return [d] if d else list(pg.get("all_drives") or [])[:1]
        dvars = pg.get("drive_vars", [])
        chosen = [d for d, v in dvars if v.get()]
        return chosen or [d for d, _ in dvars]

    def select_all(self, key, value):
        pg = self.pages[key]
        for iid, it in pg["items"].items():
            if getattr(it, "no_clean", False):
                pg["checked"][iid] = False
                pg["tree"].set(iid, "sel", "—")
                continue
            pg["checked"][iid] = value
            pg["tree"].set(iid, "sel", "☑" if value else "☐")
        self._update_selected(key)

    def _update_selected(self, key):
        pg = self.pages[key]
        chosen = [it for iid, it in pg["items"].items() if pg["checked"].get(iid)]
        label = f"已选 {len(chosen)} 项 / {human_size(sum(i.size for i in chosen))}"
        if "sel_var" in pg:
            pg["sel_var"].set(label)

    # ---------- 清理 ----------
    def _collect_files(self, item, days):
        """展开为实际文件/目录路径列表；只统计项(no_clean)不产出任何目标。

        days > 0 时目录不再整目录删除，而是只取其中早于截止时间的旧文件，
        使三个专清页（微信 / 企业微信 / WPS）的「清理范围」下拉真正生效
        （v1.9.1 已修复原先该下拉对目录项完全无效的问题）。
        """
        if getattr(item, "no_clean", False):
            return []
        cutoff = cutoff_timestamp(days)
        targets = []
        for entry in (item.files or ([item.path] if item.path else [])):
            if not entry:
                continue
            if os.path.isdir(entry):
                if cutoff:
                    targets.extend(files_older_than(entry, days))
                else:
                    targets.append(entry)
            elif os.path.isfile(entry):
                try:
                    if not cutoff or os.path.getmtime(entry) < cutoff:
                        targets.append(entry)
                except OSError:
                    pass
        return targets

    def _ask_wps_choice(self, count, size_text):
        dlg = tk.Toplevel(self.root)
        dlg.title("检测到文档文件")
        dlg.transient(self.root)
        dlg.resizable(False, False)
        dlg.configure(bg=C["card"])
        # 内容先建好，最后再 grab_set：避免建窗异常时留下"空窗+抓取锁"导致界面冻结
        tk.Label(dlg, text=f"检测到 {count} 个文档文件（{size_text}），",
                 bg=C["card"], fg=C["text"], font=F["body_bold"],
                 justify="left", anchor="w").pack(fill="x", padx=18, pady=(16, 2))
        tk.Label(dlg, text="包含 Word / 表格 / 演示 / PDF 等。请选择处理方式：",
                 bg=C["card"], fg=C["text_sub"], font=F["body"],
                 justify="left", anchor="w").pack(fill="x", padx=18, pady=(0, 6))
        tk.Label(dlg, text=f"默认转存位置：{WPS_TRANSFER_DIR}",
                 bg=C["card"], fg=C["primary"], font=F["body_bold"],
                 justify="left", anchor="w").pack(fill="x", padx=18, pady=(0, 8))
        result = {"v": "cancel"}

        def choose(v):
            result["v"] = v
            try:
                dlg.grab_release()
            except Exception:
                pass
            dlg.destroy()

        box = tk.Frame(dlg, bg=C["card"], padx=18, pady=4)
        box.pack(fill="x")
        flat_btn(box, f"转存到 {WPS_TRANSFER_DIR}（推荐）", lambda: choose("transfer_default"),
                 bg=C["primary"], fg=C["white"]).pack(fill="x", pady=3)
        flat_btn(box, "转存到其他位置…", lambda: choose("transfer_custom"),
                 bg=C["neutral_bg"], fg=C["text"], active_bg=C["neutral_hover"]).pack(fill="x", pady=3)
        flat_btn(box, "直接清理", lambda: choose("delete"),
                 bg=C["danger"], fg=C["white"]).pack(fill="x", pady=3)
        flat_btn(box, "取消", lambda: choose("cancel"),
                 bg=C["neutral_bg"], fg=C["text"], active_bg=C["neutral_hover"]).pack(fill="x", pady=3)
        tk.Label(dlg, text="取消后不会删除任何文件。", bg=C["card"], fg=C["text_mute"],
                 font=F["small"]).pack(anchor="w", padx=18, pady=(6, 14))
        dlg.update_idletasks()
        try:
            px = self.root.winfo_rootx() + (self.root.winfo_width() - 440) // 2
            py = self.root.winfo_rooty() + (self.root.winfo_height() - 310) // 2
            dlg.geometry(f"440x310+{max(px, 0)}+{max(py, 0)}")
        except Exception:
            dlg.geometry("440x310")
        dlg.protocol("WM_DELETE_WINDOW", lambda: choose("cancel"))
        dlg.lift()
        dlg.grab_set()
        dlg.focus_force()
        dlg.wait_window()
        return result["v"]

    def clean_selected(self, key):
        if self._cleaning:
            messagebox.showinfo(APP_NAME, "已有清理任务正在进行，请等待完成。")
            return
        pg = self.pages[key]
        chosen = [it for iid, it in pg["items"].items()
                  if pg["checked"].get(iid) and not getattr(it, "no_clean", False)]
        skipped = [it for iid, it in pg["items"].items()
                   if pg["checked"].get(iid) and getattr(it, "no_clean", False)]
        if not chosen:
            messagebox.showinfo(APP_NAME, "请先勾选要清理的项目。")
            return
        total = sum(i.size for i in chosen)
        perm = sum(1 for i in chosen if getattr(i, "no_recycle", False))
        # v1.10.0：微信 / 企业微信 / WPS 三个专清共用「清理范围」下拉，
        # 在弹确认框之前统一解析，确保提示、日志与实际筛选口径一致。
        age_label = "全部"
        days = 0
        if key in AGE_SCOPE_KEYS:
            age_label = pg["age_var"].get() or "全部"
            days = AGE_MAP.get(age_label, 0)
        scope_hint = (f"清理范围：{age_label}" +
                      ("（只清理该时间之前的文件，较新文件保留）" if days else "（不限时间）"))
        note = ("\n其中部分项目将被永久删除、无法还原。" if perm else
                "\n文件将送入系统回收站（可还原）。")
        if skipped:
            note += f"\n已跳过 {len(skipped)} 个「只统计不清理」项目。"
        if key in AGE_SCOPE_KEYS:
            note += f"\n{scope_hint}。"
        if not messagebox.askyesno(APP_NAME,
                                   f"已选择 {len(chosen)} 项，共 {human_size(total)}。{note}\n\n"
                                   "确定清理吗？"):
            return

        if key == "wps":  # C盘清理 14 类中无 WPS 项，原后半条件为死代码
            docs = []
            for it in chosen:
                for fp in iter_files(it.path):
                    if is_document(fp):
                        docs.append(fp)
            if docs:
                doc_size = sum(os.path.getsize(f) for f in docs if os.path.exists(f))
                choice = self._ask_wps_choice(len(docs), human_size(doc_size))
                if choice == "cancel":
                    self.log("清理已取消（检测到文档文件）")
                    return
                if choice in ("transfer_default", "transfer_custom"):
                    if choice == "transfer_default":
                        dest = WPS_TRANSFER_DIR
                        try:
                            os.makedirs(dest, exist_ok=True)  # 默认目录不存在时自动创建
                        except OSError:
                            dest = ""
                            messagebox.showwarning(APP_NAME,
                                                   f"无法创建默认转存目录 {WPS_TRANSFER_DIR}，请手动选择位置。")
                    else:
                        init = WPS_TRANSFER_DIR if os.path.isdir(WPS_TRANSFER_DIR) else (
                            "D:\\" if os.path.isdir("D:\\") else os.path.expanduser("~"))
                        dest = filedialog.askdirectory(
                            title="选择文档转存文件夹", initialdir=init)
                    if not dest:
                        return
                    moved, failed = move_preserving_tree(docs, dest)
                    self.log(f"已转存 {moved} 个文档到 {dest}" +
                             (f"，失败 {len(failed)} 个" if failed else ""))

        # 用实时进度小窗执行删除：显示正在删除的文件名与状态，完成后立即刷新列表
        self.log(f"{PAGE_META[key][0]}：开始清理 {len(chosen)} 项" +
                 (f" · {scope_hint}" if key in AGE_SCOPE_KEYS else ""))

        # 大文件页可能是用户重要数据，不启用「重启后删除」；
        # 临时/缓存类（C盘清理、微信、企业微信、WPS）才对被占用项登记重启清理。
        reboot_ok = key != "large"

        def on_finish(ok_count, failed, reboot_count=0):
            self._cleaning = False
            self.log(f"清理：已送入回收站 {ok_count} 项，" +
                     (f"已安排重启清理 {reboot_count} 项，" if reboot_count else "") +
                     (f"失败 {len(failed)} 项" if failed else "无失败") +
                     (f" · {scope_hint}" if key in AGE_SCOPE_KEYS else ""))
            self._refresh_disk_usage()
            # 文件系统 / 回收站元数据可能有落盘延迟，稍后再同步一次，
            # 保证「本机磁盘状态」显示的是清理后的最新读数。
            self.root.after(1200, self._refresh_disk_usage)
            # 删除完成后立即刷新当前列表
            if key == "checkup":
                self.start_checkup()
            else:
                self.start_scan(key)
            msg = f"清理完成：{ok_count} 项已送入回收站（可还原）。"
            if key in AGE_SCOPE_KEYS:
                msg += f"\n{scope_hint}。"
            if ok_count and not perm:
                msg += ("\n提示：清理项进入回收站后仍占用磁盘空间，"
                        "清空回收站后「本机磁盘状态」的可用空间才会增加。")
            if reboot_count:
                msg += (f"\n{reboot_count} 项被其他程序占用，已安排在下次重启时自动删除。"
                        "\n这些文件重启前仍在磁盘上，重启清理不可还原。")
            if failed:
                msg += f"\n失败 {len(failed)} 项（无权限或路径失效）。"
            messagebox.showinfo(APP_NAME, msg)

        dlg = DeleteProgressDialog(
            self.root, f"{PAGE_META[key][0]} — 实时清理进度", on_finish=on_finish)
        self._cleaning = True
        try:
            dlg.start(chosen, days, self._collect_files, reboot_on_locked=reboot_ok)
        except Exception:
            self._cleaning = False
            raise


def main():
    scan_mode = any(
        a.replace("\\", "/").rstrip("/").split("/")[-1].lstrip("-").lower() == "scan"
        for a in sys.argv[1:]
    )
    if scan_mode:
        headless_scan()
        return
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
