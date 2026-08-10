"""全局常量配置"""

# ========== 微信窗口 ==========
WEIXIN_WINDOW_TITLES = ["Weixin", "微信"]
WEIXIN_PROCESS_NAME = "Weixin.exe"

# ========== 时序 (秒) ==========
# 搜索本身已经有充足延迟（激活+Ctrl+F+粘贴+Enter ≈ 3s），
# send_service 间隔只需极小的呼吸时间
DEFAULT_SEND_INTERVAL = 0.1        # 两条消息之间的基础间隔（搜索内部已有延迟）
INTERVAL_JITTER_RATIO = 0.3       # ±30% 随机抖动
KEY_PRESS_DELAY = 0.02            # 组合键各事件间隔
CLIPBOARD_DELAY = 0.05            # 剪贴板操作后等待
ACTIVATE_DELAY = 0.2              # 窗口激活后等待
SEARCH_DELAY = 0.1                # Ctrl+F 搜索后等待结果出现
FILE_SEND_DELAY = 0.1             # 文件发送后等待

# ========== OCR ==========
OCR_CONFIDENCE_THRESHOLD = 0.7    # 低于此值视为不可靠
OCR_CACHE_TTL = 30                # 同搜索词缓存秒数

# ========== 缓存 ==========
FRIENDS_CACHE_PATH = "cache/friends.json"

# ========== 日志 ==========
LOG_DIR = "logs"
LOG_FILE = "logs/app.log"
LOG_MAX_DAYS = 7
LOG_FORMAT = "%(asctime)s [%(levelname)-5s] %(name)s: %(message)s"
LOG_DATE_FORMAT = "%m-%d %H:%M:%S"

# ========== UI 尺寸 ==========
WINDOW_WIDTH = 1100
WINDOW_HEIGHT = 720
WINDOW_TITLE = "微信助手 - 群发工具"
LEFT_PANEL_WIDTH = 450

# ========== 限制 ==========
MAX_ATTACHMENT_MB = 100
MAX_ATTACHMENT_COUNT = 5
