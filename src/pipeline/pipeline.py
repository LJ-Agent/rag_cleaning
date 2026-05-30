"""Centralized document cleaning pipeline — format parse → element process → clean → validate."""

from typing import Any, Callable

from common.models.document import CleaningTask, Document
from common.util.logger import get_logger
from common.util.utils import get_file_extension

logger = get_logger()


class Pipeline:
    """Centralized document cleaning pipeline orchestrator.

    Stages: format_parse → element_process → clean → validate → output.
    """

    def __init__(self):
        self._preprocessors = self._build_preprocessor_map()
        self._cleaners = self._build_cleaner_list()

    # ─── Main entry point ────────────────────────────────────

    def run(self, task: CleaningTask, file_data: bytes) -> Document:
        """Execute the full pipeline. Returns the processed Document."""
        ext = get_file_extension(task.file_name)

        # Stage 1: Format parsing
        prep = self._preprocessors.get(ext)
        if prep is None:
            from common.exception.exceptions import UnsupportedFormatException
            raise UnsupportedFormatException(f"Unsupported format: {ext}", format_type=ext)

        doc = prep.extract(file_data, task.file_name)
        doc.doc_id = task.document_id
        doc.log_stage("format_parse_done")

        # Stage 2: Element processing
        self._stage_element_process(doc, task.params)
        doc.log_stage("element_process_done")

        # Stage 3: Cleaning
        self._stage_clean(doc)
        doc.log_stage("clean_done")

        # Stage 4: Validation
        self._stage_validate(doc)
        doc.log_stage("validate_done")

        return doc

    def run_and_generate(self, task: CleaningTask, file_data: bytes) -> dict:
        """Run pipeline and produce markdown + metadata outputs."""
        doc = self.run(task, file_data)
        from output.markdown_generator import MarkdownGenerator
        from output.metadata_generator import MetadataGenerator
        return {
            "document": doc,
            "markdown": MarkdownGenerator().generate(doc),
            "metadata": MetadataGenerator().generate(doc),
        }

    # ─── Stage implementations ───────────────────────────────

    def _stage_element_process(self, doc: Document, params: dict | None = None):
        """Dispatch every element to its registered processor(s) via registry."""
        from elements.registry import get_element_registry
        registry = get_element_registry()

        context = params or {}
        context["document_title"] = doc.metadata.title

        all_elems = [(page, i, elem) for page in doc.pages for i, elem in enumerate(page.elements)]
        all_elems += [(None, i, elem) for i, elem in enumerate(doc.elements)]

        for container, idx, elem in all_elems:
            processors = registry.get_for_element(elem)
            for proc in processors:
                try:
                    result = proc.execute(elem, context)
                    if container is not None:
                        container.elements[idx] = result
                    else:
                        doc.elements[idx] = result
                except Exception as e:
                    logger.error(f"Processor '{proc.processor_name}' failed for {elem.element_id}: {e}")

    def _stage_clean(self, doc: Document):
        """Apply all cleaners in order."""
        for cleaner in self._cleaners:
            cleaner(doc)

    def _stage_validate(self, doc: Document):
        """Run quality validation."""
        from cleaning.quality_validator import QualityValidator
        QualityValidator().validate(doc)

    # ─── Builder methods ─────────────────────────────────────

    def _build_preprocessor_map(self) -> dict[str, Any]:
        from preprocessing.pdf_preprocessor import PDFPreprocessor
        from preprocessing.docx_preprocessor import DocxPreprocessor
        from preprocessing.xlsx_preprocessor import XlsxPreprocessor
        from preprocessing.pptx_preprocessor import PptxPreprocessor
        from preprocessing.md_preprocessor import MarkdownPreprocessor
        from preprocessing.txt_preprocessor import TxtPreprocessor
        from preprocessing.ocr_preprocessor import OCRPreprocessor

        preps = [PDFPreprocessor(), DocxPreprocessor(), XlsxPreprocessor(),
                 PptxPreprocessor(), MarkdownPreprocessor(), TxtPreprocessor(), OCRPreprocessor()]
        mapping: dict[str, Any] = {}
        for p in preps:
            for ext in p.supported_extensions:
                mapping[ext] = p
        return mapping

    def _build_cleaner_list(self) -> list[Callable[[Document], None]]:
        from cleaning.basic_cleaner import BasicCleaner
        from cleaning.content_filter import ContentFilter
        from cleaning.structure_fixer import StructureFixer
        from cleaning.sensitive_masker import SensitiveMasker

        bc = BasicCleaner()
        cf = ContentFilter()
        sf = StructureFixer()
        sm = SensitiveMasker()
        return [bc.clean, cf.filter, sf.fix, sm.mask]
