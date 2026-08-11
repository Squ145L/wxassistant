# tests/test_account_paths.py
import pytest

from src.utils import account_paths as ap


@pytest.fixture
def tmp_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(ap, "CACHE_DIR", tmp_path)
    return tmp_path


def test_sanitize_replaces_illegal_chars():
    assert ap.sanitize_account_name("账户/1") == "账户_1"
    assert ap.sanitize_account_name("a:b") == "a_b"


def test_sanitize_collapses_whitespace():
    assert ap.sanitize_account_name(" 账 户 1 ") == "账_户_1"


def test_sanitize_empty_falls_back_to_default():
    assert ap.sanitize_account_name("   ") == "default"


def test_sanitize_truncates_long_names():
    assert len(ap.sanitize_account_name("好" * 100)) <= 32


def test_account_dir_is_cache_slash_name(tmp_cache):
    assert ap.account_dir("账户1") == tmp_cache / "账户1"
    # 非法字符被 sanitize
    assert ap.account_dir("a/b") == tmp_cache / "a_b"


def test_friends_path_in_account_folder(tmp_cache):
    assert ap.friends_path_for("账户1") == tmp_cache / "账户1" / "friends.json"


def test_account_files_in_same_folder(tmp_cache):
    a = ap.friends_path_for("X")
    assert a == tmp_cache / "X" / "friends.json"
    assert ap.coordinates_path_for("X") == tmp_cache / "X" / "coordinates.json"
    assert ap.calibration_path_for("X") == tmp_cache / "X" / "ocr_calibration.json"
    assert ap.account_settings_path_for("X") == tmp_cache / "X" / "settings.json"


def test_different_accounts_get_different_folders(tmp_cache):
    assert ap.account_dir("A") != ap.account_dir("B")
    assert ap.friends_path_for("A") != ap.friends_path_for("B")
