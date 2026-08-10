# tests/test_export_service.py
import json

import pytest

from src.services import export_service as es
from src.services.friend_service import FriendDTO


@pytest.fixture(autouse=True)
def tmp_export(tmp_path, monkeypatch):
    monkeypatch.setattr(es, "EXPORT_DIR", tmp_path)
    yield tmp_path


def _friends():
    return [FriendDTO(name="张三", tag="A"), FriendDTO(name="李四", tag="B")]


def test_export_txt(tmp_export):
    p = es.export_friends(_friends(), "txt")
    assert p.suffix == ".txt"
    content = p.read_text(encoding="utf-8")
    assert "张三" in content and "李四" in content


def test_export_csv(tmp_export):
    p = es.export_friends(_friends(), "csv")
    rows = p.read_text(encoding="utf-8-sig").splitlines()
    assert rows[0] == "name,tag"
    assert "张三,A" in rows


def test_export_json(tmp_export):
    p = es.export_friends(_friends(), "json")
    data = json.loads(p.read_text(encoding="utf-8"))
    assert data["count"] == 2
    assert data["friends"][0]["name"] == "张三"
    assert data["friends"][1]["tag"] == "B"


def test_export_invalid_fmt(tmp_export):
    with pytest.raises(ValueError):
        es.export_friends(_friends(), "xlsx")


def test_export_account_in_filename(tmp_export):
    p = es.export_friends(_friends(), "txt", account_name="账户1")
    assert "账户1" in p.name


def test_export_empty_list(tmp_export):
    p = es.export_friends([], "txt")
    assert p.read_text(encoding="utf-8") == ""
