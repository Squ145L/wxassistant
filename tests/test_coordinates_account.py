# tests/test_coordinates_account.py
from src.utils import account_paths as ap
from src.utils import coordinates as coord


def test_load_falls_back_to_global_default(tmp_path, monkeypatch):
    monkeypatch.setattr(ap, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(coord, "COORDINATES_PATH", tmp_path / "coordinates.json")
    # 无全局、无账户文件 → 回退默认
    c = coord.load_coordinates("账户1")
    assert c["tab_chat"] == coord.DEFAULT_COORDINATES["tab_chat"]


def test_save_account_writes_per_account_file(tmp_path, monkeypatch):
    monkeypatch.setattr(ap, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(coord, "COORDINATES_PATH", tmp_path / "coordinates.json")
    coord.save_coordinates({"tab_chat": (0.5, 0.5), "safe_zone": (0.3, 0.6)}, "账户1")
    p = ap.coordinates_path_for("账户1")
    assert p.exists()
    c = coord.load_coordinates("账户1")
    assert c["tab_chat"] == (0.5, 0.5)
    # 全局文件不受影响（不存在）
    assert not coord.COORDINATES_PATH.exists()


def test_account_overrides_global(tmp_path, monkeypatch):
    monkeypatch.setattr(ap, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(coord, "COORDINATES_PATH", tmp_path / "coordinates.json")
    # 先写全局
    coord.save_coordinates({"tab_chat": (0.1, 0.1), "safe_zone": (0.3, 0.6)}, None)
    # 再写账户覆盖
    coord.save_coordinates({"tab_chat": (0.9, 0.9), "safe_zone": (0.3, 0.6)}, "账户1")
    c = coord.load_coordinates("账户1")
    assert c["tab_chat"] == (0.9, 0.9)   # 账户覆盖全局
    g = coord.load_coordinates(None)
    assert g["tab_chat"] == (0.1, 0.1)   # 全局不变


def test_get_coord_account_specific(tmp_path, monkeypatch):
    monkeypatch.setattr(ap, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(coord, "COORDINATES_PATH", tmp_path / "coordinates.json")
    coord.save_coordinates({"safe_zone": (0.3, 0.6)}, "账户A")
    assert coord.get_coord("safe_zone", "账户A") == (0.3, 0.6)


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
