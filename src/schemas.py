from pathlib import Path

from pydantic import BaseModel


class DocumentRecord(BaseModel):
    """One row of documents.csv (only the fields the parsers need)."""

    doc_id: str
    format: str
    path: Path


class ParseResult(BaseModel):
    """Outcome of running one parser on one document."""

    doc_id: str
    parser_name: str
    succeeded: bool
    page_texts: list[str] = []
    total_chars: int = 0
    elapsed_seconds: float = 0.0
    error_message: str = ""


class TextQualityMetrics(BaseModel):
    """Character-level quality metrics of one parsed text."""

    total_chars: int
    whitespace_ratio: float
    hangul_ratio: float
    broken_char_ratio: float
