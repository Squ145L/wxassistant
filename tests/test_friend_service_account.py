# tests/test_friend_service_account.py
import pytest

from src.utils import account_paths as ap
from src.services.friend_service import FriendService


@pytest.fixture
def tmp_cache(tmp_path, monkeypatch):
    """把每账户文件路径指到临时目录，避免污染真实 cache/"""
    monkeypatch.setattr(ap, "CACHE_DIR", tmp_path)
    yield tmp_path


def test_for_account_isolates_files(tmp_cache):
    # save_cache 现在是同步落盘，断言前无需等待
    fs_a = FriendService.for_account("账户A")
    fs_b = FriendService.for_account("账户B")

    fs_a.add_friend("张三")
    fs_b.add_friend("李四")

    # 各自从自己的文件加载
    fs_a2 = FriendService.for_account("账户A")
    fs_a2.load_cache()
    fs_b2 = FriendService.for_account("账户B")
    fs_b2.load_cache()

    assert [f.name for f in fs_a2.all_friends] == ["张三"]
    assert [f.name for f in fs_b2.all_friends] == ["李四"]
