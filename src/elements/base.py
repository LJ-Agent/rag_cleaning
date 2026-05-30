"""Abstract base for element processors — Generic[T] interface with lifecycle hooks."""

from abc import ABC, abstractmethod
from typing import Any, ClassVar, Generic, TypeVar

from common.models.document import BaseElement

T = TypeVar("T", bound=BaseElement)


class BaseElementProcessor(ABC, Generic[T]):
    """Interface for element-level processing. Each processor handles one
    concrete element type (TableElement, ImageElement, CircuitDiagramElement, etc.).

    Processors are stateless and idempotent per element_id.
    """

    # ─── Class-level identity (override in subclass) ─────────
    processor_name: ClassVar[str] = "unknown"
    element_class: ClassVar[type[BaseElement] | None] = None
    priority: ClassVar[int] = 100
    enabled: ClassVar[bool] = True

    # ─── Core interface ──────────────────────────────────────

    @classmethod
    def can_process(cls, element: BaseElement) -> bool:
        """Check if this processor handles the given element.
        Default: isinstance check against element_class."""
        if cls.element_class is None:
            return False
        return isinstance(element, cls.element_class)

    @abstractmethod
    def process(self, element: T, context: dict[str, Any] | None = None) -> T:
        """Process a single element, returning the enhanced element."""
        ...

    @abstractmethod
    def quality_score(self, element: T) -> float:
        """Compute quality score [0, 1] for the processed element."""
        ...

    # ─── Lifecycle hooks (optional override) ─────────────────

    def validate(self, element: T) -> bool:
        """Check if this element can be processed. Return False to skip."""
        return True

    def pre_process(self, element: T, context: dict[str, Any] | None = None) -> T:
        """Hook called before process(). Default: no-op."""
        return element

    def post_process(self, element: T, context: dict[str, Any] | None = None) -> T:
        """Hook called after process(). Default: mark as processed."""
        if hasattr(element, 'is_processed'):
            element.is_processed = True  # type: ignore[attr-defined]
        return element

    # ─── Full processing entry point ─────────────────────────

    def execute(self, element: T, context: dict[str, Any] | None = None) -> T:
        """Full processing lifecycle: validate → pre → process → post."""
        if not self.validate(element):
            return element
        element = self.pre_process(element, context)
        element = self.process(element, context)
        element = self.post_process(element, context)
        return element
