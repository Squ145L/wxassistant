"""交互式 UI 布局 Demo —— 验证"半集中 + 弹性布局 + 块分区"方案（原生 tkinter，零依赖）

运行：python debugtool/ui_demo/demo.py

布局要点（新布局）：
- 顶栏变轻：左上角【分组菜单按钮】(联系人/标签)，右侧只留 刷新/设置/帮助
- 操作下沉：搜索/筛选/全选 内嵌在好友列表块的顶部，不占顶栏
- 块分区：主体用【浅色背景块】区分（列表块 / 编辑块 / 底部进度块），不用分割线
- 搜索框：固定宽度（默认 ≈12 汉字），不自适应拉伸，弹性由 Spacer 承担

左侧参数面板实时调：主题 / 间距 / 按钮宽 / 字号 / 搜索框宽 / 弹性区开关。
重点实验：把窗口拖窄，对比 [顶栏弹性区] 开 / 关 的效果。

改动说明：所有参数在左侧面板调，或改本文件顶部 / ui_kit.py 常量。
依赖：无（仅标准库 tkinter/ttk）。
"""

# ⚠️ 必须在所有 import 之前：声明 DPI 感知，防止高 DPI 屏幕布局错位
import ctypes as _ctypes
try:
    _ctypes.windll.shcore.SetProcessDpiAwareness(2)  # Per-Monitor DPI Aware
except Exception:
    try:
        _ctypes.windll.user32.SetProcessDPIAware()    # 旧版 API fallback
    except Exception:
        pass

import tkinter as tk
from tkinter import ttk
from typing import Optional

import ui_kit as kit

# ================================================================
# 可用主题（tkinter 内置，可任选；clam 是自定义配色依赖的主题）
# ================================================================

THEMES = ["clam", "alt", "vista", "xpnative"]

SEARCH_DEFAULT_WIDTH = 16   # 搜索框默认宽度（字符）≈ 8 个汉字（固定，不随窗口伸缩）


class DemoApp:
    """交互式布局 Demo：参数面板（左） + 新布局预览（右）"""

    def __init__(self):
        self.root = tk.Tk()
        kit.configure_style(self.root)
        kit.window_defaults(self.root, "UI 布局 Demo")

        # ---- 布局参数（面板 / 滑杆改动后读到这里）----
        self.pad = tk.DoubleVar(value=kit.PAD_S)            # 基础间距 px
        self.btn_w = tk.IntVar(value=4)                     # 按钮字符宽
        self.font = tk.IntVar(value=kit.FONT_SIZE)          # 字号
        self.search_w = tk.IntVar(value=SEARCH_DEFAULT_WIDTH)  # 搜索框宽度（字符）
        self.use_spacer = tk.BooleanVar(value=True)         # 顶栏弹性区开关
        self.theme = tk.StringVar(value="clam")             # 主题名

        self._preview_frame: Optional[ttk.Frame] = None
        self._build_panel()
        self._on_rebuild()   # 首次构建预览

    # ================================================================
    # 参数面板（左）
    # ================================================================

    def _build_panel(self):
        panel = ttk.Frame(self.root, padding=kit.PAD_M)
        panel.pack(side="left", fill="y")
        ttk.Label(panel, text="参数面板", font=("", 11, "bold")
                  ).pack(anchor="w", pady=(0, kit.PAD_M))

        def _row(title, widget):
            """一行：标题在上，控件在下（fill=x 铺满面板宽）"""
            ttk.Label(panel, text=title).pack(anchor="w", pady=(kit.PAD_M, 0))
            widget.pack(fill="x")

        # --- 主题 ---
        theme_cb = kit.make_combo(panel, THEMES, width=12)
        theme_cb.configure(textvariable=self.theme)
        theme_cb.bind("<<ComboboxSelected>>", self._on_rebuild)
        _row("主题", theme_cb)

        # --- 基础间距 ---
        scale = ttk.Scale(panel, from_=0, to=20,
                          variable=self.pad, command=self._on_rebuild)
        _row("基础间距 px", scale)
        self._pad_label = kit.make_label(panel, "", muted=True)
        self._pad_label.pack(anchor="e")

        # --- 按钮字符宽 ---
        scale = ttk.Scale(panel, from_=0, to=12,
                          variable=self.btn_w, command=self._on_rebuild)
        _row("按钮字符宽", scale)
        self._btnw_label = kit.make_label(panel, "", muted=True)
        self._btnw_label.pack(anchor="e")

        # --- 字号 ---
        scale = ttk.Scale(panel, from_=6, to=18,
                          variable=self.font, command=self._on_rebuild)
        _row("字号", scale)
        self._font_label = kit.make_label(panel, "", muted=True)
        self._font_label.pack(anchor="e")

        # --- 搜索框宽度 ---
        scale = ttk.Scale(panel, from_=6, to=40,
                          variable=self.search_w, command=self._on_rebuild)
        _row("搜索框宽 (字符)", scale)
        self._searchw_label = kit.make_label(panel, "", muted=True)
        self._searchw_label.pack(anchor="e")

        # --- 弹性区开关 ---
        ttk.Checkbutton(panel, text="顶栏弹性区 (Spacer)",
                        variable=self.use_spacer, command=self._on_rebuild
                        ).pack(anchor="w", pady=(kit.PAD_M, 0))

        ttk.Label(panel, text="").pack(pady=4)     # 纯留白间隔，不用分割线

        kit.make_label(
            panel,
            "把窗口拖窄，对比弹性区\n"
            "开关的效果：关闭后顶栏\n"
            "按钮互相挤压、文字截断\n"
            "（即当前主程序的问题）。",
            muted=True, font=("", 9),
        ).pack(anchor="w")

    # ================================================================
    # 参数变化 → 重建预览（读最新参数）
    # ================================================================

    def _on_rebuild(self, *_):
        """任何参数变化都会走到这里：切主题 + 销毁旧预览 + 重建"""
        ttk.Style(self.root).theme_use(self.theme.get())
        self._pad_label.config(text=f"当前: {self._pad()}px")
        self._btnw_label.config(text=f"当前: {self.btn_w.get()}")
        self._font_label.config(text=f"当前: {self.font.get()}")
        self._searchw_label.config(
            text=f"当前: {self.search_w.get()} (≈{self.search_w.get() // 2}汉字)")
        if self._preview_frame is not None:
            self._preview_frame.destroy()
        self._build_preview()

    # ================================================================
    # 预览区（右）—— 新布局
    # ================================================================

    def _build_preview(self):
        p = self._pad()
        self._preview_frame = ttk.Frame(
            self.root, padding=(0, p, p, p))
        self._preview_frame.pack(side="left", fill="both", expand=True)

        self._build_top_bar()   # 顶栏：分组菜单 + 账户 + 右侧
        self._build_body()      # 主体：左右浅色背景块
        self._build_bottom()    # 底部进度块

    def _pad(self) -> int:
        """当前基础间距（px），布局里所有 padx/pady 都从这里取"""
        return int(self.pad.get())

    def _font(self):
        """当前字号字体"""
        return (kit.FONT_FAMILY, self.font.get())

    def _build_top_bar(self):
        """顶栏：左上角分组菜单按钮（联系人/标签）+ 账户 + 弹性区 + 右侧按钮"""
        p = self._pad()
        bar = ttk.Frame(self._preview_frame)
        bar.pack(fill="x", pady=(0, p))

        # 左上角：分组菜单按钮（Menubutton，点击展开子菜单）
        btn_contacts = ttk.Menubutton(bar, text="联系人")
        m = tk.Menu(btn_contacts, tearoff=0)
        m.add_command(label="检查选中名称")
        m.add_command(label="扫描并导入")
        m.add_command(label="搜索并导入")
        m.add_command(label="导出选中...")
        btn_contacts["menu"] = m
        btn_contacts.pack(side="left")

        btn_tags = ttk.Menubutton(bar, text="标签")
        m2 = tk.Menu(btn_tags, tearoff=0)
        m2.add_command(label="添加标签")
        m2.add_command(label="清除标签")
        btn_tags["menu"] = m2
        btn_tags.pack(side="left", padx=(p, 0))

        # 账户下拉
        kit.make_label(bar, "账户:").pack(side="left", padx=(p, 0))
        kit.make_combo(bar, ["账户1", "账户2"], width=8).pack(
            side="left", padx=(0, p))

        # 弹性区：开关关掉时，右侧按钮会向左挤压直到重叠（演示折叠）
        if self.use_spacer.get():
            kit.Spacer(bar).pack(side="left", fill="x", expand=True)

        # 右侧：固定按钮（只留最常用的）
        kit.make_button(bar, "刷新", self.btn_w.get()).pack(side="right")
        kit.make_button(bar, "设置", self.btn_w.get()).pack(
            side="right", padx=(p, 0))
        kit.make_button(bar, "帮助", self.btn_w.get()).pack(
            side="right", padx=(p, 0))

    def _build_body(self):
        """主体：左右两个浅色背景块（块分区，无分割线）"""
        p = self._pad()
        # 经典 tk.PanedWindow（无 sashrelief = 无分割线），可拖分栏，pane 有 minsize
        paned = tk.PanedWindow(self._preview_frame, orient="horizontal")
        paned.pack(fill="both", expand=True, pady=(0, p))

        # ---- 左块：好友列表（浅色背景 + 内嵌操作行）----
        left = kit.make_block(paned, width=240)
        self._build_list_ops(left)   # 顶部：搜索/筛选行
        tree = ttk.Treeview(left, show="tree", height=14)
        tree.pack(fill="both", expand=True, padx=(p, p), pady=p)
        for i in range(24):
            tree.insert("", "end", text=f"25级李华{i}")
        self._build_list_actions(left)   # 底部：全选/反选行（拆两行，每行固定宽 < minsize）
        # minsize 必须 ≥ 所有横排固定控件总宽的最大值（实测底部行 358px），
        # 留余量取 380，否则缩窗截断（§6 第 6 条）
        paned.add(left, minsize=380)

        # ---- 右块：消息编辑区（浅色背景）----
        right = kit.make_block(paned, width=320)
        tk.Text(right, height=8, font=("Microsoft YaHei", self.font.get()),
                wrap="word").pack(fill="both", expand=True,
                                  padx=(p, p), pady=(p, p))
        paned.add(right, minsize=260)

    def _build_list_ops(self, parent):
        """列表顶部操作行：搜索框(固定≈8汉字) + 正则 + 标签筛选

        搜索框固定宽度（不自适应拉伸），弹性由 Spacer 承担。
        注意：固定控件不能太多挤一行（会超 pane minsize 导致折叠，见 §6 第 6 条）。
        """
        p = self._pad()
        bar = ttk.Frame(parent)
        bar.pack(fill="x", padx=(p, p), pady=(p, 0))

        ttk.Entry(bar, width=self.search_w.get()).pack(side="left")
        ttk.Checkbutton(bar, text=".*").pack(side="left", padx=(p, 0))
        kit.make_combo(bar, ["全部", "A组", "B组"], width=6).pack(
            side="left", padx=(p, 0))
        kit.Spacer(bar).pack(side="left", fill="x", expand=True)  # 弹性由 Spacer 承担

    def _build_list_actions(self, parent):
        """列表底部操作行：全选 / 反选（单独一行，防与顶部挤在一行超宽折叠）"""
        p = self._pad()
        bar = ttk.Frame(parent)
        bar.pack(fill="x", padx=(p, p), pady=(0, p))

        kit.make_label(bar, "共 24 人", muted=True).pack(side="left")
        kit.Spacer(bar).pack(side="left", fill="x", expand=True)

        ttk.Button(bar, text="全选").pack(side="right")
        ttk.Button(bar, text="反选").pack(side="right", padx=(p, 0))

    def _build_bottom(self):
        """底部进度块（浅色背景）"""
        p = self._pad()
        block = kit.make_block(self._preview_frame)
        block.pack(fill="x")

        ttk.Progressbar(block, maximum=100, value=35).pack(
            side="left", fill="x", expand=True, padx=(p, p), pady=p)
        kit.make_label(block, "3/8", muted=True).pack(side="left", pady=p)
        kit.make_label(block, "✅ 2  ❌ 1", muted=False).pack(
            side="left", padx=(p, 0), pady=p)
        kit.Spacer(block).pack(side="left", fill="x", expand=True)

        kit.make_button(block, "⏹ 终止", 0, variant="danger").pack(
            side="right", padx=(0, p), pady=p)
        kit.make_button(block, "▶ 开始群发", 0, variant="success").pack(
            side="right", padx=(0, p), pady=p)


def main():
    app = DemoApp()
    app.root.mainloop()


if __name__ == "__main__":
    main()
