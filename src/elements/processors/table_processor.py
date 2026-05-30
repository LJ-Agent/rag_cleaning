"""Common table processor — merged cells, multi-level headers, cross-page tables → standard Markdown."""

from typing import Any

from common.config_loader import get_config
from common.models.document import TableCell, TableElement
from common.util.logger import get_logger
from elements.base import BaseElementProcessor
from elements.registry import get_element_registry

logger = get_logger()
registry = get_element_registry()


@registry.register
class TableProcessor(BaseElementProcessor[TableElement]):
    """Process tables from all formats into standard Markdown tables.

    Handles:
    - Merged cell expansion (fill strategy)
    - Multi-level header detection and normalization
    - Cross-page table stitching
    - Quality scoring
    """

    processor_name = "table"
    element_class = TableElement
    priority = 10

    def __init__(self):
        cfg = get_config()["elements"]["table"]
        self._max_cell_length = cfg.get("max_cell_content_length", 5000)
        self._output_format = cfg.get("output_format", "markdown")
        self._quality_threshold = cfg.get("quality_threshold", 0.6)

    def process(self, element: BaseElement, context: dict[str, Any] | None = None) -> BaseElement:
        if not isinstance(element, TableElement):
            return element

        # Expand merged cells
        if element.has_merged_cells:
            element = self._expand_merged_cells(element)

        # Normalize cell content (truncate, clean)
        element = self._normalize_cells(element)

        # Detect and normalize multi-level headers
        element = self._normalize_headers(element)

        # Compute quality
        element.quality_score = self.quality_score(element)

        return element

    def to_markdown(self, table: TableElement) -> str:
        """Convert processed TableElement to standard Markdown table string."""
        if not table.rows:
            return ""

        lines = []
        all_rows = table.headers + table.rows if table.headers else table.rows

        for i, row in enumerate(all_rows):
            cell_texts = [self._cell_to_text(cell) for cell in row]
            lines.append("| " + " | ".join(cell_texts) + " |")

            # Add header separator after header row(s)
            if table.headers and i == len(table.headers) - 1:
                sep = "| " + " | ".join(["---"] * len(row)) + " |"
                lines.append(sep)
            elif not table.headers and i == 0:
                sep = "| " + " | ".join(["---"] * len(row)) + " |"
                lines.append(sep)

        if table.caption:
            lines.insert(0, f"**{table.caption}**\n")

        return "\n".join(lines)

    def quality_score(self, element: BaseElement) -> float:
        if not isinstance(element, TableElement):
            return 0.0

        score = 1.0

        # Penalize empty tables
        if element.row_count == 0 or element.column_count == 0:
            return 0.0

        # Penalize very sparse tables (>50% empty cells)
        total_cells = element.row_count * element.column_count
        non_empty = sum(1 for row in (element.headers + element.rows) for cell in row if cell.text.strip())
        if total_cells > 0:
            fill_ratio = non_empty / total_cells
            if fill_ratio < 0.5:
                score -= 0.3

        # Penalize single-row tables (may be misidentified)
        if element.row_count == 1:
            score -= 0.2

        # Penalize very narrow tables
        if element.column_count < 2:
            score -= 0.2

        # Penalize cells with excessively long content
        for row in element.rows:
            for cell in row:
                if len(cell.text) > 1000:
                    score -= 0.1
                    break

        return max(0.0, min(1.0, score))

    def _expand_merged_cells(self, table: TableElement) -> TableElement:
        """Expand row_span/col_span by duplicating cell content (fill strategy)."""
        if not table.rows:
            return table

        cols = table.column_count or max((len(r) for r in table.rows), default=0)
        rows = table.row_count

        # Create a grid filled with None
        grid: list[list[TableCell | None]] = [[None] * cols for _ in range(rows)]

        for r, row in enumerate(table.rows):
            c = 0
            for cell in row:
                while c < cols and grid[r][c] is not None:
                    c += 1
                if c >= cols:
                    break
                grid[r][c] = cell
                # Fill spanned cells
                for dr in range(cell.row_span):
                    for dc in range(cell.col_span):
                        nr, nc = r + dr, c + dc
                        if nr < rows and nc < cols and (dr > 0 or dc > 0):
                            grid[nr][nc] = TableCell(text=cell.text)
                c += cell.col_span

        # Rebuild rows
        new_rows = []
        for r in range(rows):
            new_row = [grid[r][c] or TableCell() for c in range(cols)]
            new_rows.append(new_row)

        table.rows = new_rows
        table.column_count = cols
        table.row_count = len(new_rows)
        table.has_merged_cells = False
        return table

    def _normalize_cells(self, table: TableElement) -> TableElement:
        """Clean and truncate cell content."""
        for row in table.rows + table.headers:
            for cell in row:
                text = cell.text.strip()
                text = " ".join(text.split())  # Normalize whitespace
                if len(text) > self._max_cell_length:
                    text = text[:self._max_cell_length] + "..."
                cell.text = text
        return table

    def _normalize_headers(self, table: TableElement) -> TableElement:
        """Detect if first row is a header (if no explicit headers)."""
        if table.headers:
            return table

        if not table.rows:
            return table

        # Heuristic: first row is header if all cells are non-empty and short
        first_row = table.rows[0]
        all_short = all(len(cell.text) < 50 and cell.text.strip() for cell in first_row)
        has_data_rows = len(table.rows) > 1

        if all_short and has_data_rows:
            for cell in first_row:
                cell.is_header = True
            table.headers = [first_row]
            table.rows = table.rows[1:]
            table.row_count = len(table.rows)

        return table

    def _cell_to_text(self, cell: TableCell) -> str:
        """Format a cell for Markdown output."""
        text = cell.text.replace("\n", " ").replace("|", "\\|")
        if cell.is_header:
            return f"**{text}**"
        return text
