"""Abstract base class for element processors."""

from abc import ABC, abstractmethod
from typing import Any

from common.models.document import BaseElement


class BaseElementProcessor(ABC):
    """Interface for element-level processing (table/image/formula).

    Each processor handles one element type across all source formats.
    Processors are stateless and idempotent per element_id.
    """

    element_type: str = "unknown"

    @abstractmethod
    def process(self, element: BaseElement, context: dict[str, Any] | None = None) -> BaseElement:
        """Process a single element, returning the enhanced element.

        Args:
            element: The raw element from preprocessing.
            context: Optional processing context (document metadata, config overrides, etc.).

        Returns:
            The enhanced element (same type, enriched with processed data).
        """
        ...

    @abstractmethod
    def quality_score(self, element: BaseElement) -> float:
        """Compute quality score [0, 1] for the processed element."""
        ...

    def supports(self, element: BaseElement) -> bool:
        """Check if this processor handles the given element type."""
        return element.role.value == self.element_type
