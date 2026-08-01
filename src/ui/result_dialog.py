"""发送结果弹窗：列出失败名单"""

import tkinter as tk
from tkinter import ttk


class ResultDialog(tk.Toplevel):
    """群发完成后的结果弹窗

    显示成功/失败统计，列出失败名单和原因。
    """

    def __init__(self, parent: tk.Widget):
        super().__init__(parent)
        self.title("发送结果")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        # 居中于父窗口
        self.geometry("420x360")
        self.update_idletasks()
        pw, ph = parent.winfo_width(), parent.winfo_height()
        px, py = parent.winfo_rootx(), parent.winfo_rooty()
        w, h = 420, 360
        x = px + (pw - w) // 2
        y = py + (ph - h) // 2
        self.geometry(f"+{x}+{y}")

        self._build_ui()

    def _build_ui(self):
        # --- 统计区 ---
        summary_frame = ttk.Frame(self, padding=12)
        summary_frame.pack(fill=tk.X)

        self._label_total = ttk.Label(summary_frame, text="总计: 0", font=("", 11))
        self._label_total.pack(side=tk.LEFT, padx=(0, 16))

        self._label_success = ttk.Label(summary_frame, text="✅ 成功: 0", font=("", 11))
        self._label_success.pack(side=tk.LEFT, padx=(0, 16))

        self._label_failed = ttk.Label(summary_frame, text="❌ 失败: 0", font=("", 11))
        self._label_failed.pack(side=tk.LEFT)

        ttk.Separator(self, orient=tk.HORIZONTAL).pack(fill=tk.X, padx=12)

        # --- 失败列表 ---
        list_frame = ttk.Frame(self, padding=12)
        list_frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(list_frame, text="失败名单：", font=("", 10, "bold")).pack(anchor=tk.W)

        self._tree = ttk.Treeview(
            list_frame,
            columns=("name", "reason"),
            show="headings",
            height=10,
        )
        self._tree.heading("name", text="联系人")
        self._tree.heading("reason", text="失败原因")
        self._tree.column("name", width=130, anchor=tk.W)
        self._tree.column("reason", width=230, anchor=tk.W)

        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self._tree.yview)
        self._tree.configure(yscrollcommand=scrollbar.set)

        self._tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # --- 关闭按钮 ---
        btn_frame = ttk.Frame(self, padding=12)
        btn_frame.pack(fill=tk.X)
        ttk.Button(btn_frame, text="确定", command=self.destroy).pack(side=tk.RIGHT)

    # ================================================================
    # 数据填充
    # ================================================================

    def show_result(self, total: int, success: int, failed: int, failed_list: list):
        """填充结果数据

        Args:
            total: 总数
            success: 成功数
            failed: 失败数
            failed_list: list of SendResult (含 friend_name, error)
        """
        self._label_total.config(text=f"总计: {total}")
        self._label_success.config(text=f"✅ 成功: {success}")
        self._label_failed.config(text=f"❌ 失败: {failed}")

        # 清空旧数据
        for row in self._tree.get_children():
            self._tree.delete(row)

        if failed_list:
            for r in failed_list:
                name = getattr(r, "friend_name", str(r))
                error = getattr(r, "error", "未知错误") or "未知错误"
                self._tree.insert("", tk.END, values=(name, error))
        else:
            self._tree.insert("", tk.END, values=("无失败", "全部发送成功 🎉"))
