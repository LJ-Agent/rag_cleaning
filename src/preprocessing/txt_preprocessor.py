"""Plain text preprocessor — minimal processing, converts raw text to Document."""

from uuid import uuid4

from common.exception.exceptions import PreprocessingException
from common.models.document import (
    Document,
    DocumentMetadata,
    ElementRole,
    Page,
    TextElement,
)
from common.util.logger import bind_trace_id, get_logger
from common.util.utils import md5_bytes
from preprocessing.base import BasePreprocessor

logger = get_logger()


class TxtPreprocessor(BasePreprocessor):
    """Convert plain text files into Document format. Attempts basic paragraph detection."""

    format_type = "txt"
    supported_extensions = {"txt", "text", "log", "csv"}
    supported_mime_types = {"text/plain"}

    def extract(self, file_data: bytes, file_name: str) -> Document:
        log = bind_trace_id(str(uuid4())[:8])
        doc_id = md5_bytes(file_data)[:16]
        doc = Document(doc_id=doc_id)

        doc.metadata = DocumentMetadata(
            source_format="txt",
            mime_type="text/plain",
            file_size_bytes=len(file_data),
            file_md5=md5_bytes(file_data),
        )
        doc.log_stage("txt_preprocess_start")

        # Try UTF-8 first, then common encodings
        text = None
        for encoding in ["utf-8", "gbk", "gb2312", "latin-1"]:
            try:
                text = file_data.decode(encoding)
                break
            except (UnicodeDecodeError, LookupError):
                continue

        if text is None:
            raise PreprocessingException("Unable to decode text file with any supported encoding", format_type="txt")

        # Normalize line endings
        text = text.replace("\r\n", "\n").replace("\r", "\n")

        page = Page(page_number=1)
        elem_idx = 0

        # Split into paragraphs by double newline
        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]

        for para in paragraphs:
            page.elements.append(TextElement(
                element_id=self._make_element_id(doc_id, 1, elem_idx, "txt"),
                role=ElementRole.PARAGRAPH,
                page_numbers=[1],
                text=para,
            ))
            elem_idx += 1

        page.text_content = text
        doc.metadata.char_count = len(text)
        doc.metadata.word_count = len(text.split())
        doc.pages.append(page)

        doc.log_stage("txt_preprocess_done")
        return doc
