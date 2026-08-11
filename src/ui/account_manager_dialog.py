"""账户管理弹窗 — 持久账户列表：新建/重命名/删除/双击切换

复用 multi_account_dialog 的 Treeview + 按钮行模式，但无窗口绑定。
双击某账户 → 切到该账户并关闭弹窗（on_switch 回调）。
"""
import logging
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
from typing import Callable, Optional

from src.services import account_registry as reg
from src.services.friend_service import FriendService

logger = logging.getLogger(__name__)


class AccountManagerDialog(tk.Toplevel):
    """账户管理（模态）：列表显示账户名 + 联系人数量"""

    def __init__(self, parent, current: str = "",
                 on_switch: Optional[Callable[[str], None]] = None):
        super().__init__(parent)
        self.title("账户管理")
        self.geometry("380x340")
        self.resizable(False, False)
        self.transient(parent)
        self._current = current
        self._on_switch = on_switch      # (name) -> None，双击切换回调
        self._build_ui()
        self._refresh()

    def _build_ui(self):
        frame = ttk.Frame(self, padding=10)
        frame.pack(fill=tk.BOTH, expand=True)

        cols = ("name", "count")
        self._tree = ttk.Treeview(frame, columns=cols, show="headings", height=10)
        self._tree.heading("name", text="账户名")
        self._tree.heading("count", text="联系人")
        self._tree.column("name", width=200)
        self._tree.column("count", width=70, anchor=tk.CENTER)
        self._tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self._tree.bind("<Double-1>", self._on_double_click)

        ops = ttk.Frame(self, padding=(10, 0, 10, 10))
        ops.pack(fill=tk.X)
        ttk.Button(ops, text="新建账户", command=self._on_create).pack(side=tk.LEFT)
        ttk.Button(ops, text="重命名", command=self._on_rename).pack(side=tk.LEFT, padx=4)
        ttk.Button(ops, text="删除", command=self._on_delete).pack(side=tk.LEFT)
        ttk.Button(ops, text="关闭", command=self.destroy).pack(side=tk.RIGHT)

    # ---- 列表 ----
    def _refresh(self):
        self._tree.delete(*self._tree.get_children())
        for name in reg.load_accounts():
            fs = FriendService.for_account(name)
            fs.load_cache()
            self._tree.insert("", tk.END, values=(name, fs.count),
                              tags=("current",) if name == self._current else ())
        # 当前账户高亮
        self._tree.tag_configure("current", background="#e8f0fe")

    def _selected(self) -> Optional[str]:
        sel = self._tree.selection()
        if not sel:
            return None
        return self._tree.item(sel[0], "values")[0]

    def _on_double_click(self, _e=None):
        name = self._selected()
        if name and self._on_switch:
            self._on_switch(name)
            self.destroy()

    # ---- 操作 ----
    def _on_create(self):
        name = simpledialog.askstring("新建账户", "账户名:", parent=self)
        if not name or not name.strip():
            return
        name = name.strip()
        if name in reg.load_accounts():
            messagebox.showwarning("提示", "账户已存在。")
            return
        reg.save_accounts(reg.load_accounts() + [name])
        self._refresh()

    def _on_rename(self):
        old = self._selected()
        if not old:
            messagebox.showinfo("提示", "请先选择一个账户。")
            return
        new = simpledialog.askstring("重命名", "新账户名:", initialvalue=old, parent=self)
        if new and new.strip():
            if not reg.rename_account(old, new.strip()):
                messagebox.showwarning("提示", "重命名失败：账户不存在或重名。")
        self._refresh()

    def _on_delete(self):
        name = self._selected()
        if not name:
            messagebox.showinfo("提示", "请先选择一个账户。")
            return
        if name == reg.DEFAULT_ACCOUNT_NAME:
            messagebox.showinfo("提示", "默认账户不可删除。")
            return
        if not messagebox.askyesno("删除", f"确认删除账户 [{name}]？其联系人与校准数据将一并删除。"):
            return
        reg.delete_account(name)
        self._refresh()
