"""账户文件路径 — cache/按账户文件夹管理

cache/<账户名>/{friends.json, settings.json, ocr_calibration.json, coordinates.json}
cache/accounts.json 存账户名列表；cache/settings.json 存全局（不分账户的）设置。
账户名只体现在文件夹名上，不写入任何 json 内容。
"""
import re
from pathlib import Path

CACHE_DIR = Path("cache")

# 默认账户名：单模式默认选中、None 账户名的落点（utils 层定义，供各层引用）
DEFAULT_ACCOUNT_NAME = "默认账户"

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
    """该账户的好友名单文件路径"""
    return _account_file(account_name, "friends.json")


def coordinates_path_for(account_name: str) -> Path:
    """该账户的坐标文件路径"""
    return _account_file(account_name, "coordinates.json")


def calibration_path_for(account_name: str) -> Path:
    """该账户的 OCR 校准文件路径"""
    return _account_file(account_name, "ocr_calibration.json")


def account_settings_path_for(account_name: str) -> Path:
    """该账户的设置文件路径"""
    return _account_file(account_name, "settings.json")
