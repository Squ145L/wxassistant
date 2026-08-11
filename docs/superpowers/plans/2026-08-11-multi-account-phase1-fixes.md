# 多开阶段 1 修复计划（review 12 项 + 分层合规）

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复 2026-08-10 代码 review 发现的所有问题（5 项 Important + 7 项 Minor + 测试缺口），并顺手清理触碰代码里的 `CODING_STANDARDS.md` 违规（ui→driver import、函数内 import、裸 except），为阶段 2 流水线并发打底。

**Architecture:** 校准读写抽成纯层 `src/utils/calibration.py`（全局 → 账户两级回退，语义与 `coordinates.py::load_coordinates` 一致），四处读取方统一接入。跨账户操作期间锁定账户下拉防止结果串账户。多开引导去掉 ui→driver 依赖、激活加前台校验。`app.py` 改为顶层模式循环，消除嵌套 mainloop。sanitize 碰撞、rename 越界、设置误冻结、save_cache 异步写等逐项修复。

**Tech Stack:** Python 3.10+、tkinter、win32gui、pytest（纯逻辑层测试）

**设计文档:** `docs/superpowers/specs/2026-08-10-multi-account-broadcast-design.md` §12（review 依据 `docs/superpowers/plans/2026-08-10-multi-account-phase1.md` 交付后的 review 报告）

---

## 前置现状（实现者须知）

- 项目根 `E:\Claudeproject\wxassistant`，分支 `feature/multi-account-phase1`，工作区干净。所有命令在该根运行（bash / PowerShell 均可）。
- 现有测试 32 个全过。纯逻辑（services/utils）用 pytest 测；win32/UI 改动手工验证。
- 遵循 `CODING_STANDARDS.md`：依赖单向（ui→services→driver）、异常不可静默、禁函数内 import、魔法数字进 `config.py`、中文三级 docstring、类型标注、双引号。
- `src/ui/multi_account_dialog.py:16` 是规范点名反例（ui import driver），本次一并修。
- review 完整报告在项目根 `.review_report.md`（本计划完成后删除）。

**修复对照表**

| # | 严重度 | 问题 | 任务 |
|---|--------|------|------|
| 1 | Important | OCR 校准不回退全局（违反决策 #6） | Task 1 |
| 2 | Important | 扫描/检查中途切账户 → 结果串账户 | Task 3 |
| 3 | Important | sanitize 碰撞合并两个账户数据文件 | Task 2 |
| 4 | Important | 开设置不编辑就关闭 → 账户被动变专属 | Task 4 |
| 5 | Important | `_ensure_calibration` 只看全局文件 | Task 5 |
| 6 | Minor | `rename` 缺越界保护 | Task 2 |
| 7 | Minor | 引导激活不校验前台 + add 不防重复 hwnd | Task 6 |
| 8 | Minor | 引导续确认默认名撞名 + 重检测不重置会话 | Task 6 |
| 9 | Minor | `_enum2` 标题兜底移除（回归提示） | Task 10 验证 |
| 10 | Minor | 嵌套 mainloop（多开↔单用户往返） | Task 7 |
| 11 | Minor | 账户切换残留筛选文字 | Task 8 |
| 12 | Minor | `save_cache` 异步 daemon 写（丢最后保存） | Task 9 |

---

### Task 0: 测试基线确认

- [ ] **Step 1: 跑现有测试**

Run: `python -m pytest tests/ -v`
Expected: `32 passed`

- [ ] **Step 2: 确认工作区干净**

Run: `git status --short`
Expected: 仅 `.review_report.md`（未跟踪，本计划最后删除）

---

### Task 1: OCR 校准统一模块（#1）

**Files:**
- Create: `src/utils/calibration.py`
- Modify: `src/driver/wechat_bridge.py`（`_get_chat_title_rect`、删 `_calibration_path` 与 `DEFAULT_CHAT_TITLE_CALIB`）
- Modify: `src/operations.py`（`_load_calibration` 删除，改调用）
- Modify: `calibrate_ocr.py`（`load_config/save_config/do_reset` 接入）
- Modify: `src/ui/settings_dialog.py`（`_reset_ocr` 接入）
- Test: `tests/test_calibration.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_calibration.py
from src.utils import account_paths as ap
from src.utils import calibration as cal


def test_load_returns_default_when_no_files(tmp_path, monkeypatch):
    monkeypatch.setattr(ap, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(cal, "OCR_CALIBRATION_PATH", tmp_path / "ocr_calibration.json")
    c = cal.load_calibration("chat_title", "账户1")
    assert c["LEFT_MARGIN"] == cal.DEFAULT_CALIBRATION["chat_title"]["LEFT_MARGIN"]


def test_global_file_applies(tmp_path, monkeypatch):
    monkeypatch.setattr(ap, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(cal, "OCR_CALIBRATION_PATH", tmp_path / "ocr_calibration.json")
    cal.save_calibration("chat_title", {"LEFT_MARGIN": 0.2}, None)
    c = cal.load_calibration("chat_title", "账户1")   # 账户无文件 → 继承全局
    assert c["LEFT_MARGIN"] == 0.2


def test_account_overrides_global(tmp_path, monkeypatch):
    monkeypatch.setattr(ap, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(cal, "OCR_CALIBRATION_PATH", tmp_path / "ocr_calibration.json")
    cal.save_calibration("chat_title", {"LEFT_MARGIN": 0.2}, None)
    cal.save_calibration("chat_title", {"LEFT_MARGIN": 0.9}, "账户1")
    c = cal.load_calibration("chat_title", "账户1")
    assert c["LEFT_MARGIN"] == 0.9
    g = cal.load_calibration("chat_title", None)
    assert g["LEFT_MARGIN"] == 0.2     # 全局不受账户影响


def test_account_without_file_falls_back_to_global(tmp_path, monkeypatch):
    monkeypatch.setattr(ap, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(cal, "OCR_CALIBRATION_PATH", tmp_path / "ocr_calibration.json")
    cal.save_calibration("contacts_list", {"BOTTOM_MARGIN": 0.1}, None)
    c = cal.load_calibration("contacts_list", "账户2")
    assert c["BOTTOM_MARGIN"] == 0.1


def test_calibration_has_key_false_when_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(ap, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(cal, "OCR_CALIBRATION_PATH", tmp_path / "ocr_calibration.json")
    assert not cal.calibration_has_key("chat_title", "账户1")


def test_calibration_has_key_true_via_global(tmp_path, monkeypatch):
    monkeypatch.setattr(ap, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(cal, "OCR_CALIBRATION_PATH", tmp_path / "ocr_calibration.json")
    cal.save_calibration("chat_title", {"LEFT_MARGIN": 0.2}, None)
    assert cal.calibration_has_key("chat_title", "账户1")   # 继承全局也算已校准
    assert cal.calibration_has_key("chat_title", None)


def test_save_isolates_accounts(tmp_path, monkeypatch):
    monkeypatch.setattr(ap, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(cal, "OCR_CALIBRATION_PATH", tmp_path / "ocr_calibration.json")
    cal.save_calibration("chat_title", {"LEFT_MARGIN": 0.5}, "账户A")
    cal.save_calibration("chat_title", {"LEFT_MARGIN": 0.6}, "账户B")
    assert cal.load_calibration("chat_title", "账户A")["LEFT_MARGIN"] == 0.5
    assert cal.load_calibration("chat_title", "账户B")["LEFT_MARGIN"] == 0.6


def test_reset_removes_key(tmp_path, monkeypatch):
    monkeypatch.setattr(ap, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(cal, "OCR_CALIBRATION_PATH", tmp_path / "ocr_calibration.json")
    cal.save_calibration("chat_title", {"LEFT_MARGIN": 0.5}, "账户1")
    cal.reset_calibration("chat_title", "账户1")
    assert not cal.calibration_has_key("chat_title", "账户1")
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest tests/test_calibration.py -v`
Expected: FAIL（ModuleNotFoundError: src.utils.calibration）

- [ ] **Step 3: 实现 src/utils/calibration.py**

```python
"""OCR 校准参数读写 — 全局 + 账户覆盖两级回退（与 coordinates.load_coordinates 同款语义）"""

import json
import logging
from pathlib import Path
from typing import Optional

from src.utils.account_paths import calibration_path_for

logger = logging.getLogger(__name__)

# 全局校准文件路径（相对项目根，与全项目 Path("cache/...") 风格一致）
OCR_CALIBRATION_PATH = Path("cache/ocr_calibration.json")

# 各区域默认校准参数（窗口内百分比；LEFT/RIGHT_MARGIN >1 = 旧格式像素，兼容）
DEFAULT_CALIBRATION: dict[str, dict[str, float]] = {
    "chat_title": {
        "LEFT_MARGIN": 0.05, "TOP_PCT": 0.015, "RIGHT_MARGIN": 0.06, "BOTTOM_MARGIN": 0.91,
    },
    "search_panel": {
        "LEFT_MARGIN": 0.03, "TOP_PCT": 0.08, "RIGHT_MARGIN": 0.03, "BOTTOM_MARGIN": 0.30,
    },
    "contacts_list": {
        "LEFT_MARGIN": 0.03, "TOP_PCT": 0.25, "RIGHT_MARGIN": 0.26, "BOTTOM_MARGIN": 0.05,
    },
}


def _calibration_path(account_name: Optional[str] = None) -> Path:
    """账户专属校准文件路径；account_name 为空用全局文件"""
    if account_name:
        return calibration_path_for(account_name)
    return OCR_CALIBRATION_PATH


def _apply_key(merged: dict, path: Path, key: str) -> None:
    """把某个区域参数合并进 merged（文件存在才读）"""
    if not path.exists():
        return
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        params = data.get(key)
        if isinstance(params, dict):
            merged.update(params)
    except Exception:
        logger.warning("OCR 校准文件读取失败，使用默认值: %s", path, exc_info=True)


def load_calibration(key: str, account_name: Optional[str] = None) -> dict:
    """加载某区域校准参数：全局文件 → 账户专属文件覆盖 → 默认值兜底"""
    merged = dict(DEFAULT_CALIBRATION.get(key, {}))
    _apply_key(merged, OCR_CALIBRATION_PATH, key)                     # 全局
    if account_name:
        _apply_key(merged, calibration_path_for(account_name), key)   # 账户覆盖
    return merged


def calibration_has_key(key: str, account_name: Optional[str] = None) -> bool:
    """该账户（或继承的全局）是否已校准过指定区域"""
    paths = [OCR_CALIBRATION_PATH]
    if account_name:
        paths.append(calibration_path_for(account_name))
    for path in paths:
        if not path.exists():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data.get(key), dict):
                return True
        except Exception:
            logger.warning("OCR 校准文件读取失败: %s", path, exc_info=True)
    return False


def save_calibration(key: str, params: dict, account_name: Optional[str] = None) -> None:
    """保存某区域校准参数（账户专属或全局）"""
    path = _calibration_path(account_name)
    path.parent.mkdir(parents=True, exist_ok=True)
    existing: dict = {}
    if path.exists():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            logger.warning("OCR 校准文件读取失败，将覆盖: %s", path, exc_info=True)
    existing[key] = params
    path.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("OCR 校准已保存: %s [%s]", path, key)


def reset_calibration(key: Optional[str] = None, account_name: Optional[str] = None) -> None:
    """重置校准参数（key 为空 = 清空整个文件）"""
    path = _calibration_path(account_name)
    if not path.exists():
        return
    existing: dict = {}
    if key is not None:
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
            existing.pop(key, None)
        except Exception:
            logger.warning("OCR 校准文件读取失败: %s", path, exc_info=True)
    path.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("OCR 校准已重置: %s [%s]", path, key or "全部")
```

- [ ] **Step 4: 运行确认通过**

Run: `python -m pytest tests/test_calibration.py -v`
Expected: `8 passed`

- [ ] **Step 5: wechat_bridge 接入 + 删除冗余常量**

`src/driver/wechat_bridge.py`：
1. 删模块级 `DEFAULT_CHAT_TITLE_CALIB`（约 41-46 行）。
2. 删模块级 `OCR_CALIBRATION_PATH`（第 31 行）——`_calibration_path` 删除后它不再被引用（死代码），且与 `calibration.py` 的 `OCR_CALIBRATION_PATH` 概念重复。
3. 删方法 `_calibration_path`（约 341-346 行）。
4. `import json` **保留**（`_load_confusion_map` 约 324 行仍用）。
5. `_get_chat_title_rect`（约 348-367 行）整体替换为：

```python
    def _get_chat_title_rect(self) -> Optional[Tuple[int, int, int, int]]:
        """获取聊天标题区域的屏幕坐标（按校准参数从窗口推算）"""
        rect = self.get_window_rect()
        if rect is None:
            return None

        # 校准参数：账户专属覆盖全局，再回退默认值
        calib = load_calibration("chat_title", self._account_name)
        result = resolve_calibration_rect(calib, rect)
        logger.debug("聊天标题区域: (%d,%d)-(%d,%d)", *result)
        return result
```

并在文件顶部 src.utils import 段（`resolve_calibration_rect` 导入处）加一行：

```python
from src.utils.calibration import load_calibration
```

- [ ] **Step 6: operations.py 删 `_load_calibration` 改直调**

`src/operations.py`：
1. 删函数 `_load_calibration`（约 359-375 行）。该函数是 `import json` 的唯一使用处 → 同时删文件顶部 `import json`（第 7 行）。
2. 文件顶部 src.utils import 段加一行：

```python
from src.utils.calibration import load_calibration
```

3. 调用处（212 行）`calib = _load_calibration("contacts_list", bridge.account_name)` 改为：

```python
    calib = load_calibration("contacts_list", bridge.account_name)
```

**行为变化（顺带修复的隐藏 bug，不是回归）**：原 `_load_calibration`（363 行）对**所有 key** 都用 `DEFAULT_CHAT_TITLE_CALIB`（chat_title 的值）当默认——即 `contacts_list` 无文件时用的是 0.05/0.015/0.06/0.91，而非 contacts_list 自己的 0.03/0.25/0.26/0.05。换成 `load_calibration(key, ...)` 后各区域默认值各自正确。若用户观察到扫描区域默认框选位置变了，这是修复。附带收益：删掉的 `_load_calibration` 里 362 行 `from src.driver.wechat_bridge import DEFAULT_CHAT_TITLE_CALIB` 是跨层 import（operations→driver），一并清除。

- [ ] **Step 7: calibrate_ocr.py 接入**

`calibrate_ocr.py`：
1. 删局部 `DEFAULTS`（约 39-52 行），文件顶部 import 段加：

```python
from src.utils.calibration import DEFAULT_CALIBRATION, load_calibration, save_calibration, reset_calibration
```

并把 DEFAULTS 改为从校准模块派生（保留 desc 供界面标题）：

```python
_DESC = {"chat_title": "聊天标题栏", "search_panel": "搜索面板", "contacts_list": "通讯录列表"}
DEFAULTS = {k: {**v, "desc": _DESC.get(k, k)} for k, v in DEFAULT_CALIBRATION.items()}
```

2. 删 `_config_path`（约 32-37 行）、`load_config`（约 75-83 行）、`save_config`（约 86-93 行），替换为：

```python
def load_config(key: str) -> dict:
    """加载校准参数：全局 → 账户（--account）→ 默认"""
    return load_calibration(key, ACCOUNT)


def save_config(key: str, params: dict) -> None:
    save_calibration(key, params, ACCOUNT)
```

3. `do_reset`（约 218-229 行）主体替换为：

```python
    def do_reset():
        if messagebox.askyesno("重置", f"确认删除 [{key}] 的校准参数？"):
            reset_calibration(key, ACCOUNT)
            messagebox.showinfo("已重置", f"区域 [{key}] 已重置。")
```

注意：`calibrate_ocr.py` 以子进程运行（cwd=项目根），`import src.*` 依赖 cwd 在 sys.path，与原 `_config_path` 内 `from src.utils.account_paths import ...` 行为一致。

- [ ] **Step 8: settings_dialog._reset_ocr 接入**

`src/ui/settings_dialog.py`：
1. 文件顶部 import 段（`src.utils.settings_store` 导入处）加：

```python
from src.utils.calibration import reset_calibration
```

2. `_reset_ocr`（约 273-283 行）主体替换为：

```python
    def _reset_ocr(self) -> None:
        if not messagebox.askyesno("OCR 校准重置", "确认清除所有 OCR 校准参数？"):
            return
        reset_calibration(None, self._account_name)
        messagebox.showinfo("已重置", "OCR 校准参数已清除。")
```

- [ ] **Step 9: 语法自检**

Run: `python -c "from src.driver.wechat_bridge import WeChatBridge; from src import operations; print('ok')"`
Expected: `ok`

- [ ] **Step 10: 全量测试**

Run: `python -m pytest tests/ -v`
Expected: `40 passed`（32 + 8）

- [ ] **Step 11: Commit**

```bash
git add src/utils/calibration.py tests/test_calibration.py src/driver/wechat_bridge.py src/operations.py calibrate_ocr.py src/ui/settings_dialog.py
git commit -m "fix: OCR calibration two-level fallback (global→account) via unified calibration module"
```

---

### Task 2: sanitize 碰撞去重 + rename 边界（#3 #6）

**Files:**
- Modify: `src/services/multi_account.py`
- Test: `tests/test_multi_account.py`

- [ ] **Step 1: 写失败测试（追加到 tests/test_multi_account.py 末尾）**

```python
def test_add_rejects_sanitized_duplicate():
    # "A:B" 与 "A/B" 都折叠为 "A_B"，会共用同一数据文件，必须拒绝
    s = MultiAccountSession()
    assert s.add("A:B", 0x1)
    assert not s.add("A/B", 0x2)
    assert s.count == 1


def test_add_rejects_duplicate_hwnd():
    s = MultiAccountSession()
    assert s.add("账户1", 0x10000)
    assert not s.add("账户2", 0x10000)   # 同一窗口不能绑两次
    assert s.count == 1


def test_rename_rejects_sanitized_duplicate():
    s = MultiAccountSession()
    s.add("A:B", 0x1)
    s.add("账户2", 0x2)
    assert not s.rename(1, "A/B")
    assert s.accounts[1].name == "账户2"


def test_rename_out_of_range_returns_false():
    s = MultiAccountSession()
    s.add("账户1", 0x1)
    assert not s.rename(5, "新名")       # 不应抛 IndexError
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest tests/test_multi_account.py -v`
Expected: `4 failed`（`add` 接受了 sanitize 冲突/重复 hwnd；`rename` 越界抛 IndexError）

- [ ] **Step 3: 实现 multi_account.py**

`src/services/multi_account.py` 的 `add` 与 `rename` 改为：

```python
    def _sanitized(self, name: str) -> str:
        """账户名对应的文件片段（与 account_paths.sanitize_account_name 一致）"""
        from src.utils.account_paths import sanitize_account_name
        return sanitize_account_name(name)

    def _sanitize_conflicts(self, name: str, exclude_order: Optional[int] = None) -> bool:
        """该名字的 sanitize 片段是否与其它账户冲突（排除 exclude_order）"""
        frag = self._sanitized(name)
        return any(
            a.order != exclude_order and self._sanitized(a.name) == frag
            for a in self._accounts
        )

    def add(self, name: str, hwnd: int) -> bool:
        """追加一个账户。账户名重复/为空/sanitize 冲突/hwnd 重复返回 False"""
        name = name.strip()
        if not name:
            return False
        if any(a.hwnd == hwnd for a in self._accounts):
            return False
        if any(a.name == name for a in self._accounts) or self._sanitize_conflicts(name):
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
        """重命名指定账户。越界/重名/sanitize 冲突/为空返回 False"""
        if not 0 <= index < len(self._accounts):
            return False
        new_name = new_name.strip()
        if not new_name:
            return False
        if any(a.name == new_name for a in self._accounts
               if a.order != index):
            return False
        if self._sanitize_conflicts(new_name, exclude_order=index):
            return False
        old = self._accounts[index]
        self._accounts[index] = AccountWindow(name=new_name, hwnd=old.hwnd, order=old.order)
        return True
```

注意：文件顶部 `from typing import Optional` 已在（约 3 行）。新增的 `_sanitized/_sanitize_conflicts` 为私有方法，`rename` 中原先 `a.order != self._accounts[index].order` 的判断改为与入参 `index` 比较（重编号不变量保证 order==index）。

- [ ] **Step 4: 运行确认通过**

Run: `python -m pytest tests/test_multi_account.py -v`
Expected: `18 passed`（现有 14 + 新增 4）

- [ ] **Step 5: 全量测试**

Run: `python -m pytest tests/ -v`
Expected: `44 passed`

- [ ] **Step 6: Commit**

```bash
git add src/services/multi_account.py tests/test_multi_account.py
git commit -m "fix: reject sanitize-colliding account names + duplicate hwnd; guard rename bounds"
```

---

### Task 3: 跨账户操作锁定（#2）

**Files:**
- Modify: `src/ui/top_bar.py`
- Modify: `src/ui/main_window.py`

- [ ] **Step 1: TopBar 加 set_account_enabled，set_enabled 复用**

`src/ui/top_bar.py` 在 `set_enabled` 之后插入：

```python
    def set_account_enabled(self, enabled: bool) -> None:
        """仅禁用账户下拉（检查/搜索/导入操作期间防切账户导致结果串账户）

        set_enabled = 全部控件；本方法 = 只锁账户下拉。
        """
        if not self._multi:
            return
        self._account_combo.config(state="readonly" if enabled else tk.DISABLED)
```

并把 `set_enabled` 里重复的账户下拉行（147-148 行）改为复用，消除重复逻辑：

```python
    def set_enabled(self, enabled: bool) -> None:
        """发送中禁用顶栏按钮（防止中途切换账户/操作）"""
        state = tk.NORMAL if enabled else tk.DISABLED
        self._btn_refresh.config(state=state)
        self._btn_settings.config(state=state)
        self._btn_help.config(state=state)
        self._btn_multiopen.config(state=state)
        self._btn_contacts.config(state=state)
        self._btn_tags.config(state=state)
        self.set_account_enabled(enabled)
```

- [ ] **Step 2: MainWindow 加操作锁定辅助**

`src/ui/main_window.py` 在 `_set_ui_sending` 之后插入：

```python
    def _set_ops_active(self, active: bool) -> None:
        """检查/搜索/导入操作期间锁定账户选择器，防止用户中途切换账户"""
        self.top_bar.set_account_enabled(active)
```

- [ ] **Step 3: 三个操作入口启动时锁定**

`_on_check_names_clicked`（约 384 行）在 `self._stop_event = threading.Event()` 之前插入：
```python
        self._set_ops_active(False)
```

`_on_search_contacts_clicked`（约 398 行）在 `self._stop_event = threading.Event()` 之前插入：
```python
        self._set_ops_active(False)
```

`_on_import_all_clicked`（约 417 行）在 `self._stop_event = threading.Event()` 之前插入：
```python
        self._set_ops_active(False)
```

- [ ] **Step 4: 操作结束时解锁**

`__NAME_CHECK_DONE__` 分支（约 862 行）在 `self._interrupt_poll_active = False` 之后插入：
```python
            self._set_ops_active(True)
```

`__INTERRUPT_OFF__` 分支（约 837 行）在 `self._stop_event = None` 之后插入：
```python
            self._set_ops_active(True)
```

说明：三个操作的统一结束信号是 `__NAME_CHECK_DONE__`（异常/中断路径也都会 post），`__INTERRUPT_OFF__` 兜底早退分支。重复解锁是幂等的。

- [ ] **Step 5: 语法自检**

Run: `python -c "from src.ui.main_window import MainWindow; from src.ui.top_bar import TopBar; print('ok')"`
Expected: `ok`

- [ ] **Step 6: 手工验证（需真实多开）**

`python main.py` → 多开绑定 2 账户 → 账户1 点 [扫描并导入] → 扫描期间确认账户下拉变灰不可切 → 完成后恢复可切。
Expected: 扫描/OCR 期间账户下拉禁用；结果落在账户1 的文件（`cache/friends_账户1.json`）。

- [ ] **Step 7: Commit**

```bash
git add src/ui/top_bar.py src/ui/main_window.py
git commit -m "fix: lock account selector during check/search/import ops to prevent cross-account results"
```

---

### Task 4: 设置关闭不冻结账户（#4）

**Files:**
- Modify: `src/utils/coordinates.py`
- Modify: `src/ui/settings_dialog.py`
- Test: `tests/test_coordinates_account.py`

- [ ] **Step 1: 写失败测试（追加到 tests/test_coordinates_account.py 末尾）**

```python
def test_account_has_override_false_by_default(tmp_path, monkeypatch):
    monkeypatch.setattr(ap, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(coord, "COORDINATES_PATH", tmp_path / "coordinates.json")
    assert not coord.account_has_override("账户1")
    assert not coord.account_has_override(None)


def test_account_has_override_true_after_save(tmp_path, monkeypatch):
    monkeypatch.setattr(ap, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(coord, "COORDINATES_PATH", tmp_path / "coordinates.json")
    coord.save_coordinates({"tab_chat": (0.5, 0.5)}, "账户1")
    assert coord.account_has_override("账户1")
    assert not coord.account_has_override("账户2")


def test_should_save_coordinates_unchanged_skip(tmp_path):
    loaded = {"tab_chat": (0.5, 0.5), "safe_zone": (0.3, 0.6)}
    assert not coord.should_save_coordinates(dict(loaded), loaded, False)


def test_should_save_coordinates_changed_saves(tmp_path):
    loaded = {"tab_chat": (0.5, 0.5)}
    assert coord.should_save_coordinates({"tab_chat": (0.6, 0.5)}, loaded, False)


def test_should_save_coordinates_existing_override_saves(tmp_path):
    loaded = {"tab_chat": (0.5, 0.5)}
    # 已有专属文件 → 即使未改动也要保存（更新专属文件）
    assert coord.should_save_coordinates(dict(loaded), loaded, True)


def test_should_save_coordinates_precision_tolerant(tmp_path):
    # 显示层 4 位小数 vs 存储层更长精度 → 视为未改动，不误落盘
    loaded = {"tab_chat": (0.06000001, 0.06)}
    assert not coord.should_save_coordinates({"tab_chat": (0.06, 0.06)}, loaded, False)
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest tests/test_coordinates_account.py -v`
Expected: `6 failed`（AttributeError: account_has_override / should_save_coordinates）

- [ ] **Step 3: coordinates.py 加 account_has_override + should_save_coordinates**

`src/utils/coordinates.py` 在 `reset_coordinates` 之后插入：

```python
def account_has_override(account_name: Optional[str] = None) -> bool:
    """是否存在账户专属坐标文件（None = 全局文件是否已存在）"""
    return _coordinates_path(account_name).exists()


def should_save_coordinates(
    current: dict[str, Tuple[float, float]],
    loaded: dict[str, Tuple[float, float]],
    has_override: bool,
) -> bool:
    """是否应保存坐标：账户已有专属文件，或任一坐标值与加载值不同

    按 4 位小数比较（与设置界面输入框的显示精度一致），避免
    存储层浮点长精度把「未改动」误判为「已改动」而冻结继承。
    """
    if has_override:
        return True
    loaded_fmt = {k: (f"{v[0]:.4f}", f"{v[1]:.4f}") for k, v in loaded.items()}
    for key, (x, y) in current.items():
        if (f"{x:.4f}", f"{y:.4f}") != loaded_fmt.get(key):
            return True
    return False
```

- [ ] **Step 4: settings_dialog 记录加载值 + 未改动不写**

1. `_build_coord_tab`（约 311 行）`coords = load_coordinates(self._account_name)` 之后插入：
```python
        self._coord_loaded = coords
```

2. 文件顶部 import 段（`src.utils.settings_store` 导入处）加（coordinates.py 仅依赖 stdlib，无循环依赖）：

```python
from src.utils.coordinates import (
    save_coordinates, account_has_override, should_save_coordinates,
    DEFAULT_COORDINATES,
)
```

（`_build_coord_tab` 约 299 行原有的函数内 import 是存量代码，不在本次范围，保持不动。）

3. `_save_coordinates`（约 393-406 行）整体替换为（顺带消除该函数原本的函数内 import）：

```python
    def _save_coordinates(self) -> None:
        """收集坐标输入框的值并保存

        未改动且该账户无专属文件 → 跳过（保持继承全局）；
        已改动或已有专属文件 → 写入账户专属文件。
        """
        if not self._coord_vars:
            return
        coords = {}
        for key, (xv, yv) in self._coord_vars.items():
            try:
                x = float(xv.get())
                y = float(yv.get())
                coords[key] = (x, y)
            except ValueError:
                coords[key] = DEFAULT_COORDINATES.get(key, (0.0, 0.0))
        if not should_save_coordinates(
                coords, getattr(self, "_coord_loaded", {}),
                account_has_override(self._account_name)):
            return  # 没改任何值、也无专属文件 → 保持继承全局
        save_coordinates(coords, self._account_name)
```

- [ ] **Step 5: 运行确认通过**

Run: `python -m pytest tests/test_coordinates_account.py -v`
Expected: `10 passed`

- [ ] **Step 6: 语法自检**

Run: `python -c "from src.ui.settings_dialog import SettingsDialog; print('ok')"`
Expected: `ok`

- [ ] **Step 7: 手工验证（需真实多开）**

多开绑定 2 账户 → 进设置（账户1）→ 坐标页不改任何值 → 关闭 → 确认 `cache/coordinates_账户1.json` **未生成**；改一个值再关 → 确认生成且仅该账户有。
Expected: 不编辑不落专属文件；编辑后才变专属。

- [ ] **Step 8: Commit**

```bash
git add src/utils/coordinates.py tests/test_coordinates_account.py src/ui/settings_dialog.py
git commit -m "fix: settings close without edits no longer freezes account coordinate inheritance"
```

---

### Task 5: `_ensure_calibration` 账户感知（#5）

**Files:**
- Modify: `src/ui/main_window.py`

- [ ] **Step 1: 重写 `_ensure_calibration`**

`src/ui/main_window.py`：
1. 文件顶部 import 段（`src.utils.coordinates` 导入处）加：

```python
from src.utils.calibration import calibration_has_key
```

2. `import json`（第 3 行）是旧 `_ensure_calibration`/`_check_calibration` 的唯一使用处，改完后已无用 → 删除。

`_ensure_calibration`（约 343-354 行）整体替换为：

```python
    def _ensure_calibration(self, key: str) -> bool:
        """发送/扫描前检查校准（账户感知：账户专属或继承全局都算已校准）"""
        if calibration_has_key(key, self._current_account_name()):
            return True
        if messagebox.askyesno("未校准", f"尚未校准 [{key}] 区域，现在打开校准工具？"):
            self._launch_calibrate(key)
        return False
```

- [ ] **Step 2: 顺带把 `_check_calibration` 也统一接入**

`_check_calibration`（约 583-599 行）主体替换为：

```python
    def _check_calibration(self) -> bool:
        """发送前检查是否做过聊天标题校准，未校准则提示。返回 True=可继续"""
        if calibration_has_key("chat_title", self._current_account_name()):
            return True
        return messagebox.askyesno(
            "提示",
            "尚未校准聊天标题 OCR 区域，群发时可能无法正确验证发送对象。\n"
            "建议先在 [OCR] → [OCR校准] 聊天界面标题 完成校准。\n\n是否仍然继续？",
        )
```

删掉不再使用的 `_current_calibration_path`（约 575-581 行）。

- [ ] **Step 3: 语法自检**

Run: `python -c "from src.ui.main_window import MainWindow; print('ok')"`
Expected: `ok`

- [ ] **Step 4: 全量测试**

Run: `python -m pytest tests/ -v`
Expected: `50 passed`

- [ ] **Step 5: Commit**

```bash
git add src/ui/main_window.py
git commit -m "fix: calibration pre-checks are account-aware (inherit global or own file)"
```

---

### Task 6: 多开引导重构（#7 #8 + 分层合规）

**Files:**
- Modify: `src/driver/wechat_bridge.py`（新增 `activate_hwnd`）
- Modify: `src/services/multi_account.py`（Task 2 已加 hwnd 去重）
- Modify: `src/ui/multi_account_dialog.py`
- Test: `tests/test_multi_account.py`（Task 2 已加重复 hwnd 测试）

- [ ] **Step 1: wechat_bridge 加 activate_hwnd（前台校验 + 重试）**

`src/driver/wechat_bridge.py` 在 `activate_window` 之后插入：

```python
    def activate_hwnd(self, hwnd: int, retries: int = 3) -> bool:
        """激活任意微信窗口（多开引导用），校验前台激活成功

        Windows 前台锁定可能拒绝 SetForegroundWindow；只有确认
        GetForegroundWindow 已是目标窗口才返回 True，避免确认错账户。
        """
        try:
            if win32gui.IsIconic(hwnd):
                win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
                time.sleep(0.2)
            for _ in range(retries):
                if self._hook_suspend:
                    self._hook_suspend()
                try:
                    win32gui.SetWindowPos(hwnd, win32con.HWND_TOPMOST, 0, 0, 0, 0,
                                          win32con.SWP_NOMOVE | win32con.SWP_NOSIZE)
                    win32gui.SetWindowPos(hwnd, win32con.HWND_NOTOPMOST, 0, 0, 0, 0,
                                          win32con.SWP_NOMOVE | win32con.SWP_NOSIZE)
                    win32api.keybd_event(win32con.VK_MENU, 0, 0, 0)
                    win32gui.SetForegroundWindow(hwnd)
                    win32api.keybd_event(win32con.VK_MENU, 0, win32con.KEYEVENTF_KEYUP, 0)
                    time.sleep(0.15)
                    if win32gui.GetForegroundWindow() == hwnd:
                        return True
                finally:
                    if self._hook_resume:
                        self._hook_resume()
            logger.warning("窗口激活失败（可能被前台锁定）: 0x%X", hwnd)
            return False
        except Exception:
            logger.exception("激活窗口失败: 0x%X", hwnd)
            return False
```

- [ ] **Step 2: 语法自检**

Run: `python -c "from src.driver.wechat_bridge import WeChatBridge; print(hasattr(WeChatBridge, 'activate_hwnd'))"`
Expected: `True`

- [ ] **Step 3: 重写 multi_account_dialog.py**

1. 删模块级 `from src.driver.wechat_bridge import WeChatBridge`（第 16 行，规范 §1.1 反例）。bridge 改为注入 + `Any` 类型标注（ui 层不 import driver，只持有注入对象——与 `MainWindow.set_bridge` 同款模式）。受影响的两处签名：
   - `MultiOpenWizard.__init__(self, root: tk.Tk, bridge: Any)`
   - `def run_multiopen_wizard(bridge: Any) -> Optional[MultiAccountSession]`

2. `_bring_to_front`（约 121-141 行）整体删除，改为直接调 bridge 的 `activate_hwnd`。`__init__` 的 bridge 参数类型改 `Any`。

3. `_on_detect`（约 89-96 行）替换为（重检测重置会话）：

```python
    def _on_detect(self):
        frames = self.bridge.find_all_windows()
        if not frames:
            messagebox.showwarning("提示", "未找到微信窗口，请先登录微信。")
            return
        if self._session.accounts:
            if not messagebox.askyesno("重新检测", "重新检测将清空已绑定的账户，是否继续？"):
                return
            self._session = MultiAccountSession()
        self._frames = frames
        self._lbl_count.config(text=f"检测到 {len(frames)} 个微信窗口")
        self._refresh_tree()
```

4. `_on_confirm_all`（约 99-119 行）替换为（默认名避撞 + 绑定失败提示）：

```python
    def _on_confirm_all(self):
        if not self._frames:
            messagebox.showwarning("提示", "请先点击「检测微信窗口」。")
            return
        start = len(self._session.accounts)
        for i in range(start, len(self._frames)):
            hwnd, title, _cls = self._frames[i]
            if not self.bridge.activate_hwnd(hwnd):
                messagebox.showwarning("提示", f"无法激活窗口 0x{hwnd:X}（可能被前台锁定），跳过。")
                continue
            name = simpledialog.askstring(
                "确认账户",
                f"窗口 {i + 1}/{len(self._frames)}\n当前显示在最前的微信窗口是哪个账户？\n\n标题: {title}",
                initialvalue=self._next_available_default(_default_name(i)),
                parent=self.root,
            )
            if name is None:
                break  # 用户点了取消 → 停止逐个确认，保留已确认的
            name = name.strip() or self._next_available_default(_default_name(i))
            if not self._session.add(name=name, hwnd=hwnd):
                messagebox.showwarning(
                    "提示", f"账户名 '{name}' 与已有账户冲突（或窗口已绑定），跳过。")
        self._refresh_tree()

    def _next_available_default(self, base: str) -> str:
        """返回未占用的默认名（默认名撞已有账户时自动加 _2/_3…）"""
        name = base
        n = 2
        while any(a.name == name for a in self._session.accounts):
            name = f"{base}_{n}"
            n += 1
        return name
```

- [ ] **Step 4: 语法自检**

Run: `python -c "from src.ui.multi_account_dialog import run_multiopen_wizard; print('ok')"`
Expected: `ok`

- [ ] **Step 5: 手工验证（需真实微信多开）**

`python main.py` → 点 [多开] → 引导：
1. 检测 2 个窗口 → 逐个确认（每个窗口确实被带到最前）→ 确定 → 多账户模式
2. 删除账户1 → 重新检测 → 弹「将清空已绑定账户」确认 → 确认后列表为空
3. 重命名与 Task 2 的 sanitize 冲突联动（同名片段账户不可建）
Expected: 激活失败有明确提示；重检测不会残留旧绑定。

- [ ] **Step 6: Commit**

```bash
git add src/driver/wechat_bridge.py src/ui/multi_account_dialog.py
git commit -m "fix: wizard uses verified foreground activation; remove ui→driver import; robust re-detect/default names"
```

---

### Task 7: 顶层模式循环，消除嵌套 mainloop（#10）

**Files:**
- Modify: `src/app.py`
- Modify: `src/ui/main_window.py`

- [ ] **Step 1: MainWindow.run() 返回模式切换请求**

`src/ui/main_window.py` 的 `run`（约 926-927 行）替换为：

```python
    def run(self):
        """运行主窗口 mainloop；窗口被销毁后返回切换请求（None=退出）"""
        self.root.mainloop()
        return getattr(self, "_mode_request", None)
```

- [ ] **Step 2: app.py 改顶层模式循环**

`src/app.py` 的 `run_gui`/`run_multi_gui`/`_enter_multiopen`/`_exit_multiopen` 整体替换为：

```python
def run_gui() -> None:
    """启动 GUI（单账户模式入口）"""
    run_app(multi_session=None)


def run_multi_gui(session) -> None:
    """启动 GUI（多账户模式入口）"""
    run_app(multi_session=session)


def run_app(multi_session=None) -> None:
    """顶层模式循环：单账户 / 多开引导 / 多账户 之间切换

    每个 mainloop 都在顶层运行：窗口销毁后 run() 返回切换请求，
    由本循环启动下一个窗口/引导，避免 多开↔单用户 往返时嵌套 mainloop。
    """
    session = multi_session
    while True:
        window = _build_window(multi_session=session)
        request = window.run()
        if request == "multiopen":
            from src.driver.wechat_bridge import WeChatBridge
            from src.ui.multi_account_dialog import run_multiopen_wizard
            session = run_multiopen_wizard(WeChatBridge())
            continue  # session=None → 取消，保持单账户
        if request == "single":
            session = None
            continue
        break  # 正常退出


def _request_mode(window, mode: str) -> None:
    """设置模式切换请求并销毁当前窗口（顶层 run_app 循环接管）"""
    window._mode_request = mode
    window.root.destroy()


def _enter_multiopen(window) -> None:
    _request_mode(window, "multiopen")


def _exit_multiopen(window) -> None:
    _request_mode(window, "single")
```

注意：`_build_window` 里注入的回调引用不变（`set_enter_multiopen_callback(lambda w=window: _enter_multiopen(w))` 等）。

- [ ] **Step 3: 语法自检 + 引用确认**

Run: `python -c "from src.app import run_gui, run_multi_gui, run_app; from src.ui.main_window import MainWindow; print('ok')"`
Expected: `ok`

- [ ] **Step 4: 手工验证（需真实微信）**

`python main.py`：
1. 单账户模式正常打开 → 点 [多开] → 引导弹出
2. 引导取消 → 回到单账户模式
3. 再点 [多开] → 绑定 2 账户 → 确定 → 多账户模式
4. 多账户点 [单用户模式] → 回单账户
5. 重复 2-3 步 3 次以上 → 无报错、不卡死（验证不再嵌套）
6. 直接关闭主窗口 → 程序退出

Expected: 反复切换无累计卡顿/报错。

- [ ] **Step 5: Commit**

```bash
git add src/app.py src/ui/main_window.py
git commit -m "refactor: top-level mode loop in app.py removes nested tk mainloops"
```

---

### Task 8: 账户切换清筛选（#11）

**Files:**
- Modify: `src/ui/filter_bar.py`
- Modify: `src/ui/main_window.py`

- [ ] **Step 1: FilterBar 加 clear_filter**

`src/ui/filter_bar.py` 在 `set_enabled` 之后插入：

```python
    def clear_filter(self) -> None:
        """清空筛选文字 + 正则模式 + 标签筛选（账户切换时调用，防串账户）"""
        self._filter_var.set("")
        self._regex_mode.set(False)
        self._tag_var.set("全部")
        self.set_regex_error("")
        self.set_regex_hint("")
```

注意：只有 `_filter_var`（18 行）和 `_regex_mode`（20 行）有 `trace_add`，`_tag_var` 没有 trace（靠 `<<ComboboxSelected>>` 刷新）。`_filter_var.set("")` 触发 `_apply_filter` 刷新到当前账户列表；刷新时 `tag_filter()` 已读到新值「全部」——功能正确，只是刷新由 filter_var 驱动。

- [ ] **Step 2: _switch_account 清筛选**

`src/ui/main_window.py` 的 `_switch_account`（约 117-124 行）中 `self.friend_list.select_none()` 之后插入：

```python
        self.filter_bar.clear_filter()
```

- [ ] **Step 3: 语法自检**

Run: `python -c "from src.ui.main_window import MainWindow; from src.ui.filter_bar import FilterBar; print('ok')"`
Expected: `ok`

- [ ] **Step 4: Commit**

```bash
git add src/ui/filter_bar.py src/ui/main_window.py
git commit -m "fix: clear search/regex/tag filter on account switch"
```

---

### Task 9: FriendService.save_cache 同步化（#12）

**Files:**
- Modify: `src/services/friend_service.py`
- Modify: `tests/test_friend_service_account.py`

- [ ] **Step 1: 同步写实现**

`src/services/friend_service.py`：
1. 文件顶部（第 6 行 `import time` 之后）加 `import threading`。
2. 模块级常量（`FriendService` 类前）加：
```python
# 跨实例共享的写锁：多账户并发写各自文件时防互相覆盖
_SAVE_LOCK = threading.Lock()
```
3. `save_cache`（约 64-82 行）整体替换为：

```python
    def save_cache(self):
        """同步落盘（小 JSON，毫秒级）。跨实例共享锁防并发写互相覆盖。"""
        self._cache_path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "updated_at": time.time(),
            "count": len(self._friends),
            "friends": [{"name": f.name, "tag": f.tag} for f in self._friends],
        }
        dump = json.dumps(data, ensure_ascii=False, indent=2)
        with _SAVE_LOCK:
            self._cache_path.write_text(dump, encoding="utf-8")
        logger.debug("缓存已保存: %d 位好友", len(self._friends))
```

（顺带消除原函数内 `import threading as _thr` 的规范 §1.4 违规。）

**同步化风险评估（已确认低风险）**：`save_cache` 的调用点全部在 `friend_service.py` 内部方法（`add_friend` 99 / `remove_friends` 112 / `rename_friend` 130 / `set_tag` 140 / `import_names` 167），均由 UI 线程低频触发；`operations.py` 的后台扫描/OCR/发送循环**不**调用 `save_cache`（OCR 收集名字 → 用户确认后由 UI 线程 `import_names` 落盘）。因此同步写不会锁住后台线程，小 JSON 毫秒级，UI 可接受。原「异步 daemon 写」的历史理由（避免高频调用阻塞）不成立。

- [ ] **Step 2: 更新测试注释**

`tests/test_friend_service_account.py` 里关于「异步写需等待落盘」的注释与 `time.sleep(0.1)` 相关说明改为：

```python
    # save_cache 现在是同步落盘，断言前无需等待
```

若测试里实际有 `import time; time.sleep(0.1)` 则删除该行。

- [ ] **Step 3: 运行确认通过**

Run: `python -m pytest tests/test_friend_service_account.py -v`
Expected: `1 passed`

- [ ] **Step 4: 全量测试**

Run: `python -m pytest tests/ -v`
Expected: `50 passed`

- [ ] **Step 5: Commit**

```bash
git add src/services/friend_service.py tests/test_friend_service_account.py
git commit -m "fix: synchronous cache save under shared lock (no lost writes, no function-level import)"
```

---

### Task 10: 全量回归 + 文档收尾

- [ ] **Step 1: 跑全部测试**

Run: `python -m pytest tests/ -v`
Expected: 全部通过（50 个：原有 32 + Task 1 校准 8 + Task 2 多账户 4 + Task 4 坐标 6）

- [ ] **Step 2: review #9 回归确认（_enum2 兜底移除）**

Run: `python -c "from src.driver.wechat_bridge import WeChatBridge; b=WeChatBridge(); print(b.find_window())"`
若单账户微信已启动：Expected `True`（窗口匹配走 Qt 类名 + 标题，行为与 phase1 前一致）。

- [ ] **Step 3: 手工回归三场景（需真实微信多开）**

1. **单账户群发**：`python main.py` → 选好友 → 发送 → 与之前一致
2. **多开全流程**：进入多开 → 绑定 2 账户 → 各自名单独立 → 扫描/检查/导出均作用于当前账户 → 切换清筛选
3. **设置交互**：坐标不改不落专属文件；校准按账户读写；多开延迟页可存

- [ ] **Step 4: 更新 spec 实施状态**

`docs/superpowers/specs/2026-08-10-multi-account-broadcast-design.md` §12 末尾追加一节：

```markdown
### review 修复批次（2026-08-11）

分支 `feature/multi-account-phase1`，`docs/superpowers/plans/2026-08-11-multi-account-phase1-fixes.md` 全部交付：
- OCR 校准两级回退统一模块（`src/utils/calibration.py`，全局→账户→默认），四处读取方接入
- 跨账户操作锁定（检查/扫描/导入期间禁用账户下拉）
- 账户名 sanitize 碰撞去重 + 重复 hwnd 拦截 + rename 越界保护
- 设置关闭不编辑不再冻结账户坐标继承
- 校准预检账户感知（继承全局也算已校准）
- 引导窗口去掉 ui→driver 依赖；激活加前台校验重试；重检测重置会话
- app 顶层模式循环消除嵌套 mainloop
- 账户切换清空筛选
- save_cache 同步落盘（共享锁）
```

- [ ] **Step 5: 删除临时 review 报告**

Run: `rm -f .review_report.md`
Expected: 文件删除。

- [ ] **Step 6: Commit**

```bash
git add docs/superpowers/specs/2026-08-10-multi-account-broadcast-design.md
git rm --cached .review_report.md 2>/dev/null; rm -f .review_report.md
git add -A
git commit -m "docs: record review fix batch in multi-account spec"
```

- [ ] **Step 7: 汇报完成**

向用户汇报：12 项问题全部修复，测试数、手工验证结果、commit 数；阶段 2 流水线并发可在此之上进行。
