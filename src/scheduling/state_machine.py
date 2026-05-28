"""Task state machine — manages CleaningTaskStatus transitions."""

from datetime import datetime, timezone

from common.enums.status_enums import CleaningStage, CleaningTaskStatus
from common.util.logger import get_logger

logger = get_logger()


class TaskStateMachine:
    """Manages the lifecycle of a cleaning task through its state transitions."""

    def __init__(self, task_id: str):
        self.task_id = task_id
        self._current: CleaningTaskStatus = CleaningTaskStatus.PENDING
        self._history: list[tuple[CleaningTaskStatus, str]] = []  # (status, timestamp)
        self._stage: CleaningStage | None = None
        self._progress: int = 0  # 0-100
        self._error: str | None = None

    @property
    def current(self) -> CleaningTaskStatus:
        return self._current

    @property
    def stage(self) -> CleaningStage | None:
        return self._stage

    @property
    def progress(self) -> int:
        return self._progress

    @property
    def error(self) -> str | None:
        return self._error

    @property
    def history(self) -> list[dict]:
        return [{"status": s.value, "timestamp": ts} for s, ts in self._history]

    def transition(self, target: CleaningTaskStatus, error: str | None = None) -> bool:
        """Attempt to transition to target state. Returns True if valid."""
        if not self._current.can_transit_to(target):
            logger.warning(
                f"Task {self.task_id}: invalid transition {self._current.value} -> {target.value}"
            )
            return False

        old = self._current
        self._current = target
        self._history.append((target, datetime.now(timezone.utc).isoformat()))

        if target == CleaningTaskStatus.FAILED:
            self._error = error

        logger.info(f"Task {self.task_id}: {old.value} -> {target.value}")
        return True

    def set_stage(self, stage: CleaningStage, progress: int = 0):
        """Update current processing stage and progress."""
        self._stage = stage
        self._progress = progress

    def mark_failed(self, error: str) -> bool:
        """Mark task as failed with error message."""
        self._error = error
        return self.transition(CleaningTaskStatus.FAILED, error=error)

    def mark_retrying(self, attempt: int, max_attempts: int) -> bool:
        """Mark task for retry."""
        logger.info(f"Task {self.task_id}: retrying (attempt {attempt}/{max_attempts})")
        self._progress = 0
        return self.transition(CleaningTaskStatus.RETRYING)

    def is_terminal(self) -> bool:
        return self._current.is_terminal()

    def is_retryable(self) -> bool:
        return self._current.is_retryable()

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "status": self._current.value,
            "stage": self._stage.value if self._stage else None,
            "progress": self._progress,
            "error": self._error,
            "history": self.history,
        }


class TaskStateMachineFactory:
    """Factory for creating and caching state machines."""

    def __init__(self):
        self._machines: dict[str, TaskStateMachine] = {}

    def create(self, task_id: str) -> TaskStateMachine:
        if task_id in self._machines:
            logger.warning(f"Task {task_id}: state machine already exists, returning existing")
            return self._machines[task_id]
        machine = TaskStateMachine(task_id)
        self._machines[task_id] = machine
        return machine

    def get(self, task_id: str) -> TaskStateMachine | None:
        return self._machines.get(task_id)

    def remove(self, task_id: str):
        self._machines.pop(task_id, None)

    def active_count(self) -> int:
        return sum(1 for m in self._machines.values() if not m.is_terminal())


_state_machine_factory: TaskStateMachineFactory | None = None


def get_state_machine_factory() -> TaskStateMachineFactory:
    global _state_machine_factory
    if _state_machine_factory is None:
        _state_machine_factory = TaskStateMachineFactory()
    return _state_machine_factory
