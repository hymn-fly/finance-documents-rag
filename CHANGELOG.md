# CHANGELOG

## 2026-11-24 — documents.csv 문서 파싱 코드 추가

**What**
- documents.csv의 각 파일을 형식별 파서로 읽어 텍스트를 `data/parsed/<doc_id>/<parser>.txt`로 저장하고, 파서별 결과 요약을 `data/parsed/parse_summary.csv`에 기록.
- PDF: pdfplumber / pymupdf / pypdf 세 가지를 모두 실행(비교용). HWP/HWPX: hwp-hwpx-parser. HTML/XML: 제공된 참고 코드 기반. TXT: 그대로 읽기.

**Why**
- 형식별 파싱 품질을 비교하고 이후 RAG 인덱싱 입력을 만들기 위한 첫 단계.
- csv의 `binary_office`는 hwp와 hwpx를 모두 포함하므로 CSV `format` 대신 실제 파일 확장자로 파서를 선택.
- 파서 하나가 실패해도 전체 배치가 중단되지 않도록 예외를 `ParseResult.error_message`에 기록. 파일이 없으면(`degraded_*` 2건) SKIP 처리.

**Changed files**
- `pyproject.toml`, `uv.lock` (uv로 의존성 추가: pdfplumber, pymupdf, pypdf, hwp-hwpx-parser, pydantic)
- `src/schemas.py` (DocumentRecord, ParseResult)
- `src/parsers.py` (형식별 파싱 함수)
- `src/run_parse_documents.py` (CSV 로드, 파서 선택, 실행, 저장)

**Verify**
- `uv run python src/run_parse_documents.py` 실행 후 `data/parsed/parse_summary.csv`에서 파서별 성공 여부/글자 수 확인.
- 일부 문서만: `uv run python src/run_parse_documents.py --only law_fcpa_xml`

## 2026-11-24 — PDF 파서별 텍스트 품질 요약 CSV 추가

**What**
- `data/parsed/parsed_summary_pdf.csv` 생성: 행=PDF doc_id, 열=파서(pdfplumber/pymupdf/pypdf)별 `chars`, `whitespace_ratio`, `hangul_ratio`, `broken_char_ratio`.
- 비율은 전체 문자 수 대비. 깨진 문자 = U+FFFD, 사설영역(PUA), 제어문자(\n \r \t 제외), `(cid:N)` 글리프 표기.

**Why**
- PDF 파서 3종의 추출 품질(공백 소실/과다, 한글 비중, 깨짐)을 한눈에 비교하기 위해.

**Changed files**
- `src/schemas.py` (TextQualityMetrics 추가)
- `src/build_pdf_parse_summary.py` (신규)

**Verify**
- `uv run python src/build_pdf_parse_summary.py` 실행 후 `chars`가 `parse_summary.csv`의 chars와 일치하는지 확인.

## 2026-11-24 — PDF 파서별 비율 히스토그램 추가

**What**
- 공백/한글/깨진 문자 비율 각각에 대해, PDF 파서 3종(pdfplumber/pymupdf/pypdf)의 문서별 분포 히스토그램을 이미지 1장(서브플롯 3개)씩, 총 3장 생성.

**Why**
- 파서별 추출 품질이 문서 간에 어떻게 퍼져 있는지, 이상치 문서가 있는지 보기 위해.

**Changed files**
- `src/plot_pdf_parse_histograms.py` (신규), `pyproject.toml`, `uv.lock` (matplotlib, pandas 추가)
- 산출물: `data/parsed/plots/hist_{whitespace,hangul,broken_char}_ratio.png`

**Verify**
- `uv run python src/plot_pdf_parse_histograms.py` 실행 후 이미지 3장 생성 확인.

## 2026-11-24 — 페이지 단위 상세 CSV 추가 및 히스토그램을 페이지 기준으로 변경

**What**
- `data/parsed/parsed_detail_pdf.csv` 생성: 행=(doc_id, page), 열=파서별 chars/공백/한글/깨진 문자 비율. 0자 페이지는 비율을 공란으로 둠.
- 히스토그램 3장을 문서 단위 → 페이지 단위 데이터로 다시 생성. 깨진 문자 비율은 대부분 0이라 y축을 log 스케일로 표시.

**Why**
- 문서 평균에 가려진 페이지별 이상치(깨진 페이지, 공백 소실 페이지)를 보기 위해.

**Changed files**
- `src/build_pdf_parse_detail.py` (신규), `src/plot_pdf_parse_histograms.py` (입력을 detail CSV로 변경, log 축)

**Verify**
- `uv run python src/build_pdf_parse_detail.py && uv run python src/plot_pdf_parse_histograms.py`
- 문서별 페이지 chars 합이 `parsed_summary_pdf.csv`의 chars와 일치하는지 확인.

## 2026-11-24 — PDF 파싱을 품질 기준 기반 순차 폴백으로 변경

**What**
- PDF는 pdfplumber → pymupdf → pypdf 순서로 시도하고, 결과가 아래 기준을 모두 만족하면 즉시 채택(나머지 파서는 실행하지 않음).
  - 공백 비율 >= 0.1, 한글 비율 >= 0.1, 깨진 문자 비율 < 0.05 (문서 전체 텍스트 기준)
- 세 파서 모두 기준 미달이면 시도한 결과를 모두 저장하고 로그에 남김.
- 문자 품질 계산 함수를 `src/text_quality.py`로 분리(순환 import 방지, 임계값 상수 + `is_text_quality_acceptable` 추가).

**Why**
- 모든 파서를 항상 돌리면 시간이 오래 걸리고(특히 pdfplumber), 첫 결과가 충분히 좋으면 나머지는 불필요.

**Changed files**
- `src/run_parse_documents.py` (parse_document_with_fallback 등 추가, main 루프 변경)
- `src/text_quality.py` (신규), `src/analysis/build_pdf_parse_summary.py` (품질 함수 import로 변경)

**Verify**
- `uv run python src/run_parse_documents.py --only hana_credit_terms_2009 hanacard_std_2017`
  - hanacard_std_2017: pdfplumber만 실행 후 종료. hana_credit_terms_2009: 3개 모두 기준 미달이라 전부 시도.
