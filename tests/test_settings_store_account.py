# tests/test_settings_store_account.py
import pytest

from src.utils import account_paths as ap
from src.utils import settings_store as ss


@pytest.fixture
def tmp_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(ap, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(ss, "SETTINGS_PATH", tmp_path / "settings.json")
    return tmp_path


def test_account_settings_default(tmp_cache):
    assert ss.load_account_settings("账户1") == {"name_source": "cache"}


def test_account_settings_save_and_load(tmp_cache):
    ss.save_account_settings("账户1", {"name_source": "ocr"})
    assert ss.load_account_settings("账户1") == {"name_source": "ocr"}
    # 账户间隔离
    assert ss.load_account_settings("账户2") == {"name_source": "cache"}


def test_account_settings_not_in_global(tmp_cache):
    ss.save_account_settings("账户1", {"name_source": "ocr"})
    assert "name_source" not in ss.load_settings()   # 全局设置不含账户级 key


def test_global_settings_still_work(tmp_cache):
    ss.save_settings({"scan_page_count": 50})
    s = ss.load_settings()
    assert s["scan_page_count"] == 50
    assert "name_source" not in s


# ---- copy_account_data：单次复制坐标 + OCR 校准，之后不跟随 ----

def test_copy_account_data_copies_coords_and_calib(tmp_cache):
    src_coords = ap.coordinates_path_for("账户B")
    src_coords.parent.mkdir(parents=True, exist_ok=True)
    src_coords.write_text('{"tab_chat": [0.1, 0.2]}', encoding="utf-8")
    src_calib = ap.calibration_path_for("账户B")
    src_calib.write_text('{"chat_title": {"LEFT_MARGIN": 0.9}}', encoding="utf-8")

    copied_coords, copied_calib = ss.copy_account_data("账户B", "账户A")
    assert (copied_coords, copied_calib) == (True, True)
    assert ap.coordinates_path_for("账户A").read_text(encoding="utf-8") == '{"tab_chat": [0.1, 0.2]}'
    assert ap.calibration_path_for("账户A").exists()


def test_copy_account_data_skips_missing_files(tmp_cache):
    copied_coords, copied_calib = ss.copy_account_data("账户B", "账户A")
    assert (copied_coords, copied_calib) == (False, False)
    assert not ap.coordinates_path_for("账户A").exists()
    assert not ap.calibration_path_for("账户A").exists()


def test_copy_account_data_copy_is_independent(tmp_cache):
    src = ap.coordinates_path_for("账户B")
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_text('{"tab_chat": [0.3, 0.4]}', encoding="utf-8")
    ss.copy_account_data("账户B", "账户A")
    # 复制后再改来源，不影响目标（单次复制，不跟随）
    src.write_text('{"tab_chat": [0.9, 0.9]}', encoding="utf-8")
    assert '0.3' in ap.coordinates_path_for("账户A").read_text(encoding="utf-8")


def test_copy_account_data_empty_names(tmp_cache):
    assert ss.copy_account_data("", "") == (False, False)
