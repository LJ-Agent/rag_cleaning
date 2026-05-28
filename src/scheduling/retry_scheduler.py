"""Retry scheduler — exponential backoff with configurable delays."""

import time
from collections import defaultdict

from common.config_loader import get_config
from common.util.logger import get_logger

logger = get_logger()


class RetryScheduler:
    """Manages retry attempts with exponential backoff.

    Delay progression: base_delay * (multiplier ^ attempt)
    Default: 60s → 300s → 900s → 1800s (1min → 5min → 15min → 30min)
    """

    def __init__(self):
        cfg = get_config()["task"]
        self._max_retries = cfg.get("retry_max", 3)
        self._base_delay = cfg.get("retry_base_delay", 60)  # seconds
        self._multiplier = cfg.get("retry_multiplier", 5)

        # Track per-task retry state
        self._attempts: dict[str, int] = defaultdict(int)
        self._last_attempt_time: dict[str, float] = {}

    def should_retry(self, task_id: str) -> bool:
        """Check if a task should be retried."""
        return self._attempts[task_id] < self._max_retries

    def get_retry_count(self, task_id: str) -> int:
        return self._attempts[task_id]

    def calculate_delay(self, task_id: str) -> float:
        """Calculate delay in seconds for the next retry attempt."""
        attempt = self._attempts[task_id]
        delay = self._base_delay * (self._multiplier ** attempt)
        return delay

    def record_attempt(self, task_id: str):
        """Record a retry attempt for a task."""
        self._attempts[task_id] += 1
        self._last_attempt_time[task_id] = time.time()
        logger.info(f"Task {task_id}: retry {self._attempts[task_id]}/{self._max_retries}")

    def is_maxed_out(self, task_id: str) -> bool:
        """Check if task has exhausted all retries."""
        return self._attempts[task_id] >= self._max_retries

    def reset(self, task_id: str):
        """Reset retry counter for a task."""
        self._attempts.pop(task_id, None)
        self._last_attempt_time.pop(task_id, None)

    def get_stats(self) -> dict:
        return {
            "total_tracking": len(self._attempts),
            "max_retries": self._max_retries,
            "base_delay": self._base_delay,
            "multiplier": self._multiplier,
        }


_retry_scheduler: RetryScheduler | None = None


def get_retry_scheduler() -> RetryScheduler:
    global _retry_scheduler
    if _retry_scheduler is None:
        _retry_scheduler = RetryScheduler()
    return _retry_scheduler
