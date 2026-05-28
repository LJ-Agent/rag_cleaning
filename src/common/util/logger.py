"""Unified logging with Loguru — trace_id for full-link tracing."""
import sys
from loguru import logger


def setup_logging(level: str = "INFO", log_format: str | None = None):
    """Configure Loguru with structured format and trace_id context."""
    logger.remove()

    if log_format is None:
        log_format = (
            "{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | "
            "{extra[trace_id]: <24} | {name}:{function}:{line} | {message}"
        )

    logger.configure(extra={"trace_id": ""})

    logger.add(
        sys.stdout,
        level=level,
        format=log_format,
        colorize=True,
    )
    return logger


def bind_trace_id(trace_id: str = ""):
    """Bind trace_id to log context for full-link traceability."""
    return logger.bind(trace_id=trace_id)


def get_logger():
    """Return configured logger instance."""
    return logger
