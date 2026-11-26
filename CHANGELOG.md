# CHANGELOG

## 2026-11-26 — PDF 읽기 순서와 글자 추출 결합

**What**
- `pymupdf_layout_pdfplumber_text`에서 회전을 보정한 PyMuPDF 블록 순서에 pdfplumber 글자를 배정. 표 앞뒤의 본문을 유지하고 각 표는 마크다운으로 한 번 출력.
- 표 밖의 블록에서 위쪽 역행이 3번 이상이면 XY-cut으로 재정렬. 페이지 CSV에 `page_reading_order`를 기록.
- 판정 지표 계산에서는 생성된 마크다운 표의 구분 문법을 제외. 파싱 결과와 청크에는 표 마크다운을 포함.

**Why**
- 두 단이 섞이는 문제와 PyMuPDF 전체 페이지 추출에서 발생한 한글 공백 소실을 함께 줄임.

**Changed files**
- `src/parsers.py`, `src/schemas.py`, `src/run_parse_documents.py` — 블록 순서, 표, 글자 배정과 기본 파서.
- `src/parse_judgement.py`, `src/text_quality.py`, `src/chunking.py` — 판정용 표 문법 정리와 출처 필드 변경.
- `src/analysis/compare_xy_cut_order.py`, `src/analysis/compare_x_tolerance.py` — 순서와 띄어쓰기 비교.
- `tests/test_parsers.py`, `tests/test_parse_judgement.py` — 합성 사례와 실제 DB·iM PDF 검증.

**Verify**
- `uv run --locked pytest` 71개 통과. DB 약관 10쪽의 90일 면책 문구와 iM 가계대출 7쪽의 ❷ 제목 순서 확인.
- 정상 순서 문서 23개에서 블록이 2개 이상인 985쪽의 Kendall tau 평균은 60%·8pt에서 0.8160, 70%·10pt에서 0.8150. 순서가 뒤집힌 최저 점수 사례는 쪽 번호가 본문보다 먼저 저장된 짧은 페이지였으며 기존 기준을 유지.
- 내용이 있는 표본 172쪽에서 x_tolerance 1.0·1.5·3.0의 평균 공백 비율은 0.2125·0.2122·0.2101, 한 글자 토큰 비율은 0.1433·0.1425·0.1345. 1.5에서 DB 10쪽의 띄어쓰기를 확인하고 기본값 유지.
- 변경 전 판정 CSV는 `data/parsed/before_layout_parser/`에 보관하고, 전체 실행 전후를 `data/parsed/layout_parser_comparison.txt`에 기록.
- 원본이 있는 49개 문서의 1,378쪽에서 `pass` 1,149 → 1,357쪽, `reparse` 219 → 11쪽, `ocr` 10 → 10쪽. PDF 11쪽에 XY-cut 적용. 청크 4,156 → 4,410개, PDF 파싱 시간 합계 128.03 → 97.66초.
- 새 `reparse` 1쪽은 `db_silson_2101` 6쪽. 한글 비율이 0.1015에서 0.0997로 내려가 0.1 기준에 걸림.

## 2026-11-26 — 표가 감지된 PDF 페이지를 PyMuPDF로 추출

**What**
- PDF 기본 파서 `pdfplumber_pymupdf_tables`는 `find_tables()`로 표가 감지된 쪽을 PyMuPDF로, 나머지를 pdfplumber로 추출하고 원래 쪽 순서로 병합.
- 페이지 판정 CSV의 `page_parser`에 실제 파서를 기록하고, 청크의 `page_parser_names`에는 해당 쪽 범위에 쓰인 파서를 중복 없이 기록.

**Why**
- DB손해보험 약관 10쪽처럼 pdfplumber가 두 단의 문구를 한 줄로 합치는 사례에서 읽기 순서를 보존.

**Changed files**
- `src/parsers.py`, `src/run_parse_documents.py`, `src/schemas.py` — 페이지별 파서 선택, 추출, 병합.
- `src/parse_judgement.py`, `src/chunking.py` — 페이지 판정 및 청크에 파서 출처 기록.
- `tests/test_parsers.py`, `tests/test_parse_judgement.py` — 병합, 파서 분기, 출처 기록, 실제 DB 약관 검증.

**Verify**
- `uv run --locked pytest`에서 63개 통과. 실제 DB 약관 10쪽의 파서와 담보 예시 문구 확인.
- `uv run python src/run_parse_documents.py` 실행 전후의 문서·페이지 판정 CSV를 대조. 변경 전 CSV는 `data/parsed/before_table_routing/`에 보관.
- PyMuPDF로 추출한 718쪽 중 209쪽이 `pass`에서 `reparse`로 바뀜. `law_silson_std_pdf` 27쪽과 `sonsa_silson_std_2024` 1쪽에서 공백 소실을 확인. `knia_7000`, `knia_18259`의 페이지 판정은 유지됨.
- 전체 청크는 4,295개에서 4,156개로 줄었고, PDF 파싱 시간 합계는 92.95초에서 128.03초로 늘어남. 새 청크 전체의 파서 목록을 페이지 판정 CSV와 대조.

## 2026-11-26 — 테스트 함수 이름 단축과 한글 설명 주석 추가

**What**
- 테스트 함수 24개의 이름을 40자 이하로 줄이고, 각 함수 위에 무엇을 확인하는지 한글 주석을 추가. 검증 내용은 그대로이며, 판정 사유 문구 `긴 한글 연속 구간(공백 소실) 비율`에 맞춰 기대값 한 곳만 수정.
- `AGENTS.md`에 테스트 함수 이름과 주석 지침 추가.

**Why**
- 시나리오를 모두 담은 긴 함수 이름이 가독성을 떨어뜨림.

**Changed files**
- `tests/test_chunking.py`, `tests/test_parse_judgement.py`, `AGENTS.md`.

**Verify**
- `uv run --locked pytest`에서 57개 통과.

## 2026-11-26 — 공백 비율 판정을 긴 한글 연속 구간 비율로 교체, 짧은 페이지 분포 지표 검사 생략

**What**
- 페이지 판정에서 공백 비율(`< 0.1`) 검사를 빼고 **긴 한글 연속 구간 비율**(`long_hangul_run_ratio`) 검사로 교체. 공백 없이 15음절 이상 이어진 구간에 속한 한글 글자 수 ÷ 전체 한글 글자 수이며, 0.3을 넘으면 `reparse`. 공백 비율은 참고용으로 계속 계산해 CSV에 남김.
- 100자 미만 페이지는 분포 지표(한글 비율, 긴 한글 연속 구간 비율, 한 글자 토큰 비율) 검사를 생략하고 `짧은 페이지 (N자), 분포 지표 검사 생략` 사유로 `pass`. `(cid:N)` 같은 깨진 문자 검사는 짧은 페이지에도 그대로 적용.
- `judge_page`의 `skip_space` 인자 삭제. 검사를 `find_broken_text_reasons`와 `find_text_distribution_reasons`로 나눔. 사유는 깨진 문자 검사 결과부터 기록.
- `parse_page_report.csv`에 `long_hangul_run_ratio` 열 추가.

**Why**
- 목차 페이지는 점선(`······`)이 글자 수만 늘려 공백 비율이 0.045까지 떨어지고, 22~35자짜리 표지와 제목 페이지는 공백 하나에도 비율이 크게 흔들려, 정상 페이지가 `reparse`로 판정됨(`db_silson_2101` 1·6·7·33쪽, `knia_7000` 17·29쪽, `law_silson_std_pdf` 1쪽).
- 공백이 사라지면 한글이 끊기지 않고 길게 이어지므로, 이 증상을 직접 측정. 자세한 분석은 `problem_solving_history.md` 참고.

**Changed files**
- `src/text_quality.py` — `compute_long_hangul_run_ratio`, `LONG_HANGUL_RUN_LENGTH`, `MAX_LONG_HANGUL_RUN_RATIO`, `MIN_CHARS_FOR_RATIO_CHECKS` 추가, `MIN_WHITESPACE_RATIO` 삭제.
- `src/schemas.py` — `TextQualityMetrics.long_hangul_run_ratio` 추가.
- `src/parse_judgement.py` — 판정 기준 교체, 짧은 페이지 처리, CSV 열 추가.
- `tests/test_parse_judgement.py` — 목차와 공백이 사라진 텍스트 구분, 짧은 페이지 생략, 15음절 경계, 경계값 테스트.
- `problem_solving_history.md`(신규), `README.md` — 문제 해결 기록과 링크.

**Verify**
- `uv run --locked pytest`에서 57개 통과.
- 전체 실행 결과 `pass` 41 → 43, `reparse` 6 → 4, `ocr` 2. 오판이던 7쪽이 `pass`로 바뀌고 `db_silson_2101`, `knia_7000`이 `pass`로 바뀜. 깨진 문자로 걸린 쪽(`hana_credit_terms_2009` 6쪽 등)은 그대로 `reparse`. 청크는 4,288개에서 4,295개로 늘어남.
- `hana_credit_terms_2009` pymupdf 출력(공백 사라짐)을 새 기준으로 판정하면 본문 2~6쪽이 모두 `reparse`(비율 0.64~0.74). `pass` 페이지 중 최댓값은 0.038.

## 2026-11-25 — 문서 판정 CSV에 재처리 대상 쪽 번호 추가

**What**
- `parse_report.csv`에 `reparse_pages`와 `ocr_pages` 열을 추가. 1부터 시작하는 원본 쪽 번호를 JSON 배열로 저장하며, 해당 쪽이 없으면 `[]`로 표시.

**Why**
- 문서별 판정에서 재추출이나 OCR이 필요한 쪽을 바로 확인할 수 있게 함.

**Changed files**
- `src/parse_judgement.py`, `tests/test_parse_judgement.py`.

**Verify**
- `uv run --locked pytest`로 배열 값과 빈 배열을 확인하고, 문서별 쪽 번호와 개수를 페이지 판정 CSV와 대조.

## 2026-11-25 — 문서별·페이지별 파싱 판정 CSV 분리

**What**
- 문서별 `parse_report.csv`에 파서, 판정과 사유, 추출 글자 수, 생성 청크 수, 판정별 쪽 수, 파싱 시간과 오류를 한 행으로 기록.
- 기존 페이지별 판정을 `parse_page_report.csv`에 저장.

**Why**
- 페이지별 행을 찾아보는 과정 없이 문서의 판정과 청킹 결과를 비교할 수 있게 함.

**Changed files**
- `src/parse_judgement.py`, `src/run_parse_documents.py`, `src/schemas.py` — 문서별 실행 결과와 두 CSV 저장.
- `tests/test_parse_judgement.py` — `--only` 실행과 파싱 실패의 CSV 출력 확인.

**Verify**
- `uv run --locked pytest`로 전체 테스트 통과 확인.
- 전체 실행 후 문서별 판정의 쪽 수, 추출 글자 수와 청크 수를 페이지별 판정, 파싱 요약, JSONL과 대조.

## 2026-11-25 — PDF 기본 파서와 페이지별 파싱 판정

**What**
- PDF는 `pdfplumber`로 한 번 파싱하고, 추출 텍스트의 다섯 지표와 페이지 이미지 개수로 `pass`, `reparse`, `ocr`를 판정.
- 문서에 재추출과 OCR 대상이 모두 있으면 문서 판정은 `reparse`로 두고 두 사유를 기록. PDF 파싱 예외는 `reparse`로 기록하고, 페이지가 없는 문서의 판정은 쪽 칸을 비워 CSV에 저장.
- 통과한 페이지만 원래 번호로 청킹하고 제외된 페이지를 건너 조항을 이어 붙이지 않음. 배치가 끝나면 `parse_summary.csv`, `parse_report.csv`, `chunks.jsonl` 저장.

**Why**
- 한 문서에서 재처리가 필요한 페이지를 식별하면서 통과한 페이지는 검색에 사용할 수 있게 함.

**Changed files**
- `src/run_parse_documents.py` — 기본 파서 실행, 판정과 청킹 연결, 배치 출력.
- `src/parse_judgement.py`, `src/schemas.py`, `src/text_quality.py` — 페이지 이미지, 텍스트 품질, 문서 판정, CSV.
- `src/chunking.py` — 판정에 따른 페이지 제외와 원래 쪽 번호 유지.
- `tests/test_parse_judgement.py` — 경계값, 페이지 수 불일치, 파싱 예외, 혼합 판정 문서의 청킹 검증.

**Verify**
- 전체 실행에서 문서 49개 판정. `pass` 41개, `reparse` 6개, `ocr` 2개, `fail` 0개. 원본이 없는 2개는 건너뜀.
- `knia_3500_scan`은 8쪽 모두 `ocr`, `hana_credit_terms_2009`는 6쪽 모두 `reparse`이며 전체 깨진 문자 비율 0.973, `hanacard_std_2017`은 `pass`.
- 원문 PDF 4쪽을 대조. `db_silson_2101` 1쪽은 짧은 표지의 공백 비율 0.0909로 `reparse` 판정됨. `inspect_chunks.py`와 전체 JSONL 검증에서 청크 4,288개가 모두 `pass` 범위에 속함을 확인.
- `uv run --locked pytest`에서 50개 통과.

## 2026-11-25 — 청킹 전 연속 줄바꿈 축소

**What**
- 페이지별 목차와 쪽 번호를 제거한 뒤 연속된 LF 두 개 이상을 LF 하나로 축소.

**Why**
- 파싱 또는 줄 제거로 생긴 연속 줄바꿈을 조항과 페이지 오프셋을 계산하기 전에 정리.

**Changed files**
- `src/chunking.py` — `clean_page_text`에서 페이지 정리와 줄바꿈 축소 적용.
- `tests/test_chunking.py` — 정리된 텍스트와 글자 수를 청킹 결과에서 검증.

**Verify**
- `uv run --locked pytest`로 전체 테스트 통과 확인.

## 2026-11-25 — 문서별 청크 수 로그 추가

**What**
- 청킹 후 `[CHUNK] <doc_id>: <count> chunks`를 출력하고, 채택 결과가 없는 문서는 `[NO CHUNK]`에서 0개를 표시.

**Why**
- 배치 실행 중 문서별 청킹 결과를 콘솔에서 확인할 수 있게 함.

**Changed files**
- `src/run_parse_documents.py` — `main()`에서 문서별 청크 수 출력.

**Verify**
- `main()`을 `--only fss_case_001 knia_3500_scan`으로 실행해 로그의 건수와 JSONL의 문서별 건수가 일치하는지 확인.

## 2026-11-25 — 조항 판별과 페이지 분할의 pytest 테스트

**What**
- `find_article_headers`, `split_pages_into_article_segments`, `append_page_prefix_to_segment`의 동작을 검증하는 테스트를 추가.
- 실제 약관과 법령의 파싱 텍스트를 짧게 발췌해 여러 줄 제목, 한 페이지의 여러 조항, 다음 페이지로 이어지는 조항의 본문과 페이지 오프셋을 확인.

**Why**
- 조항 판별과 페이지 경계를 수정할 때 실제 문서에서 확인한 동작을 재현하기 위해 발췌문을 테스트에 포함.

**Changed files**
- `tests/test_chunking.py` — 문서 발췌 예시와 경계 조건 테스트.
- `pyproject.toml`, `uv.lock` — pytest 개발 의존성, 테스트 경로 및 모듈 경로 설정.

**Verify**
- 저장소 루트에서 `uv run pytest`를 실행해 21개 테스트 통과 확인.

## 2026-11-25 — 채택된 파싱 결과의 조항 단위 청킹

**What**
- 기존 PDF 품질 검사를 통과한 첫 파싱 결과와 PDF 외 형식의 성공한 파싱 결과를 채택. 채택 결과가 없으면 `[NO CHUNK]`를 기록.
- 페이지에서 목차와 단독 쪽 번호 줄을 제거한 뒤 조항 머리로 구간을 나눔. 다음 페이지의 첫 조항 앞 텍스트는 앞 구간에 붙이고, 조항 머리가 없는 페이지는 본문 구간으로 처리.
- 최대 1200자와 약 200자 겹침으로 분할. 원본 쪽 범위, 문서 메타데이터와 파서 이름을 포함해 `data/chunks/chunks.jsonl`에 UTF-8로 저장. `--only` 실행도 파싱 요약과 JSONL을 덮어씀.

**Why**
- 조항과 쪽 위치를 검색 결과에서 추적하고, 특약에 반복되는 조항 번호와 문서 내 여러 본문 구간에도 고유 ID를 부여하기 위해 같은 문서·조항 이름에서 순번을 이어서 매김.

**Changed files**
- `src/chunking.py` — 쪽 정리, 조항 판별, 페이지 오프셋, 겹침 분할, JSONL 저장.
- `src/schemas.py` — 문서 메타데이터, `ArticleSegment`, `Chunk` 스키마.
- `src/run_parse_documents.py` — 파싱 결과 채택과 청킹 연결.
- `.gitignore` — 생성된 청크 출력 제외.

**Verify**
- `uv run python src/run_parse_documents.py --only abl_cancer_2404 fss_case_001 hana_credit_terms_2009 knia_3500_scan`으로 출력 범위, 반복 조항과 본문 순번, 두 PDF의 `[NO CHUNK]` 확인.
- 전체 실행에서 47개 문서의 청크 4,341개를 검증. 최대 길이 1200자, ID 중복 0건이며, 조항별 순번·메타데이터·쪽 범위를 확인하고 겹침을 제거해 정리 후의 문서 텍스트를 정확히 복원함.
- ABL 약관에서 여러 줄로 추출된 괄호 제목과 반복 조항을, `fss_case_001`에서 조항 없는 본문 분할을 확인. ABL 약관의 일부 목차 줄은 추출 텍스트에 쪽 번호와 점선이 없어 명시된 규칙에 따라 남으며 조항 머리로 판별됨.

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
