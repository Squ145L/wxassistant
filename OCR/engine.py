"""OCR 引擎 — RapidOCR 封装

独立模块，不依赖项目其他代码。可直接复制 OCR/ 文件夹到其他项目使用。
"""

import json
import logging
import threading
import time
from pathlib import Path
from typing import Optional

from PIL import Image

logger = logging.getLogger(__name__)

# ================================================================
# 配置
# ================================================================

OCR_CONFIDENCE_THRESHOLD = 0.7    # 低于此置信度视为不可靠
OCR_CACHE_TTL = 30                # 同搜索词缓存秒数
OCR_MODEL_DIR = Path(__file__).parent / "models"  # 本地模型目录
OCR_CONFUSION_PATH = Path(__file__).parent / "ocr_confusion.json"  # 字符混淆映射

# RapidOCR 全局单例（惰性加载，线程安全）
_ocr_instance: Optional[object] = None
_ocr_lock = threading.Lock()


def _get_ocr():
    """惰性初始化 RapidOCR，全局复用（双检锁线程安全）

    预热线程与操作线程可能并发调用，用锁保证只加载一次。
    """
    global _ocr_instance
    if _ocr_instance is not None:
        return _ocr_instance
    with _ocr_lock:
        if _ocr_instance is None:
            logger.info("正在加载 RapidOCR 模型...")
            from rapidocr_onnxruntime import RapidOCR

            # 扫描本地模型和字典
            det_model = None
            rec_model = None
            dict_file = None
            if OCR_MODEL_DIR.exists():
                for f in OCR_MODEL_DIR.iterdir():
                    name = f.name.lower()
                    if "det" in name and name.endswith(".onnx"):
                        det_model = str(f)
                    elif "rec" in name and name.endswith(".onnx"):
                        rec_model = str(f)
                    elif name.endswith(".txt"):
                        dict_file = str(f)
                        logger.info("找到字典文件: %s", f.name)

            if det_model and rec_model:
                logger.info("使用本地模型: %s", OCR_MODEL_DIR)
                _ocr_instance = RapidOCR(
                    det_model_path=det_model,
                    rec_model_path=rec_model,
                    dict_path=dict_file,
                )
            elif dict_file:
                # 有字典但没有本地模型 → 用默认模型+本地字典
                logger.info("使用默认模型 + 本地字典")
                _ocr_instance = RapidOCR(dict_path=dict_file)
            else:
                logger.info("使用默认模型（无本地字典）")
                _ocr_instance = RapidOCR()
            logger.info("RapidOCR 初始化完成")
    return _ocr_instance


def warmup_ocr() -> None:
    """后台预热 OCR 模型（main.py 启动时 daemon 线程调用）

    首次模型加载约需 1-2 分钟；若发生在检查/发送操作内会阻塞且期间无法中断。
    启动即后台加载，操作时模型已就绪。日志走 logger，会自动进发送日志面板。
    """
    logger.info("OCR 模型后台预热中（首次加载约需 1-2 分钟，期间可正常使用）...")
    try:
        _get_ocr()
        logger.info("OCR 模型已预热完成，检查/发送无需等待加载")
    except Exception:
        logger.warning("OCR 模型预热失败，将在首次使用时再加载", exc_info=True)


# ================================================================
# OCR 引擎
# ================================================================

class OCREngine:
    """RapidOCR 封装

    用法:
        ocr = OCREngine()
        items = ocr.recognize(image)                      # 全量 OCR
        texts = ocr.recognize_text(image)                 # 只取文本
        names = ocr.parse_contact_names(image)            # 解析联系人列表

    缓存: 同 search_keyword 30s 内不重复 OCR。
    """

    def __init__(self):
        self._cache: dict[str, tuple[float, list[str]]] = {}
        self._confusion_map: Optional[dict] = None  # 惰性加载

    # ================================================================
    # 混淆字符归一化
    # ================================================================

    def _get_confusion_map(self) -> dict:
        """加载混淆字符映射表（惰性，只加载一次）"""
        if self._confusion_map is not None:
            return self._confusion_map
        if not OCR_CONFUSION_PATH.exists():
            self._confusion_map = {}
            return self._confusion_map
        try:
            data = json.loads(OCR_CONFUSION_PATH.read_text(encoding="utf-8"))
            self._confusion_map = {
                k: v for k, v in data.items() if not k.startswith("_")
            }
            logger.info("已加载 OCR 混淆映射: %d 条", len(self._confusion_map))
        except Exception:
            logger.warning("OCR 混淆配置读取失败", exc_info=True)
            self._confusion_map = {}
        return self._confusion_map

    def _normalize_text(self, text: str) -> str:
        """按混淆映射表归一化文本"""
        cmap = self._get_confusion_map()
        if not cmap:
            return text
        result = text
        for src, dst in cmap.items():
            result = result.replace(src, dst)
        return result

    # ================================================================
    # 基础 OCR
    # ================================================================

    def recognize(self, image: Image.Image) -> list[dict]:
        """对 PIL Image 执行 OCR

        Returns:
            [{"text": "张三", "confidence": 0.95, "box": [[x1,y1],[x2,y2],[x3,y3],[x4,y4]]}, ...]
            按从上到下、从左到右排序
        """
        ocr = _get_ocr()
        try:
            import numpy as np
            img_array = np.array(image.convert("RGB"))
            raw_result, _ = ocr(img_array)

            if raw_result is None:
                logger.debug("OCR 未识别到文字")
                return []

            items = []
            for box, text, confidence in raw_result:
                items.append({
                    "text": self._normalize_text(text.strip()),
                    "confidence": confidence,
                    "box": [list(map(int, pt)) for pt in box],
                })
            logger.debug("OCR 识别到 %d 条文本", len(items))
            return items

        except Exception:
            logger.exception("OCR 识别异常")
            return []

    def recognize_text(self, image: Image.Image) -> list[str]:
        """只返回文本列表"""
        return [it["text"] for it in self.recognize(image)]

    def recognize_text_filtered(
        self, image: Image.Image, min_confidence: float = OCR_CONFIDENCE_THRESHOLD
    ) -> list[str]:
        """只返回置信度达标的文本"""
        return [it["text"] for it in self.recognize(image) if it["confidence"] >= min_confidence]

    # ================================================================
    # 联系人解析
    # ================================================================

    def parse_contact_names(self, image: Image.Image) -> list[str]:
        """从微信搜索面板截图中提取联系人名称

        微信搜索面板中联系人按「联系人」分组列在标签下。
        识别策略: 找「联系人」标签 → 收集后续名称。
        """
        items = self.recognize(image)
        if not items:
            return []

        names: list[str] = []
        in_contacts_section = False
        section_keywords = ["联系人", "群聊", "聊天记录", "小程序", "文章", "视频号"]

        for item in items:
            text = item["text"]
            confidence = item["confidence"]

            if confidence < OCR_CONFIDENCE_THRESHOLD:
                continue

            if any(kw in text for kw in section_keywords):
                in_contacts_section = ("联系人" in text)
                logger.debug("分组标签: '%s', in_contacts=%s", text, in_contacts_section)
                continue

            if in_contacts_section and len(text) >= 1:
                if self._looks_like_name(text):
                    names.append(text)

        logger.info("解析到 %d 个联系人: %s", len(names), names[:10])
        return names

    @staticmethod
    def _looks_like_name(text: str) -> bool:
        """启发式判断是否像人名"""
        if len(text) < 1 or len(text) > 30:
            return False
        if text.isdigit():
            return False
        if all(c in " 　·•.,;:!?…—~+-*/=<>|\\/\"'@#$%^&()[]{}、。，；：？！…—～「」『』" for c in text):
            return False
        return True

    # ================================================================
    # 缓存
    # ================================================================

    def get_cached_contacts(self, keyword: str) -> Optional[list[str]]:
        entry = self._cache.get(keyword)
        if entry is None:
            return None
        ts, names = entry
        if time.time() - ts < OCR_CACHE_TTL:
            logger.debug("OCR 缓存命中: '%s' -> %d 人", keyword, len(names))
            return names
        del self._cache[keyword]
        return None

    def set_cached_contacts(self, keyword: str, names: list[str]):
        self._cache[keyword] = (time.time(), names)
        if len(self._cache) > 50:
            oldest = min(self._cache, key=lambda k: self._cache[k][0])
            del self._cache[oldest]

    def clear_cache(self):
        self._cache.clear()
