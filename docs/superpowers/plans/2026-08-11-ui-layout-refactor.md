# UI 布局重构计划（原生 tkinter · 半集中 · 块分区）

> **For agentic workers:** 实施前先跑 `debugtool/ui_demo/demo.py` 验证布局效果。
> 规范依据：`.omc/CODING_STANDARDS.md` §6（布局铁律 1-6）。

**Goal:** 消灭"任何控件被折叠/截断"（横排挤压 / 窗口缩小 / sash 拖动 / 固定控件超宽），顶栏变轻、操作下沉、块分区，视觉有层次。纯标准库，零新增依赖。

**Demo:** `debugtool/ui_demo/`（`ui_kit.py` 集中绘制层 + `demo.py` 交互预览）已冒烟通过，作为迁移的参考模板。

---

## 布局决策（已与用户确认）

| # | 决策 | 实现 |
|---|------|------|
| 1 | 顶栏变轻：左上角**分组菜单按钮** | `ttk.Menubutton`（联系人→检查/扫描/搜索/导出；标签→添加/清除），右侧只留 刷新/设置/帮助 |
| 2 | **搜索/筛选/全选 下沉** | 内嵌到好友列表块顶部（不占顶栏）：`搜索框 | .* | 标签▾ | (Spacer) | 全选 | 反选` |
| 3 | **块分区，去分割线** | 主体用浅色背景块 `Block.TFrame`（列表块 / 编辑块 / 底部进度块），`tk.PanedWindow` 不带 `sashrelief`，不用 `Separator` |
| 4 | 搜索框**固定 ≈8 汉字** | `Entry width=16`，不自适应拉伸，弹性全由独立 `Spacer` 承担 |
| 5 | **主题设置** | UI 提供主题切换（`ttk.Style.theme_use`，clam/alt/vista/xpnative） |
| 6 | **硬约束：每个控件不可折叠** | 任何横排固定控件总宽 < 容器 `minsize`（见下） |

## 布局图

```
[联系人▾ 标签▾]  [账户:▾]              [刷新][设置][帮助]      ← 顶栏（轻）
┌──────────────────────────────────────────────────────┐
│▉ 列表块: [搜索框8字][.*][标签▾]    [全选][反选]      │  ← 操作行内嵌
│▉         25级李华0 ...                               │
│▉ 编辑块: 消息模板 Text                               │
├──────────────────────────────────────────────────────┤
│▉ 进度块: [进度条] 3/8 ✅2 ❌1  [▶开始][⏹终止]       │
└──────────────────────────────────────────────────────┘
```

## 关键参数（minsize 计算依据）

| 项 | 值 | 依据 |
|---|---|---|
| 搜索框 | `width=16`（≈8 汉字） | 固定，不随窗口伸缩 |
| 左 pane（列表块）minsize | **380** | 必须 ≥ 各横排固定控件总宽的最大值（实测：顶部搜索行 313 / 底部全选反选行 358），留余量取 380 |
| 右 pane（编辑块）minsize | 260 | 编辑区文字可读下限 |
| 窗口 minsize | `WIN_MIN_W=880` | ≥ 参数面板 + 左 pane 380 + 右 pane 260 + 边距 |
| 可拖分栏 | 经典 `tk.PanedWindow` | `ttk.Panedwindow.add` 不支持 `minsize`（§6 第 5 条） |

> ⚠️ 字号调大（demo 滑杆）时固定控件会变宽，需同步加大对应 minsize——这是 §6 第 6 条的动态约束。

## 迁移步骤（等 phase-1 交付后执行）

1. 把 `ui_kit.py` 复制到 `src/ui/ui_kit.py`
2. `main_window.py` 入口：`tk.Tk()` 后调 `ui_kit.configure_style(root)` + `ui_kit.window_defaults(root, …)`（minsize + 初始尺寸 + 配色）
3. 顶栏：改成 分组菜单按钮（联系人/标签）+ 账户 + Spacer + 刷新/设置/帮助；删掉 `top_bar.py` 里不再用的按钮
4. 搜索/筛选/全选 从 `filter_bar.py` 下沉到 `friend_list.py` 块顶部内嵌；搜索框固定 `width=16`
5. 主体：`main_window.py` 用 `tk.PanedWindow`（无 sashrelief），左右 `make_block` 浅色块，pane 加 minsize（360 / 260）
6. 底部 `send_progress.py` 用 `make_block`
7. 主题设置入口：设置页加主题下拉（`ttk.Style.theme_use`）
8. 清理：删掉各组件手写 `padx=4/6/8` 魔法数字，改走 `ui_kit`

## 验证清单（每项都要过）

- [ ] `python debugtool/ui_demo/demo.py` 拖窄窗口到 minsize：顶栏 / 操作行 / 底部 **无任何控件截断**
- [ ] 全选 / 反选在 pane minsize(380) 下完整可见
- [ ] 搜索框固定 8 汉字宽，窗口拉伸不变形
- [ ] sash 拖动不把 pane 拖到内容截断
- [ ] 主题切换（clam/alt/vista）即时生效
- [ ] 每个横排固定控件总宽 < 容器 minsize（§6 第 6 条）
- [ ] 主程序迁移后重复以上验证 + 真实多开场景
