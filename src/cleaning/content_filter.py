"""Content filter — remove headers/footers, page numbers, watermarks, ads, legal notices."""

import re

from common.config_loader import get_config
from common.models.document import Document, ElementRole, TextElement
from common.util.logger import get_logger

logger = get_logger()


class ContentFilter:
    """Filter out non-content elements from documents.

    Uses pattern-based rules to identify and remove:
    - Page headers and footers
    - Page numbers
    - Watermarks
    - Advertisements
    - Copyright/legal boilerplate
    """

    def __init__(self):
        cfg = get_config()["cleaning"]["content_filter"]
        self._remove_headers_footers = cfg.get("remove_headers_footers", True)
        self._remove_page_numbers = cfg.get("remove_page_numbers", True)
        self._remove_watermarks = cfg.get("remove_watermarks", True)
        self._remove_ads = cfg.get("remove_ads", False)
        self._remove_legal = cfg.get("remove_legal_notices", True)
        self._remove_copyright = cfg.get("remove_copyright", True)

        # Pre-compiled patterns
        self._page_num_pattern = re.compile(
            r"^\s*(page\s*\d+|第\s*\d+\s*页|-\s*\d+\s*-|\d+\s*/\s*\d+)\s*$",
            re.IGNORECASE,
        )
        self._copyright_pattern = re.compile(
            r"(copyright\s*©?|©|版权(所有)?|all\s*rights?\s*reserved)",
            re.IGNORECASE,
        )
        self._legal_pattern = re.compile(
            r"(免责声明|disclaimer|terms\s*of\s*(use|service)|法律声明|"
            r"未经.*许可.*不得|confidential|机密)",
            re.IGNORECASE,
        )
        self._watermark_patterns = [
            re.compile(r"(草稿|draft|机密|confidential|内部|internal|样本|sample)", re.IGNORECASE),
        ]
        self._header_footer_indicators = [
            # Short lines that look like navigation elements
            lambda t: len(t.strip()) < 4 and t.strip().isdigit(),
            lambda t: re.match(r"^\d+$", t.strip()),
        ]

    def filter(self, doc: Document) -> Document:
        """Apply all content filters to the document."""
        doc.log_stage("content_filter_start")
        removed_count = 0

        for page in doc.pages:
            kept_elements = []

            for element in page.elements:
                if isinstance(element, TextElement):
                    if self._should_remove(element.text):
                        removed_count += 1
                        continue

                    # Filter the text itself
                    element.text = self._filter_text(element.text)

                    # Skip empty elements after filtering
                    if not element.text.strip():
                        removed_count += 1
                        continue

                kept_elements.append(element)

            page.elements = kept_elements

        logger.info(f"Content filter: removed {removed_count} elements")
        doc.log_stage("content_filter_done")
        return doc

    def _should_remove(self, text: str) -> bool:
        """Determine if text element should be entirely removed."""
        text_stripped = text.strip()
        if not text_stripped:
            return True

        # Page numbers
        if self._remove_page_numbers and self._page_num_pattern.match(text_stripped):
            return True

        # Watermarks (only remove if text is JUST a watermark)
        if self._remove_watermarks:
            for pattern in self._watermark_patterns:
                if pattern.search(text_stripped) and len(text_stripped) < 30:
                    return True

        # Header/footer detection (short lines that are likely nav elements)
        if self._remove_headers_footers:
            for check in self._header_footer_indicators:
                if check(text_stripped):
                    return True

        return False

    def _filter_text(self, text: str) -> str:
        """Apply inline filtering to text (remove matching parts but keep rest)."""
        # Remove copyright notices
        if self._remove_copyright:
            text = self._copyright_pattern.sub("", text)

        # Remove legal boilerplate
        if self._remove_legal:
            text = self._legal_pattern.sub("", text)

        return text.strip()
