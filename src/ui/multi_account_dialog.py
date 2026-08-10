"""多开引导窗口 — 检测微信窗口 → 逐个前台确认账户名 → 生成会话

流程：
1. [检测微信窗口] 枚举所有微信主窗口
2. [逐个确认账户] 对每个窗口 SetForegroundWindow 显示到最前，
   弹输入框让用户确认账户名（默认 账户1/账户2…）
3. 列表支持重命名/删除
4. [确定并进入多开] 返回 MultiAccountSession；[取消] 返回 None
"""
import logging
import time
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
from typing import Optional

from src.driver.wechat_bridge import WeChatBridge
from src.services.multi_account import MultiAccountSession

logger = logging.getLogger(__name__)


def _default_name(index: int) -> str:
    return f"账户{index + 1}"


class MultiOpenWizard:
    """多开引导（模态）"""

    def __init__(self, root: tk.Tk, bridge: WeChatBridge):
        self.root = root
        self.bridge = bridge
        self.result: Optional[MultiAccountSession] = None

        self.root.title("多开设置")
        self.root.geometry("480x440")
        self.root.minsize(400, 320)

        self._frames: list[tuple[int, str, str]] = []
        self._session = MultiAccountSession()
        self._build_ui()

    def _build_ui(self):
        pad = {"padx": 12, "pady": 6}

        ttk.Label(
            self.root,
            text="检测到微信窗口后，逐个把窗口显示到最前，\n请在每个窗口确认它属于哪个账户（账户名可自定义）。",
            justify=tk.LEFT,
        ).pack(anchor=tk.W, **pad)

        # 检测行
        row = ttk.Frame(self.root)
        row.pack(fill=tk.X, **pad)
        self._btn_detect = ttk.Button(row, text="① 检测微信窗口", command=self._on_detect)
        self._btn_detect.pack(side=tk.LEFT)
        self._lbl_count = ttk.Label(row, text="", foreground="gray")
        self._lbl_count.pack(side=tk.LEFT, padx=8)

        # 绑定列表
        tree_frame = ttk.Frame(self.root)
        tree_frame.pack(fill=tk.BOTH, expand=True, **pad)
        cols = ("order", "name", "hwnd")
        self._tree = ttk.Treeview(tree_frame, columns=cols, show="headings", height=8)
        self._tree.heading("order", text="顺序")
        self._tree.heading("name", text="账户名")
        self._tree.heading("hwnd", text="窗口句柄")
        self._tree.column("order", width=50, anchor=tk.CENTER)
        self._tree.column("name", width=170)
        self._tree.column("hwnd", width=110)
        self._tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self._tree.yview)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        self._tree.configure(yscrollcommand=sb.set)

        # 操作行
        ops = ttk.Frame(self.root)
        ops.pack(fill=tk.X, **pad)
        ttk.Button(ops, text="② 逐个确认账户", command=self._on_confirm_all).pack(side=tk.LEFT)
        ttk.Button(ops, text="重命名", command=self._on_rename).pack(side=tk.LEFT, padx=4)
        ttk.Button(ops, text="删除", command=self._on_delete).pack(side=tk.LEFT)

        # 底部按钮
        btns = ttk.Frame(self.root)
        btns.pack(fill=tk.X, side=tk.BOTTOM, **pad)
        ttk.Button(btns, text="取消", command=self._on_cancel).pack(side=tk.RIGHT)
        ttk.Button(btns, text="确定并进入多开", command=self._on_ok).pack(side=tk.RIGHT, padx=6)

    # ---- 检测 ----
    def _on_detect(self):
        frames = self.bridge.find_all_windows()
        if not frames:
            messagebox.showwarning("提示", "未找到微信窗口，请先登录微信。")
            return
        self._frames = frames
        self._lbl_count.config(text=f"检测到 {len(frames)} 个微信窗口")
        self._refresh_tree()

    # ---- 逐个确认 ----
    def _on_confirm_all(self):
        if not self._frames:
            messagebox.showwarning("提示", "请先点击「检测微信窗口」。")
            return
        start = len(self._session.accounts)
        for i in range(start, len(self._frames)):
            hwnd, title, _cls = self._frames[i]
            if not self._bring_to_front(hwnd):
                messagebox.showwarning("提示", f"无法激活窗口 0x{hwnd:X}，跳过。")
                continue
            name = simpledialog.askstring(
                "确认账户",
                f"窗口 {i + 1}/{len(self._frames)}\n当前显示在最前的微信窗口是哪个账户？\n\n标题: {title}",
                initialvalue=_default_name(i),
                parent=self.root,
            )
            if name is None:
                break  # 用户点了取消 → 停止逐个确认，保留已确认的
            name = name.strip() or _default_name(i)
            self._session.add(name=name, hwnd=hwnd)
        self._refresh_tree()

    def _bring_to_front(self, hwnd: int) -> bool:
        """把微信窗口置顶激活（复用 activate_window 的 Alt 技巧）"""
        import win32api
        import win32con
        import win32gui
        try:
            if win32gui.IsIconic(hwnd):
                win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
                time.sleep(0.2)
            win32gui.SetWindowPos(hwnd, win32con.HWND_TOPMOST, 0, 0, 0, 0,
                                  win32con.SWP_NOMOVE | win32con.SWP_NOSIZE)
            win32gui.SetWindowPos(hwnd, win32con.HWND_NOTOPMOST, 0, 0, 0, 0,
                                  win32con.SWP_NOMOVE | win32con.SWP_NOSIZE)
            win32api.keybd_event(win32con.VK_MENU, 0, 0, 0)
            win32gui.SetForegroundWindow(hwnd)
            win32api.keybd_event(win32con.VK_MENU, 0, win32con.KEYEVENTF_KEYUP, 0)
            time.sleep(0.3)
            return True
        except Exception:
            logger.exception("激活窗口失败: 0x%X", hwnd)
            return False

    # ---- 列表操作 ----
    def _refresh_tree(self):
        self._tree.delete(*self._tree.get_children())
        for acc in self._session.accounts:
            self._tree.insert("", tk.END, values=(acc.order + 1, acc.name, f"0x{acc.hwnd:X}"))

    def _selected_index(self) -> Optional[int]:
        sel = self._tree.selection()
        if not sel:
            return None
        return int(self._tree.index(sel[0]))

    def _on_rename(self):
        idx = self._selected_index()
        if idx is None:
            return
        acc = self._session.accounts[idx]
        new_name = simpledialog.askstring(
            "重命名", "新账户名:", initialvalue=acc.name, parent=self.root)
        if new_name and new_name.strip():
            if not self._session.rename(idx, new_name.strip()):
                messagebox.showwarning("提示", "重命名失败：账户名重复或为空。")
        self._refresh_tree()

    def _on_delete(self):
        idx = self._selected_index()
        if idx is None:
            return
        self._session.remove(idx)
        self._refresh_tree()

    # ---- 完成 ----
    def _on_ok(self):
        if not self._session.accounts:
            messagebox.showwarning("提示", "还没有绑定任何账户。")
            return
        self.result = self._session
        self.root.destroy()

    def _on_cancel(self):
        self.result = None
        self.root.destroy()


def run_multiopen_wizard(bridge: WeChatBridge) -> Optional[MultiAccountSession]:
    """打开多开引导，返回会话（取消返回 None）"""
    root = tk.Tk()
    wizard = MultiOpenWizard(root, bridge)
    root.mainloop()
    return wizard.result
