"""Unified Document intermediate data model — format-agnostic representation."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


# ─── Element Enums ────────────────────────────────────────


class ElementRole(str, Enum):
    """Semantic role of an element in the document structure."""

    TITLE = "title"
    HEADING = "heading"
    PARAGRAPH = "paragraph"
    LIST_ITEM = "list_item"
    TABLE = "table"
    IMAGE = "image"
    FORMULA = "formula"
    CODE_BLOCK = "code_block"
    QUOTE = "quote"
    HYPERLINK = "hyperlink"
    PAGE_BREAK = "page_break"
    FOOTER = "footer"
    HEADER = "header"
    CAPTION = "caption"
    UNKNOWN = "unknown"


class HeadingLevel(str, Enum):
    """Markdown heading levels."""

    H1 = "h1"
    H2 = "h2"
    H3 = "h3"
    H4 = "h4"
    H5 = "h5"
    H6 = "h6"


# ─── Element Models ───────────────────────────────────────


@dataclass
class BoundingBox:
    """Element position on page (normalized or pixel coords)."""

    x: float = 0.0
    y: float = 0.0
    width: float = 0.0
    height: float = 0.0
    page_number: int = 0
    unit: str = "px"  # px / normalized


@dataclass
class TextRun:
    """A styled text segment within an element."""

    text: str
    bold: bool = False
    italic: bool = False
    underline: bool = False
    strikethrough: bool = False
    font_size: float | None = None
    font_name: str | None = None
    color: str | None = None
    hyperlink: str | None = None


@dataclass
class BaseElement:
    """Abstract base for all document elements."""

    element_id: str  # UUID for dedup and caching
    role: ElementRole = ElementRole.UNKNOWN
    bbox: BoundingBox | None = None
    page_numbers: list[int] = field(default_factory=list)
    confidence: float = 1.0  # extraction confidence [0, 1]


@dataclass
class TextElement(BaseElement):
    """Textual content element."""

    text: str = ""
    runs: list[TextRun] = field(default_factory=list)
    heading_level: HeadingLevel | None = None
    list_level: int = 0
    list_marker: str = ""  # "1.", "•", "a)", etc.
    language: str = ""  # ISO 639-1


@dataclass
class TableCell:
    """A single cell in a table."""

    text: str = ""
    row_span: int = 1
    col_span: int = 1
    is_header: bool = False
    style: dict[str, Any] = field(default_factory=dict)
    elements: list[BaseElement] = field(default_factory=list)


@dataclass
class TableElement(BaseElement):
    """Table element with merged cell support."""

    rows: list[list[TableCell]] = field(default_factory=list)
    headers: list[list[TableCell]] = field(default_factory=list)  # Multi-level headers
    caption: str = ""
    column_count: int = 0
    row_count: int = 0
    has_merged_cells: bool = False
    quality_score: float = 1.0  # Table extraction quality


@dataclass
class ImageElement(BaseElement):
    """Image or graphic element."""

    image_data: bytes | None = None  # Raw image bytes
    image_url: str = ""  # MinIO URL if stored
    image_hash: str = ""  # MD5 for dedup
    width: int = 0
    height: int = 0
    format: str = ""  # png / jpeg / etc.
    alt_text: str = ""
    caption: str = ""
    description: str = ""  # VLM-generated description
    ocr_text: str = ""  # OCR extracted text
    is_processed: bool = False


@dataclass
class FormulaElement(BaseElement):
    """Mathematical formula element."""

    latex: str = ""  # Standard LaTeX representation
    image_url: str = ""  # Rendered image URL
    raw_text: str = ""  # Original text/formula before conversion
    format: str = ""  # latex / mathml / image
    confidence: float = 0.0  # Recognition confidence


@dataclass
class CodeElement(BaseElement):
    """Code block element."""

    code: str = ""
    language: str = ""  # python / java / sql / etc.
    line_numbers: bool = False


# ─── Page & Document Models ───────────────────────────────


@dataclass
class Page:
    """A single page in the document."""

    page_number: int
    elements: list[BaseElement] = field(default_factory=list)
    text_content: str = ""  # Plain text of the page
    width: float = 0.0
    height: float = 0.0
    is_scanned: bool = False  # Scanned page (needs OCR)


@dataclass
class DocumentMetadata:
    """Document-level metadata extracted during parsing."""

    title: str = ""
    author: str = ""
    subject: str = ""
    keywords: list[str] = field(default_factory=list)
    created_at: str = ""  # ISO 8601
    modified_at: str = ""
    source_format: str = ""  # pdf / docx / xlsx / pptx / md / txt
    mime_type: str = ""
    file_size_bytes: int = 0
    file_md5: str = ""
    page_count: int = 0
    word_count: int = 0
    char_count: int = 0
    language: str = ""  # ISO 639-1
    has_images: bool = False
    has_tables: bool = False
    has_formulas: bool = False
    is_encrypted: bool = False
    is_scanned: bool = False
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class QualityReport:
    """Quality evaluation report for a cleaned document."""

    overall_score: float = 0.0  # [0, 1]
    completeness: float = 0.0  # Text completeness
    purity: float = 0.0  # Content purity (noise ratio)
    structure: float = 0.0  # Structural quality
    coherence: float = 0.0  # Semantic coherence
    issues: list["QualityIssue"] = field(default_factory=list)
    passed: bool = False

    def summary(self) -> str:
        return (
            f"Quality: {self.overall_score:.2f} "
            f"(C:{self.completeness:.2f} P:{self.purity:.2f} "
            f"S:{self.structure:.2f} H:{self.coherence:.2f}) "
            f"{'PASS' if self.passed else 'FAIL'}"
        )


@dataclass
class QualityIssue:
    """A single quality issue found during validation."""

    dimension: str = ""  # completeness / purity / structure / coherence
    level: str = "WARNING"  # WARNING / ERROR
    description: str = ""
    location: str = ""  # page/paragraph reference
    suggestion: str = ""


@dataclass
class ElementStats:
    """Count statistics for different element types."""

    text_blocks: int = 0
    headings: int = 0
    tables: int = 0
    images: int = 0
    formulas: int = 0
    code_blocks: int = 0
    lists: int = 0
    quotes: int = 0
    hyperlinks: int = 0

    def total(self) -> int:
        return sum([
            self.text_blocks, self.headings, self.tables, self.images,
            self.formulas, self.code_blocks, self.lists, self.quotes, self.hyperlinks,
        ])

    def to_dict(self) -> dict[str, int]:
        return {
            "text_blocks": self.text_blocks,
            "headings": self.headings,
            "tables": self.tables,
            "images": self.images,
            "formulas": self.formulas,
            "code_blocks": self.code_blocks,
            "lists": self.lists,
            "quotes": self.quotes,
            "hyperlinks": self.hyperlinks,
        }


# ─── Main Document Model ──────────────────────────────────


@dataclass
class Document:
    """Unified intermediate document — the core data model of the cleaning pipeline.

    All format-specific preprocessors produce this unified representation.
    All downstream processing (elements, cleaning, output) consumes this.
    """

    doc_id: str = ""  # Unique document ID (from upstream system)
    metadata: DocumentMetadata = field(default_factory=DocumentMetadata)
    pages: list[Page] = field(default_factory=list)
    elements: list[BaseElement] = field(default_factory=list)  # Cross-page elements
    quality: QualityReport | None = None
    processing_log: list[str] = field(default_factory=list)  # Stage transition log

    # ─── Convenience methods ───────────────────────────────

    @property
    def page_count(self) -> int:
        return len(self.pages)

    @property
    def all_elements(self) -> list[BaseElement]:
        """Yield all page elements + cross-page elements."""
        result: list[BaseElement] = list(self.elements)
        for page in self.pages:
            result.extend(page.elements)
        return result

    def get_elements_by_role(self, role: ElementRole) -> list[BaseElement]:
        return [e for e in self.all_elements if e.role == role]

    def get_tables(self) -> list[TableElement]:
        return [e for e in self.all_elements if isinstance(e, TableElement)]

    def get_images(self) -> list[ImageElement]:
        return [e for e in self.all_elements if isinstance(e, ImageElement)]

    def get_formulas(self) -> list[FormulaElement]:
        return [e for e in self.all_elements if isinstance(e, FormulaElement)]

    def get_element_count(self) -> ElementStats:
        stats = ElementStats()
        for e in self.all_elements:
            if isinstance(e, TextElement):
                if e.role == ElementRole.HEADING:
                    stats.headings += 1
                elif e.role == ElementRole.LIST_ITEM:
                    stats.lists += 1
                elif e.role == ElementRole.QUOTE:
                    stats.quotes += 1
                elif e.role == ElementRole.HYPERLINK:
                    stats.hyperlinks += 1
                else:
                    stats.text_blocks += 1
            elif isinstance(e, TableElement):
                stats.tables += 1
            elif isinstance(e, ImageElement):
                stats.images += 1
            elif isinstance(e, FormulaElement):
                stats.formulas += 1
            elif isinstance(e, CodeElement):
                stats.code_blocks += 1
        return stats

    def log_stage(self, stage: str):
        self.processing_log.append(stage)


# ─── Task Context Models ──────────────────────────────────


@dataclass
class CleaningTask:
    """Full task context passed through the cleaning pipeline."""

    task_id: str
    document_id: str
    kb_id: int = 0
    tenant_id: str = "default"
    file_name: str = ""
    file_url: str = ""  # MinIO path to original file
    mime_type: str = ""
    file_format: str = ""  # pdf / docx / etc.
    priority: str = "normal"  # high / normal / low
    params: dict[str, Any] = field(default_factory=dict)
    created_at: str = ""

    # Filled during processing
    document: Document | None = None
    cleaned_markdown: str = ""
    metadata_json: dict[str, Any] = field(default_factory=dict)
    quality_report: QualityReport | None = None
    output_paths: dict[str, str] = field(default_factory=dict)  # {markdown: path, metadata: path}


# ─── Kafka Message Models ─────────────────────────────────


@dataclass
class KafkaTaskMessage:
    """Standard Kafka task message (aligned with Java KafkaMessage format)."""

    task_id: str
    task_type: str
    document_id: str
    kb_id: int = 0
    tenant_id: str = "default"
    data: dict[str, Any] = field(default_factory=dict)
    created_at: str = ""

    @staticmethod
    def from_json(data: dict) -> "KafkaTaskMessage":
        return KafkaTaskMessage(
            task_id=str(data.get("taskId", data.get("task_id", ""))),
            task_type=str(data.get("taskType", data.get("task_type", ""))),
            document_id=str(data.get("documentId", data.get("document_id", ""))),
            kb_id=int(data.get("kbId", data.get("kb_id", 0))),
            tenant_id=str(data.get("tenantId", data.get("tenant_id", "default"))),
            data=data.get("data", {}),
            created_at=str(data.get("createdAt", data.get("created_at", ""))),
        )

    def to_json(self) -> dict:
        return {
            "taskId": self.task_id,
            "taskType": self.task_type,
            "documentId": self.document_id,
            "kbId": self.kb_id,
            "tenantId": self.tenant_id,
            "data": self.data,
            "createdAt": self.created_at,
        }


@dataclass
class CleaningEvent:
    """Event emitted after cleaning completion, consumed by downstream services."""

    task_id: str
    document_id: str
    kb_id: int
    tenant_id: str
    status: str  # SUCCESS / FAILED
    markdown_path: str = ""  # MinIO path
    metadata_path: str = ""
    quality_score: float = 0.0
    processing_time_ms: int = 0
    element_stats: dict[str, int] = field(default_factory=dict)
    error_message: str = ""
    created_at: str = ""

    def to_json(self) -> dict:
        return {
            "taskId": self.task_id,
            "documentId": self.document_id,
            "kbId": self.kb_id,
            "tenantId": self.tenant_id,
            "status": self.status,
            "markdownPath": self.markdown_path,
            "metadataPath": self.metadata_path,
            "qualityScore": self.quality_score,
            "processingTimeMs": self.processing_time_ms,
            "elementStats": self.element_stats,
            "errorMessage": self.error_message,
            "createdAt": self.created_at,
        }
