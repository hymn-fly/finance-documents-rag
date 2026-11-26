from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Literal

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
    """Character and token quality metrics for extracted text."""

    total_chars: int
    whitespace_ratio: float
    hangul_ratio: float
    broken_char_ratio: float
    single_char_token_ratio: float
    long_hangul_run_ratio: float


type PageVerdict = Literal["pass", "reparse", "ocr"]
type DocVerdict = Literal["pass", "reparse", "ocr", "fail"]


class PageImageInfo(BaseModel):
    page: int
    image_count: int
    has_image: bool


class PageReport(BaseModel):
    page: int
    verdict: PageVerdict
    reasons: list[str]
    metrics: TextQualityMetrics
    has_image: bool
    image_count: int = 0


class DocReport(BaseModel):
    doc_id: str
    parser_name: str
    verdict: DocVerdict
    reasons: list[str]
    usable_page_count: int
    reparse_page_count: int
    ocr_page_count: int
    pages: list[PageReport]


@dataclass(frozen=True)
class DocumentRunReport:
    """Parsing, judgement and chunk count for one document in the batch."""

    parse_result: ParseResult
    judgement: DocReport
    chunk_count: int


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
