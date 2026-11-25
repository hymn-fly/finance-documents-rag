"""Build data/parsed/parsed_summary_pdf.csv: one row per PDF doc_id, and per PDF parser
the columns chars / whitespace_ratio / hangul_ratio / broken_char_ratio.

Ratios are computed over all characters of the parsed text (page-break markers excluded).
Broken characters = U+FFFD, private-use-area chars, control chars (except \\n \\r \\t),
and "(cid:N)" glyph placeholders.

Usage: uv run python src/build_pdf_parse_summary.py   (run run_parse_documents.py first)
"""
import csv
from pathlib import Path

from run_parse_documents import PAGE_SEPARATOR, PARSED_OUTPUT_DIR, PDF_PARSERS, load_document_records_from_csv, DOCUMENTS_CSV_PATH
from text_quality import compute_text_quality_metrics  # noqa: F401  (re-exported for build_pdf_parse_detail)

SUMMARY_CSV_PATH = PARSED_OUTPUT_DIR / "parsed_summary_pdf.csv"
METRIC_COLUMN_NAMES = ["chars", "whitespace_ratio", "hangul_ratio", "broken_char_ratio"]


def read_parsed_text_without_page_markers(parsed_text_path: Path) -> str:
    return parsed_text_path.read_bytes().decode("utf-8").replace(PAGE_SEPARATOR, "")


def build_summary_row_for_document(doc_id: str) -> dict[str, str]:
    summary_row = {"doc_id": doc_id}

    # fill each parser's columns; leave blank when that parser produced no output
    for parser_name in PDF_PARSERS:
        parsed_text_path = PARSED_OUTPUT_DIR / doc_id / f"{parser_name}.txt"
        metrics = (
            compute_text_quality_metrics(read_parsed_text_without_page_markers(parsed_text_path))
            if parsed_text_path.exists() else None
        )

        summary_row[f"{parser_name}_chars"] = str(metrics.total_chars) if metrics else ""
        summary_row[f"{parser_name}_whitespace_ratio"] = f"{metrics.whitespace_ratio:.4f}" if metrics else ""
        summary_row[f"{parser_name}_hangul_ratio"] = f"{metrics.hangul_ratio:.4f}" if metrics else ""
        summary_row[f"{parser_name}_broken_char_ratio"] = f"{metrics.broken_char_ratio:.4f}" if metrics else ""

    return summary_row


def main() -> None:
    # pdf doc_ids that have at least one parsed output
    pdf_doc_ids = [
        record.doc_id for record in load_document_records_from_csv(DOCUMENTS_CSV_PATH)
        if record.path.suffix.lower() == ".pdf" and (PARSED_OUTPUT_DIR / record.doc_id).exists()
    ]

    # one row per doc, one column group per parser
    column_names = ["doc_id"] + [f"{parser}_{metric}" for parser in PDF_PARSERS for metric in METRIC_COLUMN_NAMES]
    summary_rows = [build_summary_row_for_document(doc_id) for doc_id in pdf_doc_ids]

    # write the csv
    with SUMMARY_CSV_PATH.open("w", encoding="utf-8-sig", newline="") as summary_file:
        summary_writer = csv.DictWriter(summary_file, fieldnames=column_names)
        summary_writer.writeheader()
        summary_writer.writerows(summary_rows)

    print(f"wrote {len(summary_rows)} rows -> {SUMMARY_CSV_PATH}")


if __name__ == "__main__":
    main()
