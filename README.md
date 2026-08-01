# 微信助手 - 群发工具

微信 PC 版群发工具，基于 UIA SendKeys + RapidOCR + tkinter。

## 快速开始

```powershell
pip install -r requirements.txt
python main.py
```

## 项目结构

```
wxassistant/
├── main.py                      # CLI 入口
├── requirements.txt             # 依赖
├── README.md
│
├── OCR/                         # 独立 OCR 模块（可复制到其他项目使用）
│   ├── __init__.py              # from OCR import OCREngine
│   ├── engine.py                # RapidOCR 封装 + 混淆字符归一化
│   ├── ocr_confusion.json       # OCR 字符混淆映射（可外置编辑）
│   └── models/                  # 本地模型目录（.onnx 自动加载）
│
├── calibrate_ocr.py             # OCR 校准工具
│
├── debugtool/
│   └── mouse_tracker.py         # 鼠标坐标查看器（百分比 + 窗口信息）
│
├── src/
│   ├── app.py                   # 启动 + 测试命令
│   ├── operations.py            # 后台操作回调（发送/检查/搜索/导入）
│   │
│   ├── driver/
│   │   └── wechat_bridge.py     # 窗口查找/激活、UIA SendKeys、鼠标、截图、OCR 验证
│   │
│   ├── services/
│   │   ├── friend_service.py    # 好友 CRUD + JSON 持久化 + 标签 + 筛选
│   │   ├── template_engine.py   # [name] [$1] 模板替换
│   │   └── send_service.py      # 间隔控制 + 中断 + 进度回调
│   │
│   ├── ui/
│   │   ├── main_window.py       # 主窗口：布局 + 组件联动 + 后台线程
│   │   ├── filter_bar.py        # 筛选栏 + OCR 菜单 + 标签筛选 + 刷新
│   │   ├── friend_list.py       # 好友列表（复选框/标签列/右键菜单）
│   │   ├── message_editor.py    # 消息模板 + 附件
│   │   ├── send_progress.py     # 进度条 + 停止按钮 + 日志面板
│   │   ├── result_dialog.py     # 发送结果弹窗
│   │   ├── settings_dialog.py   # 设置（常规/OCR/坐标）
│   │   ├── name_check_dialog.py # 名字补全弹窗
│   │   └── confirm_dialog.py    # 可复用确认弹窗
│   │
│   └── utils/
│       ├── config.py            # 全局常量（时序/OCR/UI）
│       ├── coordinates.py       # 坐标管理
│       └── logger.py            # 日志
│
├── cache/
│   ├── friends.json             # 好友缓存（含标签）
│   ├── settings.json            # 设置
│   ├── coordinates.json         # 坐标
│   └── ocr_calibration.json     # OCR 校准参数
│
└── logs/
    └── app.log                  # 运行日志
```

## 架构分层

```
main.py
  ├── src/app.py          → 创建实例 + 注入回调
  ├── src/operations.py   → 后台操作工厂
  ├── ui/                 → tkinter，不导入 driver
  ├── services/           → 纯 Python，不导入 driver/ui
  └── driver/             → Windows API，不导入 ui/services
```

## 核心功能

### 发送流程

```
遍历选中好友:
  1. 渲染模板 [name] → "25级李华同学你好"
  2. bridge.search_contacts(name)     → 激活微信 → Ctrl+F → 粘贴名 → Enter
  3. bridge.match_chat_title(name)     → 截图标题栏 → OCR → 混淆归一化 → 前缀匹配
  4. bridge.send_text_message(msg)     → 剪贴板粘贴 → Enter
  5. bridge.send_file_message(path)    → CF_HDROP 传文件 → Ctrl+V → Enter
  6. sleep(interval ± 30%)             → 反风控间隔
  7. 按键中断 → 立即停止
  8. 失败标红，完成弹窗列出失败名单
```

### 中断机制

- 低级键盘钩子 (`WH_KEYBOARD_LL`) 截获任意按键
- 鼠标 `GetAsyncKeyState` 轮询检测点击
- bridge 模拟输入时自动暂停钩子（`_hook_suspended`），防自触发
- 中断后 `send_one` 各步骤 + bridge 内部 `_should_stop()` 双重检查
- 钩子触发后不卸载，持续监听直到操作结束

### OCR 扫描流程

```
[OCR] → 搜索并导入 / 扫描通讯录并导入:
  截图中 → 鼠标/按键中断有效
  扫描完成 → 鼠标中断关闭，[终止] 按钮亮起
  OCR 中 → 只响应 [终止] 按钮，鼠标/按键无效
  终止 → 保留已扫描结果，丢弃剩余页面
```

### OCR 字符混淆归一化

```
OCR/ocr_confusion.json 配置映射表:
  "-" → "一"     (ASCII连字符 → 汉字一)
  "—" → "一"     (em dash → 汉字一)
  "–" → "一"     (en dash → 汉字一)
  ...

匹配前双方归一化，外置文件可随时编辑。
```

### [OCR] 菜单

```
[OCR校准] 聊天界面标题        → 校准聊天标题栏
检查选中名称是否完整          → 搜索选中好友 → OCR 比对 → 搜索失败/OCR不匹配标红
──────────────
搜索并导入..                 → 弹窗输关键词 → 扫描通讯录并导入
扫描通讯录并导入              → 扫描通讯录并导入全部
[OCR校准] 扫描通讯录并导入    → 校准 contacts_list 区域
[设置] 扫描通讯录并导入       → 设置（页数/滚动高度）
──────────────
帮助...
```

### 标签功能

```
工具栏: [添加标签] [清除标签]  → 批量设置/清除勾选好友标签
右键:  设置标签               → 单个好友标签
筛选:  标签: [全部 ▾]         → 按标签筛选，AND 名字筛选
```

### 刷新按钮

```
[🔄 刷新] → 清除全部红色失败标记 + 重新查找微信窗口（多开切窗用）
```

### 鼠标坐标查看器

```
设置 → 坐标 → [鼠标位置] → 启动坐标查看器
显示: 窗口标题/类名/尺寸 + 百分比坐标
```

## 模板变量

| 变量 | 替换为 |
|------|--------|
| `[name]` | 好友名 |
| `[$1]` `[$2]` | 正则捕获组（需开启正则筛选） |

## 命令行

```powershell
python main.py                  # GUI
python main.py --test-bridge    # 测试微信连接
python main.py --test-ocr       # 测试 OCR
python calibrate_ocr.py --key chat_title    # 校准聊天标题
python calibrate_ocr.py --key contacts_list # 校准通讯录
python debugtool/mouse_tracker.py          # 坐标查看器
```

## 文件存储

| 文件 | 内容 |
|------|------|
| `cache/friends.json` | 好友列表（含标签） |
| `cache/settings.json` | 设置 |
| `cache/coordinates.json` | 坐标 |
| `cache/ocr_calibration.json` | OCR 区域校准 |
| `OCR/ocr_confusion.json` | OCR 字符混淆映射 |
| `logs/app.log` | 运行日志 |
