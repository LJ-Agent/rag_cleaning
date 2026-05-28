"""Cleaning service status enums — task lifecycle and cleaning stages."""
from enum import Enum


class CleaningTaskStatus(str, Enum):
    """Task status state machine for cleaning service."""

    PENDING = "PENDING"
    ROUTING = "ROUTING"
    PREPROCESSING = "PREPROCESSING"
    ELEMENT_PROCESSING = "ELEMENT_PROCESSING"
    CLEANING = "CLEANING"
    VALIDATING = "VALIDATING"
    GENERATING_OUTPUT = "GENERATING_OUTPUT"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    RETRYING = "RETRYING"

    @property
    def description(self) -> str:
        return {
            CleaningTaskStatus.PENDING: "等待处理",
            CleaningTaskStatus.ROUTING: "路由分发中",
            CleaningTaskStatus.PREPROCESSING: "格式预处理中",
            CleaningTaskStatus.ELEMENT_PROCESSING: "元素处理中",
            CleaningTaskStatus.CLEANING: "通用清洗中",
            CleaningTaskStatus.VALIDATING: "质量校验中",
            CleaningTaskStatus.GENERATING_OUTPUT: "生成输出中",
            CleaningTaskStatus.SUCCESS: "清洗成功",
            CleaningTaskStatus.FAILED: "清洗失败",
            CleaningTaskStatus.RETRYING: "重试中",
        }[self]

    @property
    def next_states(self) -> set["CleaningTaskStatus"]:
        _transitions = {
            CleaningTaskStatus.PENDING: {CleaningTaskStatus.ROUTING},
            CleaningTaskStatus.ROUTING: {CleaningTaskStatus.PREPROCESSING, CleaningTaskStatus.FAILED},
            CleaningTaskStatus.PREPROCESSING: {CleaningTaskStatus.ELEMENT_PROCESSING, CleaningTaskStatus.CLEANING, CleaningTaskStatus.FAILED},
            CleaningTaskStatus.ELEMENT_PROCESSING: {CleaningTaskStatus.CLEANING, CleaningTaskStatus.FAILED},
            CleaningTaskStatus.CLEANING: {CleaningTaskStatus.VALIDATING, CleaningTaskStatus.FAILED},
            CleaningTaskStatus.VALIDATING: {CleaningTaskStatus.GENERATING_OUTPUT, CleaningTaskStatus.FAILED},
            CleaningTaskStatus.GENERATING_OUTPUT: {CleaningTaskStatus.SUCCESS, CleaningTaskStatus.FAILED},
            CleaningTaskStatus.SUCCESS: set(),
            CleaningTaskStatus.FAILED: {CleaningTaskStatus.RETRYING},
            CleaningTaskStatus.RETRYING: {CleaningTaskStatus.ROUTING, CleaningTaskStatus.FAILED},
        }
        return _transitions.get(self, set())

    def can_transit_to(self, target: "CleaningTaskStatus") -> bool:
        return target in self.next_states

    def is_terminal(self) -> bool:
        return not self.next_states

    def is_retryable(self) -> bool:
        return self in {
            CleaningTaskStatus.FAILED,
            CleaningTaskStatus.PREPROCESSING,
            CleaningTaskStatus.ELEMENT_PROCESSING,
            CleaningTaskStatus.CLEANING,
            CleaningTaskStatus.VALIDATING,
            CleaningTaskStatus.GENERATING_OUTPUT,
        }


class CleaningStage(str, Enum):
    """Processing stages within the cleaning pipeline."""

    FORMAT_PREPROCESSING = "format_preprocessing"
    TABLE_PROCESSING = "table_processing"
    IMAGE_PROCESSING = "image_processing"
    FORMULA_PROCESSING = "formula_processing"
    BASIC_CLEANING = "basic_cleaning"
    CONTENT_FILTERING = "content_filtering"
    STRUCTURE_FIXING = "structure_fixing"
    SENSITIVE_MASKING = "sensitive_masking"
    QUALITY_VALIDATION = "quality_validation"
    MARKDOWN_GENERATION = "markdown_generation"
    METADATA_GENERATION = "metadata_generation"


class TaskPriority(str, Enum):
    """Task priority levels for scheduling."""

    HIGH = "high"
    NORMAL = "normal"
    LOW = "low"

    @property
    def weight(self) -> int:
        return {TaskPriority.HIGH: 0, TaskPriority.NORMAL: 1, TaskPriority.LOW: 2}[self]


class ElementType(str, Enum):
    """Element types for the common processing engine."""

    TABLE = "table"
    IMAGE = "image"
    FORMULA = "formula"
    TEXT = "text"
    LIST = "list"
    HEADING = "heading"
    CODE_BLOCK = "code_block"
    QUOTE = "quote"
    HYPERLINK = "hyperlink"
