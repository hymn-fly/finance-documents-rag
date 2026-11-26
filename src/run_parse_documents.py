"""Parse and chunk every file listed in data/documents.csv.

Usage: uv run python src/run_parse_documents.py [--only DOC_ID ...]
Outputs: data/parsed/<doc_id>_<parser_name>.txt, data/parsed/parse_summary.csv,
data/parsed/parse_report.csv, data/parsed/parse_page_report.csv, and data/chunks/chunks.jsonl.
"""
import argparse
import csv
import time
from collections import Counter
from collections.abc import Callable
from pathlib import Path

from chunking import chunk_document, save_chunks_to_jsonl
from parse_judgement import judge_parsed_result, save_parse_page_report_csv, save_parse_report_csv
from parsers import (
    parse_hwp_or_hwpx_with_hwp_hwpx_parser,
    parse_html_file,
    parse_pdf_with_pdfplumber,
    parse_pdf_with_pymupdf,
    parse_pdf_with_pypdf,
    parse_pdf_with_pymupdf_layout_and_pdfplumber_text,
    parse_plain_text_file,
    parse_xml_file,
)
from schemas import Chunk, DocReport, DocumentRecord, DocumentRunReport, ParseResult

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DOCUMENTS_CSV_PATH = PROJECT_ROOT / "data" / "documents.csv"
PARSED_OUTPUT_DIR = PROJECT_ROOT / "data" / "parsed"
PAGE_SEPARATOR = "\n\n----- page break -----\n\n"

DEFAULT_PDF_PARSER_NAME = "pymupdf_layout_pdfplumber_text"

type ParserFunction = Callable[[Path], list[str]]

# Retained for parser comparisons and future re-extraction.
PDF_PARSERS = {
    "pdfplumber": parse_pdf_with_pdfplumber,
    "pymupdf": parse_pdf_with_pymupdf,
    "pypdf": parse_pdf_with_pypdf,
}


def load_document_records_from_csv(csv_path: Path) -> list[DocumentRecord]:
    with csv_path.open(encoding="utf-8-sig", newline="") as csv_file:
        csv_rows = list(csv.DictReader(csv_file))

    return [
        DocumentRecord(**{**row, "path": PROJECT_ROOT / row["path"]})
        for row in csv_rows
    ]


def select_parsers_for_document(document: DocumentRecord) -> dict[str, ParserFunction]:
    # route by actual file extension, since csv "binary_office" covers both hwp and hwpx
    file_suffix = document.path.suffix.lower()

    if file_suffix in (".hwp", ".hwpx"):
        return {"hwp_hwpx_parser": parse_hwp_or_hwpx_with_hwp_hwpx_parser}
    if file_suffix in (".html", ".htm"):
        return {"html_regex": parse_html_file}
    if file_suffix == ".xml":
        return {"xml_etree": parse_xml_file}
    if file_suffix == ".txt":
        return {"plain_text": parse_plain_text_file}

    return {}


def run_parser_on_document(
    document: DocumentRecord, parser_name: str, parser_function: ParserFunction,
) -> ParseResult:
    start_time = time.perf_counter()

    # a failure in one parser must not stop the whole batch
    try:
        page_texts = parser_function(document.path)
    except Exception as parse_error:
        return ParseResult(
            doc_id=document.doc_id,
            parser_name=parser_name,
            succeeded=False,
            elapsed_seconds=time.perf_counter() - start_time,
            error_message=f"{type(parse_error).__name__}: {parse_error}",
        )

    return ParseResult(
        doc_id=document.doc_id,
        parser_name=parser_name,
        succeeded=True,
        page_texts=page_texts,
        total_chars=sum(len(page_text) for page_text in page_texts),
        elapsed_seconds=time.perf_counter() - start_time,
    )


def run_layout_pdf_parser(document: DocumentRecord) -> ParseResult:
    start_time = time.perf_counter()

    # Extract each PDF page and record extraction errors in the batch result.
    try:
        parsed_pages = parse_pdf_with_pymupdf_layout_and_pdfplumber_text(document.path)
    except Exception as parse_error:
        return ParseResult(
            doc_id=document.doc_id,
            parser_name=DEFAULT_PDF_PARSER_NAME,
            succeeded=False,
            elapsed_seconds=time.perf_counter() - start_time,
            error_message=f"{type(parse_error).__name__}: {parse_error}",
        )

    # Keep the page texts and their reading orders aligned in document order.
    return ParseResult(
        doc_id=document.doc_id,
        parser_name=DEFAULT_PDF_PARSER_NAME,
        succeeded=True,
        page_texts=[page.text for page in parsed_pages],
        page_reading_orders=[page.reading_order for page in parsed_pages],
        total_chars=sum(len(page.text) for page in parsed_pages),
        elapsed_seconds=time.perf_counter() - start_time,
    )


def save_parse_result_text(parse_result: ParseResult) -> None:
    output_path = PARSED_OUTPUT_DIR / f"{parse_result.doc_id}_{parse_result.parser_name}.txt"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    output_path.write_text(PAGE_SEPARATOR.join(parse_result.page_texts), encoding="utf-8")


def save_parse_summary_csv(parse_results: list[ParseResult]) -> None:
    PARSED_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    with (PARSED_OUTPUT_DIR / "parse_summary.csv").open("w", encoding="utf-8-sig", newline="") as summary_file:
        summary_writer = csv.writer(summary_file)
        summary_writer.writerow(["doc_id", "parser", "succeeded", "pages", "chars", "seconds", "error"])

        for result in parse_results:
            summary_writer.writerow([
                result.doc_id, result.parser_name, result.succeeded, len(result.page_texts),
                result.total_chars, f"{result.elapsed_seconds:.2f}", result.error_message,
            ])


def run_non_pdf_parser(document: DocumentRecord) -> ParseResult:
    parsers = select_parsers_for_document(document)
    if not parsers:
        return ParseResult(
            doc_id=document.doc_id, parser_name="", succeeded=False,
            error_message=f"지원하지 않는 파일 형식: {document.path.suffix}",
        )

    parser_name, parser_function = next(iter(parsers.items()))
    return run_parser_on_document(document, parser_name, parser_function)


def parse_document_with_default_parser(document: DocumentRecord) -> ParseResult:
    if document.path.suffix.lower() == ".pdf":
        parse_result = run_layout_pdf_parser(document)
    else:
        parse_result = run_non_pdf_parser(document)

    if parse_result.succeeded:
        save_parse_result_text(parse_result)

    return parse_result


def chunk_pass_pages(
    document: DocumentRecord, parse_result: ParseResult, report: DocReport,
) -> list[Chunk]:
    if report.verdict == "fail" or not report.usable_page_count:
        return []

    usable_pages = {page_report.page for page_report in report.pages if page_report.verdict == "pass"}

    return chunk_document(document, parse_result, usable_pages=usable_pages)


def log_document_result(parse_result: ParseResult, report: DocReport, chunk_count: int) -> None:
    reasons = " | ".join(report.reasons) or "기준 충족"
    print(f"[JUDGE] {report.doc_id}: {report.verdict} ({reasons})")

    status = "OK  " if parse_result.succeeded else "FAIL"
    print(f"[{status}] {parse_result.doc_id} / {parse_result.parser_name}: {parse_result.total_chars} chars, "
          f"{parse_result.elapsed_seconds:.1f}s, {chunk_count} chunks {parse_result.error_message}".rstrip())


def log_verdict_distribution(doc_reports: list[DocReport]) -> None:
    counts = Counter(report.verdict for report in doc_reports)
    verdict_counts = ", ".join(f"{verdict}={counts[verdict]}" for verdict in ("pass", "reparse", "ocr", "fail"))

    print(f"[JUDGE SUMMARY] {len(doc_reports)} documents: {verdict_counts}")


def main() -> None:
    argument_parser = argparse.ArgumentParser()
    argument_parser.add_argument("--only", nargs="*", help="parse only these doc_ids")
    command_line_arguments = argument_parser.parse_args()

    # load records, optionally filtered by doc_id
    documents = load_document_records_from_csv(DOCUMENTS_CSV_PATH)
    if command_line_arguments.only:
        documents = [doc for doc in documents if doc.doc_id in command_line_arguments.only]

    # Parse, judge and chunk each available document once.
    run_reports: list[DocumentRunReport] = []
    all_chunks: list[Chunk] = []
    for document in documents:
        if not document.path.exists():
            print(f"[SKIP] {document.doc_id}: file not found ({document.path.name})")
            continue

        parse_result = parse_document_with_default_parser(document)
        report = judge_parsed_result(document, parse_result)
        document_chunks = chunk_pass_pages(document, parse_result, report)

        # Keep the results of this run together for the batch outputs.
        run_reports.append(DocumentRunReport(parse_result, report, len(document_chunks)))
        all_chunks.extend(document_chunks)
        log_document_result(parse_result, report, len(document_chunks))

    # Replace the batch outputs after processing the selected documents.
    doc_judgements = [run_report.judgement for run_report in run_reports]
    save_parse_summary_csv([run_report.parse_result for run_report in run_reports])
    save_parse_report_csv(run_reports, PARSED_OUTPUT_DIR / "parse_report.csv")
    save_parse_page_report_csv(doc_judgements, PARSED_OUTPUT_DIR / "parse_page_report.csv")
    save_chunks_to_jsonl(all_chunks)
    log_verdict_distribution(doc_judgements)


if __name__ == "__main__":
    main()
