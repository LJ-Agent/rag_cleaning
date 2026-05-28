"""Basic text cleaner — whitespace, duplicates, punctuation, encoding fixes."""

import re

from common.config_loader import get_config
from common.models.document import Document, ElementRole, TextElement
from common.util.logger import get_logger

logger = get_logger()


class BasicCleaner:
    """Fundamental text-level cleaning operations.

    All operations are order-independent and idempotent.
    """

    def __init__(self):
        cfg = get_config()["cleaning"]["basic"]
        self._remove_empty_lines = cfg.get("remove_empty_lines", True)
        self._remove_duplicate_lines = cfg.get("remove_duplicate_lines", True)
        self._normalize_punctuation = cfg.get("normalize_punctuation", True)
        self._normalize_newlines = cfg.get("normalize_newlines", True)
        self._fix_encoding = cfg.get("fix_encoding", True)
        self._max_consecutive_newlines = cfg.get("max_consecutive_newlines", 2)

    def clean(self, doc: Document) -> Document:
        """Apply all basic cleaning rules to the document."""
        doc.log_stage("basic_cleaning_start")

        for page in doc.pages:
            for element in page.elements:
                if isinstance(element, TextElement):
                    element.text = self._clean_text(element.text)

            # Also clean page-level text
            page.text_content = self._clean_text(page.text_content)

        doc.log_stage("basic_cleaning_done")
        return doc

    def _clean_text(self, text: str) -> str:
        """Apply all basic cleaning rules to a text string."""
        if not text:
            return text

        if self._fix_encoding:
            text = self._fix_encoding_issues(text)

        if self._normalize_punctuation:
            text = self._normalize_punct(text)

        if self._remove_duplicate_lines:
            text = self._remove_dup_lines(text)

        if self._remove_empty_lines:
            text = self._remove_blank_lines(text)

        if self._normalize_newlines:
            text = self._normalize_nl(text)

        return text.strip()

    def _fix_encoding_issues(self, text: str) -> str:
        """Fix common encoding artifacts."""
        # Replace common mojibake patterns
        replacements = {
            "Â": "", "Ã": "", "â": "'", "â€": '"', "â€œ": '"', "â€": '"',
            "ï¿½": "", "Â®": "®", "Â©": "©", "â„¢": "™",
        }
        for bad, good in replacements.items():
            text = text.replace(bad, good)

        # Remove null bytes
        text = text.replace("\x00", "")

        # Remove control characters except common ones
        text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]", "", text)

        return text

    def _normalize_punct(self, text: str) -> str:
        """Normalize punctuation to standard forms."""
        # Full-width to half-width
        text = text.replace("　", " ")  # full-width space
        text = text.replace("，", ",")
        text = text.replace("；", ";")
        text = text.replace("：", ":")
        text = text.replace("（", "(")
        text = text.replace("）", ")")
        text = text.replace("“", '"')
        text = text.replace("”", '"')
        text = text.replace("‘", "'")
        text = text.replace("’", "'")
        text = text.replace("–", "-")
        text = text.replace("—", "--")

        # Multiple punctuation
        text = re.sub(r"[!！]{2,}", "!", text)
        text = re.sub(r"[?？]{2,}", "?", text)
        text = re.sub(r"[.。]{2,}", ".", text)

        return text

    def _remove_dup_lines(self, text: str) -> str:
        """Remove consecutive duplicate lines."""
        lines = text.split("\n")
        result = []
        prev = None
        for line in lines:
            stripped = line.strip()
            if stripped != prev:
                result.append(line)
            prev = stripped
        return "\n".join(result)

    def _remove_blank_lines(self, text: str) -> str:
        """Collapse excessive blank lines."""
        return re.sub(f"\n{{{self._max_consecutive_newlines + 1},}}", "\n" * self._max_consecutive_newlines, text)

    def _normalize_nl(self, text: str) -> str:
        """Normalize line endings and trim per-line whitespace."""
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        text = re.sub(r"[ \t]+$", "", text, flags=re.MULTILINE)  # trailing whitespace
        return text
