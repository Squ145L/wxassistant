"""顶栏 — 窗口级操作集中区

账户切换 + [联系人▾][标签▾] 菜单 + 刷新/设置/帮助/多开。
筛选（搜索/标签）留在内容区 FilterBar，这里不放筛选控件。

注意：所有 command 用 _make_cmd / _make_cmd_arg，在点击时**运行时读取回调属性**，
避免创建时（回调尚未注入）捕获到 None。
"""
import tkinter as tk
from tkinter import ttk
from typing import Callable, Optional

from src.ui import ui_kit


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
        self._on_account_manager: Optional[Callable[[], None]] = None
        self._multi = False  # 有账户列表时：账户下拉可切换
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

        # toggle：点开/再点或点别处收起（tk_popup 阻塞式，天然满足）
        self._btn_contacts.bind(
            "<Button-1>", lambda e: self._toggle_menu(self._btn_contacts, contacts_menu))
        self._btn_tags.bind(
            "<Button-1>", lambda e: self._toggle_menu(self._btn_tags, tags_menu))

        # ---- 右侧按钮 ----
        self._btn_refresh = ttk.Button(self, text="刷新", width=4, command=self._make_cmd("_on_refresh"))
        self._btn_settings = ttk.Button(self, text="设置", width=4, command=self._make_cmd("_on_settings"))
        self._btn_help = ttk.Button(self, text="帮助", width=4, command=self._make_cmd("_on_help"))
        self._btn_multiopen = ttk.Button(self, text="多开", width=7, command=self._make_cmd("_on_multiopen"))
        self._btn_account_mgr = ttk.Button(self, text="账户管理", width=6,
                                           command=self._make_cmd("_on_account_manager"))

        # 布局：左侧分组菜单 → 账户 → 多开/账户管理 → 弹性区 → 右侧 帮助/设置/刷新
        # （弹性区吸收多余空间，固定控件永不互相挤压折叠 —— 布局铁律 1）
        self._btn_contacts.pack(side=tk.LEFT)
        self._btn_tags.pack(side=tk.LEFT, padx=(ui_kit.PAD_S, 0))
        self._account_label.pack(side=tk.LEFT, padx=(ui_kit.PAD_M, 0))
        self._account_combo.pack(side=tk.LEFT, padx=(0, ui_kit.PAD_S))
        self._btn_multiopen.pack(side=tk.LEFT, padx=(ui_kit.PAD_S, 0))
        self._btn_account_mgr.pack(side=tk.LEFT, padx=(ui_kit.PAD_S, 0))
        ui_kit.Spacer(self).pack(side=tk.LEFT, fill=tk.X, expand=True)
        self._btn_help.pack(side=tk.RIGHT)
        self._btn_settings.pack(side=tk.RIGHT, padx=(ui_kit.PAD_S, 0))
        self._btn_refresh.pack(side=tk.RIGHT, padx=(ui_kit.PAD_S, 0))
        self.set_account_options(None)

    # ================================================================
    # 公开接口
    # ================================================================

    def set_account_options(self, names, account_var=None, on_change=None) -> None:
        """显示账户下拉（单/多模式都可用）。names 空/None → 禁用（暂无账户）。

        names: 账户名列表
        account_var: tk.StringVar（由外部持有，MainWindow 读取当前账户）
        on_change: 切换账户回调 (name) -> None
        """
        self._multi = bool(names)
        if names:
            self._account_combo.config(state="readonly")
            self._account_combo["values"] = list(names)
            if account_var is not None:
                self._account_combo.configure(textvariable=account_var)
                if not account_var.get():
                    account_var.set(names[0])
            if on_change:
                self._on_account_change = on_change
                self._account_combo.bind("<<ComboboxSelected>>", self._on_combo_selected)
        else:
            self._account_combo.config(state="disabled")
            self._account_combo["values"] = []

    def _on_combo_selected(self, _event=None) -> None:
        if self._on_account_change:
            self._on_account_change(self._account_combo.get())

    def _toggle_menu(self, btn: ttk.Menubutton, menu: tk.Menu) -> str:
        """[联系人]/[标签] 点击：弹出菜单（tk_popup 阻塞式）

        tk_popup 带 grab：再点按钮或点菜单外任意处即收起并返回。
        返回 "break" 阻止 Menubutton 默认行为，避免二次弹出。
        """
        try:
            menu.tk_popup(btn.winfo_rootx(), btn.winfo_rooty() + btn.winfo_height())
        finally:
            menu.grab_release()
        return "break"

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
        self._btn_account_mgr.config(state=state)
        self.set_account_enabled(enabled)

    def set_account_enabled(self, enabled: bool) -> None:
        """仅禁用账户下拉（检查/搜索/导入操作期间防切账户导致结果串账户）

        set_enabled = 全部控件；本方法 = 只锁账户下拉。
        """
        if not self._multi:
            return
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
    def set_on_account_manager(self, cb): self._on_account_manager = cb
