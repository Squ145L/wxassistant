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
