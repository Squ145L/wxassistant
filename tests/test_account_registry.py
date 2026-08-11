# tests/test_account_registry.py
import pytest

from src.services import account_registry as reg


@pytest.fixture
def tmp_accounts(tmp_path, monkeypatch):
    monkeypatch.setattr(reg, "ACCOUNTS_PATH", tmp_path / "accounts.json")
    return tmp_path


def test_default_account_exists_on_first_load(tmp_accounts):
    assert reg.load_accounts() == [reg.DEFAULT_ACCOUNT_NAME]


def test_save_and_load(tmp_accounts):
    reg.save_accounts([reg.DEFAULT_ACCOUNT_NAME, "账户2"])
    assert reg.load_accounts() == [reg.DEFAULT_ACCOUNT_NAME, "账户2"]


def test_default_account_always_ensured(tmp_accounts):
    reg.save_accounts(["账户2"])          # 缺默认账户 → 自动补在最前
    assert reg.load_accounts()[0] == reg.DEFAULT_ACCOUNT_NAME


def test_rename_moves_folder(tmp_accounts, monkeypatch):
    from src.utils import account_paths as ap
    monkeypatch.setattr(ap, "CACHE_DIR", tmp_accounts)
    (ap.account_dir("旧名") / "friends.json").parent.mkdir(parents=True, exist_ok=True)
    (ap.account_dir("旧名") / "friends.json").write_text("{}", encoding="utf-8")
    reg.save_accounts([reg.DEFAULT_ACCOUNT_NAME, "旧名"])
    assert reg.rename_account("旧名", "新名")
    assert reg.load_accounts() == [reg.DEFAULT_ACCOUNT_NAME, "新名"]
    assert (ap.account_dir("新名") / "friends.json").exists()   # 文件夹被移动
    assert not ap.account_dir("旧名").exists()


def test_rename_rejects_duplicate(tmp_accounts):
    reg.save_accounts([reg.DEFAULT_ACCOUNT_NAME, "A"])
    assert not reg.rename_account("A", reg.DEFAULT_ACCOUNT_NAME)


def test_delete_account_removes_folder(tmp_accounts, monkeypatch):
    from src.utils import account_paths as ap
    monkeypatch.setattr(ap, "CACHE_DIR", tmp_accounts)
    (ap.account_dir("账户2") / "friends.json").parent.mkdir(parents=True, exist_ok=True)
    reg.save_accounts([reg.DEFAULT_ACCOUNT_NAME, "账户2"])
    assert reg.delete_account("账户2")
    assert reg.load_accounts() == [reg.DEFAULT_ACCOUNT_NAME]
    assert not ap.account_dir("账户2").exists()


def test_cannot_delete_default_account(tmp_accounts):
    reg.save_accounts([reg.DEFAULT_ACCOUNT_NAME, "A"])
    assert not reg.delete_account(reg.DEFAULT_ACCOUNT_NAME)
