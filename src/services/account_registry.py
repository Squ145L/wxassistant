"""账户注册表 — 持久账户列表（cache/accounts.json）

账户是全局第一等概念：单模式可切换、多开绑定窗口到账户。
默认账户固定存在且排最前，名称为「默认账户」。账户名即文件夹名，不与设置混存。
"""
import json
import logging
import shutil
from pathlib import Path

from src.utils.account_paths import account_dir

logger = logging.getLogger(__name__)

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
            logger.warning("账户列表读取失败，回退到默认账户", exc_info=True)
    if DEFAULT_ACCOUNT_NAME not in names:
        names.insert(0, DEFAULT_ACCOUNT_NAME)
    return names


def save_accounts(names: list[str]) -> None:
    """保存账户名列表"""
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
            logger.warning("账户数据文件夹移动失败: %s → %s", old_dir, new_dir, exc_info=True)
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
