"""Build data/parsed/parsed_detail_pdf.csv: one row per (doc_id, page), and per PDF parser
the columns chars / whitespace_ratio / hangul_ratio / broken_char_ratio.

Ratios are left blank for pages with 0 chars (the ratio is undefined there).

Usage: uv run python src/build_pdf_parse_detail.py   (run run_parse_documents.py first)
"""
import csv

from build_pdf_parse_summary import METRIC_COLUMN_NAMES, compute_text_quality_metrics
from run_parse_documents import DOCUMENTS_CSV_PATH, PAGE_SEPARATOR, PARSED_OUTPUT_DIR, PDF_PARSERS, load_document_records_from_csv

DETAIL_CSV_PATH = PARSED_OUTPUT_DIR / "parsed_detail_pdf.csv"


def split_parsed_text_into_pages(doc_id: str, parser_name: str) -> list[str] | None:
    parsed_text_path = PARSED_OUTPUT_DIR / doc_id / f"{parser_name}.txt"
    if not parsed_text_path.exists():
        return None

    return parsed_text_path.read_bytes().decode("utf-8").split(PAGE_SEPARATOR)


def format_page_metric_columns(parser_name: str, page_text: str | None) -> dict[str, str]:
    column_values = {f"{parser_name}_{metric}": "" for metric in METRIC_COLUMN_NAMES}

    # parser has no such page
    if page_text is None:
        return column_values

    # empty page: only chars is defined
    metrics = compute_text_quality_metrics(page_text)
    column_values[f"{parser_name}_chars"] = str(metrics.total_chars)
    if metrics.total_chars == 0:
        return column_values

    column_values[f"{parser_name}_whitespace_ratio"] = f"{metrics.whitespace_ratio:.4f}"
    column_values[f"{parser_name}_hangul_ratio"] = f"{metrics.hangul_ratio:.4f}"
    column_values[f"{parser_name}_broken_char_ratio"] = f"{metrics.broken_char_ratio:.4f}"

    return column_values


def build_detail_rows_for_document(doc_id: str) -> list[dict[str, str]]:
    pages_by_parser = {parser_name: split_parsed_text_into_pages(doc_id, parser_name) for parser_name in PDF_PARSERS}
    page_count = max((len(pages) for pages in pages_by_parser.values() if pages is not None), default=0)

    # one row per page number; parsers that lack the page stay blank
    detail_rows = []
    for page_index in range(page_count):
        detail_row = {"doc_id": doc_id, "page": str(page_index + 1)}
        for parser_name, pages in pages_by_parser.items():
            page_text = pages[page_index] if pages is not None and page_index < len(pages) else None
            detail_row.update(format_page_metric_columns(parser_name, page_text))
        detail_rows.append(detail_row)

    return detail_rows


def main() -> None:
    pdf_doc_ids = [
        record.doc_id for record in load_document_records_from_csv(DOCUMENTS_CSV_PATH)
        if record.path.suffix.lower() == ".pdf" and (PARSED_OUTPUT_DIR / record.doc_id).exists()
    ]

    # build all page rows
    detail_rows = [row for doc_id in pdf_doc_ids for row in build_detail_rows_for_document(doc_id)]

    # write the csv
    column_names = ["doc_id", "page"] + [f"{parser}_{metric}" for parser in PDF_PARSERS for metric in METRIC_COLUMN_NAMES]
    with DETAIL_CSV_PATH.open("w", encoding="utf-8-sig", newline="") as detail_file:
        detail_writer = csv.DictWriter(detail_file, fieldnames=column_names)
        detail_writer.writeheader()
        detail_writer.writerows(detail_rows)

    print(f"wrote {len(detail_rows)} rows -> {DETAIL_CSV_PATH}")


if __name__ == "__main__":
    main()
