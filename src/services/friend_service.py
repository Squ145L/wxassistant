"""好友缓存管理：手动增删改 + JSON 持久化 + 筛选（前缀/正则）"""

import json
import logging
import re
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class FriendDTO:
    """好友数据"""
    name: str
    tag: str = ""


# 跨实例共享的写锁：多账户并发写各自文件时防互相覆盖
_SAVE_LOCK = threading.Lock()


class FriendService:
    """好友列表管理

    - 手动增删改
    - JSON 持久化
    - 前缀 / 正则筛选
    """

    def __init__(self, cache_path: str = "cache/friends.json"):
        self._cache_path = Path(cache_path)
        self._friends: list[FriendDTO] = []

    @classmethod
    def for_account(cls, account_name: str) -> "FriendService":
        """创建绑定到指定账户数据文件夹的实例（单/多模式通用）"""
        from src.utils.account_paths import friends_path_for
        return cls(cache_path=str(friends_path_for(account_name)))

    # ================================================================
    # 持久化
    # ================================================================

    def load_cache(self) -> bool:
        if not self._cache_path.exists():
            logger.info("缓存文件不存在: %s", self._cache_path)
            return False
        try:
            data = json.loads(self._cache_path.read_text(encoding="utf-8"))
            self._friends = [
                FriendDTO(
                    name=item.get("name", item.get("display_name", "")),
                    tag=item.get("tag", ""),
                )
                for item in data.get("friends", [])
            ]
            logger.info("从缓存加载 %d 位好友", len(self._friends))
            return True
        except Exception:
            logger.exception("加载缓存失败")
            return False

    def save_cache(self):
        """同步落盘（小 JSON，毫秒级）。跨实例共享锁防并发写互相覆盖。"""
        self._cache_path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "updated_at": time.time(),
            "count": len(self._friends),
            "friends": [{"name": f.name, "tag": f.tag} for f in self._friends],
        }
        dump = json.dumps(data, ensure_ascii=False, indent=2)
        with _SAVE_LOCK:
            self._cache_path.write_text(dump, encoding="utf-8")
        logger.debug("缓存已保存: %d 位好友", len(self._friends))

    # ================================================================
    # 手动管理
    # ================================================================

    def add_friend(self, name: str) -> bool:
        """添加好友。已存在则返回 False"""
        name = name.strip()
        if not name:
            return False
        if any(f.name == name for f in self._friends):
            logger.warning("好友已存在: '%s'", name)
            return False
        self._friends.append(FriendDTO(name=name))
        self._friends.sort(key=lambda f: f.name)
        logger.info("已添加好友: '%s' (共 %d 人)", name, len(self._friends))
        self.save_cache()
        return True

    def remove_friend(self, name: str) -> bool:
        return self.remove_friends([name])

    def remove_friends(self, names: list[str]) -> bool:
        """批量删除好友"""
        before = len(self._friends)
        name_set = set(names)
        self._friends = [f for f in self._friends if f.name not in name_set]
        if len(self._friends) < before:
            logger.info("已删除 %d 位好友", before - len(self._friends))
            self.save_cache()
            return True
        return False

    def rename_friend(self, old_name: str, new_name: str) -> bool:
        """重命名好友"""
        new_name = new_name.strip()
        if not new_name:
            return False
        # 检查是否与其他好友重名
        if any(f.name == new_name for f in self._friends if f.name != old_name):
            logger.warning("重命名失败: '%s' → '%s' (名字已被占用)", old_name, new_name)
            return False
        for f in self._friends:
            if f.name == old_name:
                f.name = new_name
                self._friends.sort(key=lambda f: f.name)
                logger.info("已重命名: '%s' → '%s'", old_name, new_name)
                self.save_cache()
                return True
        return False

    def set_tag(self, name: str, tag: str) -> bool:
        """设置好友标签"""
        tag = tag.strip()
        for f in self._friends:
            if f.name == name:
                f.tag = tag
                self.save_cache()
                logger.info("已设置标签: '%s' → '%s'", name, tag)
                return True
        return False

    def all_tags(self) -> list[str]:
        """返回所有不重复的标签（已排序，不含空字符串）"""
        tags = sorted({f.tag for f in self._friends if f.tag})
        return tags

    def filter_by_tag(self, tag: str) -> list[FriendDTO]:
        if not tag:
            return list(self._friends)
        return [f for f in self._friends if f.tag == tag]

    def import_names(self, names: list[str]):
        """批量导入（合并去重）"""
        existing = {f.name for f in self._friends}
        added = 0
        for n in names:
            n = n.strip()
            if n and n not in existing:
                self._friends.append(FriendDTO(name=n))
                existing.add(n)
                added += 1
        if added:
            self._friends.sort(key=lambda f: f.name)
            self.save_cache()
            logger.info("批量导入 %d 位好友 (共 %d 人)", added, len(self._friends))

    # ================================================================
    # 属性
    # ================================================================

    @property
    def count(self) -> int:
        return len(self._friends)

    @property
    def all_friends(self) -> list[FriendDTO]:
        return list(self._friends)

    @property
    def last_updated_str(self) -> str:
        if not self._cache_path.exists():
            return "从未更新"
        ts = self._cache_path.stat().st_mtime
        return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts))

    # ================================================================
    # 筛选
    # ================================================================

    def filter_by_prefix(self, prefix: str) -> list[FriendDTO]:
        if not prefix.strip():
            return list(self._friends)
        result = [f for f in self._friends if f.name.startswith(prefix)]
        logger.info("前缀筛选 '%s': %d/%d", prefix, len(result), len(self._friends))
        return result

    def filter_by_regex(self, pattern: str) -> list[FriendDTO]:
        if not pattern.strip():
            return list(self._friends)
        try:
            regex = re.compile(pattern)
        except re.error as e:
            logger.warning("正则语法错误: '%s' — %s", pattern, e)
            raise
        result = [f for f in self._friends if regex.search(f.name)]
        logger.info("正则筛选 '%s': %d/%d", pattern, len(result), len(self._friends))
        return result

    def search(self, keyword: str) -> list[FriendDTO]:
        if not keyword.strip():
            return list(self._friends)
        result = [f for f in self._friends if keyword.lower() in f.name.lower()]
        return result

    @staticmethod
    def try_compile_regex(pattern: str) -> Optional[re.Pattern]:
        try:
            return re.compile(pattern)
        except re.error:
            return None

    @staticmethod
    def is_regex_pattern(text: str) -> bool:
        regex_chars = r"\.^$*+?{}[]|()\\"
        return any(c in text for c in regex_chars)
