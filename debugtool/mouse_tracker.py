"""鼠标坐标查看器 — 自动跟踪光标所在顶层窗口显示百分比坐标
用法: pythonw mouse_tracker.py  (或 python mouse_tracker.py)
关窗退出
"""
import tkinter as tk
import win32gui, win32api

root = tk.Tk()
root.title("坐标查看器")
root.geometry("480x100")
root.attributes('-topmost', True)

win_var = tk.StringVar()
pct_var = tk.StringVar()

tk.Label(root, textvariable=win_var, font=("Consolas", 10)).pack(anchor=tk.W, padx=12, pady=(10, 2))
tk.Label(root, textvariable=pct_var, font=("Consolas", 11)).pack(anchor=tk.W, padx=12, pady=(2, 10))

def update():
    x, y = win32api.GetCursorPos()
    try:
        hwnd = win32gui.WindowFromPoint((x, y))
        if hwnd:
            root_hwnd = win32gui.GetAncestor(hwnd, 2)  # GA_ROOT
            if root_hwnd:
                hwnd = root_hwnd
            title = win32gui.GetWindowText(hwnd)
            cls = win32gui.GetClassName(hwnd)
            r = win32gui.GetWindowRect(hwnd)
            rx, ry = x - r[0], y - r[1]
            ww, wh = r[2] - r[0], r[3] - r[1]
            inside = 0 <= rx <= ww and 0 <= ry <= wh
            marker = "  <=" if inside else ""
            win_var.set(f"窗口: [{title}]  cls=[{cls}]\n      {ww}x{wh}")
            if ww and wh:
                pct_var.set(f"百分比: ({rx/ww:.3f}, {ry/wh:.3f}){marker}")
            else:
                pct_var.set("")
        else:
            win_var.set("窗口: (未找到)")
            pct_var.set("")
    except:
        win_var.set("窗口: (获取失败)")
        pct_var.set("")

    root.after(50, update)

update()
root.mainloop()
