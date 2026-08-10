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
    """启动 GUI（单账户模式）"""
    window = _build_window(multi_session=None)
    window.run()


def run_multi_gui(session) -> None:
    """启动 GUI（多账户模式）"""
    window = _build_window(multi_session=session)
    window.run()


def _build_window(multi_session=None):
    """构造主窗口。multi_session 为 None = 单账户模式，否则多账户模式"""
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

    template_engine = TemplateEngine()
    send_service = SendService()

    if multi_session is None:
        # ---- 单账户模式（原逻辑）----
        bridge = WeChatBridge()
        bridge.find_window()
        friend_service = FriendService()
        friend_service.load_cache()

        window = MainWindow()
        window.set_bridge(bridge)
        bridge.set_hook_control(
            window.suspend_interrupt_hook,
            window.resume_interrupt_hook,
        )
        window.set_friend_service(friend_service)
        window.set_send_callback(
            make_send_callback(lambda: bridge, template_engine, send_service))
        window.set_check_names_callback(
            make_check_names_callback(lambda: bridge, friend_service))
        window.set_search_contacts_callback(
            make_search_contacts_callback(lambda: bridge, friend_service))
        window.set_enter_multiopen_callback(lambda w=window: _enter_multiopen(w))
        return window

    # ---- 多账户模式 ----
    window = MainWindow(multi_session=multi_session)

    runtime: dict[str, tuple] = {}
    all_hwnds = {acc.hwnd for acc in multi_session.accounts}
    for acc in multi_session.accounts:
        b = WeChatBridge()
        b._hwnd = acc.hwnd  # 绑定该账户窗口（不重新 find_window）
        b.set_hook_control(
            window.suspend_interrupt_hook,
            window.resume_interrupt_hook,
        )
        # 排除其他账户窗口，防止弹窗检测把别的账户主界面当"搜一搜"关掉
        b.set_excluded_windows(all_hwnds - {acc.hwnd})
        b.set_account_name(acc.name)  # 坐标/OCR 校准按账户读取
        fs = FriendService.for_account(acc.name)
        fs.load_cache()
        runtime[acc.name] = (b, fs)
    window.set_account_runtime(runtime)

    window.set_send_callback(
        make_send_callback(window.get_current_bridge, template_engine, send_service))
    window.set_check_names_callback(
        make_check_names_callback(window.get_current_bridge, window.get_current_friend_service))
    window.set_search_contacts_callback(
        make_search_contacts_callback(window.get_current_bridge, window.get_current_friend_service))
    window.set_enter_multiopen_callback(lambda w=window: _enter_multiopen(w))
    window.set_exit_multiopen_callback(lambda w=window: _exit_multiopen(w))
    return window


def _enter_multiopen(window) -> None:
    """点 [多开]：关闭主窗口 → 打开引导 → 按结果重启对应模式"""
    from src.driver.wechat_bridge import WeChatBridge
    from src.ui.multi_account_dialog import run_multiopen_wizard

    window.root.destroy()
    session = run_multiopen_wizard(WeChatBridge())
    if session is None:
        run_gui()  # 取消 → 回单账户模式
    else:
        run_multi_gui(session)


def _exit_multiopen(window) -> None:
    """点 [单用户模式]：退出多开，回到单账户模式"""
    window.root.destroy()
    run_gui()
