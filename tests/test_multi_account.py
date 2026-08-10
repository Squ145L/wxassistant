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
