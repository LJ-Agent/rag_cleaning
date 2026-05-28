"""Structure fixer — merge broken sentences/paragraphs, fix heading hierarchy, normalize lists."""

import re

from common.config_loader import get_config
from common.models.document import Document, ElementRole, HeadingLevel, TextElement
from common.util.logger import get_logger

logger = get_logger()


class StructureFixer:
    """Correct structural issues in documents after preprocessing.

    Fixes:
    - Broken sentences (split mid-sentence across elements)
    - Split paragraphs (consecutive short paragraphs that should be one)
    - Heading hierarchy gaps (e.g., H1 → H3 without H2)
    - List format normalization
    """

    def __init__(self):
        cfg = get_config()["cleaning"]["structure"]
        self._merge_sentences = cfg.get("merge_broken_sentences", True)
        self._merge_paragraphs = cfg.get("merge_split_paragraphs", True)
        self._fix_headings = cfg.get("fix_heading_hierarchy", True)
        self._normalize_lists = cfg.get("normalize_list_format", True)

    def fix(self, doc: Document) -> Document:
        """Apply all structural fixes to the document."""
        doc.log_stage("structure_fix_start")

        for page in doc.pages:
            text_elements = [e for e in page.elements if isinstance(e, TextElement)]

            if self._merge_sentences:
                text_elements = self._fix_broken_sentences(text_elements)

            if self._merge_paragraphs:
                text_elements = self._fix_split_paragraphs(text_elements)

            if self._fix_headings:
                text_elements = self._fix_heading_hierarchy(text_elements)

            if self._normalize_lists:
                text_elements = self._normalize_list_format(text_elements)

            # Rebuild page elements with non-text elements preserved
            non_text = [e for e in page.elements if not isinstance(e, TextElement)]
            page.elements = self._interleave_elements(page.elements, text_elements, non_text)

        doc.log_stage("structure_fix_done")
        return doc

    def _fix_broken_sentences(self, elements: list[TextElement]) -> list[TextElement]:
        """Merge elements that appear to be continuation of a sentence.

        Detects: elements not ending with sentence-ending punctuation
        followed by elements not starting with a capital/Chinese character.
        """
        if len(elements) < 2:
            return elements

        merged = []
        current = elements[0]

        for next_elem in elements[1:]:
            # Only merge same-role paragraph elements
            if current.role != ElementRole.PARAGRAPH or next_elem.role != ElementRole.PARAGRAPH:
                merged.append(current)
                current = next_elem
                continue

            current_ends_open = self._ends_open(current.text)
            next_starts_continuation = self._starts_continuation(next_elem.text)

            if current_ends_open and next_starts_continuation:
                current.text = current.text.rstrip() + " " + next_elem.text.lstrip()
            else:
                merged.append(current)
                current = next_elem

        merged.append(current)
        return merged

    def _fix_split_paragraphs(self, elements: list[TextElement]) -> list[TextElement]:
        """Merge consecutive short paragraphs that likely belong together."""
        if len(elements) < 2:
            return elements

        merged = []
        current = elements[0]

        for next_elem in elements[1:]:
            if current.role == ElementRole.PARAGRAPH and next_elem.role == ElementRole.PARAGRAPH:
                if len(current.text) < 100 and len(next_elem.text) < 100:
                    current.text = current.text.rstrip() + "\n" + next_elem.text.lstrip()
                    continue

            merged.append(current)
            current = next_elem

        merged.append(current)
        return merged

    def _fix_heading_hierarchy(self, elements: list[TextElement]) -> list[TextElement]:
        """Ensure heading levels don't skip (e.g., H1 → H3 becomes H1 → H2)."""
        prev_level = 0
        for elem in elements:
            if elem.role == ElementRole.HEADING and elem.heading_level:
                current_level = int(elem.heading_level.value[1])  # h1 → 1

                if current_level > prev_level + 1:
                    # Gap found, downgrade to prev+1
                    new_level = prev_level + 1
                    new_h = HeadingLevel(f"h{new_level}")
                    elem.heading_level = new_h
                    logger.debug(f"Heading fixed: {current_level} -> {new_level}")

                prev_level = current_level

        return elements

    def _normalize_list_format(self, elements: list[TextElement]) -> list[TextElement]:
        """Normalize list item markers to consistent format."""
        list_idx = 0
        for elem in elements:
            if elem.role == ElementRole.LIST_ITEM:
                text = elem.text.strip()

                # Normalize numbered items
                num_match = re.match(r"^(\d+)[.)]\s*", text)
                if num_match:
                    list_idx += 1
                    elem.list_marker = f"{list_idx}."
                    elem.text = re.sub(r"^\d+[.)]\s*", "", text)
                else:
                    elem.list_marker = "-"
                    elem.text = re.sub(r"^[-*+]\s*", "", text)
            else:
                list_idx = 0

        return elements

    def _ends_open(self, text: str) -> bool:
        """Check if text ends without sentence-ending punctuation."""
        if not text:
            return False
        sentence_ends = {".", "!", "?", "。", "！", "？", ":", "：", ";", "；", "\n", '"', "'", "”", "»"}
        last_char = text.rstrip()[-1] if text.rstrip() else ""
        return last_char not in sentence_ends

    def _starts_continuation(self, text: str) -> bool:
        """Check if text starts like a continuation (lowercase, no indent marker)."""
        if not text:
            return False
        first_char = text.lstrip()[0] if text.lstrip() else ""
        return first_char.islower() or first_char in ",;，；、。"

    def _interleave_elements(
        self,
        original: list,
        text_elements: list[TextElement],
        non_text: list,
    ) -> list:
        """Reconstruct element list preserving original order where possible."""
        # Simple approach: text elements first, then non-text
        result = list(text_elements)
        for nt in non_text:
            # Try to place near original position based on page_numbers
            result.append(nt)
        return result
