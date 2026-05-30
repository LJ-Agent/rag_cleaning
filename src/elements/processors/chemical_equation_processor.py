"""Chemical equation processor — recognize equations, convert to SMILES/LaTeX."""

from typing import Any

from common.config_loader import get_config
from common.models.document import ChemicalEquationElement
from common.util.logger import get_logger
from elements.base import BaseElementProcessor
from elements.registry import get_element_registry

logger = get_logger()
registry = get_element_registry()


@registry.register
class ChemicalEquationProcessor(BaseElementProcessor[ChemicalEquationElement]):
    """Process chemical equations: recognize, convert to SMILES/LaTeX."""

    processor_name = "chemical_equation"
    element_class = ChemicalEquationElement
    priority = 26

    def __init__(self):
        cfg = get_config()["elements"].get("chemical_equation", {})
        self._confidence_threshold = cfg.get("confidence_threshold", 0.7)
        self._generate_description = cfg.get("generate_description", True)

    def process(self, element: ChemicalEquationElement, context: dict[str, Any] | None = None) -> ChemicalEquationElement:
        if hasattr(element, 'is_processed') and element.is_processed:
            return element

        # Convert raw text to LaTeX if possible
        if element.raw_text and not element.latex:
            element = self._text_to_latex(element)

        # Use VLM for image-based equations
        if self._generate_description and element.image_data and not element.description:
            element = self._describe(element, context)

        return element

    def quality_score(self, element: ChemicalEquationElement) -> float:
        score = element.confidence or 0.5
        if element.latex: score += 0.2
        if element.smiles: score += 0.1
        if element.description: score += 0.1
        return min(1.0, score)

    def _text_to_latex(self, element: ChemicalEquationElement) -> ChemicalEquationElement:
        """Convert raw chemical text to LaTeX."""
        import re
        raw = element.raw_text.strip()
        # Detect common patterns: H2O, C6H12O6, 2H2+O2→2H2O
        if re.match(r'^[\dA-Za-z\s\+\→\→\=\(\)\[\]\-\>\.]+$', raw):
            # Already a chemical formula, wrap in LaTeX
            element.latex = r"\ce{" + raw.replace("→", "->").replace("＝", "=") + "}"
            element.confidence = max(element.confidence, 0.7)
        else:
            element.latex = raw  # Keep as-is
        return element

    def _describe(self, element: ChemicalEquationElement, context: dict | None) -> ChemicalEquationElement:
        """Use VLM to describe chemical equation image."""
        try:
            from infrastructure.llm.llm_adapter import LLMAdapter
            llm = LLMAdapter()
            prompt = (
                "Describe this chemical equation or reaction diagram. "
                "Provide the chemical equation in text form, explain the reaction type, "
                "and note any catalysts or special conditions. Output in Chinese."
            )
            description = llm.describe_image(element.image_data, prompt)
            if description:
                element.description = description
        except Exception as e:
            logger.warning(f"Chemical equation description failed: {e}")
        return element
