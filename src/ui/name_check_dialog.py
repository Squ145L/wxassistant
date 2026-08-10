"""联系人名字补全弹窗 — 勾选后批量重命名"""

import tkinter as tk
from tkinter import ttk
from typing import Callable, Optional


class NameCheckDialog(tk.Toplevel):

    def __init__(self, parent: tk.Widget, diffs: dict[str, str]):
        super().__init__(parent)
        self.title("联系人名字补全")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        self._diffs = diffs
        self._check_vars: dict[str, tk.BooleanVar] = {}
        self._select_all_var = tk.BooleanVar(value=True)
        self._on_confirm: Optional[Callable[[dict[str, str]], None]] = None

        self._build_ui()
        self._center(parent)

    def set_on_confirm(self, callback: Callable[[dict[str, str]], None]) -> None:
        self._on_confirm = callback

    def _build_ui(self) -> None:
        frame = ttk.Frame(self, padding=16)
        frame.pack(fill=tk.BOTH, expand=True)

        # [✓]全选
        top = ttk.Frame(frame)
        top.pack(fill=tk.X, pady=(0, 8))
        ttk.Checkbutton(top, text="全选", variable=self._select_all_var,
                        command=self._toggle_all).pack(side=tk.LEFT)
        ttk.Label(top, text=f"共 {len(self._diffs)} 项", foreground="gray",
                  font=("", 9)).pack(side=tk.RIGHT)

        # 列表
        list_frame = ttk.Frame(frame)
        list_frame.pack(fill=tk.BOTH, expand=True)

        canvas = tk.Canvas(list_frame, highlightthickness=0, borderwidth=0,
                           height=min(300, max(120, len(self._diffs) * 32)))
        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=canvas.yview)
        inner = ttk.Frame(canvas)
        inner.bind("<Configure>", lambda _e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=inner, anchor=tk.NW)
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        canvas.bind("<MouseWheel>", _on_mousewheel)
        inner.bind("<MouseWheel>", _on_mousewheel)

        def _sync_select_all(*_):
            all_on = all(v.get() for v in self._check_vars.values())
            self._select_all_var.set(all_on)

        for old_name, new_name in self._diffs.items():
            row = ttk.Frame(inner)
            row.pack(fill=tk.X, pady=1)
            var = tk.BooleanVar(value=True)
            var.trace_add("write", _sync_select_all)
            self._check_vars[old_name] = var
            ttk.Checkbutton(row, text="", variable=var, width=2).pack(side=tk.LEFT)
            ttk.Label(row, text=old_name, foreground="gray").pack(side=tk.LEFT)
            ttk.Label(row, text="  →  ").pack(side=tk.LEFT)
            ttk.Label(row, text=new_name, foreground="#2196F3",
                      font=("", 10, "bold")).pack(side=tk.LEFT)

        # 确认(左) 取消(右)
        btn_frame = ttk.Frame(frame)
        btn_frame.pack(fill=tk.X, pady=(12, 0))
        ttk.Button(btn_frame, text="确认", command=self._on_confirm_clicked).pack(side=tk.RIGHT, padx=(4, 0))
        ttk.Button(btn_frame, text="取消", command=self.destroy).pack(side=tk.RIGHT)

    def _toggle_all(self) -> None:
        v = self._select_all_var.get()
        for var in self._check_vars.values():
            var.set(v)

    def _on_confirm_clicked(self) -> None:
        selected = {old: self._diffs[old] for old, var in self._check_vars.items() if var.get()}
        if self._on_confirm:
            self._on_confirm(selected)
        self.destroy()

    def _center(self, parent: tk.Widget) -> None:
        self.update_idletasks()
        pw = parent.winfo_width(); ph = parent.winfo_height()
        px = parent.winfo_rootx(); py = parent.winfo_rooty()
        h = max(240, min(450, 160 + len(self._diffs) * 32))
        self.geometry(f"420x{h}+{px + (pw - 420) // 2}+{py + (ph - h) // 2}")
