"""Circuit diagram processor — identify components, generate description."""

from typing import Any

from common.config_loader import get_config
from common.models.document import CircuitDiagramElement
from common.util.logger import get_logger
from elements.base import BaseElementProcessor
from elements.registry import get_element_registry

logger = get_logger()
registry = get_element_registry()


@registry.register
class CircuitDiagramProcessor(BaseElementProcessor[CircuitDiagramElement]):
    """Process circuit diagrams: describe, identify components."""

    processor_name = "circuit_diagram"
    element_class = CircuitDiagramElement
    priority = 25

    def __init__(self):
        cfg = get_config()["elements"].get("circuit_diagram", {})
        self._max_width = cfg.get("max_width", 2048)
        self._max_height = cfg.get("max_height", 2048)
        self._generate_description = cfg.get("generate_description", True)

    def process(self, element: CircuitDiagramElement, context: dict[str, Any] | None = None) -> CircuitDiagramElement:
        # Already processed via cache
        if hasattr(element, 'is_processed') and element.is_processed:
            return element

        # Generate VLM description if image available
        if self._generate_description and element.image_data and not element.description:
            element = self._describe(element, context)

        return element

    def quality_score(self, element: CircuitDiagramElement) -> float:
        score = 0.5
        if element.description: score += 0.3
        if element.components: score += 0.2
        return min(1.0, score)

    def _describe(self, element: CircuitDiagramElement, context: dict | None) -> CircuitDiagramElement:
        """Use VLM to describe circuit diagram."""
        try:
            from infrastructure.llm.llm_adapter import LLMAdapter
            llm = LLMAdapter()
            prompt = (
                "Describe this circuit diagram in detail. "
                "Identify components (resistors, capacitors, transistors, ICs, etc.), "
                "their connections, and the circuit's function. "
                "Output in Chinese."
            )
            description = llm.describe_image(element.image_data, prompt)
            if description:
                element.description = description
                # Extract component references from description
                element.components = self._extract_components(description)
        except Exception as e:
            logger.warning(f"Circuit diagram description failed: {e}")
        return element

    def _extract_components(self, description: str) -> list[str]:
        """Extract component references from description text."""
        import re
        # Match patterns like R1, C2, Q1, U1, L1, D1
        matches = re.findall(r'\b([RrCcQqUuLlDd]\d+)\b', description)
        return list(dict.fromkeys(matches))[:20]  # Dedup, max 20
