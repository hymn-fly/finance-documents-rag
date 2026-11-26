import csv
import json
from functools import partial
from pathlib import Path

import pytest

import parse_judgement
import run_parse_documents
from parse_judgement import judge_page, judge_parsed_result, save_parse_page_report_csv, save_parse_report_csv
from run_parse_documents import chunk_pass_pages, parse_document_with_default_parser
from schemas import DocumentRecord, DocumentRunReport, PageImageInfo, ParseResult, TextQualityMetrics
from text_quality import compute_long_hangul_run_ratio, compute_text_quality_metrics


# 공백만 있는 텍스트와 일반 텍스트의 한 글자 토큰 비율 계산 확인
@pytest.mark.parametrize(("text", "ratio"), [("  \n\t", 0.0), ("가\t나 계약\n보험", 0.5)])
def test_single_char_token_ratio(text: str, ratio: float):
    assert compute_text_quality_metrics(text).single_char_token_ratio == ratio


# 20자 미만 페이지는 이미지가 없으면 pass, 있으면 ocr 판정하는지 확인
def test_judge_page_blank_page():
    metrics = compute_text_quality_metrics("가 나!")

    assert judge_page(metrics, has_image=False) == ("pass", ["빈 페이지 (4자)"])
    assert judge_page(metrics, has_image=True) == ("ocr", ["텍스트 부족 (4자) 및 이미지 있음"])


# 모든 지표가 기준값과 정확히 같으면 pass 판정하는지 확인
def test_judge_page_threshold_values():
    metrics = TextQualityMetrics(
        total_chars=100, whitespace_ratio=0.0, hangul_ratio=0.1,
        broken_char_ratio=0.05, single_char_token_ratio=0.55, long_hangul_run_ratio=0.3,
    )

    assert judge_page(metrics, has_image=False) == ("pass", [])


# 모든 기준을 어기면 reparse 사유 4개가 순서대로 기록되는지 확인
def test_judge_page_all_reasons():
    metrics = TextQualityMetrics(
        total_chars=100, whitespace_ratio=0.0, hangul_ratio=0.09,
        broken_char_ratio=0.06, single_char_token_ratio=0.56, long_hangul_run_ratio=0.31,
    )

    verdict, reasons = judge_page(metrics, has_image=True)

    assert verdict == "reparse"
    assert reasons == [
        "깨진 문자 비율 0.0600 > 0.05", "한글 비율 0.0900 < 0.1",
        "긴 한글 연속 구간(공백 소실) 비율 0.3100 > 0.3", "한 글자 토큰 비율 0.5600 > 0.55",
    ]


# 100자 미만 페이지는 분포 지표 검사를 생략하고, 깨진 문자는 그대로 reparse 판정하는지 확인
def test_judge_page_short_page():
    # db_silson_2101 page 33: a 22-char title whose single-char token ratio is noise.
    title_metrics = compute_text_quality_metrics("제 3 절 제 도 성 특 별 약 관 가")
    broken_metrics = compute_text_quality_metrics("(cid:23)" * 5)

    assert title_metrics.single_char_token_ratio > 0.55
    assert judge_page(title_metrics, has_image=False) == (
        "pass", [f"짧은 페이지 ({title_metrics.total_chars}자), 분포 지표 검사 생략"],
    )
    assert judge_page(broken_metrics, has_image=False) == ("reparse", ["깨진 문자 비율 1.0000 > 0.05"])


# 점선 때문에 공백이 적은 목차는 pass, 공백이 사라진 텍스트는 reparse 판정하는지 확인
def test_judge_page_toc_vs_lost_spaces():
    # A table of contents has few spaces because of leader dots, but its words are still separated.
    table_of_contents = "\n".join(
        f"{number}. (보험금의 청구)" + "·" * 30 + str(40 + number) for number in range(1, 20)
    )
    lost_spaces = "이은행여신거래기본약관은하나은행과거래처와의상호신뢰를바탕으로여신거래의원활하고공정한처리를위하여만들어진것입니다" * 3

    toc_metrics = compute_text_quality_metrics(table_of_contents)
    lost_space_metrics = compute_text_quality_metrics(lost_spaces)

    assert toc_metrics.whitespace_ratio < 0.1
    assert toc_metrics.long_hangul_run_ratio == 0.0
    assert judge_page(toc_metrics, has_image=False) == ("pass", [])
    assert lost_space_metrics.long_hangul_run_ratio == 1.0
    assert judge_page(lost_space_metrics, has_image=False)[0] == "reparse"


# 15음절 이상 연속된 한글 구간만 비율에 포함되는지 확인
@pytest.mark.parametrize(("text", "ratio"), [("", 0.0), ("ABC 123", 0.0), ("가" * 14, 0.0), ("가" * 15 + " 나다", 15 / 17)])
def test_long_hangul_run_ratio(text: str, ratio: float):
    assert compute_long_hangul_run_ratio(text) == ratio


# 파싱 쪽 수와 PDF 쪽 수가 다르면 경고를 남기고, 짝이 없는 쪽은 이미지 없음으로 판정하는지 확인
def test_judge_result_page_mismatch(monkeypatch, capsys):
    document = DocumentRecord(doc_id="mismatch", format="pdf", path=Path("mismatch.pdf"))
    parse_result = ParseResult(
        doc_id=document.doc_id, parser_name="pdfplumber", succeeded=True, page_texts=["", ""],
    )
    monkeypatch.setattr(
        parse_judgement, "detect_page_visual_objects",
        lambda path: [PageImageInfo(page=1, image_count=2, has_image=True)],
    )

    report = judge_parsed_result(document, parse_result)

    assert report.verdict == "ocr"
    assert (report.usable_page_count, report.ocr_page_count) == (1, 1)
    assert [(page.page, page.verdict, page.has_image, page.image_count) for page in report.pages] == [
        (1, "ocr", True, 2),
        (2, "pass", False, 0),
    ]
    assert "[WARN] mismatch: 파싱 2쪽 / PDF 1쪽" in capsys.readouterr().out


# pass 쪽만 원래 쪽 번호로 청킹하고, 제외된 쪽을 건너 조항을 잇지 않는지 확인
def test_chunk_pass_pages_excluded(monkeypatch, tmp_path):
    # The third page starts with a continuation before its first heading.
    document = DocumentRecord(doc_id="mixed", format="pdf", path=Path("mixed.pdf"))
    first_page = "제11조(보험수익자의 지정) 보험수익자는 계약자가 정할 수 있습니다."
    last_page = "피보험자로 정합니다.\n제12조(대표자의 지정) 계약자는 각 대표자를 지정하여야 합니다."
    parse_result = ParseResult(
        doc_id=document.doc_id, parser_name="pdfplumber", succeeded=True,
        page_texts=[first_page, "", last_page, "(cid:23)" * 5],
    )
    monkeypatch.setattr(
        parse_judgement, "detect_page_visual_objects",
        lambda path: [
            PageImageInfo(page=page, image_count=int(page == 2), has_image=page == 2)
            for page in range(1, 5)
        ],
    )

    # OCR and reparse pages both stay out of the chunk spans.
    report = judge_parsed_result(document, parse_result)
    chunks = chunk_pass_pages(document, parse_result, report)

    # Article 11 cannot absorb the prefix from page 3 across the gap.
    assert report.verdict == "reparse"
    assert report.reasons == ["재추출 필요 1쪽", "OCR 필요 1쪽"]
    assert [page.verdict for page in report.pages] == ["pass", "ocr", "pass", "reparse"]
    assert [(chunk.article, chunk.page_start, chunk.page_end) for chunk in chunks] == [
        ("제11조", 1, 1), ("", 3, 3), ("제12조", 3, 3),
    ]
    assert chunks[0].text == first_page + "\n"
    assert chunks[1].text == "피보험자로 정합니다.\n"

    # The document CSV identifies the same excluded pages by their original numbers.
    output = tmp_path / "parse_report.csv"
    save_parse_report_csv([DocumentRunReport(parse_result, report, len(chunks))], output)
    with output.open(encoding="utf-8-sig", newline="") as report_file:
        row, = csv.DictReader(report_file)
    assert json.loads(row["reparse_pages"]) == [4]
    assert json.loads(row["ocr_pages"]) == [2]


# PDF 파싱이 실패하면 reparse로 판정하고 두 CSV에 기록하는지 확인
def test_failed_pdf_parse_report(monkeypatch, tmp_path):
    document = DocumentRecord(doc_id="bad", format="pdf", path=tmp_path / "bad.pdf")

    def fail_to_parse_pdf(path: Path) -> list[str]:
        raise ValueError("unreadable PDF")

    # The fallback parsers are deliberately unavailable during the default path.
    monkeypatch.setattr(run_parse_documents, "PDF_PARSERS", {"pdfplumber": fail_to_parse_pdf})
    parse_result = parse_document_with_default_parser(document)
    report = judge_parsed_result(document, parse_result)

    # A failed extraction still has a document verdict in the report CSV.
    assert not parse_result.succeeded
    assert report.verdict == "reparse"
    assert report.reasons == ["파싱 실패: ValueError: unreadable PDF"]
    assert chunk_pass_pages(document, parse_result, report) == []

    # The document report includes the failure, and the page report leaves the page number blank.
    document_csv = tmp_path / "parse_report.csv"
    page_csv = tmp_path / "parse_page_report.csv"
    save_parse_report_csv([DocumentRunReport(parse_result, report, 0)], document_csv)
    save_parse_page_report_csv([report], page_csv)
    with document_csv.open(encoding="utf-8-sig", newline="") as report_file:
        row, = csv.DictReader(report_file)
    assert row["doc_verdict"] == "reparse"
    assert row["succeeded"] == "False"
    assert row["error_message"] == "ValueError: unreadable PDF"
    assert (row["total_chars"], row["chunk_count"], row["page_count"]) == ("0", "0", "0")
    assert row["reparse_pages"] == row["ocr_pages"] == "[]"
    with page_csv.open(encoding="utf-8-sig", newline="") as report_file:
        row, = csv.DictReader(report_file)
    assert (row["doc_id"], row["parser"], row["page"], row["doc_verdict"]) == ("bad", "pdfplumber", "", "reparse")


# --only 실행 시 문서별·페이지별 CSV와 청크 파일의 수치가 일치하는지 확인
def test_main_saves_reports(monkeypatch, tmp_path):
    # Set up a selected PDF with one usable page and one page requiring OCR.
    pdf_path = tmp_path / "mixed.pdf"
    pdf_path.touch()
    document = DocumentRecord(doc_id="mixed", format="pdf", path=pdf_path)
    unselected = DocumentRecord(doc_id="other", format="pdf", path=pdf_path)
    first_page = "제11조(보험수익자의 지정) 보험수익자는 계약자가 정할 수 있습니다."
    second_page = "표지"
    monkeypatch.setattr(run_parse_documents, "load_document_records_from_csv", lambda path: [document, unselected])
    monkeypatch.setattr(run_parse_documents, "PDF_PARSERS", {"pdfplumber": lambda path: [first_page, second_page]})
    monkeypatch.setattr(parse_judgement, "detect_page_visual_objects", lambda path: [
        PageImageInfo(page=1, image_count=0, has_image=False),
        PageImageInfo(page=2, image_count=1, has_image=True),
    ])

    # Redirect all CLI outputs and run only the selected document.
    chunks_path = tmp_path / "chunks.jsonl"
    monkeypatch.setattr(run_parse_documents, "PARSED_OUTPUT_DIR", tmp_path)
    monkeypatch.setattr(
        run_parse_documents, "save_chunks_to_jsonl",
        partial(run_parse_documents.save_chunks_to_jsonl, output_path=chunks_path),
    )
    monkeypatch.setattr("sys.argv", ["run_parse_documents.py", "--only", document.doc_id])
    run_parse_documents.main()

    # The document row agrees with the counts in the page report and chunk file.
    with (tmp_path / "parse_report.csv").open(encoding="utf-8-sig", newline="") as report_file:
        report, = csv.DictReader(report_file)
    with (tmp_path / "parse_page_report.csv").open(encoding="utf-8-sig", newline="") as report_file:
        page_rows = list(csv.DictReader(report_file))
    chunks = [json.loads(line) for line in chunks_path.read_text(encoding="utf-8").splitlines()]
    assert report["doc_id"] == document.doc_id
    assert report["doc_verdict"] == "ocr"
    assert report["doc_reasons"] == "OCR 필요 1쪽"
    assert report["total_chars"] == str(len(first_page) + len(second_page))
    assert report["chunk_count"] == str(len(chunks)) == "1"
    assert report["page_count"] == str(len(page_rows)) == "2"
    assert (report["usable_page_count"], report["ocr_page_count"], report["reparse_page_count"]) == ("1", "1", "0")
    assert json.loads(report["ocr_pages"]) == [2]
    assert report["reparse_pages"] == "[]"
    assert [(row["doc_id"], row["page"], row["page_verdict"]) for row in page_rows] == [
        (document.doc_id, "1", "pass"), (document.doc_id, "2", "ocr"),
    ]
