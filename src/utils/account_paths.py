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
