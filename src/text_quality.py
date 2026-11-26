import re

from schemas import TextQualityMetrics

MIN_CHARS_PER_PAGE = 20
MIN_CHARS_FOR_RATIO_CHECKS = 100
LONG_HANGUL_RUN_LENGTH = 15
MAX_LONG_HANGUL_RUN_RATIO = 0.3
MIN_HANGUL_RATIO = 0.1
MAX_BROKEN_CHAR_RATIO = 0.05
MAX_SINGLE_CHAR_TOKEN_RATIO = 0.55

CID_PLACEHOLDER_PATTERN = re.compile(r"\(cid:\d+\)")
HANGUL_PATTERN = re.compile(r"[가-힣]")
LONG_HANGUL_RUN_PATTERN = re.compile(rf"[가-힣]{{{LONG_HANGUL_RUN_LENGTH},}}")
MARKDOWN_TABLE_SEPARATOR = re.compile(r"\|(?: --- \|)+")

ALLOWED_RANGES = [
    (0x09, 0x0A), (0x0D, 0x0D), (0x20, 0x7E), (0xA0, 0xFF),
    (0x2000, 0x206F), (0x20A0, 0x20CF), (0x2100, 0x21FF), (0x2200, 0x22FF),
    (0x2460, 0x24FF), (0x2500, 0x257F), (0x25A0, 0x26FF),
    (0x3000, 0x303F), (0x3130, 0x318F), (0x4E00, 0x9FFF), (0xAC00, 0xD7A3),
    (0xF900, 0xFAFF), (0xFF00, 0xFFEF),
]


def is_allowed(ch: str) -> bool:
    o = ord(ch)
    return any(lo <= o <= hi for lo, hi in ALLOWED_RANGES)


def count_broken_chars(text: str) -> int:
    cid_placeholder_chars = sum(len(match) for match in CID_PLACEHOLDER_PATTERN.findall(text))

    text_without_placeholders = CID_PLACEHOLDER_PATTERN.sub("", text)
    broken_chars = sum(1 for char in text_without_placeholders if not is_allowed(char))

    return cid_placeholder_chars + broken_chars


def strip_markdown_table_syntax(text: str) -> str:
    lines = text.split("\n")
    content_lines: list[str] = []
    inside_table = False

    # Recognize the table header and separator produced by the PDF parser.
    for line, next_line in zip(lines, [*lines[1:], ""], strict=True):
        is_table_row = line.startswith("| ") and line.endswith(" |")
        starts_table = is_table_row and MARKDOWN_TABLE_SEPARATOR.fullmatch(next_line)
        inside_table = is_table_row and (inside_table or bool(starts_table))

        # Keep cell contents while omitting structural separators and empty rows.
        if not inside_table:
            content_lines.append(line)
        elif not MARKDOWN_TABLE_SEPARATOR.fullmatch(line):
            cell_text = line[2:-2].replace(" | ", " ").replace(r"\|", "|").replace("<br>", " ")
            cell_text = " ".join(cell_text.split())
            if cell_text:
                content_lines.append(cell_text)

    return "\n".join(content_lines)


def compute_text_quality_metrics(text: str) -> TextQualityMetrics:
    total_chars = len(text)
    safe_denominator = max(total_chars, 1)

    # count each character category
    whitespace_chars = sum(1 for char in text if char.isspace())
    hangul_chars = len(HANGUL_PATTERN.findall(text))
    broken_chars = count_broken_chars(text)

    return TextQualityMetrics(
        total_chars=total_chars,
        whitespace_ratio=whitespace_chars / safe_denominator,
        hangul_ratio=hangul_chars / safe_denominator,
        broken_char_ratio=broken_chars / safe_denominator,
        single_char_token_ratio=compute_single_char_token_ratio(text),
        long_hangul_run_ratio=compute_long_hangul_run_ratio(text),
    )


def compute_single_char_token_ratio(text: str) -> float:
    tokens = text.split()
    if not tokens:
        return 0.0

    return sum(len(token) == 1 for token in tokens) / len(tokens)


def compute_long_hangul_run_ratio(text: str) -> float:
    """한글 글자가 LONG_HANGUL_RUN_LENGTH 보다 길게 이어지는 부분을 잡아내는 함수"""
    hangul_chars = len(HANGUL_PATTERN.findall(text))
    if not hangul_chars:
        return 0.0

    long_run_chars = sum(len(run) for run in LONG_HANGUL_RUN_PATTERN.findall(text))
    return long_run_chars / hangul_chars
