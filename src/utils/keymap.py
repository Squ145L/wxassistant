"""按键 keysym ↔ VK 映射（纯层，不 import win32）

中断钩子线程收到的是 VK code（int），tkinter 捕获到的是 keysym（str，如 F8/Escape/a）。
映射表供 设置对话框（存 keysym）与 中断钩子（转 VK）共用，放 utils 才符合分层。
"""
from typing import Optional

# 功能键/特殊键 → Windows 虚拟键码
_VK_SPECIAL: dict[str, int] = {
    "Escape": 0x1B, "Tab": 0x09, "space": 0x20, "Return": 0x0D,
    "BackSpace": 0x08, "Delete": 0x2E, "Insert": 0x2D,
    "Home": 0x24, "End": 0x23, "Prior": 0x21, "Next": 0x22,
    "Left": 0x25, "Up": 0x26, "Right": 0x27, "Down": 0x28,
    "F1": 0x70, "F2": 0x71, "F3": 0x72, "F4": 0x73,
    "F5": 0x74, "F6": 0x75, "F7": 0x76, "F8": 0x77,
    "F9": 0x78, "F10": 0x79, "F11": 0x7A, "F12": 0x7B,
    "F13": 0x7C, "F14": 0x7D, "F15": 0x7E, "F16": 0x7F,
    "F17": 0x80, "F18": 0x81, "F19": 0x82, "F20": 0x83,
    "F21": 0x84, "F22": 0x85, "F23": 0x86, "F24": 0x87,
}


def keysym_to_vk(keysym: Optional[str]) -> Optional[int]:
    """keysym 字符串 → VK code；字母/数字用 ord(大写)，特殊键查表。无效返回 None。"""
    if not keysym:
        return None
    key = keysym.strip()
    if len(key) == 1:
        c = key.upper()
        if c.isalnum():
            return ord(c)
        return None
    return _VK_SPECIAL.get(key)
