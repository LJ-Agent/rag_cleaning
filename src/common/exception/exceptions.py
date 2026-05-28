"""Custom exception hierarchy for the cleaning service."""


class CleaningException(Exception):
    """Base cleaning service exception."""

    def __init__(self, code: int, message: str, task_id: str | None = None):
        self.code = code
        self.message = message
        self.task_id = task_id
        super().__init__(message)


class PreprocessingException(CleaningException):
    """Format preprocessing failure (single format isolation)."""

    def __init__(self, message: str, format_type: str | None = None, task_id: str | None = None):
        self.format_type = format_type
        super().__init__(code=10701, message=message, task_id=task_id)


class ElementProcessingException(CleaningException):
    """Element processing failure (table/image/formula)."""

    def __init__(self, message: str, element_type: str | None = None, task_id: str | None = None):
        self.element_type = element_type
        super().__init__(code=10702, message=message, task_id=task_id)


class CleaningRuleException(CleaningException):
    """Cleaning rule execution failure."""

    def __init__(self, message: str, rule_name: str | None = None, task_id: str | None = None):
        self.rule_name = rule_name
        super().__init__(code=10703, message=message, task_id=task_id)


class QualityValidationException(CleaningException):
    """Quality score below threshold."""

    def __init__(self, message: str, score: float = 0.0, task_id: str | None = None):
        self.score = score
        super().__init__(code=10704, message=message, task_id=task_id)


class UnsupportedFormatException(CleaningException):
    """File format not supported."""

    def __init__(self, message: str, format_type: str | None = None):
        self.format_type = format_type
        super().__init__(code=10705, message=message)


class TaskException(CleaningException):
    """Task execution exception (retryable)."""

    def __init__(self, message: str, task_id: str | None = None, retryable: bool = True):
        self.retryable = retryable
        super().__init__(code=500, message=message, task_id=task_id)


class ResourceException(CleaningException):
    """Infrastructure resource exception (MinIO, Redis, Kafka unavailable)."""

    def __init__(self, message: str, task_id: str | None = None):
        super().__init__(code=500, message=message, task_id=task_id)


class ValidationException(CleaningException):
    """Request validation exception."""

    def __init__(self, message: str):
        super().__init__(code=400, message=message)
