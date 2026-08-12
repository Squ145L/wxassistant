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

from src.utils.calibration import load_calibration
from src.utils.config import WEIXIN_WINDOW_TITLES
from src.utils.coordinates import get_coord, resolve_calibration_rect

logger = logging.getLogger(__name__)

# OCR 混淆字符映射配置（在 OCR 引擎中也会加载）
OCR_CONFUSION_PATH = Path("OCR/ocr_confusion.json")


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
        self._pause_check = None   # 暂停检查：暂停时阻塞等待恢复/终止（防暂停后继续发按键）
        self._hook_suspend = None
        self._hook_resume = None
        self._excluded_hwnds: set[int] = set()
        self._account_name: Optional[str] = None
        # 操作间延迟（设置→延迟，全局不分账户；构造时读一次快照）
        from src.utils.settings_store import load_delay_settings
        _d = load_delay_settings()
        self._activate_delay = _d["op_activate_delay"]
        self._search_delay = _d["op_search_delay"]
        self._clipboard_delay = _d["op_clipboard_delay"]
        self._paste_delay = _d["op_paste_delay"]
        self._send_after_delay = _d["op_send_after_delay"]
        self._file_send_delay = _d["op_file_send_delay"]
        self._key_press_delay = _d["op_key_press_delay"]

    def set_stop_check(self, checker):
        self._stop_check = checker

    def set_pause_check(self, checker):
        """注入暂停检查（阻塞式）：暂停时不在发送任何模拟按键，恢复/终止后继续"""
        self._pause_check = checker

    def set_hook_control(self, suspend_fn, resume_fn):
        """注入钩子开关：SendKeys 前暂停钩子，之后恢复"""
        self._hook_suspend = suspend_fn
        self._hook_resume = resume_fn

    def set_excluded_windows(self, hwnds):
        """多账户：排除其他账户的主窗口，防止弹窗检测误关它们"""
        self._excluded_hwnds = set(hwnds)

    def set_account_name(self, name: Optional[str]):
        """设置当前账户名（多账户：坐标/OCR 校准按账户读取）"""
        self._account_name = name

    @property
    def account_name(self) -> Optional[str]:
        return self._account_name

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

            time.sleep(self._activate_delay)
            logger.info("窗口已激活: 0x%X", hwnd)
            return True

        except Exception:
            logger.exception("窗口激活失败")
            return False
        finally:
            if self._hook_resume: self._hook_resume()

    def activate_hwnd(self, hwnd: int, retries: int = 3) -> bool:
        """激活任意微信窗口（多开引导用），校验前台激活成功

        Windows 前台锁定可能拒绝 SetForegroundWindow；只有确认
        GetForegroundWindow 已是目标窗口才返回 True，避免确认错账户。
        """
        try:
            if win32gui.IsIconic(hwnd):
                win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
                time.sleep(0.2)
            for _ in range(retries):
                if self._hook_suspend:
                    self._hook_suspend()
                try:
                    win32gui.SetWindowPos(hwnd, win32con.HWND_TOPMOST, 0, 0, 0, 0,
                                          win32con.SWP_NOMOVE | win32con.SWP_NOSIZE)
                    win32gui.SetWindowPos(hwnd, win32con.HWND_NOTOPMOST, 0, 0, 0, 0,
                                          win32con.SWP_NOMOVE | win32con.SWP_NOSIZE)
                    win32api.keybd_event(win32con.VK_MENU, 0, 0, 0)
                    win32gui.SetForegroundWindow(hwnd)
                    win32api.keybd_event(win32con.VK_MENU, 0, win32con.KEYEVENTF_KEYUP, 0)
                    time.sleep(0.15)
                    if win32gui.GetForegroundWindow() == hwnd:
                        return True
                finally:
                    if self._hook_resume:
                        self._hook_resume()
            logger.warning("窗口激活失败（可能被前台锁定）: 0x%X", hwnd)
            return False
        except Exception:
            logger.exception("激活窗口失败: 0x%X", hwnd)
            return False

    # ================================================================
    # 键盘模拟 — UIA SendKeys（线程安全，每次创建 UIA 控件）
    # ================================================================

    def _send_keys(self, keys: str):
        """UIA SendKeys — 暂停钩子防止模拟按键触发中断"""
        if self._should_stop():
            logger.info("SendKeys 已中断，跳过: %s", keys)
            return
        # 暂停时阻塞：暂停后不再发送按键，恢复/终止后继续
        if self._pause_check:
            self._pause_check()
        if self._should_stop():
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
        time.sleep(self._clipboard_delay)
        self._send_keys('{Ctrl}v')
        time.sleep(self._paste_delay)          # 粘贴后稍等
        self._send_keys('{Enter}')
        time.sleep(self._send_after_delay)     # 发送后稍等

    # ================================================================
    # 鼠标模拟
    # ================================================================

    def click_at(self, x: int, y: int):
        """鼠标左键单击（暂停钩子防自触发）"""
        if self._pause_check:
            self._pause_check()
        if self._should_stop():
            return
        if self._hook_suspend: self._hook_suspend()
        logger.info("click_at: (%d, %d)", x, y)
        win32api.SetCursorPos((x, y))
        time.sleep(self._key_press_delay)
        win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
        time.sleep(self._key_press_delay)
        win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
        if self._hook_resume: self._hook_resume()

    def scroll_at(self, x: int, y: int, delta: int):
        """鼠标滚轮（暂停钩子防自触发）"""
        if self._pause_check:
            self._pause_check()
        if self._should_stop():
            return
        if self._hook_suspend: self._hook_suspend()
        try:
            win32api.SetCursorPos((x, y))
            time.sleep(self._key_press_delay)
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

        # 校准参数：账户专属覆盖全局，再回退默认值
        calib = load_calibration("chat_title", self._account_name)
        result = resolve_calibration_rect(calib, rect)
        logger.debug("聊天标题区域: (%d,%d)-(%d,%d)", *result)
        return result

    def capture_chat_title(self) -> Optional[Image.Image]:
        """前台：截图聊天标题区域（截图需要窗口在前台，供后台 OCR 使用）"""
        rect = self._get_chat_title_rect()
        if rect is None:
            logger.warning("无法获取聊天标题区域")
            return None
        return self.screenshot_region(*rect)

    def ocr_and_match(self, expected_name: str, img: Image.Image):
        """后台：OCR 识别截图 → 归一化 → 匹配（纯计算，不碰窗口，可跨账户并行）

        Returns: (matched: bool, ocr_name: str)
        """
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

    def match_chat_title(self, expected_name: str):
        """截图聊天标题 → OCR → 从首字符开始匹配（单账户同步路径）

        规则：
        1. OCR 结果和 expected_name 从第一个字开始比较
        2. 只要短的是长的前缀就算匹配
          例: expected="25级李"  ocr="25级李华"  → 匹配
          例: expected="25级李华" ocr="25级李"   → 匹配
        3. 返回 OCR 到的实际名称（可能比 expected 长）

        Returns: (matched: bool, ocr_name: str)
        """
        img = self.capture_chat_title()
        if img is None:
            return (False, "")
        return self.ocr_and_match(expected_name, img)

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
        time.sleep(self._key_press_delay)
        if self._should_stop(): return False
        self._send_keys('{Ctrl}a')
        time.sleep(self._key_press_delay)
        self._paste_and_enter(keyword)
        time.sleep(self._search_delay)
        if self._should_stop(): return False

        if self._close_search_popup():
            logger.info("搜索弹窗已关闭，联系人不存在: '%s'", keyword)
            return False
        return True

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
            # 多账户：跳过其他已锁定账户的主窗口，防止把"微信"标题误判成搜一搜弹窗
            if hwnd in self._excluded_hwnds:
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
        time.sleep(self._file_send_delay)
        self._send_keys('{Ctrl}v')
        time.sleep(self._file_send_delay)
        self._send_keys('{Enter}')
        time.sleep(self._file_send_delay)

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
        safe_x_pct, safe_y_pct = get_coord("safe_zone", self._account_name)
        safe_x = rect[0] + int(ww * safe_x_pct)
        safe_y = rect[1] + int(wh * safe_y_pct)
        self.click_at(safe_x, safe_y)
        time.sleep(0.15)
        # 再点通讯录标签
        cx_pct, cy_pct = get_coord("tab_contacts", self._account_name)
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
        cx_pct, cy_pct = get_coord("btn_contacts_mgr", self._account_name)
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
