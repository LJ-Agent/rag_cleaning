"""Quality validator — 4-dimension scoring: completeness, purity, structure, coherence."""

import re

from common.config_loader import get_config
from common.models.document import Document, QualityIssue, QualityReport
from common.util.logger import get_logger

logger = get_logger()


class QualityValidator:
    """Evaluate cleaned document quality across 4 dimensions.

    Scoring dimensions:
    1. Completeness: text length, content coverage
    2. Purity: noise ratio, unwanted elements
    3. Structure: heading density, element organization
    4. Coherence: sentence length, readability
    """

    def __init__(self):
        cfg = get_config()["quality"]
        self._enabled = cfg.get("enabled", True)
        self._pass_threshold = cfg.get("pass_threshold", 0.6)
        self._warn_threshold = cfg.get("warn_threshold", 0.4)

        dims = cfg.get("dimensions", {})
        self._completeness_weight = dims.get("completeness", {}).get("weight", 0.3)
        self._min_text_length = dims.get("completeness", {}).get("min_text_length", 50)

        self._purity_weight = dims.get("purity", {}).get("weight", 0.25)
        self._max_noise_ratio = dims.get("purity", {}).get("max_noise_ratio", 0.2)

        self._structure_weight = dims.get("structure", {}).get("weight", 0.25)
        self._min_heading_density = dims.get("structure", {}).get("min_heading_density", 0.01)

        self._coherence_weight = dims.get("coherence", {}).get("weight", 0.2)
        self._min_avg_sentence_length = dims.get("coherence", {}).get("min_avg_sentence_length", 5)

    def validate(self, doc: Document) -> QualityReport:
        """Compute quality scores for document. Returns QualityReport with passed/failed flag."""
        if not self._enabled:
            return QualityReport(overall_score=1.0, passed=True)

        doc.log_stage("quality_validation_start")

        issues: list[QualityIssue] = []

        completeness = self._score_completeness(doc, issues)
        purity = self._score_purity(doc, issues)
        structure = self._score_structure(doc, issues)
        coherence = self._score_coherence(doc, issues)

        overall = (
            completeness * self._completeness_weight
            + purity * self._purity_weight
            + structure * self._structure_weight
            + coherence * self._coherence_weight
        )

        passed = overall >= self._pass_threshold

        report = QualityReport(
            overall_score=round(overall, 4),
            completeness=round(completeness, 4),
            purity=round(purity, 4),
            structure=round(structure, 4),
            coherence=round(coherence, 4),
            issues=issues,
            passed=passed,
        )

        if not passed:
            logger.warning(f"Quality FAIL: {report.summary()}")
        else:
            logger.info(f"Quality PASS: {report.summary()}")

        doc.quality = report
        doc.log_stage("quality_validation_done")
        return report

    def _score_completeness(self, doc: Document, issues: list[QualityIssue]) -> float:
        """Score text completeness based on length and content coverage."""
        total_text = ""
        for page in doc.pages:
            total_text += page.text_content

        if len(total_text) < self._min_text_length:
            issues.append(QualityIssue(
                dimension="completeness",
                level="ERROR",
                description=f"Document text too short ({len(total_text)} chars, min {self._min_text_length})",
            ))
            return 0.0

        # Score based on text length: log scale, max at ~50000 chars
        score = min(1.0, len(total_text) / 50000.0)
        score = max(0.2, score)  # Minimum 0.2 if above length threshold

        # Check for page-level content coverage
        empty_pages = sum(1 for p in doc.pages if not p.text_content.strip())
        if empty_pages > 0:
            ratio = empty_pages / max(len(doc.pages), 1)
            score -= ratio * 0.3
            if ratio > 0.5:
                issues.append(QualityIssue(
                    dimension="completeness",
                    level="WARNING",
                    description=f"{empty_pages}/{len(doc.pages)} pages are empty",
                ))

        return max(0.0, min(1.0, score))

    def _score_purity(self, doc: Document, issues: list[QualityIssue]) -> float:
        """Score content purity: low noise, high signal."""
        score = 1.0

        total_elements = sum(len(p.elements) for p in doc.pages)
        if total_elements == 0:
            return 0.0

        # Check for noise indicators
        noise_count = 0
        for page in doc.pages:
            for elem in page.elements:
                text = getattr(elem, "text", "")
                if not text:
                    noise_count += 1
                    continue

                # High ratio of special characters to text = noise
                special_ratio = sum(1 for c in text if not c.isalnum() and not c.isspace()) / max(len(text), 1)
                if special_ratio > 0.5:
                    noise_count += 1

        noise_ratio = noise_count / max(total_elements, 1)
        score -= noise_ratio

        if noise_ratio > self._max_noise_ratio:
            issues.append(QualityIssue(
                dimension="purity",
                level="WARNING",
                description=f"Noise ratio {noise_ratio:.2f} exceeds threshold {self._max_noise_ratio}",
            ))

        return max(0.0, min(1.0, score))

    def _score_structure(self, doc: Document, issues: list[QualityIssue]) -> float:
        """Score document structure quality."""
        score = 0.5

        total_elements = sum(len(p.elements) for p in doc.pages)
        if total_elements == 0:
            return 0.0

        # Count headings
        from common.models.document import ElementRole
        heading_count = 0
        for page in doc.pages:
            for elem in page.elements:
                if hasattr(elem, "role") and elem.role == ElementRole.HEADING:
                    heading_count += 1

        heading_density = heading_count / max(total_elements, 1)

        # Good heading density: 0.05-0.2
        if 0.02 <= heading_density <= 0.3:
            score += 0.3
        elif heading_density < self._min_heading_density:
            score -= 0.2
            if total_elements > 20:
                issues.append(QualityIssue(
                    dimension="structure",
                    level="WARNING",
                    description=f"Low heading density ({heading_density:.3f}), document may lack structure",
                ))

        # Check for element variety (good structure has mix of types)
        element_types = set()
        for page in doc.pages:
            for elem in page.elements:
                element_types.add(type(elem).__name__)
        if len(element_types) >= 3:
            score += 0.2
        elif len(element_types) >= 2:
            score += 0.1

        return max(0.0, min(1.0, score))

    def _score_coherence(self, doc: Document, issues: list[QualityIssue]) -> float:
        """Score semantic coherence based on sentence analysis."""
        score = 0.5

        all_sentences = []
        for page in doc.pages:
            text = page.text_content
            if text:
                sentences = re.split(r"[.!?。!?;；\n]+", text)
                all_sentences.extend(s.strip() for s in sentences if s.strip())

        if not all_sentences:
            return 0.3  # Can't evaluate but not zero

        # Average sentence length
        avg_len = sum(len(s) for s in all_sentences) / len(all_sentences)
        if avg_len >= self._min_avg_sentence_length:
            score += 0.2
        elif avg_len < 3:
            score -= 0.3
            issues.append(QualityIssue(
                dimension="coherence",
                level="WARNING",
                description=f"Very short average sentence length ({avg_len:.1f} chars), text may be fragmented",
            ))

        # Sentence length variance (good: moderate variance)
        lengths = [len(s) for s in all_sentences]
        mean_len = sum(lengths) / len(lengths)
        if mean_len > 0:
            variance = sum((l - mean_len) ** 2 for l in lengths) / len(lengths)
            cv = (variance ** 0.5) / mean_len  # Coefficient of variation
            if 0.3 <= cv <= 1.5:
                score += 0.2
            elif cv < 0.1:
                score += 0.1  # Very uniform, suspicious but not terrible

        # Very few sentences = probably bad extraction
        if len(all_sentences) < 3:
            score -= 0.2

        return max(0.0, min(1.0, score))
