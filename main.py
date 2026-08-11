"""微信助手 - 群发工具 | 入口

用法:
    python main.py                # 启动 GUI
    python main.py --test-bridge  # 测试微信窗口连接
    python main.py --test-ocr     # 测试 OCR
"""

# ⚠️ 必须在所有 import 之前：声明 DPI 感知，防止高 DPI 屏幕截图不全
# 不设这个的话，150%/175% DPI 屏幕上 GetWindowRect 返回虚拟坐标，
# 而 ImageGrab 用物理像素，二者不匹配导致截图只截到 67% 区域。
import ctypes as _ctypes
try:
    _ctypes.windll.shcore.SetProcessDpiAwareness(2)  # Per-Monitor DPI Aware
except Exception:
    try:
        _ctypes.windll.user32.SetProcessDPIAware()    # 旧版 API fallback
    except Exception:
        pass

import sys
import argparse
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.utils.logger import setup_logging


def main():
    parser = argparse.ArgumentParser(description="微信助手 - 群发工具")
    parser.add_argument("--test-bridge", action="store_true", help="测试微信窗口连接")
    parser.add_argument("--test-ocr", action="store_true", help="测试 OCR 识别")
    args = parser.parse_args()

    setup_logging()

    # 启动时应用用户日志开关设置
    from src.utils.settings_store import load_settings
    if not load_settings().get("logging_enabled", True):
        from src.utils.logger import set_file_logging
        set_file_logging(False)

    # OCR 模型后台预热：首次加载约需 1-2 分钟，若发生在检查/发送操作内会阻塞且无法中断。
    # 启动即后台加载，操作时模型已就绪；日志自动进发送日志面板。
    import threading
    from OCR.engine import warmup_ocr
    threading.Thread(target=warmup_ocr, daemon=True).start()

    if args.test_bridge:
        from src.app import cmd_test_bridge
        sys.exit(cmd_test_bridge())
    if args.test_ocr:
        from src.app import cmd_test_ocr
        sys.exit(cmd_test_ocr())

    from src.app import run_gui
    run_gui()


if __name__ == "__main__":
    main()
