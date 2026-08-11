"""多开引导窗口 — 检测微信窗口 → 逐个绑定到持久账户 → 生成会话

流程：
1. [检测微信窗口] 枚举所有微信主窗口
2. [逐个确认账户] 对每个窗口 SetForegroundWindow 显示到最前，
   弹选择框让用户选该窗口属于哪个持久账户（或新建账户）
3. 列表支持重命名/删除（重命名 = 改绑到另一账户）
4. [确定并进入多开] 返回 MultiAccountSession；[取消] 返回 None
"""
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
from typing import Any, Optional

from src.services import account_registry as reg
from src.services.multi_account import MultiAccountSession


class MultiOpenWizard:
    """多开引导（模态）"""

    def __init__(self, root: tk.Tk, bridge: Any):
        self.root = root
        self.bridge = bridge
        self.result: Optional[MultiAccountSession] = None

        self.root.title("多开设置")
        self.root.geometry("480x440")
        self.root.minsize(400, 320)
        # 屏幕居中（主窗口已销毁，无父窗口可相对）
        self.root.update_idletasks()
        _w, _h = 480, 440
        _x = (self.root.winfo_screenwidth() - _w) // 2
        _y = (self.root.winfo_screenheight() - _h) // 2
        self.root.geometry(f"{_w}x{_h}+{_x}+{_y}")

        self._frames: list[tuple[int, str, str]] = []
        self._session = MultiAccountSession()
        self._build_ui()

    def _build_ui(self):
        pad = {"padx": 12, "pady": 6}

        ttk.Label(
            self.root,
            text="检测到微信窗口后，逐个把窗口显示到最前，\n请在每个窗口确认它属于哪个账户（账户名可自定义）。\n\n⚠ 请先将微信窗口平铺、勿重叠，否则发送前会被拦截提醒。",
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
        if self._session.accounts:
            if not messagebox.askyesno("重新检测", "重新检测将清空已绑定的账户，是否继续？"):
                return
            self._session = MultiAccountSession()
        self._frames = frames
        self._lbl_count.config(text=f"检测到 {len(frames)} 个微信窗口")
        self._refresh_tree()

    # ---- 逐个确认 ----
    def _on_confirm_all(self):
        if not self._frames:
            messagebox.showwarning("提示", "请先点击「检测微信窗口」。")
            return
        accounts = reg.load_accounts()
        start = len(self._session.accounts)
        for i in range(start, len(self._frames)):
            hwnd, title, _cls = self._frames[i]
            if not self.bridge.activate_hwnd(hwnd):
                messagebox.showwarning("提示", f"无法激活窗口 0x{hwnd:X}（可能被前台锁定），跳过。")
                continue
            name = self._pick_account(i + 1, len(self._frames), title, accounts)
            if name is None:
                break  # 取消 → 停止逐个确认，保留已确认的
            if not self._session.add(name=name, hwnd=hwnd):
                messagebox.showwarning("提示", f"窗口已绑定给 [{name}]，或账户冲突，跳过。")
        self._refresh_tree()

    def _pick_account(self, idx: int, total: int, title: str,
                      accounts: list[str]) -> Optional[str]:
        """弹选择框：选已有持久账户 / 新建账户。取消返回 None。"""
        dlg = tk.Toplevel(self.root)
        dlg.title(f"窗口 {idx}/{total} 绑定账户")
        dlg.transient(self.root)
        dlg.grab_set()
        dlg.resizable(False, False)
        ttk.Label(dlg, text=f"当前前台微信窗口属于哪个账户？\n窗口标题: {title}",
                  justify=tk.LEFT).pack(padx=16, pady=(12, 6))
        var = tk.StringVar(value=accounts[0] if accounts else "")
        combo = ttk.Combobox(dlg, textvariable=var, values=accounts + ["＋ 新建账户…"],
                             state="readonly", width=18)
        combo.pack(padx=16, pady=4)
        result: list[Optional[str]] = [None]

        def _ok():
            v = var.get()
            if v == "＋ 新建账户…":
                n = simpledialog.askstring("新建账户", "账户名:", parent=dlg)
                if n and n.strip():
                    n = n.strip()
                    if n in accounts:
                        messagebox.showwarning("提示", "账户已存在。", parent=dlg)
                        return
                    accounts.append(n)
                    reg.save_accounts(list(accounts))
                    result[0] = n
                    dlg.destroy()
                return
            if v:
                result[0] = v
                dlg.destroy()

        btn = ttk.Frame(dlg)
        btn.pack(pady=(8, 12))
        ttk.Button(btn, text="确定", command=_ok).pack(side=tk.LEFT, padx=4)
        ttk.Button(btn, text="取消", command=dlg.destroy).pack(side=tk.LEFT, padx=4)
        # 相对向导窗口居中（tkinter 默认不定位，会叠在父窗口标题栏上）
        dlg.update_idletasks()
        _w = dlg.winfo_reqwidth()
        _h = dlg.winfo_reqheight()
        _x = self.root.winfo_rootx() + (self.root.winfo_width() - _w) // 2
        _y = self.root.winfo_rooty() + (self.root.winfo_height() - _h) // 2
        dlg.geometry(f"{_w}x{_h}+{_x}+{_y}")
        dlg.wait_window()
        return result[0]

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
        accounts = reg.load_accounts()
        new_name = self._pick_account(acc.order + 1, len(self._frames), acc.name, accounts)
        if new_name and new_name != acc.name:
            if not self._session.rename(idx, new_name):
                messagebox.showwarning("提示", "重命名失败：账户名冲突。")
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


def run_multiopen_wizard(bridge: Any) -> Optional[MultiAccountSession]:
    """打开多开引导，返回会话（取消返回 None）"""
    root = tk.Tk()
    wizard = MultiOpenWizard(root, bridge)
    root.mainloop()
    return wizard.result
