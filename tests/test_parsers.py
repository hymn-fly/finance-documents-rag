from pathlib import Path
from types import SimpleNamespace

import pdfplumber
import pymupdf
import pytest

from chunking import clean_page_text
from parsers import (
    assign_chars_to_reading_items,
    build_page_text_from_reading_items,
    convert_table_rows_to_markdown,
    count_upward_block_jumps,
    extract_page_text_with_pymupdf_layout,
    get_rotated_pymupdf_text_block_boxes,
    order_block_boxes_for_reading,
    sort_block_boxes_by_xy_cut,
)
from schemas import PdfLayoutBox, PdfLayoutChar, PdfTableRegion


def make_box(x0: float, top: float, x1: float, bottom: float) -> PdfLayoutBox:
    return PdfLayoutBox(x0=x0, top=top, x1=x1, bottom=bottom)


def make_char(x: float, y: float, text: str) -> PdfLayoutChar:
    return PdfLayoutChar(x0=x, top=y, x1=x + 1, bottom=y + 1, text=text)


# 빈 셀, 여러 줄, 파이프와 열 수가 다른 행을 마크다운에 보존하는지 확인
def test_table_markdown_ragged_rows():
    rows = [["이름", None], ["가|나\n다", ""], ["마지막"]]

    assert convert_table_rows_to_markdown(rows) == (
        "| 이름 |  |\n| --- | --- |\n| 가\\|나<br>다 |  |\n| 마지막 |  |"
    )
    assert convert_table_rows_to_markdown([[], []]) == ""


# 정상적인 단 전환은 역행에서 제외하고 같은 단의 위쪽 이동만 세는지 확인
def test_count_jumps_distinguishes_columns():
    columns = [make_box(x, y, x + 20, y + 5) for x in (0, 40) for y in (0, 10, 20, 30)]
    reversed_column = list(reversed(columns[:4]))

    assert count_upward_block_jumps(columns) == 0
    assert count_upward_block_jumps(reversed_column) == 3


# 머리글과 하단 블록 사이에서 왼쪽 단과 오른쪽 단을 각각 읽는지 확인
def test_xy_cut_keeps_columns_together():
    header = make_box(0, 0, 100, 8)
    footer = make_box(0, 56, 100, 65)
    left = [make_box(0, y, 40, y + 10) for y in (14, 32)]
    right = [make_box(60, y, 100, y + 10) for y in (14, 32)]

    assert sort_block_boxes_by_xy_cut([footer, right[0], left[1], header, left[0], right[1]]) == [
        header, *left, *right, footer,
    ]


# 두 단의 문단 여백이 같은 높이에 있어도 가로로 섞어 읽지 않는지 확인
def test_xy_cut_keeps_aligned_columns():
    left = [make_box(0, y, 40, y + 10) for y in (0, 45)]
    right = [make_box(60, y, 100, y + 10) for y in (0, 45)]

    assert sort_block_boxes_by_xy_cut([right[0], left[1], left[0], right[1]]) == [*left, *right]


# 단 하나인 문서는 위쪽부터 정렬하는지 확인
def test_xy_cut_sorts_single_column():
    boxes = [make_box(0, y, 50, y + 4) for y in (0, 9, 22, 37)]

    assert sort_block_boxes_by_xy_cut(boxes[::-1]) == boxes


# 저장 순서는 정상일 때 유지하고 역행이 세 번이면 XY-cut을 쓰는지 확인
def test_reading_order_switches_on_jumps():
    boxes = [make_box(0, y, 50, y + 4) for y in (0, 9, 22, 37)]

    stream = order_block_boxes_for_reading(boxes)
    jumbled = order_block_boxes_for_reading(boxes[::-1])

    assert (stream.reading_order, stream.boxes) == ("stream", boxes)
    assert (jumbled.reading_order, jumbled.boxes) == ("xy_cut", boxes)


# 표 안 블록의 역행은 페이지 읽기 순서 판정에서 제외하는지 확인
def test_reading_order_ignores_table_jumps():
    boxes = [make_box(0, y, 20, y + 4) for y in (30, 20, 10, 0)]
    table = PdfTableRegion(box=make_box(0, 0, 20, 35), markdown="표")

    assert order_block_boxes_for_reading(boxes, [table]).reading_order == "stream"


# 표 우선, 가장 가까운 블록, 각 글자의 단일 배정을 함께 확인
def test_assign_chars_uses_one_destination():
    boxes = [make_box(0, 0, 20, 30), make_box(60, 0, 80, 30)]
    table = PdfTableRegion(box=make_box(5, 10, 75, 23), markdown="표")
    chars = [make_char(7, 12, "표"), make_char(70, 12, "셀"), make_char(55, 5, "밖"), make_char(5, 1, "글")]

    items = assign_chars_to_reading_items(chars, [table], boxes)

    assert items.table_chars == [chars[:2]]
    assert items.block_chars == [[chars[3]], [chars[2]]]
    assert items.table_indices_by_block == [[0], []]


# 두 블록에 걸친 표의 마크다운을 첫 글자의 블록에서 한 번만 출력하는지 확인
def test_build_page_emits_table_once(monkeypatch):
    boxes = [make_box(0, 0, 20, 30), make_box(60, 0, 80, 30)]
    table = PdfTableRegion(box=make_box(5, 10, 75, 23), markdown="| 표 |")
    chars = [make_char(5, 1, "앞"), make_char(7, 12, "표"), make_char(70, 12, "셀"), make_char(70, 27, "뒤")]
    items = assign_chars_to_reading_items(chars, [table], boxes)
    monkeypatch.setattr(pdfplumber.utils, "extract_text", lambda chars, **kwargs: "".join(c["text"] for c in chars))

    assert build_page_text_from_reading_items(items, [table]) == "앞\n| 표 |\n뒤"


# 90도 회전 보정이 텍스트 블록에 적용되고 이미지 블록은 제외되는지 확인
def test_rotated_boxes_match_pdfplumber():
    mu_page = SimpleNamespace(
        rotation_matrix=pymupdf.Matrix(0, 1, -1, 0, 100, 0),
        get_text=lambda mode: [(10, 20, 30, 40, "text", 0, 0), (0, 0, 10, 10, "", 1, 1)],
    )

    assert get_rotated_pymupdf_text_block_boxes(mu_page) == [make_box(60, 10, 80, 30)]


# 목차처럼 보이는 값이 마크다운 셀에 있어도 페이지 정리에서 행이 보존되는지 확인
def test_clean_page_keeps_markdown_rows():
    markdown = "| 제1조 목적 ··· 3 |\n| --- |\n| 12 |"

    assert clean_page_text(markdown) == markdown


def read_pdf_page(document: str, page_number: int):
    path = Path(__file__).resolve().parents[1] / "data" / "raw" / f"{document}.pdf"
    if not path.exists():
        pytest.skip(f"원본 PDF가 없음: {document}")

    with pymupdf.open(path) as mu_pdf, pdfplumber.open(path) as pl_pdf:
        return extract_page_text_with_pymupdf_layout(mu_pdf[page_number - 1], pl_pdf.pages[page_number - 1])


# DB 약관 10쪽에서 두 단이 섞이지 않고 90일 면책 문구의 띄어쓰기가 유지되는지 확인
def test_layout_db_page_ten():
    page = read_pdf_page("db_silson_2101", 10)
    text = " ".join(page.text.split())

    assert "가입 후 1년간 보장 제외 질병입원특약" not in text
    assert "가입 후 90일간 보장 제외" in text


# iM 가계대출 7쪽에서 XY-cut이 ❷ 제목을 해당 예시 앞으로 옮기는지 확인
def test_layout_im_page_seven():
    page = read_pdf_page("im_household_2025", 7)

    assert page.reading_order == "xy_cut"
    assert page.text.index("❷") < page.text.index("(예시)")
