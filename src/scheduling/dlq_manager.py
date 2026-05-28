"""Dead letter queue (DLQ) manager — handles tasks that exceeded max retries."""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from common.config_loader import get_config
from common.constant.kafka_constants import CleaningTopics
from common.util.logger import get_logger

logger = get_logger()


class DLQManager:
    """Manage dead-letter-queued tasks.

    When a task exceeds max retries:
    1. Task is sent to rag-cleaning-dlq topic
    2. Error details are persisted to local JSON log
    3. Dashboard/Admin API can list, inspect, and re-submit DLQ tasks
    """

    def __init__(self, dlq_path: str | None = None):
        if dlq_path is None:
            from pathlib import Path as P
            root = P(__file__).parent.parent.parent  # project root
            dlq_path = str(root / "logs" / "dlq.jsonl")
        self._dlq_path = Path(dlq_path)
        self._dlq_path.parent.mkdir(parents=True, exist_ok=True)
        self._tasks: dict[str, dict] = {}

    def enqueue(self, task_id: str, task_data: dict[str, Any], error: str):
        """Add a task to the dead letter queue."""
        entry = {
            "task_id": task_id,
            "task_data": task_data,
            "error": error,
            "enqueued_at": datetime.now(timezone.utc).isoformat(),
            "status": "PENDING_REVIEW",
        }
        self._tasks[task_id] = entry
        self._persist(entry)
        logger.warning(f"Task {task_id} enqueued to DLQ: {error}")

    def list_tasks(self, status: str | None = None) -> list[dict]:
        """List DLQ tasks, optionally filtered by status."""
        tasks = list(self._tasks.values())
        if status:
            tasks = [t for t in tasks if t["status"] == status]
        return sorted(tasks, key=lambda t: t["enqueued_at"], reverse=True)

    def get_task(self, task_id: str) -> dict | None:
        """Get details of a specific DLQ task."""
        return self._tasks.get(task_id)

    def re_submit(self, task_id: str) -> dict | None:
        """Mark a DLQ task for re-submission. Returns task data to re-send."""
        entry = self._tasks.get(task_id)
        if not entry:
            return None
        entry["status"] = "RE_SUBMITTED"
        entry["resubmitted_at"] = datetime.now(timezone.utc).isoformat()
        logger.info(f"Task {task_id} re-submitted from DLQ")
        return entry["task_data"]

    def delete(self, task_id: str) -> bool:
        """Remove a task from the DLQ."""
        if task_id in self._tasks:
            self._tasks[task_id]["status"] = "DELETED"
            self._tasks[task_id]["deleted_at"] = datetime.now(timezone.utc).isoformat()
            return True
        return False

    def get_stats(self) -> dict:
        total = len(self._tasks)
        pending = sum(1 for t in self._tasks.values() if t["status"] == "PENDING_REVIEW")
        return {"total": total, "pending_review": pending}

    def _persist(self, entry: dict):
        """Append entry to DLQ log file."""
        try:
            with open(self._dlq_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception as e:
            logger.error(f"Failed to persist DLQ entry: {e}")


_dlq_manager: DLQManager | None = None


def get_dlq_manager() -> DLQManager:
    global _dlq_manager
    if _dlq_manager is None:
        _dlq_manager = DLQManager()
    return _dlq_manager
