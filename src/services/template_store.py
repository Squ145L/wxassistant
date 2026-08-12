"""消息模板持久化 — cache/template.txt（全局不分账户）

用户明确：模板只存文本、不按账户拆分，直接放 cache/。
附件不随模板保存，每次启动后重新选择。
"""
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

TEMPLATE_PATH = Path("cache/template.txt")

DEFAULT_TEMPLATE = "[name]同学你好，\n\n这是本学期的课程安排。\n\n[name]=25级李华 [name2]=李华"


def load_template() -> str:
    """加载模板文本；文件缺失/空/损坏时返回默认示例"""
    if TEMPLATE_PATH.exists():
        try:
            text = TEMPLATE_PATH.read_text(encoding="utf-8")
            if text.strip():
                return text
        except Exception:
            logger.warning("消息模板读取失败，使用默认示例: %s", TEMPLATE_PATH, exc_info=True)
    return DEFAULT_TEMPLATE


def save_template(text: str) -> None:
    """保存模板文本（全局，不分账户）"""
    TEMPLATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    TEMPLATE_PATH.write_text(text, encoding="utf-8")
