# -*- coding: utf-8 -*-
"""DiskCleaner UI 主题与可复用组件（参考 DiskMate 风格）。"""
from __future__ import annotations
import tkinter as tk
from tkinter import ttk

VERSION = "1.3.0"  # 版本号单一来源，app.py 与侧栏共用

# ---------- 配色 ----------
# 主题「精密仪器」：深墨蓝控制台侧栏 + 冷白数据区（自 v1.2.0 沿用至今）。
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


class SweepCanvas(tk.Canvas):
    """清理进度小窗里的「动态扫地」效果。

    纯 Canvas 绘制地面、碎屑、扫把与右侧回收桶：扫把随真实清理进度从左向右
    推进，沿途碎屑被扫起并飞入桶中；收集文件阶段扫把在左侧小幅往复摆动。
    """

    def __init__(self, parent, width=460, height=78):
        tk.Canvas.__init__(self, parent, width=width, height=height,
                           bg=C["card"], highlightthickness=0)
        import random
        self.W, self.H = width, height
        self._ground = height - 15
        self._x = 0.02
        self._target = 0.02
        self._idle = True
        self._dir = 1
        self._after_id = None
        self._debris = []
        self._rng = random.Random(20261120)
        self._build_scene()
        self._tick()

    @property
    def _broom_x(self):
        # 留出右侧回收桶的宽度，进度 100% 时扫把刚好停在桶左侧
        return self._x * (self.W - 70)

    def _build_scene(self):
        self.create_line(10, self._ground, self.W - 10, self._ground,
                         fill=C["border"], width=2)
        bx = self.W - 48
        self.create_polygon(bx, self._ground - 26, bx + 30, self._ground - 26,
                            bx + 26, self._ground - 2, bx + 4, self._ground - 2,
                            fill=C["primary_light"], outline=C["primary"], width=1.5)
        self.create_rectangle(bx - 3, self._ground - 30, bx + 33, self._ground - 26,
                              fill=C["primary"], outline="")
        # 碎屑用略深的柔和色，白底上才能看清「被扫走」的过程
        palette = ["#B9CDF7", "#A8B7CE", "#F3C77A", "#8FA6CC", "#CBD8F2"]
        for i in range(26):
            x = 14 + i * ((self.W - 120) / 26) + self._rng.uniform(-4, 4)
            y = self._ground - self._rng.uniform(3, 13)
            s = self._rng.uniform(3, 6)
            cid = self.create_rectangle(x, y, x + s, y + s,
                                        fill=palette[i % len(palette)], outline="")
            self._debris.append([cid, x, y, "idle", 0])
        self._label = self.create_text(12, 14, anchor="w",
                                      text="正在收集待清理文件…",
                                      fill=C["text_mute"], font=F["small"])
        self._draw_broom()

    def _draw_broom(self):
        self.delete("broom")
        x, y = self._broom_x, self._ground
        self.create_line(x + 12, y - 44, x - 1, y - 13, fill=C["primary"],
                         width=3, capstyle="round", tags="broom")
        self.create_polygon(x - 11, y - 13, x + 11, y - 13,
                            x + 14, y - 1, x - 14, y - 1,
                            fill=C["primary_light"], outline=C["primary"],
                            width=1.5, tags="broom")
        for k in range(6):
            bx = x - 12 + k * 5
            self.create_line(bx, y - 1, bx - 1, y + 2, fill=C["primary"],
                             width=1, tags="broom")

    def _sweep_debris(self):
        bx = self._broom_x
        for d in self._debris:
            state = d[3]
            if state == "gone":
                continue
            if state == "flying":
                self.move(d[0], 3.4, -1.7)
                d[4] -= 1
                if d[4] <= 0:
                    self.delete(d[0])
                    d[3] = "gone"
            elif d[1] <= bx + 10:
                d[3] = "flying"
                d[4] = 9

    def set_progress(self, fraction):
        """由真实清理进度驱动（0.0 ~ 1.0）。"""
        self._idle = False
        self._target = max(0.0, min(1.0, float(fraction)))

    def finish(self):
        self._idle = False
        self._target = 1.0
        self.after(360, self._clear_all)

    def _clear_all(self):
        try:
            for d in self._debris:
                if d[3] != "gone":
                    self.delete(d[0])
                    d[3] = "gone"
            self.itemconfigure(self._label, text="✓  已清理干净")
        except tk.TclError:
            pass

    def stop(self):
        try:
            if self._after_id:
                self.after_cancel(self._after_id)
        except Exception:
            pass

    def _tick(self):
        try:
            if not self.winfo_exists():
                return
            if self._idle:
                self._x += 0.005 * self._dir
                if self._x > 0.22:
                    self._dir = -1
                elif self._x < 0.02:
                    self._dir = 1
            else:
                self._x += (self._target - self._x) * 0.14
            self._draw_broom()
            self._sweep_debris()
            if not self._idle:
                self.itemconfigure(self._label, text="清理进度 %d%%" % int(self._x * 100))
        except tk.TclError:
            return
        self._after_id = self.after(30, self._tick)


class MagnifierCanvas(tk.Canvas):
    """扫描进度弹窗里的运动放大镜。

    镜片沿一排「文件块」左右移动，扫过的文件块被放大高亮；扫描开始时往复
    巡视，随后由真实进度驱动平滑推进，完成后定格并提示「扫描完成」。
    """

    def __init__(self, parent, width=430, height=78):
        tk.Canvas.__init__(self, parent, width=width, height=height,
                           bg=C["card"], highlightthickness=0)
        self.W, self.H = width, height
        self._x = 0.06
        self._target = 0.06
        self._idle = True
        self._dir = 1
        self._after_id = None
        self._cells = []
        self._cy = height - 34
        self._r = 15
        self._build_scene()
        self._tick()

    def _mag_x(self):
        return 22 + self._x * (self.W - 70)

    def _build_scene(self):
        self.create_line(10, self.H - 14, self.W - 10, self.H - 14,
                         fill=C["border"], width=2)
        palette = ["#D7E2F7", "#C9D6EE", "#E8EDF6", "#BFD0F0"]
        for i in range(16):
            x = 14 + i * ((self.W - 40) / 16)
            y = self._cy - 6
            color = palette[i % len(palette)]
            cid = self.create_rectangle(x, y, x + 14, y + 12,
                                        fill=color, outline="")
            self._cells.append([cid, x, y, 14, color])
        self._label = self.create_text(12, 14, anchor="w", text="正在扫描…",
                                      fill=C["text_mute"], font=F["small"])
        self._draw_magnifier()

    def _draw_magnifier(self):
        self.delete("mag")
        x, cy, r = self._mag_x(), self._cy, self._r
        self.create_oval(x - r, cy - r, x + r, cy + r,
                         fill=C["primary_light"], outline=C["primary"],
                         width=2, tags="mag")
        for k in (-6, 0, 6):
            self.create_line(x - 8, cy + k * 0.7, x + 8, cy + k * 0.7,
                             fill=C["primary"], width=1.5, tags="mag")
        self.create_line(x + r * 0.7, cy + r * 0.7, x + r + 12, cy + r + 12,
                         fill=C["primary"], width=4, capstyle="round", tags="mag")

    def _highlight(self, x):
        for c in self._cells:
            cx = c[1] + c[3] / 2
            self.itemconfigure(c[0], fill=C["primary"] if abs(cx - x) < 22 else c[4])

    def set_progress(self, fraction):
        """由真实扫描进度驱动（0.0 ~ 1.0），必须在主线程调用。"""
        self._idle = False
        self._target = max(0.0, min(1.0, float(fraction)))

    def finish(self):
        self._idle = False
        self._target = 1.0
        self.after(260, self._show_done)

    def _show_done(self):
        try:
            self.itemconfigure(self._label, text="✓  扫描完成")
        except tk.TclError:
            pass

    def stop(self):
        try:
            if self._after_id:
                self.after_cancel(self._after_id)
        except Exception:
            pass

    def _tick(self):
        try:
            if not self.winfo_exists():
                return
            if self._idle:
                self._x += 0.008 * self._dir
                if self._x > 0.92:
                    self._dir = -1
                elif self._x < 0.06:
                    self._dir = 1
            else:
                self._x += (self._target - self._x) * 0.14
            self._draw_magnifier()
            self._highlight(self._mag_x())
            if not self._idle:
                self.itemconfigure(self._label, text="扫描进度 %d%%" % int(self._x * 100))
        except tk.TclError:
            return
        self._after_id = self.after(30, self._tick)
