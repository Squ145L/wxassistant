"""设置弹窗"""

import sys
import threading
import time
import tkinter as tk
from tkinter import ttk, messagebox
from pathlib import Path
from typing import Callable, Optional

from src.utils.calibration import reset_calibration
from src.utils.coordinates import (
    save_coordinates, account_has_override, should_save_coordinates,
    DEFAULT_COORDINATES,
)
from src.utils.settings_store import (
    DEFAULT_SETTINGS,
    copy_account_data,
    load_account_settings,
    load_delay_settings,
    load_scan_settings,
    load_settings,
    save_account_settings,
    save_settings,
)


# OCR 模型集选项（值 → 展示标签）
OCR_MODELS = {
    "v5": "v5 移动端（默认，字库更全）",
    "v4": "v4 经典（更快更小）",
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


class SettingsDialog(tk.Toplevel):

    def __init__(self, parent: tk.Widget, tab: str = "常规",
                 account_name: Optional[str] = None,
                 account_names: Optional[list[str]] = None,
                 on_calibrate: Optional[Callable[[str], None]] = None,
                 get_hwnd: Optional[Callable[[], Optional[int]]] = None):
        super().__init__(parent)
        self.title("设置")
        self.resizable(True, True)
        self.minsize(700, 500)  # 坐标 tab 每行控件较多, 最小宽度给足防止右侧按钮被挤
        self.transient(parent)
        self._initial_tab = tab
        self._parent = parent
        self._get_hwnd = get_hwnd      # () -> 当前锁定的微信窗口 hwnd（校准/测试作用于它）
        self._account_name = account_name      # 当前账户（None=全局/单账户）
        self._account_names = account_names    # 可用账户列表（多账户模式）
        self._on_calibrate = on_calibrate      # (key) -> None，打开 OCR 校准
        self.protocol("WM_DELETE_WINDOW", self._on_close)  # X 按钮也保存

        self._settings = load_settings()
        # name_source 是账户级设置（每个账户独立）；None 账户名 → 默认账户
        account_settings = load_account_settings(self._account_name or "")
        self._name_source = tk.StringVar(value=account_settings.get("name_source", "cache"))
        self._theme_var = tk.StringVar(value=self._settings.get("theme", "vista"))
        self._ocr_debug = tk.BooleanVar(value=self._settings.get("ocr_debug_save", False))
        self._logging_enabled = tk.BooleanVar(value=self._settings.get("logging_enabled", True))
        self._page_count = tk.IntVar(value=self._settings.get("scan_page_count", 10))
        self._scroll_px = tk.IntVar(value=self._settings.get("scan_scroll_px", 600))
        # 多开延迟参数
        self._mo_activate = tk.DoubleVar(value=self._settings.get("multi_open_activate_delay", 0.2))
        self._mo_search = tk.DoubleVar(value=self._settings.get("multi_open_search_delay", 0.1))
        self._mo_ready = tk.DoubleVar(value=self._settings.get("multi_open_ready_timeout", 2.0))
        self._mo_account_interval = tk.DoubleVar(value=self._settings.get("multi_open_account_interval", 3.0))
        self._mo_send_interval = tk.DoubleVar(value=self._settings.get("multi_open_send_interval", 0.1))
        self._mo_popup_retry = tk.IntVar(value=self._settings.get("multi_open_popup_retry", 0))

        # 操作间延迟参数（设置→延迟，全局不分账户）
        _dl = load_delay_settings()
        self._op_activate = tk.DoubleVar(value=_dl["op_activate_delay"])
        self._op_search = tk.DoubleVar(value=_dl["op_search_delay"])
        self._op_clipboard = tk.DoubleVar(value=_dl["op_clipboard_delay"])
        self._op_paste = tk.DoubleVar(value=_dl["op_paste_delay"])
        self._op_send_after = tk.DoubleVar(value=_dl["op_send_after_delay"])
        self._op_file_send = tk.DoubleVar(value=_dl["op_file_send_delay"])
        self._op_key_press = tk.DoubleVar(value=_dl["op_key_press_delay"])
        self._op_send_interval = tk.DoubleVar(value=_dl["op_send_interval"])
        self._op_send_jitter = tk.DoubleVar(value=_dl["op_send_jitter"])

        # OCR 模型集（全局不分账户）
        _ocr_value = self._settings.get("ocr_model", "v5")
        self._ocr_model = tk.StringVar(value=OCR_MODELS.get(_ocr_value, OCR_MODELS["v5"]))

        # 坐标变量（延迟加载，从 coordinates.py）
        self._coord_vars: dict[str, tuple[tk.StringVar, tk.StringVar]] = {}

        self._build_ui()
        self._center(parent)

    def _build_ui(self) -> None:
        # 账户行（始终显示可切换下拉；单模式也有持久账户）
        acct_row = ttk.Frame(self)
        acct_row.pack(fill=tk.X, padx=8, pady=(8, 0))
        names = self._account_names or ([self._account_name] if self._account_name else ["默认账户"])
        self._display_account = self._account_name or names[0]
        self._account_combo = ttk.Combobox(
            acct_row, values=names, state="readonly", width=12)
        self._account_combo.set(self._display_account)
        self._account_combo.bind("<<ComboboxSelected>>", self._on_account_selected)
        self._account_combo.pack(side=tk.LEFT, padx=(6, 0))
        # 同步其他账户设置：按钮 → 选来源账户 → 单次复制坐标+OCR校准，之后不跟随
        ttk.Button(acct_row, text="同步其他账户设置(坐标/OCR)",
                   command=self._on_sync_settings).pack(side=tk.LEFT, padx=(12, 0))

        nb = ttk.Notebook(self)
        self._nb = nb
        nb.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

        # ---- 标签1: 常规 ----
        tab1 = ttk.Frame(nb, padding=16)
        nb.add(tab1, text="常规")

        ttk.Label(tab1, text="发送的 name 来源:", font=("Microsoft YaHei", 10, "bold")).pack(anchor=tk.W, pady=(0, 8))
        ttk.Radiobutton(tab1, text="缓存加载", variable=self._name_source, value="cache").pack(anchor=tk.W, pady=2)
        ttk.Radiobutton(tab1, text="OCR 扫描  (扫描微信通讯录获取)", variable=self._name_source, value="ocr").pack(anchor=tk.W, pady=2)

        ttk.Separator(tab1, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=12)

        ttk.Label(tab1, text="界面主题:", font=("Microsoft YaHei", 10, "bold")).pack(anchor=tk.W, pady=(0, 8))
        theme_row = ttk.Frame(tab1)
        theme_row.pack(fill=tk.X)
        from src.ui import ui_kit
        theme_combo = ui_kit.make_combo(theme_row, ["vista", "clam", "alt", "xpnative"], width=10)
        theme_combo.configure(textvariable=self._theme_var)
        theme_combo.bind("<<ComboboxSelected>>", self._on_theme_selected)
        theme_combo.pack(side=tk.LEFT)
        ttk.Label(theme_row, text="（即时切换整界面配色）", foreground="gray").pack(side=tk.LEFT, padx=ui_kit.PAD_S)

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
        _ocr_canvas, _ocr_sb, ocr_body, _bind_ocr_wheel = self._build_scroll_area(tab2)

        # OCR 校准按钮置顶
        ttk.Button(ocr_body, text="校准聊天界面标题",
                   command=lambda: self._calibrate("chat_title")).pack(anchor=tk.W, pady=(0, 6))
        ttk.Button(ocr_body, text="校准通讯录区域",
                   command=lambda: self._calibrate("contacts_list")).pack(anchor=tk.W, pady=(0, 6))
        ttk.Button(ocr_body, text="OCR 校准重置",
                   command=self._reset_ocr).pack(anchor=tk.W, pady=(0, 10))

        ttk.Separator(ocr_body, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=8)

        ttk.Label(ocr_body, text="OCR 模型:", font=("Microsoft YaHei", 10, "bold")).pack(anchor=tk.W, pady=(0, 6))
        model_row = ttk.Frame(ocr_body)
        model_row.pack(fill=tk.X, pady=(0, 2))
        ttk.Combobox(model_row, textvariable=self._ocr_model,
                     values=list(OCR_MODELS.values()), state="readonly", width=30).pack(side=tk.LEFT)
        ttk.Label(model_row, text="更改后重启程序生效（模型启动时加载一次）",
                  foreground="gray", font=("", 9)).pack(side=tk.LEFT, padx=8)
        ttk.Separator(ocr_body, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=8)

        ttk.Label(ocr_body, text="调试选项:", font=("Microsoft YaHei", 10, "bold")).pack(anchor=tk.W, pady=(0, 8))
        ttk.Checkbutton(ocr_body, text="保存调试截图 (cache/debug_scan/)", variable=self._ocr_debug).pack(anchor=tk.W)

        ttk.Separator(ocr_body, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=12)

        ttk.Label(ocr_body, text="扫描通讯录并导入:", font=("Microsoft YaHei", 10, "bold")).pack(anchor=tk.W, pady=(0, 8))
        ttk.Label(ocr_body, text="截图页数:").pack(anchor=tk.W)
        ttk.Spinbox(ocr_body, from_=1, to=50, textvariable=self._page_count, width=8).pack(anchor=tk.W, pady=(2, 8))
        ttk.Label(ocr_body, text="每页滚动高度 (px):").pack(anchor=tk.W)
        ttk.Entry(ocr_body, textvariable=self._scroll_px, width=10).pack(anchor=tk.W, pady=(2, 6))
        ttk.Label(ocr_body, text="每次翻的页数:").pack(anchor=tk.W)
        self._pages_per = tk.IntVar(value=self._settings.get("scan_pages_per_scroll", 1))
        ttk.Spinbox(ocr_body, from_=1, to=10, textvariable=self._pages_per, width=8).pack(anchor=tk.W, pady=(2, 10))

        _bind_ocr_wheel(ocr_body)

        # ---- 标签3: 坐标 ----
        tab3 = ttk.Frame(nb, padding=16)
        nb.add(tab3, text="坐标")
        self._build_coord_tab(tab3)

        # ---- 标签4: 多开 ----
        tab4 = ttk.Frame(nb, padding=16)
        nb.add(tab4, text="多开")

        ttk.Label(tab4, text="流水线并发发送的时序参数（多开模式生效）：",
                  font=("Microsoft YaHei", 10, "bold")).pack(anchor=tk.W, pady=(0, 8))

        def _row_delay(parent, label, var):
            row = ttk.Frame(parent)
            row.pack(fill=tk.X, pady=2)
            ttk.Label(row, text=label).pack(side=tk.LEFT)
            ttk.Entry(row, textvariable=var, width=10).pack(side=tk.RIGHT)

        _row_delay(tab4, "窗口激活延迟 (s):", self._mo_activate)
        _row_delay(tab4, "搜索后延迟 (s):", self._mo_search)
        _row_delay(tab4, "就绪检测超时 (s):", self._mo_ready)
        _row_delay(tab4, "账户切换间隔 (s):", self._mo_account_interval)
        _row_delay(tab4, "发送间隔 (s):", self._mo_send_interval)

        ttk.Separator(tab4, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=10)

        retry_row = ttk.Frame(tab4)
        retry_row.pack(fill=tk.X, pady=2)
        ttk.Label(retry_row, text="弹窗检测重试次数:").pack(side=tk.LEFT)
        ttk.Spinbox(retry_row, from_=0, to=5, textvariable=self._mo_popup_retry, width=6).pack(side=tk.RIGHT)

        # ---- 标签5: 延迟 ----
        tab5 = ttk.Frame(nb, padding=16)
        nb.add(tab5, text="延迟")

        ttk.Label(tab5, text="操作之间的延迟（所有账户共用，存 cache/settings.json）：",
                  font=("Microsoft YaHei", 10, "bold")).pack(anchor=tk.W, pady=(0, 8))

        _row_delay(tab5, "窗口激活延迟 (s):", self._op_activate)
        _row_delay(tab5, "搜索后延迟 (s):", self._op_search)
        _row_delay(tab5, "剪贴板复制延迟 (s):", self._op_clipboard)
        _row_delay(tab5, "粘贴后延迟 (s):", self._op_paste)
        _row_delay(tab5, "发送后延迟 (s):", self._op_send_after)
        _row_delay(tab5, "文件发送延迟 (s):", self._op_file_send)
        _row_delay(tab5, "组合键事件间隔 (s):", self._op_key_press)

        ttk.Separator(tab5, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=10)

        _row_delay(tab5, "消息基础间隔 (s):", self._op_send_interval)
        _row_delay(tab5, "间隔抖动比例 (0~1):", self._op_send_jitter)
        ttk.Label(tab5, text="抖动 = 每次实际间隔在基础值 ±该比例 内随机。",
                  foreground="gray", font=("", 9)).pack(anchor=tk.W, pady=(4, 0))

        # ---- 标签6: 更新 ----
        tab6 = ttk.Frame(nb, padding=16)
        nb.add(tab6, text="更新")
        self._build_update_tab(tab6)

        # 跳到指定标签
        if self._initial_tab == "OCR":
            nb.select(tab2)
        elif self._initial_tab == "坐标":
            nb.select(tab3)
        elif self._initial_tab == "多开":
            nb.select(tab4)
        elif self._initial_tab == "延迟":
            nb.select(tab5)
        elif self._initial_tab == "更新":
            nb.select(tab6)

        # ---- 底部 ----
        btn_frame = ttk.Frame(self, padding=12)
        # side=BOTTOM：窗口较小时 [关闭] 始终贴底可见，不被 notebook 内容挤出
        btn_frame.pack(fill=tk.X, side=tk.BOTTOM)
        ttk.Button(btn_frame, text="关闭", command=self._on_close).pack(side=tk.RIGHT)

    def _on_close(self) -> None:
        self._settings["theme"] = self._theme_var.get()
        self._settings["ocr_debug_save"] = self._ocr_debug.get()
        self._settings["logging_enabled"] = self._logging_enabled.get()
        self._settings["scan_page_count"] = self._page_count.get()
        self._settings["scan_scroll_px"] = self._scroll_px.get()
        self._settings["scan_pages_per_scroll"] = self._pages_per.get()
        self._settings["multi_open_activate_delay"] = float(self._mo_activate.get())
        self._settings["multi_open_search_delay"] = float(self._mo_search.get())
        self._settings["multi_open_ready_timeout"] = float(self._mo_ready.get())
        self._settings["multi_open_account_interval"] = float(self._mo_account_interval.get())
        self._settings["multi_open_send_interval"] = float(self._mo_send_interval.get())
        self._settings["multi_open_popup_retry"] = int(self._mo_popup_retry.get())
        self._settings["op_activate_delay"] = float(self._op_activate.get())
        self._settings["op_search_delay"] = float(self._op_search.get())
        self._settings["op_clipboard_delay"] = float(self._op_clipboard.get())
        self._settings["op_paste_delay"] = float(self._op_paste.get())
        self._settings["op_send_after_delay"] = float(self._op_send_after.get())
        self._settings["op_file_send_delay"] = float(self._op_file_send.get())
        self._settings["op_key_press_delay"] = float(self._op_key_press.get())
        self._settings["op_send_interval"] = float(self._op_send_interval.get())
        self._settings["op_send_jitter"] = float(self._op_send_jitter.get())
        # OCR 模型（展示标签 → 值）
        _label = self._ocr_model.get()
        self._settings["ocr_model"] = next(
            (k for k, v in OCR_MODELS.items() if v == _label), "v5")
        save_settings(self._settings)
        # name_source 是账户级设置
        save_account_settings(self._account_name or "",
                              {"name_source": self._name_source.get()})
        self._save_coordinates()
        self.destroy()

    def _on_theme_selected(self, _event=None) -> None:
        """即时切换 ttk 主题（theme_use 后重配命名样式）"""
        from src.ui import ui_kit
        ui_kit.configure_style(self._parent, self._theme_var.get())

    def _on_account_selected(self, _event=None) -> None:
        """设置弹窗内切换账户：保存当前账户 → 重开对应账户的设置"""
        new = self._account_combo.get()
        if not new or new == self._account_name:
            return
        current_tab = self._nb.select()
        tab_name = self._nb.tab(current_tab, "text")
        self._on_close()  # 保存当前账户并关闭
        SettingsDialog(self._parent, tab=tab_name,
                       account_name=new, account_names=self._account_names)

    def _on_sync_settings(self) -> None:
        """「同步其他账户设置(坐标/OCR)」：选来源账户 → 单次复制坐标+OCR校准，之后不跟随"""
        others = [n for n in (self._account_names or []) if n != self._display_account]
        if not others:
            messagebox.showinfo("提示", "没有其他账户可选用。")
            return
        source = self._pick_inherit_source(others)
        if not source:
            return
        copied_coords, copied_calib = copy_account_data(source, self._display_account)
        if not copied_coords and not copied_calib:
            messagebox.showwarning(
                "提示", f"来源账户「{source}」没有已保存的坐标/OCR 校准，无内容可复制。")
            return
        parts = [p for p, ok in (("坐标", copied_coords), ("OCR 校准", copied_calib)) if ok]
        messagebox.showinfo(
            "已同步",
            f"已从「{source}」同步 {'、'.join(parts)} 到当前账户。\n之后各自独立，不再跟随。")
        self._refresh_coord_vars_from_disk()

    def _pick_inherit_source(self, others: list[str]) -> Optional[str]:
        """弹选择框：选一个来源账户（其坐标/OCR校准将复制到当前账户）"""
        dlg = tk.Toplevel(self)
        dlg.title("选择来源账户")
        dlg.resizable(False, False)
        dlg.transient(self)
        dlg.grab_set()
        var = tk.StringVar(value=others[0])
        ttk.Label(dlg, text="从哪个账户复制坐标和 OCR 校准？").pack(padx=16, pady=(14, 6))
        combo = ttk.Combobox(dlg, textvariable=var, values=others,
                             state="readonly", width=16)
        combo.pack(padx=16, pady=4)
        result: list[Optional[str]] = [None]

        def _ok():
            result[0] = var.get()
            dlg.destroy()

        btn = ttk.Frame(dlg)
        btn.pack(pady=(6, 12))
        ttk.Button(btn, text="确定", command=_ok).pack(side=tk.LEFT, padx=4)
        ttk.Button(btn, text="取消", command=dlg.destroy).pack(side=tk.LEFT, padx=4)
        combo.bind("<Return>", lambda e: _ok())
        dlg.update_idletasks()
        try:
            pw, ph = self.winfo_width(), self.winfo_height()
            px, py = self.winfo_rootx(), self.winfo_rooty()
            w, h = dlg.winfo_reqwidth(), dlg.winfo_reqheight()
            dlg.geometry(f"+{px + (pw - w) // 2}+{py + (ph - h) // 2}")
        except Exception:
            pass
        dlg.wait_window()
        return result[0]

    def _refresh_coord_vars_from_disk(self) -> None:
        """复制后把坐标页输入框刷新为落盘值（若坐标页已构建）"""
        if not self._coord_vars:
            return
        from src.utils.coordinates import load_coordinates
        coords = load_coordinates(self._display_account)
        for key, (xv, yv) in self._coord_vars.items():
            if key in coords:
                xv.set(f"{coords[key][0]:.4f}")
                yv.set(f"{coords[key][1]:.4f}")

    def _on_logging_toggled(self) -> None:
        from src.utils.logger import set_file_logging
        set_file_logging(self._logging_enabled.get())

    def _on_clear_logs(self) -> None:
        from src.utils.logger import clear_logs
        clear_logs()
        # 同时清除扫描截图
        import shutil
        for d in ("cache/debug_scan", "cache/temp_scan"):
            try:
                shutil.rmtree(d, ignore_errors=True)
            except Exception:
                pass
        messagebox.showinfo("已清除", "日志和扫描截图已清空。")

    def _reset_ocr(self) -> None:
        if not messagebox.askyesno("OCR 校准重置", "确认清除所有 OCR 校准参数？"):
            return
        reset_calibration(None, self._account_name)
        messagebox.showinfo("已重置", "OCR 校准参数已清除。")

    def _calibrate(self, key: str) -> None:
        """打开 OCR 校准工具（优先走 MainWindow 的入口，带账户）"""
        if self._on_calibrate:
            self._on_calibrate(key)
        else:
            import subprocess
            script = Path(__file__).parent.parent.parent / "calibrate_ocr.py"
            cmd = ["python", str(script), "--key", key]
            if self._account_name:
                cmd += ["--account", self._account_name]
            if self._get_hwnd:
                hwnd = self._get_hwnd()
                if hwnd:
                    cmd += ["--hwnd", str(hwnd)]   # 校准工具作用于当前锁定的窗口
            subprocess.Popen(cmd)

    def _build_scroll_area(self, parent: ttk.Frame) -> tuple:
        """构建可滚动内容区（OCR/坐标共用）

        Returns: (canvas, scrollbar, scroll_frame, bind_mousewheel)
        """
        canvas = tk.Canvas(parent, borderwidth=0, highlightthickness=0)
        scrollbar = ttk.Scrollbar(parent, orient=tk.VERTICAL, command=canvas.yview)
        scroll_frame = ttk.Frame(canvas)
        scroll_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        cw = canvas.create_window((0, 0), window=scroll_frame, anchor=tk.NW)
        # scroll_frame 宽度跟随 canvas，防止右边内容被截断
        canvas.bind("<Configure>", lambda e: canvas.itemconfig(cw, width=e.width))
        canvas.configure(yscrollcommand=scrollbar.set)

        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        def _bind_mousewheel(widget):
            widget.bind("<MouseWheel>", _on_mousewheel)
            for child in widget.winfo_children():
                _bind_mousewheel(child)

        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        return canvas, scrollbar, scroll_frame, _bind_mousewheel

    def _build_coord_tab(self, parent: ttk.Frame) -> None:
        """构建坐标标签页：每个坐标一行 X% + Y% spinbox"""
        from src.utils.coordinates import (
            load_coordinates, save_coordinates, reset_coordinates,
            COORD_LABELS, COORD_GROUPS, DEFAULT_COORDINATES,
        )

        # 提前导入，避免循环内异常导致整个标签页空白
        try:
            from src.ui.coord_picker import has_image_for
        except Exception:
            has_image_for = lambda _k: False

        self._all_coord_keys: list[str] = []
        coords = load_coordinates(self._account_name)
        self._coord_loaded = coords

        # 滚动区（坐标多时避免溢出）
        _canvas, _scrollbar, scroll_frame, _bind_mousewheel = self._build_scroll_area(parent)

        pct_vcmd = (parent.register(_validate_pct), "%P")

        for group_name, keys in COORD_GROUPS:
            group_row = ttk.Frame(scroll_frame)
            group_row.pack(fill=tk.X, pady=(12, 4))
            # 组名列 weight=1: 窗口变窄时先压缩组名, 保护右侧「鼠标位置」按钮
            group_row.columnconfigure(0, weight=1)
            ttk.Label(group_row, text=group_name,
                      font=("Microsoft YaHei", 10, "bold"),
                      anchor=tk.W).grid(row=0, column=0, sticky=tk.W)
            if group_name == "微信主界面":
                ttk.Button(group_row, text="鼠标位置", width=9,
                           command=self._launch_mouse_tracker).grid(row=0, column=1)

            for key in keys:
                self._all_coord_keys.append(key)
                cx, cy = coords.get(key, DEFAULT_COORDINATES[key])
                label_text = COORD_LABELS.get(key, key)

                row = ttk.Frame(scroll_frame)
                row.pack(fill=tk.X, pady=1)
                # 名称列 weight=1: 窗口变窄时先压缩名称文字, 保护右侧 X/Y 输入和按钮
                row.columnconfigure(0, weight=1)

                ttk.Label(row, text=label_text, width=16, anchor=tk.W).grid(
                    row=0, column=0, sticky=tk.W)

                # X%
                ttk.Label(row, text="X:").grid(row=0, column=1)
                x_var = tk.StringVar(value=f"{cx:.4f}")
                x_entry = ttk.Entry(row, textvariable=x_var, width=6,
                                    validate="key", validatecommand=pct_vcmd)
                x_entry.grid(row=0, column=2, padx=(0, 4))

                # Y%
                ttk.Label(row, text="Y:").grid(row=0, column=3)
                y_var = tk.StringVar(value=f"{cy:.4f}")
                y_entry = ttk.Entry(row, textvariable=y_var, width=6,
                                    validate="key", validatecommand=pct_vcmd)
                y_entry.grid(row=0, column=4, padx=(0, 4))

                # 测试点击按钮
                ttk.Button(row, text="测试", width=4,
                           command=lambda k=key: self._test_coord_click(k)).grid(
                    row=0, column=5, padx=(0, 2))

                # 校准按钮（有帮助图片才显示）
                if has_image_for(key):
                    ttk.Button(row, text="校准",
                               command=lambda k=key: self._launch_coord_picker(k)).grid(
                        row=0, column=6)

                self._coord_vars[key] = (x_var, y_var)

        # 所有控件创建完毕，绑定滚轮事件
        _bind_mousewheel(scroll_frame)

    def _save_coordinates(self) -> None:
        """收集坐标输入框的值并保存

        未改动且该账户无专属文件 → 跳过（保持继承全局）；
        已改动或已有专属文件 → 写入账户专属文件。
        """
        if not self._coord_vars:
            return
        coords = {}
        for key, (xv, yv) in self._coord_vars.items():
            try:
                x = float(xv.get())
                y = float(yv.get())
                coords[key] = (x, y)
            except ValueError:
                coords[key] = DEFAULT_COORDINATES.get(key, (0.0, 0.0))
        if not should_save_coordinates(
                coords, getattr(self, "_coord_loaded", {}),
                account_has_override(self._account_name)):
            return  # 没改任何值、也无专属文件 → 保持继承全局
        save_coordinates(coords, self._account_name)

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
                hwnd = self._get_hwnd() if self._get_hwnd else None
                if hwnd:
                    bridge._hwnd = hwnd   # 测试点击作用于当前锁定的窗口
                elif not bridge.find_window():
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

    def _launch_coord_picker(self, key: str) -> None:
        """打开坐标校准帮助器：缩略图 + 右键取点"""
        from src.utils.coordinates import COORD_LABELS
        from src.ui.coord_picker import CoordPicker, CM_KEYS

        label = COORD_LABELS.get(key, key)

        def on_save(coord_key: str, x: float, y: float) -> None:
            xv, yv = self._coord_vars.get(coord_key, (None, None))
            if xv is not None:
                xv.set(f"{x:.4f}")
            if yv is not None:
                yv.set(f"{y:.4f}")
            import logging
            logging.getLogger(__name__).info(
                "已保存 %s 坐标：(%.4f, %.4f)", label, x, y)

        hwnd = self._get_hwnd() if self._get_hwnd else None
        CoordPicker(self, key, label, on_save, is_cm=(key in CM_KEYS), hwnd=hwnd)

    def _build_update_tab(self, parent: ttk.Frame) -> None:
        """构建更新标签页"""
        # 版本信息
        ver_frame = ttk.Frame(parent)
        ver_frame.pack(fill=tk.X)

        ttk.Label(ver_frame, text="软件版本",
                  font=("Microsoft YaHei", 10, "bold")).pack(anchor=tk.W)

        from update import get_local_version
        local_ver = get_local_version()
        self._version_label = ttk.Label(
            ver_frame, text=f"当前版本：v{local_ver}",
            font=("Microsoft YaHei", 10))
        self._version_label.pack(anchor=tk.W, pady=(8, 4))

        self._update_status = ttk.Label(
            ver_frame, text="",
            font=("Microsoft YaHei", 9), foreground="gray")
        self._update_status.pack(anchor=tk.W)

        ttk.Separator(parent, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=16)

        # 检查更新按钮
        ttk.Button(
            parent, text="🔍 检查更新",
            command=self._check_for_updates,
        ).pack(pady=(0, 8))

        ttk.Label(
            parent,
            text="检查 GitHub 上的最新版本并下载更新。\n"
                 "更新会覆盖程序文件，保留 cache/ 和 logs/。\n"
                 "更新完成后需重启程序。",
            font=("", 9), foreground="gray", wraplength=380,
        ).pack(anchor=tk.W)

    def _check_for_updates(self):
        """启动 update.py 子进程检查更新"""
        import subprocess
        import os

        update_script = Path(__file__).parent.parent.parent / "update.py"
        try:
            subprocess.Popen(
                [sys.executable, str(update_script), "--parent-pid", str(os.getpid())],
                cwd=str(Path(__file__).parent.parent.parent),
                creationflags=subprocess.CREATE_NO_WINDOW
                if os.name == "nt" else 0,
            )
            self._update_status.config(
                text="更新窗口已打开，请在弹出的窗口中操作。", foreground="gray")
        except Exception as e:
            self._update_status.config(
                text=f"启动失败: {e}", foreground="red")

    def _center(self, parent: tk.Widget) -> None:
        self.update_idletasks()
        try:
            pw = parent.winfo_width()
            ph = parent.winfo_height()
            px = parent.winfo_rootx()
            py = parent.winfo_rooty()
            sw = self.winfo_screenwidth()
            sh = self.winfo_screenheight()

            # 自适应尺寸：不超过屏幕 90%
            w = min(600, int(sw * 0.9))
            h = min(540, int(sh * 0.9))

            if pw > 10 and ph > 10:
                x = px + (pw - w) // 2
                y = py + (ph - h) // 2
            else:
                x = (sw - w) // 2
                y = (sh - h) // 2

            # 边界检测：不超出屏幕
            x = max(0, min(x, sw - w))
            y = max(0, min(y, sh - h))

            self.geometry(f"{w}x{h}+{x}+{y}")
        except Exception:
            pass
