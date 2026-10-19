# SPDX-License-Identifier: LGPL-3.0-or-later
# Copyright (C) 2026 LiteZero

"""状态窗口、托盘和用户自选的登录启动"""

import os
import sys
import threading
import tkinter as tk
import winreg
from pathlib import Path
from tkinter import messagebox, ttk

import pystray
from PIL import Image, ImageDraw

from .http_server import PORT


def startup_enabled():
    """检查本应用是否已设置登录启动"""
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run"
        ) as key:
            winreg.QueryValueEx(key, "SPlayerEC")
        return True
    except FileNotFoundError:
        return False


def set_startup(enabled):
    """仅按用户点击设置或移除当前用户的登录启动项"""
    with winreg.CreateKey(
        winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run"
    ) as key:
        if enabled:
            if not getattr(sys, "frozen", False):
                raise ValueError("请使用打包后的程序设置登录启动")
            winreg.SetValueEx(key, "SPlayerEC", 0, winreg.REG_SZ, f'"{sys.executable}" --tray')
        else:
            try:
                winreg.DeleteValue(key, "SPlayerEC")
            except FileNotFoundError:
                pass


def make_icon():
    """生成小尺寸托盘图标，无需额外图片资源"""
    image = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((3, 3, 61, 61), radius=14, fill="#3276e8")
    draw.rectangle((35, 14, 40, 43), fill="white")
    draw.rectangle((24, 14, 40, 20), fill="white")
    draw.ellipse((20, 36, 40, 51), fill="white")
    return image


def run_ui(service, tray=False, shutdown_event=None):
    """展示连接状态和托盘菜单，关闭窗口时继续在托盘同步"""
    root = tk.Tk()
    root.title("SPlayerEC · K20 GT 歌词互联")
    root.geometry("570x390")
    root.resizable(False, False)
    root.configure(background="#f6f8fc")
    style = ttk.Style(root)
    style.configure("TFrame", background="#f6f8fc")
    style.configure("TLabel", background="#f6f8fc", font=("Microsoft YaHei UI", 10))
    frame = ttk.Frame(root, padding=24)
    frame.pack(fill="both", expand=True)
    ttk.Label(frame, text="K20 GT 歌词互联", font=("Microsoft YaHei UI", 18, "bold")).pack(
        anchor="w"
    )
    ttk.Label(frame, text="导入歌词插件后，将 SPlayer 当前歌词发送到音箱").pack(
        anchor="w", pady=(7, 16)
    )
    state = tk.StringVar(value="等待歌词插件")
    details = tk.StringVar(value="")
    ttk.Label(frame, textvariable=state, font=("Microsoft YaHei UI", 12, "bold")).pack(anchor="w")
    ttk.Label(frame, textvariable=details, wraplength=510).pack(anchor="w", pady=(5, 8))
    ttk.Label(frame, text=f"本机接口：127.0.0.1:{PORT}  ·  仅监听本机").pack(anchor="w")
    ttk.Label(
        frame,
        text="关闭 MCHOSE HUB 和 SPlayer 内置的音箱歌词同步\n关闭此窗口后继续在托盘运行，右键托盘图标可退出",
        wraplength=510,
    ).pack(anchor="w", pady=(12, 10))
    startup = tk.BooleanVar(value=startup_enabled())
    exit_requested = shutdown_event or threading.Event()
    show_requested = threading.Event()

    def toggle_startup():
        """应用登录启动选择，失败时还原开关"""
        try:
            set_startup(startup.get())
        except (OSError, ValueError) as error:
            startup.set(startup_enabled())
            messagebox.showerror("无法设置登录启动", str(error), parent=root)

    ttk.Checkbutton(
        frame,
        text="登录 Windows 时启动桥接程序",
        variable=startup,
        command=toggle_startup,
    ).pack(anchor="w")
    buttons = ttk.Frame(frame)
    buttons.pack(fill="x", pady=(16, 0))

    def open_plugin():
        """打开插件所在目录，便于在播放器中选择本地导入"""
        base = (
            Path(sys.executable).parent
            if getattr(sys, "frozen", False)
            else Path(__file__).resolve().parent.parent
        )
        path = base / "plugin"
        os.startfile(path if path.exists() else base)

    ttk.Button(buttons, text="打开插件文件夹", command=open_plugin).pack(side="left")
    ttk.Button(buttons, text="隐藏到托盘", command=root.withdraw).pack(side="left", padx=8)
    ttk.Button(buttons, text="退出", command=exit_requested.set).pack(side="right")
    icon = pystray.Icon(
        "SPlayerEC",
        make_icon(),
        "SPlayerEC · K20 GT 歌词互联",
        menu=pystray.Menu(
            pystray.MenuItem("显示状态", lambda _icon, _item: show_requested.set(), default=True),
            pystray.MenuItem("退出", lambda _icon, _item: exit_requested.set()),
        ),
    )
    icon_thread = threading.Thread(target=icon.run, name="k20gt-tray", daemon=True)
    icon_thread.start()

    def refresh():
        """低频刷新可见窗口，托盘模式不更新控件"""
        if exit_requested.is_set():
            root.destroy()
            return
        if show_requested.is_set():
            show_requested.clear()
            root.deiconify()
            root.lift()
        if root.state() != "withdrawn":
            snapshot = service.snapshot()
            state.set(
                {
                    "connected": "已连接 K20 GT",
                    "disconnected": "设备未连接，正在自动重试",
                    "waiting": "等待歌词" if snapshot["active"] else "等待歌词插件",
                }[snapshot["state"]]
            )
            details.set(
                snapshot["error"]
                or (
                    "当前文字：" + snapshot["text"]
                    if snapshot["text"]
                    else "播放带有歌词的歌曲后自动连接音箱"
                )
            )
        root.after(500, refresh)

    root.protocol("WM_DELETE_WINDOW", root.withdraw)
    if tray:
        root.withdraw()
    root.after(100, refresh)
    try:
        root.mainloop()
    finally:
        icon.stop()
        icon_thread.join(timeout=2)
