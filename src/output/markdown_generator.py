"""Markdown generator — converts Document intermediate object to standard Markdown."""

from common.models.document import (
    CodeElement,
    Document,
    ElementRole,
    FormulaElement,
    HeadingLevel,
    ImageElement,
    TableElement,
    TextElement,
)
from common.util.logger import get_logger
from elements.table_processor import TableProcessor

logger = get_logger()


class MarkdownGenerator:
    """Generate standard Markdown from a unified Document object.

    Preserves element order within each page and handles:
    - Headings at correct levels
    - Tables as Markdown tables
    - Images as Markdown image syntax (with description as alt text)
    - Formulas as LaTeX blocks
    - Code blocks with language markers
    - Lists and quotes
    """

    HEADING_MARKERS = {
        HeadingLevel.H1: "#",
        HeadingLevel.H2: "##",
        HeadingLevel.H3: "###",
        HeadingLevel.H4: "####",
        HeadingLevel.H5: "#####",
        HeadingLevel.H6: "######",
    }

    def __init__(self):
        self._table_processor = TableProcessor()

    def generate(self, doc: Document) -> str:
        """Convert entire document to Markdown string."""
        doc.log_stage("markdown_generation_start")
        lines: list[str] = []

        # Document title
        if doc.metadata.title:
            lines.append(f"# {doc.metadata.title}")
            lines.append("")

        for page in doc.pages:
            if doc.page_count > 1:
                lines.append(f"<!-- Page {page.page_number} -->")
                lines.append("")

            for element in page.elements:
                md = self._element_to_markdown(element)
                if md:
                    lines.append(md)
                    lines.append("")

        result = "\n".join(lines).strip()
        doc.log_stage("markdown_generation_done")
        return result

    def _element_to_markdown(self, element) -> str:
        """Convert a single element to its Markdown representation."""
        if isinstance(element, TextElement):
            return self._text_to_markdown(element)
        elif isinstance(element, TableElement):
            return self._table_to_markdown(element)
        elif isinstance(element, ImageElement):
            return self._image_to_markdown(element)
        elif isinstance(element, FormulaElement):
            return self._formula_to_markdown(element)
        elif isinstance(element, CodeElement):
            return self._code_to_markdown(element)
        elif type(element).__name__ == "CircuitDiagramElement":
            return self._circuit_to_markdown(element)
        elif type(element).__name__ == "ChemicalEquationElement":
            return self._equation_to_markdown(element)
        elif type(element).__name__ == "AudioElement":
            return self._audio_to_markdown(element)
        elif type(element).__name__ == "VideoElement":
            return self._video_to_markdown(element)
        return ""

    def _text_to_markdown(self, elem: TextElement) -> str:
        text = elem.text.strip()
        if not text:
            return ""

        if elem.role == ElementRole.HEADING and elem.heading_level:
            marker = self.HEADING_MARKERS.get(elem.heading_level, "")
            return f"{marker} {text}"

        elif elem.role == ElementRole.LIST_ITEM:
            marker = elem.list_marker or "-"
            indent = "  " * elem.list_level
            return f"{indent}{marker} {text}"

        elif elem.role == ElementRole.QUOTE:
            return "\n".join(f"> {line}" for line in text.split("\n"))

        elif elem.role == ElementRole.CAPTION:
            return f"*{text}*"

        else:
            return text

    def _table_to_markdown(self, elem: TableElement) -> str:
        return self._table_processor.to_markdown(elem)

    def _image_to_markdown(self, elem: ImageElement) -> str:
        alt = elem.description or elem.alt_text or elem.caption or "image"
        url = elem.image_url or f"[image:{elem.element_id}]"
        result = f"![{alt}]({url})"
        if elem.caption:
            result += f"\n*{elem.caption}*"
        if elem.ocr_text:
            result += f"\n> [OCR] {elem.ocr_text[:300]}"
        return result

    def _formula_to_markdown(self, elem: FormulaElement) -> str:
        latex = elem.latex.strip()
        if not latex:
            return ""

        # Display math (block)
        if latex.startswith("\\[") or "\\begin{" in latex:
            return f"\n{latex}\n"
        # Inline math
        elif latex.startswith("$"):
            return latex
        else:
            return f"$$\n{latex}\n$$"

    def _code_to_markdown(self, elem: CodeElement) -> str:
        lang = elem.language or ""
        code = elem.code.strip()
        return f"```{lang}\n{code}\n```"

    def _circuit_to_markdown(self, elem) -> str:
        lines = []
        if elem.description:
            lines.append(f"> **电路描述**: {elem.description}")
        if elem.components:
            comps = ", ".join(elem.components[:10])
            lines.append(f"> **组件**: {comps}")
        return "\n".join(lines) if lines else ""

    def _equation_to_markdown(self, elem) -> str:
        lines = []
        if elem.latex:
            lines.append(f"$$\n{elem.latex}\n$$")
        if elem.smiles:
            lines.append(f"> SMILES: `{elem.smiles}`")
        if elem.description:
            lines.append(f"> {elem.description}")
        return "\n".join(lines) if lines else ""

    def _audio_to_markdown(self, elem) -> str:
        parts = []
        if elem.transcript:
            parts.append(f"> **转录**: {elem.transcript[:200]}")
        if elem.duration_seconds:
            parts.append(f"> 时长: {elem.duration_seconds:.0f}s")
        return "\n".join(parts) if parts else ""

    def _video_to_markdown(self, elem) -> str:
        parts = []
        if elem.description:
            parts.append(f"> **描述**: {elem.description}")
        if elem.transcript:
            parts.append(f"> **转录**: {elem.transcript[:200]}")
        if elem.duration_seconds:
            parts.append(f"> 时长: {elem.duration_seconds:.0f}s")
        return "\n".join(parts) if parts else ""
