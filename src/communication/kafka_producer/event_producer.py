"""Kafka event producer — sends cleaning task status and completion events."""

import json

from kafka import KafkaProducer

from common.config_loader import get_config
from common.constant.kafka_constants import CleaningTopics
from common.exception.exceptions import ResourceException
from common.models.document import CleaningEvent
from common.util.logger import get_logger
from common.util.utils import json_dumps, now_iso

logger = get_logger()


class CleaningEventProducer:
    """Produces cleaning pipeline events to Kafka.

    Output topics:
    - rag-cleaning-unified-input (document after preprocessing)
    - rag-cleaning-element-{type} (routed to element processors)
    - rag-cleaning-general-input (routed to general cleaning)
    - rag-cleaning-complete (final success)
    - rag-cleaning-failed (failure)
    - rag-cleaning-dlq (dead letter queue)
    """

    def __init__(self):
        cfg = get_config()["kafka"]
        producer_cfg = cfg.get("producer", {})
        self._producer = KafkaProducer(
            bootstrap_servers=cfg["bootstrap_servers"],
            acks=producer_cfg.get("acks", 1),
            retries=producer_cfg.get("retries", 3),
            linger_ms=producer_cfg.get("linger_ms", 5),
            value_serializer=lambda v: json.dumps(v, ensure_ascii=False).encode("utf-8") if isinstance(v, dict) else v,
        )

    def send_unified_document(self, task_msg_dict: dict):
        """Send document to unified input topic (post-preprocessing)."""
        self._send(CleaningTopics.UNIFIED_INPUT, task_msg_dict)

    def send_for_element_processing(self, element_type: str, task_msg_dict: dict):
        """Route to element-specific topic."""
        topic = getattr(CleaningTopics, f"ELEMENT_{element_type.upper()}", None)
        if topic:
            self._send(topic, task_msg_dict)
        else:
            logger.warning(f"No element topic for type: {element_type}")

    def send_for_general_cleaning(self, task_msg_dict: dict):
        """Send to general cleaning input topic."""
        self._send(CleaningTopics.GENERAL_CLEANING, task_msg_dict)

    def send_complete(self, event: CleaningEvent):
        """Send task completion event."""
        self._send(CleaningTopics.TASK_COMPLETE, event.to_json(), key=event.task_id)

    def send_failed(self, event: CleaningEvent):
        """Send task failure event."""
        self._send(CleaningTopics.TASK_FAILED, event.to_json(), key=event.task_id)

    def send_to_dlq(self, event: CleaningEvent):
        """Send to dead letter queue."""
        self._send(CleaningTopics.DLQ, event.to_json(), key=event.task_id)

    def send_retry(self, task_msg_dict: dict):
        """Send to retry topic for delayed reprocessing."""
        self._send(CleaningTopics.RETRY, task_msg_dict)

    def _send(self, topic: str, payload: dict, key: str | None = None):
        """Send message to Kafka topic with error handling."""
        try:
            key_bytes = key.encode("utf-8") if key else None
            self._producer.send(topic, value=payload, key=key_bytes)
            self._producer.flush()
            logger.debug(f"Event sent to {topic}: {key or 'no-key'}")
        except Exception as e:
            raise ResourceException(f"Kafka send failed to {topic}: {e}")

    def close(self):
        """Close the producer."""
        self._producer.close()


_event_producer: CleaningEventProducer | None = None


def get_event_producer() -> CleaningEventProducer:
    global _event_producer
    if _event_producer is None:
        _event_producer = CleaningEventProducer()
    return _event_producer
