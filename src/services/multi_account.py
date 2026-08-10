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
