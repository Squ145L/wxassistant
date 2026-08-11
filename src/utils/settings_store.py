"""设置持久化（纯层，无 UI/驱动依赖）

全局设置 cache/settings.json：调试/扫描/多开等不分账户的选项。
账户级设置 cache/<账户>/settings.json：该账户专属选项（name_source 等）。
从 settings_dialog 抽取，供 driver/operations/main 等各层复用。
"""
import json
import logging
from pathlib import Path

from src.utils.account_paths import account_settings_path_for
from src.utils.config import (
    ACTIVATE_DELAY, SEARCH_DELAY, CLIPBOARD_DELAY, PASTE_DELAY,
    SEND_AFTER_DELAY, FILE_SEND_DELAY, KEY_PRESS_DELAY,
    DEFAULT_SEND_INTERVAL, INTERVAL_JITTER_RATIO,
)

logger = logging.getLogger(__name__)

SETTINGS_PATH = Path("cache/settings.json")

# 全局设置（不分账户）
DEFAULT_SETTINGS = {
    "theme": "vista",   # ttk 主题：clam/alt/vista/xpnative（默认 vista 原生外观）
    "ocr_debug_save": False,
    "scan_page_count": 100,
    "scan_scroll_px": 1200,
    "scan_pages_per_scroll": 12,
    "logging_enabled": True,
    "ocr_model": "v5",              # OCR 模型集档位：v5 移动端高精度 / v4 经典快速（全局不分账户）
    # ---- 多开（流水线并发发送的时序参数，阶段2 启用读取）----
    "multi_open_activate_delay": 0.2,       # 窗口激活后等待 (s)
    "multi_open_search_delay": 0.1,         # 搜索 Enter 后、弹窗检测前 (s)
    "multi_open_ready_timeout": 2.0,        # 切回后等待窗口就绪超时 (s)
    "multi_open_account_interval": 3.0,     # 两个账户最后一步之间 (s)
    "multi_open_send_interval": 0.1,        # 发送基础间隔 (s)
    "multi_open_popup_retry": 0,            # 弹窗检测重试次数
    # ---- 操作间延迟（设置→延迟 标签页，全局不分账户）----
    "op_activate_delay": ACTIVATE_DELAY,        # 窗口激活后等待 (s)
    "op_search_delay": SEARCH_DELAY,            # Ctrl+F 搜索 Enter 后等待 (s)
    "op_clipboard_delay": CLIPBOARD_DELAY,      # 剪贴板复制后等待 (s)
    "op_paste_delay": PASTE_DELAY,              # Ctrl+V 粘贴后等待 (s)
    "op_send_after_delay": SEND_AFTER_DELAY,    # Enter 发送后等待 (s)
    "op_file_send_delay": FILE_SEND_DELAY,      # 文件发送后等待 (s)
    "op_key_press_delay": KEY_PRESS_DELAY,      # 组合键/鼠标事件间隔 (s)
    "op_send_interval": DEFAULT_SEND_INTERVAL,  # 两条消息之间基础间隔 (s)
    "op_send_jitter": INTERVAL_JITTER_RATIO,    # 发送间隔 ±抖动比例 (0~1)
}

# 账户级设置（每个账户独立，存在 账户文件夹/settings.json）
ACCOUNT_DEFAULT_SETTINGS = {
    "name_source": "cache",   # 该账户联系人来源：cache / ocr
}


def load_settings() -> dict:
    """加载设置：用户文件覆盖默认值"""
    if SETTINGS_PATH.exists():
        try:
            data = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
            merged = dict(DEFAULT_SETTINGS)
            merged.update(data)
            return merged
        except Exception:
            pass
    return dict(DEFAULT_SETTINGS)


def load_scan_settings() -> dict:
    """返回扫描页数和滚动高度（供 operations 调用）"""
    s = load_settings()
    return {"page_count": s["scan_page_count"], "scroll_px": s["scan_scroll_px"],
            "pages_per_scroll": s["scan_pages_per_scroll"]}


_DELAY_KEYS = (
    "op_activate_delay", "op_search_delay", "op_clipboard_delay",
    "op_paste_delay", "op_send_after_delay", "op_file_send_delay",
    "op_key_press_delay", "op_send_interval", "op_send_jitter",
)


def load_delay_settings() -> dict:
    """返回操作间延迟参数（用户覆盖 → 默认值）

    设置→延迟 标签页的读取入口，也是 bridge/send_service 取延迟的唯一途径。
    """
    s = load_settings()
    return {k: s.get(k, DEFAULT_SETTINGS[k]) for k in _DELAY_KEYS}


def save_settings(settings: dict) -> None:
    SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS_PATH.write_text(
        json.dumps(settings, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def load_account_settings(account_name: str) -> dict:
    """加载账户级设置（cache/<账户>/settings.json）；缺失/损坏回退默认"""
    path = account_settings_path_for(account_name)
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            merged = dict(ACCOUNT_DEFAULT_SETTINGS)
            merged.update(data)
            return merged
        except Exception:
            logger.warning("账户设置读取失败，回退默认: %s", path, exc_info=True)
    return dict(ACCOUNT_DEFAULT_SETTINGS)


def save_account_settings(account_name: str, settings: dict) -> None:
    """保存账户级设置"""
    path = account_settings_path_for(account_name)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(settings, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
