import re

from schemas import TextQualityMetrics

# Acceptance thresholds for a parsed text (used to decide whether a PDF parser's result is good enough)
MIN_WHITESPACE_RATIO = 0.1
MIN_HANGUL_RATIO = 0.1
MAX_BROKEN_CHAR_RATIO_EXCLUSIVE = 0.05

CID_PLACEHOLDER_PATTERN = re.compile(r"\(cid:\d+\)")
HANGUL_PATTERN = re.compile(r"[가-힣]")

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
    )


def is_text_quality_acceptable(metrics: TextQualityMetrics) -> bool:
    return (
        metrics.total_chars > 0
        and metrics.whitespace_ratio >= MIN_WHITESPACE_RATIO
        and metrics.hangul_ratio >= MIN_HANGUL_RATIO
        and metrics.broken_char_ratio < MAX_BROKEN_CHAR_RATIO_EXCLUSIVE
    )
