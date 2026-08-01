"""设置弹窗"""

import json
import threading
import time
import tkinter as tk
from tkinter import ttk, messagebox
from pathlib import Path

SETTINGS_PATH = Path("cache/settings.json")
DEFAULT_SETTINGS = {
    "name_source": "cache",
    "ocr_debug_save": False,
    "scan_page_count": 100,
    "scan_scroll_px": 1200,
    "scan_pages_per_scroll": 12,
    "logging_enabled": True,
}

# 浮点数百分比校验
def _validate_pct(P: str) -> bool:
    if P == "" or P == ".":
        return True
    try:
        v = float(P)
        return 0.0 <= v <= 1.0
    except ValueError:
        return False


def load_settings() -> dict:
    if SETTINGS_PATH.exists():
        try:
            data = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
            merged = dict(DEFAULT_SETTINGS)
            merged.update(data)
            return merged
        except Exception:
            pass
    return dict(DEFAULT_SETTINGS)


def load_scan_settings() -> dict:
    """供 operations.py 调用：返回扫描页数和滚动高度"""
    s = load_settings()
    return {"page_count": s["scan_page_count"], "scroll_px": s["scan_scroll_px"],
            "pages_per_scroll": s["scan_pages_per_scroll"]}


def save_settings(settings: dict) -> None:
    SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS_PATH.write_text(
        json.dumps(settings, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


class SettingsDialog(tk.Toplevel):

    def __init__(self, parent: tk.Widget, tab: str = "常规"):
        super().__init__(parent)
        self.title("设置")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        self._initial_tab = tab
        self.protocol("WM_DELETE_WINDOW", self._on_close)  # X 按钮也保存

        self._settings = load_settings()
        self._name_source = tk.StringVar(value=self._settings.get("name_source", "cache"))
        self._ocr_debug = tk.BooleanVar(value=self._settings.get("ocr_debug_save", False))
        self._logging_enabled = tk.BooleanVar(value=self._settings.get("logging_enabled", True))
        self._page_count = tk.IntVar(value=self._settings.get("scan_page_count", 10))
        self._scroll_px = tk.IntVar(value=self._settings.get("scan_scroll_px", 600))

        # 坐标变量（延迟加载，从 coordinates.py）
        self._coord_vars: dict[str, tuple[tk.StringVar, tk.StringVar]] = {}

        self._build_ui()
        self._center(parent)

    def _build_ui(self) -> None:
        nb = ttk.Notebook(self)
        nb.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

        # ---- 标签1: 常规 ----
        tab1 = ttk.Frame(nb, padding=16)
        nb.add(tab1, text="常规")

        ttk.Label(tab1, text="发送的 name 来源:", font=("Microsoft YaHei", 10, "bold")).pack(anchor=tk.W, pady=(0, 8))
        ttk.Radiobutton(tab1, text="缓存加载  (从 cache/friends.json 读取)", variable=self._name_source, value="cache").pack(anchor=tk.W, pady=2)
        ttk.Radiobutton(tab1, text="OCR 扫描  (扫描微信通讯录获取)", variable=self._name_source, value="ocr").pack(anchor=tk.W, pady=2)

        ttk.Separator(tab1, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=12)

        ttk.Label(tab1, text="日志:", font=("Microsoft YaHei", 10, "bold")).pack(anchor=tk.W, pady=(0, 8))
        log_row = ttk.Frame(tab1)
        log_row.pack(fill=tk.X)
        ttk.Checkbutton(log_row, text="启用文件日志 (logs/app.log)", variable=self._logging_enabled,
                        command=self._on_logging_toggled).pack(side=tk.LEFT)
        ttk.Button(log_row, text="清除日志", command=self._on_clear_logs).pack(side=tk.RIGHT)

        # ---- 标签2: OCR ----
        tab2 = ttk.Frame(nb, padding=16)
        nb.add(tab2, text="OCR")

        ttk.Label(tab2, text="调试选项:", font=("Microsoft YaHei", 10, "bold")).pack(anchor=tk.W, pady=(0, 8))
        ttk.Checkbutton(tab2, text="保存调试截图 (cache/debug_scan/)", variable=self._ocr_debug).pack(anchor=tk.W)

        ttk.Separator(tab2, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=12)

        ttk.Label(tab2, text="扫描通讯录并导入:", font=("Microsoft YaHei", 10, "bold")).pack(anchor=tk.W, pady=(0, 8))

        ttk.Label(tab2, text="截图页数:").pack(anchor=tk.W)
        ttk.Spinbox(tab2, from_=1, to=50, textvariable=self._page_count, width=8).pack(anchor=tk.W, pady=(2, 8))

        ttk.Label(tab2, text="每页滚动高度 (px):").pack(anchor=tk.W)
        ttk.Entry(tab2, textvariable=self._scroll_px, width=10).pack(anchor=tk.W, pady=(2, 6))

        ttk.Label(tab2, text="每次翻的页数:").pack(anchor=tk.W)
        self._pages_per = tk.IntVar(value=self._settings.get("scan_pages_per_scroll", 1))
        ttk.Spinbox(tab2, from_=1, to=10, textvariable=self._pages_per, width=8).pack(anchor=tk.W, pady=(2, 10))

        ttk.Button(tab2, text="测试：通讯录 → 通讯录管理 → 滚一页",
                   command=self._run_test).pack(pady=(0, 4))

        ttk.Separator(tab2, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=8)

        ttk.Button(tab2, text="OCR 校准重置",
                   command=self._reset_ocr).pack(pady=(0, 8))

        # ---- 标签3: 坐标 ----
        tab3 = ttk.Frame(nb, padding=16)
        nb.add(tab3, text="坐标")
        self._build_coord_tab(tab3)

        # 跳到指定标签
        if self._initial_tab == "OCR":
            nb.select(tab2)
        elif self._initial_tab == "坐标":
            nb.select(tab3)

        # ---- 底部 ----
        btn_frame = ttk.Frame(self, padding=12)
        btn_frame.pack(fill=tk.X)
        ttk.Button(btn_frame, text="关闭", command=self._on_close).pack(side=tk.RIGHT)

    def _on_close(self) -> None:
        self._settings["name_source"] = self._name_source.get()
        self._settings["ocr_debug_save"] = self._ocr_debug.get()
        self._settings["logging_enabled"] = self._logging_enabled.get()
        self._settings["scan_page_count"] = self._page_count.get()
        self._settings["scan_scroll_px"] = self._scroll_px.get()
        self._settings["scan_pages_per_scroll"] = self._pages_per.get()
        save_settings(self._settings)
        self._save_coordinates()
        self.destroy()

    def _on_logging_toggled(self) -> None:
        from src.utils.logger import set_file_logging
        set_file_logging(self._logging_enabled.get())

    def _on_clear_logs(self) -> None:
        from src.utils.logger import clear_logs
        clear_logs()
        messagebox.showinfo("已清除", "日志文件已清空。")

    def _run_test(self) -> None:
        def _do():
            try:
                from src.driver.wechat_bridge import WeChatBridge
                bridge = WeChatBridge()
                if not bridge.find_window():
                    self.after(0, lambda: messagebox.showerror("错误", "未找到微信窗口"))
                    return

                hwnd = bridge.open_contacts_manager()
                if hwnd is None:
                    self.after(0, lambda: messagebox.showerror("错误", "未找到通讯录管理窗口"))
                    return

                import win32gui
                from src.utils.coordinates import get_coord
                rect = win32gui.GetWindowRect(hwnd)
                if rect:
                    cx_pct, cy_pct = get_coord("cm_list_focus")
                    fx = rect[0] + int((rect[2] - rect[0]) * cx_pct)
                    fy = rect[1] + int((rect[3] - rect[1]) * cy_pct)
                    bridge.click_at(fx, fy)
                    time.sleep(0.15)
                    bridge.scroll_at(fx, fy, -self._scroll_px.get())
                    time.sleep(1.5)

                self.after(0, lambda: [self.lift(), self.focus_force()])

            except Exception as e:
                self.after(0, lambda: messagebox.showerror("测试失败", str(e)))

        threading.Thread(target=_do, daemon=True).start()

    def _reset_ocr(self) -> None:
        if not messagebox.askyesno("OCR 校准重置", "确认清除所有 OCR 校准参数？"):
            return
        config_path = Path("cache/ocr_calibration.json")
        if config_path.exists():
            config_path.write_text("{}", encoding="utf-8")
        messagebox.showinfo("已重置", "OCR 校准参数已清除。")

    def _build_coord_tab(self, parent: ttk.Frame) -> None:
        """构建坐标标签页：每个坐标一行 X% + Y% spinbox"""
        from src.utils.coordinates import (
            load_coordinates, save_coordinates, reset_coordinates,
            COORD_LABELS, COORD_GROUPS, DEFAULT_COORDINATES,
        )

        self._all_coord_keys: list[str] = []
        coords = load_coordinates()

        # 滚动区（坐标多时避免溢出）
        canvas = tk.Canvas(parent, borderwidth=0, highlightthickness=0)
        scrollbar = ttk.Scrollbar(parent, orient=tk.VERTICAL, command=canvas.yview)
        scroll_frame = ttk.Frame(canvas)

        scroll_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=scroll_frame, anchor=tk.NW)
        canvas.configure(yscrollcommand=scrollbar.set)

        pct_vcmd = (parent.register(_validate_pct), "%P")

        for group_name, keys in COORD_GROUPS:
            group_row = ttk.Frame(scroll_frame)
            group_row.pack(fill=tk.X, pady=(12, 4))
            ttk.Label(group_row, text=group_name,
                      font=("Microsoft YaHei", 10, "bold")).pack(side=tk.LEFT)
            if group_name == "微信主界面":
                ttk.Button(group_row, text="鼠标位置", width=9,
                           command=self._launch_mouse_tracker).pack(side=tk.RIGHT)

            for key in keys:
                self._all_coord_keys.append(key)
                cx, cy = coords.get(key, DEFAULT_COORDINATES[key])
                label_text = COORD_LABELS.get(key, key)

                row = ttk.Frame(scroll_frame)
                row.pack(fill=tk.X, pady=1)

                # 标签
                ttk.Label(row, text=label_text, width=22, anchor=tk.W).pack(side=tk.LEFT)

                # X%
                ttk.Label(row, text="X:").pack(side=tk.LEFT)
                x_var = tk.StringVar(value=f"{cx:.4f}")
                x_entry = ttk.Entry(row, textvariable=x_var, width=7,
                                    validate="key", validatecommand=pct_vcmd)
                x_entry.pack(side=tk.LEFT, padx=(0, 8))

                # Y%
                ttk.Label(row, text="Y:").pack(side=tk.LEFT)
                y_var = tk.StringVar(value=f"{cy:.4f}")
                y_entry = ttk.Entry(row, textvariable=y_var, width=7,
                                    validate="key", validatecommand=pct_vcmd)
                y_entry.pack(side=tk.LEFT, padx=(0, 6))

                # 测试点击按钮
                ttk.Button(row, text="测试", width=4,
                           command=lambda k=key: self._test_coord_click(k)).pack(side=tk.LEFT)

                self._coord_vars[key] = (x_var, y_var)

        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

    def _save_coordinates(self) -> None:
        """收集坐标输入框的值并保存"""
        if not self._coord_vars:
            return
        from src.utils.coordinates import save_coordinates, DEFAULT_COORDINATES
        coords = {}
        for key, (xv, yv) in self._coord_vars.items():
            try:
                x = float(xv.get())
                y = float(yv.get())
                coords[key] = (x, y)
            except ValueError:
                coords[key] = DEFAULT_COORDINATES.get(key, (0.0, 0.0))
        save_coordinates(coords)

    @staticmethod
    def _launch_mouse_tracker() -> None:
        """启动鼠标坐标查看器"""
        import subprocess
        import os
        tracker = Path(__file__).parent.parent.parent / "debugtool" / "mouse_tracker.py"
        subprocess.Popen(["python", str(tracker)],
                         cwd=str(Path(__file__).parent.parent.parent))

    def _test_coord_click(self, key: str) -> None:
        """测试点击指定坐标：切换到微信 → 点击

        - 主界面坐标：激活微信 → 点击
        - 通讯录管理坐标：先打开通讯录管理 → (cm_list_focus 会全屏) → 点击
        """
        if key not in self._coord_vars:
            return
        xv, yv = self._coord_vars[key]
        try:
            x_pct = float(xv.get())
            y_pct = float(yv.get())
        except ValueError:
            messagebox.showerror("格式错误", f"[{key}] 坐标值无法解析")
            return

        def _do():
            try:
                from src.driver.wechat_bridge import WeChatBridge
                bridge = WeChatBridge()
                if not bridge.find_window():
                    self.after(0, lambda: messagebox.showerror("错误", "未找到微信窗口"))
                    return

                if key in ("cm_search_box", "cm_list_focus"):
                    # 通讯录管理窗口：先打开通讯录管理
                    hwnd = bridge.open_contacts_manager()
                    if hwnd is None:
                        self.after(0, lambda: messagebox.showerror("错误", "未找到通讯录管理窗口"))
                        return

                    if key == "cm_list_focus":
                        # 列表聚焦前确保全屏
                        import win32gui as _wg2
                        import win32con as _wc2
                        placement = _wg2.GetWindowPlacement(hwnd)
                        if placement[1] != _wc2.SW_SHOWMAXIMIZED:
                            _wg2.ShowWindow(hwnd, _wc2.SW_MAXIMIZE)
                            time.sleep(0.3)

                    import win32gui as _wg
                    target_rect = _wg.GetWindowRect(hwnd)
                else:
                    # 微信主界面：激活窗口
                    bridge.activate_window()
                    time.sleep(0.3)
                    target_rect = bridge.get_window_rect()

                if target_rect is None:
                    self.after(0, lambda: messagebox.showerror("错误", "无法获取窗口区域"))
                    return

                ww = target_rect[2] - target_rect[0]
                wh = target_rect[3] - target_rect[1]
                cx = target_rect[0] + int(ww * x_pct)
                cy = target_rect[1] + int(wh * y_pct)
                bridge.click_at(cx, cy)

                self.after(0, lambda: [self.lift(), self.focus_force()])
                self.after(0, lambda: messagebox.showinfo(
                    "测试完成", f"已在 ({x_pct:.4f}, {y_pct:.4f}) 处点击。"))

            except Exception as e:
                self.after(0, lambda: messagebox.showerror("测试失败", str(e)))

        threading.Thread(target=_do, daemon=True).start()

    def _center(self, parent: tk.Widget) -> None:
        self.update_idletasks()
        pw = parent.winfo_width(); ph = parent.winfo_height()
        px = parent.winfo_rootx(); py = parent.winfo_rooty()
        w, h = 460, 440
        x = px + (pw - w) // 2; y = py + (ph - h) // 2
        self.geometry(f"{w}x{h}+{x}+{y}")
