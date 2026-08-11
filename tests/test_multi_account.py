# tests/test_multi_account.py
from src.services.multi_account import (
    AccountWindow,
    MultiAccountSession,
    find_overlapping_accounts,
    rects_overlap,
)


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


def test_rects_overlap_no_overlap():
    assert not rects_overlap((0, 0, 100, 100), (200, 200, 300, 300))


def test_rects_overlap_partial():
    assert rects_overlap((0, 0, 100, 100), (50, 50, 150, 150))


def test_rects_overlap_contained():
    assert rects_overlap((0, 0, 200, 200), (50, 50, 100, 100))


def test_rects_overlap_touching_edges_not():
    # 右边刚好接触（交叠宽为 0）不算重叠
    assert not rects_overlap((0, 0, 100, 100), (100, 0, 200, 100))


def test_find_overlapping_accounts():
    rects = [("A", (0, 0, 100, 100)), ("B", (50, 50, 150, 150)), ("C", (300, 300, 400, 400))]
    pairs = find_overlapping_accounts(rects)
    assert ("A", "B") in pairs
    assert len(pairs) == 1


def test_find_overlapping_accounts_empty_when_no_overlap():
    rects = [("A", (0, 0, 100, 100)), ("B", (200, 200, 300, 300))]
    assert find_overlapping_accounts(rects) == []


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
