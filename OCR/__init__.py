"""OCR 模块 — 独立可复用

使用方式:
    from OCR import OCREngine
    ocr = OCREngine()
    texts = ocr.recognize_text(image)
    names = ocr.parse_contact_names(image)

依赖: pip install rapidocr-onnxruntime
"""

from OCR.engine import OCREngine
