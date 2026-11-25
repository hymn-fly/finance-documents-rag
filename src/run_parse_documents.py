"""Parse every file listed in data/documents.csv and save the extracted text.

Usage: uv run python src/run_parse_documents.py [--only DOC_ID ...]
Output: data/parsed/<doc_id>/<parser_name>.txt and data/parsed/parse_summary.csv
"""
import argparse
import csv
import time
from pathlib import Path

from parsers import (
    parse_hwp_or_hwpx_with_hwp_hwpx_parser,
    parse_html_file,
    parse_pdf_with_pdfplumber,
    parse_pdf_with_pymupdf,
    parse_pdf_with_pypdf,
    parse_plain_text_file,
    parse_xml_file,
)
from schemas import DocumentRecord, ParseResult
from text_quality import compute_text_quality_metrics, is_text_quality_acceptable

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DOCUMENTS_CSV_PATH = PROJECT_ROOT / "data" / "documents.csv"
PARSED_OUTPUT_DIR = PROJECT_ROOT / "data" / "parsed"
PAGE_SEPARATOR = "\n\n----- page break -----\n\n"

# tried in this order; the first parser whose result passes the quality check wins
PDF_PARSERS = {
    "pdfplumber": parse_pdf_with_pdfplumber,
    "pymupdf": parse_pdf_with_pymupdf,
    "pypdf": parse_pdf_with_pypdf,
}


def load_document_records_from_csv(csv_path: Path) -> list[DocumentRecord]:
    with csv_path.open(encoding="utf-8-sig", newline="") as csv_file:
        csv_rows = list(csv.DictReader(csv_file))

    return [
        DocumentRecord(doc_id=row["doc_id"], format=row["format"], path=PROJECT_ROOT / row["path"])
        for row in csv_rows
    ]


def select_parsers_for_document(document: DocumentRecord) -> dict:
    # route by actual file extension, since csv "binary_office" covers both hwp and hwpx
    file_suffix = document.path.suffix.lower()

    if file_suffix == ".pdf":
        return PDF_PARSERS
    if file_suffix in (".hwp", ".hwpx"):
        return {"hwp_hwpx_parser": parse_hwp_or_hwpx_with_hwp_hwpx_parser}
    if file_suffix in (".html", ".htm"):
        return {"html_regex": parse_html_file}
    if file_suffix == ".xml":
        return {"xml_etree": parse_xml_file}
    if file_suffix == ".txt":
        return {"plain_text": parse_plain_text_file}

    return {}


def run_parser_on_document(document: DocumentRecord, parser_name: str, parser_function) -> ParseResult:
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


def is_parse_result_acceptable(parse_result: ParseResult) -> bool:
    if not parse_result.succeeded:
        return False

    return is_text_quality_acceptable(compute_text_quality_metrics("".join(parse_result.page_texts)))


def run_save_and_log_parser(document: DocumentRecord, parser_name: str, parser_function) -> ParseResult:
    parse_result = run_parser_on_document(document, parser_name, parser_function)

    # save only successful outputs
    if parse_result.succeeded:
        save_parse_result_text(parse_result)

    status_label = "OK  " if parse_result.succeeded else "FAIL"
    print(f"[{status_label}] {document.doc_id} / {parser_name}: {parse_result.total_chars} chars "
          f"{parse_result.elapsed_seconds:.1f}s {parse_result.error_message}")

    return parse_result


def parse_document_with_fallback(document: DocumentRecord) -> list[ParseResult]:
    parsers_in_order = select_parsers_for_document(document)
    document_results: list[ParseResult] = []

    # try parsers in order and stop at the first acceptable result
    for parser_name, parser_function in parsers_in_order.items():
        parse_result = run_save_and_log_parser(document, parser_name, parser_function)
        document_results.append(parse_result)

        if is_parse_result_acceptable(parse_result):
            return document_results

        if len(document_results) < len(parsers_in_order):
            print(f"       -> quality check failed, trying next parser for {document.doc_id}")

    # all parsers tried; none passed (expected for non-pdf formats that have a single parser)
    return document_results


def main() -> None:
    argument_parser = argparse.ArgumentParser()
    argument_parser.add_argument("--only", nargs="*", help="parse only these doc_ids")
    command_line_arguments = argument_parser.parse_args()

    # load records, optionally filtered by doc_id
    documents = load_document_records_from_csv(DOCUMENTS_CSV_PATH)
    if command_line_arguments.only:
        documents = [doc for doc in documents if doc.doc_id in command_line_arguments.only]

    # parse each document (pdf: fallback chain, others: their single parser)
    all_results: list[ParseResult] = []
    for document in documents:
        if not document.path.exists():
            print(f"[SKIP] {document.doc_id}: file not found ({document.path.name})")
            continue

        all_results.extend(parse_document_with_fallback(document))

    # write the overall summary
    save_parse_summary_csv(all_results)


if __name__ == "__main__":
    main()
