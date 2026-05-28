"""Unified response wrapper — aligned with Java Result<T> format."""

import time
from dataclasses import dataclass, field
from typing import Generic, TypeVar

T = TypeVar("T")


@dataclass
class Result(Generic[T]):
    """Unified API response, identical structure to com.rag.common.result.Result."""

    code: int = 0
    message: str = "success"
    data: T | None = None
    timestamp: int = field(default_factory=lambda: int(time.time() * 1000))

    @staticmethod
    def success(data: T | None = None) -> "Result[T]":
        return Result(code=0, message="success", data=data)

    @staticmethod
    def fail(code: int, message: str) -> "Result":
        return Result(code=code, message=message, data=None)


@dataclass
class ResultCode:
    """Error code marker, aligned with Java ResultCode interface."""

    code: int
    message: str


class ResultCodeEnum:
    """All error codes aligned with Java ResultCodeEnum."""

    SUCCESS = ResultCode(0, "成功")
    PARAM_ERROR = ResultCode(400, "参数错误")
    UNAUTHORIZED = ResultCode(401, "未授权")
    FORBIDDEN = ResultCode(403, "无权限")
    NOT_FOUND = ResultCode(404, "资源不存在")
    METHOD_NOT_ALLOWED = ResultCode(405, "请求方法不支持")
    CONFLICT = ResultCode(409, "资源冲突")
    RATE_LIMIT = ResultCode(429, "请求过于频繁")
    SYSTEM_ERROR = ResultCode(500, "系统内部错误")
    SERVICE_UNAVAILABLE = ResultCode(503, "服务不可用")

    # Business error codes (10000+)
    FILE_UPLOAD_ERROR = ResultCode(10001, "文件上传失败")
    FILE_NOT_FOUND = ResultCode(10002, "文件不存在")
    FILE_DUPLICATE = ResultCode(10003, "文件已存在")
    FILE_TYPE_NOT_SUPPORTED = ResultCode(10004, "不支持的文件类型")
    FILE_SIZE_EXCEEDED = ResultCode(10005, "文件大小超出限制")

    # Cleaning-specific error codes (10700+)
    PREPROCESSING_ERROR = ResultCode(10701, "格式预处理失败")
    ELEMENT_PROCESSING_ERROR = ResultCode(10702, "元素处理失败")
    CLEANING_RULE_ERROR = ResultCode(10703, "清洗规则执行失败")
    QUALITY_BELOW_THRESHOLD = ResultCode(10704, "质量评分不达标")
    UNSUPPORTED_FORMAT = ResultCode(10705, "不支持的文件格式")

    # Infrastructure
    GRPC_CALL_ERROR = ResultCode(10601, "gRPC调用失败")
    KAFKA_SEND_ERROR = ResultCode(10602, "Kafka消息发送失败")
