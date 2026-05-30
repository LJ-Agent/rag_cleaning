"""PDF preprocessor — extract text, tables, images from PDF files.
Supports OCR fallback for scanned/image-only PDFs (no text layer).
"""

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
        self._ocr_enabled = cfg.get("ocr_enabled", True)
        # OCR language and DPI from ocr preprocessor config
        ocr_cfg = get_config()["preprocessing"].get("ocr", {})
        self._ocr_lang = ocr_cfg.get("language", "chi_sim+eng")
        self._ocr_dpi = ocr_cfg.get("dpi", 300)

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

        # ─── Phase 3: OCR fallback for scanned/image-only pages ────
        if self._ocr_enabled and doc.metadata.is_scanned and doc.metadata.char_count < 50:
            log.info(
                f"Scanned PDF detected (char_count={doc.metadata.char_count}), "
                f"running OCR on {total_pages} page(s)..."
            )
            try:
                ocr_char_count = self._ocr_scanned_pages(file_data, doc, total_pages)
                if ocr_char_count > 0:
                    doc.metadata.char_count += ocr_char_count
                    doc.metadata.word_count = doc.metadata.char_count // 2
                    doc.metadata.is_scanned = True  # keep flag for downstream
                    log.info(f"OCR extracted {ocr_char_count} chars from scanned PDF")
            except Exception as e:
                log.warning(f"OCR fallback failed for scanned PDF: {e}. "
                            f"Document may have empty pages.")

        doc.log_stage("pdf_preprocess_done")
        return doc

    def _ocr_scanned_pages(self, file_data: bytes, doc: Document, total_pages: int) -> int:
        """Run OCR on scanned PDF pages using pdf2image + pytesseract (or easyocr fallback).

        Renders each page as a high-resolution image, then extracts text via OCR.
        Adds the recognized text as TextElements to the corresponding page.

        Returns:
            Total number of OCR-extracted characters.
        """
        try:
            from pdf2image import convert_from_bytes
            images = convert_from_bytes(file_data, dpi=self._ocr_dpi, fmt="png")
        except ImportError:
            logger.warning("pdf2image not available for OCR. Install: pip install pdf2image + poppler-utils")
            return 0

        if not images:
            return 0

        pages_to_ocr = images[:total_pages]
        total_chars = 0

        for page_num, img in enumerate(pages_to_ocr, start=1):
            # Convert PIL image to bytes
            img_bytes = self._pil_image_to_bytes(img)

            # Run OCR on the page image
            ocr_text = self._ocr_image(img_bytes)
            if not ocr_text:
                continue

            # Find or create the page object
            page_obj = self._get_or_create_page(doc, page_num, img)
            page_obj.is_scanned = True
            page_obj.text_content = (page_obj.text_content or "") + ocr_text

            # Parse OCR text into paragraphs and add as TextElements
            paragraphs = [p.strip() for p in ocr_text.split("\n\n") if p.strip()]
            elem_idx = len(page_obj.elements)
            for p_idx, para in enumerate(paragraphs):
                page_obj.elements.append(TextElement(
                    element_id=self._make_element_id(doc.doc_id, page_num, elem_idx + p_idx, "ocr"),
                    role=ElementRole.PARAGRAPH,
                    page_numbers=[page_num],
                    text=para,
                ))

            total_chars += len(ocr_text)
            doc.metadata.has_ocr = True

        return total_chars

    def _pil_image_to_bytes(self, img) -> bytes:
        """Convert PIL Image to PNG bytes."""
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()

    def _ocr_image(self, img_data: bytes) -> str:
        """Run OCR on an image — tries Tesseract first, falls back to EasyOCR."""
        # Try Tesseract first (fast, lightweight)
        try:
            import pytesseract
            from PIL import Image
            img = Image.open(io.BytesIO(img_data))
            if img.mode != "L":
                img = img.convert("L")
            text = pytesseract.image_to_string(img, lang=self._ocr_lang)
            if text.strip():
                return text.strip()
        except Exception:
            pass

        # Fallback: EasyOCR (pure Python, no system deps)
        try:
            import easyocr
            import numpy as np
            from PIL import Image
            reader = easyocr.Reader(["ch_sim", "en"], gpu=False)
            img = Image.open(io.BytesIO(img_data))
            arr = np.array(img)
            results = reader.readtext(arr)
            text = "\n".join(r[1] for r in results)
            return text.strip()
        except ImportError:
            logger.warning("No OCR engine available (pytesseract + easyocr missing)")
            return ""
        except Exception as e:
            logger.warning(f"EasyOCR runtime error: {e}. Falling back to empty result.")
            return ""

    def _get_or_create_page(self, doc: Document, page_num: int, img) -> Page:
        """Get existing page object or create a new one for this page number."""
        # Check if page already exists
        for p in doc.pages:
            if p.page_number == page_num:
                return p

        # Create a new page
        width = getattr(img, "width", 0)
        height = getattr(img, "height", 0)
        page = Page(page_number=page_num, width=width, height=height)
        doc.pages.append(page)
        return page

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
