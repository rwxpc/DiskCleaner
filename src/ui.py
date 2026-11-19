# -*- coding: utf-8 -*-
"""DiskCleaner UI 主题与可复用组件（参考 DiskMate 风格）。"""
from __future__ import annotations
import tkinter as tk
from tkinter import ttk

VERSION = "1.2.0"  # 版本号单一来源，app.py 与侧栏共用

# ---------- 配色 ----------
# v1.2.0 主题「精密仪器」：深墨蓝控制台侧栏 + 冷白数据区。
# 侧栏与其文字色成对定义，保证深底对比度；语义色与主色同调。
C = {
    # 品牌主色（精确靛蓝）
    "primary": "#2E6BF2",
    "primary_hover": "#2459D6",
    "primary_light": "#EAF1FE",
    # 侧栏（深墨蓝控制台）
    "sidebar": "#151E32",
    "sidebar_hover": "#202C47",
    "sidebar_active": "#26395E",
    "sidebar_line": "#2B3A56",
    "sidebar_text": "#E9EEF8",
    "sidebar_sub": "#9AA8C2",
    "sidebar_mute": "#6F7D99",
    # 主区
    "bg": "#FFFFFF",
    "page_bg": "#F3F6FA",
    "card": "#FFFFFF",
    "border": "#E2E8F1",
    "text": "#172033",
    "text_sub": "#5D6A80",
    "text_mute": "#94A0B4",
    "neutral_bg": "#EDF1F7",
    "neutral_hover": "#DDE4EF",
    # 语义色
    "danger": "#E14B4B",
    "danger_hover": "#C93C3C",
    "success": "#0E9F6E",
    "success_bg": "#E7F7F0",
    "success_border": "#C4E9D8",
    "warning": "#D98816",
    "warning_bg": "#FFF4E5",
    "tip_bg": "#FFF8E8",
    "tip_fg": "#8A6D00",
    "high_bg": "#FDECEC",
    "mid_bg": "#FFF3E2",
    "low_bg": "#E7F7F0",
    "log_bg": "#111827",
    "log_fg": "#CBD5E1",
    "white": "#FFFFFF",
}

F = {
    "logo": ("Microsoft YaHei UI", 16, "bold"),
    "logo_sub": ("Microsoft YaHei UI", 9),
    "title": ("Microsoft YaHei UI", 22, "bold"),
    "subtitle": ("Microsoft YaHei UI", 10),
    "nav": ("Microsoft YaHei UI", 10),
    "nav_small": ("Microsoft YaHei UI", 9),
    "card_label": ("Microsoft YaHei UI", 10),
    "card_value": ("Microsoft YaHei UI", 22, "bold"),
    "card_unit": ("Microsoft YaHei UI", 9),
    "body": ("Microsoft YaHei UI", 10),
    "body_bold": ("Microsoft YaHei UI", 10, "bold"),
    "small": ("Microsoft YaHei UI", 9),
    "btn": ("Microsoft YaHei UI", 10, "bold"),
    "pill": ("Microsoft YaHei UI", 9, "bold"),
    "admin": ("Microsoft YaHei UI", 9, "bold"),
}

NAV_ICONS = {
    "checkup": "✓", "wechat": "✆", "wxwork": "▦", "wps": "▤",
    "junk": "◎", "large": "▣", "log": "≡", "about": "?",
}


def setup_styles(root):
    st = ttk.Style()
    try:
        st.theme_use("clam")
    except Exception:
        pass
    st.configure("Treeview", background=C["card"], fieldbackground=C["card"],
                 foreground=C["text"], rowheight=34, borderwidth=0,
                 font=F["body"])
    st.configure("Treeview.Heading", background="#EDF2F9", foreground=C["text_sub"],
                 font=F["body_bold"], borderwidth=0, relief="flat")
    st.map("Treeview.Heading", background=[("active", C["primary_light"])])
    st.configure("Card.TFrame", background=C["card"], relief="flat")
    st.configure("TCombobox", fieldbackground=C["card"], background=C["card"],
                 foreground=C["text"], arrowcolor=C["text_sub"], borderwidth=1)
    st.configure("Horizontal.TProgressbar", background=C["primary"],
                 troughcolor="#DDE5F0", borderwidth=0, thickness=6)
    # 深墨蓝侧栏专用进度条（磁盘占用），避免浅色槽在深底上突兀
    st.configure("Sidebar.Horizontal.TProgressbar", background=C["primary"],
                 troughcolor=C["sidebar_line"], borderwidth=0, thickness=6)


def flat_btn(parent, text, command, *, bg=None, fg=None, font=None,
             padx=14, pady=6, active_bg=None, width=None):
    """扁平圆润按钮（tk.Button 实现，便于自定义配色）。"""
    bg = bg or C["primary"]
    fg = fg or C["white"]
    active_bg = active_bg or C["primary_hover"]
    return tk.Button(
        parent, text=text, command=command, bg=bg, fg=fg, font=font or F["btn"],
        activebackground=active_bg, activeforeground=fg, relief="flat", bd=0,
        padx=padx, pady=pady, width=width, cursor="hand2", highlightthickness=0,
    )


def ghost_btn(parent, text, command, *, padx=12, pady=6, font=None):
    """白底描边按钮。"""
    b = tk.Button(
        parent, text=text, command=command, bg=C["card"], fg=C["text"],
        font=font or F["body"], activebackground=C["primary_light"],
        relief="flat", bd=1, padx=padx, pady=pady, cursor="hand2",
    )
    b.configure(highlightbackground=C["border"], highlightthickness=1)
    return b


def card_frame(parent, **kw):
    """白色卡片容器（浅边框）。"""
    f = tk.Frame(parent, bg=C["card"], highlightbackground=C["border"],
                 highlightthickness=1, **kw)
    return f


def risk_pill(parent, text, level):
    colors = {
        "低风险": (C["low_bg"], C["success"]),
        "中风险": (C["mid_bg"], C["warning"]),
        "高风险": (C["high_bg"], C["danger"]),
    }
    bg, fg = colors.get(level, (C["low_bg"], C["success"]))
    return tk.Label(parent, text=level, bg=bg, fg=fg, font=F["pill"],
                    padx=9, pady=2)


class Sidebar(tk.Frame):
    """左侧导航栏：Logo、导航、语言/版本、磁盘使用、管理员状态、版权。"""

    def __init__(self, parent, nav_items, on_nav, copyright_lines, drives=None,
                 logo_path=None, on_about=None):
        tk.Frame.__init__(self, parent, bg=C["sidebar"], width=232)
        self.pack_propagate(False)
        self.on_nav = on_nav
        self.nav_btns = {}
        self.drives = list(drives or ["C:\\", "D:\\"])
        self.logo_img = None
        if logo_path:
            try:
                self.logo_img = tk.PhotoImage(file=logo_path)
            except Exception:
                self.logo_img = None
        self._build(nav_items, copyright_lines, on_about)

    def _build(self, nav_items, copyright_lines, on_about):
        # Logo（图案与软件 icon 一致）
        logo = tk.Frame(self, bg=C["sidebar"])
        logo.pack(fill="x", padx=18, pady=(14, 10))
        if self.logo_img is not None:
            tk.Label(logo, image=self.logo_img, bg=C["sidebar"]).pack(side="left")
        else:  # 图标加载失败时回退为绘制的圆形对勾
            badge = tk.Canvas(logo, width=34, height=34, bg=C["sidebar"], highlightthickness=0)
            badge.pack(side="left")
            badge.create_oval(2, 2, 34, 34, fill=C["primary"])
            badge.create_line(10, 18, 16, 24, 25, 12, fill=C["white"], width=3,
                              capstyle="round", joinstyle="round")
        txt = tk.Frame(logo, bg=C["sidebar"])
        txt.pack(side="left", padx=9)
        tk.Label(txt, text="DiskCleaner", bg=C["sidebar"], fg=C["sidebar_text"],
                 font=F["logo"]).pack(anchor="w")
        tk.Label(txt, text="磁盘清理助手", bg=C["sidebar"], fg=C["sidebar_sub"],
                 font=F["logo_sub"]).pack(anchor="w")

        # 导航（深底：未激活=侧栏底，hover=稍亮，激活=靛蓝黑底+亮字）
        for key, label, icon in nav_items:
            btn = tk.Label(self, text=f"  {icon}   {label}", bg=C["sidebar"],
                           fg=C["sidebar_sub"], font=F["nav"], anchor="w",
                           cursor="hand2", padx=14, pady=8)
            btn.pack(fill="x", padx=12, pady=1)
            btn.bind("<Button-1>", lambda e, k=key: self.on_nav(k))
            btn.bind("<Enter>", lambda e, b=btn, k=key: self._nav_hover(b, k, True))
            btn.bind("<Leave>", lambda e, b=btn, k=key: self._nav_hover(b, k, False))
            self.nav_btns[key] = btn

        # 磁盘状态标题（可滚动区，盘符较多时不挤掉底部版权信息）
        tk.Label(self, text="本机磁盘状态", bg=C["sidebar"], fg=C["sidebar_sub"],
                 font=F["body_bold"], anchor="w").pack(fill="x", padx=18, pady=(10, 4))
        self.disk_bars = {}
        disk_wrap = tk.Frame(self, bg=C["sidebar"])
        disk_wrap.pack(fill="x", padx=14)

        canvas = tk.Canvas(disk_wrap, bg=C["sidebar"], highlightthickness=0,
                           width=180, height=196)
        vbar = ttk.Scrollbar(disk_wrap, orient="vertical", command=canvas.yview)
        disk_holder = tk.Frame(canvas, bg=C["sidebar"])

        def sync_region():
            """按实际内容刷新滚动范围（内容增减或文字变化后调用）。"""
            try:
                canvas.update_idletasks()
                bbox = canvas.bbox("all")
                if bbox:
                    canvas.configure(scrollregion=bbox)
            except Exception:
                pass

        win_id = canvas.create_window((0, 0), window=disk_holder, anchor="nw")
        # 内部容器宽度始终跟随画布，不产生横向滚动
        canvas.bind("<Configure>", lambda e: canvas.itemconfig(win_id, width=e.width))
        disk_holder.bind("<Configure>", lambda e: sync_region())
        canvas.configure(yscrollcommand=vbar.set)
        # 先放滚动条再放画布，避免画布 expand 抢占全部横向空间把滚动条挤成 1px
        vbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        def on_wheel(event):
            canvas.yview_scroll(-1 if event.delta > 0 else 1, "units")
            return "break"  # 阻止事件继续传递，避免主界面误滚动

        def bind_wheel(widget):
            # 关键：滚动事件必须绑定在所有子控件上，否则悬停在文字/进度条上时滚轮失效
            widget.bind("<MouseWheel>", on_wheel)
            for child in widget.winfo_children():
                bind_wheel(child)

        canvas.bind("<MouseWheel>", on_wheel)
        for drive in self.drives:
            row = tk.Frame(disk_holder, bg=C["sidebar"])
            row.pack(fill="x", pady=(4, 0))
            lbl = tk.Label(row, text=f"{drive[0]}: 检测中…", bg=C["sidebar"],
                           fg=C["sidebar_sub"], font=F["small"], anchor="w")
            lbl.pack(fill="x")
            pb = ttk.Progressbar(row, style="Sidebar.Horizontal.TProgressbar", length=186,
                                 mode="determinate", maximum=100, value=0)
            pb.pack(fill="x", pady=(2, 0))
            total = tk.Label(row, text="", bg=C["sidebar"], fg=C["sidebar_mute"],
                             font=F["small"], anchor="w")
            total.pack(fill="x")
            self.disk_bars[drive] = (lbl, pb, total)
        bind_wheel(disk_holder)
        self._disk_canvas = canvas
        self._sync_disk_region = sync_region
        self.after_idle(sync_region)

        # 底部区域（版权 / 管理员 / 版本）
        bottom = tk.Frame(self, bg=C["sidebar"])
        bottom.pack(side="bottom", fill="x", padx=18, pady=(0, 10))
        sep = tk.Frame(bottom, bg=C["sidebar_line"], height=1)
        sep.pack(fill="x", pady=(0, 8))
        for line in copyright_lines:
            tk.Label(bottom, text=line, bg=C["sidebar"], fg=C["sidebar_sub"],
                     font=F["small"], wraplength=200, justify="left").pack(anchor="w")
        tk.Label(bottom, text="●  已获得管理员权限", bg=C["sidebar"], fg=C["success"],
                 font=F["admin"]).pack(anchor="w", pady=(8, 2))
        tk.Label(bottom, text=f"DiskCleaner {VERSION}", bg=C["sidebar"], fg=C["sidebar_mute"],
                 font=F["small"]).pack(anchor="w", pady=(6, 0))

    def _nav_hover(self, btn, key, entering):
        if key == getattr(self, "active_key", None):
            return
        btn.configure(bg=C["sidebar_hover"] if entering else C["sidebar"],
                      fg=C["sidebar_text"] if entering else C["sidebar_sub"])

    def set_active(self, key):
        self.active_key = key
        for k, b in self.nav_btns.items():
            if k == key:
                b.configure(bg=C["sidebar_active"], fg=C["white"],
                            font=("Microsoft YaHei UI", 10, "bold"))
            else:
                b.configure(bg=C["sidebar"], fg=C["sidebar_sub"], font=F["nav"])

    def update_disk_usage(self, info: dict):
        """info: {'C:': (free_gb, percent, total_gb), ...}"""
        for drive, (lbl, pb, total) in self.disk_bars.items():
            d = drive[0] + ":"
            if d in info:
                free, pct, cap = info[d]
                used = cap - free
                lbl.configure(text=f"{d}  已用 {used:.0f} / {cap:.0f} GB  ({pct:.0f}%)")
                pb["value"] = pct
                total.configure(text=f"可用 {free:.1f} GB  ·  共 {cap:.0f} GB")
        self._sync_disk_region()


class StatCard(tk.Frame):
    """统计卡片：色点 + 大号数值 + 标签 + 子说明。"""

    def __init__(self, parent, label, value, sub, dot_color, width=196):
        tk.Frame.__init__(self, parent, bg=C["card"], highlightbackground=C["border"],
                          highlightthickness=1, width=width, height=88)
        self.pack_propagate(False)
        dot = tk.Canvas(self, width=10, height=10, bg=C["card"], highlightthickness=0)
        dot.pack(anchor="w", padx=(15, 0), pady=(11, 0))
        dot.create_oval(1, 1, 9, 9, fill=dot_color)
        tk.Label(self, text=label, bg=C["card"], fg=C["text_sub"],
                 font=F["card_label"]).pack(anchor="w", padx=15)
        row = tk.Frame(self, bg=C["card"])
        row.pack(fill="x", padx=15)
        tk.Label(row, text=value, bg=C["card"], fg=C["text"],
                 font=F["card_value"]).pack(side="left")
        tk.Label(row, text=f"  {sub}", bg=C["card"], fg=C["text_mute"],
                 font=F["card_unit"]).pack(side="left")
