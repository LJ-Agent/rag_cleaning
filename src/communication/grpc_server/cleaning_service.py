"""gRPC CleaningService implementation — synchronous cleaning + status query."""

import time
from uuid import uuid4

import grpc
from google.protobuf.json_format import MessageToDict

from common.config_loader import get_config
from common.models.document import CleaningTask
from common.util.logger import bind_trace_id, get_logger
from communication.grpc_server.generated import cleaning_pb2
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

    def CleanStream(self, request_iterator, context):
        """Handle streaming cleaning request (not implemented — use Clean for sync)."""
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details("CleanStream is not implemented. Use the synchronous Clean RPC.")
        return cleaning_pb2.CleaningResponse(
            task_id="stream",
            status=cleaning_pb2.CleaningStatus.FAILED,
            error_message="CleanStream not implemented",
        )

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
            md_text, doc = self._run_inline_pipeline(task, file_data)
            meta_gen = MetadataGenerator()
            metadata = meta_gen.generate(doc)

            # Store results to MinIO
            tenant_id = task.tenant_id or "default"
            doc_id = task.document_id
            md_path = self._minio.put_cleaned_markdown(doc_id, tenant_id, md_text)
            meta_path = self._minio.put_metadata_json(doc_id, tenant_id, metadata)

            # Build response using protobuf message
            quality = cleaning_pb2.QualityReport(
                overall_score=doc.quality.overall_score if doc.quality else 1.0,
                completeness=doc.quality.completeness if doc.quality else 1.0,
                purity=doc.quality.purity if doc.quality else 1.0,
                structure=doc.quality.structure if doc.quality else 1.0,
                coherence=doc.quality.coherence if doc.quality else 1.0,
            )
            doc_meta = cleaning_pb2.DocumentMetadata(
                title=doc.metadata.title,
                author=doc.metadata.author,
                page_count=doc.page_count,
                word_count=doc.metadata.word_count,
                language=doc.metadata.language,
            )
            return cleaning_pb2.CleaningResponse(
                task_id=task_id,
                status=cleaning_pb2.CleaningStatus.SUCCESS,
                markdown_url=md_path,
                metadata_url=meta_path,
                quality=quality,
                doc_meta=doc_meta,
            )

        except Exception as e:
            logger.error(f"Cleaning failed for {task_id}: {e}")
            return self._build_error_response(task_id, str(e))

    def _run_inline_pipeline(self, task: CleaningTask, file_data: bytes):
        """Run the full cleaning pipeline in-process (for gRPC sync path).

        Returns:
            Tuple of (markdown_text: str, doc: Document)
        """
        from pipeline.pipeline import Pipeline
        doc = Pipeline().run(task, file_data)
        from output.markdown_generator import MarkdownGenerator
        md_text = MarkdownGenerator().generate(doc)
        return md_text, doc

    # ─── GetTaskStatus ─────────────────────────────────────

    def GetTaskStatus(self, request, context):
        sm = self._state_factory.get(request.task_id)
        if not sm:
            context.set_code(grpc.StatusCode.NOT_FOUND)
            context.set_details(f"Task not found: {request.task_id}")
            return cleaning_pb2.TaskStatusResponse(task_id=request.task_id, status="NOT_FOUND")
        return cleaning_pb2.TaskStatusResponse(task_id=request.task_id, status=sm.current_state or "UNKNOWN")

        return type("TaskStatusResponse", (), sm.to_dict())()

    # ─── HealthCheck ───────────────────────────────────────

    def HealthCheck(self, request, context):
        components = {
            "minio": self._minio is not None,
            "redis": self._redis is not None,
            "kafka": True,  # Would check actual connectivity
            "llm": True,
        }
        return cleaning_pb2.HealthCheckResponse(
            healthy=all(components.values()),
            version="1.0.0",
            components=components,
        )

    def _build_error_response(self, task_id: str, error: str):
        return cleaning_pb2.CleaningResponse(
            task_id=task_id,
            status=cleaning_pb2.CleaningStatus.FAILED,
            markdown_url="",
            metadata_url="",
            error_message=error,
        )
