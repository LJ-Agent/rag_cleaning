"""Sensitive data masker — detect and mask PII in document content."""

import re

from common.config_loader import get_config
from common.models.document import Document, TextElement
from common.util.logger import get_logger

logger = get_logger()


class SensitiveMasker:
    """Detect and mask personally identifiable information (PII) in documents.

    Supports:
    - Chinese Mainland phone numbers (mobile + landline)
    - Chinese ID card numbers (18-digit)
    - Bank card numbers (16-19 digits)
    - Email addresses
    - IP addresses (optional)
    """

    def __init__(self):
        cfg = get_config()["cleaning"]["sensitive"]
        self._enabled = cfg.get("enabled", True)
        self._mask_phone = cfg.get("mask_phone", True)
        self._mask_id_card = cfg.get("mask_id_card", True)
        self._mask_bank_card = cfg.get("mask_bank_card", True)
        self._mask_email = cfg.get("mask_email", True)
        self._mask_ip = cfg.get("mask_ip", False)
        self._strategy = cfg.get("mask_strategy", "replace")
        self._placeholder = cfg.get("mask_placeholder", "***")

        # Pre-compiled patterns
        self._patterns: list[tuple[str, re.Pattern]] = []

        if self._mask_phone:
            # Chinese mobile phone numbers
            self._patterns.append(("phone", re.compile(r"\b1[3-9]\d{9}\b")))
            # Chinese landline numbers
            self._patterns.append(("phone", re.compile(r"\b0\d{2,3}[-]?\d{7,8}\b")))

        if self._mask_id_card:
            self._patterns.append(("id_card", re.compile(r"\b[1-9]\d{5}(?:19|20)\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])\d{3}[\dXx]\b")))

        if self._mask_bank_card:
            self._patterns.append(("bank_card", re.compile(r"\b\d{16,19}\b")))

        if self._mask_email:
            self._patterns.append(("email", re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")))

        if self._mask_ip:
            self._patterns.append(("ip", re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")))

    def mask(self, doc: Document) -> Document:
        """Apply masking to all text elements in document."""
        if not self._enabled:
            return doc

        doc.log_stage("sensitive_mask_start")
        total_masked = 0

        for page in doc.pages:
            for element in page.elements:
                if isinstance(element, TextElement):
                    text, count = self._mask_text(element.text)
                    element.text = text
                    total_masked += count

        logger.info(f"Sensitive masker: {total_masked} instances masked")
        doc.log_stage("sensitive_mask_done")
        return doc

    def _mask_text(self, text: str) -> tuple[str, int]:
        """Apply all enabled patterns to text. Returns (masked_text, count_masked)."""
        count = 0
        for label, pattern in self._patterns:
            matches = pattern.findall(text)
            count += len(matches)
            text = pattern.sub(self._get_replacement(label), text)
        return text, count

    def _get_replacement(self, label: str) -> str:
        """Generate replacement string based on masking strategy."""
        if self._strategy == "remove":
            return ""
        elif self._strategy == "hash":
            return f"[{label}_hashed]"
        else:  # replace
            return f"[{label}{self._placeholder}]"
