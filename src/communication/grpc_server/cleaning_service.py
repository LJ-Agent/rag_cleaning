"""gRPC CleaningService implementation — synchronous cleaning + status query."""

import time
from uuid import uuid4

import grpc
from google.protobuf.json_format import MessageToDict

from common.config_loader import get_config
from common.models.document import CleaningTask
from common.util.logger import bind_trace_id, get_logger
from infrastructure.minio.minio_client import get_minio_client
from infrastructure.redis.redis_client import get_redis_client
from scheduling.state_machine import get_state_machine_factory

logger = get_logger()


class CleaningServiceServicer:
    """gRPC CleaningService implementation (port 50056).

    This is a simplified implementation that delegates to the Kafka-driven
    pipeline. The gRPC endpoint is used for:
    - Synchronous small-file cleaning
    - Task status queries
    - Health checks
    """

    def __init__(self):
        self._minio = get_minio_client()
        self._redis = get_redis_client()
        self._state_factory = get_state_machine_factory()
        self._start_time = time.time()

    # ─── Clean (synchronous, for small files) ──────────────

    def Clean(self, request, context):
        """Handle synchronous cleaning request."""
        task_id = request.task_id or str(uuid4())
        log = bind_trace_id(task_id)

        logger.info(f"gRPC Clean request: task={task_id}, doc={request.document_id}, file={request.file_name}")

        # Create state machine entry
        sm = self._state_factory.create(task_id)

        # Download file from MinIO
        try:
            file_data = self._minio.get_object(request.file_url)
        except Exception as e:
            context.set_code(grpc.StatusCode.NOT_FOUND)
            context.set_details(f"File not found: {request.file_url}")
            return self._build_error_response(task_id, str(e))

        # Build cleaning task context
        task = CleaningTask(
            task_id=task_id,
            document_id=request.document_id,
            kb_id=request.kb_id,
            tenant_id=request.tenant_id or "default",
            file_name=request.file_name,
            file_url=request.file_url,
            mime_type=request.mime_type,
            created_at=str(int(time.time() * 1000)),
        )

        # Dispatch to pipeline (simplified for gRPC path — uses in-process pipeline)
        # Full implementation would send to Kafka and poll for result
        try:
            from output.metadata_generator import MetadataGenerator
            result = self._run_inline_pipeline(task, file_data)
            meta_gen = MetadataGenerator()
            metadata = meta_gen.generate(result)

            # Store results to MinIO
            tenant_id = task.tenant_id or "default"
            doc_id = task.document_id
            md_path = self._minio.put_cleaned_markdown(doc_id, tenant_id, result)
            meta_path = self._minio.put_metadata_json(doc_id, tenant_id, metadata)

            # Build response
            response = {
                "task_id": task_id,
                "status": "SUCCESS",
                "markdown_url": md_path,
                "metadata_url": meta_path,
                "quality": {
                    "overall_score": result.quality.overall_score if result.quality else 1.0,
                    "completeness": result.quality.completeness if result.quality else 1.0,
                    "purity": result.quality.purity if result.quality else 1.0,
                    "structure": result.quality.structure if result.quality else 1.0,
                    "coherence": result.quality.coherence if result.quality else 1.0,
                },
                "doc_meta": {
                    "title": result.metadata.title,
                    "author": result.metadata.author,
                    "page_count": result.page_count,
                    "word_count": result.metadata.word_count,
                    "language": result.metadata.language,
                },
            }
            return type("CleaningResponse", (), response)()

        except Exception as e:
            logger.error(f"Cleaning failed for {task_id}: {e}")
            return self._build_error_response(task_id, str(e))

    def _run_inline_pipeline(self, task: CleaningTask, file_data: bytes):
        """Run the full cleaning pipeline in-process (for gRPC sync path)."""
        from common.util.utils import get_file_extension

        ext = get_file_extension(task.file_name)

        # Step 1: Format preprocessing
        from preprocessing.pdf_preprocessor import PDFPreprocessor
        from preprocessing.docx_preprocessor import DocxPreprocessor
        from preprocessing.xlsx_preprocessor import XlsxPreprocessor
        from preprocessing.pptx_preprocessor import PptxPreprocessor
        from preprocessing.md_preprocessor import MarkdownPreprocessor
        from preprocessing.txt_preprocessor import TxtPreprocessor

        preprocessors = {
            "pdf": PDFPreprocessor(),
            "docx": DocxPreprocessor(),
            "xlsx": XlsxPreprocessor(),
            "pptx": PptxPreprocessor(),
            "md": MarkdownPreprocessor(),
            "txt": TxtPreprocessor(),
        }

        prep = preprocessors.get(ext)
        if prep is None:
            from common.exception.exceptions import UnsupportedFormatException
            raise UnsupportedFormatException(f"Unsupported format: {ext}", format_type=ext)

        doc = prep.extract(file_data, task.file_name)
        doc.doc_id = task.document_id

        # Step 2: Element processing
        from elements.table_processor import TableProcessor
        from elements.image_processor import ImageProcessor
        from elements.formula_processor import FormulaProcessor

        table_proc = TableProcessor()
        image_proc = ImageProcessor()
        formula_proc = FormulaProcessor()

        for page in doc.pages:
            for i, elem in enumerate(page.elements):
                if hasattr(elem, "role") and elem.role.value == "table":
                    page.elements[i] = table_proc.process(elem)
                elif hasattr(elem, "role") and elem.role.value == "image":
                    page.elements[i] = image_proc.process(elem)
                elif hasattr(elem, "role") and elem.role.value == "formula":
                    page.elements[i] = formula_proc.process(elem)

        # Step 3: General cleaning
        from cleaning.basic_cleaner import BasicCleaner
        from cleaning.content_filter import ContentFilter
        from cleaning.structure_fixer import StructureFixer
        from cleaning.sensitive_masker import SensitiveMasker

        BasicCleaner().clean(doc)
        ContentFilter().filter(doc)
        StructureFixer().fix(doc)
        SensitiveMasker().mask(doc)

        # Step 4: Quality validation
        from cleaning.quality_validator import QualityValidator
        QualityValidator().validate(doc)

        # Step 5: Markdown generation
        from output.markdown_generator import MarkdownGenerator
        task.cleaned_markdown = MarkdownGenerator().generate(doc)

        return task.cleaned_markdown

    # ─── GetTaskStatus ─────────────────────────────────────

    def GetTaskStatus(self, request, context):
        sm = self._state_factory.get(request.task_id)
        if not sm:
            context.set_code(grpc.StatusCode.NOT_FOUND)
            context.set_details(f"Task not found: {request.task_id}")
            return type("TaskStatusResponse", (), {"task_id": request.task_id, "status": "NOT_FOUND"})()

        return type("TaskStatusResponse", (), sm.to_dict())()

    # ─── HealthCheck ───────────────────────────────────────

    def HealthCheck(self, request, context):
        components = {
            "minio": self._minio is not None,
            "redis": self._redis is not None,
            "kafka": True,  # Would check actual connectivity
            "llm": True,
        }
        return type("HealthCheckResponse", (), {
            "healthy": all(components.values()),
            "version": "1.0.0",
            "components": components,
        })()

    def _build_error_response(self, task_id: str, error: str):
        return type("CleaningResponse", (), {
            "task_id": task_id,
            "status": "FAILED",
            "markdown_url": "",
            "metadata_url": "",
            "error_message": error,
        })()
