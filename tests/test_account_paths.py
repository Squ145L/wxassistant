# tests/test_account_paths.py
from src.utils import account_paths as ap


def test_sanitize_replaces_illegal_chars():
    assert ap.sanitize_account_name("账户/1") == "账户_1"
    assert ap.sanitize_account_name("a:b") == "a_b"


def test_sanitize_collapses_whitespace():
    assert ap.sanitize_account_name(" 账 户 1 ") == "账_户_1"


def test_sanitize_empty_falls_back_to_default():
    assert ap.sanitize_account_name("   ") == "default"


def test_sanitize_truncates_long_names():
    assert len(ap.sanitize_account_name("好" * 100)) <= 32


def test_friends_path_for():
    p = ap.friends_path_for("账户1")
    assert p.name == "friends_账户1.json"
    assert p.parent == ap.CACHE_DIR


def test_different_accounts_get_different_paths():
    assert ap.friends_path_for("A") != ap.friends_path_for("B")
    assert ap.coordinates_path_for("A") != ap.coordinates_path_for("B")
    assert ap.calibration_path_for("A") != ap.calibration_path_for("B")
