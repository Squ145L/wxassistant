"""日志配置：文件轮转 + 控制台 + UI 钩子"""

import logging
import sys
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from typing import Optional, Callable

from src.utils.config import LOG_DIR, LOG_FILE, LOG_MAX_DAYS, LOG_FORMAT, LOG_DATE_FORMAT

_ui_callback: Optional[Callable[[str], None]] = None
"""UI 钩子：可选，由 ui/send_progress.py 注入，将日志同步到界面"""


def set_ui_callback(callback: Optional[Callable[[str], None]]):
    """注入 UI 回调函数，用于将日志推送到界面文本框"""
    global _ui_callback
    _ui_callback = callback


class _UIHandler(logging.Handler):
    """将日志转发到 UI 回调"""

    def emit(self, record: logging.LogRecord):
        if _ui_callback is not None:
            try:
                msg = self.format(record)
                _ui_callback(msg)
            except Exception:
                pass  # UI 回调出错不应影响程序


def setup_logging(level: int = logging.DEBUG):
    """初始化全局日志配置，只需在 main.py 启动时调用一次"""
    # 确保目录存在
    Path(LOG_DIR).mkdir(parents=True, exist_ok=True)

    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # 清除已有的 handler（防止重复添加）
    root_logger.handlers.clear()

    formatter = logging.Formatter(fmt=LOG_FORMAT, datefmt=LOG_DATE_FORMAT)

    # 文件 handler：按天轮转，保留 7 天
    file_handler = TimedRotatingFileHandler(
        filename=LOG_FILE,
        when="midnight",
        interval=1,
        backupCount=LOG_MAX_DAYS,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)

    # 控制台 handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # UI handler（默认无回调，等 UI 注入）
    ui_handler = _UIHandler()
    ui_handler.setLevel(logging.INFO)
    ui_handler.setFormatter(formatter)
    root_logger.addHandler(ui_handler)

    # 抑制第三方库的 DEBUG 日志
    logging.getLogger("PIL").setLevel(logging.WARNING)
    logging.getLogger("rapidocr").setLevel(logging.WARNING)

    logging.getLogger(__name__).info("日志系统初始化完成")


def set_file_logging(enabled: bool) -> None:
    """开关文件日志（不删已有日志，只停/启 handler）"""
    root = logging.getLogger()
    for h in list(root.handlers):
        if isinstance(h, TimedRotatingFileHandler):
            if enabled:
                root.addHandler(h)  # 恢复（若已被移除则加回）
            else:
                root.removeHandler(h)  # 暂停写文件
            return
    # 之前没有 file handler，现在需要加
    if enabled:
        _add_file_handler(root)


def _add_file_handler(root: logging.Logger) -> None:
    Path(LOG_DIR).mkdir(parents=True, exist_ok=True)
    formatter = logging.Formatter(fmt=LOG_FORMAT, datefmt=LOG_DATE_FORMAT)
    fh = TimedRotatingFileHandler(
        filename=LOG_FILE, when="midnight", interval=1,
        backupCount=LOG_MAX_DAYS, encoding="utf-8",
    )
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(formatter)
    root.addHandler(fh)


def clear_logs() -> None:
    """清空所有日志文件"""
    import glob as _glob
    log_path = Path(LOG_FILE)
    # 主日志 + 轮转日志
    for p in _glob.glob(str(log_path.parent / f"{log_path.stem}*")):
        try:
            open(p, "w").close()  # 清空内容但不删文件（避免 handler 报错）
        except OSError:
            pass


def is_file_logging_enabled() -> bool:
    """检查文件日志是否启用"""
    root = logging.getLogger()
    return any(isinstance(h, TimedRotatingFileHandler) for h in root.handlers)


def get_logger(name: str) -> logging.Logger:
    """获取模块级 logger"""
    return logging.getLogger(name)
