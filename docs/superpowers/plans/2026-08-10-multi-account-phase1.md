# 多开阶段 1 实现计划（账户绑定 + 每账户名单 + 模式化重构）

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 wxassistant 支持手动进入多开模式：绑定多个微信窗口为账户、每账户独立好友名单、UI 可切换账户并管理各自名单。阶段 1 不涉及流水线并发发送（阶段 2）。

**Architecture:** 单账户模式完全不变。新增会话级 `MultiAccountSession`（不落盘跨会话），`WeChatBridge` 增加 `find_all_windows()`，`FriendService` 支持账户维度文件，`operations.py` 三个回调工厂改为动态取当前 bridge，`app.py` 重构为单/多账户两种启动路径，`MainWindow` 支持账户选择器与 [多开] 按钮。

**Tech Stack:** Python 3.10+、tkinter、win32gui、pytest（新增，仅测纯逻辑）

**设计文档:** `docs/superpowers/specs/2026-08-10-multi-account-broadcast-design.md`（阶段 1 = 该文档 §10 阶段 1）

---

## 前置现状（实现者须知）

- 项目无 `requirements.txt`、无 `tests/`、git 仓库 `master` 分支**无任何提交**
- 所有命令在项目根 `E:\Claudeproject\wxassistant` 运行（bash / PowerShell 均可）
- 纯逻辑（路径、数据模型）用 pytest 测；win32/UI（引导、find_all_windows、主窗口）手工验证
- 参考：`main.py` 用 `sys.path.insert(0, PROJECT_ROOT)` 保证 `import src.*` 可用；pytest 用 `tests/conftest.py` 做同样的事
- 项目是中文注释风格，新增代码保持中文注释

---

### Task 0: 测试脚手架 + 基线提交

**Files:**
- Create: `requirements-dev.txt`
- Create: `tests/conftest.py`
- Create: `tests/test_smoke.py`

- [ ] **Step 1: 创建开发依赖文件**

```text
# requirements-dev.txt — 仅开发/测试用
pytest>=8.0
```

- [ ] **Step 2: 创建 tests/conftest.py（让 pytest 能 import src）**

```python
# tests/conftest.py
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
```

- [ ] **Step 3: 创建冒烟测试**

```python
# tests/test_smoke.py
def test_project_importable():
    """能 import 纯 Python 服务模块"""
    from src.services.send_service import SendService
    from src.services.template_engine import TemplateEngine
    assert SendService is not None
    assert TemplateEngine is not None
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/test_smoke.py -v`
Expected: `1 passed`

- [ ] **Step 5: 配置 git 用户（若未配置）并做基线提交**

Run: `git config user.email >/dev/null 2>&1 || git config user.email "dev@local"; git config user.name >/dev/null 2>&1 || git config user.name "dev"`
Run: `git add -A`
Run: `git commit -m "chore: baseline existing codebase + pytest scaffold"`

Expected: commit 成功，包含全部现有代码。

---

### Task 1: 账户文件路径工具（纯函数）

**Files:**
- Create: `src/utils/account_paths.py`
- Test: `tests/test_account_paths.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_account_paths.py
from src.utils import account_paths as ap


def test_sanitize_replaces_illegal_chars():
    assert ap.sanitize_account_name("账户/1") == "账户_1"
    assert ap.sanitize_account_name("a:b") == "a_b"


def test_sanitize_collapses_whitespace():
    assert ap.sanitize_account_name(" 账 户 1 ") == "账_户_1"


def test_sanitize_empty_falls_back_to_default():
    assert ap.sanitize_account_name("   ") == "default"


def test_sanitize_truncates_long_names():
    assert len(ap.sanitize_account_name("好" * 100)) <= 32


def test_friends_path_for():
    p = ap.friends_path_for("账户1")
    assert p.name == "friends_账户1.json"
    assert p.parent == ap.CACHE_DIR


def test_different_accounts_get_different_paths():
    assert ap.friends_path_for("A") != ap.friends_path_for("B")
    assert ap.coordinates_path_for("A") != ap.coordinates_path_for("B")
    assert ap.calibration_path_for("A") != ap.calibration_path_for("B")
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest tests/test_account_paths.py -v`
Expected: FAIL（ModuleNotFoundError: src.utils.account_paths）

- [ ] **Step 3: 实现 account_paths.py**

```python
"""账户文件路径工具 — 多账户模式的每账户文件路径与账户名规范化

单账户使用全局文件（cache/friends.json 等）；多账户每账户一份：
cache/friends_<账户名>.json、cache/coordinates_<账户名>.json、cache/ocr_calibration_<账户名>.json
"""
import re
from pathlib import Path

CACHE_DIR = Path("cache")

# Windows 文件名非法字符 → 下划线
_INVALID_CHARS = re.compile(r'[\\/:*?"<>|]')
_WHITESPACE = re.compile(r"\s+")

_MAX_NAME_LEN = 32


def sanitize_account_name(name: str) -> str:
    """账户名 → 安全文件片段（去非法字符、压缩空白、截断、兜底 default）"""
    s = _INVALID_CHARS.sub("_", name.strip())
    s = _WHITESPACE.sub("_", s)
    if not s:
        s = "default"
    return s[:_MAX_NAME_LEN]


def _per_account_path(prefix: str, account_name: str) -> Path:
    return CACHE_DIR / f"{prefix}_{sanitize_account_name(account_name)}.json"


def friends_path_for(account_name: str) -> Path:
    """该账户的好友名单文件路径"""
    return _per_account_path("friends", account_name)


def coordinates_path_for(account_name: str) -> Path:
    """该账户的坐标覆盖文件路径（仅当该账户单独设置过才存在）"""
    return _per_account_path("coordinates", account_name)


def calibration_path_for(account_name: str) -> Path:
    """该账户的 OCR 校准覆盖文件路径"""
    return _per_account_path("ocr_calibration", account_name)
```

- [ ] **Step 4: 运行确认通过**

Run: `python -m pytest tests/test_account_paths.py -v`
Expected: `7 passed`

- [ ] **Step 5: Commit**

```bash
git add src/utils/account_paths.py tests/test_account_paths.py
git commit -m "feat: account file path utilities with sanitization"
```

---

### Task 2: MultiAccount 会话模型

**Files:**
- Create: `src/services/multi_account.py`
- Test: `tests/test_multi_account.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_multi_account.py
from src.services.multi_account import AccountWindow, MultiAccountSession


def test_add_and_count():
    s = MultiAccountSession()
    assert s.add("账户1", 0x10000)
    assert s.count == 1
    assert s.names == ["账户1"]


def test_add_rejects_duplicate_name():
    s = MultiAccountSession()
    s.add("账户1", 0x10000)
    assert not s.add("账户1", 0x20000)
    assert s.count == 1


def test_add_rejects_blank_name():
    s = MultiAccountSession()
    assert not s.add("   ", 0x10000)


def test_remove_renumbers_orders():
    s = MultiAccountSession()
    s.add("账户1", 0x1)
    s.add("账户2", 0x2)
    s.add("账户3", 0x3)
    assert s.remove(1)
    assert [a.order for a in s.accounts] == [0, 1]
    assert [a.name for a in s.accounts] == ["账户1", "账户3"]


def test_remove_out_of_range_returns_false():
    s = MultiAccountSession()
    s.add("账户1", 0x1)
    assert not s.remove(5)


def test_rename_updates_name():
    s = MultiAccountSession()
    s.add("账户1", 0x1)
    assert s.rename(0, "主号")
    assert s.accounts[0].name == "主号"


def test_rename_rejects_duplicate():
    s = MultiAccountSession()
    s.add("账户1", 0x1)
    s.add("账户2", 0x2)
    assert not s.rename(1, "账户1")
    assert s.accounts[1].name == "账户2"


def test_account_window_frozen_fields():
    a = AccountWindow(name="x", hwnd=123, order=0)
    assert a.hwnd == 123
    assert a.order == 0
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest tests/test_multi_account.py -v`
Expected: FAIL（ModuleNotFoundError）

- [ ] **Step 3: 实现 multi_account.py**

```python
"""多开会话模型 — 账户窗口绑定的会话级数据结构（不落盘跨会话）"""
from dataclasses import dataclass


@dataclass(frozen=True)
class AccountWindow:
    """一个账户在其微信窗口上的绑定"""
    name: str
    hwnd: int
    order: int


class MultiAccountSession:
    """本会话内多账户绑定列表（每次手动进入多开时重新创建）"""

    def __init__(self):
        self._accounts: list[AccountWindow] = []

    @property
    def accounts(self) -> list[AccountWindow]:
        return list(self._accounts)

    @property
    def count(self) -> int:
        return len(self._accounts)

    @property
    def names(self) -> list[str]:
        return [a.name for a in self._accounts]

    def add(self, name: str, hwnd: int) -> bool:
        """追加一个账户。账户名重复或为空返回 False"""
        name = name.strip()
        if not name:
            return False
        if any(a.name == name for a in self._accounts):
            return False
        self._accounts.append(AccountWindow(name=name, hwnd=hwnd, order=len(self._accounts)))
        return True

    def remove(self, index: int) -> bool:
        """删除指定序号的账户，并重新编号"""
        if 0 <= index < len(self._accounts):
            self._accounts.pop(index)
            self._renumber()
            return True
        return False

    def rename(self, index: int, new_name: str) -> bool:
        """重命名指定账户。重名或为空返回 False"""
        new_name = new_name.strip()
        if not new_name:
            return False
        if any(a.name == new_name for a in self._accounts
               if a.order != self._accounts[index].order):
            return False
        old = self._accounts[index]
        self._accounts[index] = AccountWindow(name=new_name, hwnd=old.hwnd, order=old.order)
        return True

    def _renumber(self):
        for i, a in enumerate(self._accounts):
            if a.order != i:
                self._accounts[i] = AccountWindow(name=a.name, hwnd=a.hwnd, order=i)
```

- [ ] **Step 4: 运行确认通过**

Run: `python -m pytest tests/test_multi_account.py -v`
Expected: `8 passed`

- [ ] **Step 5: Commit**

```bash
git add src/services/multi_account.py tests/test_multi_account.py
git commit -m "feat: multi-account session model"
```

---

### Task 3: FriendService 账户维度

**Files:**
- Modify: `src/services/friend_service.py`
- Test: `tests/test_friend_service_account.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_friend_service_account.py
import sys
from pathlib import Path

import pytest

from src.services import account_paths as ap  # noqa: F401  (仅为 monkeypatch 目标)
from src.services.friend_service import FriendService


@pytest.fixture
def tmp_cache(tmp_path, monkeypatch):
    """把每账户文件路径指到临时目录，避免污染真实 cache/"""
    monkeypatch.setattr(ap, "CACHE_DIR", tmp_path)
    yield tmp_path


def test_for_account_isolates_files(tmp_cache):
    fs_a = FriendService.for_account("账户A")
    fs_b = FriendService.for_account("账户B")

    fs_a.add_friend("张三")
    fs_a.save_cache()
    fs_b.add_friend("李四")
    fs_b.save_cache()

    # 各自从自己的文件加载
    fs_a2 = FriendService.for_account("账户A")
    fs_a2.load_cache()
    fs_b2 = FriendService.for_account("账户B")
    fs_b2.load_cache()

    assert [f.name for f in fs_a2.all_friends] == ["张三"]
    assert [f.name for f in fs_b2.all_friends] == ["李四"]
    assert fs_a.count == 1 and fs_b.count == 1
```

注意：`FriendService.save_cache()` 是异步写（daemon 线程），测试里需要等待落盘。若断言前未落盘，可在 `fs_a.add_friend` 后短暂等待。若测试不稳定，在测试末尾加 `import time; time.sleep(0.1)`。如果加了 sleep 仍不稳，可在下一步实现里说明。

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest tests/test_friend_service_account.py -v`
Expected: FAIL（AttributeError: type object 'FriendService' has no attribute 'for_account'）

- [ ] **Step 3: 实现 for_account classmethod**

在 `src/services/friend_service.py` 的 `__init__` 方法后、`load_cache` 前插入：

```python
    @classmethod
    def for_account(cls, account_name: str) -> "FriendService":
        """创建绑定到指定账户好友文件的实例（多开模式用）"""
        from src.utils.account_paths import friends_path_for
        return cls(cache_path=str(friends_path_for(account_name)))
```

- [ ] **Step 4: 运行确认通过**

Run: `python -m pytest tests/test_friend_service_account.py -v`
Expected: `1 passed`

- [ ] **Step 5: Commit**

```bash
git add src/services/friend_service.py tests/test_friend_service_account.py
git commit -m "feat: FriendService.for_account for per-account friend files"
```

---

### Task 4: WeChatBridge.find_all_windows() + find_window 复用

**Files:**
- Modify: `src/driver/wechat_bridge.py`（`find_window` 区域，106-155 行附近）

- [ ] **Step 1: 实现 find_all_windows 并让 find_window 复用它**

将现有 `find_window`（约 106-155 行）整体替换为：

```python
    def find_all_windows(self) -> list[tuple[int, str, str]]:
        """枚举所有可见微信主窗口，返回 [(hwnd, title, class)] 列表

        匹配规则与 find_window 一致：Qt 类名 + 标题含 '微信'/'Weixin'，
        排除自身进程的窗口。找不到则返回空列表。
        """
        import win32process
        self._ensure_com()
        self_pid = os.getpid()

        def _is_self(hwnd: int) -> bool:
            try:
                _, pid = win32process.GetWindowThreadProcessId(hwnd)
                return pid == self_pid
            except Exception:
                return False

        matches: list[tuple[int, str, str]] = []

        def _enum(hwnd: int, results: list) -> bool:
            if not win32gui.IsWindowVisible(hwnd) or _is_self(hwnd):
                return True
            title = win32gui.GetWindowText(hwnd)
            cls = win32gui.GetClassName(hwnd)
            if any(pattern in title for pattern in WEIXIN_WINDOW_TITLES) and 'Qt' in cls:
                results.append((hwnd, title, cls))
            return True

        win32gui.EnumWindows(_enum, matches)
        return matches

    def find_window(self) -> bool:
        """查找微信窗口：取 find_all_windows 的第一个匹配（保持单账户行为）"""
        matches = self.find_all_windows()
        if matches:
            self._hwnd = matches[0][0]
            title, cls = matches[0][1], matches[0][2]
            logger.info("已连接微信: hwnd=0x%X, class='%s', title='%s'",
                        self._hwnd, cls, title)
            return True
        logger.warning("未找到微信窗口（标题含'微信'/'Weixin'）")
        return False
```

注意：原 `find_window` 有一个第二层兜底 `_enum2`（只按标题匹配、不要求 Qt 类名）。新实现为保持一致性暂去掉该兜底；若实际发现某些环境只有标题无 Qt 类名，阶段 2 再补。此改动对单账户正常使用无影响（微信 4.x 主窗口类名就是 Qt）。

- [ ] **Step 2: 语法自检**

Run: `python -c "from src.driver.wechat_bridge import WeChatBridge; print('ok')"`
Expected: `ok`

- [ ] **Step 3: 手工验证（需真实微信）**

Run: `python -c "from src.driver.wechat_bridge import WeChatBridge; b=WeChatBridge(); print(b.find_all_windows())"`
Expected: 输出 1 个窗口 `[(hwnd, '微信', 'Qt')]`（单开时）；若多开则输出多个。

- [ ] **Step 4: Commit**

```bash
git add src/driver/wechat_bridge.py
git commit -m "feat: find_all_windows + reuse in find_window"
```

---

### Task 5: operations.py 改为动态取当前 bridge

**Files:**
- Modify: `src/operations.py`

背景：多账户模式下，`MainWindow` 切换账户会换 bridge。三个回调工厂若持有固定 bridge，切换后仍操作旧窗口。改为工厂接收 `get_bridge` 可调用对象，函数内每次取当前 bridge。单账户模式传 `lambda: bridge`，行为不变。

- [ ] **Step 1: 改 make_send_callback**

将 `def make_send_callback(bridge, template_engine, send_service):` 改为：

```python
def make_send_callback(get_bridge, template_engine, send_service):
    """创建群发后台回调（get_bridge: 可调用，返回当前账户的 WeChatBridge）

    流程：遍历好友 → 渲染 → 搜索 → OCR 验证 → 发送
    """

    def do_send(
        friends: list, message_template: str, attachments: list[str],
        interval: float, regex_pattern: str,
        progress_queue: queue.Queue, stop_event,
    ):
        bridge = get_bridge()
        compiled_regex = None
        if regex_pattern:
            try:
                compiled_regex = re.compile(regex_pattern)
            except re.error:
                pass

        bridge.set_stop_check(lambda: stop_event.is_set())
        ...
```

其余 `do_send` 内部不变（后续 `bridge` 变量已在上方取得）。

- [ ] **Step 2: 改 make_check_names_callback**

```python
def make_check_names_callback(get_bridge, friend_service):
    """检查选中好友名称是否完整（get_bridge: 返回当前账户 WeChatBridge）"""

    def do_check(friends: list, progress_queue: queue.Queue, stop_event):
        bridge = get_bridge()
        bridge.set_stop_check(lambda: stop_event.is_set())
        ...
```

其余不变。

- [ ] **Step 3: 改 make_search_contacts_callback**

```python
def make_search_contacts_callback(get_bridge, friend_service):
    """搜索并导入 / 扫描通讯录并导入（get_bridge: 返回当前账户 WeChatBridge）"""

    def do_search(keyword: str, progress_queue: queue.Queue, stop_event):
        bridge = get_bridge()
        bridge.set_stop_check(lambda: stop_event.is_set())
        ...
```

其余不变。

- [ ] **Step 4: 语法自检**

Run: `python -c "from src import operations; print('ok')"`
Expected: `ok`

- [ ] **Step 5: Commit**

```bash
git add src/operations.py
git commit -m "refactor: send/check/import callbacks take get_bridge callable"
```

---

### Task 6: 多开引导窗口

**Files:**
- Create: `src/ui/multi_account_dialog.py`

- [ ] **Step 1: 实现引导窗口**

```python
"""多开引导窗口 — 检测微信窗口 → 逐个前台确认账户名 → 生成会话

流程：
1. [检测微信窗口] 枚举所有微信主窗口
2. [逐个确认账户] 对每个窗口 SetForegroundWindow 显示到最前，
   弹输入框让用户确认账户名（默认 账户1/账户2…）
3. 列表支持重命名/删除
4. [确定并进入多开] 返回 MultiAccountSession；[取消] 返回 None
"""
import logging
import time
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
from typing import Optional

from src.driver.wechat_bridge import WeChatBridge
from src.services.multi_account import MultiAccountSession

logger = logging.getLogger(__name__)


def _default_name(index: int) -> str:
    return f"账户{index + 1}"


class MultiOpenWizard:
    """多开引导（模态）"""

    def __init__(self, root: tk.Tk, bridge: WeChatBridge):
        self.root = root
        self.bridge = bridge
        self.result: Optional[MultiAccountSession] = None

        self.root.title("多开设置")
        self.root.geometry("480x440")
        self.root.minsize(400, 320)

        self._frames: list[tuple[int, str, str]] = []
        self._session = MultiAccountSession()
        self._build_ui()

    def _build_ui(self):
        pad = {"padx": 12, "pady": 6}

        ttk.Label(
            self.root,
            text="检测到微信窗口后，逐个把窗口显示到最前，\n请在每个窗口确认它属于哪个账户（账户名可自定义）。",
            justify=tk.LEFT,
        ).pack(anchor=tk.W, **pad)

        # 检测行
        row = ttk.Frame(self.root)
        row.pack(fill=tk.X, **pad)
        self._btn_detect = ttk.Button(row, text="① 检测微信窗口", command=self._on_detect)
        self._btn_detect.pack(side=tk.LEFT)
        self._lbl_count = ttk.Label(row, text="", foreground="gray")
        self._lbl_count.pack(side=tk.LEFT, padx=8)

        # 绑定列表
        tree_frame = ttk.Frame(self.root)
        tree_frame.pack(fill=tk.BOTH, expand=True, **pad)
        cols = ("order", "name", "hwnd")
        self._tree = ttk.Treeview(tree_frame, columns=cols, show="headings", height=8)
        self._tree.heading("order", text="顺序")
        self._tree.heading("name", text="账户名")
        self._tree.heading("hwnd", text="窗口句柄")
        self._tree.column("order", width=50, anchor=tk.CENTER)
        self._tree.column("name", width=170)
        self._tree.column("hwnd", width=110)
        self._tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self._tree.yview)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        self._tree.configure(yscrollcommand=sb.set)

        # 操作行
        ops = ttk.Frame(self.root)
        ops.pack(fill=tk.X, **pad)
        ttk.Button(ops, text="② 逐个确认账户", command=self._on_confirm_all).pack(side=tk.LEFT)
        ttk.Button(ops, text="重命名", command=self._on_rename).pack(side=tk.LEFT, padx=4)
        ttk.Button(ops, text="删除", command=self._on_delete).pack(side=tk.LEFT)

        # 底部按钮
        btns = ttk.Frame(self.root)
        btns.pack(fill=tk.X, side=tk.BOTTOM, **pad)
        ttk.Button(btns, text="取消", command=self._on_cancel).pack(side=tk.RIGHT)
        ttk.Button(btns, text="确定并进入多开", command=self._on_ok).pack(side=tk.RIGHT, padx=6)

    # ---- 检测 ----
    def _on_detect(self):
        frames = self.bridge.find_all_windows()
        if not frames:
            messagebox.showwarning("提示", "未找到微信窗口，请先登录微信。")
            return
        self._frames = frames
        self._lbl_count.config(text=f"检测到 {len(frames)} 个微信窗口")
        self._refresh_tree()

    # ---- 逐个确认 ----
    def _on_confirm_all(self):
        if not self._frames:
            messagebox.showwarning("提示", "请先点击「检测微信窗口」。")
            return
        start = len(self._session.accounts)
        for i in range(start, len(self._frames)):
            hwnd, title, _cls = self._frames[i]
            if not self._bring_to_front(hwnd):
                messagebox.showwarning("提示", f"无法激活窗口 0x{hwnd:X}，跳过。")
                continue
            name = simpledialog.askstring(
                "确认账户",
                f"窗口 {i + 1}/{len(self._frames)}\n当前显示在最前的微信窗口是哪个账户？\n\n标题: {title}",
                initialvalue=_default_name(i),
                parent=self.root,
            )
            if name is None:
                break  # 用户点了取消 → 停止逐个确认，保留已确认的
            name = name.strip() or _default_name(i)
            self._session.add(name=name, hwnd=hwnd)
        self._refresh_tree()

    def _bring_to_front(self, hwnd: int) -> bool:
        """把微信窗口置顶激活（复用 activate_window 的 Alt 技巧）"""
        import win32api
        import win32con
        import win32gui
        try:
            if win32gui.IsIconic(hwnd):
                win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
                time.sleep(0.2)
            win32gui.SetWindowPos(hwnd, win32con.HWND_TOPMOST, 0, 0, 0, 0,
                                  win32con.SWP_NOMOVE | win32con.SWP_NOSIZE)
            win32gui.SetWindowPos(hwnd, win32con.HWND_NOTOPMOST, 0, 0, 0, 0,
                                  win32con.SWP_NOMOVE | win32con.SWP_NOSIZE)
            win32api.keybd_event(win32con.VK_MENU, 0, 0, 0)
            win32gui.SetForegroundWindow(hwnd)
            win32api.keybd_event(win32con.VK_MENU, 0, win32con.KEYEVENTF_KEYUP, 0)
            time.sleep(0.3)
            return True
        except Exception:
            logger.exception("激活窗口失败: 0x%X", hwnd)
            return False

    # ---- 列表操作 ----
    def _refresh_tree(self):
        self._tree.delete(*self._tree.get_children())
        for acc in self._session.accounts:
            self._tree.insert("", tk.END, values=(acc.order + 1, acc.name, f"0x{acc.hwnd:X}"))

    def _selected_index(self) -> Optional[int]:
        sel = self._tree.selection()
        if not sel:
            return None
        return int(self._tree.index(sel[0]))

    def _on_rename(self):
        idx = self._selected_index()
        if idx is None:
            return
        acc = self._session.accounts[idx]
        new_name = simpledialog.askstring(
            "重命名", "新账户名:", initialvalue=acc.name, parent=self.root)
        if new_name and new_name.strip():
            if not self._session.rename(idx, new_name.strip()):
                messagebox.showwarning("提示", "重命名失败：账户名重复或为空。")
        self._refresh_tree()

    def _on_delete(self):
        idx = self._selected_index()
        if idx is None:
            return
        self._session.remove(idx)
        self._refresh_tree()

    # ---- 完成 ----
    def _on_ok(self):
        if not self._session.accounts:
            messagebox.showwarning("提示", "还没有绑定任何账户。")
            return
        self.result = self._session
        self.root.destroy()

    def _on_cancel(self):
        self.result = None
        self.root.destroy()


def run_multiopen_wizard(bridge: WeChatBridge) -> Optional[MultiAccountSession]:
    """打开多开引导，返回会话（取消返回 None）"""
    root = tk.Tk()
    wizard = MultiOpenWizard(root, bridge)
    root.mainloop()
    return wizard.result
```

- [ ] **Step 2: 语法自检**

Run: `python -c "from src.ui.multi_account_dialog import run_multiopen_wizard; print('ok')"`
Expected: `ok`

- [ ] **Step 3: 手工验证（需真实微信多开）**

Run: `python -c "from src.driver.wechat_bridge import WeChatBridge; from src.ui.multi_account_dialog import run_multiopen_wizard; s=run_multiopen_wizard(WeChatBridge()); print('session:', s.names if s else None)"`
Expected: 引导窗口弹出 → 检测 → 逐个确认 → 确定后打印账户名列表；取消打印 None。

- [ ] **Step 4: Commit**

```bash
git add src/ui/multi_account_dialog.py
git commit -m "feat: multi-open wizard dialog"
```

---

### Task 7: FilterBar 加 [多开] 按钮

**Files:**
- Modify: `src/ui/filter_bar.py`

- [ ] **Step 1: 加回调槽位（__init__ 中，_on_refresh 附近）**

```python
        self._on_multiopen: Optional[Callable[[], None]] = None
```

- [ ] **Step 2: 在 row2 加按钮（"刷新"按钮旁）**

将 row2 中 `self._btn_refresh` 的 pack 语句之后插入：

```python
        self._btn_multiopen = ttk.Button(
            row2, text="多开", width=6, command=self._on_multiopen_clicked,
        )
        self._btn_multiopen.pack(side=tk.LEFT, padx=(6, 0))
```

- [ ] **Step 3: 加公开 setter 与内部 handler**

在 `set_on_clear_tags` 方法之后插入：

```python
    def set_on_multiopen(self, callback: Callable[[], None]) -> None:
        self._on_multiopen = callback

    def _on_multiopen_clicked(self) -> None:
        if self._on_multiopen:
            self._on_multiopen()
```

- [ ] **Step 4: 语法自检**

Run: `python -c "from src.ui.filter_bar import FilterBar; print('ok')"`
Expected: `ok`

- [ ] **Step 5: Commit**

```bash
git add src/ui/filter_bar.py
git commit -m "feat: multi-open button in filter bar"
```

---

### Task 8: MainWindow 多账户模式（账户选择器 + 进入多开）

**Files:**
- Modify: `src/ui/main_window.py`

- [ ] **Step 1: 修改 __init__ 支持 multi_session 参数**

将 `def __init__(self):` 改为：

```python
    def __init__(self, multi_session=None):
        self.root = tk.Tk()
        self.root.title(WINDOW_TITLE)
        self.root.geometry(f"{WINDOW_WIDTH}x{WINDOW_HEIGHT}")
        self.root.minsize(780, 520)

        self._friend_service = None
        self._bridge = None  # WeChatBridge，校准前用来打开对应窗口
        self._multi_session = multi_session      # Optional[MultiAccountSession]
        self._account_runtime: dict = {}          # name -> (bridge, friend_service)
        self._account_var: Optional[tk.StringVar] = None
        self._on_send: Optional[Callable] = None
        self._on_check_names: Optional[Callable] = None
        self._on_search_contacts: Optional[Callable] = None
        self._on_enter_multiopen: Optional[Callable] = None
        self._progress_queue: queue.Queue = queue.Queue()
        self._stop_event: Optional[threading.Event] = None
        self._interrupt_poll_active: bool = False

        self._build_ui()
        self._wire_events()
        self._poll_progress_queue()
        ...
```

（其余 __init__ 体不变，包括 bind/set_ui_callback/_show_startup_hints）

- [ ] **Step 2: 加公开 setter**

在 `set_search_contacts_callback` 之后插入：

```python
    def set_enter_multiopen_callback(self, callback: Callable) -> None:
        self._on_enter_multiopen = callback

    def set_account_runtime(self, runtime: dict) -> None:
        """注入多账户运行时：{账户名: (bridge, friend_service)}"""
        self._account_runtime = runtime
        if self._multi_session and runtime:
            first = self._multi_session.names[0]
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
        """切换到指定账户：换 bridge + friend_service"""
        if name not in self._account_runtime:
            return
        bridge, service = self._account_runtime[name]
        self.set_bridge(bridge)
        self.set_friend_service(service)
```

- [ ] **Step 3: _build_ui 加账户选择器行（多账户模式）**

在 `_build_ui` 里 `left = ttk.Frame(main_paned, ...)` 之后、`self.filter_bar = FilterBar(left)` 之前插入：

```python
        if self._multi_session is not None:
            account_bar = ttk.Frame(left)
            account_bar.pack(fill=tk.X, padx=4, pady=(4, 0))
            ttk.Label(account_bar, text="账户:").pack(side=tk.LEFT)
            self._account_var = tk.StringVar()
            self._account_combo = ttk.Combobox(
                account_bar, textvariable=self._account_var,
                values=self._multi_session.names, state="readonly", width=14,
            )
            self._account_combo.pack(side=tk.LEFT, padx=(6, 0), fill=tk.X, expand=True)
            self._account_combo.bind("<<ComboboxSelected>>", self._on_account_selected)
```

注意：账户选择器必须在 `set_account_runtime` 之前创建（__init__ 顺序：_build_ui 先于外部 set_account_runtime 调用，满足）。

- [ ] **Step 4: 加账户切换与多开按钮的 handler**

在 `_on_refresh` 方法前插入：

```python
    def _on_account_selected(self, _event=None) -> None:
        if self._account_var:
            self._switch_account(self._account_var.get())

    def _on_multiopen_clicked(self) -> None:
        if self._on_enter_multiopen:
            self._on_enter_multiopen()
```

- [ ] **Step 5: _wire_events 接入 [多开] 按钮**

在 `_wire_events` 中 `self.filter_bar.set_on_refresh(self._on_refresh)` 附近插入：

```python
        self.filter_bar.set_on_multiopen(self._on_multiopen_clicked)
```

- [ ] **Step 6: 多账户模式下刷新按钮不重找窗口**

将 `_on_refresh` 改为：

```python
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
```

- [ ] **Step 7: 语法自检**

Run: `python -c "from src.ui.main_window import MainWindow; print('ok')"`
Expected: `ok`（注意：构造 MainWindow 需要 Tk 环境，此自检只验证 import/语法，不实例化）

- [ ] **Step 8: Commit**

```bash
git add src/ui/main_window.py
git commit -m "feat: multi-account mode in main window (account selector + multi-open button)"
```

---

### Task 9: app.py 模式化重构（单账户 / 多账户启动）

**Files:**
- Modify: `src/app.py`

- [ ] **Step 1: 重写 run_gui 为模式化**

将 `run_gui` 函数整体替换为：

```python
def run_gui() -> None:
    """启动 GUI（单账户模式）"""
    window = _build_window(multi_session=None)
    window.run()


def run_multi_gui(session) -> None:
    """启动 GUI（多账户模式）"""
    window = _build_window(multi_session=session)
    window.run()


def _build_window(multi_session=None):
    """构造主窗口。multi_session 为 None = 单账户模式，否则多账户模式"""
    from src.driver.wechat_bridge import WeChatBridge
    from src.services.friend_service import FriendService
    from src.services.template_engine import TemplateEngine
    from src.services.send_service import SendService
    from src.ui.main_window import MainWindow
    from src.operations import (
        make_send_callback,
        make_check_names_callback,
        make_search_contacts_callback,
    )

    template_engine = TemplateEngine()
    send_service = SendService()

    if multi_session is None:
        # ---- 单账户模式（原逻辑）----
        bridge = WeChatBridge()
        bridge.find_window()
        friend_service = FriendService()
        friend_service.load_cache()

        window = MainWindow()
        window.set_bridge(bridge)
        window.set_friend_service(friend_service)
        window.set_send_callback(
            make_send_callback(lambda: bridge, template_engine, send_service))
        window.set_check_names_callback(
            make_check_names_callback(lambda: bridge, friend_service))
        window.set_search_contacts_callback(
            make_search_contacts_callback(lambda: bridge, friend_service))
        window.set_enter_multiopen_callback(lambda w=window: _enter_multiopen(w))
        return window

    # ---- 多账户模式 ----
    window = MainWindow(multi_session=multi_session)

    runtime: dict[str, tuple] = {}
    for acc in multi_session.accounts:
        b = WeChatBridge()
        b._hwnd = acc.hwnd  # 绑定该账户窗口（不重新 find_window）
        fs = FriendService.for_account(acc.name)
        fs.load_cache()
        runtime[acc.name] = (b, fs)
    window.set_account_runtime(runtime)

    window.set_send_callback(
        make_send_callback(window.get_current_bridge, template_engine, send_service))
    window.set_check_names_callback(
        make_check_names_callback(window.get_current_bridge, window.get_current_friend_service))
    window.set_search_contacts_callback(
        make_search_contacts_callback(window.get_current_bridge, window.get_current_friend_service))
    window.set_enter_multiopen_callback(lambda w=window: _enter_multiopen(w))
    return window


def _enter_multiopen(window) -> None:
    """点 [多开]：关闭主窗口 → 打开引导 → 按结果重启对应模式"""
    from src.driver.wechat_bridge import WeChatBridge
    from src.ui.multi_account_dialog import run_multiopen_wizard

    window.root.destroy()
    session = run_multiopen_wizard(WeChatBridge())
    if session is None:
        run_gui()  # 取消 → 回单账户模式
    else:
        run_multi_gui(session)
```

注意：`window.set_check_names_callback(make_check_names_callback(...))` 传入 `window.get_current_friend_service`（方法引用，作为参数值传入——friend_service 参数目前未在 do_check 内使用，仅保持签名）。`make_search_contacts_callback` 同理。

- [ ] **Step 2: 确认 main.py 的 run_gui 引用不变**

Run: `python -c "from src.app import run_gui, run_multi_gui; print('ok')"`
Expected: `ok`

- [ ] **Step 3: 手工验证**

Run: `python main.py`
Expected:
1. 单账户模式正常打开（需微信已启动），[多开] 按钮出现在筛选栏
2. 点 [多开] → 主窗口关闭 → 引导弹出
3. 引导：检测到 N 个微信窗口 → 逐个确认 → 确定 → 多账户模式主窗口打开
4. 多账户主窗口：顶部有账户下拉，切换账户 → 好友列表切换（各账户独立）
5. 关闭多开窗口后再 `python main.py` → 仍是单账户模式（多开不持久，符合决策）

- [ ] **Step 4: Commit**

```bash
git add src/app.py
git commit -m "feat: single/multi-account app launch paths + multi-open entry"
```

---

### Task 10: 端到端验证 + 收尾

- [ ] **Step 1: 跑全部测试**

Run: `python -m pytest tests/ -v`
Expected: 全部通过（约 16 个：smoke 1 + account_paths 7 + multi_account 8 + friend_service_account 1）

- [ ] **Step 2: 三场景手工回归**

1. **单账户群发**：`python main.py` → 选好友 → 发送 → 与之前完全一致（回归）
2. **多开引导**：点 [多开] → 引导绑定 2 个账户 → 多账户模式
3. **每账户名单隔离**：账户1 导入好友 A/B，切账户2 导入 C/D，再切回账户1 确认仍是 A/B；`cache/friends_账户1.json` 与 `cache/friends_账户2.json` 内容独立

- [ ] **Step 3: 更新 README（.omc/README.md）补多开说明**

在 `.omc/README.md` 的「核心功能」后新增一节（用文档现有中文风格）：

```markdown
## 多开（多个微信账号）

1. 登录多个微信账号，将窗口平铺（勿重叠）
2. 主界面点 [多开] → 检测窗口 → 逐个确认账户名 → 确定
3. 顶部账户下拉切换，每个账户的好友名单独立管理
4. 发送 / OCR 扫描 / 名字检查均作用于当前选中的账户

说明：多开绑定只在本次运行有效，重启后回到单账户模式。
```

- [ ] **Step 4: Commit**

```bash
git add .omc/README.md
git commit -m "docs: multi-open usage in README"
```

- [ ] **Step 5: 汇报阶段 1 完成**

完成所有测试与回归后，向用户汇报：可手动进入多开、切换账户、独立管理名单；发送仍为"当前账户"单发（流水线并发在阶段 2）。
