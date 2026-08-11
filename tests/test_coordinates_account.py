# tests/test_coordinates_account.py
import pytest

from src.utils import account_paths as ap
from src.utils import coordinates as coord


@pytest.fixture
def tmp_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(ap, "CACHE_DIR", tmp_path)
    return tmp_path


def test_load_falls_back_to_default(tmp_cache):
    # 无账户文件 → 回退默认
    c = coord.load_coordinates("账户1")
    assert c["tab_chat"] == coord.DEFAULT_COORDINATES["tab_chat"]


def test_save_account_writes_account_file(tmp_cache):
    coord.save_coordinates({"tab_chat": (0.5, 0.5), "safe_zone": (0.3, 0.6)}, "账户1")
    p = ap.coordinates_path_for("账户1")
    assert p.exists()
    c = coord.load_coordinates("账户1")
    assert c["tab_chat"] == (0.5, 0.5)
    # 其它账户不受影响
    c2 = coord.load_coordinates("账户2")
    assert c2["tab_chat"] == coord.DEFAULT_COORDINATES["tab_chat"]


def test_get_coord_account_specific(tmp_cache):
    coord.save_coordinates({"safe_zone": (0.3, 0.6)}, "账户A")
    assert coord.get_coord("safe_zone", "账户A") == (0.3, 0.6)
    assert coord.get_coord("safe_zone", "账户B") == coord.DEFAULT_COORDINATES["safe_zone"]


def test_account_has_override_false_by_default(tmp_cache):
    assert not coord.account_has_override("账户1")
    assert not coord.account_has_override("默认账户")


def test_account_has_override_true_after_save(tmp_cache):
    coord.save_coordinates({"tab_chat": (0.5, 0.5)}, "账户1")
    assert coord.account_has_override("账户1")
    assert not coord.account_has_override("账户2")


def test_should_save_coordinates_unchanged_skip(tmp_cache):
    loaded = {"tab_chat": (0.5, 0.5), "safe_zone": (0.3, 0.6)}
    assert not coord.should_save_coordinates(dict(loaded), loaded, False)


def test_should_save_coordinates_changed_saves(tmp_cache):
    loaded = {"tab_chat": (0.5, 0.5)}
    assert coord.should_save_coordinates({"tab_chat": (0.6, 0.5)}, loaded, False)


def test_should_save_coordinates_existing_override_saves(tmp_cache):
    loaded = {"tab_chat": (0.5, 0.5)}
    # 已有专属文件 → 即使未改动也要保存（更新专属文件）
    assert coord.should_save_coordinates(dict(loaded), loaded, True)


def test_should_save_coordinates_precision_tolerant(tmp_cache):
    # 显示层 4 位小数 vs 存储层更长精度 → 视为未改动，不误落盘
    loaded = {"tab_chat": (0.06000001, 0.06)}
    assert not coord.should_save_coordinates({"tab_chat": (0.06, 0.06)}, loaded, False)
