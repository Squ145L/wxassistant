"""发送进度条 + 控制按钮 + 日志面板（浅色背景块）"""

import tkinter as tk
from tkinter import ttk
from typing import Callable, Optional

from src.ui import ui_kit


class SendProgress(ttk.Frame):
    """底部控制区（浅色背景块）

    布局自上而下：开始/终止按钮行（含统计/状态）→ 进度条 → 日志文本框。
    """

    def __init__(self, parent: tk.Widget):
        super().__init__(parent, style="Block.TFrame", padding=ui_kit.PAD_M)
        self._on_start: Optional[Callable[[], None]] = None
        self._on_stop: Optional[Callable[[], None]] = None
        self._running: bool = False   # 是否处于运行态（供 set_paused 恢复按钮文案）
        self._build_ui()

    def _build_ui(self):
        # === 统计 + 按钮行（置顶）===
        ctrl_frame = ttk.Frame(self)
        ctrl_frame.pack(fill=tk.X, pady=(0, ui_kit.PAD_XS))

        # 统计标签
        stats = ttk.Frame(ctrl_frame)
        stats.pack(side=tk.LEFT)

        self._label_success = ttk.Label(stats, text="✅ 0", foreground="green")
        self._label_success.pack(side=tk.LEFT, padx=(0, ui_kit.PAD_L))

        self._label_failed = ttk.Label(stats, text="❌ 0", foreground="red")
        self._label_failed.pack(side=tk.LEFT)

        # 状态标签
        self._status_var = tk.StringVar(value="就绪")
        self._status_label = ttk.Label(
            ctrl_frame,
            textvariable=self._status_var,
            foreground="gray",
        )
        self._status_label.pack(side=tk.LEFT, padx=(ui_kit.PAD_XL, 0))

        # 弹性区：统计/状态 与 按钮 之间，防折叠（布局铁律 1）
        ui_kit.Spacer(ctrl_frame).pack(side=tk.LEFT, fill=tk.X, expand=True)

        # 按钮（开始群发 最右，终止 在左）
        btn_frame = ttk.Frame(ctrl_frame)
        btn_frame.pack(side=tk.RIGHT)

        self._btn_stop = ui_kit.make_button(
            btn_frame, "⏹ 终止", 0, variant="danger",
            command=self._on_stop_clicked,
        )
        self._btn_stop.pack(side=tk.RIGHT, padx=(ui_kit.PAD_S, 0))
        self._btn_stop.config(state=tk.DISABLED)

        self._btn_start = ui_kit.make_button(
            btn_frame, "▶ 开始群发", 0, variant="success",
            command=self._on_start_clicked,
        )
        self._btn_start.pack(side=tk.RIGHT)

        # === 进度条（在开始群发按钮下方）===
        bar_frame = ttk.Frame(self)
        bar_frame.pack(fill=tk.X, pady=(ui_kit.PAD_XS, ui_kit.PAD_S))

        self._progress = ttk.Progressbar(
            bar_frame,
            mode="determinate",
            maximum=100,
        )
        self._progress.pack(side=tk.LEFT, fill=tk.X, expand=True)

        self._progress_label = ttk.Label(
            bar_frame,
            text="0/0",
            width=8,
            anchor=tk.CENTER,
        )
        self._progress_label.pack(side=tk.RIGHT, padx=(ui_kit.PAD_M, 0))

        # === 日志面板 ===
        log_frame = ttk.LabelFrame(self, text="发送日志", padding=ui_kit.PAD_S)
        log_frame.pack(fill=tk.BOTH, expand=True, pady=(ui_kit.PAD_M, 0))

        self._log_text = tk.Text(
            log_frame,
            height=4,
            font=("Consolas", 9),
            wrap=tk.WORD,
            state=tk.DISABLED,
        )
        log_scroll = ttk.Scrollbar(log_frame, orient=tk.VERTICAL, command=self._log_text.yview)
        self._log_text.configure(yscrollcommand=log_scroll.set)
        self._log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        log_scroll.pack(side=tk.RIGHT, fill=tk.Y)

    # ================================================================
    # 公开接口
    # ================================================================

    def set_callbacks(
        self,
        on_start: Callable[[], None],
        on_stop: Callable[[], None],
    ):
        """设置开始/终止回调"""
        self._on_start = on_start
        self._on_stop = on_stop

    def set_running(self, running: bool):
        """切换运行/就绪状态"""
        self._running = running
        if running:
            self._btn_start.config(state=tk.DISABLED)
            self._btn_stop.config(state=tk.NORMAL)
            self._status_var.set("发送中...")
        else:
            self._btn_start.config(state=tk.NORMAL)
            self._btn_stop.config(state=tk.DISABLED)
            self._status_var.set("就绪")

    def set_paused(self, paused: bool):
        """暂停/恢复状态：暂停时开始钮变「▶ 继续」且可点；恢复后按 _running 回位。"""
        if paused:
            self._btn_start.config(text="▶ 继续", state=tk.NORMAL)
            self._status_var.set("已暂停")
        elif self._running:
            self._btn_start.config(text="▶ 开始群发", state=tk.DISABLED)
            self._status_var.set("发送中...")
        else:
            self._btn_start.config(text="▶ 开始群发", state=tk.NORMAL)
            self._status_var.set("就绪")

    def set_terminate_available(self, available: bool):
        """只开关 ⏹ 终止按钮（名字检查等不改状态字的流程用）"""
        self._btn_stop.config(state=tk.NORMAL if available else tk.DISABLED)

    def update_progress(self, current: int, total: int):
        """更新进度条"""
        if total > 0:
            pct = int(current / total * 100)
            self._progress.config(value=pct)
            self._progress_label.config(text=f"{current}/{total}")

    def update_stats(self, success: int, failed: int):
        """更新成功/失败计数"""
        self._label_success.config(text=f"✅ {success}")
        self._label_failed.config(text=f"❌ {failed}")

    def set_status(self, text: str):
        """更新状态文字"""
        self._status_var.set(text)

    def append_log(self, message: str):
        """在日志面板追加一行"""
        self._log_text.config(state=tk.NORMAL)
        self._log_text.insert(tk.END, message + "\n")
        self._log_text.see(tk.END)
        self._log_text.config(state=tk.DISABLED)

    def clear_log(self):
        """清空日志面板"""
        self._log_text.config(state=tk.NORMAL)
        self._log_text.delete("1.0", tk.END)
        self._log_text.config(state=tk.DISABLED)

    def reset(self):
        """重置所有状态"""
        self._running = False
        self._progress.config(value=0)
        self._progress_label.config(text="0/0")
        self._label_success.config(text="✅ 0")
        self._label_failed.config(text="❌ 0")
        self._status_var.set("就绪")
        self._btn_start.config(text="▶ 开始群发", state=tk.NORMAL)
        self._btn_stop.config(state=tk.DISABLED)

    # ================================================================
    # 内部
    # ================================================================

    def _on_start_clicked(self):
        if self._on_start:
            self._on_start()

    def _on_stop_clicked(self):
        if self._on_stop:
            self._on_stop()
