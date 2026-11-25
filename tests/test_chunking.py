import pytest

from chunking import (
    ArticleHeader,
    append_page_prefix_to_segment,
    find_article_headers,
    split_pages_into_article_segments,
)
from schemas import ArticleSegment, PageCharOffset


# Excerpts from law_silson_std_pdf, pages 7–8, after page number removal.
BENEFICIARY_DESIGNATION = (
    "제11조(보험수익자의 지정) 이 계약에서 계약자가 보험수익자를 지정하\n"
    "지 않은 때에는 보험수익자를 제3조(보험금의 지급사유) 제1호 및 제2호"
)
BENEFICIARY_DESIGNATION_CONTINUATION = (
    "의 경우는 계약자로 하고, 같은 조 제3호는 피보험자의 법정상속인, 제4\n"
    "호 및 제5호는 피보험자로 합니다.\n"
)
REPRESENTATIVE_DESIGNATION = (
    "제12조(대표자의 지정) ① 계약자 또는 보험수익자가 2명 이상인 경우에는\n"
    "각 대표자를 1명 지정하여야 합니다."
)


def test_find_article_headers_preserves_wrapped_abl_title_and_offsets():
    # abl_cancer_2404, page 26, preserves a line wrap within the article title.
    preceding_line = "험금을 감액하여 지급하는 방법을 말합니다.\n"
    wrapped_title = (
        "“암”, “유방암”, “전립선암”, “기타피부암”, “중증갑상선암”, “중증 이외의 갑\n"
        "상선암” 및 “대장점막내암”의 정의 및 진단확정"
    )
    article_excerpt = f"제 3조［{wrapped_title}］\n"
    page_text = preceding_line + article_excerpt + "제 4조［“제자리암”의 정의 및 진단확정］"

    assert find_article_headers(page_text) == [
        ArticleHeader(len(preceding_line), "제3조", wrapped_title),
        ArticleHeader(len(preceding_line + article_excerpt), "제4조", "“제자리암”의 정의 및 진단확정"),
    ]


@pytest.mark.parametrize(
    ("line", "expected_article", "expected_title"),
    [
        pytest.param("제4조의2 대출계약의 철회", "제4조의2", "대출계약의 철회", id="hana-plain-title"),
        pytest.param(
            "제16조의2(방문판매 및 전화권유판매 임직원의 명부 작성 등)",
            "제16조의2",
            "방문판매 및 전화권유판매 임직원의 명부 작성 등",
            id="consumer-protection-act",
        ),
        pytest.param("  제 5 조 의 2 [적용 범위]", "제5조의2", "적용 범위", id="spaced-number"),
        pytest.param("제7조【보험금의 청구】", "제7조", "보험금의 청구", id="corner-brackets"),
        pytest.param(
            "제28조(강제집행 등으로 인한 해지계약의 특별부활(효력회복)) ① 회사",
            "제28조",
            "강제집행 등으로 인한 해지계약의 특별부활(효력회복)",
            id="standard-terms-nested-brackets",
        ),
        pytest.param("제1조 " + "가" * 26, "제1조", "가" * 26, id="30-character-plain-line"),
    ],
)
def test_find_article_headers_extracts_qualified_titles(
    line: str, expected_article: str, expected_title: str,
):
    preceding_line = "표준약관\r\n"

    assert find_article_headers(preceding_line + line) == [
        ArticleHeader(len(preceding_line), expected_article, expected_title),
    ]


@pytest.mark.parametrize(
    "line",
    [
        pytest.param("제12조 및 제13조에 따른 10% 해당액과", id="db-terms-citation"),
        pytest.param("제12조에 따라 처리합니다.", id="pursuant-to"),
        pytest.param('제12조 중 "계약"을 변경한다.', id="quoted-citation"),
        pytest.param("제12조 제2항을 적용합니다.", id="paragraph-reference"),
        pytest.param("제12조의 규정에 따릅니다.", id="provision-reference"),
        pytest.param("제1조 " + "가" * 27, id="31-character-plain-line"),
        pytest.param("보험수익자를 제3조(보험금의 지급사유)에 따라 정합니다.", id="inline-citation"),
    ],
)
def test_find_article_headers_rejects_citations_or_overlong_plain_lines(line: str):
    assert find_article_headers(line) == []


def test_find_article_headers_resumes_after_an_unclosed_title():
    unclosed_title = "제1조［목적\n"
    next_heading = "제2조［용어의 정의］"

    assert find_article_headers(unclosed_title + next_heading) == [
        ArticleHeader(len(unclosed_title), "제2조", "용어의 정의"),
    ]


def test_split_pages_into_article_segments_preserves_body_and_cross_page_article():
    # The excerpts contain two source pages, numbered 1–2 by the splitter.
    leading_text = "게 도달된 것으로 봅니다.\n"
    page_1_article_text = BENEFICIARY_DESIGNATION + "\n"
    pages = [
        leading_text + BENEFICIARY_DESIGNATION,
        BENEFICIARY_DESIGNATION_CONTINUATION + REPRESENTATIVE_DESIGNATION,
    ]

    segments = split_pages_into_article_segments(pages)

    # The first heading separates the leading body, and the next page continues article 11.
    assert [
        (segment.article, segment.article_title, segment.page_start, segment.page_end)
        for segment in segments
    ] == [
        ("", "", 1, 1),
        ("제11조", "보험수익자의 지정", 1, 2),
        ("제12조", "대표자의 지정", 2, 2),
    ]
    leading_segment, continued_segment, next_segment = segments
    assert [segment.text for segment in segments] == [
        leading_text,
        page_1_article_text + BENEFICIARY_DESIGNATION_CONTINUATION,
        REPRESENTATIVE_DESIGNATION,
    ]

    # Offsets are local to each segment and use an exclusive end index.
    page_boundary = len(page_1_article_text)
    assert leading_segment.page_char_offsets == [PageCharOffset(page=1, start=0, end=len(leading_text))]
    assert continued_segment.page_char_offsets == [
        PageCharOffset(page=1, start=0, end=page_boundary),
        PageCharOffset(page=2, start=page_boundary, end=len(continued_segment.text)),
    ]
    assert next_segment.page_char_offsets == [
        PageCharOffset(page=2, start=0, end=len(REPRESENTATIVE_DESIGNATION)),
    ]
    assert "".join(segment.text for segment in segments) == "\n".join(pages)


def test_split_pages_into_article_segments_keeps_headerless_pages_separate():
    # abl_cancer_2404, excerpts from the cover and greeting on pages 1–2.
    cover = "보험약관\n무배당\nABL인터넷암보험Ⅲ\n(갱신형)"
    greeting = "CEO인사말 존경하는 고객님께,\nABL생명의 소중한 가족이 되어주신 고객님께"

    segments = split_pages_into_article_segments([cover, greeting])

    assert segments == [
        ArticleSegment(
            text=cover + "\n", article="", article_title="", page_start=1, page_end=1,
            page_char_offsets=[PageCharOffset(page=1, start=0, end=len(cover) + 1)],
        ),
        ArticleSegment(
            text=greeting, article="", article_title="", page_start=2, page_end=2,
            page_char_offsets=[PageCharOffset(page=2, start=0, end=len(greeting))],
        ),
    ]


def test_split_pages_into_article_segments_splits_same_page_headings_before_headerless_page():
    # abl_cancer_2404 has two headings on page 24 and no heading on page 25.
    article_1 = (
        "제 1조［목적］\n"
        "이 보험계약(이하 “계약”이라 합니다)은 보험계약자(이하 “계약자”라 합니다)와 보험회사(이\n"
        "하 “회사”라 합니다) 사이에 제6조(보험금의 지급사유)에 해당하는 피보험자의 위험을 보장\n"
        "하기 위하여 체결됩니다.\n"
    )
    article_2 = (
        "제 2조［용어의 정의］\n"
        "이 계약에서 사용되는 용어의 정의는, 이 계약의 다른 조항에서 달리 정의되지 않는 한 다음\n"
        "과 같습니다."
    )
    headerless_page = (
        "분류에 따라 이 약관에서 보장하는 질병 또는 재해 해당 여부가 판단된 경우, 이후\n"
        "한국표준질병·사인분류 개정으로 질병·사인분류가 변경되더라도 이 약관에서 보장하"
    )

    segments = split_pages_into_article_segments([article_1 + article_2, headerless_page])

    # A citation inside article 1 stays in its text, and page 25 becomes its own body segment.
    assert [
        (segment.article, segment.page_start, segment.page_end) for segment in segments
    ] == [("제1조", 1, 1), ("제2조", 1, 1), ("", 2, 2)]
    assert [segment.text for segment in segments] == [article_1, article_2 + "\n", headerless_page]


@pytest.mark.parametrize("pages", [[], [""]], ids=["no-pages", "empty-page"])
def test_split_pages_into_article_segments_returns_no_segments_for_empty_input(pages: list[str]):
    assert split_pages_into_article_segments(pages) == []


def test_append_page_prefix_to_segment_extends_text_and_page_range():
    # Include the inter-page newline already supplied by the caller.
    original_text = BENEFICIARY_DESIGNATION + "\n"
    original_offset = PageCharOffset(page=7, start=0, end=len(original_text))
    segment = ArticleSegment(
        text=original_text, article="제11조", article_title="보험수익자의 지정",
        page_start=7, page_end=7, page_char_offsets=[original_offset],
    )

    append_page_prefix_to_segment(segment, BENEFICIARY_DESIGNATION_CONTINUATION, page=8)

    assert segment.text == original_text + BENEFICIARY_DESIGNATION_CONTINUATION
    assert (segment.article, segment.article_title) == ("제11조", "보험수익자의 지정")
    assert (segment.page_start, segment.page_end) == (7, 8)
    assert segment.page_char_offsets == [
        original_offset,
        PageCharOffset(page=8, start=len(original_text), end=len(segment.text)),
    ]
