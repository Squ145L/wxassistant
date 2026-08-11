"""OCR 校准参数读写 — 全局 + 账户覆盖两级回退（与 coordinates.load_coordinates 同款语义）"""

import json
import logging
from pathlib import Path
from typing import Optional

from src.utils.account_paths import calibration_path_for

logger = logging.getLogger(__name__)

# 全局校准文件路径（相对项目根，与全项目 Path("cache/...") 风格一致）
OCR_CALIBRATION_PATH = Path("cache/ocr_calibration.json")

# 各区域默认校准参数（窗口内百分比；LEFT/RIGHT_MARGIN >1 = 旧格式像素，兼容）
DEFAULT_CALIBRATION: dict[str, dict[str, float]] = {
    "chat_title": {
        "LEFT_MARGIN": 0.05, "TOP_PCT": 0.015, "RIGHT_MARGIN": 0.06, "BOTTOM_MARGIN": 0.91,
    },
    "search_panel": {
        "LEFT_MARGIN": 0.03, "TOP_PCT": 0.08, "RIGHT_MARGIN": 0.03, "BOTTOM_MARGIN": 0.30,
    },
    "contacts_list": {
        "LEFT_MARGIN": 0.03, "TOP_PCT": 0.25, "RIGHT_MARGIN": 0.26, "BOTTOM_MARGIN": 0.05,
    },
}


def _calibration_path(account_name: Optional[str] = None) -> Path:
    """账户专属校准文件路径；account_name 为空用全局文件"""
    if account_name:
        return calibration_path_for(account_name)
    return OCR_CALIBRATION_PATH


def _apply_key(merged: dict, path: Path, key: str) -> None:
    """把某个区域参数合并进 merged（文件存在才读）"""
    if not path.exists():
        return
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        params = data.get(key)
        if isinstance(params, dict):
            merged.update(params)
    except Exception:
        logger.warning("OCR 校准文件读取失败，使用默认值: %s", path, exc_info=True)


def load_calibration(key: str, account_name: Optional[str] = None) -> dict:
    """加载某区域校准参数：全局文件 → 账户专属文件覆盖 → 默认值兜底"""
    merged = dict(DEFAULT_CALIBRATION.get(key, {}))
    _apply_key(merged, OCR_CALIBRATION_PATH, key)                     # 全局
    if account_name:
        _apply_key(merged, calibration_path_for(account_name), key)   # 账户覆盖
    return merged


def calibration_has_key(key: str, account_name: Optional[str] = None) -> bool:
    """该账户（或继承的全局）是否已校准过指定区域"""
    paths = [OCR_CALIBRATION_PATH]
    if account_name:
        paths.append(calibration_path_for(account_name))
    for path in paths:
        if not path.exists():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data.get(key), dict):
                return True
        except Exception:
            logger.warning("OCR 校准文件读取失败: %s", path, exc_info=True)
    return False


def save_calibration(key: str, params: dict, account_name: Optional[str] = None) -> None:
    """保存某区域校准参数（账户专属或全局）"""
    path = _calibration_path(account_name)
    path.parent.mkdir(parents=True, exist_ok=True)
    existing: dict = {}
    if path.exists():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            logger.warning("OCR 校准文件读取失败，将覆盖: %s", path, exc_info=True)
    existing[key] = params
    path.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("OCR 校准已保存: %s [%s]", path, key)


def reset_calibration(key: Optional[str] = None, account_name: Optional[str] = None) -> None:
    """重置校准参数（key 为空 = 清空整个文件）"""
    path = _calibration_path(account_name)
    if not path.exists():
        return
    existing: dict = {}
    if key is not None:
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
            existing.pop(key, None)
        except Exception:
            logger.warning("OCR 校准文件读取失败: %s", path, exc_info=True)
    path.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("OCR 校准已重置: %s [%s]", path, key or "全部")
