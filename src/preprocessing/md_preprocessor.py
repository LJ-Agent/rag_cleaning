"""Markdown preprocessor — parse Markdown into structured Document elements."""

import re
from uuid import uuid4

from common.models.document import (
    CodeElement,
    Document,
    DocumentMetadata,
    ElementRole,
    HeadingLevel,
    Page,
    TextElement,
)
from common.util.logger import bind_trace_id, get_logger
from common.util.utils import md5_bytes
from preprocessing.base import BasePreprocessor

logger = get_logger()


class MarkdownPreprocessor(BasePreprocessor):
    """Parse Markdown files into Document elements, preserving heading hierarchy and code blocks."""

    format_type = "md"
    supported_extensions = {"md", "markdown"}
    supported_mime_types = {"text/markdown"}

    # Heading patterns
    HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)
    CODE_BLOCK_RE = re.compile(r"```(\w+)?\n(.*?)```", re.DOTALL)
    QUOTE_RE = re.compile(r"^>\s?(.+)$", re.MULTILINE)
    LIST_ITEM_RE = re.compile(r"^(\s*)([-*+]|\d+[.)])\s+(.+)$", re.MULTILINE)

    LEVEL_MAP = {1: HeadingLevel.H1, 2: HeadingLevel.H2, 3: HeadingLevel.H3, 4: HeadingLevel.H4, 5: HeadingLevel.H5, 6: HeadingLevel.H6}

    def extract(self, file_data: bytes, file_name: str) -> Document:
        log = bind_trace_id(str(uuid4())[:8])
        doc_id = md5_bytes(file_data)[:16]
        doc = Document(doc_id=doc_id)

        doc.metadata = DocumentMetadata(
            source_format="md",
            mime_type="text/markdown",
            file_size_bytes=len(file_data),
            file_md5=md5_bytes(file_data),
        )
        doc.log_stage("md_preprocess_start")

        try:
            text = self._decode_text(file_data)
        except Exception as e:
            from common.exception.exceptions import PreprocessingException
            raise PreprocessingException(f"MD decode failed: {e}", format_type="md")

        page = Page(page_number=1)
        elem_idx = 0

        # Split into blocks by double newline
        blocks = text.split("\n\n")
        remaining = text

        for block in blocks:
            block = block.strip()
            if not block:
                continue

            # Check heading
            heading_match = self.HEADING_RE.match(block)
            if heading_match:
                level_num = len(heading_match.group(1))
                content = heading_match.group(2).strip()
                page.elements.append(TextElement(
                    element_id=self._make_element_id(doc_id, 1, elem_idx, "h"),
                    role=ElementRole.HEADING,
                    page_numbers=[1],
                    text=content,
                    heading_level=self.LEVEL_MAP.get(level_num, HeadingLevel.H2),
                ))
                elem_idx += 1
                if level_num == 1 and not doc.metadata.title:
                    doc.metadata.title = content
                continue

            # Check code block
            code_match = self.CODE_BLOCK_RE.match(block)
            if code_match:
                lang = code_match.group(1) or ""
                code = code_match.group(2).strip()
                page.elements.append(CodeElement(
                    element_id=self._make_element_id(doc_id, 1, elem_idx, "code"),
                    role=ElementRole.CODE_BLOCK,
                    page_numbers=[1],
                    code=code,
                    language=lang,
                ))
                elem_idx += 1
                continue

            # Check quote
            if block.startswith("> "):
                clean = "\n".join(line[2:] for line in block.split("\n") if line.startswith("> "))
                page.elements.append(TextElement(
                    element_id=self._make_element_id(doc_id, 1, elem_idx, "q"),
                    role=ElementRole.QUOTE,
                    page_numbers=[1],
                    text=clean,
                ))
                elem_idx += 1
                continue

            # Check list items
            if self.LIST_ITEM_RE.match(block.split("\n")[0]):
                page.elements.append(TextElement(
                    element_id=self._make_element_id(doc_id, 1, elem_idx, "li"),
                    role=ElementRole.LIST_ITEM,
                    page_numbers=[1],
                    text=block,
                ))
                elem_idx += 1
                continue

            # Regular paragraph
            page.elements.append(TextElement(
                element_id=self._make_element_id(doc_id, 1, elem_idx, "p"),
                role=ElementRole.PARAGRAPH,
                page_numbers=[1],
                text=block,
            ))
            elem_idx += 1

        page.text_content = text
        doc.metadata.char_count = len(text)
        doc.metadata.word_count = len(text.split())
        doc.pages.append(page)

        doc.log_stage("md_preprocess_done")
        return doc
