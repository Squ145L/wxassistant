# tests/test_calibration.py
import pytest

from src.utils import account_paths as ap
from src.utils import calibration as cal


@pytest.fixture
def tmp_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(ap, "CACHE_DIR", tmp_path)
    return tmp_path


def test_load_returns_default_when_no_files(tmp_cache):
    c = cal.load_calibration("chat_title", "账户1")
    assert c["LEFT_MARGIN"] == cal.DEFAULT_CALIBRATION["chat_title"]["LEFT_MARGIN"]


def test_account_file_applies(tmp_cache):
    cal.save_calibration("chat_title", {"LEFT_MARGIN": 0.2}, "账户1")
    c = cal.load_calibration("chat_title", "账户1")
    assert c["LEFT_MARGIN"] == 0.2
    # 其它账户不受影响（回退默认）
    c2 = cal.load_calibration("chat_title", "账户2")
    assert c2["LEFT_MARGIN"] == cal.DEFAULT_CALIBRATION["chat_title"]["LEFT_MARGIN"]


def test_account_without_file_uses_default(tmp_cache):
    cal.save_calibration("contacts_list", {"BOTTOM_MARGIN": 0.1}, "账户1")
    c = cal.load_calibration("contacts_list", "账户2")
    assert c["BOTTOM_MARGIN"] == cal.DEFAULT_CALIBRATION["contacts_list"]["BOTTOM_MARGIN"]


def test_calibration_has_key_false_when_missing(tmp_cache):
    assert not cal.calibration_has_key("chat_title", "账户1")


def test_calibration_has_key_true_when_saved(tmp_cache):
    cal.save_calibration("chat_title", {"LEFT_MARGIN": 0.2}, "账户1")
    assert cal.calibration_has_key("chat_title", "账户1")
    assert not cal.calibration_has_key("chat_title", "账户2")


def test_save_isolates_accounts(tmp_cache):
    cal.save_calibration("chat_title", {"LEFT_MARGIN": 0.5}, "账户A")
    cal.save_calibration("chat_title", {"LEFT_MARGIN": 0.6}, "账户B")
    assert cal.load_calibration("chat_title", "账户A")["LEFT_MARGIN"] == 0.5
    assert cal.load_calibration("chat_title", "账户B")["LEFT_MARGIN"] == 0.6


def test_reset_removes_key(tmp_cache):
    cal.save_calibration("chat_title", {"LEFT_MARGIN": 0.5}, "账户1")
    cal.reset_calibration("chat_title", "账户1")
    assert not cal.calibration_has_key("chat_title", "账户1")
