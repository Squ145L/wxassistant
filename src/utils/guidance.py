"""就绪检查 — 坐标 / OCR 校准 是否配置好（未配置先引导）

约定：坐标值 (0,0) 视为未配置（见 coordinates.DEFAULT_COORDINATES）；
OCR 校准看账户文件夹 ocr_calibration.json 里是否有对应 key。
纯层：只依赖 utils 的 coordinates/calibration，无 UI/驱动依赖。
"""
from typing import Optional

from src.utils.calibration import calibration_has_key
from src.utils.coordinates import load_coordinates

# 各操作需要的坐标 key（(0,0)=未配置时先引导校准坐标）
SEND_COORD_KEYS = ["tab_chat", "chat_first"]
SCAN_COORD_KEYS = ["tab_contacts", "btn_contacts_mgr", "cm_search_box", "cm_list_focus"]

# OCR key → 友好中文名（弹窗用，避免显示原始 key）
CALIB_LABELS = {
    "chat_title": "聊天标题",
    "contacts_list": "通讯录区域",
    "search_panel": "搜索面板",
}

READY_OK = "ok"
READY_NEED_COORDS = "need_coords"
READY_NEED_CALIB = "need_calib"


def check_ready(account_name: Optional[str],
                coord_keys: list[str],
                calib_keys: list[str]) -> str:
    """检查就绪状态（坐标优先：先确保坐标可定位，再查 OCR 校准）。

    Args:
        account_name: 账户名（None = 默认账户）
        coord_keys:   该操作需要的坐标 key 列表
        calib_keys:   该操作需要的 OCR 校准 key 列表

    Returns:
        READY_OK            全部就绪
        READY_NEED_COORDS   有坐标未配置（(0,0)）
        READY_NEED_CALIB    有 OCR 校准缺失
    """
    coords = load_coordinates(account_name)
    for k in coord_keys:
        x, y = coords.get(k, (0.0, 0.0))
        if x == 0.0 and y == 0.0:
            return READY_NEED_COORDS
    for k in calib_keys:
        if not calibration_has_key(k, account_name):
            return READY_NEED_CALIB
    return READY_OK
