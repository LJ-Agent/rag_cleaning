"""Utility functions — MD5, JSON, text processing."""
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def md5_file(file_path: str | Path) -> str:
    """Compute MD5 digest of a file (streaming, aligned with Java Md5Util)."""
    md5 = hashlib.md5()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            md5.update(chunk)
    return md5.hexdigest()


def md5_bytes(data: bytes) -> str:
    """Compute MD5 digest of bytes."""
    return hashlib.md5(data).hexdigest()


def md5_text(text: str) -> str:
    """Compute MD5 digest of text (used for element dedup)."""
    return hashlib.md5(text.encode("utf-8")).hexdigest()


def json_dumps(obj: Any) -> str:
    """Serialize to JSON string with datetime support."""

    def default(o):
        if isinstance(o, datetime):
            return o.isoformat()
        raise TypeError(f"Object of type {type(o)} is not JSON serializable")

    return json.dumps(obj, ensure_ascii=False, default=default)


def json_loads(s: str) -> Any:
    """Deserialize JSON string."""
    return json.loads(s)


def now_iso() -> str:
    """Return current UTC timestamp in ISO 8601 format."""
    return datetime.now(timezone.utc).isoformat()


def format_datetime(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def get_file_extension(filename: str) -> str:
    """Extract lowercase file extension without dot."""
    return Path(filename).suffix.lower().lstrip(".")


def get_mime_type(filename: str) -> str:
    """Guess MIME type from file extension."""
    ext = get_file_extension(filename)
    mapping = {
        "pdf": "application/pdf",
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "md": "text/markdown",
        "txt": "text/plain",
        "png": "image/png",
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "bmp": "image/bmp",
        "tiff": "image/tiff",
    }
    return mapping.get(ext, "application/octet-stream")


def clean_text(text: str) -> str:
    """Normalize whitespace, newlines, and trim."""
    text = re.sub(r"\r\n|\r", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r"^\s+|\s+$", "", text, flags=re.MULTILINE)
    return text.strip()


def truncate_text(text: str, max_len: int = 200) -> str:
    """Truncate text with ellipsis."""
    if len(text) <= max_len:
        return text
    return text[:max_len] + "..."


def validate_file_type(filename: str, supported: set[str] | None = None) -> bool:
    """Check if file extension is in the supported set."""
    if supported is None:
        supported = {"pdf", "docx", "xlsx", "pptx", "md", "txt", "png", "jpg", "jpeg", "bmp", "tiff"}
    ext = get_file_extension(filename)
    return ext in supported


def is_image_file(filename: str) -> bool:
    """Check if file is an image based on extension."""
    return get_file_extension(filename) in {"png", "jpg", "jpeg", "bmp", "tiff", "gif", "webp"}


def normalize_punctuation(text: str) -> str:
    """Normalize Chinese/English punctuation to standard forms."""
    # Full-width to half-width for common punctuation
    text = text.replace("　", " ")  # full-width space
    text = text.replace("，", ",")  # ，
    text = text.replace("；", ";")  # ；
    text = text.replace("：", ":")  # ：
    text = text.replace("（", "(")  # （
    text = text.replace("）", ")")  # ）
    return text
