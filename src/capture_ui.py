# -*- coding: utf-8 -*-
"""截图核验 v1.2.0 深色控制台 UI。"""
import os
import tkinter as tk
from PIL import ImageGrab
import app

root = tk.Tk()
root.geometry("1180x760")
root.title("DiskCleaner v1.2.0")
root.attributes("-topmost", True)
a = app.App(root)
root.update_idletasks(); root.update()

info = {}
for i, d in enumerate(["C:", "D:", "E:", "F:", "G:", "H:", "I:", "J:", "K:"]):
    info[d] = (100 - i * 8, 8 + i * 9, 200)
a.sidebar.update_disk_usage(info)
root.update_idletasks(); root.update()

for key, name in (("checkup", "checkup"), ("wechat", "wechat"), ("wps", "wps"),
                 ("large", "large"), ("log", "log")):
    a.navigate(key)
    root.update_idletasks(); root.update()
    x, y = root.winfo_rootx(), root.winfo_rooty()
    w, h = root.winfo_width(), root.winfo_height()
    ImageGrab.grab(bbox=(x, y, x + w, y + h)).save(
        os.path.join(os.path.dirname(__file__), f"v12_{name}.png"))
    print("captured", name)

root.destroy()
