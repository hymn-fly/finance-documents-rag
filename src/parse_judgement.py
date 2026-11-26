"""Judge the extracted pages and save the evidence for each verdict."""

import csv
import json
from collections import Counter
from pathlib import Path

from schemas import (
    DocReport,
    DocVerdict,
    DocumentRecord,
    DocumentRunReport,
    PageImageInfo,
    PageReport,
    PageVerdict,
    ParseResult,
    TextQualityMetrics,
)
from text_quality import (
    MAX_BROKEN_CHAR_RATIO,
    MAX_LONG_HANGUL_RUN_RATIO,
    MAX_SINGLE_CHAR_TOKEN_RATIO,
    MIN_CHARS_FOR_RATIO_CHECKS,
    MIN_CHARS_PER_PAGE,
    MIN_HANGUL_RATIO,
    compute_text_quality_metrics,
)

PARSE_REPORT_CSV_PATH = Path(__file__).resolve().parent.parent / "data" / "parsed" / "parse_report.csv"
PARSE_PAGE_REPORT_CSV_PATH = PARSE_REPORT_CSV_PATH.with_name("parse_page_report.csv")
PARSE_REPORT_COLUMNS = [
    "doc_id", "parser", "doc_verdict", "doc_reasons", "total_chars", "chunk_count",
    "page_count", "usable_page_count", "reparse_page_count", "reparse_pages",
    "ocr_page_count", "ocr_pages",
    "succeeded", "elapsed_seconds", "error_message",
]
PARSE_PAGE_REPORT_COLUMNS = [
    "doc_id", "parser", "page", "page_verdict", "page_reasons",
    "total_chars", "whitespace_ratio", "hangul_ratio", "broken_char_ratio",
    "single_char_token_ratio", "long_hangul_run_ratio", "image_count", "doc_verdict", "doc_reasons",
]


def detect_page_visual_objects(pdf_path: Path) -> list[PageImageInfo]:
    import pymupdf

    with pymupdf.open(pdf_path) as pdf_document:
        image_counts = [len(page.get_images()) for page in pdf_document]

    return [
        PageImageInfo(page=page, image_count=image_count, has_image=image_count >= 1)
        for page, image_count in enumerate(image_counts, start=1)
    ]


def find_broken_text_reasons(metrics: TextQualityMetrics) -> list[str]:
    if metrics.broken_char_ratio > MAX_BROKEN_CHAR_RATIO:
        return [f"깨진 문자 비율 {metrics.broken_char_ratio:.4f} > {MAX_BROKEN_CHAR_RATIO}"]
    return []


def find_text_distribution_reasons(metrics: TextQualityMetrics) -> list[str]:
    reasons: list[str] = []
    if metrics.hangul_ratio < MIN_HANGUL_RATIO:
        reasons.append(f"한글 비율 {metrics.hangul_ratio:.4f} < {MIN_HANGUL_RATIO}")
    if metrics.long_hangul_run_ratio > MAX_LONG_HANGUL_RUN_RATIO:
        reasons.append(f"긴 한글 연속 구간(공백 소실) 비율 {metrics.long_hangul_run_ratio:.4f} > {MAX_LONG_HANGUL_RUN_RATIO}")
    if metrics.single_char_token_ratio > MAX_SINGLE_CHAR_TOKEN_RATIO:
        reasons.append(f"한 글자 토큰 비율 {metrics.single_char_token_ratio:.4f} > {MAX_SINGLE_CHAR_TOKEN_RATIO}")
    return reasons


def judge_page(metrics: TextQualityMetrics, *, has_image: bool) -> tuple[PageVerdict, list[str]]:
    # Handle blank pages and scans before checking ratios.
    if metrics.total_chars < MIN_CHARS_PER_PAGE:
        if has_image:
            return "ocr", [f"텍스트 부족 ({metrics.total_chars}자) 및 이미지 있음"]
        return "pass", [f"빈 페이지 ({metrics.total_chars}자)"]

    # Broken characters such as (cid:N) are a direct signal, so check them on every text page.
    reasons = find_broken_text_reasons(metrics)

    # Distribution ratios swing too much on short pages such as covers and titles.
    is_short_page = metrics.total_chars < MIN_CHARS_FOR_RATIO_CHECKS
    if not is_short_page:
        reasons.extend(find_text_distribution_reasons(metrics))

    # Keep a note when a short page passes without the distribution checks.
    if reasons:
        return "reparse", reasons
    if is_short_page:
        return "pass", [f"짧은 페이지 ({metrics.total_chars}자), 분포 지표 검사 생략"]
    return "pass", []


def judge_document_from_page_reports(page_reports: list[PageReport]) -> tuple[DocVerdict, list[str]]:
    if not page_reports:
        return "fail", ["판정할 페이지 없음"]

    counts = Counter(page_report.verdict for page_report in page_reports)
    if counts["reparse"]:
        reasons = [f"재추출 필요 {counts['reparse']}쪽"]
        if counts["ocr"]:
            reasons.append(f"OCR 필요 {counts['ocr']}쪽")
        return "reparse", reasons
    if counts["ocr"]:
        return "ocr", [f"OCR 필요 {counts['ocr']}쪽"]

    return "pass", []


def get_page_images_for_parse_result(
    document: DocumentRecord, parsed_page_count: int,
) -> list[PageImageInfo]:
    # An image inspection error should leave the parsed text available for judging.
    try:
        page_images = detect_page_visual_objects(document.path)
    except Exception as image_error:
        print(f"[WARN] {document.doc_id}: 이미지 탐지 실패 ({image_error})")
        return []

    # Match available image data by the original one-based page number.
    if len(page_images) != parsed_page_count:
        print(f"[WARN] {document.doc_id}: 파싱 {parsed_page_count}쪽 / PDF {len(page_images)}쪽")

    return page_images


def build_page_reports(
    page_metrics: list[TextQualityMetrics], page_images: list[PageImageInfo],
) -> list[PageReport]:
    images_by_page = {image_info.page: image_info for image_info in page_images}
    page_reports: list[PageReport] = []

    # Use no image for unmatched parsed pages and for formats without image inspection.
    for page, metrics in enumerate(page_metrics, start=1):
        image_info = images_by_page.get(page)
        has_image = image_info.has_image if image_info else False
        verdict, reasons = judge_page(metrics, has_image=has_image)
        page_reports.append(PageReport(
            page=page,
            verdict=verdict,
            reasons=reasons,
            metrics=metrics,
            has_image=has_image,
            image_count=image_info.image_count if image_info else 0,
        ))

    return page_reports


def judge_parsed_result(document: DocumentRecord, parse_result: ParseResult) -> DocReport:
    is_pdf = document.path.suffix.lower() == ".pdf"

    # A failed PDF extraction can be retried by a different parser.
    if not parse_result.succeeded:
        return DocReport(
            doc_id=document.doc_id, parser_name=parse_result.parser_name,
            verdict="reparse" if is_pdf else "fail",
            reasons=[f"파싱 실패: {parse_result.error_message}"],
            usable_page_count=0, reparse_page_count=0, ocr_page_count=0, pages=[],
        )

    # Judge extracted text using image evidence where available.
    page_metrics = [compute_text_quality_metrics(page_text) for page_text in parse_result.page_texts]
    page_images = get_page_images_for_parse_result(document, len(page_metrics)) if is_pdf else []
    page_reports = build_page_reports(page_metrics, page_images)

    # Aggregate page verdicts into a document report.
    verdict, reasons = judge_document_from_page_reports(page_reports)
    counts = Counter(page_report.verdict for page_report in page_reports)

    return DocReport(
        doc_id=document.doc_id, parser_name=parse_result.parser_name,
        verdict=verdict, reasons=reasons, usable_page_count=counts["pass"],
        reparse_page_count=counts["reparse"], ocr_page_count=counts["ocr"], pages=page_reports,
    )


def save_parse_report_csv(
    run_reports: list[DocumentRunReport], output_path: Path = PARSE_REPORT_CSV_PATH,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Write one row per document, including documents whose extraction failed.
    with output_path.open("w", encoding="utf-8-sig", newline="") as report_file:
        writer = csv.DictWriter(report_file, fieldnames=PARSE_REPORT_COLUMNS)
        writer.writeheader()
        for run_report in run_reports:
            result = run_report.parse_result
            judgement = run_report.judgement
            reparse_pages = [page.page for page in judgement.pages if page.verdict == "reparse"]
            ocr_pages = [page.page for page in judgement.pages if page.verdict == "ocr"]

            writer.writerow({
                "doc_id": judgement.doc_id,
                "parser": judgement.parser_name,
                "doc_verdict": judgement.verdict,
                "doc_reasons": " | ".join(judgement.reasons),
                "total_chars": result.total_chars,
                "chunk_count": run_report.chunk_count,
                "page_count": len(result.page_texts),
                "usable_page_count": judgement.usable_page_count,
                "reparse_page_count": judgement.reparse_page_count,
                "reparse_pages": json.dumps(reparse_pages),
                "ocr_page_count": judgement.ocr_page_count,
                "ocr_pages": json.dumps(ocr_pages),
                "succeeded": result.succeeded,
                "elapsed_seconds": f"{result.elapsed_seconds:.2f}",
                "error_message": result.error_message,
            })


def save_parse_page_report_csv(
    doc_reports: list[DocReport], output_path: Path = PARSE_PAGE_REPORT_CSV_PATH,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Output one row per judged page. A document without pages still gets a verdict row.
    with output_path.open("w", encoding="utf-8-sig", newline="") as report_file:
        writer = csv.DictWriter(report_file, fieldnames=PARSE_PAGE_REPORT_COLUMNS)
        writer.writeheader()
        for report in doc_reports:
            doc_fields = {
                "doc_id": report.doc_id,
                "parser": report.parser_name,
                "doc_verdict": report.verdict,
                "doc_reasons": " | ".join(report.reasons),
            }
            if not report.pages:
                writer.writerow(doc_fields)

            for page_report in report.pages:
                writer.writerow({
                    **doc_fields,
                    "page": page_report.page,
                    "page_verdict": page_report.verdict,
                    "page_reasons": " | ".join(page_report.reasons),
                    **page_report.metrics.model_dump(),
                    "image_count": page_report.image_count,
                })
