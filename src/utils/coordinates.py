"""坐标注册中心 — 所有点击坐标的唯一定义点

从 cache/coordinates.json 加载用户自定义坐标，fallback 到默认值。
"""

import json
import logging
from pathlib import Path
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

COORDINATES_PATH = Path("cache/coordinates.json")

# ================================================================
# 默认坐标（窗口内百分比，相对于窗口左上角）
# ================================================================
DEFAULT_COORDINATES: dict[str, Tuple[float, float]] = {
    # 微信主界面
    "tab_chat":          (0.06, 0.14),   # 微信主界面(聊天)标签 — 左栏导航第1个图标
    "tab_contacts":      (0.06, 0.22),   # 通讯录标签 — 左栏导航第3个图标
    "btn_contacts_mgr":  (0.19, 0.12),   # 通讯录管理按钮 — 通讯录页面顶部
    "chat_first":        (0.19, 0.12),   # 聊天区域点击 — 聊天列表第一个聊天
    "chat_dismiss":      (0.55, 0.50),   # 聊天区域点击(关闭弹窗) — 窗口中央偏右

    # 通讯录管理窗口（全屏后）
    "cm_search_box":     (0.20, 0.03),   # 搜索框 — 顶部搜索输入框
    "cm_list_focus":     (0.71, 0.30),   # 列表聚焦点 — 联系人列表中间位置

    # 搜一搜
    "sousou_independent_btn": (0.00, 0.00),  # 搜一搜独立窗口按钮 — (0,0)=未配置，跳过

    # 安全区
    "safe_zone":         (0.30, 0.60),   # 安全区 — 窗口中间偏下，避免误折叠联系人
}

# 中文标签（给设置界面用）
COORD_LABELS: dict[str, str] = {
    "tab_chat":          "聊天标签",
    "tab_contacts":      "通讯录标签",
    "btn_contacts_mgr":  "通讯录管理按钮",
    "chat_first":        "聊天区域点击(第一个聊天)",
    "chat_dismiss":      "聊天区域点击(关闭弹窗)",
    "cm_search_box":     "通讯录管理-搜索框",
    "cm_list_focus":     "通讯录管理-列表聚焦",
    "sousou_independent_btn": "搜一搜-独立窗口按钮",
    "safe_zone":         "安全区(防误折叠)",
}

# 分组（给设置界面用）
COORD_GROUPS = [
    ("微信主界面", ["tab_chat", "tab_contacts", "btn_contacts_mgr", "chat_first", "chat_dismiss"]),
    ("通讯录管理窗口", ["cm_search_box", "cm_list_focus"]),
    ("搜一搜", ["sousou_independent_btn"]),
    ("其他", ["safe_zone"]),
]


def _coordinates_path(account_name: Optional[str] = None) -> Path:
    """账户专属坐标文件；account_name 为空则用全局文件"""
    if account_name:
        from src.utils.account_paths import coordinates_path_for
        return coordinates_path_for(account_name)
    return COORDINATES_PATH


def _apply_coord_file(merged: dict, path: Path) -> None:
    """把坐标文件合并进 merged（文件存在才读）"""
    if not path.exists():
        return
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        for key, value in data.items():
            if key in DEFAULT_COORDINATES and isinstance(value, list) and len(value) == 2:
                merged[key] = (float(value[0]), float(value[1]))
    except Exception:
        logger.warning("坐标配置文件读取失败，使用默认值: %s", path, exc_info=True)


def load_coordinates(account_name: Optional[str] = None) -> dict[str, Tuple[float, float]]:
    """加载坐标配置：全局文件 → 账户专属文件覆盖 → 默认值兜底"""
    merged = dict(DEFAULT_COORDINATES)
    _apply_coord_file(merged, COORDINATES_PATH)                       # 全局
    if account_name:
        _apply_coord_file(merged, _coordinates_path(account_name))     # 账户覆盖
    return merged


def save_coordinates(coords: dict[str, Tuple[float, float]],
                     account_name: Optional[str] = None) -> None:
    """保存坐标配置到文件（账户专属或全局）"""
    path = _coordinates_path(account_name)
    path.parent.mkdir(parents=True, exist_ok=True)
    serializable = {k: [v[0], v[1]] for k, v in coords.items()}
    path.write_text(
        json.dumps(serializable, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    logger.info("坐标配置已保存: %s", path)


def get_coord(key: str, account_name: Optional[str] = None) -> Tuple[float, float]:
    """获取单个坐标（账户优先，fallback 全局/默认值）

    Returns: (x_pct, y_pct) 窗口内百分比
    """
    coords = load_coordinates(account_name)
    if key in coords:
        return coords[key]
    logger.warning("未知坐标 key: %s，使用安全区默认值", key)
    return DEFAULT_COORDINATES.get("safe_zone", (0.30, 0.60))


def reset_coordinates() -> None:
    """重置为默认坐标"""
    save_coordinates(DEFAULT_COORDINATES)
    logger.info("坐标配置已重置为默认值")


# ================================================================
# OCR 校准区域解析（兼容旧格式像素值 → 新格式百分比）
# ================================================================

def resolve_calibration_rect(calib: dict, window_rect: tuple) -> tuple[int, int, int, int]:
    """将 OCR 校准参数解析为屏幕像素坐标

    新格式（百分比）: LEFT_MARGIN / RIGHT_MARGIN 为 0~1 的比例
    旧格式（像素）:   LEFT_MARGIN / RIGHT_MARGIN > 1 时为像素值（向后兼容）

    Args:
        calib: {"LEFT_MARGIN": 0.05, "TOP_PCT": 0.015, "RIGHT_MARGIN": 0.06, "BOTTOM_MARGIN": 0.91}
        window_rect: (left, top, right, bottom) 屏幕坐标

    Returns:
        (x1, y1, x2, y2) 截图区域屏幕坐标
    """
    wl, wt, wr, wb = window_rect
    ww = wr - wl
    wh = wb - wt

    lm = calib.get("LEFT_MARGIN", 0.05)
    tp = calib.get("TOP_PCT", 0.015)
    rm = calib.get("RIGHT_MARGIN", 0.06)
    bm = calib.get("BOTTOM_MARGIN", 0.91)

    # LEFT_MARGIN: >1 = 旧格式像素, ≤1 = 新格式比例
    if lm > 1:
        x1 = wl + int(lm)
    else:
        x1 = wl + int(ww * lm)

    # TOP_PCT: always percentage
    y1 = wt + int(wh * tp)

    # RIGHT_MARGIN: >1 = 旧格式像素, ≤1 = 新格式比例
    if rm > 1:
        x2 = wr - int(rm)
    else:
        x2 = wr - int(ww * rm)

    # BOTTOM_MARGIN: >1 = 旧格式像素, ≤1 = 新格式比例
    if bm > 1:
        y2 = wb - int(bm)
    else:
        y2 = wb - int(wh * bm)

    return (x1, y1, x2, y2)


def pixel_to_pct_margins(calib: dict, ww: int, wh: int) -> dict:
    """将校准参数中的像素值转为百分比（用于升级旧格式配置）

    只在保存时调用，确保旧格式平滑迁移。
    """
    result = dict(calib)
    for key, size in [("LEFT_MARGIN", ww), ("RIGHT_MARGIN", ww), ("BOTTOM_MARGIN", wh)]:
        if key in result and result[key] > 1:
            result[key] = round(result[key] / size, 6)
    return result
