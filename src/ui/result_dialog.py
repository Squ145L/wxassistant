"""发送结果弹窗：勾选列表 + 选中失败/成功 + 打标签"""

import tkinter as tk
from tkinter import ttk, simpledialog, messagebox
from typing import Callable, Optional


class ResultDialog(tk.Toplevel):
    """群发完成后的结果弹窗

    展示全部发送结果（成功+失败），每行带复选框。
    底部三个按钮：选中失败 | 选中成功 | 打标签
    """

    def __init__(self, parent: tk.Widget):
        super().__init__(parent)
        self.title("发送结果")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        self._results: list = []          # list of (name, success, error)
        self._check_vars: list[tk.BooleanVar] = []
        self._select_all_var = tk.BooleanVar(value=True)
        self._on_set_tag: Optional[Callable[[str, str], bool]] = None

        self._build_ui()
        self._center_on_parent(parent)

    def set_tag_callback(self, callback: Callable[[str, str], bool]):
        """注入标签回调，参数为 (name, tag) -> bool"""
        self._on_set_tag = callback

    def _center_on_parent(self, parent: tk.Widget) -> None:
        self.update_idletasks()
        try:
            pw = parent.winfo_width()
            ph = parent.winfo_height()
            px = parent.winfo_rootx()
            py = parent.winfo_rooty()
            w = self.winfo_reqwidth()
            h = self.winfo_reqheight()
            if pw > 10 and ph > 10:
                x = px + (pw - w) // 2
                y = py + (ph - h) // 2
            else:
                sw = self.winfo_screenwidth()
                sh = self.winfo_screenheight()
                x = (sw - w) // 2
                y = (sh - h) // 2
            self.geometry(f"+{x}+{y}")
        except Exception:
            pass

    def _build_ui(self):
        frame = ttk.Frame(self, padding=16)
        frame.pack(fill=tk.BOTH, expand=True)

        # --- 统计区 ---
        summary_frame = ttk.Frame(frame)
        summary_frame.pack(fill=tk.X, pady=(0, 10))

        self._label_total = ttk.Label(summary_frame, text="总计: 0", font=("", 11))
        self._label_total.pack(side=tk.LEFT, padx=(0, 16))

        self._label_success = ttk.Label(summary_frame, text="✅ 成功: 0", font=("", 11))
        self._label_success.pack(side=tk.LEFT, padx=(0, 16))

        self._label_failed = ttk.Label(summary_frame, text="❌ 失败: 0", font=("", 11))
        self._label_failed.pack(side=tk.LEFT)

        ttk.Separator(frame, orient=tk.HORIZONTAL).pack(fill=tk.X)

        # --- 全选 ---
        top = ttk.Frame(frame)
        top.pack(fill=tk.X, pady=(8, 4))
        ttk.Checkbutton(
            top, text="全选", variable=self._select_all_var,
            command=self._toggle_all,
        ).pack(side=tk.LEFT)

        # --- 可滚动列表 ---
        list_frame = ttk.Frame(frame)
        list_frame.pack(fill=tk.BOTH, expand=True)

        canvas = tk.Canvas(list_frame, highlightthickness=0, borderwidth=0,
                           height=280)
        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=canvas.yview)
        self._inner = ttk.Frame(canvas)
        self._inner.bind("<Configure>",
                         lambda _e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=self._inner, anchor=tk.NW)
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        canvas.bind("<MouseWheel>", _on_mousewheel)
        self._inner.bind("<MouseWheel>", _on_mousewheel)

        # --- 底部按钮区 ---
        btn_frame = ttk.Frame(frame)
        btn_frame.pack(fill=tk.X, pady=(12, 0))

        ttk.Button(btn_frame, text="选中失败",
                   command=self._select_failed).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(btn_frame, text="选中成功",
                   command=self._select_success).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(btn_frame, text="🏷 打标签",
                   command=self._tag_selected).pack(side=tk.LEFT)

        ttk.Button(btn_frame, text="确定",
                   command=self.destroy).pack(side=tk.RIGHT)

    # ================================================================
    # 数据填充
    # ================================================================

    def show_result(self, total: int, success: int, failed: int,
                    all_results: list):
        """填充结果数据

        Args:
            total: 总数
            success: 成功数
            failed: 失败数
            all_results: list of SendResult (含 friend_name, success, error)
        """
        self._label_total.config(text=f"总计: {total}")
        self._label_success.config(text=f"✅ 成功: {success}")
        self._label_failed.config(text=f"❌ 失败: {failed}")

        # 清空旧数据
        for w in self._inner.winfo_children():
            w.destroy()
        self._check_vars.clear()
        self._results = all_results

        def _sync_select_all(*_):
            if self._check_vars:
                all_on = all(v.get() for v in self._check_vars)
                self._select_all_var.set(all_on)

        for r in all_results:
            name = getattr(r, "friend_name", str(r))
            ok = getattr(r, "success", False)
            error = getattr(r, "error", "") or ""
            icon = "✅" if ok else "❌"
            label = f"{icon} {name}"
            if error:
                label += f"  — {error}"

            var = tk.BooleanVar(value=not ok)  # 默认勾选失败的
            var.trace_add("write", _sync_select_all)
            self._check_vars.append(var)
            ttk.Checkbutton(self._inner, text=label, variable=var).pack(
                anchor=tk.W, pady=1)

        self._select_all_var.set(
            all(not r.success for r in all_results) if all_results else False)

        # 内容填充后重新居中
        self._center_on_parent(self.master)

    # ================================================================
    # 按钮行为
    # ================================================================

    def _toggle_all(self):
        v = self._select_all_var.get()
        for var in self._check_vars:
            var.set(v)

    def _select_failed(self):
        for i, r in enumerate(self._results):
            if i < len(self._check_vars):
                self._check_vars[i].set(not r.success)

    def _select_success(self):
        for i, r in enumerate(self._results):
            if i < len(self._check_vars):
                self._check_vars[i].set(r.success)

    def _tag_selected(self):
        """对弹窗内勾选的联系人打标签"""
        selected_names = [
            getattr(self._results[i], "friend_name", str(self._results[i]))
            for i, v in enumerate(self._check_vars) if v.get()
        ]
        if not selected_names:
            messagebox.showinfo("提示", "请先勾选要打标签的联系人")
            return

        new_tag = simpledialog.askstring(
            "设置标签",
            f"为 {len(selected_names)} 位联系人设置标签：",
            parent=self,
        )
        if new_tag is not None and self._on_set_tag:
            for name in selected_names:
                self._on_set_tag(name, new_tag.strip())
            messagebox.showinfo(
                "完成", f"已为 {len(selected_names)} 位联系人设置标签「{new_tag.strip()}」",
                parent=self)
