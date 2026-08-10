"""可复用确认弹窗 — 勾选列表 + 确认/取消"""

import tkinter as tk
from tkinter import ttk
from typing import Callable, Optional


class ConfirmDialog(tk.Toplevel):
    """带复选框列表的确认弹窗

    布局:
        [✓] 全选
        ┌──────────────────┐
        │ [✓] 行1          │
        │ [✓] 行2          │  ← 可滚动
        └──────────────────┘
           [确认]   [取消]
    """

    def __init__(self, parent: tk.Widget, title: str, items: list[str],
                 checked: bool = True):
        """
        Args:
            parent: 父窗口
            title: 弹窗标题
            items: 行标签列表
            checked: 默认是否勾选
        """
        super().__init__(parent)
        self.title(title)
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        self._items = items
        self._check_vars: list[tk.BooleanVar] = []
        self._select_all_var = tk.BooleanVar(value=checked)
        self._on_confirm: Optional[Callable[[list[int]], None]] = None

        self._build_ui()
        self._center(parent)

    def set_on_confirm(self, callback: Callable[[list[int]], None]) -> None:
        """回调参数: 被勾选的索引列表"""
        self._on_confirm = callback

    def get_checked_indices(self) -> list[int]:
        return [i for i, v in enumerate(self._check_vars) if v.get()]

    def _build_ui(self) -> None:
        frame = ttk.Frame(self, padding=16)
        frame.pack(fill=tk.BOTH, expand=True)

        # [✓]全选
        top = ttk.Frame(frame)
        top.pack(fill=tk.X, pady=(0, 8))
        ttk.Checkbutton(top, text="全选", variable=self._select_all_var,
                        command=self._toggle_all).pack(side=tk.LEFT)

        # 可滚动列表
        list_frame = ttk.Frame(frame)
        list_frame.pack(fill=tk.BOTH, expand=True)

        canvas = tk.Canvas(list_frame, highlightthickness=0, borderwidth=0,
                           height=min(300, max(120, len(self._items) * 28)))
        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=canvas.yview)
        inner = ttk.Frame(canvas)
        inner.bind("<Configure>", lambda _e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=inner, anchor=tk.NW)
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        def _bind_mousewheel(widget):
            widget.bind("<MouseWheel>", _on_mousewheel)
            for child in widget.winfo_children():
                _bind_mousewheel(child)

        canvas.bind("<MouseWheel>", _on_mousewheel)
        inner.bind("<MouseWheel>", _on_mousewheel)

        def _sync_select_all(*_):
            all_on = all(v.get() for v in self._check_vars)
            self._select_all_var.set(all_on)

        for item in self._items:
            var = tk.BooleanVar(value=self._select_all_var.get())
            var.trace_add("write", _sync_select_all)
            self._check_vars.append(var)
            ttk.Checkbutton(inner, text=item, variable=var).pack(anchor=tk.W, pady=1)

        # 子控件创建完毕，递归绑定滚轮
        _bind_mousewheel(inner)

        # 底部按钮：确认 取消（右对齐，取消在右）
        btn_frame = ttk.Frame(frame)
        btn_frame.pack(fill=tk.X, pady=(12, 0))
        ttk.Button(btn_frame, text="取消", command=self.destroy).pack(side=tk.RIGHT)
        ttk.Button(btn_frame, text="确认", command=self._on_confirm_clicked).pack(side=tk.RIGHT, padx=(0, 10))

    def _toggle_all(self) -> None:
        v = self._select_all_var.get()
        for var in self._check_vars:
            var.set(v)

    def _on_confirm_clicked(self) -> None:
        if self._on_confirm:
            self._on_confirm(self.get_checked_indices())
        self.destroy()

    def _center(self, parent: tk.Widget) -> None:
        self.update_idletasks()
        try:
            pw = parent.winfo_width()
            ph = parent.winfo_height()
            px = parent.winfo_rootx()
            py = parent.winfo_rooty()
            h = min(460, 200 + len(self._items) * 28)
            if pw > 10 and ph > 10:
                x = px + (pw - 420) // 2
                y = py + (ph - h) // 2
            else:
                sw = self.winfo_screenwidth()
                sh = self.winfo_screenheight()
                x = (sw - 420) // 2
                y = (sh - h) // 2
            self.geometry(f"420x{h}+{x}+{y}")
        except Exception:
            pass
