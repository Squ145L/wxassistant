"""主窗口：布局组装 + 组件联动 + 后台发送线程管理"""

import logging
import queue
import subprocess
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import ttk, messagebox
from typing import Optional, Callable

from src.utils.calibration import calibration_has_key
from src.utils.config import (
    WINDOW_WIDTH, WINDOW_HEIGHT, WINDOW_TITLE, LEFT_PANEL_WIDTH, LEFT_MIN_PANEL_WIDTH,
)
from src.utils.coordinates import get_coord
from src.utils.logger import set_ui_callback
from src.ui.filter_bar import FilterBar
from src.ui.friend_list import FriendList
from src.ui.message_editor import MessageEditor
from src.ui.send_progress import SendProgress
from src.ui.result_dialog import ResultDialog
from src.ui.top_bar import TopBar
from src.services.multi_account import find_overlapping_accounts

logger = logging.getLogger(__name__)


class MainWindow:

    def __init__(self, multi_session=None):
        self.root = tk.Tk()
        self.root.title(WINDOW_TITLE)
        self.root.geometry(f"{WINDOW_WIDTH}x{WINDOW_HEIGHT}")
        self.root.minsize(960, 580)

        self._friend_service = None
        self._bridge = None  # WeChatBridge，校准前用来打开对应窗口
        self._multi_session = multi_session      # Optional[MultiAccountSession]
        self._account_runtime: dict = {}          # name -> (bridge, friend_service)
        self._account_var: Optional[tk.StringVar] = None
        self._on_send: Optional[Callable] = None
        self._on_check_names: Optional[Callable] = None
        self._on_search_contacts: Optional[Callable] = None
        self._on_enter_multiopen: Optional[Callable] = None
        self._on_exit_multiopen: Optional[Callable] = None
        self._on_account_manager: Optional[Callable] = None
        self._progress_queue: queue.Queue = queue.Queue()
        self._stop_event: Optional[threading.Event] = None
        self._interrupt_poll_active: bool = False
        self._busy: bool = False

        self._build_ui()
        self._wire_events()
        self._poll_progress_queue()

        # 任意键/鼠标点击中断（仅在操作进行中生效）
        self.root.bind("<Key>", self._on_interrupt)
        self.root.bind("<Button-1>", self._on_interrupt)
        self.root.bind("<Button-3>", self._on_interrupt)

        set_ui_callback(self._on_log_message)
        logger.info("主窗口初始化完成")

        # 输出 startup.txt 内容到日志窗口
        self._show_startup_hints()

    # ================================================================
    # 回调注入
    # ================================================================

    def set_bridge(self, bridge):
        self._bridge = bridge

    def set_friend_service(self, friend_service):
        self._friend_service = friend_service
        self._reload_from_service()

    def set_send_callback(self, callback: Callable):
        self._on_send = callback

    def set_check_names_callback(self, callback: Callable):
        self._on_check_names = callback

    def set_search_contacts_callback(self, callback: Callable):
        self._on_search_contacts = callback

    def set_enter_multiopen_callback(self, callback: Callable) -> None:
        self._on_enter_multiopen = callback

    def set_exit_multiopen_callback(self, callback: Callable) -> None:
        self._on_exit_multiopen = callback

    def set_on_account_manager(self, callback: Callable) -> None:
        self._on_account_manager = callback

    def set_account_runtime(self, runtime: dict) -> None:
        """注入账户运行时：{账户名: (bridge, friend_service)}（单/多模式通用）"""
        self._account_runtime = runtime
        names = list(runtime.keys())
        if names:
            self.top_bar.set_account_options(names, self._account_var, self._on_account_selected)
            first = names[0]
            self._account_var.set(first)
            self._switch_account(first)

    def get_current_bridge(self):
        """返回当前账户的 bridge（多账户）；单账户返回 self._bridge"""
        if self._account_runtime and self._account_var is not None:
            name = self._account_var.get()
            if name in self._account_runtime:
                return self._account_runtime[name][0]
        return self._bridge

    def get_current_friend_service(self):
        """返回当前账户的 friend_service（多账户）；单账户返回 self._friend_service"""
        if self._account_runtime and self._account_var is not None:
            name = self._account_var.get()
            if name in self._account_runtime:
                return self._account_runtime[name][1]
        return self._friend_service

    def _switch_account(self, name: str) -> None:
        """切换到指定账户：换 bridge + friend_service（不可跨账户多选，清空勾选）"""
        if name not in self._account_runtime:
            return
        bridge, service = self._account_runtime[name]
        self.set_bridge(bridge)
        self.set_friend_service(service)
        self.friend_list.select_none()
        # 清空上一条账户残留的搜索/正则/标签筛选，再刷新到当前账户全量列表
        self.filter_bar.clear_filter()

    # ================================================================
    # UI 构建
    # ================================================================

    def _build_ui(self):
        # 顶栏（窗口级操作：账户/联系人/标签/刷新/设置/多开）
        self.top_bar = TopBar(self.root)
        self.top_bar.pack(fill=tk.X, side=tk.TOP, padx=6, pady=(6, 0))
        self.top_bar.set_on_account_change(self._on_account_selected)
        self.top_bar.set_on_check_names(self._on_check_names_clicked)
        self.top_bar.set_on_export(self._on_export_clicked)
        self.top_bar.set_on_import_all(self._on_import_all_clicked)
        self.top_bar.set_on_search_import(self._on_search_contacts_clicked)
        self.top_bar.set_on_batch_tag(self._on_batch_tag_clicked)
        self.top_bar.set_on_clear_tags(self._on_clear_tags_clicked)
        self.top_bar.set_on_refresh(self._on_refresh)
        self.top_bar.set_on_settings(self._open_settings)
        self.top_bar.set_on_help(self._on_help_clicked)
        self.top_bar.set_on_multiopen(self._on_multiopen_clicked)

        # 账户选择器始终创建；账户列表由 set_account_runtime 填充
        self._account_var = tk.StringVar()
        self.top_bar.set_account_options([], self._account_var, self._on_account_selected)
        if self._multi_session is not None:
            self.top_bar.set_multiopen_label(True)

        # 底部先 pack（确保不被挤出）
        self.send_progress = SendProgress(self.root)
        self.send_progress.pack(fill=tk.X, side=tk.BOTTOM, padx=6, pady=(0, 6))

        # 主区域
        # 用经典 tk.PanedWindow（支持 pane minsize，限制联系人面板最小宽度）
        main_paned = tk.PanedWindow(self.root, orient=tk.HORIZONTAL, sashrelief=tk.RAISED)
        main_paned.pack(fill=tk.BOTH, expand=True, padx=6, pady=(6, 0))

        left = ttk.Frame(main_paned, width=LEFT_PANEL_WIDTH)
        main_paned.add(left, minsize=LEFT_MIN_PANEL_WIDTH)

        self.filter_bar = FilterBar(left)
        self.filter_bar.pack(fill=tk.X)
        self.filter_bar.set_on_tag_filter(self._on_tag_filter_changed)

        self.friend_list = FriendList(left)
        self.friend_list.pack(fill=tk.BOTH, expand=True)

        right = ttk.Frame(main_paned)
        main_paned.add(right, minsize=360)

        self.message_editor = MessageEditor(right)
        self.message_editor.pack(fill=tk.BOTH, expand=True)

    def _wire_events(self):
        self.filter_bar.bind("<<FilterChanged>>", lambda _e: self._apply_filter())
        self.friend_list.set_callbacks(
            on_add=self._handle_add,
            on_delete=self._handle_delete,
            on_rename=self._handle_rename,
            on_set_tag=self._handle_set_tag,
            on_search=self._on_search_contacts_clicked,
            on_import=self._on_import_all_clicked,
        )
        self.send_progress.set_callbacks(
            on_start=self._on_start_send,
            on_stop=self._on_stop_send,
        )
        # 消息模板被修改 → 清除失败红字
        self.message_editor.set_on_text_changed(self.friend_list.clear_failed_marks)

    # ================================================================
    # 好友管理
    # ================================================================

    def _reload_from_service(self):
        if self._friend_service:
            self.filter_bar.set_tag_options(self._friend_service.all_tags())
            self._apply_filter()

    def _apply_filter(self):
        if not self._friend_service:
            return

        text = self.filter_bar.filter_text
        use_regex = self.filter_bar.is_regex_mode
        all_friends = self._friend_service.all_friends

        if not text:
            filtered = list(all_friends)
            self.filter_bar.set_regex_error("")
            self.filter_bar.set_regex_hint("")
        elif use_regex:
            try:
                from src.services.friend_service import FriendService
                compiled = FriendService.try_compile_regex(text)
                if compiled is None:
                    self.filter_bar.set_regex_error("正则语法错误")
                    return
                self.filter_bar.set_regex_error("")
                filtered = [f for f in all_friends if compiled.search(f.name)]
                if compiled.groups > 0:
                    self.filter_bar.set_regex_hint(
                        f"{compiled.groups} 个捕获组 -> [$1]...[${compiled.groups}] 可用于模板"
                    )
                else:
                    self.filter_bar.set_regex_hint("正则匹配模式")
            except Exception:
                self.filter_bar.set_regex_error("正则匹配异常")
                return
        else:
            filtered = [f for f in all_friends if f.name.startswith(text)]
            self.filter_bar.set_regex_error("")
            self.filter_bar.set_regex_hint("")

        # 标签筛选（和名字筛选是 AND 关系）
        tag = self.filter_bar.tag_filter
        if tag:
            filtered = [f for f in filtered if getattr(f, "tag", "") == tag]

        self.friend_list.set_friends(filtered)
        self.filter_bar.set_match_count(len(filtered), len(all_friends))
        self._sync_selected_count()

    def update_friend_list(self, friends: list, keyword: str = ""):
        self._apply_filter()

    def _handle_add(self, name: str) -> bool:
        if self._friend_service:
            ok = self._friend_service.add_friend(name)
            if ok:
                self._apply_filter()
            return ok
        return False

    def _handle_delete(self, names) -> bool:
        if self._friend_service:
            ok = self._friend_service.remove_friends(names if isinstance(names, list) else [names])
            if ok:
                self._apply_filter()
            return ok
        return False

    def _handle_set_tag(self, name: str, tag: str) -> bool:
        if self._friend_service:
            ok = self._friend_service.set_tag(name, tag)
            if ok:
                self.filter_bar.set_tag_options(self._friend_service.all_tags())
                self._apply_filter()
            return ok
        return False

    def _on_tag_filter_changed(self, tag: str) -> None:
        self._apply_filter()

    def _on_batch_tag_clicked(self) -> None:
        """FilterBar 的 🏷 标签按钮 → 调用 FriendList 的批量标签"""
        self.friend_list._batch_set_tag()

    def _on_clear_tags_clicked(self) -> None:
        """FilterBar 的清除标签按钮 → 清除选中联系人的标签"""
        names = [f.name for f in self.friend_list._friends
                 if self.friend_list._check_vars.get(f.name, tk.BooleanVar(value=True)).get()]
        if not names:
            messagebox.showinfo("提示", "请先勾选要清除标签的好友")
            return
        for name in names:
            self._handle_set_tag(name, "")

    def _handle_rename(self, old: str, new: str) -> bool:
        if self._friend_service:
            ok = self._friend_service.rename_friend(old, new)
            if ok:
                self._apply_filter()
            return ok
        return False

    def _launch_calibrate(self, key: str = "chat_title"):
        if self._bridge:
            if key == "contacts_list":
                self.send_progress.set_status("正在打开通讯录管理...")
                def _prep():
                    self._bridge.open_contacts_manager()
                    self._launch_calibrate_subprocess(key)
                threading.Thread(target=_prep, daemon=True).start()
                return
            elif key == "chat_title":
                self.send_progress.set_status("正在打开聊天界面...")
                def _prep():
                    self._bridge.activate_window()
                    rect = self._bridge.get_window_rect()
                    if rect:
                        ww = rect[2] - rect[0]; wh = rect[3] - rect[1]
                        # 点微信主界面(聊天)标签
                        cx_pct, cy_pct = get_coord("tab_chat", self._current_account_name())
                        self._bridge.click_at(
                            rect[0] + int(ww * cx_pct),
                            rect[1] + int(wh * cy_pct))
                        time.sleep(0.5)
                        # 点第一个聊天
                        cx_pct, cy_pct = get_coord("chat_first", self._current_account_name())
                        self._bridge.click_at(
                            rect[0] + int(ww * cx_pct),
                            rect[1] + int(wh * cy_pct))
                        time.sleep(0.5)
                    self._launch_calibrate_subprocess(key)
                threading.Thread(target=_prep, daemon=True).start()
                return
        self._launch_calibrate_subprocess(key)

    def _launch_calibrate_subprocess(self, key: str):
        script = Path(__file__).parent.parent.parent / "calibrate_ocr.py"
        cmd = ["python", str(script), "--key", key]
        acct = self._current_account_name()
        if acct:
            cmd += ["--account", acct]
        subprocess.Popen(cmd)
        self.send_progress.set_status("就绪")
        logger.info("启动校准: key=%s account=%s", key, acct)

    def _ensure_calibration(self, key: str) -> bool:
        """发送/扫描前检查校准（账户感知：账户专属或继承全局都算已校准）"""
        if calibration_has_key(key, self._current_account_name()):
            return True
        if messagebox.askyesno("未校准", f"尚未校准 [{key}] 区域，现在打开校准工具？"):
            self._launch_calibrate(key)
        return False

    def _on_account_selected(self, _event=None) -> None:
        if self._account_var:
            self._switch_account(self._account_var.get())

    def _on_multiopen_clicked(self) -> None:
        if self._multi_session is not None:
            if self._on_exit_multiopen:
                self._on_exit_multiopen()
        else:
            if self._on_enter_multiopen:
                self._on_enter_multiopen()

    def _on_account_manager_clicked(self) -> None:
        """打开账户管理弹窗：新建/重命名/删除/双击切换"""
        from src.ui.account_manager_dialog import AccountManagerDialog
        dlg = AccountManagerDialog(self.root, current=self._current_account_name() or "",
                                   on_switch=self._switch_account)
        dlg.grab_set()

    def _on_refresh(self) -> None:
        """刷新按钮：清除所有红色标记 + 重新连接微信窗口"""
        self.friend_list.clear_failed_marks()
        if self._multi_session is not None:
            # 多账户：不重找窗口（会破坏账户绑定），只校验当前窗口有效性
            bridge = self.get_current_bridge()
            if bridge.is_window_valid():
                self.send_progress.set_status("已刷新 — 当前账户窗口有效")
            else:
                self.send_progress.set_status("刷新失败 — 当前账户窗口已失效，请重新进入多开")
            return
        if self._bridge.find_window():
            self.send_progress.set_status("已刷新 — 重新连接微信窗口")
        else:
            self.send_progress.set_status("刷新失败 — 未找到微信窗口")

    def _on_check_names_clicked(self):
        if not self._ensure_not_busy():
            return
        selected = self.friend_list.get_selected()
        if not selected:
            messagebox.showinfo("提示", "请先勾选要检查的好友。")
            return
        if not self._on_check_names:
            return
        self._set_busy(True)
        self._stop_event = threading.Event()
        self._interrupt_poll_active = True
        self._was_interrupted = False
        threading.Thread(target=self._interrupt_poll_loop, daemon=True).start()
        self.send_progress.set_status("正在检查选中名称...")
        threading.Thread(target=self._on_check_names, args=(selected, self._progress_queue, self._stop_event), daemon=True).start()

    def _on_search_contacts_clicked(self):
        if not self._ensure_not_busy():
            return
        if not self._ensure_calibration("contacts_list"):
            return
        if not self._on_search_contacts:
            return
        # 弹窗输入关键词
        kw = self._prompt_keyword()
        if not kw:
            return
        self.send_progress.set_status("正在搜索并导入...")
        self.send_progress.append_log(f"搜索: '{kw}'")
        self._set_busy(True)
        self._stop_event = threading.Event()
        self._interrupt_poll_active = True
        self._was_interrupted = False
        threading.Thread(target=self._interrupt_poll_loop, daemon=True).start()
        threading.Thread(target=self._on_search_contacts,
                         args=(kw.strip(), self._progress_queue, self._stop_event),
                         daemon=True).start()

    def _on_import_all_clicked(self):
        if not self._ensure_not_busy():
            return
        if not self._ensure_calibration("contacts_list"):
            return
        if not self._on_search_contacts:
            return
        if not messagebox.askyesno("扫描通讯录并导入",
                                    "确认开始扫描通讯录并导入所有联系人？\n\n"
                                    "此操作将打开通讯录管理窗口并翻页截图。"):
            return
        self.send_progress.set_status("正在扫描通讯录...")
        self.send_progress.clear_log()
        self._set_busy(True)
        self._stop_event = threading.Event()
        self._interrupt_poll_active = True
        self._was_interrupted = False
        threading.Thread(target=self._interrupt_poll_loop, daemon=True).start()
        threading.Thread(target=self._on_search_contacts,
                         args=("", self._progress_queue, self._stop_event),
                         daemon=True).start()

    def _prompt_keyword(self) -> str:
        """弹出关键词输入窗口（居中，较大）"""
        dlg = tk.Toplevel(self.root)
        dlg.title("搜索并导入")
        dlg.resizable(False, False)
        dlg.transient(self.root)
        dlg.grab_set()

        frame = ttk.Frame(dlg, padding=20)
        frame.pack()

        ttk.Label(frame, text="输入关键词", font=("Microsoft YaHei", 11)).pack(pady=(0, 8))
        entry = ttk.Entry(frame, font=("Microsoft YaHei", 11), width=30)
        entry.pack(fill=tk.X, pady=(0, 12))
        entry.focus_set()

        result = [""]

        def _ok():
            result[0] = entry.get().strip()
            dlg.destroy()

        btn_frame = ttk.Frame(frame)
        btn_frame.pack()
        ttk.Button(btn_frame, text="确认", command=_ok).pack(side=tk.LEFT, padx=4)
        ttk.Button(btn_frame, text="取消", command=dlg.destroy).pack(side=tk.LEFT, padx=4)

        entry.bind("<Return>", lambda e: _ok())
        entry.bind("<Escape>", lambda e: dlg.destroy())

        dlg.update_idletasks()
        pw = self.root.winfo_width(); ph = self.root.winfo_height()
        px = self.root.winfo_rootx(); py = self.root.winfo_rooty()
        dw, dh = 360, 140
        dlg.geometry(f"{dw}x{dh}+{px + (pw - dw) // 2}+{py + (ph - dh) // 2}")

        dlg.wait_window()
        return result[0]

    def _on_help_clicked(self):
        dlg = tk.Toplevel(self.root)
        dlg.title("帮助")
        dlg.resizable(False, False)
        dlg.transient(self.root)
        dlg.grab_set()

        frame = ttk.Frame(dlg, padding=20)
        frame.pack()

        msg = (
            "OCR 菜单说明:\n\n"
            "[OCR校准] 聊天界面标题 — 校准聊天标题栏位置\n"
            "检查选中名称是否完整 — 搜索选中的好友并 OCR 比对\n"
            "搜索并导入.. — 输入关键词搜索联系人\n"
            "扫描通讯录并导入 — 打开通讯录管理，翻页 OCR 导入全部\n"
            "[OCR校准] / [设置] — 校准/设置扫描通讯录功能\n\n"
            "消息模板变量: [name]=好友名 [name2]=后两字\n"
            "[$1][$2].. = 正则捕获组\n"
            "中断: 操作进行中按任意键或鼠标点击"
        )
        ttk.Label(frame, text=msg, font=("Microsoft YaHei", 10),
                  justify=tk.LEFT).pack(pady=(0, 16))

        btn_frame = ttk.Frame(frame)
        btn_frame.pack()
        ttk.Button(btn_frame, text="打开文件夹",
                   command=lambda: [self._open_project_dir(), dlg.destroy()]).pack(
                       side=tk.LEFT, padx=(0, 12))
        ttk.Button(btn_frame, text="关闭", command=dlg.destroy).pack(side=tk.RIGHT)

        dlg.update_idletasks()
        pw = self.root.winfo_width(); ph = self.root.winfo_height()
        px = self.root.winfo_rootx(); py = self.root.winfo_rooty()
        dw, dh = 420, 330
        dlg.geometry(f"{dw}x{dh}+{px + (pw - dw) // 2}+{py + (ph - dh) // 2}")

    def _open_project_dir(self):
        import os
        os.startfile(str(Path(__file__).parent.parent.parent))

    def _on_import_settings_clicked(self):
        self._open_settings("OCR")

    def _on_export_clicked(self, fmt: str) -> None:
        """导出选中联系人（fmt: txt/csv/json）"""
        selected = self.friend_list.get_selected()
        if not selected:
            messagebox.showinfo("提示", "请先勾选要导出的联系人。")
            return
        from src.services.export_service import export_friends
        path = export_friends(selected, fmt, self._current_account_name())
        messagebox.showinfo("导出完成", f"已导出 {len(selected)} 位联系人到：\n{path}")

    def _current_account_name(self) -> Optional[str]:
        """当前账户名（单/多模式都用账户选择器的选中值）；无账户时返回 None"""
        if self._account_var and self._account_var.get():
            return self._account_var.get()
        return None

    def _current_account_names(self) -> list[str]:
        """当前可切换的账户名列表（单/多模式）；无账户返回空列表"""
        return list(self._account_runtime.keys())

    def _open_settings(self, tab: str = "常规") -> None:
        """打开设置弹窗（携带当前账户上下文 + 校准入口）"""
        from src.ui.settings_dialog import SettingsDialog
        names = self._current_account_names()
        SettingsDialog(
            self.root, tab=tab,
            account_name=self._current_account_name(),
            account_names=names or None,
            on_calibrate=self._launch_calibrate,
        )

    # ================================================================
    # 发送控制
    # ================================================================

    def _check_window_overlap(self) -> bool:
        """多账户模式下检测窗口重叠。返回 True=无重叠或用户选择继续"""
        if self._multi_session is None:
            return True
        rects: list[tuple[str, tuple]] = []
        for name, (bridge, _fs) in self._account_runtime.items():
            rect = bridge.get_window_rect()
            if rect is not None:
                rects.append((name, rect))
        pairs = find_overlapping_accounts(rects)
        if not pairs:
            return True
        names = "\n".join(f"  • {a} 与 {b}" for a, b in pairs)
        return messagebox.askyesno(
            "检测到窗口重叠",
            f"以下窗口存在重叠，可能互相遮挡导致操作错误：\n{names}\n\n"
            "建议平铺窗口后重新进入多开。\n是否仍然继续？",
        )

    def _check_calibration(self) -> bool:
        """发送前检查是否做过聊天标题校准，未校准则提示。返回 True=可继续"""
        if calibration_has_key("chat_title", self._current_account_name()):
            return True
        return messagebox.askyesno(
            "提示",
            "尚未校准聊天标题 OCR 区域，群发时可能无法正确验证发送对象。\n"
            "建议先在 [OCR] → [OCR校准] 聊天界面标题 完成校准。\n\n是否仍然继续？",
        )

    def _on_start_send(self):
        if not self._ensure_not_busy():
            return
        selected = self.friend_list.get_selected()
        if not selected:
            messagebox.showwarning("提示", "请先选择要发送的好友。")
            return

        message = self.message_editor.get_message()
        if not message.strip():
            messagebox.showwarning("提示", "请输入消息内容。")
            return

        # 多账户模式：发送前检测窗口重叠（防止切窗操作点错窗口）
        if not self._check_window_overlap():
            return

        # 发送前检查 OCR 校准（未校准会干扰发送对象验证）
        if not self._check_calibration():
            return

        attachments = self.message_editor.get_attachments()
        interval = self.message_editor.get_interval()
        regex_pattern = self.filter_bar.filter_text if self.filter_bar.is_regex_mode else ""

        logger.info("发起群发: %d 人, 间隔 %.1fs, %d 附件",
                     len(selected), interval, len(attachments))

        if not messagebox.askyesno("确认发送", f"将向 {len(selected)} 位好友发送消息，确认开始？"):
            return

        self._set_ui_sending(True)
        self.send_progress.clear_log()

        self._stop_event = threading.Event()
        self._interrupt_poll_active = True
        self._was_interrupted = False
        threading.Thread(target=self._interrupt_poll_loop, daemon=True).start()

        if self._on_send:
            thread = threading.Thread(
                target=self._on_send,
                args=(selected, message, attachments, interval, regex_pattern,
                      self._progress_queue, self._stop_event),
                daemon=True,
            )
            thread.start()

    def _on_interrupt(self, _event=None):
        self._do_interrupt()

    def suspend_interrupt_hook(self):
        """SendKeys 前调用：暂停钩子避免模拟按键触发中断"""
        self._hook_suspended = True

    def resume_interrupt_hook(self):
        """SendKeys 后调用：恢复钩子"""
        self._hook_suspended = False

    def _do_interrupt(self):
        """触发中断 —— 不抢焦点，只设标志"""
        if self._stop_event and not self._stop_event.is_set():
            self._stop_event.set()
            self._interrupt_poll_active = False
            self._was_interrupted = True
            self.send_progress.append_log("已中断")
            self.send_progress.set_status("已中断")
            logger.info("按键中断")
            messagebox.showinfo("已中断", "已按下按键中断")
            self.root.lift()
            self.root.focus_force()

    def _interrupt_poll_loop(self):
        """后台线程：Windows 低级键盘钩子 + GetAsyncKeyState 鼠标检测"""
        import ctypes
        from ctypes import wintypes, CFUNCTYPE, POINTER, c_int

        user32 = ctypes.windll.user32
        WH_KEYBOARD_LL = 13
        WM_KEYDOWN = 0x0100

        class KBDLLHOOKSTRUCT(ctypes.Structure):
            _fields_ = [("vkCode", wintypes.DWORD), ("scanCode", wintypes.DWORD),
                        ("flags", wintypes.DWORD), ("time", wintypes.DWORD),
                        ("dwExtraInfo", ctypes.c_void_p)]

        # 保存引用防止被 GC
        hook_proc_ref = [None]
        hook_id = [None]

        def hook_cb(nCode, wParam, lParam):
            if getattr(self, '_hook_suspended', False):
                return user32.CallNextHookEx(hook_id[0], nCode, wParam, lParam)
            if nCode >= 0 and wParam == WM_KEYDOWN:
                self.root.after(0, self._do_interrupt)
                return -1  # 吃掉这个按键
            return user32.CallNextHookEx(hook_id[0], nCode, wParam, lParam)

        try:
            logger.info("中断键盘钩子已启动")
            time.sleep(0.3)  # 等释放点击按钮

            # 安装低级键盘钩子
            HOOKPROC = CFUNCTYPE(c_int, c_int, wintypes.WPARAM, POINTER(KBDLLHOOKSTRUCT))
            hook_proc = HOOKPROC(hook_cb)
            hook_proc_ref[0] = hook_proc
            hook_id[0] = user32.SetWindowsHookExW(
                WH_KEYBOARD_LL, hook_proc, None, 0)

            if not hook_id[0]:
                logger.warning("键盘钩子安装失败，回退到轮询")
                # 回退方案
                self._poll_fallback()
                return

            # 泵消息（钩子需要消息循环）
            msg = wintypes.MSG()
            while self._interrupt_poll_active:
                # 鼠标检测
                # 鼠标检测 —— bridge 模拟鼠标时跳过
                if not getattr(self, '_hook_suspended', False):
                    if user32.GetAsyncKeyState(0x01) & 0x8000:
                        self.root.after(0, self._do_interrupt)
                        break
                    if user32.GetAsyncKeyState(0x02) & 0x8000:
                        self.root.after(0, self._do_interrupt)
                        break
                # 泵消息
                if user32.PeekMessageW(ctypes.byref(msg), 0, 0, 0, 1):
                    user32.TranslateMessage(ctypes.byref(msg))
                    user32.DispatchMessageW(ctypes.byref(msg))
                else:
                    time.sleep(0.01)
        except Exception:
            logger.exception("中断钩子崩溃，回退轮询")
            try: self._poll_fallback()
            except: pass
        finally:
            if hook_id[0] is not None:
                user32.UnhookWindowsHookEx(hook_id[0])

    def _poll_fallback(self):
        """GetAsyncKeyState 轮询（钩子失败时的回退）"""
        import ctypes
        user32 = ctypes.windll.user32
        for vk in range(0x08, 0xFF):
            user32.GetAsyncKeyState(vk)
        user32.GetAsyncKeyState(0x01)
        user32.GetAsyncKeyState(0x02)
        while self._interrupt_poll_active:
            hit = False
            for vk in range(0x08, 0xFF):
                if user32.GetAsyncKeyState(vk) & 0x8001:
                    hit = True; break
            if not hit:
                m = user32.GetAsyncKeyState(0x01)
                if m & 0x8001: hit = True
                m = user32.GetAsyncKeyState(0x02)
                if m & 0x8001: hit = True
            if hit:
                self.root.after(0, self._do_interrupt)
                return
            time.sleep(0.01)

    def _on_stop_send(self):
        if self._stop_event:
            self._stop_event.set()
        self.send_progress.set_status("正在终止...")
        logger.info("用户请求终止")

    def _set_ui_sending(self, sending: bool):
        self._set_busy(sending)
        self.send_progress.set_running(sending)
        self.filter_bar.set_enabled(not sending)
        self.top_bar.set_enabled(not sending)
        self.message_editor.set_enabled(not sending)
        if sending:
            self.friend_list.select_none()

    def _set_busy(self, busy: bool) -> None:
        """标记任一后台操作（发送/检查/扫描/导入）占用；busy=True 锁定账户下拉"""
        self._busy = busy
        self.top_bar.set_account_enabled(not busy)

    def _ensure_not_busy(self) -> bool:
        """有后台操作进行中则提示并返回 False"""
        if self._busy:
            messagebox.showinfo("提示", "有操作正在进行，请等待完成或中断后再试。")
            return False
        return True

    # ================================================================
    # 进度队列轮询
    # ================================================================

    def _poll_progress_queue(self):
        try:
            while True:
                msg = self._progress_queue.get_nowait()
                try:
                    self._handle_progress(msg)
                except Exception:
                    logger.exception("处理进度消息失败")
        except queue.Empty:
            pass
        self._sync_selected_count()
        self.root.after(100, self._poll_progress_queue)

    def _handle_progress(self, msg: tuple):
        msg_type = msg[0] if msg else None

        if msg_type == "__PROGRESS__":
            _, current, total, succ, fail, fname, error = msg
            self.send_progress.update_progress(current, total)
            self.send_progress.update_stats(succ, fail)
            if error:
                self.send_progress.append_log(f"❌ {fname}: {error}")
            else:
                self.send_progress.append_log(f"✅ {fname}")
            self.send_progress.set_status(f"发送中... {current}/{total}")

        elif msg_type == "__DONE__":
            _, succ, fail, failed_list, all_results = msg
            total = succ + fail
            self._interrupt_poll_active = False
            self._stop_event = None
            self._set_ui_sending(False)
            self.send_progress.set_status("发送完成" if not self._was_interrupted else "已中断")
            self.send_progress.update_progress(total, total)
            failed_names = [r.friend_name for r in failed_list]
            succeeded_names = {f.name for f in self.friend_list._friends
                               if f.name not in set(failed_names)}
            self.friend_list.set_checked_by_names(succeeded_names, False)
            if failed_names:
                self.friend_list.mark_failed(failed_names)
            if not self._was_interrupted:
                dialog = ResultDialog(self.root)
                dialog.show_result(total, succ, fail, all_results)
            else:
                dialog = ResultDialog(self.root)
                dialog.title("发送结果 - 已中断")
                dialog.show_result(total, succ, fail, all_results)
            # 注入标签回调（选中联系人打标签后刷新主窗口）
            if self._friend_service:
                dialog.set_tag_callback(
                    lambda name, tag: self._handle_set_tag(name, tag))

        elif msg_type == "__LOG__":
            _, text = msg
            self.send_progress.append_log(text)

        elif msg_type == "__INTERRUPT_OFF__":
            self._interrupt_poll_active = False
            self._stop_event = None

        elif msg_type == "__SCAN_DONE_FOCUS__":
            _, page_count = msg
            # 截图完成 → 关闭鼠标中断，保留 _stop_event 给终止按钮
            self._interrupt_poll_active = False
            self.root.lift()
            self.root.focus_force()
            self.send_progress.set_status(f"扫描完成 {page_count} 页，正在后台 OCR...")
            self.send_progress.set_running(True)

        elif msg_type == "__IMPORT_CONFIRM__":
            _, names = msg
            from src.ui.confirm_dialog import ConfirmDialog
            dlg = ConfirmDialog(self.root, "确认导入联系人", names, checked=True)
            def _import_selected(indices):
                selected = [names[i] for i in indices]
                if selected and self._friend_service:
                    self._friend_service.import_names(selected)
                    self.send_progress.append_log(f"已导入 {len(selected)} 个联系人")
                    self._apply_filter()
            dlg.set_on_confirm(_import_selected)

        elif msg_type == "__NAME_CHECK_DONE__":
            diffs, failed = {}, {}
            if len(msg) >= 3:
                diffs, failed = msg[1], msg[2]
            elif len(msg) == 2:
                diffs = msg[1]
            self._interrupt_poll_active = False
            self._stop_event = None
            self._set_busy(False)
            self.send_progress.set_status("就绪")
            self.send_progress.set_running(False)
            self.friend_list.mark_failed(failed)
            self._apply_filter()
            self.root.lift()
            self.root.focus_force()
            if not self._was_interrupted:
                if not diffs:
                    if failed:
                        failed_count = len(failed)
                        diff_count = len([n for n, r in failed.items() if "expected" in r])
                        search_count = failed_count - diff_count
                        messagebox.showinfo("检查完成",
                            f"检查完成。\n"
                            f"搜索失败: {search_count} 人\n"
                            f"名字不完整: {diff_count} 人")
                    else:
                        messagebox.showinfo("检查完成", "全部名称完整，操作完成。")
                else:
                    from src.ui.name_check_dialog import NameCheckDialog
                    dialog = NameCheckDialog(self.root, diffs)
                    dialog.set_on_confirm(self._apply_name_fixes)

    # ================================================================
    # 辅助
    # ================================================================

    def _apply_name_fixes(self, fixes: dict[str, str]):
        """用户确认补全 → 批量重命名"""
        if not self._friend_service:
            return
        for old, new in fixes.items():
            self._friend_service.rename_friend(old, new)
            logger.info("名字补全: '%s' → '%s'", old, new)
        self._apply_filter()

    def _sync_selected_count(self):
        count = self.friend_list.get_selected_count()
        self.message_editor.set_selected_count(count)

    def _on_log_message(self, text: str):
        if any(level in text for level in ("[INFO", "[WARNING", "[ERROR")):
            self._progress_queue.put(("__LOG__", text))

    def _show_startup_hints(self):
        """读取 startup.txt 并输出到日志窗口"""
        hint_path = Path(__file__).resolve().parent.parent.parent / "startup.txt"
        try:
            if hint_path.exists():
                text = hint_path.read_text(encoding="utf-8").strip()
                if text:
                    self.send_progress.append_log("── 启动提示 ──")
                    for line in text.splitlines():
                        line = line.strip()
                        if line:
                            self.send_progress.append_log(f"  {line}")
                    self.send_progress.append_log("──────────────")
        except Exception:
            pass

    def run(self):
        """运行主窗口 mainloop；窗口被销毁后返回切换请求（None=退出）"""
        self.root.mainloop()
        return getattr(self, "_mode_request", None)
