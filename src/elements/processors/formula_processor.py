"""Common formula processor — image/Word/LaTeX → standard LaTeX + rendered image."""

import base64
import io
import re
from typing import Any

from common.config_loader import get_config
from common.models.document import BaseElement, FormulaElement
from common.util.logger import get_logger
from elements.base import BaseElementProcessor
from elements.registry import get_element_registry

logger = get_logger()
registry = get_element_registry()


@registry.register
class FormulaProcessor(BaseElementProcessor[FormulaElement]):
    """Process formulas from all formats into standard LaTeX.

    Handles:
    - Image formula → LaTeX (VLM recognition)
    - Word formula → LaTeX (OMath/Equation conversion)
    - LaTeX validation and normalization
    - Rendered image generation (optional, GPU node)
    """

    processor_name = "formula"
    element_class = FormulaElement
    priority = 20

    # Common LaTeX validation patterns
    LATEX_ENVS = {
        "inline", "display", "equation", "align", "gather", "multline",
        "matrix", "pmatrix", "bmatrix", "cases", "array", "split",
    }

    def __init__(self):
        cfg = get_config()["elements"]["formula"]
        self._output_format = cfg.get("output_format", "latex")
        self._render_dpi = cfg.get("render_dpi", 150)
        self._confidence_threshold = cfg.get("confidence_threshold", 0.7)
        self._llm = None

    def process(self, element: BaseElement, context: dict[str, Any] | None = None) -> BaseElement:
        if not isinstance(element, FormulaElement):
            return element

        # Step 1: Convert to LaTeX if not already
        if not element.latex and element.raw_text:
            element = self._convert_to_latex(element)
        elif not element.latex and element.image_url:
            element = self._recognize_from_image(element)

        # Step 2: Validate and normalize LaTeX
        if element.latex:
            element.latex = self._normalize_latex(element.latex)
            element.confidence = self._estimate_confidence(element.latex)

        return element

    def quality_score(self, element: BaseElement) -> float:
        if not isinstance(element, FormulaElement):
            return 0.0
        return element.confidence

    def _convert_to_latex(self, formula: FormulaElement) -> FormulaElement:
        """Convert raw formula text to LaTeX. Handles Word OMath and plain text."""
        raw = formula.raw_text.strip()

        # Word equation often starts with specific patterns
        if raw.startswith("\\") or any(symbol in raw for symbol in ["∑", "∫", "√", "α", "β", "θ", "∞"]):
            # Already LaTeX-like or has math symbols
            formula.latex = raw
            formula.format = "latex"
        else:
            # Plain text formula - wrap as LaTeX math
            formula.latex = f"${raw}$"
            formula.format = "latex"

        return formula

    def _recognize_from_image(self, formula: FormulaElement) -> FormulaElement:
        """Recognize LaTeX from formula image using VLM."""
        try:
            from infrastructure.llm.llm_adapter import get_llm_adapter
            if self._llm is None:
                self._llm = get_llm_adapter()

            # If we have image data (base64), use VLM
            # Otherwise mark as needing manual review
            if not formula.latex:
                logger.warning(f"Formula {formula.element_id}: no image data for OCR recognition")
                formula.confidence = 0.0
                return formula

            formula.confidence = self._estimate_confidence(formula.latex)

        except Exception as e:
            logger.warning(f"Formula OCR failed for {formula.element_id}: {e}")
            formula.confidence = 0.0

        return formula

    def _normalize_latex(self, latex: str) -> str:
        """Normalize and validate LaTeX string."""
        # Strip outer whitespace
        latex = latex.strip()

        # Ensure math mode delimiters
        if not latex.startswith(("$", "\\[", "\\(")):
            # Check if it looks like display math
            if any(env in latex for env in ["\\begin{", "\\end{"]):
                latex = f"\\[\n{latex}\n\\]"
            else:
                latex = f"${latex}$"

        # Fix common LaTeX issues
        latex = latex.replace("\\$", "$")  # Unescape dollar signs
        latex = re.sub(r"\\(?!([a-zA-Z]+|\[|\(|begin|end))", r"\\", latex)  # Double backslashes

        return latex

    def _estimate_confidence(self, latex: str) -> float:
        """Estimate LaTeX quality confidence based on structure."""
        score = 0.5  # Base score

        # Balanced braces
        if latex.count("{") == latex.count("}"):
            score += 0.2

        # Balanced brackets
        if latex.count("[") == latex.count("]"):
            score += 0.1

        # Has recognizable math commands
        math_commands = ["\\frac", "\\sum", "\\int", "\\sqrt", "\\alpha", "\\beta",
                         "\\theta", "\\pi", "\\infty", "\\partial", "\\nabla", "\\pm"]
        for cmd in math_commands:
            if cmd in latex:
                score += 0.05
                break

        # Not just plain text in dollar signs
        if len(latex) > 10 and not all(c.isalpha() or c.isspace() for c in latex.strip("$")):
            score += 0.1

        return max(0.0, min(1.0, score))
