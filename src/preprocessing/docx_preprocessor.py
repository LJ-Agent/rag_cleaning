"""Word (DOCX) preprocessor — extract text, tables, images, headings, lists."""

import io
from uuid import uuid4

from common.config_loader import get_config
from common.exception.exceptions import PreprocessingException
from common.models.document import (
    BoundingBox,
    Document,
    DocumentMetadata,
    ElementRole,
    HeadingLevel,
    ImageElement,
    Page,
    TableCell,
    TableElement,
    TextElement,
    TextRun,
)
from common.util.logger import bind_trace_id, get_logger
from common.util.utils import md5_bytes
from preprocessing.base import BasePreprocessor

logger = get_logger()


class DocxPreprocessor(BasePreprocessor):
    """Extract raw elements from Word documents using python-docx."""

    format_type = "docx"
    supported_extensions = {"docx"}
    supported_mime_types = {
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    }

    def __init__(self):
        cfg = get_config()["preprocessing"]["docx"]
        self._extract_images = cfg.get("extract_images", True)
        self._extract_tables = cfg.get("extract_tables", True)
        self._preserve_headings = cfg.get("preserve_heading_hierarchy", True)

    def extract(self, file_data: bytes, file_name: str) -> Document:
        log = bind_trace_id(str(uuid4())[:8])
        doc_id = md5_bytes(file_data)[:16]
        doc = Document(doc_id=doc_id)

        doc.metadata = DocumentMetadata(
            source_format="docx",
            mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            file_size_bytes=len(file_data),
            file_md5=md5_bytes(file_data),
        )
        doc.log_stage("docx_preprocess_start")

        try:
            from docx import Document as DocxDocument
            from docx.enum.text import WD_ALIGN_PARAGRAPH
            from docx.oxml.ns import qn

            docx = DocxDocument(io.BytesIO(file_data))

            # Metadata
            if docx.core_properties:
                doc.metadata.title = docx.core_properties.title or ""
                doc.metadata.author = docx.core_properties.author or ""
                doc.metadata.subject = docx.core_properties.subject or ""
                doc.metadata.created_at = str(docx.core_properties.created) if docx.core_properties.created else ""
                doc.metadata.keywords = list(docx.core_properties.keywords or [])

            # Process all body elements in order
            page = Page(page_number=1)
            elem_idx = 0
            full_text = ""

            for item in docx.element.body:
                tag = item.tag.split("}")[-1] if "}" in item.tag else item.tag

                if tag == "p":
                    # Paragraph
                    para = self._get_paragraph(docx, item)
                    if para is None:
                        continue

                    text = para.text.strip()
                    if not text:
                        continue

                    full_text += text + "\n"
                    role = self._detect_paragraph_role(para)
                    level = self._detect_heading_level(para)

                    runs = []
                    for run in para.runs:
                        runs.append(TextRun(
                            text=run.text,
                            bold=run.bold or False,
                            italic=run.italic or False,
                            underline=run.underline or False,
                            font_size=run.font.size.pt if run.font.size else None,
                            font_name=run.font.name,
                        ))

                    elem = TextElement(
                        element_id=self._make_element_id(doc_id, 1, elem_idx, "txt"),
                        role=role,
                        page_numbers=[1],
                        text=text,
                        runs=runs,
                        heading_level=level,
                    )
                    page.elements.append(elem)
                    elem_idx += 1

                elif tag == "tbl":
                    # Table
                    if self._extract_tables:
                        table = self._extract_docx_table(item, doc_id, elem_idx)
                        page.elements.append(table)
                        elem_idx += 1
                        doc.metadata.has_tables = True

            # Extract images from relationships
            if self._extract_images:
                for rel in docx.part.rels.values():
                    if "image" in rel.reltype:
                        try:
                            img_data = rel.target_part.blob
                            img_hash = md5_bytes(img_data)
                            img = ImageElement(
                                element_id=self._make_element_id(doc_id, 1, elem_idx, "img"),
                                role=ElementRole.IMAGE,
                                page_numbers=[1],
                                image_data=img_data,
                                image_hash=img_hash,
                                format=rel.target_ext.strip(".") if rel.target_ext else "png",
                            )
                            page.elements.append(img)
                            elem_idx += 1
                            doc.metadata.has_images = True
                        except Exception:
                            pass

            page.text_content = full_text
            doc.metadata.char_count = len(full_text)
            doc.metadata.word_count = len(full_text.split())
            doc.pages.append(page)

        except Exception as e:
            raise PreprocessingException(f"DOCX extraction failed: {e}", format_type="docx")

        doc.log_stage("docx_preprocess_done")
        return doc

    def _get_paragraph(self, docx, xml_element):
        """Get paragraph object from XML element (python-docx internal API)."""
        from docx.text.paragraph import Paragraph
        return Paragraph(xml_element, docx)

    def _detect_paragraph_role(self, para) -> ElementRole:
        """Detect semantic role of a paragraph."""
        style_name = (para.style.name if para.style else "").lower()
        if any(kw in style_name for kw in ["heading", "title", "heading"]):
            return ElementRole.HEADING
        if para.paragraph_format and para.paragraph_format.first_line_indent:
            return ElementRole.PARAGRAPH
        return ElementRole.PARAGRAPH

    def _detect_heading_level(self, para) -> HeadingLevel | None:
        """Detect heading level from paragraph style."""
        style_name = (para.style.name if para.style else "").lower()
        mapping = {
            "heading 1": HeadingLevel.H1,
            "heading 2": HeadingLevel.H2,
            "heading 3": HeadingLevel.H3,
            "heading 4": HeadingLevel.H4,
            "heading 5": HeadingLevel.H5,
            "heading 6": HeadingLevel.H6,
            "title": HeadingLevel.H1,
        }
        return mapping.get(style_name)

    def _extract_docx_table(self, tbl_xml, doc_id: str, start_idx: int) -> TableElement:
        """Extract table from docx table XML element."""
        from docx import Document as DocxDocument
        from docx.table import Table

        rows = []
        for row_xml in tbl_xml.findall(".//{http://schemas.openxmlformats.org/wordprocessingml/2006/main}tr"):
            cells = []
            for cell_xml in row_xml.findall(".//{http://schemas.openxmlformats.org/wordprocessingml/2006/main}tc"):
                text_parts = []
                for p in cell_xml.findall(".//{http://schemas.openxmlformats.org/wordprocessingml/2006/main}p"):
                    for t in p.findall(".//{http://schemas.openxmlformats.org/wordprocessingml/2006/main}t"):
                        if t.text:
                            text_parts.append(t.text)
                cells.append(TableCell(text="".join(text_parts).strip()))
            rows.append(cells)

        return TableElement(
            element_id=self._make_element_id(doc_id, 1, start_idx, "tbl"),
            role=ElementRole.TABLE,
            page_numbers=[1],
            rows=rows,
            column_count=max((len(r) for r in rows), default=0),
            row_count=len(rows),
        )
