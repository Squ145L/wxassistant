"""多开会话模型 — 账户窗口绑定的会话级数据结构（不落盘跨会话）"""
from dataclasses import dataclass
from typing import Optional

from src.utils.account_paths import sanitize_account_name


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

    def _sanitized(self, name: str) -> str:
        """账户名对应的文件片段（与 account_paths.sanitize_account_name 一致）"""
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

    def _renumber(self):
        for i, a in enumerate(self._accounts):
            if a.order != i:
                self._accounts[i] = AccountWindow(name=a.name, hwnd=a.hwnd, order=i)


def rects_overlap(r1, r2, min_pixels: int = 1) -> bool:
    """两个窗口矩形是否交叠（屏幕坐标 (left, top, right, bottom)）

    仅当交叠区域宽、高均 >= min_pixels 才算重叠（避免贴边误报）。
    """
    x1 = max(r1[0], r2[0])
    y1 = max(r1[1], r2[1])
    x2 = min(r1[2], r2[2])
    y2 = min(r1[3], r2[3])
    return (x2 - x1) >= min_pixels and (y2 - y1) >= min_pixels


def find_overlapping_accounts(
    account_rects: list[tuple[str, tuple]],
) -> list[tuple[str, str]]:
    """检测多账户窗口两两重叠，返回重叠账户名对 [(name1, name2)]

    account_rects: [(账户名, GetWindowRect 返回的 (left, top, right, bottom))]
    """
    pairs: list[tuple[str, str]] = []
    for i in range(len(account_rects)):
        for j in range(i + 1, len(account_rects)):
            if rects_overlap(account_rects[i][1], account_rects[j][1]):
                pairs.append((account_rects[i][0], account_rects[j][0]))
    return pairs
