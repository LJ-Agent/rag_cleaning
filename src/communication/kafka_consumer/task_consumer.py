"""Kafka task consumer — consumes cleaning tasks from multiple topics."""

import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from kafka import KafkaConsumer, TopicPartition

from common.config_loader import get_config
from common.constant.kafka_constants import CleaningTopics
from common.models.document import CleaningTask, KafkaTaskMessage
from common.util.logger import bind_trace_id, get_logger

logger = get_logger()


class CleaningTaskConsumer:
    """Kafka consumer for cleaning task topics.

    Consumes from all cleaning-specific topics and dispatches
    tasks to the appropriate stage handler.
    """

    def __init__(self, dispatcher: "TaskDispatcher | None" = None):
        cfg = get_config()["kafka"]
        self._bootstrap = cfg["bootstrap_servers"]
        self._group = cfg["consumer_group"]
        self._consumer_cfg = cfg.get("consumer", {})
        self._topics = CleaningTopics.consume_topics()

        self._dispatcher = dispatcher
        self._consumer: KafkaConsumer | None = None
        self._running = False
        self._thread: threading.Thread | None = None
        self._committed: dict[tuple[str, int], int] = {}  # (topic, partition) -> offset

        # Handlers per topic
        self._topic_handlers: dict[str, callable] = {}

    def register_handler(self, topic: str, handler: callable):
        """Register a handler function for a specific topic."""
        self._topic_handlers[topic] = handler

    def start(self):
        """Start the Kafka consumer loop in a background thread."""
        self._consumer = KafkaConsumer(
            bootstrap_servers=self._bootstrap,
            group_id=self._group,
            auto_offset_reset=self._consumer_cfg.get("auto_offset_reset", "earliest"),
            enable_auto_commit=self._consumer_cfg.get("enable_auto_commit", False),
            max_poll_records=self._consumer_cfg.get("max_poll_records", 10),
            session_timeout_ms=self._consumer_cfg.get("session_timeout_ms", 30000),
            value_deserializer=lambda v: v.decode("utf-8") if v else "",
        )

        # Manual partition assignment for KRaft compatibility
        all_tps = []
        for topic in self._topics:
            try:
                partitions = self._consumer.partitions_for_topic(topic)
                if partitions:
                    for p in partitions:
                        all_tps.append(TopicPartition(topic, p))
            except Exception as e:
                logger.warning(f"Cannot get partitions for topic {topic}: {e}")

        if all_tps:
            self._consumer.assign(all_tps)
            logger.info(f"Consumer assigned {len(all_tps)} partitions across {len(self._topics)} topics")
        else:
            self._consumer.subscribe(self._topics)
            logger.info(f"Consumer subscribed to {len(self._topics)} topics")

        self._running = True
        self._thread = threading.Thread(target=self._poll_loop, name="cleaning-consumer", daemon=True)
        self._thread.start()
        logger.info("Cleaning task consumer started")

    def stop(self):
        """Stop the consumer gracefully."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=10)
        if self._consumer:
            self._consumer.close()
        logger.info("Cleaning task consumer stopped")

    def _poll_loop(self):
        """Main poll loop running in background thread."""
        while self._running:
            try:
                records = self._consumer.poll(timeout_ms=1000, max_records=10)
                for tp, batch in records.items():
                    for msg in batch:
                        try:
                            self._process_message(msg, tp.topic, tp.partition, msg.offset)
                        except Exception as e:
                            logger.error(f"Message processing error: {e}")
                            self._commit_offset(tp.topic, tp.partition, msg.offset)
            except Exception as e:
                logger.error(f"Consumer poll error: {e}")
                time.sleep(1)

    def _process_message(self, msg, topic: str, partition: int, offset: int):
        """Parse and dispatch a single Kafka message."""
        try:
            raw = json.loads(msg.value)
        except json.JSONDecodeError:
            logger.error(f"Invalid JSON in Kafka message: {topic}[{partition}]@{offset}")
            self._commit_offset(topic, partition, offset)
            return

        task_msg = KafkaTaskMessage.from_json(raw)
        log = bind_trace_id(task_msg.task_id)

        if not task_msg.task_id or not task_msg.document_id:
            logger.error(f"Invalid task message (missing task_id/document_id): {topic}")
            self._commit_offset(topic, partition, offset)
            return

        logger.info(f"Received task: {task_msg.task_id} (type={task_msg.task_type}, topic={topic})")

        # Dispatch to registered handler
        handler = self._topic_handlers.get(topic)
        if handler:
            try:
                handler(task_msg, topic, partition, offset)
            except Exception as e:
                logger.error(f"Handler error for task {task_msg.task_id}: {e}")
                self._commit_offset(topic, partition, offset)
        else:
            logger.warning(f"No handler registered for topic: {topic}")
            self._commit_offset(topic, partition, offset)

    def _commit_offset(self, topic: str, partition: int, offset: int):
        """Commit offset with deduplication."""
        key = (topic, partition)
        if self._committed.get(key, -1) >= offset + 1:
            return

        try:
            tp = TopicPartition(topic, partition)
            self._consumer.commit({tp: offset + 1})
            self._committed[key] = offset + 1
        except Exception as e:
            logger.error(f"Offset commit failed: {topic}[{partition}] — {e}")
