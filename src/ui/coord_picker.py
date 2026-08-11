"""坐标校准帮助器 — 缩略图弹窗 + 右键捕获坐标"""
import logging
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import ttk
from typing import Callable

import win32api
from PIL import Image, ImageTk

logger = logging.getLogger(__name__)

HELP_DIR = Path(__file__).resolve().parent.parent.parent / "帮助" / "pngs"

# 坐标 key → 帮助图片文件名
HELP_IMAGES: dict[str, str] = {
    "tab_chat":               "聊天标签.png",
    "tab_contacts":           "通讯录标签.png",
    "btn_contacts_mgr":       "通讯录管理按钮.png",
    "chat_first":             "聊天区域点击（第一个聊天）.png",
    "cm_search_box":          "通讯录管理-搜索框.png",
    "cm_list_focus":          "通讯录管理-列表聚焦.png",
}

# 通讯录管理窗口内的坐标（需要先打开通讯录管理，坐标相对于该弹窗）
CM_KEYS = {"cm_search_box", "cm_list_focus"}


def help_image_exists(coord_key: str) -> bool:
    """检查某个坐标是否有帮助图片"""
    filename = HELP_IMAGES.get(coord_key, "")
    return filename != "" and (HELP_DIR / filename).exists()


def has_image_for(coord_key: str) -> bool:
    return coord_key in HELP_IMAGES and help_image_exists(coord_key)


# ================================================================
# 缩略图弹窗
# ================================================================

class ThumbnailWindow(tk.Toplevel):
    """显示帮助截图 + 提示文字「如图请右键点击"xx"」"""

    def __init__(self, parent: tk.Widget, coord_key: str, label: str):
        super().__init__(parent)
        self.title(f"坐标参考 - {label}")
        self.resizable(False, False)
        self.transient(parent)

        # 提示文字
        ttk.Label(
            self, text=f'如图请右键点击"{label}"',
            font=("Microsoft YaHei", 11, "bold"),
            padding=12,
        ).pack()

        # 加载并显示缩略图
        img_path = HELP_DIR / HELP_IMAGES.get(coord_key, "")
        self._photo = None
        if img_path.exists():
            try:
                img = Image.open(img_path)
                img.thumbnail((400, 300), Image.LANCZOS)
                self._photo = ImageTk.PhotoImage(img)
                tk.Label(self, image=self._photo).pack(padx=10, pady=(0, 10))
            except Exception as e:
                ttk.Label(self, text=f"图片加载失败: {e}").pack(padx=20, pady=20)
        else:
            ttk.Label(self, text="（帮助图片不存在）").pack(padx=20, pady=20)

        self.update_idletasks()  # 让 tk 计算好 reqwidth/reqheight


# ================================================================
# 坐标记录器
# ================================================================

class RecorderWindow(tk.Toplevel):
    """topmost 小窗口：轮询右键 → 捕捉坐标 → 保存/取消"""

    def __init__(
        self,
        parent: tk.Widget,
        coord_key: str,
        label: str,
        on_save: Callable[[str, float, float], None],
        on_cancel: Callable[[], None],
        is_cm: bool = False,
    ):
        super().__init__(parent)
        self.title(f"右键取点 - {label}")
        self.resizable(False, False)
        self.attributes('-topmost', True)
        self.transient(parent)
        self.protocol("WM_DELETE_WINDOW", self._cancel)

        self._coord_key = coord_key
        self._label = label
        self._on_save = on_save
        self._on_cancel = on_cancel
        self._is_cm = is_cm
        self._captured_x = None  # type: Optional[float]
        self._captured_y = None  # type: Optional[float]
        self._running = True

        # 提示
        self._hint_label = ttk.Label(
            self,
            text=f'请在微信窗口中右键点击"{label}"位置',
            font=("Microsoft YaHei", 10),
            padding=(16, 12),
        )
        self._hint_label.pack()

        # 坐标显示
        self._coord_var = tk.StringVar(value="X: --.----  Y: --.----")
        ttk.Label(
            self, textvariable=self._coord_var,
            font=("Consolas", 14, "bold"),
        ).pack(pady=(0, 10))

        # 按钮
        btn_frame = ttk.Frame(self)
        btn_frame.pack(pady=(0, 14))
        self._save_btn = ttk.Button(btn_frame, text="保存", command=self._save, state=tk.DISABLED)
        self._save_btn.pack(side=tk.LEFT, padx=8)
        ttk.Button(btn_frame, text="取消", command=self._cancel).pack(side=tk.LEFT, padx=8)

        self.update_idletasks()  # 让 tk 计算好 reqwidth/reqheight

        # 启动右键轮询线程
        self._poll_thread = threading.Thread(target=self._poll_right_click, daemon=True)
        self._poll_thread.start()

    # ----------------------------------------------------------
    # 右键轮询
    # ----------------------------------------------------------

    def _poll_right_click(self) -> None:
        """后台线程：50ms 轮询 GetAsyncKeyState(0x02)"""
        import win32gui as _wg
        import win32process as _wp
        from src.driver.wechat_bridge import WeChatBridge

        bridge = WeChatBridge()

        while self._running:
            try:
                if win32api.GetAsyncKeyState(0x02) & 0x8000:
                    x, y = win32api.GetCursorPos()
                    rect = None

                    if self._is_cm:
                        rect = self._find_cm_rect(bridge)
                    else:
                        if bridge.find_window():
                            rect = bridge.get_window_rect()

                    if rect:
                        ww = rect[2] - rect[0]
                        wh = rect[3] - rect[1]
                        rx, ry = x - rect[0], y - rect[1]
                        if ww > 0 and wh > 0 and 0 <= rx <= ww and 0 <= ry <= wh:
                            px = rx / ww
                            py = ry / wh
                            self._captured_x = px
                            self._captured_y = py
                            self.after(0, self._on_capture)
                            time.sleep(0.3)  # 防抖

            except Exception:
                pass
            time.sleep(0.05)

    @staticmethod
    def _find_cm_rect(bridge):  # -> Optional[tuple]
        """找通讯录管理弹窗的屏幕坐标"""
        import win32gui as _wg
        import win32process as _wp
        if not bridge.find_window():
            return None
        try:
            _, main_pid = _wp.GetWindowThreadProcessId(bridge.hwnd)
        except Exception:
            return None

        result = []

        def _enum(hwnd, _):
            if hwnd == bridge.hwnd: return True
            if not _wg.IsWindowVisible(hwnd): return True
            if "通讯录" not in _wg.GetWindowText(hwnd): return True
            try:
                _, pid = _wp.GetWindowThreadProcessId(hwnd)
            except Exception:
                return True
            if pid != main_pid: return True
            result.append(_wg.GetWindowRect(hwnd))
            return False

        _wg.EnumWindows(_enum, None)
        return result[0] if result else None

    def _on_capture(self) -> None:
        if not self._running:
            return
        try:
            self._coord_var.set(f"X: {self._captured_x:.4f}  Y: {self._captured_y:.4f}")
            self._hint_label.config(text=f'已捕获"{self._label}"，检查无误后保存')
            self._save_btn.config(state=tk.NORMAL)
        except tk.TclError:
            pass

    # ----------------------------------------------------------
    # 保存 / 取消
    # ----------------------------------------------------------

    def _save(self) -> None:
        self._running = False
        try:
            self._on_save(self._coord_key, self._captured_x, self._captured_y)
        except Exception:
            logger.exception("保存回调异常")
        self.destroy()

    def _cancel(self) -> None:
        self._running = False
        try:
            self._on_cancel()
        except Exception:
            logger.exception("取消回调异常")
        self.destroy()


# ================================================================
# 胶水层
# ================================================================

class CoordPicker:
    """同时打开缩略图窗口 + 坐标记录器，管理生命周期"""

    def __init__(
        self,
        parent: tk.Widget,
        coord_key: str,
        label: str,
        on_save: Callable[[str, float, float], None],
        is_cm: bool = False,
    ):
        self._parent = parent
        self._user_on_save = on_save

        # 通讯录管理坐标：先打开通讯录管理窗口
        if is_cm:
            self._open_contacts_manager()

        self._thumb = ThumbnailWindow(parent, coord_key, label)
        self._recorder = RecorderWindow(parent, coord_key, label,
                                         on_save=self._on_save,
                                         on_cancel=self._on_cancel,
                                         is_cm=is_cm)

        # 统一布局：缩略图在上，记录器在下，整体居中于设置窗口
        self._layout_side_by_side(parent)

        # 对焦目标窗口，方便用户右键取点
        if is_cm:
            self._focus_cm_window()
        else:
            self._focus_wechat()

    def _on_save(self, coord_key: str, x: float, y: float) -> None:
        self._close_thumb()
        self._user_on_save(coord_key, x, y)
        logger.info("已保存 %s 坐标：(%.4f, %.4f)", coord_key, x, y)
        self._focus_parent()

    def _on_cancel(self) -> None:
        self._close_thumb()
        self._focus_parent()

    def _close_thumb(self) -> None:
        try:
            self._thumb.destroy()
        except tk.TclError:
            pass

    def _layout_side_by_side(self, parent: tk.Widget) -> None:
        """缩略图在上，记录器在下，整体居中于设置窗口"""
        gap = 8
        try:
            px = parent.winfo_rootx()
            py = parent.winfo_rooty()
            pw = parent.winfo_width()
            ph = parent.winfo_height()

            thumb_w = self._thumb.winfo_reqwidth()
            thumb_h = self._thumb.winfo_reqheight()
            rec_w = self._recorder.winfo_reqwidth()
            rec_h = self._recorder.winfo_reqheight()

            total_w = max(thumb_w, rec_w)
            total_h = thumb_h + gap + rec_h

            base_x = px + (pw - total_w) // 2
            base_y = py + (ph - total_h) // 2

            self._thumb.geometry(f"+{base_x + (total_w - thumb_w) // 2}+{base_y}")
            self._recorder.geometry(f"+{base_x + (total_w - rec_w) // 2}+{base_y + thumb_h + gap}")
        except Exception:
            pass

    def _focus_parent(self) -> None:
        try:
            self._parent.lift()
            self._parent.focus_force()
        except Exception:
            pass

    @staticmethod
    def _open_contacts_manager() -> None:
        """打开通讯录管理窗口（后台线程，不阻塞 UI）"""
        def _do():
            try:
                from src.driver.wechat_bridge import WeChatBridge
                bridge = WeChatBridge()
                if bridge.find_window():
                    hwnd = bridge.open_contacts_manager()
                    if hwnd:
                        logger.info("通讯录管理窗口已打开: 0x%X", hwnd)
            except Exception:
                logger.exception("打开通讯录管理窗口失败")
        threading.Thread(target=_do, daemon=True).start()

    @staticmethod
    def _focus_wechat() -> None:
        """激活微信主窗口，方便用户右键取点"""
        try:
            from src.driver.wechat_bridge import WeChatBridge
            bridge = WeChatBridge()
            if bridge.find_window():
                bridge.activate_window()
        except Exception:
            pass

    @staticmethod
    def _focus_cm_window() -> None:
        """激活通讯录管理窗口（只匹配和微信同进程的窗口，排除自身）"""
        import win32gui as _wg
        import win32con as _wc
        import win32process as _wp

        self_pid = None
        try:
            import os as _os
            self_pid = _os.getpid()
        except Exception:
            pass

        # 先找到微信主窗口 PID
        from src.driver.wechat_bridge import WeChatBridge
        bridge = WeChatBridge()
        if not bridge.find_window():
            return
        try:
            _, main_pid = _wp.GetWindowThreadProcessId(bridge.hwnd)
        except Exception:
            return

        def _enum(hwnd, _):
            if not _wg.IsWindowVisible(hwnd):
                return True
            if "通讯录" not in _wg.GetWindowText(hwnd):
                return True
            # 排除自身进程窗口
            try:
                _, pid = _wp.GetWindowThreadProcessId(hwnd)
            except Exception:
                return True
            if pid == self_pid:
                return True
            if pid != main_pid:
                return True
            try:
                _wg.SetForegroundWindow(hwnd)
                placement = _wg.GetWindowPlacement(hwnd)
                if placement[1] != _wc.SW_SHOWMAXIMIZED:
                    _wg.ShowWindow(hwnd, _wc.SW_MAXIMIZE)
            except Exception:
                pass
            return False
        _wg.EnumWindows(_enum, None)
