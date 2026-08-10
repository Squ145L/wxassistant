"""应用启动 + 测试命令"""

import logging
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

logger = logging.getLogger(__name__)


def cmd_test_bridge() -> int:
    """测试微信窗口连接"""
    from src.driver.wechat_bridge import WeChatBridge

    tlog = logging.getLogger("test_bridge")
    bridge = WeChatBridge()

    tlog.info("=== 1. 查找微信窗口 ===")
    if not bridge.find_window():
        tlog.error("未找到微信窗口，请确认微信 PC 版已启动。")
        return 1
    rect = bridge.get_window_rect()
    size = bridge.get_window_size()
    tlog.info("窗口: %s, 大小: %s", rect, size)

    tlog.info("=== 2. 激活窗口 ===")
    if not bridge.activate_window():
        tlog.error("窗口激活失败")
        return 1

    tlog.info("=== 3. 截取窗口 ===")
    img = bridge.screenshot_window()
    if img:
        test_path = PROJECT_ROOT / "cache" / "test_screenshot.png"
        img.save(str(test_path))
        tlog.info("截图已保存: %s", test_path)

    tlog.info("=== 4. 测试搜索 ===")
    kw = input("输入搜索词测试（直接回车跳过）: ").strip()
    if kw:
        bridge.search_contacts(kw)
        tlog.info("搜索完成。")

    tlog.info("=== 全部测试完成 ===")
    return 0


def cmd_test_ocr() -> int:
    """测试 OCR 识别"""
    from src.driver.wechat_bridge import WeChatBridge
    from OCR import OCREngine

    tlog = logging.getLogger("test_ocr")
    bridge = WeChatBridge()
    ocr = OCREngine()

    if not bridge.find_window():
        tlog.error("未找到微信窗口。")
        return 1
    bridge.activate_window()

    kw = input("输入搜索词: ").strip()
    if not kw:
        tlog.info("未输入搜索词，退出。")
        return 0

    bridge.search_contacts(kw)
    img = bridge.screenshot_window()
    if img is None:
        tlog.error("截图失败。")
        return 1

    test_path = PROJECT_ROOT / "cache" / "test_ocr_screenshot.png"
    img.save(str(test_path))
    tlog.info("截图已保存: %s", test_path)

    names = ocr.parse_contact_names(img)
    tlog.info("识别到 %d 个联系人: %s", len(names), names)
    return 0


def run_gui() -> None:
    """启动 GUI"""
    from src.driver.wechat_bridge import WeChatBridge
    from src.services.friend_service import FriendService
    from src.services.template_engine import TemplateEngine
    from src.services.send_service import SendService
    from src.ui.main_window import MainWindow
    from src.operations import (
        make_send_callback,
        make_check_names_callback,
        make_search_contacts_callback,
    )

    bridge = WeChatBridge()
    bridge.find_window()  # 主线程提前找到窗口

    friend_service = FriendService()
    template_engine = TemplateEngine()
    send_service = SendService()

    friend_service.load_cache()

    window = MainWindow()
    window.set_bridge(bridge)
    bridge.set_hook_control(
        window.suspend_interrupt_hook,
        window.resume_interrupt_hook,
    )
    window.set_friend_service(friend_service)
    window.set_send_callback(
        make_send_callback(bridge, template_engine, send_service))
    window.set_check_names_callback(
        make_check_names_callback(bridge, friend_service))
    window.set_search_contacts_callback(
        make_search_contacts_callback(bridge, friend_service))

    logger.info("启动 GUI")
    window.run()
