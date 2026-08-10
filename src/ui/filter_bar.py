"""筛选栏：搜索框 + 正则/前缀切换 + 匹配计数 + OCR 按钮"""

import tkinter as tk
from tkinter import ttk
from typing import Callable, Optional


class FilterBar(ttk.Frame):
    """好友筛选栏

    按钮：
    - OCR: 弹出菜单（OCR校准 / 检查联系人名字）
    - .*: 正则开关
    - ✕: 清除筛选
    """

    def __init__(self, parent: tk.Widget):
        super().__init__(parent, padding=4)
        self._on_calibrate: Optional[Callable[[str], None]] = None  # (key)
        self._on_check_names: Optional[Callable[[], None]] = None
        self._on_search_contacts: Optional[Callable[[], None]] = None
        self._on_import_all: Optional[Callable[[], None]] = None
        self._on_import_settings: Optional[Callable[[], None]] = None
        self._on_help: Optional[Callable[[], None]] = None
        self._on_refresh: Optional[Callable[[], None]] = None
        self._on_multiopen: Optional[Callable[[], None]] = None
        self._on_tag_filter: Optional[Callable[[str], None]] = None
        self._on_batch_tag: Optional[Callable[[], None]] = None
        self._on_clear_tags: Optional[Callable[[], None]] = None
        self._filter_var = tk.StringVar()
        self._filter_var.trace_add("write", self._on_var_changed)
        self._regex_mode = tk.BooleanVar(value=False)
        self._regex_mode.trace_add("write", self._on_var_changed)
        self._match_label_var = tk.StringVar(value="匹配 0/0 人")
        self._build_ui()

    def _build_ui(self) -> None:
        row1 = ttk.Frame(self)
        row1.pack(fill=tk.X, pady=(2, 2))

        ttk.Label(row1, text="🔍 筛选:", font=("", 10)).pack(side=tk.LEFT)

        self._entry = ttk.Entry(
            row1,
            textvariable=self._filter_var,
            font=("Consolas", 10),
            width=22,
        )
        self._entry.pack(side=tk.LEFT, padx=(6, 2), fill=tk.X, expand=True)

        self._btn_clear = ttk.Button(
            row1, text="✕", width=3, command=self._clear_filter,
        )
        self._btn_clear.pack(side=tk.LEFT, padx=(0, 4))

        self._cb_regex = ttk.Checkbutton(
            row1, text=".*", variable=self._regex_mode,
        )
        self._cb_regex.pack(side=tk.LEFT, padx=(0, 8))

        # OCR 按钮 + 弹出菜单
        self._btn_ocr = ttk.Button(row1, text="OCR", width=5, command=self._pop_ocr_menu)
        self._btn_ocr.pack(side=tk.RIGHT, padx=(0, 4))

        self._ocr_menu = tk.Menu(self, tearoff=0)
        self._ocr_menu.add_command(label="[OCR校准] 聊天界面标题", command=lambda: self._on_calibrate_clicked("chat_title"))
        self._ocr_menu.add_command(label="检查选中名称是否完整", command=self._on_check_names_clicked)
        self._ocr_menu.add_separator()
        self._ocr_menu.add_command(label="搜索并导入..", command=self._on_search_contacts_clicked)
        self._ocr_menu.add_command(label="扫描通讯录并导入", command=self._on_import_all_clicked)
        self._ocr_menu.add_command(label="[OCR校准] 扫描通讯录并导入", command=lambda: self._on_calibrate_clicked("contacts_list"))
        self._ocr_menu.add_command(label="[设置] 扫描通讯录并导入", command=self._on_import_settings_clicked)
        self._ocr_menu.add_separator()
        self._ocr_menu.add_command(label="帮助...", command=self._on_help_clicked)

        # 第二行
        row2 = ttk.Frame(self)
        row2.pack(fill=tk.X)

        self._label_match = ttk.Label(
            row2, textvariable=self._match_label_var,
            foreground="gray", font=("", 9),
        )
        self._label_match.pack(side=tk.LEFT, padx=(2, 0))

        self._btn_batch_tag = ttk.Button(
            row2, text="添加标签", width=8, command=self._on_batch_tag_clicked,
        )
        self._btn_batch_tag.pack(side=tk.LEFT, padx=(8, 2))

        self._btn_clear_tags = ttk.Button(
            row2, text="清除标签", width=8, command=self._on_clear_tags_clicked,
        )
        self._btn_clear_tags.pack(side=tk.LEFT, padx=(0, 6))

        self._btn_refresh = ttk.Button(
            row2, text="🔄 刷新", width=7, command=self._on_refresh_clicked,
        )
        self._btn_refresh.pack(side=tk.LEFT)

        self._btn_multiopen = ttk.Button(
            row2, text="多开", width=6, command=self._on_multiopen_clicked,
        )
        self._btn_multiopen.pack(side=tk.LEFT, padx=(6, 0))

        # 右侧：标签筛选
        self._regex_hint = ttk.Label(row2, text="", foreground="#2196F3", font=("", 8))
        self._regex_hint.pack(side=tk.RIGHT)

        self._tag_var = tk.StringVar(value="全部")
        self._tag_combo = ttk.Combobox(
            row2, textvariable=self._tag_var, values=["全部"],
            state="readonly", width=10,
        )
        self._tag_combo.pack(side=tk.RIGHT, padx=(0, 2))
        self._tag_combo.bind("<<ComboboxSelected>>", self._on_tag_selected)

        ttk.Label(row2, text="标签:", font=("", 9)).pack(side=tk.RIGHT, padx=(0, 2))

        self._entry.bind("<Return>", lambda _e: None)

    # ================================================================
    # 公开接口
    # ================================================================

    def set_on_calibrate(self, callback: Callable[[str], None]) -> None:
        self._on_calibrate = callback

    def set_on_check_names(self, callback: Callable[[], None]) -> None:
        self._on_check_names = callback

    def set_on_search_contacts(self, callback: Callable[[], None]) -> None:
        self._on_search_contacts = callback

    def set_on_import_all(self, callback: Callable[[], None]) -> None:
        self._on_import_all = callback

    def set_on_import_settings(self, callback: Callable[[], None]) -> None:
        self._on_import_settings = callback

    def set_on_help(self, callback: Callable[[], None]) -> None:
        self._on_help = callback

    def set_on_refresh(self, callback: Callable[[], None]) -> None:
        self._on_refresh = callback

    def set_on_tag_filter(self, callback: Callable[[str], None]) -> None:
        self._on_tag_filter = callback

    def set_on_batch_tag(self, callback: Callable[[], None]) -> None:
        self._on_batch_tag = callback

    def set_on_clear_tags(self, callback: Callable[[], None]) -> None:
        self._on_clear_tags = callback

    def set_on_multiopen(self, callback: Callable[[], None]) -> None:
        self._on_multiopen = callback

    def set_multiopen_label(self, is_multi: bool) -> None:
        """多开模式下按钮显示 [单用户模式]，单账户显示 [多开]"""
        self._btn_multiopen.config(text="单用户模式" if is_multi else "多开")

    def _on_multiopen_clicked(self) -> None:
        if self._on_multiopen:
            self._on_multiopen()

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
        self._btn_clear.config(state=state)
        self._btn_ocr.config(state=state)
        self._cb_regex.config(state=state)

    # ================================================================
    # 内部
    # ================================================================

    def _pop_ocr_menu(self) -> None:
        """在按钮下方弹出 OCR 菜单"""
        x = self._btn_ocr.winfo_rootx()
        y = self._btn_ocr.winfo_rooty() + self._btn_ocr.winfo_height()
        self._ocr_menu.tk_popup(x, y)

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

    def _on_calibrate_clicked(self, key: str) -> None:
        if self._on_calibrate:
            self._on_calibrate(key)

    def _on_check_names_clicked(self) -> None:
        if self._on_check_names:
            self._on_check_names()

    def _on_search_contacts_clicked(self) -> None:
        if self._on_search_contacts:
            self._on_search_contacts()

    def _on_import_all_clicked(self) -> None:
        if self._on_import_all:
            self._on_import_all()

    def _on_import_settings_clicked(self) -> None:
        if self._on_import_settings:
            self._on_import_settings()

    def _on_help_clicked(self) -> None:
        if self._on_help:
            self._on_help()

    def _on_refresh_clicked(self) -> None:
        if self._on_refresh:
            self._on_refresh()

    def _on_tag_selected(self, _event=None) -> None:
        if self._on_tag_filter:
            self._on_tag_filter(self.tag_filter)

    def _on_batch_tag_clicked(self) -> None:
        if self._on_batch_tag:
            self._on_batch_tag()

    def _on_clear_tags_clicked(self) -> None:
        if self._on_clear_tags:
            self._on_clear_tags()
