"""Metadata generator — produces structured JSON metadata for cleaned documents."""

from datetime import datetime, timezone

from common.models.document import Document
from common.util.logger import get_logger

logger = get_logger()


class MetadataGenerator:
    """Generate standardized metadata JSON from a cleaned Document.

    Output format is consumed by downstream RAG services (chunking, indexing).
    """

    def generate(self, doc: Document) -> dict:
        """Generate complete metadata dict for a cleaned document."""
        doc.log_stage("metadata_generation_start")

        element_stats = doc.get_element_count()

        metadata = {
            "document_id": doc.doc_id,
            "source_format": doc.metadata.source_format,
            "mime_type": doc.metadata.mime_type,
            "file_size_bytes": doc.metadata.file_size_bytes,
            "file_md5": doc.metadata.file_md5,
            "cleaning_info": {
                "version": "1.0.0",
                "cleaned_at": datetime.now(timezone.utc).isoformat(),
                "processing_log": doc.processing_log,
            },
            "document": {
                "title": doc.metadata.title,
                "author": doc.metadata.author,
                "subject": doc.metadata.subject,
                "keywords": doc.metadata.keywords,
                "created_at": doc.metadata.created_at,
                "modified_at": doc.metadata.modified_at,
                "language": doc.metadata.language,
                "page_count": doc.metadata.page_count,
                "word_count": doc.metadata.word_count,
                "char_count": doc.metadata.char_count,
                "is_encrypted": doc.metadata.is_encrypted,
                "is_scanned": doc.metadata.is_scanned,
            },
            "elements": element_stats.to_dict(),
            "has_tables": doc.metadata.has_tables,
            "has_images": doc.metadata.has_images,
            "has_formulas": doc.metadata.has_formulas,
            "page_summary": [
                {
                    "page_number": p.page_number,
                    "element_count": len(p.elements),
                    "char_count": len(p.text_content),
                    "is_scanned": p.is_scanned,
                }
                for p in doc.pages
            ],
        }

        # Add quality report if available
        if doc.quality:
            metadata["quality"] = {
                "overall_score": doc.quality.overall_score,
                "completeness": doc.quality.completeness,
                "purity": doc.quality.purity,
                "structure": doc.quality.structure,
                "coherence": doc.quality.coherence,
                "passed": doc.quality.passed,
                "issues": [
                    {
                        "dimension": i.dimension,
                        "level": i.level,
                        "description": i.description,
                        "location": i.location,
                    }
                    for i in doc.quality.issues
                ],
            }

        doc.log_stage("metadata_generation_done")
        return metadata

    def generate_summary(self, doc: Document) -> dict:
        """Generate a lightweight summary (for task completion events)."""
        return {
            "document_id": doc.doc_id,
            "title": doc.metadata.title,
            "source_format": doc.metadata.source_format,
            "page_count": doc.page_count,
            "word_count": doc.metadata.word_count,
            "element_counts": doc.get_element_count().to_dict(),
            "quality_score": doc.quality.overall_score if doc.quality else 0.0,
            "quality_passed": doc.quality.passed if doc.quality else False,
            "processing_stages": len(doc.processing_log),
        }
