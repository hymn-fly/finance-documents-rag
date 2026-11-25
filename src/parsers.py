import html as html_module
import re
import xml.etree.ElementTree as ElementTree
from pathlib import Path


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
