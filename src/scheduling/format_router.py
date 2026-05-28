"""Format router — dispatches tasks to format-specific preprocessing topics."""

from common.config_loader import get_config
from common.constant.kafka_constants import CleaningTopics
from common.exception.exceptions import UnsupportedFormatException
from common.util.logger import get_logger
from common.util.utils import get_file_extension

logger = get_logger()


class FormatRouter:
    """Route cleaning tasks to the appropriate format preprocessing topic.

    Routing rules (configurable via settings.yaml):
    - PDF → rag-cleaning-pdf-preprocess
    - DOCX → rag-cleaning-docx-preprocess
    - XLSX → rag-cleaning-xlsx-preprocess
    - PPTX → rag-cleaning-pptx-preprocess
    - Images (PNG/JPG/etc.) → rag-cleaning-ocr-preprocess
    - MD/TXT → No preprocessing, directly to general cleaning
    - Unsupported → Dead letter queue
    """

    def __init__(self):
        cfg = get_config()["file"]
        self._supported_types = set(cfg.get("supported_types", []))
        self._mime_to_format = cfg.get("mime_to_format", {})

    def route(self, file_name: str, mime_type: str = "") -> str | None:
        """Determine the preprocessing topic for a given file.

        Returns:
            Topic name string, or None if no preprocessing is needed (MD/TXT).
            Raises UnsupportedFormatException for unsupported types.
        """
        ext = get_file_extension(file_name)

        # Determine format from extension (primary) or MIME type (fallback)
        format_type = ext
        if ext not in self._supported_types and mime_type:
            format_type = self._mime_to_format.get(mime_type, ext)

        if format_type not in self._supported_types:
            raise UnsupportedFormatException(
                f"Unsupported file format: {ext} (MIME: {mime_type})",
                format_type=ext,
            )

        # Get target topic
        topic = CleaningTopics.get_format_topic(format_type)

        if topic:
            logger.info(f"Routing {file_name} ({format_type}) → {topic}")
        else:
            logger.info(f"Routing {file_name} ({format_type}) → direct (no preprocessing)")

        return topic

    def is_supported(self, file_name: str, mime_type: str = "") -> bool:
        """Check if file format is supported."""
        ext = get_file_extension(file_name)
        return ext in self._supported_types or mime_type in self._mime_to_format

    def get_supported_formats(self) -> list[str]:
        return sorted(self._supported_types)
