"""筛选栏：单行 — 搜索框 + 正则 + 标签筛选 + 匹配计数

窗口级操作（联系人/标签/刷新/设置/多开）已上移到顶栏 TopBar，
这里只保留筛选相关。
"""
import tkinter as tk
from tkinter import ttk
from typing import Callable, Optional


class FilterBar(ttk.Frame):
    """好友筛选栏（单行精简）"""

    def __init__(self, parent: tk.Widget):
        super().__init__(parent, padding=4)
        self._on_tag_filter: Optional[Callable[[str], None]] = None
        self._filter_var = tk.StringVar()
        self._filter_var.trace_add("write", self._on_var_changed)
        self._regex_mode = tk.BooleanVar(value=False)
        self._regex_mode.trace_add("write", self._on_var_changed)
        self._match_label_var = tk.StringVar(value="匹配 0/0 人")
        self._build_ui()

    def _build_ui(self) -> None:
        row = ttk.Frame(self)
        row.pack(fill=tk.X, pady=(2, 2))

        self._entry = ttk.Entry(
            row, textvariable=self._filter_var, font=("Consolas", 10), width=20)
        self._entry.pack(side=tk.LEFT, padx=(0, 2))

        ttk.Button(row, text="✕", width=3, command=self._clear_filter).pack(side=tk.LEFT, padx=(0, 2))

        self._cb_regex = ttk.Checkbutton(row, text=".*", variable=self._regex_mode)
        self._cb_regex.pack(side=tk.LEFT, padx=(0, 6))

        # 右侧：匹配计数 / 标签筛选 / 正则提示（先 pack 的靠右）
        self._label_match = ttk.Label(
            row, textvariable=self._match_label_var, foreground="gray", font=("", 9))
        self._label_match.pack(side=tk.RIGHT, padx=(0, 6))

        self._tag_var = tk.StringVar(value="全部")
        self._tag_combo = ttk.Combobox(
            row, textvariable=self._tag_var, values=["全部"], state="readonly", width=8)
        # 先 pack combo → 更靠右；后 pack label → 在其左边，显示为 标签:[全部]
        self._tag_combo.pack(side=tk.RIGHT, padx=(0, 4))
        self._lbl_tag = ttk.Label(row, text="标签:", font=("", 9))
        self._lbl_tag.pack(side=tk.RIGHT, padx=(0, 2))
        self._tag_combo.bind("<<ComboboxSelected>>", self._on_tag_selected)

        self._regex_hint = ttk.Label(row, text="", foreground="#2196F3", font=("", 8))
        self._regex_hint.pack(side=tk.RIGHT, padx=(0, 4))

        self._entry.bind("<Return>", lambda _e: None)

    # ================================================================
    # 公开接口
    # ================================================================

    def set_on_tag_filter(self, callback: Callable[[str], None]) -> None:
        self._on_tag_filter = callback

    def set_tag_options(self, tags: list[str]) -> None:
        cur = self._tag_var.get()
        self._tag_combo["values"] = ["全部"] + list(tags)
        if cur not in self._tag_combo["values"]:
            self._tag_var.set("全部")

    @property
    def tag_filter(self) -> str:
        v = self._tag_var.get().strip()
        return "" if v == "全部" else v

    @property
    def filter_text(self) -> str:
        return self._filter_var.get().strip()

    def set_filter_text(self, text: str) -> None:
        self._filter_var.set(text)

    @property
    def is_regex_mode(self) -> bool:
        return self._regex_mode.get()

    def set_match_count(self, matched: int, total: int) -> None:
        self._match_label_var.set(f"匹配 {matched}/{total} 人")

    def set_regex_error(self, message: str = "") -> None:
        if message:
            self._regex_hint.config(text=f"⚠ {message}", foreground="red")
        else:
            self._regex_hint.config(text="", foreground="#2196F3")

    def set_regex_hint(self, text: str = "") -> None:
        self._regex_hint.config(text=text, foreground="#2196F3")

    def set_enabled(self, enabled: bool) -> None:
        state = tk.NORMAL if enabled else tk.DISABLED
        self._entry.config(state=state)
        self._cb_regex.config(state=state)

    def clear_filter(self) -> None:
        """清空筛选文字 + 正则模式 + 标签筛选（账户切换时调用，防串账户）"""
        # 注意顺序：_tag_var 无 trace，须先重置为「全部」；
        # 否则下方 _filter_var.set("") 触发的刷新会读到旧标签，跨账户残留。
        self._tag_var.set("全部")
        self._regex_mode.set(False)
        self._filter_var.set("")
        self.set_regex_error("")
        self.set_regex_hint("")

    # ================================================================
    # 内部
    # ================================================================

    def _on_var_changed(self, *_args) -> None:
        if self._regex_mode.get() and self.filter_text:
            from src.services.friend_service import FriendService
            compiled = FriendService.try_compile_regex(self.filter_text)
            if compiled is None:
                self.set_regex_error("正则语法错误")
            elif compiled.groups > 0:
                self.set_regex_hint(f"{compiled.groups} 个捕获组 → [$1]…[${compiled.groups}] 可用")
            else:
                self.set_regex_hint("正则匹配模式")
        else:
            self.set_regex_error("")
            self.set_regex_hint("")
        self.event_generate("<<FilterChanged>>")

    def _clear_filter(self) -> None:
        self._filter_var.set("")
        self.set_regex_error("")
        self.set_regex_hint("")
        self._entry.focus_set()

    def _on_tag_selected(self, _event=None) -> None:
        if self._on_tag_filter:
            self._on_tag_filter(self.tag_filter)
