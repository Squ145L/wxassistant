"""好友列表面板 — 顶部筛选行（搜索/正则/标签）+ Treeview + 底部操作行（全选/反选/删除）"""

import tkinter as tk
from tkinter import ttk, simpledialog, messagebox
from typing import Callable, Optional

from src.ui import ui_kit


class FriendList(ttk.Frame):

    def __init__(self, parent: tk.Widget):
        super().__init__(parent)
        self._friends: list = []
        self._check_vars: dict[str, tk.BooleanVar] = {}
        self._failed_reasons: dict[str, str] = {}
        self._select_all_var = tk.BooleanVar(value=True)

        # ---- 筛选状态（原 FilterBar 逻辑并入）----
        self._filter_var = tk.StringVar()
        self._filter_var.trace_add("write", self._on_filter_var_changed)
        self._regex_mode = tk.BooleanVar(value=False)
        self._regex_mode.trace_add("write", self._on_filter_var_changed)
        self._tag_var = tk.StringVar(value="全部")
        self._match_label_var = tk.StringVar(value="匹配 0/0 人")
        self._on_tag_filter: Optional[Callable[[str], None]] = None
        # 搜索框占位符（未输入时浅色 "搜索..."）
        self._placeholder_text = "搜索..."
        self._placeholder_active = True

        self._on_add: Optional[Callable[[str], bool]] = None
        self._on_delete: Optional[Callable[[list], bool]] = None
        self._on_rename: Optional[Callable[[str, str], bool]] = None
        self._on_set_tag: Optional[Callable[[str, str], bool]] = None
        self._on_search_contacts: Optional[Callable[[], None]] = None
        self._on_import_all: Optional[Callable[[], None]] = None

        self._rename_entry = None
        self._rename_iid = None
        self._selected_count = 0
        self._dirty_rows: set[str] = set()

        self._build_ui()

    def set_callbacks(self, on_add, on_delete, on_rename, on_set_tag=None, on_search=None, on_import=None):
        self._on_add = on_add
        self._on_delete = on_delete
        self._on_rename = on_rename
        self._on_set_tag = on_set_tag
        self._on_search_contacts = on_search
        self._on_import_all = on_import

    # ================================================================
    # UI 构建
    # ================================================================

    def _build_ui(self):
        # ---- 顶部筛选行（下沉自 filter_bar）：搜索框(固定≈8汉字) + .* + 标签▾ + 匹配计数 ----
        filter_row = ttk.Frame(self)
        filter_row.pack(fill=tk.X, padx=ui_kit.PAD_S, pady=(ui_kit.PAD_S, 0))

        self._filter_entry = ttk.Entry(filter_row, textvariable=self._filter_var,
                                       font=("Consolas", 10), width=16)
        self._filter_entry.pack(side=tk.LEFT)
        self._setup_search_placeholder()
        ttk.Button(filter_row, text="✕", width=3, command=self.clear_filter).pack(
            side=tk.LEFT, padx=(ui_kit.PAD_XS, 0))
        self._cb_regex = ttk.Checkbutton(filter_row, text=".*", variable=self._regex_mode)
        self._cb_regex.pack(side=tk.LEFT, padx=(ui_kit.PAD_S, 0))
        ttk.Label(filter_row, text="标签:").pack(side=tk.LEFT, padx=(ui_kit.PAD_S, 0))
        self._tag_combo = ttk.Combobox(filter_row, textvariable=self._tag_var,
                                       values=["全部"], state="readonly", width=6)
        self._tag_combo.pack(side=tk.LEFT, padx=(ui_kit.PAD_XS, 0))
        self._tag_combo.bind("<<ComboboxSelected>>", self._on_tag_selected)
        ui_kit.Spacer(filter_row).pack(side=tk.LEFT, fill=tk.X, expand=True)  # 弹性区防折叠
        self._regex_hint = ttk.Label(filter_row, text="", foreground="#2196F3", font=("", 8))
        self._regex_hint.pack(side=tk.RIGHT, padx=(0, ui_kit.PAD_S))
        self._match_label = ttk.Label(filter_row, textvariable=self._match_label_var,
                                      foreground="gray", font=("", 9))
        self._match_label.pack(side=tk.RIGHT, padx=(0, ui_kit.PAD_S))

        # ---- 操作行（搜索框下面一行）：➕/删除 (Spacer) 已选x/y 全选 反选 ----
        actions = ttk.Frame(self)
        actions.pack(fill=tk.X, padx=ui_kit.PAD_S, pady=(ui_kit.PAD_S, 0))
        self._btn_add = ttk.Button(actions, text="➕", width=3, command=self._pop_add_menu)
        self._btn_add.pack(side=tk.LEFT)
        self._add_menu = tk.Menu(self, tearoff=0)
        self._add_menu.add_command(label="手动添加", command=self._add_friend)
        self._add_menu.add_command(label="搜索并导入", command=self._on_search_menu)
        self._add_menu.add_command(label="扫描通讯录并导入", command=self._on_import_menu)
        # 删除：默认按钮外观 + 红字（ui_kit Danger.TButton 只染文字色）
        ttk.Button(actions, text="删除", style="Danger.TButton", width=4,
                   command=self._delete_friend).pack(side=tk.LEFT, padx=(ui_kit.PAD_S, 0))
        ui_kit.Spacer(actions).pack(side=tk.LEFT, fill=tk.X, expand=True)
        self._label_count = ttk.Label(actions, text="", foreground="gray", font=("", 9))
        self._label_count.pack(side=tk.RIGHT, padx=(0, ui_kit.PAD_S))
        self._cb_select_all = ttk.Checkbutton(
            actions, text="全选", variable=self._select_all_var,
            command=self._on_select_all_toggle,
        )
        self._cb_select_all.pack(side=tk.RIGHT, padx=(0, ui_kit.PAD_S))
        ttk.Button(actions, text="反选", width=4, command=self.invert_selection).pack(side=tk.RIGHT)

        ttk.Separator(self, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=(ui_kit.PAD_S, 0))

        # Treeview（名称列 + 内嵌 Checkbutton）
        tree_frame = ttk.Frame(self)
        tree_frame.pack(fill=tk.BOTH, expand=True)

        self._tree = ttk.Treeview(
            tree_frame,
            columns=("cb", "name", "tag"),
            show="headings",
            selectmode="none",
        )
        self._tree.heading("cb", text="")
        self._tree.heading("name", text="名称")
        self._tree.heading("tag", text="标签")
        self._tree.column("cb", width=24, anchor=tk.CENTER, stretch=False)
        self._tree.column("name", width=200, anchor=tk.W)
        self._tree.column("tag", width=80, anchor=tk.W)

        scrollbar = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self._tree.yview)
        self._tree.configure(yscrollcommand=scrollbar.set)
        self._tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # 双击名称 → 重命名
        self._tree.bind("<Double-Button-1>", self._on_tree_double)
        # 单击名称 → 切换选中
        self._tree.bind("<Button-1>", self._on_tree_click)

        self._right_click_iid = None
        self._context_menu = tk.Menu(self, tearoff=0)
        self._context_menu.add_command(label="重命名", command=self._rename_right_clicked)
        self._context_menu.add_command(label="设置标签", command=self._set_tag_right_clicked)
        self._context_menu.add_separator()
        self._context_menu.add_command(label="删除", command=self._delete_right_clicked)
        self._tree.bind("<Button-3>", self._on_right_click)

        self._tree.tag_configure("failed", foreground="red")

    # ================================================================
    # 筛选（原 FilterBar 逻辑）
    # ================================================================

    def _setup_search_placeholder(self) -> None:
        """搜索框空时显示浅色 "搜索..." 占位（不参与筛选）"""
        self._filter_entry.insert(0, self._placeholder_text)
        self._filter_entry.config(foreground="gray")
        self._filter_entry.bind("<FocusIn>", self._on_search_focus_in)
        self._filter_entry.bind("<FocusOut>", self._on_search_focus_out)

    def _on_search_focus_in(self, _e=None) -> None:
        if self._placeholder_active:
            self._placeholder_active = False
            self._filter_entry.delete(0, tk.END)
            self._filter_entry.config(foreground="black")

    def _on_search_focus_out(self, _e=None) -> None:
        if not self._filter_var.get().strip():
            self._placeholder_active = True
            self._filter_entry.delete(0, tk.END)
            self._filter_entry.insert(0, self._placeholder_text)
            self._filter_entry.config(foreground="gray")

    @property
    def filter_text(self) -> str:
        # 占位符状态下视为未输入
        if self._placeholder_active:
            return ""
        return self._filter_var.get().strip()

    @property
    def is_regex_mode(self) -> bool:
        return self._regex_mode.get()

    @property
    def tag_filter(self) -> str:
        v = self._tag_var.get().strip()
        return "" if v == "全部" else v

    def set_on_tag_filter(self, callback: Callable[[str], None]) -> None:
        self._on_tag_filter = callback

    def set_tag_options(self, tags: list[str]) -> None:
        cur = self._tag_var.get()
        self._tag_combo["values"] = ["全部"] + list(tags)
        if cur not in self._tag_combo["values"]:
            self._tag_var.set("全部")

    def set_match_count(self, matched: int, total: int) -> None:
        self._match_label_var.set(f"匹配 {matched}/{total} 人")

    def set_regex_error(self, message: str = "") -> None:
        if message:
            self._regex_hint.config(text=f"⚠ {message}", foreground="red")
        else:
            self._regex_hint.config(text="", foreground="#2196F3")

    def set_regex_hint(self, text: str = "") -> None:
        self._regex_hint.config(text=text, foreground="#2196F3")

    def clear_filter(self) -> None:
        """清空筛选 + 恢复浅色占位符（账户切换时调用，防串账户）"""
        self._placeholder_active = True
        self._filter_var.set("")
        self._filter_entry.delete(0, tk.END)
        self._filter_entry.insert(0, self._placeholder_text)
        self._filter_entry.config(foreground="gray")
        self._regex_mode.set(False)
        self._tag_var.set("全部")
        self.set_regex_error("")
        self.set_regex_hint("")

    def _on_filter_var_changed(self, *_args) -> None:
        """搜索/正则变化 → 提示更新 + 触发外部重筛（<<FilterChanged>>）"""
        if self._placeholder_active:
            return  # 占位符的插入/删除不触发筛选
        from src.services.friend_service import FriendService
        if self._regex_mode.get() and self.filter_text:
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

    def set_enabled(self, enabled: bool) -> None:
        """发送中禁用筛选控件（搜索框 + 正则开关）"""
        state = tk.NORMAL if enabled else tk.DISABLED
        self._filter_entry.config(state=state)
        self._cb_regex.config(state=state)

    def _on_tag_selected(self, _event=None) -> None:
        if self._on_tag_filter:
            self._on_tag_filter(self.tag_filter)

    # ================================================================
    # 数据
    # ================================================================

    def set_friends(self, friends: list):
        self._friends = list(friends)
        for f in self._friends:
            if f.name not in self._check_vars:
                self._check_vars[f.name] = tk.BooleanVar(value=True)
        self._selected_count = sum(1 for v in self._check_vars.values() if v.get())
        self._populate_tree()

    def get_selected(self) -> list:
        return [f for f in self._friends if self._check_vars.get(f.name, tk.BooleanVar(value=True)).get()]

    def get_selected_count(self) -> int:
        return sum(1 for f in self._friends if self._check_vars.get(f.name, tk.BooleanVar(value=True)).get())

    @property
    def total_count(self) -> int:
        return len(self._friends)

    def select_all(self):
        for f in self._friends:
            self._check_vars[f.name].set(True)
        self._select_all_var.set(True)
        self._populate_tree()

    def select_none(self):
        for f in self._friends:
            self._check_vars[f.name].set(False)
        self._select_all_var.set(False)
        self._populate_tree()

    def invert_selection(self):
        for f in self._friends:
            v = self._check_vars[f.name]
            v.set(not v.get())
        self._populate_tree()

    def set_checked_by_names(self, names: set, checked: bool):
        for f in self._friends:
            if f.name in names:
                self._check_vars[f.name].set(checked)
        self._populate_tree()

    def mark_failed(self, names):
        """标记失败项。names 为 list[str] 时原因默认"发送失败"；为 dict[str,str] 时自定义原因"""
        if isinstance(names, list):
            self._failed_reasons = {n: "发送失败" for n in names}
        else:
            self._failed_reasons = dict(names)
        self._populate_tree()

    def clear_failed_marks(self):
        if self._failed_reasons:
            self._failed_reasons.clear()
            self._populate_tree()

    # ================================================================
    # Treeview 填充
    # ================================================================

    def _populate_tree(self):
        self._tree.delete(*self._tree.get_children())
        for f in self._friends:
            name = f.name
            checked = self._check_vars.get(name, tk.BooleanVar(value=True)).get()
            mark = "☑" if checked else "☐"
            reason = self._failed_reasons.get(name, "")
            display = name + (f"  {reason}" if reason else "")
            tags = ("failed",) if reason else ()
            self._tree.insert("", tk.END, iid=name,
                              values=(mark, display, getattr(f, "tag", "")), tags=tags)
        self._selected_count = sum(1 for v in self._check_vars.values() if v.get())
        self._dirty_rows.clear()
        self._update_count_label()
        self._update_select_all_sync()

    def _update_count_label(self):
        selected = self.get_selected_count()
        self._label_count.config(text=f"已选 {selected}/{len(self._friends)} 人")

    def _update_select_all_sync(self):
        if self._friends:
            all_on = all(self._check_vars.get(f.name, tk.BooleanVar(value=True)).get() for f in self._friends)
            self._select_all_var.set(all_on)

    # ================================================================
    # 树操作
    # ================================================================

    def _on_tree_click(self, event):
        item = self._tree.identify_row(event.y)
        if item and item in self._check_vars:
            v = self._check_vars[item]
            new_val = not v.get()
            v.set(new_val)
            # 数据层立即更新
            self._selected_count += 1 if new_val else -1
            total = len(self._friends)
            self._label_count.config(text=f"已选 {self._selected_count}/{total} 人")
            self._select_all_var.set(self._selected_count == total)
            # 显示层延迟批量刷新
            if not self._dirty_rows:
                self._tree.after_idle(self._flush_dirty_rows)
            self._dirty_rows.add(item)

    def _flush_dirty_rows(self):
        """批量刷新被修改的行，idle 时只跑一次"""
        for name in self._dirty_rows:
            checked = self._check_vars.get(name, tk.BooleanVar(value=True)).get()
            mark = "☑" if checked else "☐"
            reason = self._failed_reasons.get(name, "")
            display = name + (f"  {reason}" if reason else "")
            tags = ("failed",) if reason else ()
            if self._tree.exists(name):
                self._tree.item(name, values=(mark, display, getattr(
                    next((f for f in self._friends if f.name == name), None), "tag", ""
                )), tags=tags)
        self._dirty_rows.clear()

    def _on_tree_double(self, event):
        # 只响应名称列（#2），复选框列双击不触发重命名
        if self._tree.identify_column(event.x) != "#2":
            return
        item = self._tree.identify_row(event.y)
        if item:
            for f in self._friends:
                if f.name == item:
                    self._do_rename(f)
                    break

    def _on_right_click(self, event):
        item = self._tree.identify_row(event.y)
        if item:
            self._right_click_iid = item
            self._context_menu.tk_popup(event.x_root, event.y_root)

    def _rename_right_clicked(self):
        if self._right_click_iid:
            for f in self._friends:
                if f.name == self._right_click_iid:
                    self._do_rename(f)
                    break

    def _set_tag_right_clicked(self):
        if not self._right_click_iid or not self._on_set_tag:
            return
        old_tag = ""
        for f in self._friends:
            if f.name == self._right_click_iid:
                old_tag = getattr(f, "tag", "")
                break
        new_tag = simpledialog.askstring(
            "设置标签", f"为 '{self._right_click_iid}' 设置标签：",
            initialvalue=old_tag, parent=self,
        )
        if new_tag is not None:
            self._on_set_tag(self._right_click_iid, new_tag.strip())

    def _on_select_all_toggle(self):
        if self._select_all_var.get():
            self.select_all()
        else:
            self.select_none()

    # ================================================================
    # 增删改
    # ================================================================

    def _pop_add_menu(self):
        x = self._btn_add.winfo_rootx()
        y = self._btn_add.winfo_rooty() + self._btn_add.winfo_height()
        self._add_menu.tk_popup(x, y)

    def _on_search_menu(self):
        if self._on_search_contacts:
            self._on_search_contacts()

    def _on_import_menu(self):
        if self._on_import_all:
            self._on_import_all()

    def _add_friend(self):
        name = simpledialog.askstring("添加好友", "输入好友名称：", parent=self)
        if name and name.strip() and self._on_add:
            self._on_add(name.strip())

    def _do_rename(self, friend):
        old = friend.name
        if self._rename_entry:
            self._rename_commit()

        bbox = self._tree.bbox(old, column="#2")
        if not bbox:
            return
        x, y, w, h = bbox

        entry = tk.Entry(self._tree, font=("Microsoft YaHei", 10))
        entry.insert(0, old)
        entry.select_range(0, tk.END)
        entry.place(x=x, y=y, width=w, height=h)
        entry.focus_set()

        self._rename_entry = entry
        self._rename_iid = old

        def _commit(_e=None):
            self._rename_commit()

        def _cancel(_e=None):
            self._rename_cancel()

        entry.bind("<Return>", _commit)
        entry.bind("<Escape>", _cancel)
        self._tree.bind("<Button-1>", lambda e: entry.after(50, _commit))

    def _rename_commit(self):
        entry = self._rename_entry
        old = self._rename_iid
        if entry is None:
            return
        new = entry.get().strip()
        entry.destroy()
        self._tree.unbind("<Button-1>")
        self._tree.bind("<Button-1>", self._on_tree_click)
        self._rename_entry = None
        if new and new != old and self._on_rename:
            self._on_rename(old, new)

    def _rename_cancel(self):
        entry = self._rename_entry
        if entry is None:
            return
        entry.destroy()
        self._tree.unbind("<Button-1>")
        self._tree.bind("<Button-1>", self._on_tree_click)
        self._rename_entry = None

    def _batch_set_tag(self):
        """为勾选的联系人批量设置标签"""
        if not self._on_set_tag:
            return
        names = [f.name for f in self._friends if self._check_vars.get(f.name, tk.BooleanVar(value=True)).get()]
        if not names:
            messagebox.showinfo("提示", "请先勾选要设置标签的好友")
            return
        # 预填：如果所有选中好友标签一致，就用那个标签
        tags = {getattr(f, "tag", "") for f in self._friends if f.name in names}
        initial = list(tags)[0] if len(tags) == 1 else ""
        new_tag = simpledialog.askstring(
            "设置标签", f"为 {len(names)} 位联系人设置标签：",
            initialvalue=initial, parent=self,
        )
        if new_tag is not None:
            for name in names:
                self._on_set_tag(name, new_tag.strip())

    def _delete_friend(self):
        names = [f.name for f in self._friends if self._check_vars.get(f.name, tk.BooleanVar(value=True)).get()]
        if not names:
            messagebox.showinfo("提示", "请先勾选要删除的好友")
            return
        msg = f"确认删除 {len(names)} 位联系人？(微信内不会删除)\n\n" + "\n".join(names[:10])
        if len(names) > 10:
            msg += f"\n... 还有 {len(names) - 10} 位"
        if messagebox.askyesno("确认删除", msg):
            if self._on_delete:
                self._on_delete(names)

    def _delete_right_clicked(self):
        """右键删除：只删右键点击的那一个"""
        if not self._right_click_iid:
            return
        name = self._right_click_iid
        if messagebox.askyesno("确认删除", f"确认删除 '{name}'？\n(微信内不会删除)"):
            if self._on_delete:
                self._on_delete([name])
