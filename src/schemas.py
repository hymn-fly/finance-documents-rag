from dataclasses import asdict, dataclass, field
from pathlib import Path

from pydantic import BaseModel


class DocumentRecord(BaseModel):
    """Document source and metadata from documents.csv."""

    doc_id: str
    format: str
    path: Path
    doc_type: str = ""
    issuer: str = ""
    product: str = ""
    generation: str = ""
    effective_from: str = ""
    effective_to: str = ""
    category: str = ""


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


class PageCharOffset(BaseModel):
    """Half-open character range of a page within one article segment."""

    page: int
    start: int
    end: int


class ArticleSegment(BaseModel):
    """Contiguous document text with its article and source page ranges."""

    text: str
    article: str
    article_title: str
    page_start: int
    page_end: int
    page_char_offsets: list[PageCharOffset]


@dataclass
class Chunk:
    chunk_id: str
    doc_id: str
    text: str
    article: str = ""
    article_title: str = ""
    seq: int = 0
    page_start: int = 0
    page_end: int = 0
    n_chars: int = 0
    meta: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)
