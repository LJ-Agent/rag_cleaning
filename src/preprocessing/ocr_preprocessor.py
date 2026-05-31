"""OCR preprocessor — extract text from scanned PDF / image files via Tesseract OCR."""

import io
from uuid import uuid4

from common.models.document import (
    Document,
    DocumentMetadata,
    ElementRole,
    Page,
    TextElement,
)
from common.util.logger import bind_trace_id, get_logger
from common.util.utils import get_file_extension, md5_bytes
from preprocessing.base import BasePreprocessor

logger = get_logger()


class OCRPreprocessor(BasePreprocessor):
    """Extract text from image-based files using Tesseract OCR.

    Supports scanned PDF (each page rendered as image → OCR) and
    direct image formats (PNG, JPG, BMP, TIFF).
    """

    format_type = "ocr"
    supported_extensions = {"png", "jpg", "jpeg", "bmp", "tiff", "tif"}
    supported_mime_types = {"image/png", "image/jpeg", "image/bmp", "image/tiff"}

    def __init__(self):
        self._lang = "chi_sim+eng"  # Chinese simplified + English
        self._dpi = 300

    def extract(self, file_data: bytes, file_name: str) -> Document:
        log = bind_trace_id(str(uuid4())[:8])
        doc_id = md5_bytes(file_data)[:16]
        doc = Document(doc_id=doc_id)
        doc.metadata = DocumentMetadata(
            source_format="ocr",
            mime_type="application/ocr",
            file_size_bytes=len(file_data),
            file_md5=md5_bytes(file_data),
        )
        doc.log_stage("ocr_preprocess_start")

        ext = get_file_extension(file_name)

        try:
            if ext == "pdf":
                pages_data = self._pdf_to_images(file_data)
                doc.metadata.source_format = "pdf"
            elif ext in self.supported_extensions:
                # Single image file → one page
                pages_data = [file_data]
            else:
                self._raise_unsupported(ext)

            if not pages_data:
                self._raise_no_text()

            for page_num, img_data in enumerate(pages_data, start=1):
                text = self._ocr_image(img_data)
                page = Page(page_number=page_num)
                page.text_content = text
                page.is_scanned = True

                # Split OCR text into paragraphs
                paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
                for p_idx, para in enumerate(paragraphs):
                    page.elements.append(TextElement(
                        element_id=self._make_element_id(doc_id, page_num, p_idx, "ocr"),
                        role=ElementRole.PARAGRAPH,
                        page_numbers=[page_num],
                        text=para,
                    ))

                doc.pages.append(page)

            doc.metadata.char_count = sum(p.text_content and len(p.text_content) or 0 for p in doc.pages)
            doc.metadata.word_count = doc.metadata.char_count // 2  # rough estimate for CJK
            doc.metadata.page_count = len(doc.pages)
            doc.metadata.is_scanned = True

            doc.log_stage("ocr_preprocess_done")
            return doc

        except Exception as e:
            from common.exception.exceptions import PreprocessingException
            raise PreprocessingException(f"OCR extraction failed: {e}", format_type="ocr")

    def _pdf_to_images(self, pdf_data: bytes) -> list[bytes]:
        """Convert PDF pages to PNG images for OCR."""
        try:
            from pdf2image import convert_from_bytes
            images = convert_from_bytes(pdf_data, dpi=self._dpi, fmt="png")
            result = []
            for img in images:
                buf = io.BytesIO()
                img.save(buf, format="PNG")
                result.append(buf.getvalue())
            logger.info(f"PDF converted: {len(result)} page images")
            return result
        except ImportError:
            raise PreprocessingException(
                "pdf2image not installed. Install: pip install pdf2image + apt install poppler-utils",
                format_type="ocr"
            )

    def _ocr_image(self, img_data: bytes) -> str:
        """Run OCR on an image — tries Tesseract first, falls back to EasyOCR."""
        # Try Tesseract first (fast, lightweight)
        try:
            import pytesseract
            from PIL import Image
            img = Image.open(io.BytesIO(img_data))
            if img.mode != "L":
                img = img.convert("L")
            text = pytesseract.image_to_string(img, lang=self._lang)
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

    def _raise_unsupported(self, ext: str):
        from common.exception.exceptions import PreprocessingException
        raise PreprocessingException(f"Unsupported format for OCR: {ext}", format_type="ocr")

    def _raise_no_text(self):
        from common.exception.exceptions import PreprocessingException
        raise PreprocessingException("OCR produced no text (possibly blank image)", format_type="ocr")
