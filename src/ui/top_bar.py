"""顶栏 — 窗口级操作集中区

账户切换 + [联系人▾][标签▾] 菜单 + 刷新/设置/帮助/多开。
筛选（搜索/标签）留在内容区 FilterBar，这里不放筛选控件。

注意：所有 command 用 _make_cmd / _make_cmd_arg，在点击时**运行时读取回调属性**，
避免创建时（回调尚未注入）捕获到 None。
"""
import tkinter as tk
from tkinter import ttk
from typing import Callable, Optional


class TopBar(ttk.Frame):
    """主窗口顶栏"""

    def __init__(self, parent: tk.Widget):
        super().__init__(parent, padding=(4, 4))
        self._on_account_change: Optional[Callable[[str], None]] = None
        self._on_check_names: Optional[Callable[[], None]] = None
        self._on_export: Optional[Callable[[str], None]] = None   # fmt: txt/csv/json
        self._on_import_all: Optional[Callable[[], None]] = None
        self._on_search_import: Optional[Callable[[], None]] = None
        self._on_batch_tag: Optional[Callable[[], None]] = None
        self._on_clear_tags: Optional[Callable[[], None]] = None
        self._on_refresh: Optional[Callable[[], None]] = None
        self._on_settings: Optional[Callable[[], None]] = None
        self._on_help: Optional[Callable[[], None]] = None
        self._on_multiopen: Optional[Callable[[], None]] = None
        self._multi = False  # 多账户模式：账户下拉可切换
        self._build_ui()

    # ================================================================
    # command 辅助：运行时读取回调，防止创建时捕获 None
    # ================================================================

    def _make_cmd(self, attr):
        def cmd():
            cb = getattr(self, attr, None)
            if cb:
                cb()
        return cmd

    def _make_cmd_arg(self, attr, arg):
        def cmd():
            cb = getattr(self, attr, None)
            if cb:
                cb(arg)
        return cmd

    # ================================================================
    # UI
    # ================================================================

    def _build_ui(self) -> None:
        # ---- 账户（多账户模式显示）----
        self._account_label = ttk.Label(self, text="账户:")
        self._account_combo = ttk.Combobox(self, state="readonly", width=10)

        # ---- 联系人菜单 ----
        self._btn_contacts = ttk.Menubutton(self, text="联系人")
        contacts_menu = tk.Menu(self._btn_contacts, tearoff=0)
        contacts_menu.add_command(label="检查选中名称", command=self._make_cmd("_on_check_names"))
        export_menu = tk.Menu(contacts_menu, tearoff=0)
        for fmt in ("txt", "csv", "json"):
            export_menu.add_command(
                label=fmt.upper(), command=self._make_cmd_arg("_on_export", fmt))
        contacts_menu.add_cascade(label="导出选中联系人...", menu=export_menu)
        contacts_menu.add_command(label="扫描并导入", command=self._make_cmd("_on_import_all"))
        contacts_menu.add_command(label="搜索并导入", command=self._make_cmd("_on_search_import"))
        self._btn_contacts["menu"] = contacts_menu

        # ---- 标签菜单 ----
        self._btn_tags = ttk.Menubutton(self, text="标签")
        tags_menu = tk.Menu(self._btn_tags, tearoff=0)
        tags_menu.add_command(label="添加标签", command=self._make_cmd("_on_batch_tag"))
        tags_menu.add_command(label="清除标签", command=self._make_cmd("_on_clear_tags"))
        self._btn_tags["menu"] = tags_menu

        # ---- 右侧按钮 ----
        self._btn_refresh = ttk.Button(self, text="刷新", width=4, command=self._make_cmd("_on_refresh"))
        self._btn_settings = ttk.Button(self, text="设置", width=4, command=self._make_cmd("_on_settings"))
        self._btn_help = ttk.Button(self, text="帮助", width=4, command=self._make_cmd("_on_help"))
        self._btn_multiopen = ttk.Button(self, text="多开", width=7, command=self._make_cmd("_on_multiopen"))

        # pack 顺序：右侧按钮从右往左
        self._btn_multiopen.pack(side=tk.RIGHT, padx=(4, 2))
        self._btn_settings.pack(side=tk.RIGHT, padx=4)
        self._btn_help.pack(side=tk.RIGHT, padx=4)
        self._btn_refresh.pack(side=tk.RIGHT, padx=4)
        # 左侧：联系人 / 标签菜单
        self._btn_tags.pack(side=tk.LEFT, padx=(8, 0))
        self._btn_contacts.pack(side=tk.LEFT, padx=(8, 0))
        # 账户（默认隐藏，单账户模式不显示）
        self._account_combo.pack(side=tk.LEFT, padx=(0, 2))
        self._account_label.pack(side=tk.LEFT)
        self.set_account_options(None)

    # ================================================================
    # 公开接口
    # ================================================================

    def set_account_options(self, names, account_var=None, on_change=None) -> None:
        """多账户：显示账户下拉；单账户：隐藏

        names: 账户名列表（空/None = 单账户，隐藏）
        account_var: tk.StringVar（由外部持有，MainWindow 读取当前账户）
        on_change: 切换账户回调 (name) -> None
        """
        self._multi = bool(names)
        if names:
            self._account_label.pack(side=tk.LEFT)
            self._account_combo.pack(side=tk.LEFT, padx=(0, 2))
            self._account_combo["values"] = list(names)
            if account_var is not None:
                self._account_combo.configure(textvariable=account_var)
                if not account_var.get():
                    account_var.set(names[0])
            if on_change:
                self._on_account_change = on_change
                self._account_combo.bind("<<ComboboxSelected>>", self._on_combo_selected)
        else:
            # 单账户：显示"全局"（禁用），账户维度始终可见
            self._account_label.pack(side=tk.LEFT)
            self._account_combo.pack(side=tk.LEFT, padx=(0, 2))
            self._account_combo["values"] = ["全局"]
            self._account_combo.set("全局")
            self._account_combo.config(state="disabled")

    def _on_combo_selected(self, _event=None) -> None:
        if self._on_account_change:
            self._on_account_change(self._account_combo.get())

    def set_multiopen_label(self, is_multi: bool) -> None:
        """多开模式下按钮显示 [单用户模式]，单账户显示 [多开]"""
        self._btn_multiopen.config(text="单用户模式" if is_multi else "多开")

    def set_enabled(self, enabled: bool) -> None:
        """发送中禁用顶栏按钮（防止中途切换账户/操作）"""
        state = tk.NORMAL if enabled else tk.DISABLED
        self._btn_refresh.config(state=state)
        self._btn_settings.config(state=state)
        self._btn_help.config(state=state)
        self._btn_multiopen.config(state=state)
        self._btn_contacts.config(state=state)
        self._btn_tags.config(state=state)
        if self._multi:
            self._account_combo.config(state="readonly" if enabled else tk.DISABLED)

    # ---- 回调注入 ----
    def set_on_account_change(self, cb): self._on_account_change = cb
    def set_on_check_names(self, cb): self._on_check_names = cb
    def set_on_export(self, cb): self._on_export = cb
    def set_on_import_all(self, cb): self._on_import_all = cb
    def set_on_search_import(self, cb): self._on_search_import = cb
    def set_on_batch_tag(self, cb): self._on_batch_tag = cb
    def set_on_clear_tags(self, cb): self._on_clear_tags = cb
    def set_on_refresh(self, cb): self._on_refresh = cb
    def set_on_settings(self, cb): self._on_settings = cb
    def set_on_help(self, cb): self._on_help = cb
    def set_on_multiopen(self, cb): self._on_multiopen = cb
