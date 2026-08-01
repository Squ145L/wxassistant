"""启动提示弹窗 — 独立脚本，用 bat 调用前弹出"""
import os
import subprocess
import sys
from pathlib import Path
import tkinter as tk
from tkinter import ttk

HELP_DIR = Path(__file__).resolve().parent / "帮助"


def open_help():
    if HELP_DIR.exists():
        os.startfile(str(HELP_DIR))
    else:
        os.makedirs(str(HELP_DIR), exist_ok=True)
        os.startfile(str(HELP_DIR))


def main():
    root = tk.Tk()
    root.title("微信助手 - 启动提示")
    root.resizable(False, False)

    # 居中
    w, h = 420, 200
    sw = root.winfo_screenwidth()
    sh = root.winfo_screenheight()
    x = (sw - w) // 2
    y = (sh - h) // 2
    root.geometry(f"{w}x{h}+{x}+{y}")

    frame = ttk.Frame(root, padding=24)
    frame.pack(fill=tk.BOTH, expand=True)

    msg = (
        "请保持微信在前台没有最小化\n"
        "使用之前先顶部点击OCR-> 然后校准两个\n"
        "不要手动改变微信窗口大小\n"
	"运行时点击键盘鼠标任意处终止\n"
    )
    ttk.Label(frame, text=msg, font=("Microsoft YaHei", 11),
              justify=tk.CENTER, wraplength=360).pack(pady=(0, 24))

    btn_frame = ttk.Frame(frame)
    btn_frame.pack()

    ttk.Button(btn_frame, text="打开帮助", command=lambda: [open_help(), root.destroy()]).pack(
        side=tk.LEFT, padx=(0, 12))
    ttk.Button(btn_frame, text="关闭", command=root.destroy).pack(side=tk.RIGHT)

    root.mainloop()


if __name__ == "__main__":
    main()
