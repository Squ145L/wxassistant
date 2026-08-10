"""消息编辑面板：模板输入（[name] 格式）、附件管理"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from typing import Callable, Optional

from src.utils.config import DEFAULT_SEND_INTERVAL, MAX_ATTACHMENT_COUNT


class MessageEditor(ttk.Frame):
    """右侧面板：消息模板编辑 + 附件管理"""

    def __init__(self, parent: tk.Widget):
        super().__init__(parent, padding=8)
        self._attachments: list[str] = []
        self._on_text_changed: Optional[Callable[[], None]] = None
        self._build_ui()

    def _build_ui(self):
        # === 消息模板标题 ===
        header = ttk.Frame(self)
        header.pack(fill=tk.X, pady=(0, 4))

        ttk.Label(header, text="📝 消息模板", font=("", 11, "bold")).pack(side=tk.LEFT)
        # 提示文字 expand: 宽度不足时它先被压缩(文字截断)
        ttk.Label(
            header, text="[name]=好友名 [name2]=后两字",
            foreground="gray", font=("", 9), anchor=tk.W,
        ).pack(side=tk.LEFT, padx=(10, 0), fill=tk.X, expand=True)

        # === 模板输入框（固定高度，不挤占底部空间）===
        template_frame = ttk.Frame(self)
        template_frame.pack(fill=tk.X)  # 只横向填充

        self._text = tk.Text(
            template_frame,
            font=("Microsoft YaHei", 10),
            wrap=tk.WORD,
            relief=tk.SUNKEN,
            borderwidth=1,
            padx=6,
            pady=6,
            height=5,  # 固定 5 行高度
        )
        text_scroll = ttk.Scrollbar(template_frame, orient=tk.VERTICAL, command=self._text.yview)
        self._text.configure(yscrollcommand=text_scroll.set)

        self._text.pack(side=tk.LEFT, fill=tk.X, expand=True)
        text_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        # 默认示例文本
        self._text.insert("1.0", "[name]同学你好，\n\n这是本学期的课程安排。\n\n[name]=25级李华 [name2]=李华")

        # 绑定事件更新变量提示
        self._text.bind("<KeyRelease>", self._on_text_change)

        # 变量提示标签
        self._var_hint_var = tk.StringVar()
        self._var_hint = ttk.Label(
            self,
            textvariable=self._var_hint_var,
            foreground="gray",
            font=("", 8),
        )
        self._var_hint.pack(anchor=tk.W, pady=(2, 6))

        # === 附件区 ===
        attach_frame = ttk.LabelFrame(self, text="📎 附件", padding=6)
        attach_frame.pack(fill=tk.X, pady=(0, 8))

        btn_row = ttk.Frame(attach_frame)
        btn_row.pack(fill=tk.X)

        self._btn_add = ttk.Button(
            btn_row, text="➕ 添加文件",
            command=self._add_attachment,
        )
        self._btn_add.pack(side=tk.LEFT)

        self._btn_remove = ttk.Button(
            btn_row, text="➖ 移除选中",
            command=self._remove_attachment,
        )
        self._btn_remove.pack(side=tk.LEFT, padx=(4, 0))

        # 附件列表
        self._attach_listbox = tk.Listbox(
            attach_frame,
            height=4,
            font=("", 9),
            relief=tk.FLAT,
        )
        self._attach_listbox.pack(fill=tk.X, pady=(4, 0))

        # === 选中计数 ===
        self._selected_var = tk.StringVar(value="已选 0 人")
        ttk.Label(
            self, textvariable=self._selected_var,
            foreground="gray", font=("", 9),
        ).pack(anchor=tk.E, pady=(4, 0))

    # ================================================================
    # 公开接口
    # ================================================================

    def get_message(self) -> str:
        return self._text.get("1.0", tk.END).strip()

    def set_message(self, text: str):
        self._text.delete("1.0", tk.END)
        self._text.insert("1.0", text)
        self._update_var_hint()

    def get_attachments(self) -> list[str]:
        return list(self._attachments)

    def get_interval(self) -> float:
        return DEFAULT_SEND_INTERVAL

    def set_selected_count(self, count: int):
        self._selected_var.set(f"已选 {count} 人")

    def set_on_text_changed(self, callback: Callable[[], None]):
        self._on_text_changed = callback

    def set_enabled(self, enabled: bool):
        state = tk.NORMAL if enabled else tk.DISABLED
        self._text.config(state=state)
        self._btn_add.config(state=state)
        self._btn_remove.config(state=state)

    # ================================================================
    # 内部
    # ================================================================

    def _add_attachment(self):
        if len(self._attachments) >= MAX_ATTACHMENT_COUNT:
            messagebox.showwarning("附件限制", f"最多添加 {MAX_ATTACHMENT_COUNT} 个附件")
            return

        paths = filedialog.askopenfilenames(
            title="选择附件",
            filetypes=[
                ("所有文件", "*.*"),
                ("图片", "*.jpg;*.jpeg;*.png;*.gif;*.bmp"),
                ("视频", "*.mp4;*.avi;*.mov;*.wmv"),
                ("文档", "*.pdf;*.doc;*.docx;*.xls;*.xlsx"),
            ],
        )
        for p in paths:
            if p not in self._attachments:
                self._attachments.append(p)
                display = p.split("/")[-1].split("\\")[-1]
                self._attach_listbox.insert(tk.END, display)

    def _remove_attachment(self):
        sel = self._attach_listbox.curselection()
        if not sel:
            return
        idx = sel[0]
        self._attach_listbox.delete(idx)
        del self._attachments[idx]

    def _on_text_change(self, *_args):
        self._update_var_hint()
        if self._on_text_changed:
            self._on_text_changed()

    def _update_var_hint(self):
        from src.services.template_engine import TemplateEngine
        msg = self.get_message()
        if msg:
            vars_found = TemplateEngine.validate(msg)
            if vars_found:
                self._var_hint_var.set(f"检测到变量: {', '.join(vars_found)}")
            else:
                self._var_hint_var.set("未检测到变量（可直接输入文字）")
        else:
            self._var_hint_var.set("")

