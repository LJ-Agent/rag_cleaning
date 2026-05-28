"""Abstract base class for all format-specific preprocessors."""

from abc import ABC, abstractmethod

from common.models.document import Document


class BasePreprocessor(ABC):
    """Interface for format-specific document preprocessing.

    Each preprocessor's sole responsibility is to extract raw elements
    from the native format and produce a unified Document intermediate object.
    No cleaning, enhancement, or transformation logic belongs here.
    """

    # Override in subclass
    format_type: str = "unknown"
    supported_extensions: set[str] = set()
    supported_mime_types: set[str] = set()

    @abstractmethod
    def extract(self, file_data: bytes, file_name: str) -> Document:
        """Extract raw elements from file bytes into a unified Document.

        Args:
            file_data: Raw file bytes.
            file_name: Original file name (for format detection).

        Returns:
            Unified Document object with pages and elements populated.

        Raises:
            PreprocessingException: If extraction fails.
        """
        ...

    def supports(self, extension: str) -> bool:
        """Check if this preprocessor handles the given file extension."""
        return extension.lower() in self.supported_extensions

    def supports_mime(self, mime_type: str) -> bool:
        """Check if this preprocessor handles the given MIME type."""
        return mime_type.lower() in self.supported_mime_types

    @staticmethod
    def _make_element_id(doc_id: str, page_num: int, elem_index: int, prefix: str = "e") -> str:
        """Generate a unique element ID."""
        return f"{doc_id}_{prefix}_{page_num}_{elem_index}"
