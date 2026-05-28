"""PDF preprocessor — extract text, tables, images from PDF files."""

import io
import re
from uuid import uuid4

from common.config_loader import get_config
from common.exception.exceptions import PreprocessingException
from common.models.document import (
    BoundingBox,
    Document,
    DocumentMetadata,
    ElementRole,
    FormulaElement,
    HeadingLevel,
    ImageElement,
    Page,
    TableCell,
    TableElement,
    TextElement,
    TextRun,
)
from common.util.logger import bind_trace_id, get_logger
from common.util.utils import get_file_extension, md5_bytes
from preprocessing.base import BasePreprocessor

logger = get_logger()


class PDFPreprocessor(BasePreprocessor):
    """Extract raw elements from PDF files using pypdf + pdfplumber."""

    format_type = "pdf"
    supported_extensions = {"pdf"}
    supported_mime_types = {"application/pdf"}

    def __init__(self):
        cfg = get_config()["preprocessing"]["pdf"]
        self._extract_images = cfg.get("extract_images", True)
        self._extract_tables = cfg.get("extract_tables", True)
        self._max_pages = cfg.get("max_pages", 500)

    def extract(self, file_data: bytes, file_name: str) -> Document:
        log = bind_trace_id(str(uuid4())[:8])
        doc_id = md5_bytes(file_data)[:16]
        doc = Document(doc_id=doc_id)

        doc.metadata = DocumentMetadata(
            source_format="pdf",
            mime_type="application/pdf",
            file_size_bytes=len(file_data),
            file_md5=md5_bytes(file_data),
        )
        doc.log_stage("pdf_preprocess_start")

        # ─── Phase 1: Basic text extraction with pypdf ──────
        try:
            from pypdf import PdfReader
            reader = PdfReader(io.BytesIO(file_data))
            total_pages = min(len(reader.pages), self._max_pages)

            doc.metadata.page_count = total_pages
            if reader.metadata:
                doc.metadata.title = reader.metadata.title or ""
                doc.metadata.author = reader.metadata.author or ""
                doc.metadata.subject = reader.metadata.subject or ""
                doc.metadata.created_at = str(reader.metadata.creation_date) if reader.metadata.creation_date else ""

            # Detect if document is scanned (no extractable text on first pages)
            sample_text = ""
            for i in range(min(3, total_pages)):
                sample_text += (reader.pages[i].extract_text() or "")
            doc.metadata.is_scanned = len(sample_text.strip()) < 50

        except Exception as e:
            raise PreprocessingException(f"PDF read failed: {e}", format_type="pdf")

        # ─── Phase 2: Advanced extraction with pdfplumber ────
        try:
            import pdfplumber
            with pdfplumber.open(io.BytesIO(file_data)) as pdf:
                for i, page in enumerate(pdf.pages[:total_pages]):
                    page_obj = Page(page_number=i + 1, width=page.width or 0, height=page.height or 0)

                    # Extract text with position info
                    text = page.extract_text() or ""
                    page_obj.text_content = text
                    doc.metadata.char_count += len(text)

                    elem_idx = 0

                    # Extract tables
                    if self._extract_tables:
                        tables = page.extract_tables()
                        for table_data in tables:
                            if table_data:
                                table = self._build_table(table_data, doc_id, i + 1, elem_idx)
                                page_obj.elements.append(table)
                                elem_idx += 1
                                doc.metadata.has_tables = True

                    # Extract images
                    if self._extract_images and page.images:
                        for img_info in page.images:
                            img = self._build_image(img_info, doc_id, i + 1, elem_idx)
                            page_obj.elements.append(img)
                            elem_idx += 1
                            doc.metadata.has_images = True

                    # Build text elements from page content
                    if text.strip():
                        text_elements = self._parse_text_blocks(text, page_obj, doc_id, i + 1, elem_idx)
                        page_obj.elements.extend(text_elements)
                        elem_idx += len(text_elements)

                    doc.metadata.word_count += len(text.split())
                    doc.pages.append(page_obj)

        except Exception as e:
            raise PreprocessingException(f"PDF extraction failed: {e}", format_type="pdf")

        doc.log_stage("pdf_preprocess_done")
        return doc

    def _build_table(self, table_data: list[list[str | None]], doc_id: str, page_num: int, idx: int) -> TableElement:
        """Convert pdfplumber table data to TableElement."""
        rows = []
        for row_data in table_data:
            cells = [TableCell(text=str(cell or "").strip()) for cell in row_data]
            rows.append(cells)

        return TableElement(
            element_id=self._make_element_id(doc_id, page_num, idx, "tbl"),
            role=ElementRole.TABLE,
            page_numbers=[page_num],
            rows=rows,
            column_count=max((len(r) for r in rows), default=0),
            row_count=len(rows),
        )

    def _build_image(self, img_info: dict, doc_id: str, page_num: int, idx: int) -> ImageElement:
        """Build ImageElement from pdfplumber image info."""
        return ImageElement(
            element_id=self._make_element_id(doc_id, page_num, idx, "img"),
            role=ElementRole.IMAGE,
            page_numbers=[page_num],
            bbox=BoundingBox(
                x=img_info.get("x0", 0),
                y=img_info.get("top", 0),
                width=img_info.get("width", 0),
                height=img_info.get("height", 0),
                page_number=page_num,
            ),
            width=int(img_info.get("width", 0)),
            height=int(img_info.get("height", 0)),
            format="png",
        )

    def _parse_text_blocks(self, text: str, page: Page, doc_id: str, page_num: int, start_idx: int) -> list[TextElement]:
        """Parse extracted text into TextElement blocks."""
        elements = []
        blocks = text.split("\n\n")
        idx = start_idx

        for block in blocks:
            block = block.strip()
            if not block:
                continue

            # Detect headings (short lines, possibly numbered)
            lines = block.split("\n")
            if len(lines) == 1 and len(block) < 120:
                role = ElementRole.HEADING
                level = HeadingLevel.H2 if len(block) < 60 else HeadingLevel.H3
            else:
                role = ElementRole.PARAGRAPH
                level = None

            elem = TextElement(
                element_id=self._make_element_id(doc_id, page_num, idx, "txt"),
                role=role,
                page_numbers=[page_num],
                text=block,
                heading_level=level,
            )
            elements.append(elem)
            idx += 1

        return elements
