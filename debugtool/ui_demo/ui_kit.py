"""集中绘制层（ui_kit）：样式 + 间距常量 + 控件工厂 + Spacer + 窗口默认

半集中布局方案的核心：
- 所有样式参数（间距 / 字号 / 控件宽度 / 配色）在这里定义，组件不再手写魔法数字
- 组件文件只保留结构（有哪些控件、命令绑定），样式一律从本模块取

调整整体风格只改这一个文件。**纯标准库（tkinter/ttk），零第三方依赖**——
别人克隆项目即可运行，不需要额外安装任何包。
"""

import tkinter as tk
from tkinter import ttk
from typing import Iterable, Optional

# ================================================================
# 全局间距常量 —— 想调整整体密度，只改这里
# ================================================================

PAD_XS = 2    # 极窄：图标间距、内边距
PAD_S = 4     # 窄：同排相邻控件
PAD_M = 8     # 中：行间距、分组间距、与窗口边缘
PAD_L = 12    # 宽：分组之间
PAD_XL = 20   # 极宽：强调间隔（如状态文字前）

# ================================================================
# 窗口默认
# ================================================================

WIN_MIN_W = 880   # 最小宽度：保证所有横排控件不折叠（见布局铁律）
WIN_MIN_H = 560
WIN_W = 1080      # 初始宽度
WIN_H = 680

# ================================================================
# 控件默认
# ================================================================

FONT_SIZE = 10                     # 默认字号
FONT_FAMILY = "Microsoft YaHei"    # 默认字体（Windows 中文字体）

# 简洁配色（clam 主题；想换配色只改这里的色值）
COLOR_PRIMARY = "#0d6efd"   # 主色（蓝）
COLOR_SUCCESS = "#198754"   # 成功（绿）
COLOR_DANGER = "#dc3545"    # 危险（红）
COLOR_MUTED = "#888888"     # 弱化文字（灰）
COLOR_BLOCK = "#eef1f5"     # 浅色背景块（块分区：用背景区分区域，不用分割线）


def configure_style(root: Optional[tk.Tk] = None) -> None:
    """一次性配置全局 ttk 样式：clam 主题 + 命名按钮/标签样式。

    入口调用一次即可。按钮工厂的 variant 参数会映射到这里的命名样式，
    保证全应用同款配色。想换整体风格，改上面的 COLOR_* 常量。
    """
    style = ttk.Style(root)
    style.theme_use("clam")
    style.configure("Primary.TButton", foreground="white", background=COLOR_PRIMARY)
    style.configure("Success.TButton", foreground="white", background=COLOR_SUCCESS)
    style.configure("Danger.TButton", foreground="white", background=COLOR_DANGER)
    style.configure("Muted.TLabel", foreground=COLOR_MUTED)
    style.configure("Block.TFrame", background=COLOR_BLOCK)


def make_button(parent, text: str, width: int = 0, variant: str = "",
                command=None, font=None) -> ttk.Button:
    """统一按钮工厂。

    Args:
        parent:   父容器
        text:     按钮文字
        width:    字符宽（0 = 自适应内容）
        variant:  配色：""（默认）/ primary / success / danger
        command:  点击回调
        font:     字体元组，如 ("Microsoft YaHei", 10)；None = 默认
    """
    style = f"{variant.title()}.TButton" if variant else None
    return ttk.Button(parent, text=text, width=width, style=style,
                      command=command, font=font)


def make_label(parent, text: str, muted: bool = False,
               anchor: str = "w", font=None, **kw) -> ttk.Label:
    """统一标签工厂。muted=True 用灰色（提示性文字）"""
    style = "Muted.TLabel" if muted else None
    return ttk.Label(parent, text=text, style=style, anchor=anchor,
                     font=font, **kw)


def make_combo(parent, values: Iterable[str], width: int = 10,
               state: str = "readonly", **kw) -> ttk.Combobox:
    """统一下拉框工厂"""
    return ttk.Combobox(parent, values=list(values), width=width, state=state, **kw)


def make_block(parent, **kw) -> ttk.Frame:
    """浅色背景块（块分区）：用背景色区分区域，不用分割线。

    用法：把一块内容的 Frame 用 make_block 创建，配色由 configure_style 的
    Block.TFrame 统一控制。块之间靠大间距（PAD_XL）自然分隔。
    """
    return ttk.Frame(parent, style="Block.TFrame", **kw)


class Spacer(ttk.Frame):
    """弹性占位：吸收多余空间，让两侧固定控件永远贴边、不互相挤压。

    这是防"按钮/文字折叠"的关键 —— tkinter 的 pack 在容器变窄时会把
    固定宽度控件压扁到 0（文字截断、不换行），弹性区能吸收这部分挤压。

    用法（每个横排行必备）：
        btn_left.pack(side="left")
        Spacer(self).pack(side="left", fill="x", expand=True)   # 弹性区
        btn_right.pack(side="right")
    """

    def __init__(self, parent, *args, **kw):
        super().__init__(parent, *args, **kw)


def window_defaults(root: tk.Tk, title: str,
                    size: Optional[tuple[int, int]] = None) -> None:
    """窗口通用配置：标题 + 初始尺寸 + 最小尺寸 + 居中。

    minsize 必须设 —— 否则用户把窗口拖到按钮总宽以下，横排控件会折叠。
    """
    w, h = size or (WIN_W, WIN_H)
    root.title(title)
    root.geometry(f"{w}x{h}")
    root.minsize(WIN_MIN_W, WIN_MIN_H)
    root.update_idletasks()
    # 居中显示
    x = (root.winfo_screenwidth() - w) // 2
    y = (root.winfo_screenheight() - h) // 2
    root.geometry(f"{w}x{h}+{x}+{y}")
