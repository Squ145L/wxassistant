# UI 布局 Demo（ttkbootstrap）

交互式验证"**半集中 + 弹性布局 + ttkbootstrap 主题**"方案的参考实现，也是主程序 UI 重构的模板。

## 为什么有这个 Demo

主程序（`src/ui/`）当前的 UI 问题是：水平调整窗口大小时，顶栏按钮 / 文字会互相挤压、截断（"折叠"）。根因是**横排的固定宽度控件之间没有弹性区**，且无窗口最小宽度约束（详见 `.omc/CODING_STANDARDS.md` §6）。

这个 Demo 让你在**不动主程序**的前提下，可视化验证修复方案：左侧调参数，右侧是复刻主程序骨架的预览区。

## 依赖

**无** —— 纯标准库（tkinter / ttk）。别人克隆项目即可运行，不需要安装任何额外包。

## 运行

```powershell
python debugtool/ui_demo/demo.py
```

## 调参方式（两种）

### 1. 运行后面板实时调
| 参数 | 作用 | 建议实验 |
|---|---|---|
| 主题 | 切换整套配色（litera/flatly/darkly/…） | 深色系试试 superhero |
| 基础间距 px | 全局行距 / 控件间距密度 | 拉到 0 看最紧状态 |
| 按钮字符宽 | 顶栏按钮宽度 | 0 时按钮自适应文字 |
| 字号 | 全局字体大小 | |
| 顶栏弹性区 (Spacer) | 开/关顶栏弹性占位 | **把窗口拖窄，对比开关效果** |

### 2. 改代码常量
- `ui_kit.py` 顶部：`PAD_*` 间距、`WIN_MIN_W/H` 窗口最小/初始尺寸、`FONT_SIZE/FONT_FAMILY` 字号字体 —— 全局生效
- `demo.py` 顶部：`THEMES` 可选主题列表

每个常量/参数旁都有中文注释。

## 目录结构

```
debugtool/ui_demo/
├── README.md     # 本文件
├── ui_kit.py     # 集中绘制层（可复制的参考实现）
└── demo.py       # 入口：参数面板 + 主程序骨架预览
```

## 迁移到主程序（后续步骤，等 phase-1 交付后做）

1. 把 `ui_kit.py` 复制到 `src/ui/ui_kit.py`
2. `main_window.py` 入口：`tk.Tk()` 后调 `ui_kit.configure_style(root)` + `ui_kit.window_defaults(root, …)`（minsize + 初始尺寸 + 配色）
3. 各组件 `_build_ui` 改走 `ui_kit` 工厂 + `Spacer`，删掉手写 `padx=4/6/8` 魔法数字
4. 按 `.omc/CODING_STANDARDS.md` §6 的布局铁律逐组件过一遍

## 注意

- Demo 与主程序完全解耦，**不会影响正在执行的 phase-1 分支**
- `demo.py` 顶部有 DPI 声明（与主程序 `main.py` 一致），高 DPI 屏布局不错位
