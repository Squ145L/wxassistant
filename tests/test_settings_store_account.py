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
