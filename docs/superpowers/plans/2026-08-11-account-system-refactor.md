# 账户系统重构计划（持久账户 + 文件夹存储 + 单模式切换 + 搜一搜清理）

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把「账户」从多开专属的会话概念提升为**持久化第一等概念**：单账户模式也能切换账户、各账户独立联系人/坐标/OCR校准、默认账户叫「默认账户」；存储格式重构为 `cache/<账户名>/` 文件夹；顺带清掉搜一搜功能、修几处 UI（删除按钮宽度、账户选择器标签顺序、账户管理弹窗）。

**Architecture:** 存储改为 `cache/accounts.json`（账户名列表）+ 每账户一个文件夹 `cache/<账户名>/{friends.json, settings.json, ocr_calibration.json, coordinates.json}` + 全局 `cache/settings.json`（不需分账户的设置）。新增纯层 `account_registry.py` 管账户列表，`account_paths.py` 改为文件夹路径。单模式启动也构建账户运行时（账户选择器常显），多开引导改为「窗口 → 绑到已有持久账户」。

**Tech Stack:** Python 3.10+、tkinter、win32gui、pytest（纯逻辑层测试）

**前置决策（已与用户确认）：**
1. 账户列表持久化；**多开窗口绑定仍会话级**（不保存，每次进多开重新绑）。
2. 旧全局文件（`cache/friends.json` 等）**废弃，不迁移**（旧数据丢失可接受）。
3. **多开引导绑到持久账户**：窗口绑定在已存在的账户上（或新建持久账户）。
4. 坐标/OCR校准**每账户独立**，未设置时回退**代码内置默认值**（不继承默认账户）。

---

## 目标存储结构

```
cache/
  accounts.json              # ["默认账户", "账户2", ...]  账户名列表（第一个为当前选中？不，选中是 UI 状态）
  settings.json              # 全局设置：ocr_debug_save / scan_page_count / scan_scroll_px /
                             #   scan_pages_per_scroll / logging_enabled / multi_open_*
  <账户名>/                  # 文件夹名 = sanitize(账户名)；默认账户文件夹 = "默认账户/"
    friends.json             # 该账户联系人
    settings.json            # 账户级设置（当前仅 name_source）
    ocr_calibration.json     # 该账户 OCR 位置
    coordinates.json         # 该账户坐标
```

**设置归属划分：**
- 全局 `cache/settings.json`：`ocr_debug_save`、`scan_page_count`、`scan_scroll_px`、`scan_pages_per_scroll`、`logging_enabled`、`multi_open_*`（调试/扫描/多开这些不分账户的）。
- 账户级 `cache/<账户>/settings.json`：`name_source`（该账户联系人来源：cache / OCR）。
- 「账户名」只存在 `accounts.json` 与文件夹名里，**不写入** settings.json（名称与设置分离）。

---

## 前置现状（实现者须知）

- 项目根 `E:\Claudeproject\wxassistant`，分支 `feature/multi-account-phase1`，pytest 50 passed。
- 现有全局文件 `cache/friends.json`/`coordinates.json`/`ocr_calibration.json`/`settings.json` 将被取代，实现后**删除或忽略**（用户明确旧数据不要了）。
- 当前路径工具 `src/utils/account_paths.py`：`friends_path_for(name)` 返回 `cache/friends_<name>.json`（扁平文件），需改为 `cache/<name>/friends.json`（文件夹）。
- 当前 `FriendService()` 默认读 `config.FRIENDS_CACHE_PATH = "cache/friends.json"`；`FriendService.for_account(name)` 读扁平账户文件。
- `coordinates.py` 的 `load_coordinates(account_name=None)` 现做「全局 → 账户」两级合并；`calibration.py` 同理。重构后**取消全局文件**，只读账户文件 + 回退代码默认。
- `settings_store.py` 现在只读写全局 `cache/settings.json`；需新增账户级设置读写。
- 账户选择器在 `top_bar.py`（`set_account_options`，单模式禁用显示「全局」）；`main_window.py` 只在 `multi_session is not None` 时显示账户选择器。
- 多开引导 `multi_account_dialog.py` 现创建会话级账户（默认名「账户1/账户2」）；改为绑到持久账户。
- 搜一搜触点 11 处：见 Task 8。

---

### Task 0: 测试基线确认

- [ ] **Step 1:** `python -m pytest tests/ -q` → `50 passed`
- [ ] **Step 2:** `git status --short` → 干净

---

### Task 1: 纯层 —— account_paths 文件夹化 + account_registry

**Files:**
- Rewrite: `src/utils/account_paths.py`
- Create: `src/services/account_registry.py`
- Update: `tests/test_account_paths.py`
- Create: `tests/test_account_registry.py`

- [ ] **Step 1: 写失败测试（test_account_paths.py 重写）**

```python
# tests/test_account_paths.py
import pytest
from src.utils import account_paths as ap


@pytest.fixture
def tmp_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(ap, "CACHE_DIR", tmp_path)
    return tmp_path


def test_sanitize_replaces_illegal_chars():
    assert ap.sanitize_account_name("账户/1") == "账户_1"
    assert ap.sanitize_account_name("a:b") == "a_b"


def test_sanitize_empty_falls_back_to_default():
    assert ap.sanitize_account_name("   ") == "default"


def test_account_dir_is_cache_slash_name(tmp_cache):
    assert ap.account_dir("账户1") == tmp_cache / "账户1"
    # 非法字符被 sanitize
    assert ap.account_dir("a/b") == tmp_cache / "a_b"


def test_friends_path_in_account_folder(tmp_cache):
    p = ap.friends_path_for("账户1")
    assert p == tmp_cache / "账户1" / "friends.json"


def test_account_files_in_same_folder(tmp_cache):
    a = ap.friends_path_for("X")
    assert a == tmp_cache / "X" / "friends.json"
    assert ap.coordinates_path_for("X") == tmp_cache / "X" / "coordinates.json"
    assert ap.calibration_path_for("X") == tmp_cache / "X" / "ocr_calibration.json"
    assert ap.account_settings_path_for("X") == tmp_cache / "X" / "settings.json"


def test_different_accounts_get_different_folders(tmp_cache):
    assert ap.account_dir("A") != ap.account_dir("B")
    assert ap.friends_path_for("A") != ap.friends_path_for("B")
```

- [ ] **Step 2: 运行确认失败**

`python -m pytest tests/test_account_paths.py -v` → FAIL（`friends_path_for` 现在返回扁平文件路径）

- [ ] **Step 3: 重写 account_paths.py**

```python
"""账户文件路径 — cache/按账户文件夹管理

cache/<账户名>/{friends.json, settings.json, ocr_calibration.json, coordinates.json}
cache/accounts.json 存账户名列表；cache/settings.json 存全局（不分账户的）设置。
账户名只体现在文件夹名上，不写入任何 json 内容。
"""
import re
from pathlib import Path

CACHE_DIR = Path("cache")

# Windows 文件名非法字符 → 下划线
_INVALID_CHARS = re.compile(r'[\\/:*?"<>|]')
_WHITESPACE = re.compile(r"\s+")
_MAX_NAME_LEN = 32


def sanitize_account_name(name: str) -> str:
    """账户名 → 安全文件夹片段（去非法字符、压缩空白、截断、兜底 default）"""
    s = _INVALID_CHARS.sub("_", name.strip())
    s = _WHITESPACE.sub("_", s)
    if not s:
        s = "default"
    return s[:_MAX_NAME_LEN]


def account_dir(account_name: str) -> Path:
    """该账户的数据文件夹（cache/<sanitized>/）"""
    return CACHE_DIR / sanitize_account_name(account_name)


def _account_file(account_name: str, filename: str) -> Path:
    return account_dir(account_name) / filename


def friends_path_for(account_name: str) -> Path:
    return _account_file(account_name, "friends.json")


def coordinates_path_for(account_name: str) -> Path:
    return _account_file(account_name, "coordinates.json")


def calibration_path_for(account_name: str) -> Path:
    return _account_file(account_name, "ocr_calibration.json")


def account_settings_path_for(account_name: str) -> Path:
    return _account_file(account_name, "settings.json")
```

- [ ] **Step 4: 运行确认通过**

`python -m pytest tests/test_account_paths.py -v` → 全过

- [ ] **Step 5: 写 account_registry 测试（tests/test_account_registry.py）**

```python
# tests/test_account_registry.py
import pytest
from src.services import account_registry as reg


@pytest.fixture
def tmp_accounts(tmp_path, monkeypatch):
    monkeypatch.setattr(reg, "ACCOUNTS_PATH", tmp_path / "accounts.json")
    return tmp_path


def test_default_account_exists_on_first_load(tmp_accounts):
    assert reg.load_accounts() == [reg.DEFAULT_ACCOUNT_NAME]


def test_save_and_load(tmp_accounts):
    reg.save_accounts([reg.DEFAULT_ACCOUNT_NAME, "账户2"])
    assert reg.load_accounts() == [reg.DEFAULT_ACCOUNT_NAME, "账户2"]


def test_default_account_always_ensured(tmp_accounts):
    reg.save_accounts(["账户2"])          # 缺默认账户 → 自动补在最前
    assert reg.load_accounts()[0] == reg.DEFAULT_ACCOUNT_NAME


def test_rename_moves_folder(tmp_accounts, monkeypatch):
    from src.utils import account_paths as ap
    monkeypatch.setattr(ap, "CACHE_DIR", tmp_accounts)
    (ap.account_dir("旧名") / "friends.json").parent.mkdir(parents=True, exist_ok=True)
    (ap.account_dir("旧名") / "friends.json").write_text("{}", encoding="utf-8")
    reg.save_accounts([reg.DEFAULT_ACCOUNT_NAME, "旧名"])
    assert reg.rename_account("旧名", "新名")
    assert reg.load_accounts() == [reg.DEFAULT_ACCOUNT_NAME, "新名"]
    assert (ap.account_dir("新名") / "friends.json").exists()   # 文件夹被移动
    assert not ap.account_dir("旧名").exists()


def test_rename_rejects_duplicate(tmp_accounts):
    reg.save_accounts([reg.DEFAULT_ACCOUNT_NAME, "A"])
    assert not reg.rename_account("A", reg.DEFAULT_ACCOUNT_NAME)


def test_delete_account_removes_folder(tmp_accounts, monkeypatch):
    from src.utils import account_paths as ap
    monkeypatch.setattr(ap, "CACHE_DIR", tmp_accounts)
    (ap.account_dir("账户2") / "friends.json").parent.mkdir(parents=True, exist_ok=True)
    reg.save_accounts([reg.DEFAULT_ACCOUNT_NAME, "账户2"])
    assert reg.delete_account("账户2")
    assert reg.load_accounts() == [reg.DEFAULT_ACCOUNT_NAME]
    assert not ap.account_dir("账户2").exists()


def test_cannot_delete_default_account(tmp_accounts):
    reg.save_accounts([reg.DEFAULT_ACCOUNT_NAME, "A"])
    assert not reg.delete_account(reg.DEFAULT_ACCOUNT_NAME)
```

- [ ] **Step 6: 运行确认失败**

`python -m pytest tests/test_account_registry.py -v` → FAIL（ModuleNotFoundError）

- [ ] **Step 7: 实现 src/services/account_registry.py**

```python
"""账户注册表 — 持久账户列表（cache/accounts.json）

账户是全局第一等概念：单模式可切换、多开绑定窗口到账户。
默认账户固定存在且排最前，名称为「默认账户」。账户名即文件夹名，不与设置混存。
"""
import json
import shutil
from pathlib import Path

from src.utils.account_paths import account_dir

ACCOUNTS_PATH = Path("cache/accounts.json")
DEFAULT_ACCOUNT_NAME = "默认账户"


def load_accounts() -> list[str]:
    """加载账户名列表；文件缺失/损坏时返回仅含默认账户。默认账户始终保证存在且在最前。"""
    names: list[str] = [DEFAULT_ACCOUNT_NAME]
    if ACCOUNTS_PATH.exists():
        try:
            data = json.loads(ACCOUNTS_PATH.read_text(encoding="utf-8"))
            if isinstance(data, list):
                names = [n.strip() for n in data if isinstance(n, str) and n.strip()]
        except Exception:
            pass
    if DEFAULT_ACCOUNT_NAME not in names:
        names.insert(0, DEFAULT_ACCOUNT_NAME)
    return names


def save_accounts(names: list[str]) -> None:
    ACCOUNTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    ACCOUNTS_PATH.write_text(
        json.dumps(names, ensure_ascii=False, indent=2), encoding="utf-8")


def rename_account(old: str, new: str) -> bool:
    """重命名账户：更新列表 + 移动数据文件夹。重名/不存在返回 False。"""
    names = load_accounts()
    if old not in names or new in names:
        return False
    names[names.index(old)] = new
    save_accounts(names)
    old_dir, new_dir = account_dir(old), account_dir(new)
    if old_dir.exists() and not new_dir.exists():
        try:
            old_dir.rename(new_dir)
        except OSError:
            pass
    return True


def delete_account(name: str) -> bool:
    """删除账户：从列表移除 + 删数据文件夹。默认账户不可删。"""
    if name == DEFAULT_ACCOUNT_NAME:
        return False
    names = load_accounts()
    if name not in names:
        return False
    names.remove(name)
    save_accounts(names)
    d = account_dir(name)
    if d.exists():
        shutil.rmtree(d, ignore_errors=True)
    return True
```

- [ ] **Step 8: 运行确认通过**

`python -m pytest tests/test_account_registry.py -v` → 全过

- [ ] **Step 9: 全量测试 + Commit**

`python -m pytest tests/ -q` → 通过（account_paths 测试重写，account_registry 新增）
```bash
git add src/utils/account_paths.py src/services/account_registry.py tests/test_account_paths.py tests/test_account_registry.py
git commit -m "refactor: account storage to per-account folders + persisted account registry"
```

---

### Task 2: 纯层 —— friend_service / coordinates / calibration / settings_store 改造

**Files:**
- Modify: `src/services/friend_service.py`
- Modify: `src/utils/coordinates.py`
- Modify: `src/utils/calibration.py`
- Modify: `src/utils/settings_store.py`
- Modify: `src/utils/config.py`（删 `FRIENDS_CACHE_PATH` 或改为默认账户路径）
- Update: `tests/test_coordinates_account.py`、`tests/test_calibration.py`、`tests/test_friend_service_account.py`
- Create: `tests/test_settings_store_account.py`

- [ ] **Step 1: coordinates.py 改只读账户文件**

`load_coordinates`（现约 80-86 行）改为：
```python
def load_coordinates(account_name: str) -> dict:
    """加载账户坐标：账户文件覆盖 → 代码默认值兜底（无全局文件）"""
    merged = dict(DEFAULT_COORDINATES)
    _apply_coord_file(merged, coordinates_path_for(account_name))
    return merged
```
- 删 `COORDINATES_PATH`、`_coordinates_path()` 的全局分支；`_apply_coord_file` 保留。
- `save_coordinates(coords, account_name)` 写 `coordinates_path_for(account_name)`。
- `get_coord(key, account_name)` 不变（调 load_coordinates）。
- `account_has_override(account_name)` 改为检查账户文件是否存在（不再有 None=全局语义）：
```python
def account_has_override(account_name: str) -> bool:
    """该账户是否已保存过坐标文件"""
    return coordinates_path_for(account_name).exists()
```
- 更新 `tests/test_coordinates_account.py`：monkeypatch `ap.CACHE_DIR` 即可；删掉「全局文件」相关断言（如 `test_account_overrides_global`、`test_account_has_override(None)`），新增「账户文件缺失回退默认」用例。

- [ ] **Step 2: calibration.py 改只读账户文件**

`load_calibration`（现约 40-48 行）改为：
```python
def load_calibration(key: str, account_name: str) -> dict:
    """加载账户校准参数：账户文件覆盖 → 代码默认值兜底（无全局文件）"""
    merged = dict(DEFAULT_CALIBRATION.get(key, {}))
    _apply_key(merged, calibration_path_for(account_name), key)
    return merged
```
- 删 `OCR_CALIBRATION_PATH`；`calibration_has_key(key, account_name)` 只查账户文件。
- 更新 `tests/test_calibration.py`：monkeypatch `ap.CACHE_DIR`；删全局相关断言，改为「无账户文件回退默认」「账户文件覆盖」「账户间隔离」。

- [ ] **Step 3: friend_service.py 改账户文件夹**

```python
    @classmethod
    def for_account(cls, account_name: str) -> "FriendService":
        """创建绑定到指定账户数据文件夹的实例"""
        from src.utils.account_paths import friends_path_for
        return cls(cache_path=str(friends_path_for(account_name)))
```
- `config.FRIENDS_CACHE_PATH` 删除；`FriendService.__init__` 默认参数改为 `cache_path: str = "cache/friends.json"`（遗留兜底，调用方一律传账户路径）。
- 更新 `tests/test_friend_service_account.py`：monkeypatch `ap.CACHE_DIR` 即可（现在路径是 `cache/<name>/friends.json`）。

- [ ] **Step 4: settings_store.py 加账户级设置**

保留全局 `load_settings/save_settings/load_scan_settings`（读 `cache/settings.json`，从 DEFAULT_SETTINGS 删掉 `sousou_independent_enabled`，见 Task 8）。新增：
```python
from src.utils.account_paths import account_settings_path_for

def load_account_settings(account_name: str) -> dict:
    """加载账户级设置（cache/<账户>/settings.json）"""
    path = account_settings_path_for(account_name)
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return dict(ACCOUNT_DEFAULT_SETTINGS).update(data) or ACCOUNT_DEFAULT_SETTINGS | data
        except Exception:
            pass
    return dict(ACCOUNT_DEFAULT_SETTINGS)


def save_account_settings(account_name: str, settings: dict) -> None:
    path = account_settings_path_for(account_name)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(settings, ensure_ascii=False, indent=2), encoding="utf-8")
```
`ACCOUNT_DEFAULT_SETTINGS = {"name_source": "cache"}`（账户级设置仅 name_source 起步）。

`DEFAULT_SETTINGS`（全局）移除 `name_source` 与 `sousou_independent_enabled`，保留其余。

- [ ] **Step 5: 新增 tests/test_settings_store_account.py**

```python
# tests/test_settings_store_account.py
import pytest
from src.utils import account_paths as ap
from src.utils import settings_store as ss


@pytest.fixture
def tmp_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(ap, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(ss, "SETTINGS_PATH", tmp_path / "settings.json")
    return tmp_path


def test_account_settings_default(tmp_cache):
    assert ss.load_account_settings("账户1") == {"name_source": "cache"}


def test_account_settings_save_and_load(tmp_cache):
    ss.save_account_settings("账户1", {"name_source": "ocr"})
    assert ss.load_account_settings("账户1") == {"name_source": "ocr"}
    # 账户间隔离
    assert ss.load_account_settings("账户2") == {"name_source": "cache"}


def test_account_settings_not_in_global(tmp_cache):
    ss.save_account_settings("账户1", {"name_source": "ocr"})
    assert "name_source" not in ss.load_settings()   # 全局设置不含账户级 key
```

- [ ] **Step 6: 全量测试 + Commit**

`python -m pytest tests/ -q` → 全过
```bash
git add src/services/friend_service.py src/utils/coordinates.py src/utils/calibration.py src/utils/settings_store.py src/utils/config.py tests/
git commit -m "refactor: per-account folder storage for friends/coordinates/calibration/settings"
```

---

### Task 3: 单模式账户切换（app.py + TopBar 顺序 + MainWindow 选择器常显）

**Files:**
- Modify: `src/app.py`
- Modify: `src/ui/top_bar.py`
- Modify: `src/ui/main_window.py`

- [ ] **Step 1: top_bar.py 账户选择器**

1. **标签顺序**：`账户:[combo]`（label 在左）。当前 `_build_ui` 里 `self._account_combo.pack(...)` 在 `self._account_label.pack(...)` 之前 → 交换顺序：
```python
        self._account_label.pack(side=tk.LEFT)
        self._account_combo.pack(side=tk.LEFT, padx=(0, 2))
```
2. `set_account_options`：单模式不再显示「全局」禁用；统一显示账户列表。改为接收账户列表 + 当前选中：
```python
    def set_account_options(self, names: list[str], account_var=None, on_change=None) -> None:
        """显示账户下拉（单/多模式都可用）。names 空 → 仍显示但禁用"""
        self._multi = bool(names)
        self._account_label.pack(side=tk.LEFT)
        self._account_combo.pack(side=tk.LEFT, padx=(0, 2))
        self._account_combo["values"] = list(names) if names else []
        if account_var is not None:
            self._account_combo.configure(textvariable=account_var)
        if on_change:
            self._on_account_change = on_change
            self._account_combo.bind("<<ComboboxSelected>>", self._on_combo_selected)
        if names:
            self._account_combo.config(state="readonly")
        else:
            self._account_combo.config(state="disabled")
```
3. `set_account_enabled` 保持现状（`if not self._multi: return`；有账户时 `_multi=True`，语义正确）。

- [ ] **Step 2: main_window.py 账户选择器常显 + 账户管理入口**

1. `_build_ui`：删 `if self._multi_session is not None:` 门，账户选择器改为**始终创建**（值由 `set_account_options` 填充）：
```python
        self._account_var = tk.StringVar()
        self.top_bar.set_account_options([], self._account_var, self._on_account_selected)
```
   `set_account_runtime` 里：`if self._multi_session and runtime:` 改为 `if runtime:`，选中第一个账户并 `_switch_account`。
2. 新增账户管理回调槽 `set_on_account_manager(callback)` 与 `_on_account_manager_clicked`；`_wire_events` 接 `top_bar.set_on_account_manager(...)`。

- [ ] **Step 3: app.py 单模式构建账户运行时**

`_build_window` 单账户分支改为（**顺序：先建 window，再建 bridge 并注入钩子**，与多账户分支一致）：
```python
    if multi_session is None:
        # ---- 单账户模式：账户持久化，选择器切换 ----
        from src.services.account_registry import load_accounts

        window = MainWindow()
        bridge = WeChatBridge()
        bridge.find_window()
        bridge.set_hook_control(window.suspend_interrupt_hook, window.resume_interrupt_hook)
        window.set_bridge(bridge)

        runtime: dict[str, tuple] = {}
        for name in load_accounts():
            fs = FriendService.for_account(name)
            fs.load_cache()
            runtime[name] = (bridge, fs)
        window.set_account_runtime(runtime)
        window.set_send_callback(make_send_callback(window.get_current_bridge, template_engine, send_service))
        window.set_check_names_callback(make_check_names_callback(window.get_current_bridge, window.get_current_friend_service))
        window.set_search_contacts_callback(make_search_contacts_callback(window.get_current_bridge, window.get_current_friend_service))
        window.set_enter_multiopen_callback(lambda w=window: _enter_multiopen(w))
        return window
```

- [ ] **Step 4: 语法自检 + 手工验证（待用户）**

`python -c "from src.ui.main_window import MainWindow; from src.app import run_gui; print('ok')"` → `ok`
手工（真实微信）：启动单模式 → 顶部显示 `账户:[默认账户]` 且可下拉切换；切账户联系人列表变化；默认账户文件夹生成。

- [ ] **Step 5: Commit**

```bash
git add src/app.py src/ui/top_bar.py src/ui/main_window.py
git commit -m "feat: single-mode account switching with persisted accounts (selector always visible)"
```

---

### Task 4: 账户管理弹窗（新建 + 重命名/删除 + 双击切换）

**Files:**
- Create: `src/ui/account_manager_dialog.py`
- Modify: `src/ui/top_bar.py`（账户管理按钮，联系人右侧）
- Modify: `src/ui/main_window.py`（弹窗接线 + 切换/刷新）

- [ ] **Step 1: top_bar 加账户管理按钮（联系人右侧）**

`_build_ui` 在 `self._btn_contacts.pack(...)` 之后插入：
```python
        self._btn_account_mgr = ttk.Button(self, text="账户管理", width=6,
                                           command=self._make_cmd("_on_account_manager"))
        self._btn_account_mgr.pack(side=tk.LEFT, padx=(8, 0))
```
`set_enabled` 里把它加入禁用列表。

- [ ] **Step 2: 实现 account_manager_dialog.py（复用多开弹窗的列表风格）**

```python
"""账户管理弹窗 — 持久账户列表：新建/重命名/删除/双击切换

复用 multi_account_dialog 的 Treeview + 按钮行模式，但无窗口绑定。
双击某账户 → 切到该账户并关闭弹窗。
"""
import logging
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
from typing import Callable, Optional

from src.services import account_registry as reg
from src.services.friend_service import FriendService

logger = logging.getLogger(__name__)


class AccountManagerDialog(tk.Toplevel):

    def __init__(self, parent, current: str, on_switch: Optional[Callable[[str], None]] = None):
        super().__init__(parent)
        self.title("账户管理")
        self.geometry("360x320")
        self.resizable(False, False)
        self.transient(parent)
        self._current = current
        self._on_switch = on_switch      # (name) -> None，双击切换回调
        self._build_ui()
        self._refresh()

    def _build_ui(self):
        # Treeview：账户名 + 联系人数量
        frame = ttk.Frame(self, padding=10)
        frame.pack(fill=tk.BOTH, expand=True)
        cols = ("name", "count")
        self._tree = ttk.Treeview(frame, columns=cols, show="headings", height=10)
        self._tree.heading("name", text="账户名")
        self._tree.heading("count", text="联系人")
        self._tree.column("name", width=180)
        self._tree.column("count", width=60, anchor=tk.CENTER)
        self._tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self._tree.bind("<Double-1>", self._on_double_click)

        ops = ttk.Frame(self, padding=(10, 0, 10, 10))
        ops.pack(fill=tk.X)
        ttk.Button(ops, text="新建账户", command=self._on_create).pack(side=tk.LEFT)
        ttk.Button(ops, text="重命名", command=self._on_rename).pack(side=tk.LEFT, padx=4)
        ttk.Button(ops, text="删除", command=self._on_delete).pack(side=tk.LEFT)
        ttk.Button(ops, text="关闭", command=self.destroy).pack(side=tk.RIGHT)

    def _refresh(self):
        self._tree.delete(*self._tree.get_children())
        for name in reg.load_accounts():
            count = len(FriendService.for_account(name).all_friends)  # load_cache 前为空，需先 load
            fs = FriendService.for_account(name)
            fs.load_cache()
            self._tree.insert("", tk.END, values=(name, fs.count),
                              tags=("current",) if name == self._current else ())

    def _selected(self) -> Optional[str]:
        sel = self._tree.selection()
        if not sel:
            return None
        return self._tree.item(sel[0], "values")[0]

    def _on_double_click(self, _e=None):
        name = self._selected()
        if name and self._on_switch:
            self._on_switch(name)
            self.destroy()

    def _on_create(self):
        name = simpledialog.askstring("新建账户", "账户名:", parent=self)
        if not name or not name.strip():
            return
        name = name.strip()
        if name in reg.load_accounts():
            messagebox.showwarning("提示", "账户已存在。")
            return
        reg.save_accounts(reg.load_accounts() + [name])
        self._refresh()

    def _on_rename(self):
        old = self._selected()
        if not old:
            return
        new = simpledialog.askstring("重命名", "新账户名:", initialvalue=old, parent=self)
        if new and new.strip():
            if not reg.rename_account(old, new.strip()):
                messagebox.showwarning("提示", "重命名失败：账户不存在或重名。")
        self._refresh()

    def _on_delete(self):
        name = self._selected()
        if not name:
            return
        if name == reg.DEFAULT_ACCOUNT_NAME:
            messagebox.showinfo("提示", "默认账户不可删除。")
            return
        if not messagebox.askyesno("删除", f"确认删除账户 [{name}]？其联系人与校准数据将一并删除。"):
            return
        reg.delete_account(name)
        self._refresh()
```

- [ ] **Step 3: main_window 接线**

- 新增 `self._on_account_manager: Optional[Callable] = None` 槽 + `set_on_account_manager`。
- `_on_account_manager_clicked`：
```python
    def _on_account_manager_clicked(self) -> None:
        from src.ui.account_manager_dialog import AccountManagerDialog
        dlg = AccountManagerDialog(self.root, current=self._current_account_name() or "",
                                   on_switch=self._switch_account)
        dlg.grab_set()
```
- `_switch_account` 在切账户后刷新账户下拉（若账户列表变了）：
```python
    def _switch_account(self, name: str) -> None:
        if name not in self._account_runtime:
            return
        bridge, service = self._account_runtime[name]
        self.set_bridge(bridge)
        self.set_friend_service(service)
        self.friend_list.select_none()
        self.filter_bar.clear_filter()
```
- `app.py` 注入 `set_on_account_manager`（单/多模式都注入）。

- [ ] **Step 4: 语法自检**

`python -c "from src.ui.account_manager_dialog import AccountManagerDialog; print('ok')"` → `ok`

- [ ] **Step 5: Commit**

```bash
git add src/ui/account_manager_dialog.py src/ui/top_bar.py src/ui/main_window.py src/app.py
git commit -m "feat: account manager dialog (create/rename/delete/double-click switch)"
```

---

### Task 5: 设置对话框 —— 账户行常显可切换 + name_source 账户级

**Files:**
- Modify: `src/ui/settings_dialog.py`

- [ ] **Step 1: 账户行常显**

`_build_ui` 的账户行：删「全局（单账户）」disabled 分支，改为始终显示账户下拉：
```python
        self._account_combo = ttk.Combobox(
            acct_row, values=self._account_names or [self._account_name or ""],
            state="readonly", width=12)
        self._account_combo.set(self._account_name or "")
        self._account_combo.bind("<<ComboboxSelected>>", self._on_account_selected)
```
`SettingsDialog` 构造参数：`account_names` 由调用方传入（MainWindow `_open_settings` 改为传 `load_accounts()`，不再仅多模式）。

- [ ] **Step 2: name_source 账户级**

- `self._name_source` 初值从 `load_account_settings(self._account_name).get("name_source", "cache")` 读。
- `_on_close` 里 `name_source` 写入 `save_account_settings(self._account_name, {"name_source": ...})`；其余设置仍写全局 `save_settings`。
- `settings_dialog.py:97` 标签「缓存加载 (从 cache/friends.json 读取)」文案改「缓存加载」。

- [ ] **Step 3: 手工验证（待用户）**

设置 → 顶部账户下拉切换 → 各账户 name_source 独立；改 name_source 只影响当前账户。

- [ ] **Step 4: Commit**

```bash
git add src/ui/settings_dialog.py
git commit -m "feat: settings account row always usable; name_source per-account"
```

---

### Task 6: 多开引导改为绑定持久账户

**Files:**
- Modify: `src/ui/multi_account_dialog.py`
- Modify: `src/app.py`（多账户分支运行时已按账户名构建，基本不变）

- [ ] **Step 1: 引导弹窗选账户**

`_on_confirm_all`：不再用会话默认名「账户1/账户2」，改为每个窗口弹选择框让用户选**持久账户**（下拉列出 `load_accounts()` + 「＋新建账户…」）：
```python
    def _on_confirm_all(self):
        if not self._frames:
            messagebox.showwarning("提示", "请先点击「检测微信窗口」。")
            return
        accounts = reg.load_accounts()
        for i in range(len(self._frames)):
            hwnd, title, _cls = self._frames[i]
            if not self.bridge.activate_hwnd(hwnd):
                messagebox.showwarning("提示", f"无法激活窗口 0x{hwnd:X}（可能被前台锁定），跳过。")
                continue
            name = self._pick_account(i + 1, len(self._frames), accounts)
            if name is None:
                break
            if not self._session.add(name=name, hwnd=hwnd):
                messagebox.showwarning("提示", f"窗口已绑定给 [{name}]，或名称冲突。")
        self._refresh_tree()

    def _pick_account(self, idx: int, total: int, accounts: list[str]) -> Optional[str]:
        """弹选择框：已有账户 + 新建账户"""
        dlg = tk.Toplevel(self.root)
        dlg.title(f"窗口 {idx}/{total} 绑定账户")
        dlg.transient(self.root)
        dlg.grab_set()
        var = tk.StringVar(value=accounts[0] if accounts else "")
        ttk.Label(dlg, text="当前前台微信窗口属于哪个账户？").pack(pady=8)
        combo = ttk.Combobox(dlg, textvariable=var, values=accounts + ["＋ 新建账户…"],
                             state="readonly", width=16)
        combo.pack(padx=12, pady=4)
        result = [None]
        def _ok():
            v = var.get()
            if v == "＋ 新建账户…":
                n = simpledialog.askstring("新建账户", "账户名:", parent=dlg)
                if n and n.strip():
                    n = n.strip()
                    reg.save_accounts(accounts + [n])
                    accounts.append(n)
                    result[0] = n
                    dlg.destroy()
                return
            if v:
                result[0] = v
                dlg.destroy()
        ttk.Button(dlg, text="确定", command=_ok).pack(pady=6)
        dlg.wait_window()
        return result[0]
```
注意：`_session.add(name, hwnd)` 的去重现在按持久账户名；同名窗口不能重复绑（Task 2 已有 sanitize/hwnd 去重）。

- [ ] **Step 2: app.py 多账户分支确认**

`_build_window` 多账户分支已用 `FriendService.for_account(acc.name)` → 现在是持久账户文件夹，无需改；确认 `runtime` 构建与 `_switch_account` 一致。

- [ ] **Step 3: 手工验证（待用户）**

多开 → 引导弹「绑定账户」下拉 → 选已有账户/新建 → 多账户模式各窗口用对应账户数据。

- [ ] **Step 4: Commit**

```bash
git add src/ui/multi_account_dialog.py
git commit -m "feat: multi-open wizard binds windows to persisted accounts"
```

---

### Task 7: UI 微调 —— 删除按钮宽度

**Files:**
- Modify: `src/ui/friend_list.py`

- [ ] **Step 1: 找删除按钮并改宽度**

`friend_list.py` 里好友列表操作行（➕/反选/删除）。当前删除按钮 `[  删除  ]` 偏宽，改为与「反选」同尺寸（`width=4` 左右，和反选一致）。先读文件定位，改 `ttk.Button(..., text="删除", width=N)` 的 N 与反选一致。

- [ ] **Step 2: 语法自检 + Commit**

`python -c "from src.ui.friend_list import FriendList; print('ok')"` → `ok`
```bash
git add src/ui/friend_list.py
git commit -m "fix: delete button width matches deselect button"
```

---

### Task 8: UI 细节批次（Toggle 菜单 / 标签顺序 / OCR 布局 / 关闭按钮）

**Files:**
- Modify: `src/ui/top_bar.py`（[标签][联系人] toggle）
- Modify: `src/ui/filter_bar.py`（`标签:[全部]` 顺序）
- Modify: `src/ui/settings_dialog.py`（OCR 布局 + 关闭按钮）

- [ ] **Step 1: top_bar [标签][联系人] 加 toggle（点开/再点/旁边点击收起）**

两个 Menubutton 改为手动 toggle：
```python
    def _build_ui(self):
        ...
        self._btn_contacts["menu"] = contacts_menu
        self._btn_tags["menu"] = tags_menu
        self._open_menu: Optional[tk.Menu] = None
        self._btn_contacts.bind("<Button-1>", lambda e: self._toggle_menu(self._btn_contacts, contacts_menu))
        self._btn_tags.bind("<Button-1>", lambda e: self._toggle_menu(self._btn_tags, tags_menu))
        # 点击其它任意处收起
        self.winfo_toplevel().bind("<Button-1>", self._close_open_menu, add="+")

    def _toggle_menu(self, btn: ttk.Menubutton, menu: tk.Menu) -> None:
        """点开/收起：再点同一按钮收起，点另一按钮切过去"""
        if self._open_menu is menu:
            self._close_open_menu()
            return
        self._close_open_menu()
        self._open_menu = menu
        menu.post(btn.winfo_rootx(), btn.winfo_rooty() + btn.winfo_height())

    def _close_open_menu(self, event=None) -> None:
        """收起已打开的菜单。点击 Menubutton 自身时跳过（让 toggle 处理）。"""
        if event is not None:
            w = getattr(event, "widget", None)
            if isinstance(w, ttk.Menubutton):
                return
        if self._open_menu is not None:
            try:
                self._open_menu.unpost()
            except tk.TclError:
                pass
            self._open_menu = None
```
注意：tkinter bindtags 顺序 widget→class→toplevel→all，按钮自身 `<Button-1>` 先于 toplevel 触发，`_close_open_menu` 用 `isinstance(w, ttk.Menubutton)` 跳过自身即可保证 toggle 不被 toplevel 绑定立刻关掉。

- [ ] **Step 2: filter_bar 标签顺序改为 `标签:[全部] 匹配x/x人`**

`_build_ui` 里 `标签:` label 与 `_tag_combo` 的 pack 顺序交换（先 pack combo、再 pack label），使显示顺序为 `标签:[全部]`；匹配计数保持最右：
```python
        self._tag_combo.pack(side=tk.RIGHT, padx=(0, 4))   # 先 pack → 靠右
        ttk.Label(row, text="标签:").pack(side=tk.RIGHT, padx=(0, 2))  # 后 pack → 在 combo 左边
```
（匹配计数 `_label_match` 仍最先 pack、最右。）

- [ ] **Step 3: 设置→OCR 布局**

1. 删「测试：通讯录 → 通讯录管理 → 滚一页」按钮（`_run_test` 的 button，约 131-132 行）。
2. 三个 OCR 校准按钮（校准聊天界面标题 / 校准通讯录区域 / OCR 校准重置）移到 tab **顶部**。
3. OCR tab 改为**可滚动布局**（复用坐标 tab 的 Canvas + Scrollbar + `_bind_mousewheel` 模式，见 `_build_coord_tab` 约 313-391 行）。

- [ ] **Step 4: 设置窗口 [关闭] 按钮窗口较小时不被折叠**

`_build_ui` 底部按钮行改为始终贴底可见：`btn_frame.pack(fill=tk.X, side=tk.BOTTOM, padding=12)`（明确 `side=tk.BOTTOM`），并确保 notebook 的 `minsize` 不把按钮行挤出窗口。若 OCR tab 引入 Canvas 后内容撑大，把 `nb.pack` 的 `expand=True` 保留、按钮行固定贴底。

- [ ] **Step 5: 语法自检**

`python -c "from src.ui.top_bar import TopBar; from src.ui.filter_bar import FilterBar; from src.ui.settings_dialog import SettingsDialog; print('ok')"` → `ok`

- [ ] **Step 6: 手工验证（待用户）**

点 [联系人] 展开 → 再点收起；点旁边收起；点 [标签] 切换。筛选栏显示 `标签:[全部]`。设置→OCR 可滚动、校准按钮在顶、无测试按钮；窗口缩小时 [关闭] 仍可见。

- [ ] **Step 7: Commit**

```bash
git add src/ui/top_bar.py src/ui/filter_bar.py src/ui/settings_dialog.py
git commit -m "feat: toggle menubuttons, tag label order, OCR tab scrollable, close button always visible"
```

---

### Task 9: 搜一搜功能彻底清理

**Files:**
- Modify: `src/utils/settings_store.py`
- Modify: `src/ui/settings_dialog.py`
- Modify: `src/driver/wechat_bridge.py`
- Modify: `src/utils/coordinates.py`
- Modify: `src/ui/coord_picker.py`

- [ ] **Step 1: settings_store** — 删 `DEFAULT_SETTINGS` 里的 `"sousou_independent_enabled": False`。
- [ ] **Step 2: settings_dialog** — 删 `self._sousou_independent` var（56 行）、「搜一搜」Checkbutton（97-99 行）、`_on_close` 里 `self._settings["sousou_independent_enabled"] = ...`（203 行）。
- [ ] **Step 3: wechat_bridge** — 删 `_click_sousou_independent_btn` 方法（480-497 行）及其调用（`search_contacts` 里 473 行）。
- [ ] **Step 4: coordinates** — 删 `DEFAULT_COORDINATES["sousou_independent_btn"]`（31 行）、`COORD_LABELS["sousou_independent_btn"]`（46 行）、COORD_GROUPS 里的 `("搜一搜", [...])` 整组（54 行）。
- [ ] **Step 5: coord_picker** — 删 `"sousou_independent_btn": "搜一搜独立窗口按钮.png"`（23 行）。
- [ ] **Step 6: 语法自检 + 回归**

`python -c "from src.driver.wechat_bridge import WeChatBridge; from src import operations; from src.ui.settings_dialog import SettingsDialog; print('ok')"` → `ok`
grep `sousou` → 无残留（除文档）。
`python -m pytest tests/ -q` → 全过

- [ ] **Step 7: Commit**

```bash
git add src/utils/settings_store.py src/ui/settings_dialog.py src/driver/wechat_bridge.py src/utils/coordinates.py src/ui/coord_picker.py
git commit -m "chore: remove sousou independent-window feature (settings/coord/bridge/coord_picker)"
```

---

### Task 10: 全量回归 + 文档收尾

- [ ] **Step 1:** `python -m pytest tests/ -q` → 全过
- [ ] **Step 2:** `git status --short` → 干净（除新生成的 cache/ 测试产物，gitignore 忽略）
- [ ] **Step 3:** 更新 `docs/superpowers/specs/2026-08-10-multi-account-broadcast-design.md` §12 追加「账户系统重构批次」小节（存储结构、决策、新文件）。
- [ ] **Step 4:** 手工回归清单（需真实微信，交给用户）：
  1. 单模式：账户切换、默认账户「默认账户」、各账户联系人独立
  2. 账户管理弹窗：新建/重命名/删除/双击切换
  3. 多开：引导绑定到已有账户/新建 → 各窗口用对应账户数据
  4. 设置：账户行切换、name_source 账户级、坐标/校准按账户读写
  5. 搜一搜功能消失（设置无该项、坐标无搜一搜组）
  6. 删除按钮宽度、账户选择器标签顺序
- [ ] **Step 5:** Commit 文档
```bash
git add docs/superpowers/specs/2026-08-10-multi-account-broadcast-design.md
git commit -m "docs: record account-system refactor in multi-account spec"
```

---

## 测试策略

- **纯层（pytest）**：account_paths（文件夹路径/sanitize）、account_registry（默认账户兜底/重命名移文件夹/删除/禁删默认）、coordinates/calibration（账户文件回退默认、账户隔离）、settings_store 账户级（与全局隔离）。
- **UI/win32（手工）**：单模式账户切换、账户管理弹窗、多开绑持久账户、设置账户行、搜一搜清理、删除按钮宽度。

## 注意（与现有行为的差异）

- 旧 `cache/friends.json` 等全局文件不再使用；现有测试里「全局文件」相关断言需重写。
- `load_coordinates`/`load_calibration`/`calibration_has_key` 的 `account_name` 参数**不再允许 None**（无全局概念）——调用方传当前账户名。
- `set_account_runtime` 单模式也会被调用 → `_switch_account`/账户选择器语义统一。
- 多开窗口绑定仍会话级；账户数据（联系人/校准）来自持久账户文件夹，两模式一致。
