"""微信窗口驱动：UIA SendKeys + 鼠标点击 + 截图 + OCR 聊天验证"""

import json
import logging
import os
import subprocess
import time
from pathlib import Path
from typing import Optional, Tuple

import pythoncom
import win32gui
import win32con
import win32api
import uiautomation as uia
import pyperclip
from PIL import Image, ImageGrab

from src.utils.config import (
    WEIXIN_WINDOW_TITLES,
    CLIPBOARD_DELAY,
    ACTIVATE_DELAY,
    SEARCH_DELAY,
    FILE_SEND_DELAY,
)
from src.utils.coordinates import get_coord, resolve_calibration_rect

logger = logging.getLogger(__name__)

# OCR 校准配置文件路径（和 calibrate.py 同样的位置格式）
OCR_CALIBRATION_PATH = Path("cache/ocr_calibration.json")

# OCR 混淆字符映射配置（在 OCR 引擎中也会加载）
OCR_CONFUSION_PATH = Path("OCR/ocr_confusion.json")

# 聊天标题区域的默认校准参数（窗口内相对坐标）
#   LEFT_MARGIN: 距左边缘 px
#   TOP_PCT:     距顶部比例 (0~1)
#   RIGHT_MARGIN: 距右边缘 px
#   BOTTOM_MARGIN: 距离底部高度比例, by = wh * (1 - BOTTOM_MARGIN)
DEFAULT_CHAT_TITLE_CALIB = {
    "LEFT_MARGIN": 0.05,      # 百分比（兼容旧格式：>1 = 像素）
    "TOP_PCT": 0.015,
    "RIGHT_MARGIN": 0.06,     # 百分比（兼容旧格式：>1 = 像素）
    "BOTTOM_MARGIN": 0.91,    # 标题栏占窗口 ~9% 高度
}


class WeChatNotFoundError(Exception):
    """未找到微信窗口"""


class WeChatBridge:
    """微信 PC 4.x 窗口驱动

    键盘输入：UIA SendKeys → 直接投递到微信窗口
    鼠标操作：win32api SetCursorPos + mouse_event
    截图：PIL ImageGrab

    注意：UIA 对象是 COM 线程绑定的，每次 _send_keys 都会
    在调用线程中重新 CoInitialize + ControlFromHandle。
    """

    def __init__(self):
        self._hwnd: Optional[int] = None
        self._stop_check = None
        self._hook_suspend = None
        self._hook_resume = None

    def set_stop_check(self, checker):
        self._stop_check = checker

    def set_hook_control(self, suspend_fn, resume_fn):
        """注入钩子开关：SendKeys 前暂停钩子，之后恢复"""
        self._hook_suspend = suspend_fn
        self._hook_resume = resume_fn

    def _should_stop(self) -> bool:
        if self._stop_check:
            return self._stop_check()
        return False

    # ================================================================
    # 窗口查找
    # ================================================================

    def _ensure_com(self):
        """每个线程必须独立初始化 COM（UIA 底层依赖 COM，线程绑定）"""
        try:
            pythoncom.CoInitialize()
        except Exception:
            pass  # 已初始化则忽略

    def _get_uia_control(self) -> Optional[uia.Control]:
        """在当前线程创建 UIA 控件（COM 线程绑定，不能跨线程共用）"""
        if self._hwnd is None:
            logger.warning("窗口句柄为空，无法创建 UIA 控件")
            return None
        self._ensure_com()
        try:
            return uia.ControlFromHandle(self._hwnd)
        except Exception:
            logger.exception("创建 UIA 控件失败")
            return None

    def find_all_windows(self) -> list[tuple[int, str, str]]:
        """枚举所有可见微信主窗口，返回 [(hwnd, title, class)] 列表

        匹配规则与 find_window 一致：Qt 类名 + 标题含 '微信'/'Weixin'，
        排除自身进程的窗口。找不到则返回空列表。
        """
        import win32process
        self._ensure_com()
        self_pid = os.getpid()

        def _is_self(hwnd: int) -> bool:
            try:
                _, pid = win32process.GetWindowThreadProcessId(hwnd)
                return pid == self_pid
            except Exception:
                return False

        matches: list[tuple[int, str, str]] = []

        def _enum(hwnd: int, results: list) -> bool:
            if not win32gui.IsWindowVisible(hwnd) or _is_self(hwnd):
                return True
            title = win32gui.GetWindowText(hwnd)
            cls = win32gui.GetClassName(hwnd)
            if any(pattern in title for pattern in WEIXIN_WINDOW_TITLES) and 'Qt' in cls:
                results.append((hwnd, title, cls))
            return True

        win32gui.EnumWindows(_enum, matches)
        return matches

    def find_window(self) -> bool:
        """查找微信窗口：取 find_all_windows 的第一个匹配（保持单账户行为）"""
        matches = self.find_all_windows()
        if matches:
            self._hwnd = matches[0][0]
            title, cls = matches[0][1], matches[0][2]
            logger.info("已连接微信: hwnd=0x%X, class='%s', title='%s'",
                        self._hwnd, cls, title)
            return True
        logger.warning("未找到微信窗口（标题含'微信'/'Weixin'）")
        return False

    def require_window(self):
        """确保已连接微信，否则抛异常"""
        if not self.is_window_valid() and not self.find_window():
            raise WeChatNotFoundError("微信未运行。请先启动微信 PC 版。")

    def is_window_valid(self) -> bool:
        if self._hwnd is None:
            return False
        try:
            return bool(win32gui.IsWindow(self._hwnd))
        except Exception:
            return False

    @property
    def hwnd(self) -> Optional[int]:
        if not self.is_window_valid():
            self._hwnd = None
        return self._hwnd

    # ================================================================
    # 窗口激活
    # ================================================================

    def activate_window(self) -> bool:
        """激活微信窗口（Alt键技巧 + SetForegroundWindow）"""
        self.require_window()
        hwnd = self._hwnd

        # keybd_event 会触发中断钩子，暂停
        if self._hook_suspend: self._hook_suspend()
        try:
            if win32gui.IsIconic(hwnd):
                win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
                time.sleep(0.3)

            win32gui.SetWindowPos(hwnd, win32con.HWND_TOPMOST,
                                  0, 0, 0, 0,
                                  win32con.SWP_NOMOVE | win32con.SWP_NOSIZE)
            win32gui.SetWindowPos(hwnd, win32con.HWND_NOTOPMOST,
                                  0, 0, 0, 0,
                                  win32con.SWP_NOMOVE | win32con.SWP_NOSIZE)

            win32api.keybd_event(win32con.VK_MENU, 0, 0, 0)
            win32gui.SetForegroundWindow(hwnd)
            win32api.keybd_event(win32con.VK_MENU, 0, win32con.KEYEVENTF_KEYUP, 0)

            time.sleep(ACTIVATE_DELAY)
            logger.info("窗口已激活: 0x%X", hwnd)
            return True

        except Exception:
            logger.exception("窗口激活失败")
            return False
        finally:
            if self._hook_resume: self._hook_resume()

    # ================================================================
    # 键盘模拟 — UIA SendKeys（线程安全，每次创建 UIA 控件）
    # ================================================================

    def _send_keys(self, keys: str):
        """UIA SendKeys — 暂停钩子防止模拟按键触发中断"""
        if self._should_stop():
            logger.info("SendKeys 已中断，跳过: %s", keys)
            return
        # 暂停中断钩子（模拟按键会触发 WH_KEYBOARD_LL）
        if self._hook_suspend:
            self._hook_suspend()
        ctrl = self._get_uia_control()
        if ctrl is not None:
            try:
                ctrl.SendKeys(keys)
                logger.debug("SendKeys: %s", keys)
            except Exception:
                logger.exception("SendKeys 失败: %s", keys)
        if self._hook_resume:
            self._hook_resume()

    def _paste_and_enter(self, text: str):
        """剪贴板复制 → Ctrl+V 粘贴 → Enter 发送"""
        pyperclip.copy(text)
        time.sleep(CLIPBOARD_DELAY)
        self._send_keys('{Ctrl}v')
        time.sleep(0.03)          # 粘贴后稍等
        self._send_keys('{Enter}')
        time.sleep(0.05)          # 发送后稍等

    # ================================================================
    # 鼠标模拟
    # ================================================================

    def click_at(self, x: int, y: int):
        """鼠标左键单击（暂停钩子防自触发）"""
        if self._hook_suspend: self._hook_suspend()
        logger.info("click_at: (%d, %d)", x, y)
        win32api.SetCursorPos((x, y))
        time.sleep(0.02)
        win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
        time.sleep(0.03)
        win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
        if self._hook_resume: self._hook_resume()

    def scroll_at(self, x: int, y: int, delta: int):
        """鼠标滚轮（暂停钩子防自触发）"""
        if self._hook_suspend: self._hook_suspend()
        try:
            win32api.SetCursorPos((x, y))
            time.sleep(0.02)
            win32api.mouse_event(win32con.MOUSEEVENTF_WHEEL, 0, 0, delta, 0)
        except Exception:
            logger.exception("滚轮失败")
        if self._hook_resume: self._hook_resume()

    # ================================================================
    # 窗口信息
    # ================================================================

    def get_window_rect(self) -> Optional[Tuple[int, int, int, int]]:
        if self.hwnd is None:
            return None
        try:
            return win32gui.GetWindowRect(self.hwnd)
        except Exception:
            logger.exception("获取窗口位置失败")
            return None

    def get_window_size(self) -> Optional[Tuple[int, int]]:
        rect = self.get_window_rect()
        if rect is None:
            return None
        return (rect[2] - rect[0], rect[3] - rect[1])

    # ================================================================
    # 截图
    # ================================================================

    def screenshot_region(self, left, top, right, bottom) -> Optional[Image.Image]:
        try:
            img = ImageGrab.grab(bbox=(left, top, right, bottom), all_screens=True)
            logger.debug("截图: (%d,%d)-(%d,%d) %dx%d", left, top, right, bottom, img.width, img.height)
            return img
        except Exception:
            logger.exception("截图失败")
            return None

    def screenshot_window(self) -> Optional[Image.Image]:
        rect = self.get_window_rect()
        if rect is None:
            return None
        return self.screenshot_region(*rect)

    # ================================================================
    # OCR 聊天验证
    # ================================================================

    @staticmethod
    def _load_confusion_map() -> dict:
        """加载 OCR 混淆字符映射表（带缓存，文件不存在则返回空表）"""
        if not OCR_CONFUSION_PATH.exists():
            return {}
        try:
            data = json.loads(OCR_CONFUSION_PATH.read_text(encoding="utf-8"))
            # 过滤掉以 _ 开头的注释字段
            return {k: v for k, v in data.items() if not k.startswith("_")}
        except Exception:
            logger.warning("OCR 混淆配置读取失败", exc_info=True)
            return {}

    @staticmethod
    def _normalize_confusable(text: str, confusion_map: dict) -> str:
        """按混淆映射表归一化文本中的易混淆字符"""
        if not confusion_map:
            return text
        result = text
        for src, dst in confusion_map.items():
            result = result.replace(src, dst)
        return result

    def _get_chat_title_rect(self) -> Optional[Tuple[int, int, int, int]]:
        """获取聊天标题区域的屏幕坐标（按校准参数从窗口推算）"""
        rect = self.get_window_rect()
        if rect is None:
            return None

        # 加载校准参数
        calib = dict(DEFAULT_CHAT_TITLE_CALIB)
        if OCR_CALIBRATION_PATH.exists():
            try:
                data = json.loads(OCR_CALIBRATION_PATH.read_text(encoding="utf-8"))
                if "chat_title" in data:
                    calib.update(data["chat_title"])
            except Exception:
                logger.warning("OCR 校准文件读取失败，使用默认值")

        result = resolve_calibration_rect(calib, rect)
        logger.debug("聊天标题区域: (%d,%d)-(%d,%d)", *result)
        return result

    def match_chat_title(self, expected_name: str):
        """截图聊天标题 → OCR → 从首字符开始匹配

        规则：
        1. OCR 结果和 expected_name 从第一个字开始比较
        2. 只要短的是长的前缀就算匹配
          例: expected="25级李"  ocr="25级李华"  → 匹配
          例: expected="25级李华" ocr="25级李"   → 匹配
        3. 返回 OCR 到的实际名称（可能比 expected 长）

        Returns: (matched: bool, ocr_name: str)
        """
        title_rect = self._get_chat_title_rect()
        if title_rect is None:
            logger.warning("无法获取聊天标题区域")
            return (False, "")

        img = self.screenshot_region(*title_rect)
        if img is None:
            return (False, "")

        from OCR import OCREngine
        ocr = OCREngine()
        texts = ocr.recognize_text(img)
        ocr_text = "".join(texts).strip()
        logger.info("OCR 聊天标题: '%s' (expected='%s')", ocr_text, expected_name)

        if not ocr_text:
            return (False, "")

        # 加载混淆字符映射，归一化后再比较
        confusion_map = self._load_confusion_map()
        norm_expected = self._normalize_confusable(expected_name, confusion_map)
        norm_ocr = self._normalize_confusable(ocr_text, confusion_map)

        if norm_expected != expected_name or norm_ocr != ocr_text:
            logger.info(
                "归一化: expected '%s'→'%s', ocr '%s'→'%s'",
                expected_name, norm_expected, ocr_text, norm_ocr,
            )

        # 清洗 OCR 结果中的微信 UI 噪声
        #   '+test2(3)' → 'test2'  (去除前导 +、后缀括号数字、前导空格)
        import re
        cleaned_ocr = norm_ocr
        # 前导噪声: +、空格、emoji 等
        cleaned_ocr = re.sub(r'^[\s+➕※†‡•·▪▸►▻❖◇◆○●◎◉◎⦿⊙⊕⊗⨁⨂⨷➤➢➣✚✙✛✜✢✣✤✥✦✧✩✪✫✬✭✮✯✰]+', '', cleaned_ocr)
        # 后缀噪声: (3)、(3人) 等
        cleaned_ocr = re.sub(r'[\s]*[\(（]\d+[\)）]\s*$', '', cleaned_ocr)
        cleaned_ocr = cleaned_ocr.strip()

        if cleaned_ocr and cleaned_ocr != norm_ocr:
            logger.info("OCR 清洗: '%s' → '%s'", norm_ocr, cleaned_ocr)

        # 匹配策略（按优先级尝试）:
        # 1. 清洗后的前缀匹配（处理 UI 装饰噪声）
        # 2. 原始子串包含匹配（处理 OCR 拼接场景）
        short = norm_expected if len(norm_expected) <= len(cleaned_ocr) else cleaned_ocr
        long_ = cleaned_ocr if len(norm_expected) <= len(cleaned_ocr) else norm_expected

        matched = False
        if long_.startswith(short):
            matched = True
        elif norm_expected in cleaned_ocr or cleaned_ocr in norm_expected:
            matched = True
        else:
            # 3. 序列相似度兜底（OCR 漏字/多字场景，如 '高一卓' vs '高卓'）
            from difflib import SequenceMatcher
            ratio = SequenceMatcher(None, norm_expected, cleaned_ocr).ratio()
            if ratio >= 0.7:
                logger.info("模糊匹配: ratio=%.2f '%s' ↔ '%s'", ratio, norm_expected, cleaned_ocr)
                matched = True

        if matched:
            logger.info("标题匹配: '%s' ↔ '%s' (ocr='%s')", expected_name, cleaned_ocr, ocr_text)
            return (True, ocr_text)

        logger.warning("标题不匹配: '%s' vs '%s' (ocr='%s')", expected_name, cleaned_ocr, ocr_text)
        return (False, "")

    # ================================================================
    # 微信操作
    # ================================================================

    def search_contacts(self, keyword: str) -> bool:
        """激活微信 → Ctrl+F → 粘贴关键词 → Enter"""
        if self._should_stop(): return False
        logger.info("搜索联系人: '%s'", keyword)
        self.activate_window()
        # 锁定主窗口句柄，防止搜索后浮层子窗口干扰坐标计算
        main_hwnd = self._hwnd
        if self._should_stop(): return False
        self._send_keys('{Ctrl}f')
        time.sleep(0.03)
        if self._should_stop(): return False
        self._send_keys('{Ctrl}a')
        time.sleep(0.03)
        self._paste_and_enter(keyword)
        time.sleep(SEARCH_DELAY)
        if self._should_stop(): return False

        self._click_sousou_independent_btn(main_hwnd)

        if self._close_search_popup():
            logger.info("搜索弹窗已关闭，联系人不存在: '%s'", keyword)
            return False
        return True

    def _click_sousou_independent_btn(self, main_hwnd: int = 0):
        """搜一搜独立窗口处理：点击独立窗口按钮（设置开关+坐标非零时生效）

        main_hwnd: 搜索前锁定的主窗口句柄，避免被浮层子窗口干扰。
        """
        try:
            from src.ui.settings_dialog import load_settings
            settings = load_settings()
            if not settings.get("sousou_independent_enabled", False):
                return
        except Exception:
            return

        from src.utils.coordinates import get_coord
        x_pct, y_pct = get_coord("sousou_independent_btn")
        if x_pct == 0.0 and y_pct == 0.0:
            return

        # 直接用传入的主窗口 hwnd，不调用任何 find_window 或属性
        if not main_hwnd:
            main_hwnd = self._hwnd
        if not main_hwnd or not win32gui.IsWindow(main_hwnd):
            return
        try:
            rect = win32gui.GetWindowRect(main_hwnd)
        except Exception:
            return
        ww = rect[2] - rect[0]
        wh = rect[3] - rect[1]

        cx = rect[0] + int(ww * x_pct)
        cy = rect[1] + int(wh * y_pct)
        logger.info("搜一搜独立窗口: hwnd=0x%X coord=(%.4f,%.4f) → 屏幕(%d,%d)",
                    main_hwnd, x_pct, y_pct, cx, cy)
        self.click_at(cx, cy)
        time.sleep(0.3)

    def _close_search_popup(self) -> bool:
        """检测并关闭微信搜索弹窗

        - 「添加朋友」: 同进程 + Qt 类名
        - 「搜一搜」: 独立进程 + Chrome_WidgetWin_0 类名（Chromium/CEF）
        共同特征：标题都是"微信"（和主窗口一样）
        """
        if self._hwnd is None:
            return False

        import win32process
        try:
            _, main_pid = win32process.GetWindowThreadProcessId(self._hwnd)
        except Exception:
            main_pid = None

        main_title = win32gui.GetWindowText(self._hwnd)
        popup_hwnd = None

        def _enum(hwnd, _):
            nonlocal popup_hwnd
            if hwnd == self._hwnd:
                return True
            if not win32gui.IsWindowVisible(hwnd):
                return True

            cls = win32gui.GetClassName(hwnd)
            title = win32gui.GetWindowText(hwnd)

            # 条件1: 同进程的 Qt 窗口 → 添加朋友
            if main_pid is not None and 'Qt' in cls:
                try:
                    _, pid = win32process.GetWindowThreadProcessId(hwnd)
                except Exception:
                    pid = None
                if pid == main_pid:
                    popup_hwnd = hwnd
                    return False

            # 条件2: 标题含"微信"且不是主窗口 → 搜一搜（Chromium窗口）
            if title and main_title and title == main_title:
                popup_hwnd = hwnd
                return False

            return True

        win32gui.EnumWindows(_enum, None)

        if popup_hwnd is None:
            return False

        title = win32gui.GetWindowText(popup_hwnd)
        cls = win32gui.GetClassName(popup_hwnd)
        logger.info("发现搜索弹窗: 0x%X '%s' cls=[%s]", popup_hwnd, title, cls)

        # 策略1: WM_CLOSE（不模拟输入，安全）
        try:
            win32gui.PostMessage(popup_hwnd, win32con.WM_CLOSE, 0, 0)
        except Exception:
            pass
        time.sleep(0.05)
        if not win32gui.IsWindow(popup_hwnd) or not win32gui.IsWindowVisible(popup_hwnd):
            logger.info("弹窗已关闭 (WM_CLOSE)")
            return True

        # 策略2: Alt+F4，通过 _send_keys 走钩子暂停路径
        orig_hwnd = self._hwnd
        try:
            self._hwnd = popup_hwnd
            self._send_keys('%{F4}')
        except Exception:
            pass
        finally:
            self._hwnd = orig_hwnd
        time.sleep(0.05)
        if not win32gui.IsWindow(popup_hwnd) or not win32gui.IsWindowVisible(popup_hwnd):
            logger.info("弹窗已关闭 (Alt+F4)")
            return True

        logger.warning("弹窗未关闭: 0x%X '%s' cls=[%s]", popup_hwnd, title, cls)
        return True

    def open_chat(self, name: str):
        """搜索联系人并打开聊天"""
        logger.info("打开聊天: '%s'", name)
        self.search_contacts(name)
        time.sleep(CHAT_OPEN_DELAY)

    def send_text_message(self, text: str):
        """发送文本消息"""
        display = text[:60] + "..." if len(text) > 60 else text
        logger.info("发送文本: %s", display)
        self._paste_and_enter(text)

    def send_file_message(self, filepath: str):
        """发送文件（剪贴板复制文件本身 → Ctrl+V → Enter）"""
        logger.info("发送文件: %s", filepath)
        if not os.path.exists(filepath):
            logger.error("文件不存在: %s", filepath)
            return
        # CF_HDROP 格式复制文件到剪贴板（不是路径文字）
        self._copy_file_to_clipboard(filepath)
        time.sleep(0.1)
        self._send_keys('{Ctrl}v')
        time.sleep(0.1)
        self._send_keys('{Enter}')
        time.sleep(FILE_SEND_DELAY)

    @staticmethod
    def _copy_file_to_clipboard(filepath: str):
        """将文件以 CF_HDROP 格式复制到剪贴板（微信识别为文件）"""
        subprocess.run(
            ['powershell', '-NoProfile', '-Command',
             f'Set-Clipboard -Path "{filepath}"'],
            capture_output=True, timeout=10,
        )

    def click_contacts_tab(self):
        """点击通讯录标签 — 先移光标到安全位置，避免误折叠联系人"""
        self.activate_window()
        rect = self.get_window_rect()
        if rect is None:
            return
        ww = rect[2] - rect[0]
        wh = rect[3] - rect[1]
        # 先把光标移到窗口中间偏下（安全区，不会点到折叠按钮）
        safe_x_pct, safe_y_pct = get_coord("safe_zone")
        safe_x = rect[0] + int(ww * safe_x_pct)
        safe_y = rect[1] + int(wh * safe_y_pct)
        self.click_at(safe_x, safe_y)
        time.sleep(0.15)
        # 再点通讯录标签
        cx_pct, cy_pct = get_coord("tab_contacts")
        cx = rect[0] + int(ww * cx_pct)
        cy = rect[1] + int(wh * cy_pct)
        self.click_at(cx, cy)
        time.sleep(0.2)

    def open_contacts_manager(self) -> Optional[int]:
        """点击通讯录 → 点击「通讯录管理」→ 等弹窗 → 最大化"""
        self.click_contacts_tab()
        time.sleep(0.3)

        rect = self.get_window_rect()
        if rect is None:
            return None
        ww = rect[2] - rect[0]
        wh = rect[3] - rect[1]
        cx_pct, cy_pct = get_coord("btn_contacts_mgr")
        cx = rect[0] + int(ww * cx_pct)
        cy = rect[1] + int(wh * cy_pct)
        logger.info("点击通讯录管理: (%d,%d)", cx, cy)
        self.click_at(cx, cy)
        time.sleep(0.3)

        popup = self._find_contacts_manager_window()
        if popup is None:
            logger.warning("未找到通讯录管理窗口")
            return None

        self._maximize_window(popup)
        time.sleep(0.3)
        return popup

    def close_contacts_manager(self):
        """关闭通讯录管理窗口（标题含'通讯录管理'的同进程窗口）"""
        if self._hwnd is None:
            return

        import win32process
        try:
            _, main_pid = win32process.GetWindowThreadProcessId(self._hwnd)
        except Exception:
            return

        popup = None

        def _enum(hwnd, _):
            nonlocal popup
            if hwnd == self._hwnd:
                return True
            if not win32gui.IsWindowVisible(hwnd):
                return True
            if "通讯录管理" not in win32gui.GetWindowText(hwnd):
                return True
            try:
                _, pid = win32process.GetWindowThreadProcessId(hwnd)
            except Exception:
                return True
            if pid != main_pid:
                return True
            popup = hwnd
            return False

        win32gui.EnumWindows(_enum, None)
        if popup:
            logger.info("关闭通讯录管理窗口: 0x%X", popup)
            win32gui.PostMessage(popup, win32con.WM_CLOSE, 0, 0)
            time.sleep(0.2)

    def _find_contacts_manager_window(self) -> Optional[int]:
        """找通讯录管理弹窗（和主窗口同进程、标题含"通讯录"的可见窗口）"""
        if self._hwnd is None:
            return None

        import win32process
        try:
            _, main_pid = win32process.GetWindowThreadProcessId(self._hwnd)
        except Exception:
            return None

        result = []

        def _enum(hwnd, _):
            if hwnd == self._hwnd:
                return True
            if not win32gui.IsWindowVisible(hwnd):
                return True
            title = win32gui.GetWindowText(hwnd)
            if "通讯录" not in title:
                return True
            try:
                _, pid = win32process.GetWindowThreadProcessId(hwnd)
            except Exception:
                return True
            if pid != main_pid:
                return True
            result.append(hwnd)
            return False

        win32gui.EnumWindows(_enum, None)
        if result:
            logger.info("找到通讯录管理窗口: 0x%X '%s'", result[0], win32gui.GetWindowText(result[0]))
            return result[0]
        return None

    @staticmethod
    def _maximize_window(hwnd: int):
        """最大化窗口（已最大化的跳过）"""
        import win32gui, win32con
        placement = win32gui.GetWindowPlacement(hwnd)
        if placement[1] == win32con.SW_SHOWMAXIMIZED:
            logger.info("窗口已最大化，跳过: 0x%X", hwnd)
            return
        win32gui.ShowWindow(hwnd, win32con.SW_MAXIMIZE)
        logger.info("窗口已最大化: 0x%X", hwnd)
