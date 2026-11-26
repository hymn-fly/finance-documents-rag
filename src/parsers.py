from __future__ import annotations

import html as html_module
import re
import xml.etree.ElementTree as ElementTree
from pathlib import Path

from typing import TYPE_CHECKING

from schemas import (
    LayoutGap, OrderedBlockBoxes, PdfLayoutBox, PdfLayoutChar, PdfPageText,
    PdfReadingItems, PdfTableRegion,
)

if TYPE_CHECKING:
    from pdfplumber.page import Page as PlumberPage
    from pymupdf import Page as MuPage

PDFPLUMBER_X_TOLERANCE = 1.5
UPWARD_JUMP_TOLERANCE_PT = 5
JUMBLED_PAGE_MIN_JUMPS = 3
WIDE_BOX_MIN_WIDTH_RATIO = 0.6
COLUMN_GUTTER_MIN_WIDTH_PT = 8


def get_rotated_pymupdf_text_block_boxes(mu_page: MuPage) -> list[PdfLayoutBox]:
    from pymupdf import Rect

    rotation = mu_page.rotation_matrix
    rectangles = [Rect(block[:4]) * rotation for block in mu_page.get_text("blocks") if block[6] == 0]

    return [PdfLayoutBox(x0=rect.x0, top=rect.y0, x1=rect.x1, bottom=rect.y1) for rect in rectangles]


def count_upward_block_jumps(boxes: list[PdfLayoutBox]) -> int:
    return sum(
        previous.top - current.top > UPWARD_JUMP_TOLERANCE_PT
        and current.x0 <= previous.x0
        for previous, current in zip(boxes, boxes[1:])
    )


def is_block_stream_order_jumbled(boxes: list[PdfLayoutBox]) -> bool:
    return count_upward_block_jumps(boxes) >= JUMBLED_PAGE_MIN_JUMPS


def find_layout_gaps(intervals: list[tuple[float, float]], min_width: float = 0) -> list[LayoutGap]:
    gaps: list[LayoutGap] = []
    covered_end = float("-inf")

    for start, end in sorted(intervals):
        if covered_end != float("-inf") and start > covered_end and start - covered_end >= min_width:
            gaps.append(LayoutGap(start=covered_end, end=start))
        covered_end = max(covered_end, end)

    return gaps


def find_horizontal_gaps(boxes: list[PdfLayoutBox]) -> list[LayoutGap]:
    return find_layout_gaps([(box.top, box.bottom) for box in boxes])


def find_vertical_gaps(boxes: list[PdfLayoutBox], min_width: float) -> list[LayoutGap]:
    return find_layout_gaps([(box.x0, box.x1) for box in boxes], min_width)


def find_wide_boxes(
    boxes: list[PdfLayoutBox], region_width: float, *, min_width_ratio: float = WIDE_BOX_MIN_WIDTH_RATIO,
) -> list[PdfLayoutBox]:
    return [box for box in boxes if box.x1 - box.x0 >= region_width * min_width_ratio]


def split_boxes_at_horizontal_gap(
    boxes: list[PdfLayoutBox], gap: LayoutGap,
) -> tuple[list[PdfLayoutBox], list[PdfLayoutBox]]:
    return [box for box in boxes if box.bottom <= gap.start], [box for box in boxes if box.top >= gap.end]


def split_boxes_at_vertical_gap(
    boxes: list[PdfLayoutBox], gap: LayoutGap,
) -> tuple[list[PdfLayoutBox], list[PdfLayoutBox]]:
    return [box for box in boxes if box.x1 <= gap.start], [box for box in boxes if box.x0 >= gap.end]


def get_gap_width(gap: LayoutGap) -> float:
    return gap.end - gap.start


def sort_block_boxes_by_xy_cut(
    boxes: list[PdfLayoutBox], *,
    wide_box_min_width_ratio: float = WIDE_BOX_MIN_WIDTH_RATIO,
    column_gutter_min_width: float = COLUMN_GUTTER_MIN_WIDTH_PT,
) -> list[PdfLayoutBox]:
    if len(boxes) < 2:
        return boxes

    # Isolate wide headings or footers before looking for columns.
    horizontal_gaps = find_horizontal_gaps(boxes)
    region_width = max(box.x1 for box in boxes) - min(box.x0 for box in boxes)
    wide_boxes = find_wide_boxes(boxes, region_width, min_width_ratio=wide_box_min_width_ratio)
    adjacent_gaps = [
        gap for gap in horizontal_gaps
        if any(box.bottom == gap.start or box.top == gap.end for box in wide_boxes)
    ]

    # Otherwise keep each column together, then fall back to horizontal cuts.
    vertical_gaps = find_vertical_gaps(boxes, column_gutter_min_width)
    if adjacent_gaps:
        first, second = split_boxes_at_horizontal_gap(boxes, max(adjacent_gaps, key=get_gap_width))
    elif vertical_gaps:
        first, second = split_boxes_at_vertical_gap(boxes, max(vertical_gaps, key=get_gap_width))
    elif horizontal_gaps:
        first, second = split_boxes_at_horizontal_gap(boxes, max(horizontal_gaps, key=get_gap_width))
    else:
        return sorted(boxes, key=lambda box: box.top)

    # Apply the same thresholds to each remaining region.
    return [
        box
        for region in (first, second)
        for box in sort_block_boxes_by_xy_cut(
            region, wide_box_min_width_ratio=wide_box_min_width_ratio,
            column_gutter_min_width=column_gutter_min_width,
        )
    ]


def is_point_inside_box(x: float, y: float, box: PdfLayoutBox) -> bool:
    return box.x0 <= x <= box.x1 and box.top <= y <= box.bottom


def is_box_center_in_table(box: PdfLayoutBox, tables: list[PdfTableRegion]) -> bool:
    x, y = (box.x0 + box.x1) / 2, (box.top + box.bottom) / 2

    return any(is_point_inside_box(x, y, table.box) for table in tables)


def order_block_boxes_for_reading(
    boxes: list[PdfLayoutBox], tables: list[PdfTableRegion] | None = None,
) -> OrderedBlockBoxes:
    table_regions = tables or []
    text_boxes = [box for box in boxes if not is_box_center_in_table(box, table_regions)]

    if is_block_stream_order_jumbled(text_boxes):
        return OrderedBlockBoxes(boxes=sort_block_boxes_by_xy_cut(boxes), reading_order="xy_cut")

    return OrderedBlockBoxes(boxes=boxes, reading_order="stream")


def convert_table_rows_to_markdown(rows: list[list[str | None]]) -> str:
    width = max((len(row) for row in rows), default=0)
    if not width:
        return ""

    # Escape pipe characters and keep each cell on one Markdown line.
    table_lines: list[str] = []
    for row in rows:
        cells = ["<br>".join((cell or "").strip().splitlines()).replace("|", r"\|") for cell in row]
        cells.extend([""] * (width - len(cells)))
        table_lines.append("| " + " | ".join(cells) + " |")

    # Use the first extracted row as the Markdown header.
    table_lines.insert(1, "| " + " | ".join(["---"] * width) + " |")

    return "\n".join(table_lines)


def extract_table_regions_as_markdown(
    pl_page: PlumberPage, *, x_tolerance: float = PDFPLUMBER_X_TOLERANCE,
) -> list[PdfTableRegion]:
    regions: list[PdfTableRegion] = []
    for table in pl_page.find_tables():
        x0, top, x1, bottom = table.bbox
        regions.append(PdfTableRegion(
            box=PdfLayoutBox(x0=x0, top=top, x1=x1, bottom=bottom),
            markdown=convert_table_rows_to_markdown(table.extract(x_tolerance=x_tolerance)),
        ))

    return regions


def find_nearest_box_index(x: float, y: float, boxes: list[PdfLayoutBox]) -> int:
    def distance_to_box(box: PdfLayoutBox) -> float:
        dx = max(box.x0 - x, x - box.x1, 0)
        dy = max(box.top - y, y - box.bottom, 0)

        return dx * dx + dy * dy

    return min(range(len(boxes)), key=lambda index: distance_to_box(boxes[index]))


def find_reading_box_index(x: float, y: float, boxes: list[PdfLayoutBox]) -> int:
    for index, box in enumerate(boxes):
        if is_point_inside_box(x, y, box):
            return index

    return find_nearest_box_index(x, y, boxes)


def assign_chars_to_reading_items(
    chars: list[PdfLayoutChar], tables: list[PdfTableRegion], boxes: list[PdfLayoutBox],
) -> PdfReadingItems:
    # Keep table glyphs out of the plain text, and anchor each table only once.
    items = PdfReadingItems(
        block_chars=[[] for _ in boxes],
        table_chars=[[] for _ in tables],
        table_indices_by_block=[[] for _ in boxes],
    )
    for char in chars:
        x = (char["x0"] + char["x1"]) / 2
        y = (char["top"] + char["bottom"]) / 2

        # A table owns the character if its center lies inside the table bounds.
        for index, table in enumerate(tables):
            if is_point_inside_box(x, y, table.box):
                if not items.table_chars[index]:
                    block_index = find_reading_box_index(x, y, boxes)
                    items.table_indices_by_block[block_index].append(index)
                items.table_chars[index].append(char)
                break
        else:
            items.block_chars[find_reading_box_index(x, y, boxes)].append(char)

    return items


def build_page_text_from_reading_items(
    items: PdfReadingItems, tables: list[PdfTableRegion], *, x_tolerance: float = PDFPLUMBER_X_TOLERANCE,
) -> str:
    from pdfplumber.utils import extract_text

    # Insert each table at its anchor, keeping any text above it in the same block.
    sections: list[str] = []
    for chars, table_indices in zip(items.block_chars, items.table_indices_by_block, strict=True):
        for index in sorted(table_indices, key=lambda index: tables[index].box.top):
            table = tables[index]
            above_table = [char for char in chars if char["top"] < table.box.top]
            chars = [char for char in chars if char["top"] >= table.box.top]
            sections.append(extract_text(above_table, x_tolerance=x_tolerance) if above_table else "")
            sections.append(table.markdown)
        if chars:
            sections.append(extract_text(chars, x_tolerance=x_tolerance))

    return "\n".join(section.strip() for section in sections if section.strip())


def extract_page_text_with_pymupdf_layout(
    mu_page: MuPage, pl_page: PlumberPage, *, x_tolerance: float = PDFPLUMBER_X_TOLERANCE,
) -> PdfPageText:
    # Fall back to the whole page if PyMuPDF supplies no text boxes.
    boxes = get_rotated_pymupdf_text_block_boxes(mu_page)
    if not boxes:
        x0, top, x1, bottom = pl_page.bbox
        boxes = [PdfLayoutBox(x0=x0, top=top, x1=x1, bottom=bottom)]

    # Use the layout for ordering and pdfplumber for all text and table cells.
    tables = extract_table_regions_as_markdown(pl_page, x_tolerance=x_tolerance)
    ordered = order_block_boxes_for_reading(boxes, tables)
    items = assign_chars_to_reading_items(pl_page.chars, tables, ordered.boxes)

    return PdfPageText(
        page=pl_page.page_number, reading_order=ordered.reading_order,
        text=build_page_text_from_reading_items(items, tables, x_tolerance=x_tolerance),
    )


def parse_pdf_with_pymupdf_layout_and_pdfplumber_text(
    pdf_path: Path, *, x_tolerance: float = PDFPLUMBER_X_TOLERANCE,
) -> list[PdfPageText]:
    import pdfplumber
    import pymupdf

    # Match both libraries' pages by physical order.
    page_texts: list[PdfPageText] = []
    with pymupdf.open(pdf_path) as mu_document, pdfplumber.open(pdf_path) as pl_document:
        if len(mu_document) != len(pl_document.pages):
            raise ValueError(f"PDF page count mismatch: {len(mu_document)} vs {len(pl_document.pages)}")

        # Release each pdfplumber page's cached layout once its text is extracted.
        for mu_page, pl_page in zip(mu_document, pl_document.pages, strict=True):
            page_texts.append(extract_page_text_with_pymupdf_layout(mu_page, pl_page, x_tolerance=x_tolerance))
            pl_page.close()

    return page_texts


def parse_pdf_with_pdfplumber(pdf_path: Path) -> list[str]:
    import pdfplumber

    page_texts: list[str] = []

    # extract text page by page
    with pdfplumber.open(pdf_path) as pdf_document:
        for pdf_page in pdf_document.pages:
            page_texts.append(pdf_page.extract_text() or "")

    return page_texts


def parse_pdf_with_pymupdf(pdf_path: Path) -> list[str]:
    import pymupdf

    page_texts: list[str] = []

    # extract text page by page
    with pymupdf.open(pdf_path) as pdf_document:
        for pdf_page in pdf_document:
            page_texts.append(pdf_page.get_text("text") or "")

    return page_texts


def parse_pdf_with_pypdf(pdf_path: Path) -> list[str]:
    from pypdf import PdfReader

    pdf_reader = PdfReader(pdf_path)

    # extract text page by page
    return [pdf_page.extract_text() or "" for pdf_page in pdf_reader.pages]


def parse_hwp_or_hwpx_with_hwp_hwpx_parser(hwp_path: Path) -> list[str]:
    from hwp_hwpx_parser import Reader

    with Reader(hwp_path) as hwp_reader:
        document_text = hwp_reader.text

    return [document_text]


def read_file_as_utf8_text(file_path: Path) -> str:
    return file_path.read_bytes().decode("utf-8", "replace")


def convert_html_to_plain_text(raw_html: str) -> str:
    # drop script/style blocks entirely
    text = re.sub(r"<(script|style).*?</\1>", " ", raw_html, flags=re.S | re.I)

    # turn block-level closing tags into line breaks
    text = re.sub(r"<br\s*/?>|</p>|</div>|</tr>|</li>|</h\d>", "\n", text, flags=re.I)

    # strip remaining tags and decode entities
    text = html_module.unescape(re.sub(r"<[^>]+>", " ", text))

    # collapse whitespace and remove empty lines
    return "\n".join(" ".join(line.split()) for line in text.splitlines() if line.strip())


def convert_xml_to_plain_text(raw_xml: str) -> str:
    xml_root = ElementTree.fromstring(raw_xml)

    return "\n".join(text.strip() for text in xml_root.itertext() if text.strip())


def parse_html_file(html_path: Path) -> list[str]:
    return [convert_html_to_plain_text(read_file_as_utf8_text(html_path))]


def parse_xml_file(xml_path: Path) -> list[str]:
    return [convert_xml_to_plain_text(read_file_as_utf8_text(xml_path))]


def parse_plain_text_file(text_path: Path) -> list[str]:
    return [read_file_as_utf8_text(text_path)]
