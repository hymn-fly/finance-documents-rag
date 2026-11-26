import pytest

from chunking import (
    ArticleHeader,
    append_page_prefix_to_segment,
    find_article_headers,
    is_table_of_contents_line,
    remove_standalone_page_number_lines,
    remove_table_of_contents_lines,
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


# 지원하는 여러 형식의 쪽 번호만 있는 줄이 제거되는지 확인
@pytest.mark.parametrize(
    "page_number",
    [
        pytest.param("12", id="digits"),
        pytest.param(" - 12 - ", id="hyphens-with-padding"),
        pytest.param("— 12 —", id="em-dashes"),
        pytest.param("12 / 30", id="page-of-total"),
        pytest.param("(12)", id="parentheses"),
        pytest.param("p.12", id="page-prefix"),
    ],
)
def test_remove_page_number_formats(page_number: str):
    # The footer at the end of a parsed PDF page may have no final newline.
    body = "각 대표자를 1명 지정하여야 합니다.\n"

    assert remove_standalone_page_number_lines(body + page_number) == body


# 쪽 번호 줄을 제거해도 본문과 줄바꿈 문자는 그대로 남는지 확인
def test_remove_page_number_keeps_body():
    # The hyphenated footer appears in law_silson_std_pdf on page 7.
    first_line = "  보험수익자를 제3조(보험금의 지급사유) 제1호 및 제2호\r\n"
    following_lines = "\r\n계약서 12\r\n20 . . ."
    page_text = first_line + "- 7 -\r\n" + following_lines

    assert remove_standalone_page_number_lines(page_text) == first_line + following_lines


# 쪽 번호나 점선이 있는 줄만 목차 줄로 판별하는지 확인
@pytest.mark.parametrize(
    ("line", "expected"),
    [
        pytest.param("  제18조［청약의 철회］ 38  ", True, id="abl-numbered-entry"),
        pytest.param("제5조의2(특약 적용 범위) 21", True, id="subarticle-with-page"),
        pytest.param("제1조(목적) ······ 3", True, id="article-with-dot-leader"),
        pytest.param("1. 화재보험 ········ 55", True, id="section-with-dot-leader"),
        pytest.param("4. 실손의료보험 ········", True, id="dot-leader-without-page"),
        pytest.param("제 1조［목적］", False, id="abl-title-without-page-or-leader"),
        pytest.param("제5조의 2", False, id="subarticle-number-is-not-a-page"),
        pytest.param("제1조(목적) 이 계약은 다음과 같이 적용합니다.", False, id="article-with-body"),
        pytest.param("계약일 ...", False, id="abl-ellipsis"),
        pytest.param("20 . . .", False, id="im-bank-date-field"),
        pytest.param("· · ·", False, id="kbstar-standalone-ellipsis"),
        pytest.param("12", False, id="standalone-page-number"),
        pytest.param("   ", False, id="blank-line"),
    ],
)
def test_is_toc_line(
    line: str, expected: bool,
):
    assert is_table_of_contents_line(line) is expected


# 목차 줄만 제거하고 주변 텍스트는 보존하는지 확인
def test_remove_toc_lines():
    # Short excerpts from the ABL and standard insurance terms, with mixed line endings.
    heading = "  제 1조［목적］\r\n"
    body = "\r\n계약일 ...\n"
    page_text = (
        "제18조［청약의 철회］ 38\r\n"
        + heading
        + "1. 화재보험 ········ 55\r\n"
        + body
        + "4. 실손의료보험 ········"
    )

    assert remove_table_of_contents_lines(page_text) == heading + body


# 조 제목이 줄바꿈되어도 제목 전체와 시작 위치를 정확히 찾는지 확인
def test_find_headers_wrapped_title():
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


# 다양한 표기의 조 머리글에서 조 번호와 제목을 추출하는지 확인
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
def test_find_headers_title_formats(
    line: str, expected_article: str, expected_title: str,
):
    preceding_line = "표준약관\r\n"

    assert find_article_headers(preceding_line + line) == [
        ArticleHeader(len(preceding_line), expected_article, expected_title),
    ]


# 본문 속 조항 인용이나 너무 긴 일반 줄은 머리글로 보지 않는지 확인
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
def test_find_headers_rejects_citations(line: str):
    assert find_article_headers(line) == []


# 닫히지 않은 제목이 있어도 다음 조 머리글은 찾는지 확인
def test_find_headers_unclosed_title():
    unclosed_title = "제1조［목적\n"
    next_heading = "제2조［용어의 정의］"

    assert find_article_headers(unclosed_title + next_heading) == [
        ArticleHeader(len(unclosed_title), "제2조", "용어의 정의"),
    ]


# 쪽을 넘어가는 조항을 하나로 묶고 본문과 쪽별 위치를 보존하는지 확인
def test_split_segments_cross_page():
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


# 조 머리글이 없는 쪽들은 쪽별로 따로 나뉘는지 확인
def test_split_segments_headerless():
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


# 한 쪽의 여러 조항을 나누고, 뒤이은 머리글 없는 쪽은 별도 구간으로 두는지 확인
def test_split_segments_same_page():
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


# 쪽이 없거나 빈 쪽이면 구간을 만들지 않는지 확인
@pytest.mark.parametrize("pages", [[], [""]], ids=["no-pages", "empty-page"])
def test_split_segments_empty_input(pages: list[str]):
    assert split_pages_into_article_segments(pages) == []


# 다음 쪽 앞부분을 붙이면 본문, 쪽 범위, 위치 정보가 늘어나는지 확인
def test_append_page_prefix():
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
