"""联系人导出：txt / csv / json

导出好友名单到 cache/export/，文件名带账户名（多开）与时间戳。
"""
import csv
import json
import time
from pathlib import Path

EXPORT_DIR = Path("cache/export")


def export_friends(friends, fmt: str, account_name=None) -> Path:
    """导出好友列表，返回生成的文件路径

    Args:
        friends: list[FriendDTO]（有 name / tag 属性）
        fmt: 'txt' | 'csv' | 'json'
        account_name: 账户名（用于文件名区分，None=全局）

    Returns:
        Path 导出文件
    """
    fmt = fmt.lower()
    if fmt not in ("txt", "csv", "json"):
        raise ValueError(f"不支持的导出格式: {fmt}")

    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S")
    suffix = f"_{account_name}" if account_name else ""
    base = EXPORT_DIR / f"friends{suffix}_{ts}"

    if fmt == "txt":
        path = base.with_suffix(".txt")
        lines = "\n".join(f.name for f in friends)
        path.write_text(lines + ("\n" if friends else ""), encoding="utf-8")
    elif fmt == "csv":
        path = base.with_suffix(".csv")
        with path.open("w", newline="", encoding="utf-8-sig") as fh:
            writer = csv.writer(fh)
            writer.writerow(["name", "tag"])
            for f in friends:
                writer.writerow([f.name, getattr(f, "tag", "")])
    else:
        path = base.with_suffix(".json")
        data = {
            "updated_at": time.time(),
            "count": len(friends),
            "friends": [{"name": f.name, "tag": getattr(f, "tag", "")} for f in friends],
        }
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    return path
