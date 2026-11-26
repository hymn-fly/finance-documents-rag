
## 수정 필요 사항
- DocumentRecord 필드 추가(메타 데이터)

## Todo
- [x] 파싱 데이터에 대한 클렌징 (- 1 - 이런 페이지 제거) - 구현 내용 파악 필요
- [x] 데이터 전처리 및 chunking - 구현 내용 파악 필요
- [x] 파싱된 데이터 validation (이후 어떤 노드로 연결할 지 정하기 위해 문서 판단 - reparse, ocr, pass. )
    - [ ] 표 데이터에 대한 고려 필요
- [ ] Ingestion Graph 구성 ()
    - [ ] Embedding Vector DB 어떤 것 쓸지
    - [ ] Embedding Model 어떤 것 쓸지 
- [ ] Indexing, Retrieve 로직 구현

## 아키텍처 기술적 고민
- 파싱 후 classify 할 때, 문서별로 판단 기준값(공백비율, 한글비율, 깨진 비율, 단음절 토큰 비율) 정한 과정

## 문제 해결
- pdfplumber 의 한계. 표 페이지에서 셀을 좌표 순서로 읽어 문장 순서가 잘못 이어붙여짐. PyMuPDF 는 블록 단위로 읽어서 이런 문제 해결하나 싶었지만 공백소실이 크게 존재. PyMuPDF 로 블록의 bbox와 순서를 가져옴. 각 bbox 영역을 pdfplumber 로 텍스트 추출. 표는 pdfplumber find_tables()로 찾아 파싱 (이 방법의 정확도는 RAG 를 통해 측정 필요함)
- 공백비율 계산 방식 변경 → [problem_solving_history.md](problem_solving_history.md)