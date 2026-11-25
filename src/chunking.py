"""Build article-aware chunks from the text of an accepted parse result."""

import json
import re
from bisect import bisect_right
from collections import Counter
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import TypedDict

from schemas import ArticleSegment, Chunk, DocumentRecord, PageCharOffset, ParseResult

MAX_CHUNK_CHARS = 1200
CHUNK_OVERLAP_CHARS = 200
CHUNKS_JSONL_PATH = Path(__file__).resolve().parent.parent / "data" / "chunks" / "chunks.jsonl"

HORIZONTAL_SPACE = r"[^\S\r\n]*"
ARTICLE_NUMBER_PATTERN = re.compile(
    rf"제{HORIZONTAL_SPACE}\d+{HORIZONTAL_SPACE}조(?:{HORIZONTAL_SPACE}의{HORIZONTAL_SPACE}\d+)?"
)
ARTICLE_LINE_START_PATTERN = re.compile(
    rf"(?:\A|(?<=\n)|(?<=\r)){HORIZONTAL_SPACE}({ARTICLE_NUMBER_PATTERN.pattern}){HORIZONTAL_SPACE}"
)
ARTICLE_CITATION_PATTERN = re.compile(r'및|에\s*따라|중\s*["“”]|제\s*\d+\s*항|의\s*규정')
TITLE_BRACKETS = {"(": ("(", ")"), "[": ("[［", "]］"), "［": ("[［", "]］"), "【": ("【", "】")}
ANY_TITLE_BRACKET_PATTERN = re.compile(r"[()（）\[\]［］【】]")
TOC_PAGE_NUMBER_PATTERN = re.compile(r"(?<=[\s)\]］】])\d+$")
# A leader without a page number needs a longer run to distinguish it from an ellipsis.
DOT_LEADER_PATTERN = re.compile(
    r"[^.\s·ㆍ…⋯]\s*(?:(?:(?:[.·ㆍ]\s*){3,}|(?:[…⋯]\s*){2,})\d+"
    r"|(?:[.·ㆍ]\s*){5,}|(?:[…⋯]\s*){3,})$"
)
STANDALONE_PAGE_NUMBER_PATTERN = re.compile(
    r"(?:\d+(?:\s*/\s*\d+)?|\(\s*\d+\s*\)|p\.\s*\d+|[-–—]\s*\d+\s*[-–—])",
    re.IGNORECASE,
)
LINE_BREAK = r"(?:\r\n?|\n)"
LINE_BREAK_PATTERN = re.compile(LINE_BREAK)
CHUNK_BREAK_PATTERNS = (
    re.compile(rf"{LINE_BREAK}(?:[^\S\r\n]*{LINE_BREAK})+"),
    LINE_BREAK_PATTERN,
    re.compile(r"""[.!?。！？]+["'”’」』]?(?=\s|$)"""),
)
WHITESPACE_PATTERN = re.compile(r"\s")


@dataclass(frozen=True)
class ArticleHeader:
    offset: int
    article: str
    article_title: str


@dataclass(frozen=True)
class ChunkSpan:
    start: int
    end: int
    page_start: int
    page_end: int


class ChunkMetadata(TypedDict):
    doc_type: str
    issuer: str
    product: str
    generation: str
    effective_from: str
    effective_to: str
    category: str
    format: str
    parser_name: str


def is_table_of_contents_line(line: str) -> bool:
    stripped_line = line.strip()
    article_match = ARTICLE_NUMBER_PATTERN.match(stripped_line)

    return bool(
        DOT_LEADER_PATTERN.search(stripped_line)
        or (
            article_match
            and TOC_PAGE_NUMBER_PATTERN.search(stripped_line, article_match.end())
        )
    )

# 목차 줄 제거
def remove_table_of_contents_lines(page_text: str) -> str:
    return "".join(
        line for line in page_text.splitlines(keepends=True)
        if not is_table_of_contents_line(line)
    )

# 페이지 번호만 있는 줄 제거
def remove_standalone_page_number_lines(page_text: str) -> str:
    return "".join(
        line for line in page_text.splitlines(keepends=True)
        if not STANDALONE_PAGE_NUMBER_PATTERN.fullmatch(line.strip())
    )


def extract_bracketed_article_title(page_text: str, start: int, limit: int) -> str | None:
    opening_brackets, closing_brackets = TITLE_BRACKETS[page_text[start]]
    depth = 1

    # Avoid treating a malformed title as part of the next article candidate.
    for index in range(start + 1, limit):
        character = page_text[index]
        if character in opening_brackets:
            depth += 1
        elif character in closing_brackets:
            depth -= 1
            if depth == 0:
                return page_text[start + 1:index].strip() or None

    return None


def get_unbracketed_article_title(line: str, title_text: str) -> str | None:
    if (
        len(line) <= 30
        and not ANY_TITLE_BRACKET_PATTERN.search(title_text)
        and not ARTICLE_CITATION_PATTERN.search(title_text)
    ):
        return title_text

    return None


def find_article_headers(page_text: str) -> list[ArticleHeader]:
    # Find candidates at line starts and use the next candidate to bound wrapped titles.
    headers: list[ArticleHeader] = []
    matches = list(ARTICLE_LINE_START_PATTERN.finditer(page_text))
    limits = [match.start() for match in matches[1:]] + [len(page_text)] if matches else []

    for match, limit in zip(matches, limits, strict=True):
        # Bracketed titles may wrap, while a plain title must fit on one short line.
        title_start = match.end()
        if title_start < limit and page_text[title_start] in TITLE_BRACKETS:
            title = extract_bracketed_article_title(page_text, title_start, limit)
        else:
            line_break = LINE_BREAK_PATTERN.search(page_text, title_start, limit)
            line_end = line_break.start() if line_break else limit
            line = page_text[match.start():line_end].strip()
            title_text = page_text[title_start:line_end].strip()
            title = get_unbracketed_article_title(line, title_text)

        # Keep the original line offset while normalising the article number.
        if title is not None:
            article = "".join(match[1].split())
            headers.append(ArticleHeader(match.start(), article, title))

    return headers


def create_article_segment(
    text: str, page: int, header: ArticleHeader | None = None,
) -> ArticleSegment:
    return ArticleSegment(
        text=text,
        article=header.article if header else "",
        article_title=header.article_title if header else "",
        page_start=page,
        page_end=page,
        page_char_offsets=[PageCharOffset(page=page, start=0, end=len(text))],
    )


def append_page_prefix_to_segment(segment: ArticleSegment, prefix: str, page: int) -> None:
    start = len(segment.text)
    segment.text += prefix

    segment.page_end = page
    segment.page_char_offsets.append(PageCharOffset(page=page, start=start, end=len(segment.text)))


def split_pages_into_article_segments(page_texts: list[str]) -> list[ArticleSegment]:
    segments: list[ArticleSegment] = []

    # Attribute each inter-page newline to the page it follows.
    for page, page_text in enumerate(page_texts, start=1):
        if page < len(page_texts):
            page_text += "\n"
        if not page_text:
            continue

        # Keep a page without headers in its own body segment.
        headers = find_article_headers(page_text)
        if not headers:
            segments.append(create_article_segment(page_text, page))
            continue

        # Text before the first header continues the preceding segment when one exists.
        prefix = page_text[:headers[0].offset]
        if prefix:
            if segments:
                append_page_prefix_to_segment(segments[-1], prefix, page)
            else:
                segments.append(create_article_segment(prefix, page))

        # Each header starts a new segment up to the next header or page end.
        header_ends = [header.offset for header in headers[1:]] + [len(page_text)]
        for header, end in zip(headers, header_ends, strict=True):
            segments.append(create_article_segment(page_text[header.offset:end], page, header))

    return segments


def find_chunk_end(text: str, start: int, previous_end: int) -> int:
    limit = min(start + MAX_CHUNK_CHARS, len(text))
    if limit == len(text):
        return limit

    # Search beyond the previous chunk so every split covers new text.
    search_start = max(previous_end, start + CHUNK_OVERLAP_CHARS)
    for break_pattern in CHUNK_BREAK_PATTERNS:
        matches = list(break_pattern.finditer(text, search_start, limit))
        if matches:
            return matches[-1].end()

    return limit


def find_overlap_start(text: str, start: int, end: int) -> int:
    target = end - CHUNK_OVERLAP_CHARS
    tolerance = CHUNK_OVERLAP_CHARS // 4
    search_start = max(start, target - tolerance - 1)
    search_end = min(end - 1, target + tolerance)

    # Use the closest whitespace boundary within 50 characters of the target.
    boundaries = (match.end() for match in WHITESPACE_PATTERN.finditer(text, search_start, search_end))

    return min(boundaries, key=lambda offset: (abs(offset - target), -offset), default=target)


def split_segment_with_overlap(segment: ArticleSegment) -> Iterator[ChunkSpan]:
    page_offsets = segment.page_char_offsets
    page_starts = [offset.start for offset in page_offsets]
    start = previous_end = 0

    # Map the first and last included characters to their source pages.
    while previous_end < len(segment.text):
        end = find_chunk_end(segment.text, start, previous_end)
        first_page = page_offsets[bisect_right(page_starts, start) - 1].page
        last_page = page_offsets[bisect_right(page_starts, end - 1) - 1].page
        yield ChunkSpan(start, end, first_page, last_page)

        # Only look for an overlap if more text still needs to be covered.
        previous_end = end
        if end < len(segment.text):
            start = find_overlap_start(segment.text, start, end)


def get_chunk_metadata(document: DocumentRecord, parser_name: str) -> ChunkMetadata:
    return ChunkMetadata(
        doc_type=document.doc_type,
        issuer=document.issuer,
        product=document.product,
        generation=document.generation,
        effective_from=document.effective_from,
        effective_to=document.effective_to,
        category=document.category,
        format=document.format,
        parser_name=parser_name,
    )


def chunk_document(document: DocumentRecord, parse_result: ParseResult) -> list[Chunk]:
    # Clean each page before finding article boundaries and assigning offsets.
    cleaned_pages = [
        remove_standalone_page_number_lines(remove_table_of_contents_lines(page_text))
        for page_text in parse_result.page_texts
    ]
    segments = split_pages_into_article_segments(cleaned_pages)

    # Carry the sequence across repeated article names and all unlabelled body segments.
    sequences: Counter[str] = Counter()
    metadata = get_chunk_metadata(document, parse_result.parser_name)
    chunks: list[Chunk] = []

    for segment in segments:
        # Keep only the original segment's text and the pages actually covered by each span.
        article_label = segment.article or "본문"
        for span in split_segment_with_overlap(segment):
            sequences[article_label] += 1
            seq = sequences[article_label]
            text = segment.text[span.start:span.end]
            chunks.append(Chunk(
                chunk_id=f"{document.doc_id}#{article_label}#{seq}",
                doc_id=document.doc_id,
                text=text,
                article=segment.article,
                article_title=segment.article_title,
                seq=seq,
                page_start=span.page_start,
                page_end=span.page_end,
                n_chars=len(text),
                meta=metadata.copy(),
            ))

    return chunks


def save_chunks_to_jsonl(chunks: list[Chunk], output_path: Path = CHUNKS_JSONL_PATH) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", encoding="utf-8", newline="\n") as jsonl_file:
        for chunk in chunks:
            jsonl_file.write(json.dumps(chunk.to_dict(), ensure_ascii=False) + "\n")
