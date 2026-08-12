# tests/test_template_store.py
import pytest

from src.services import template_store as ts


@pytest.fixture
def tmp_store(tmp_path, monkeypatch):
    monkeypatch.setattr(ts, "TEMPLATE_PATH", tmp_path / "template.txt")
    return tmp_path


def test_load_returns_default_when_missing(tmp_store):
    assert ts.load_template() == ts.DEFAULT_TEMPLATE


def test_save_and_load_roundtrip(tmp_store):
    ts.save_template("你好，[name]同学")
    assert ts.load_template() == "你好，[name]同学"


def test_load_returns_default_when_file_blank(tmp_store):
    ts.TEMPLATE_PATH.write_text("   \n  ", encoding="utf-8")
    assert ts.load_template() == ts.DEFAULT_TEMPLATE
