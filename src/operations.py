"""后台操作回调工厂 — 发送/检查/搜索

所有回调接收 progress_queue + stop_event，通过 stop_event 支持中断。
不导入 ui/ 层。
"""

import logging
import queue
import re
import time

import win32gui
import win32api
import win32con

from src.services.send_service import SendResult
from src.utils.calibration import load_calibration
from src.utils.coordinates import get_coord, resolve_calibration_rect

logger = logging.getLogger(__name__)


# ================================================================
# 群发回调
# ================================================================

def make_send_callback(get_bridge, template_engine, send_service):
    """创建群发后台回调（get_bridge: 可调用，返回当前账户的 WeChatBridge）

    流程：遍历好友 → 渲染 → 搜索 → OCR 验证 → 发送
    """

    def do_send(
        friends: list, message_template: str, attachments: list[str],
        interval: float, regex_pattern: str,
        progress_queue: queue.Queue, stop_event,
    ):
        bridge = get_bridge()
        compiled_regex = None
        if regex_pattern:
            try:
                compiled_regex = re.compile(regex_pattern)
            except re.error:
                pass

        bridge.set_stop_check(lambda: stop_event.is_set())

        def _stopped():
            return stop_event.is_set()

        def send_one(friend) -> SendResult:
            if _stopped():
                return SendResult(friend_name=friend.name, success=False, error="已中断")

            name = friend.name
            try:
                regex_match = compiled_regex.search(name) if compiled_regex else None
                rendered = template_engine.render(message_template, friend, regex_match=regex_match)

                if _stopped():
                    return SendResult(friend_name=name, success=False, error="已中断")

                found = bridge.search_contacts(name)
                if not found:
                    return SendResult(friend_name=name, success=False, error="联系人不存在(搜索弹窗已关闭)")

                if _stopped():
                    return SendResult(friend_name=name, success=False, error="已中断")

                matched, _ = bridge.match_chat_title(name)
                if not matched:
                    return SendResult(friend_name=name, success=False, error="OCR验证失败: 聊天对象不匹配")

                if _stopped():
                    return SendResult(friend_name=name, success=False, error="已中断")

                if rendered.strip():
                    bridge.send_text_message(rendered)

                for filepath in attachments:
                    if _stopped():
                        return SendResult(friend_name=name, success=False, error="已中断")
                    bridge.send_file_message(filepath)

                return SendResult(friend_name=name, success=True)

            except Exception as e:
                logger.exception("发送失败: %s", name)
                return SendResult(friend_name=name, success=False, error=str(e))

        def on_progress(current: int, total: int, result: SendResult):
            progress_queue.put((
                "__PROGRESS__",
                current, total,
                current - (1 if result and not result.success else 0),
                1 if result and not result.success else 0,
                result.friend_name if result else "",
                result.error if result and not result.success else None,
            ))

        send_service._stop_event = stop_event
        send_service.base_interval = interval
        batch = send_service.send_batch(friends=friends, send_one=send_one, on_progress=on_progress)

        progress_queue.put(("__DONE__", batch.success, batch.failed, batch.failed_list, batch.results))
        send_service.reset()

    return do_send


# ================================================================
# 检查联系人名字回调
# ================================================================

def make_check_names_callback(get_bridge, friend_service):
    """检查选中好友名称是否完整（get_bridge: 返回当前账户 WeChatBridge）"""

    def do_check(friends: list, progress_queue: queue.Queue, stop_event):
        bridge = get_bridge()
        bridge.set_stop_check(lambda: stop_event.is_set())
        diffs: dict[str, str] = {}
        failed: dict[str, str] = {}

        for friend in friends:
            if stop_event.is_set():
                progress_queue.put(("__LOG__", "已中断"))
                break
            name = friend.name
            try:
                found = bridge.search_contacts(name)
                if not found:
                    if not stop_event.is_set():
                        logger.info("检查名字: '%s' — 搜不到", name)
                        failed[name] = "搜索失败"
                    continue

                matched, ocr_name = bridge.match_chat_title(name)
                if matched and ocr_name and ocr_name != name:
                    logger.info("检查名字: '%s' -> '%s'", name, ocr_name)
                    diffs[name] = ocr_name
                    failed[name] = f"'{ocr_name}' (expected='{name}')"
                elif not matched:
                    logger.info("检查名字: '%s' — OCR 不匹配 '%s'", name, ocr_name)
                    failed[name] = f"'{ocr_name}' (expected='{name}')"
                else:
                    logger.info("检查名字: '%s' — 已完整", name)

            except Exception as e:
                logger.exception("检查名字异常: '%s'", name)

        progress_queue.put(("__NAME_CHECK_DONE__", diffs, failed))

    return do_check


# ================================================================
# 通讯录扫描（公共）—— 截图和 OCR 分离
# ================================================================

def _capture_contacts_manager(bridge, progress_queue, stop_event, keyword: str = ""):
    """截图循环（前台，可中断）→ 返回保存的图片路径列表"""
    import os
    temp_dir = "cache/temp_scan"
    os.makedirs(temp_dir, exist_ok=True)
    # 清旧文件
    for f in os.listdir(temp_dir):
        os.remove(os.path.join(temp_dir, f))

    hwnd = bridge.open_contacts_manager()
    if hwnd is None:
        progress_queue.put(("__LOG__", "❌ 未找到通讯录管理窗口"))
        return []

    rect = win32gui.GetWindowRect(hwnd)
    if rect:
        cx_pct, cy_pct = get_coord("cm_list_focus", bridge.account_name)
        fx = rect[0] + int((rect[2] - rect[0]) * cx_pct)
        fy = rect[1] + int((rect[3] - rect[1]) * cy_pct)
        bridge.click_at(fx, fy)
        time.sleep(0.15)
        for _ in range(8):
            if stop_event.is_set(): break
            bridge.scroll_at(fx, fy, 200 * 120)  # 正数=往上滚到顶
            time.sleep(0.03)
    time.sleep(0.3)

    if keyword and rect:
        sx_pct, sy_pct = get_coord("cm_search_box", bridge.account_name)
        sx = rect[0] + int((rect[2] - rect[0]) * sx_pct)
        sy = rect[1] + int((rect[3] - rect[1]) * sy_pct)
        bridge.click_at(sx, sy)
        time.sleep(0.2)
        main_hwnd = bridge._hwnd
        bridge._hwnd = hwnd
        bridge._send_keys('{Ctrl}a')
        time.sleep(0.03)
        import pyperclip
        pyperclip.copy(keyword)
        time.sleep(0.05)
        bridge._send_keys('{Ctrl}v')
        time.sleep(0.3)
        bridge._hwnd = main_hwnd

    from src.utils.settings_store import load_scan_settings
    scan = load_scan_settings()
    page_count = scan["page_count"]
    scroll_px = scan["scroll_px"]
    scroll_times = scan.get("pages_per_scroll", 1)  # 每页滚几次

    calib = load_calibration("contacts_list", bridge.account_name)
    rect = win32gui.GetWindowRect(hwnd)
    left, top, right, bottom = rect
    ww, wh = right - left, bottom - top
    x1, y1, x2, y2 = resolve_calibration_rect(calib, rect)

    paths = []
    for page in range(page_count):
        if stop_event.is_set():
            progress_queue.put(("__LOG__", "已中断"))
            break
        progress_queue.put(("__PROGRESS__", page + 1, page_count, 0, 0, "", None))
        progress_queue.put(("__LOG__", f"截图第 {page + 1}/{page_count} 页..."))

        img = bridge.screenshot_region(x1, y1, x2, y2)
        if img:
            path = os.path.join(temp_dir, f"page_{page:03d}.png")
            img.save(path)
            paths.append(path)

        if page < page_count - 1 and not stop_event.is_set():
            cx = left + int(ww * 0.5)
            cy = top + int(wh * 0.5)
            win32api.SetCursorPos((cx, cy))
            time.sleep(0.03)
            for _ in range(scroll_times):
                if stop_event.is_set(): break
                win32api.mouse_event(win32con.MOUSEEVENTF_WHEEL, 0, 0, -scroll_px, 0)
                time.sleep(0.05)
            time.sleep(0.3)

    bridge.close_contacts_manager()
    return paths


def _ocr_pages(paths: list[str], progress_queue, stop_event) -> list[str]:
    """后台 OCR（可中断）→ 返回已扫描到的名字列表"""
    from OCR import OCREngine
    ocr = OCREngine()
    all_names: list[str] = []
    same_count = 0

    for i, path in enumerate(paths):
        if stop_event and stop_event.is_set():
            progress_queue.put(("__LOG__", f"OCR已中断，保留已扫描 {len(all_names)} 人"))
            break
        try:
            progress_queue.put(("__PROGRESS__", i + 1, len(paths), 0, 0, "", None))
            from PIL import Image
            img = Image.open(path)
            names = [t for t in ocr.recognize_text(img) if 2 <= len(t) <= 20 and not t.isdigit()]
            new_in_page = [n for n in names if n not in all_names]
            all_names.extend(new_in_page)
            progress_queue.put(("__LOG__", f"OCR第{i + 1}页: +{len(new_in_page)}人 (累计{len(all_names)})"))

            if not new_in_page:
                same_count += 1
                if same_count >= 3:
                    progress_queue.put(("__LOG__", "连续3页无新联系人，OCR完成"))
                    break
            else:
                same_count = 0
        except Exception as e:
            progress_queue.put(("__LOG__", f"OCR第{i + 1}页失败: {e}"))

    return list(dict.fromkeys(all_names))


def _save_debug_screenshots(paths: list[str], progress_queue) -> None:
    """复制 OCR 截图到 debug_scan 目录供用户检查"""
    import shutil as _shutil
    debug_dir = "cache/debug_scan"
    try:
        _shutil.rmtree(debug_dir, ignore_errors=True)
        import os as _os
        _os.makedirs(debug_dir, exist_ok=True)
        for p in paths:
            _shutil.copy2(p, debug_dir)
        progress_queue.put(("__LOG__", f"调试截图已保存到 {debug_dir}/ ({len(paths)} 张)"))
    except Exception as e:
        progress_queue.put(("__LOG__", f"调试截图保存失败: {e}"))


def _cleanup_temp_scan(progress_queue) -> None:
    """清空临时截图目录"""
    import os as _os
    import shutil as _shutil
    temp_dir = "cache/temp_scan"
    try:
        _shutil.rmtree(temp_dir, ignore_errors=True)
    except Exception:
        pass


# ================================================================
# 导入回调
# ================================================================

def make_search_contacts_callback(get_bridge, friend_service):
    """搜索并导入 / 扫描通讯录并导入（get_bridge: 返回当前账户 WeChatBridge）"""

    def do_search(keyword: str, progress_queue: queue.Queue, stop_event):
        bridge = get_bridge()
        bridge.set_stop_check(lambda: stop_event.is_set())
        try:
            # 阶段1: 截图（鼠标中断可触发）
            paths = _capture_contacts_manager(bridge, progress_queue, stop_event, keyword)
            progress_queue.put(("__LOG__", f"扫描完成 {len(paths)} 页，正在后台 OCR..."))
            progress_queue.put(("__SCAN_DONE_FOCUS__", len(paths)))
            if not paths:
                progress_queue.put(("__INTERRUPT_OFF__", None))
                progress_queue.put(("__NAME_CHECK_DONE__", {}, {}))
                return

            # 阶段2: 后台 OCR（可终止）
            stop_event.clear()
            names = _ocr_pages(paths, progress_queue, stop_event)
            progress_queue.put(("__PROGRESS__", len(paths), len(paths), 0, 0, "", None))

            # OCR 完成 → 关闭中断
            progress_queue.put(("__INTERRUPT_OFF__", None))

            # OCR 调试截图：根据设置决定是否保留一份副本
            from src.utils.settings_store import load_settings
            if load_settings().get("ocr_debug_save", False):
                _save_debug_screenshots(paths, progress_queue)
            # temp_scan 是临时目录，无论如何都清掉
            _cleanup_temp_scan(progress_queue)

            # 阶段3: 弹确认窗
            if names:
                progress_queue.put(("__IMPORT_CONFIRM__", names))
            progress_queue.put(("__NAME_CHECK_DONE__", {}, {}))
            progress_queue.put(("__LOG__", f"共 {len(names)} 个联系人"))

        except Exception as e:
            logger.exception("操作异常")
            progress_queue.put(("__LOG__", f"❌ 错误: {e}"))
            progress_queue.put(("__NAME_CHECK_DONE__", {}))

    return do_search


# ================================================================
# 工具
# ================================================================
