"""校准 OCR 扫描区域 — 自适应窗口，拖拽绿色矩形框选"""

# ⚠️ 必须在所有 import 之前：声明 DPI 感知
import ctypes as _ctypes
try:
    _ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    try:
        _ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

import json
import sys
import time
from pathlib import Path

import win32gui
import win32con
import win32api
from PIL import ImageGrab, Image, ImageTk
import tkinter as tk
from tkinter import messagebox

PROJECT_DIR = Path(__file__).resolve().parent
CACHE_DIR = PROJECT_DIR / "cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)
CONFIG_PATH = CACHE_DIR / "ocr_calibration.json"
ACCOUNT = None  # --account 参数（多开时按账户保存校准）


def _config_path():
    """账户专属校准文件（指定账户时），否则全局文件"""
    if ACCOUNT:
        from src.utils.account_paths import calibration_path_for
        return calibration_path_for(ACCOUNT)
    return CONFIG_PATH

DEFAULTS = {
    "chat_title": {
        "LEFT_MARGIN": 0.05, "TOP_PCT": 0.015, "RIGHT_MARGIN": 0.06,
        "BOTTOM_MARGIN": 0.91, "desc": "聊天标题栏",
    },
    "search_panel": {
        "LEFT_MARGIN": 0.03, "TOP_PCT": 0.08, "RIGHT_MARGIN": 0.03,
        "BOTTOM_MARGIN": 0.30, "desc": "搜索面板",
    },
    "contacts_list": {
        "LEFT_MARGIN": 0.03, "TOP_PCT": 0.25, "RIGHT_MARGIN": 0.26,
        "BOTTOM_MARGIN": 0.05, "desc": "通讯录列表",
    },
}

BAR_H = 60


def find_wechat(key: str = ""):
    result = []
    if key == "contacts_list":
        def cb(h, _):
            t = win32gui.GetWindowText(h) or ""; c = win32gui.GetClassName(h) or ""
            if "通讯录管理" in t and "Qt" in c: result.append(h)
            return True
        win32gui.EnumWindows(cb, None)
        if result: return result[0]
        print("未找到通讯录管理窗口")
    def cb2(h, _):
        t = win32gui.GetWindowText(h) or ""; c = win32gui.GetClassName(h) or ""
        if "微信" in t and "Qt" in c: result.append(h)
        return True
    win32gui.EnumWindows(cb2, None)
    return result[0] if result else None


def load_config(key: str) -> dict:
    defaults = dict(DEFAULTS.get(key, {}))
    path = _config_path()
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if key in data: defaults.update(data[key])
        except Exception: pass
    return defaults


def save_config(key: str, params: dict) -> None:
    path = _config_path()
    existing = {}
    if path.exists():
        try: existing = json.loads(path.read_text(encoding="utf-8"))
        except Exception: pass
    existing[key] = params
    path.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")


def main():
    global ACCOUNT
    key = "chat_title"
    for arg in sys.argv[1:]:
        if arg.startswith("--key="): key = arg.split("=", 1)[1]
        elif arg == "--key" and len(sys.argv) > sys.argv.index(arg) + 1:
            key = sys.argv[sys.argv.index(arg) + 1]
        elif arg.startswith("--account="): ACCOUNT = arg.split("=", 1)[1]
        elif arg == "--account" and len(sys.argv) > sys.argv.index(arg) + 1:
            ACCOUNT = sys.argv[sys.argv.index(arg) + 1]

    if key not in DEFAULTS:
        print(f"未知 key: {key}"); sys.exit(1)

    hwnd = find_wechat(key)
    if not hwnd:
        print("未找到目标窗口！"); input("按回车退出..."); sys.exit(1)

    try:
        placement = win32gui.GetWindowPlacement(hwnd)
        if placement[1] != win32con.SW_SHOWMAXIMIZED:
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
        win32api.keybd_event(win32con.VK_MENU, 0, 0, 0)
        win32gui.SetForegroundWindow(hwnd)
        win32api.keybd_event(win32con.VK_MENU, 0, win32con.KEYEVENTF_KEYUP, 0)
    except Exception: pass
    time.sleep(0.5)

    rect = win32gui.GetWindowRect(hwnd)
    _, _, right, bottom = rect
    ww, wh = right - rect[0], bottom - rect[1]
    desc = DEFAULTS[key].get("desc", key)

    # 原图
    full_img = ImageGrab.grab(bbox=rect)

    # 加载配置（兼容新旧格式：>1 = 旧格式像素, ≤1 = 新格式百分比）
    cfg = load_config(key)
    lm = cfg["LEFT_MARGIN"]
    lx = int(lm) if lm > 1 else int(ww * lm)
    ty = int(wh * cfg["TOP_PCT"])
    rm = cfg["RIGHT_MARGIN"]
    rx = ww - (int(rm) if rm > 1 else int(ww * rm))
    bot_m = cfg["BOTTOM_MARGIN"]
    by = wh - (int(bot_m) if bot_m > 1 else int(wh * bot_m))
    if by <= ty + 10: by = ty + 40
    if ty < 0: ty = 0

    root = tk.Tk()
    root.title(f"校准: {desc} — 拖拽绿色矩形框选 | 保存后关闭")
    root.geometry(f"900x680")
    root.minsize(400, 300)
    root.configure(bg="#f0f0f0")

    # ---- 底部栏 ----
    bar = tk.Frame(root, height=BAR_H, bg="#f0f0f0")
    bar.pack(side=tk.BOTTOM, fill=tk.X)
    bar.pack_propagate(False)

    btn_frame = tk.Frame(bar, bg="#f0f0f0")
    btn_frame.pack(pady=4)
    tk.Button(btn_frame, text="💾 保存参数", font=("Microsoft YaHei", 12, "bold"),
              bg="#4CAF50", fg="white", command=lambda: do_save()).pack(
                  side=tk.LEFT, padx=4)
    tk.Button(btn_frame, text="🗑 重置", font=("Microsoft YaHei", 10),
              command=lambda: do_reset()).pack(side=tk.LEFT, padx=4)

    info_var = tk.StringVar()

    def update_info():
        info_var.set(
            f"({lx},{ty})-({rx},{by}) | {rx - lx}x{by - ty} | "
            f"L={lx / ww:.3f} T={ty / wh:.3f} R={(ww - rx) / ww:.3f} B={(wh - by) / wh:.3f}"
        )
    update_info()
    tk.Label(bar, textvariable=info_var, font=("Consolas", 9), bg="#f0f0f0").pack()

    # ---- Canvas ----
    canvas = tk.Canvas(root, bg="#888888", highlightthickness=0)
    canvas.pack(fill=tk.BOTH, expand=True)

    # 显示用的 PhotoImage（随窗口缩放重建）
    photo_ref = [None]

    def get_scale():
        cw = canvas.winfo_width() or 900
        ch = canvas.winfo_height() or 600
        return min(cw / ww, ch / wh, 1.0)

    def rebuild_display():
        s = get_scale()
        dw = int(ww * s); dh = int(wh * s)
        img = full_img.resize((dw, dh), Image.LANCZOS)
        photo_ref[0] = ImageTk.PhotoImage(img)
        canvas.delete("all")
        canvas.create_image(0, 0, anchor="nw", image=photo_ref[0])
        redraw_rect()

    def to_disp(ox, oy):
        s = get_scale()
        return ox * s, oy * s

    def to_orig(dx, dy):
        s = get_scale()
        return dx / s, dy / s

    def redraw_rect():
        s = get_scale()
        dlx, dty = lx * s, ty * s
        drx, dby = rx * s, by * s
        r = max(4, int(6 * s))
        canvas.delete("calib")
        canvas.create_rectangle(dlx, dty, drx, dby, outline="lime", width=2, tags="calib")
        canvas.create_oval(dlx - r, dty - r, dlx + r, dty + r, fill="lime",
                           outline="white", width=1, tags="calib")
        canvas.create_oval(drx - r, dty - r, drx + r, dty + r, fill="lime",
                           outline="white", width=1, tags="calib")
        canvas.create_oval(dlx - r, dby - r, dlx + r, dby + r, fill="lime",
                           outline="white", width=1, tags="calib")
        canvas.create_oval(drx - r, dby - r, drx + r, dby + r, fill="lime",
                           outline="white", width=1, tags="calib")

    def do_reset():
        if messagebox.askyesno("重置", f"确认删除 [{key}] 的校准参数？"):
            path = _config_path()
            if path.exists():
                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
                    if key in data:
                        del data[key]
                    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
                except Exception:
                    pass
            messagebox.showinfo("已重置", f"区域 [{key}] 已重置。")

    def do_save():
        params = {
            "LEFT_MARGIN": round(lx / ww, 6), "TOP_PCT": round(ty / wh, 4),
            "RIGHT_MARGIN": round((ww - rx) / ww, 6), "BOTTOM_MARGIN": round((wh - by) / wh, 4),
        }
        save_config(key, params)
        messagebox.showinfo("已保存", f"区域 [{key}] 已保存!\n{desc}")

    # ---- 拖拽 ----
    drag = {"corner": None, "sx": 0, "sy": 0}
    CORNER_SZ = 12

    EDGE_SZ = 6  # 边缘把手宽度（像素）

    def get_corner(dx, dy):
        s = get_scale()
        dlx, dty = lx * s, ty * s
        drx, dby = rx * s, by * s
        # 四角优先
        for name, cx, cy in [("tl", dlx, dty), ("tr", drx, dty),
                              ("bl", dlx, dby), ("br", drx, dby)]:
            if abs(dx - cx) < CORNER_SZ and abs(dy - cy) < CORNER_SZ:
                return name
        # 四条边缘
        if dlx <= dx <= drx:
            if abs(dy - dty) < EDGE_SZ:
                return "top"
            if abs(dy - dby) < EDGE_SZ:
                return "bottom"
        if dty <= dy <= dby:
            if abs(dx - dlx) < EDGE_SZ:
                return "left"
            if abs(dx - drx) < EDGE_SZ:
                return "right"
        # 内部 = 移动
        if dlx <= dx <= drx and dty <= dy <= dby:
            return "move"
        return None

    CURSOR_MAP = {"tl": "size_nw_se", "br": "size_nw_se",
                  "tr": "size_ne_sw", "bl": "size_ne_sw",
                  "top": "sb_v_double_arrow", "bottom": "sb_v_double_arrow",
                  "left": "sb_h_double_arrow", "right": "sb_h_double_arrow",
                  "move": "fleur"}

    def on_motion(e):
        canvas.config(cursor=CURSOR_MAP.get(get_corner(e.x, e.y), ""))

    def on_press(e):
        c = get_corner(e.x, e.y)
        if c: drag["corner"] = c; drag["sx"] = e.x; drag["sy"] = e.y

    def on_drag(e):
        nonlocal lx, ty, rx, by
        s = get_scale()
        odx = (e.x - drag["sx"]) / s
        ody = (e.y - drag["sy"]) / s
        c = drag["corner"]
        if c == "tl":
            lx = max(0, min(lx + odx, rx - 20)); ty = max(0, min(ty + ody, by - 10))
        elif c == "tr":
            rx = min(ww, max(rx + odx, lx + 20)); ty = max(0, min(ty + ody, by - 10))
        elif c == "bl":
            lx = max(0, min(lx + odx, rx - 20)); by = min(wh, max(by + ody, ty + 10))
        elif c == "br":
            rx = min(ww, max(rx + odx, lx + 20)); by = min(wh, max(by + ody, ty + 10))
        elif c == "top":
            ty = max(0, min(ty + ody, by - 10))
        elif c == "bottom":
            by = min(wh, max(by + ody, ty + 10))
        elif c == "left":
            lx = max(0, min(lx + odx, rx - 20))
        elif c == "right":
            rx = min(ww, max(rx + odx, lx + 20))
        elif c == "move":
            nlx, nrx = lx + odx, rx + odx; nty, nby = ty + ody, by + ody
            if 0 <= nlx and nrx <= ww: lx, rx = nlx, nrx
            if 0 <= nty and nby <= wh: ty, by = nty, nby
        drag["sx"] = e.x; drag["sy"] = e.y
        redraw_rect()
        update_info()

    def on_release(e):
        drag["corner"] = None

    # 窗口大小变化时重建显示（防抖 300ms）
    resize_after_id = [None]

    def on_resize(e):
        if resize_after_id[0]:
            root.after_cancel(resize_after_id[0])
        resize_after_id[0] = root.after(100, rebuild_display)

    canvas.bind("<Configure>", on_resize)
    canvas.bind("<Motion>", on_motion)
    canvas.bind("<ButtonPress-1>", on_press)
    canvas.bind("<B1-Motion>", on_drag)
    canvas.bind("<ButtonRelease-1>", on_release)

    root.after(100, lambda: [root.lift(), root.focus_force(), rebuild_display()])
    root.mainloop()


if __name__ == "__main__":
    main()
