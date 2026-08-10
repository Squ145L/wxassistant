"""消息模板引擎：[name] 替换 + 正则捕获组 [$1], [$2]..."""

import logging
import re
from typing import Any, Optional

logger = logging.getLogger(__name__)


class TemplateEngine:
    """消息模板变量替换

    变量（方括号）：
    - [name]   → 好友完整名称
    - [name2]  → 好友名称后2字（去掉前缀年级等）
    - [$1][$2] → 正则捕获组

    未识别变量保持原样。
    """

    @staticmethod
    def render(template: str, friend: Any, regex_match: Optional[re.Match] = None) -> str:
        """渲染模板

        Args:
            template:   消息模板，如 "[name]同学你好"
            friend:     FriendDTO
            regex_match: 正则匹配对象（用于 [$1] [$2] 捕获组）
        """
        display_name = getattr(friend, "display_name", getattr(friend, "name", ""))

        variables: dict[str, str] = {
            "name": display_name,
            "name2": display_name[-2:] if len(display_name) >= 2 else display_name,
        }

        if regex_match:
            for idx, group_val in enumerate(regex_match.groups(), start=1):
                variables[f"${idx}"] = group_val or ""

        def _replace(match: re.Match) -> str:
            var_name = match.group(1).strip()
            if var_name in variables:
                return variables[var_name]
            logger.debug("模板中未识别的变量: [%s]", var_name)
            return match.group(0)

        result = re.sub(r"\[(\$?\w+)\]", _replace, template)
        logger.debug("模板渲染: '%s' → '%s'", template[:40], result[:40])
        return result

    @staticmethod
    def validate(template: str) -> list[str]:
        """返回模板中使用的变量列表"""
        vars_found = re.findall(r"\[(\$?\w+)\]", template)
        return list(dict.fromkeys(vars_found))

    @staticmethod
    def get_help_text() -> str:
        return (
            "可用变量 (方括号格式):\n"
            "  [name]  - 替换为好友完整名称\n"
            "  [name2] - 替换为好友名称后2字 (去前缀, 如 25级李华->李华)\n"
            "  [$1] [$2] ... - 正则捕获组 (开启正则筛选时可用)\n"
            "\n"
            "示例:\n"
            "  模板: [name]同学你好, 这是课程表.\n"
            "  效果: 25级李华同学你好, 这是课程表.\n"
            "\n"
            "正则提取示例 (筛选正则为 (\d+级)(.+)):\n"
            "  [$1] -> 25级, [$2] -> 李华\n"
            "  模板: [$2]同学你好 -> 李华同学你好"
        )
