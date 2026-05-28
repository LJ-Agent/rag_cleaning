"""RAG-CLEANING service entry point.

Starts:
- gRPC CleaningService (port 50056)
- Kafka consumer (multi-topic cleaning tasks)
- Graceful shutdown on SIGINT/SIGTERM
"""

import signal
import sys
import threading
import time
from concurrent import futures

import grpc

from common.config_loader import get_config
from common.util.logger import get_logger, setup_logging


def start_grpc_server(servicer) -> grpc.Server:
    """Start gRPC server on configured port."""
    cfg = get_config()["grpc"]["cleaning"]
    port = cfg["port"]
    max_workers = cfg.get("max_workers", 20)

    server = grpc.server(futures.ThreadPoolExecutor(max_workers=max_workers))

    # Import generated stubs (compiled from cleaning.proto)
    try:
        from communication.grpc_server.generated import cleaning_pb2, cleaning_pb2_grpc
        cleaning_pb2_grpc.add_CleaningServiceServicer_to_server(servicer, server)
    except ImportError:
        logger = get_logger()
        logger.warning("gRPC stubs not compiled. Run: python scripts/compile_proto.py")
        logger.warning("gRPC server will start without service registration.")

    server.add_insecure_port(f"[::]:{port}")
    server.start()
    logger = get_logger()
    logger.info(f"gRPC CleaningService started on port {port}")
    return server


def start_kafka_consumer():
    """Start Kafka consumer for cleaning tasks."""
    from communication.kafka_consumer.task_consumer import CleaningTaskConsumer
    from communication.kafka_producer.event_producer import get_event_producer
    from common.constant.kafka_constants import CleaningTopics

    logger = get_logger()

    consumer = CleaningTaskConsumer()

    # Register topic handlers
    from scheduling.format_router import FormatRouter
    router = FormatRouter()
    producer = get_event_producer()

    def handle_task_submit(task_msg, topic, partition, offset):
        """Handle incoming task submission: validate → route → forward."""
        logger.info(f"Handling task submit: {task_msg.task_id} ({task_msg.document_id})")
        try:
            file_name = task_msg.data.get("fileName", "")
            mime_type = task_msg.data.get("mimeType", "")
            target_topic = router.route(file_name, mime_type)
            msg_dict = task_msg.to_json()

            if target_topic:
                producer._send(target_topic, msg_dict, key=task_msg.task_id)
            else:
                # Direct to general cleaning (MD/TXT)
                producer.send_for_general_cleaning(msg_dict)

            consumer._commit_offset(topic, partition, offset)
        except Exception as e:
            logger.error(f"Task routing failed: {task_msg.task_id} — {e}")
            from common.models.document import CleaningEvent
            event = CleaningEvent(
                task_id=task_msg.task_id, document_id=task_msg.document_id,
                kb_id=task_msg.kb_id, tenant_id=task_msg.tenant_id,
                status="FAILED", error_message=str(e),
            )
            producer.send_to_dlq(event)
            consumer._commit_offset(topic, partition, offset)

    def handle_preprocess_complete(task_msg, topic, partition, offset):
        """Handle preprocessing completion → forward to element processing."""
        logger.info(f"Preprocessing complete: {task_msg.task_id}")
        msg_dict = task_msg.to_json()
        producer.send_unified_document(msg_dict)
        consumer._commit_offset(topic, partition, offset)

    def handle_element_complete(task_msg, topic, partition, offset):
        """Handle element processing completion → forward to general cleaning."""
        logger.info(f"Element processing complete: {task_msg.task_id}")
        msg_dict = task_msg.to_json()
        producer.send_for_general_cleaning(msg_dict)
        consumer._commit_offset(topic, partition, offset)

    def handle_general_cleaning(task_msg, topic, partition, offset):
        """Handle general cleaning → validate → complete/fail."""
        logger.info(f"General cleaning: {task_msg.task_id}")
        from common.models.document import CleaningEvent
        event = CleaningEvent(
            task_id=task_msg.task_id,
            document_id=task_msg.document_id,
            kb_id=task_msg.kb_id,
            tenant_id=task_msg.tenant_id,
            status="SUCCESS",
        )
        producer.send_complete(event)
        consumer._commit_offset(topic, partition, offset)

    def handle_retry(task_msg, topic, partition, offset):
        """Handle retry task → re-route to appropriate stage."""
        logger.info(f"Handling retry: {task_msg.task_id}")
        from scheduling.retry_scheduler import get_retry_scheduler
        retry = get_retry_scheduler()

        if retry.should_retry(task_msg.task_id):
            retry.record_attempt(task_msg.task_id)
            delay = retry.calculate_delay(task_msg.task_id)
            logger.info(f"Task {task_msg.task_id} will retry after {delay}s")
            time.sleep(min(delay, 5))  # Non-blocking approximation
            msg_dict = task_msg.to_json()
            producer.send_retry(msg_dict)
        else:
            from common.models.document import CleaningEvent
            from scheduling.dlq_manager import get_dlq_manager
            dlq = get_dlq_manager()
            event = CleaningEvent(
                task_id=task_msg.task_id,
                document_id=task_msg.document_id,
                kb_id=task_msg.kb_id,
                tenant_id=task_msg.tenant_id,
                status="FAILED",
                error_message=f"Max retries ({retry._max_retries}) exceeded",
            )
            producer.send_to_dlq(event)
            dlq.enqueue(task_msg.task_id, task_msg.to_json(),
                        f"Max retries ({retry._max_retries}) exceeded")

        consumer._commit_offset(topic, partition, offset)

    # Register handlers
    consumer.register_handler(CleaningTopics.TASK_SUBMIT, handle_task_submit)

    # Format preprocessing topics → all go to unified input
    for topic in [CleaningTopics.PDF_PREPROCESS, CleaningTopics.DOCX_PREPROCESS,
                  CleaningTopics.XLSX_PREPROCESS, CleaningTopics.PPTX_PREPROCESS,
                  CleaningTopics.OCR_PREPROCESS]:
        consumer.register_handler(topic, handle_preprocess_complete)

    # Element processing topics
    for topic in [CleaningTopics.ELEMENT_TABLE, CleaningTopics.ELEMENT_IMAGE,
                  CleaningTopics.ELEMENT_FORMULA]:
        consumer.register_handler(topic, handle_element_complete)

    consumer.register_handler(CleaningTopics.GENERAL_CLEANING, handle_general_cleaning)
    consumer.register_handler(CleaningTopics.RETRY, handle_retry)

    consumer.start()
    return consumer


def main():
    """Main entry point — start all services."""
    # Initialize configuration
    cfg = get_config()

    # Setup logging
    log_cfg = cfg["logging"]
    setup_logging(level=log_cfg.get("level", "INFO"), log_format=log_cfg.get("format"))
    logger = get_logger()
    logger.info("Starting RAG-CLEANING service...")

    # Pre-warm infrastructure singletons
    from infrastructure.minio.minio_client import get_minio_client
    from infrastructure.redis.redis_client import get_redis_client
    get_minio_client()
    get_redis_client()
    logger.info("Infrastructure clients initialized")

    # Start gRPC server
    from communication.grpc_server.cleaning_service import CleaningServiceServicer
    servicer = CleaningServiceServicer()
    grpc_server = start_grpc_server(servicer)

    # Start Kafka consumer
    consumer = start_kafka_consumer()

    # Graceful shutdown handler
    shutdown_flag = threading.Event()

    def shutdown(signum, frame):
        logger.info(f"Received signal {signum}, shutting down...")
        shutdown_flag.set()

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    logger.info("RAG-CLEANING service started successfully")
    logger.info(f"  gRPC: :{cfg['grpc']['cleaning']['port']}")
    logger.info(f"  Kafka: {cfg['kafka']['bootstrap_servers']}")

    # Wait for shutdown
    try:
        while not shutdown_flag.is_set():
            time.sleep(1)
    except KeyboardInterrupt:
        pass

    # Graceful shutdown
    logger.info("Shutting down...")
    consumer.stop()
    grpc_server.stop(5)
    from infrastructure.redis.redis_client import get_redis_client
    get_redis_client().close()

    logger.info("RAG-CLEANING service stopped")
    sys.exit(0)


if __name__ == "__main__":
    main()
