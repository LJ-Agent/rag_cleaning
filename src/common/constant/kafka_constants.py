"""Kafka topic constants for the cleaning service."""


class CleaningTopics:
    """Kafka topic names — all cleaning service topics."""

    # ─── Input topics (consumed by cleaning service) ────────

    TASK_SUBMIT = "rag-cleaning-task-submit"  # Task submission entry point

    # Format-specific preprocessing topics
    PDF_PREPROCESS = "rag-cleaning-pdf-preprocess"
    DOCX_PREPROCESS = "rag-cleaning-docx-preprocess"
    XLSX_PREPROCESS = "rag-cleaning-xlsx-preprocess"
    PPTX_PREPROCESS = "rag-cleaning-pptx-preprocess"
    OCR_PREPROCESS = "rag-cleaning-ocr-preprocess"

    # Element processing topics
    ELEMENT_TABLE = "rag-cleaning-element-table"
    ELEMENT_IMAGE = "rag-cleaning-element-image"
    ELEMENT_FORMULA = "rag-cleaning-element-formula"

    # General cleaning input
    GENERAL_CLEANING = "rag-cleaning-general-input"

    # Retry topic
    RETRY = "rag-cleaning-retry"

    # ─── Output topics (produced by cleaning service) ───────

    UNIFIED_INPUT = "rag-cleaning-unified-input"  # Unified Document after preprocessing
    TASK_COMPLETE = "rag-cleaning-complete"
    TASK_FAILED = "rag-cleaning-failed"
    DLQ = "rag-cleaning-dlq"  # Dead letter queue

    # ─── All consume topics ────────────────────────────────

    @classmethod
    def consume_topics(cls) -> list[str]:
        return [
            cls.TASK_SUBMIT,
            cls.PDF_PREPROCESS,
            cls.DOCX_PREPROCESS,
            cls.XLSX_PREPROCESS,
            cls.PPTX_PREPROCESS,
            cls.OCR_PREPROCESS,
            cls.ELEMENT_TABLE,
            cls.ELEMENT_IMAGE,
            cls.ELEMENT_FORMULA,
            cls.GENERAL_CLEANING,
            cls.RETRY,
        ]

    # ─── Format routing ────────────────────────────────────

    FORMAT_TO_TOPIC = {
        "pdf": PDF_PREPROCESS,
        "docx": DOCX_PREPROCESS,
        "xlsx": XLSX_PREPROCESS,
        "pptx": PPTX_PREPROCESS,
        "md": None,  # Markdown skips preprocessing, goes directly to general cleaning
        "txt": None,
        "png": OCR_PREPROCESS,
        "jpg": OCR_PREPROCESS,
        "jpeg": OCR_PREPROCESS,
        "bmp": OCR_PREPROCESS,
        "tiff": OCR_PREPROCESS,
    }

    @classmethod
    def get_format_topic(cls, format_type: str) -> str | None:
        """Get the preprocessing topic for a given format. None means skip preprocessing."""
        return cls.FORMAT_TO_TOPIC.get(format_type.lower())

    # ─── Kafka consumer group ──────────────────────────────

    CONSUMER_GROUP = "rag-cleaning-group"
