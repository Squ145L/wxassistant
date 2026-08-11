"""群发任务调度：间隔控制 + 结果收集 + 中断支持"""

import logging
import random
import threading
import time
from dataclasses import dataclass, field
from typing import Optional, Callable


logger = logging.getLogger(__name__)


@dataclass
class SendResult:
    """单条发送结果"""
    friend_name: str
    success: bool
    error: Optional[str] = None


@dataclass
class BatchResult:
    """批量发送汇总"""
    total: int = 0
    success: int = 0
    failed: int = 0
    results: list[SendResult] = field(default_factory=list)

    @property
    def failed_list(self) -> list[SendResult]:
        return [r for r in self.results if not r.success]


class SendService:
    """群发任务调度器

    职责：
    - 遍历好友列表，调用发送回调逐人发送
    - 发送间隔 = base_interval + random ±jitter_ratio
    - 支持中途终止（threading.Event）
    """

    def __init__(
        self,
        base_interval: Optional[float] = None,
        jitter_ratio: Optional[float] = None,
    ):
        # 默认值来自 设置→延迟（全局不分账户）；显式传参优先
        from src.utils.settings_store import load_delay_settings
        _d = load_delay_settings()
        self.base_interval = base_interval if base_interval is not None else _d["op_send_interval"]
        self.jitter_ratio = jitter_ratio if jitter_ratio is not None else _d["op_send_jitter"]
        self._stop_event = threading.Event()
        self._is_running = False

    # ================================================================
    # 公开接口
    # ================================================================

    @property
    def is_running(self) -> bool:
        return self._is_running

    def stop(self):
        """请求终止发送（不等待，立即返回）"""
        logger.info("收到终止请求")
        self._stop_event.set()

    def reset(self):
        """重置终止标志，准备下次发送"""
        self._stop_event.clear()
        self._is_running = False

    def send_batch(
        self,
        friends: list,  # list[FriendDTO]
        send_one: Callable,  # (FriendDTO) -> SendResult
        on_progress: Optional[Callable] = None,  # (current, total, result) -> None
    ) -> BatchResult:
        """遍历好友列表逐人发送（同步方法，调用者应放在后台线程）

        Args:
            friends: 待发送的好友列表
            send_one: 单人发送函数，接收 FriendDTO，返回 SendResult
            on_progress: 进度回调，参数为 (index, total, SendResult)

        Returns:
            BatchResult 汇总
        """
        self._is_running = True
        batch = BatchResult(total=len(friends))

        logger.info("开始群发: %d 人, 基础间隔 %.1fs ±%d%%",
                     len(friends), self.base_interval, int(self.jitter_ratio * 100))

        for i, friend in enumerate(friends):
            # --- 检查终止 ---
            if self._stop_event.is_set():
                logger.info("群发已终止: 完成 %d/%d", i, len(friends))
                break

            # --- 发送 ---
            display = getattr(friend, "display_name", str(friend))
            logger.info("[%d/%d] 发送给: %s", i + 1, len(friends), display)

            try:
                result = send_one(friend)
            except Exception as e:
                result = SendResult(friend_name=display, success=False, error=str(e))
                logger.error("[%d/%d] 发送异常: %s — %s", i + 1, len(friends), display, e)

            batch.results.append(result)
            if result.success:
                batch.success += 1
            else:
                batch.failed += 1

            # --- 进度回调 ---
            if on_progress:
                try:
                    on_progress(i + 1, len(friends), result)
                except Exception:
                    logger.exception("进度回调异常")

            # --- 间隔等待（最后一条不发间隔）---
            if i < len(friends) - 1 and not self._stop_event.is_set():
                delay = self._calc_delay()
                logger.debug("等待 %.1fs", delay)
                # 分段睡眠，便于及时响应终止
                self._interruptible_sleep(delay)

        self._is_running = False
        logger.info("群发完成: 成功 %d, 失败 %d", batch.success, batch.failed)
        return batch

    # ================================================================
    # 内部
    # ================================================================

    def _calc_delay(self) -> float:
        """计算本次间隔: base ± random(jitter)"""
        jitter = self.base_interval * self.jitter_ratio
        delay = self.base_interval + random.uniform(-jitter, jitter)
        return max(0.03, delay)  # 最短不低于 0.03 秒

    def _interruptible_sleep(self, total_seconds: float):
        """分段睡眠，每 0.1s 检查一次终止信号"""
        chunk = 0.1
        elapsed = 0.0
        while elapsed < total_seconds:
            if self._stop_event.is_set():
                return
            sleep_time = min(chunk, total_seconds - elapsed)
            time.sleep(sleep_time)
            elapsed += sleep_time
