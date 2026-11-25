# DART Risk Insight

DART(전자공시시스템) 공시 데이터를 기반으로 재무비율을 자동 계산하고,
LLM으로 리스크 요인을 추출·요약하는 미니 대시보드. 상세 요구사항은
[PRD.md](./PRD.md) 참고.

## 아키텍처

```
frontend/streamlit_app.py  →  backend/app (FastAPI)  →  DART OpenAPI / OpenRouter
```

- `backend/app/dart_client.py` — 기업 검색, 공시 목록, 재무제표 조회
- `backend/app/financial.py` — 재무비율 계산 (부채비율/영업이익률/ROE/유동비율), **LLM 미사용**
- `backend/app/report_parser.py` — 사업보고서 원문에서 "사업의 위험" 섹션 추출 (best-effort)
- `backend/app/llm_client.py` — OpenRouter 호출, 계산된 수치 + 위험요인 원문을 넣어 구조화 JSON(`AnalysisReport`) 강제 출력. 재무 수치는 계산값으로 덮어쓰고, 위험요인은 원문 인용문 대조로 검증 (아래 "신뢰성 설계")
- `backend/app/news_client.py` — 네이버 뉴스 검색 API로 기업 관련 최신 기사 N건 조회 (P1)
- `backend/app/valuation.py` — PER/PBR 계산: pykrx 종가(로그인 불필요) × DART 발행주식총수로 시가총액 직접 산출 (P2)
- `backend/app/disclosures.py` — 감사의견(`accnutAdtorNmNdAdtOpinion`)/배당정보(`alotMatter`) 파싱 (P3)
- `backend/app/cache.py` — SQLite 기반 분석 결과 캐시(24시간 TTL)
- `frontend/streamlit_app.py` — "기업 분석"/"기업 비교" 탭 UI, 재무 차트, 리스크 레이더/트렌드 차트, PER/PBR·배당 카드, 감사의견 배지, 전체 재무제표 원본 보기, 관련 뉴스 목록
- `frontend/report_utils.py` — 분석 결과 → Markdown 리포트, 비교 결과 → CSV/HTML 표 변환 (다운로드 버튼용, 새 백엔드 불필요)
- `frontend/theme.py` — 색상/스타일 상수 (카테고리 팔레트, 상태 배지 색상, 카드 CSS)
- `.streamlit/config.toml` — 파스텔 하늘색 테마 설정

## 신뢰성 설계 (LLM 환각 방지)

핵심 원칙은 "계산은 코드, 해석은 LLM"이다.

1. **재무 수치는 LLM이 만들지 않는다**: 비율·PER/PBR은 Python이 계산하고, LLM이 출력한
   수치는 검증 후 항상 계산값으로 덮어쓴다.
2. **위험요인은 원문 근거를 요구한다**: LLM은 각 위험요인마다 입력 원문에서 그대로 복사한
   인용문(`evidence_quote`)을 함께 반환해야 한다.
3. **인용문을 코드로 대조한다**: 인용문이 입력 원문에 실제로 존재하는지(공백 정규화 후 부분
   문자열 일치, 최소 15자) 확인하고, 출처 소제목은 LLM의 주장 대신 코드가 인용문이 발견된
   소제목으로 채운다. 통과하지 못한 항목은 사유와 함께 1회 재요청하고, 그래도 통과하지 못하면
   버린다. 원문이 없으면 위험요인은 빈 목록이 된다.
4. **형식은 스키마로 강제한다**: Pydantic으로 카테고리/심각도 허용값을 검증하고, 실패 시
   오류 내용을 알려주며 재요청한다.

## LLM 모델 선택

모델은 OpenRouter를 통해 호출하며 `.env`의 `OPENROUTER_MODEL`로 바꿀 수 있다.

- **이력**: 초기에는 `qwen3-235b-a22b`를 썼으나 응답이 특정 토큰을 무한 반복하는 현상이 관측되어
  `deepseek/deepseek-chat`으로 교체했다. 이후 무료 모델들을 같은 입력으로 비교해 현재 기본값을
  정했다.
- **비교 방법**: 삼성전자 2025 사업보고서의 위험 원문(3,000자)과 계산된 재무비율을 동일하게 넣고
  `generate_analysis_report`를 모델별로 실행해 소요 시간, LLM 호출 횟수, 근거 검증 통과 건수,
  요약 품질을 확인했다 (모델당 1회 측정이라 참고용).

| 모델 | 소요 | 검증 통과 | 요약 품질 |
|---|---|---|---|
| `nvidia/nemotron-3-ultra-550b-a55b:free` (기본값) | 37초 | 5/5 (1회 호출) | 계산된 수치를 정확히 인용해 서술 |
| `inclusionai/ling-3.2-flash:free` | 31초 | 5/5 (1회 호출) | 수치 없이 "두 자릿수 초반" 같은 모호한 표현 |
| `nvidia/nemotron-3.5-lightning:free` | 101초 | 5/5 (1회 호출) | 수치 없이 짧고 일반적인 서술 |

- 무료 모델은 제공사 사정에 따라 호출 한도(429)나 응답 지연이 생길 수 있어, 시연 전에 대상 기업을
  미리 분석해 캐시에 담아두는 것이 안전하다.
- 모델 비교 중 첫 검증 방식(LLM이 적은 소제목이 원문과 일치해야 통과)이 정상 인용까지 탈락시키는
  것을 확인했다. 모델이 원문 안의 하위 제목을 소제목으로 적어 5건이 전부 탈락한 경우가 있었고,
  그래서 인용문 존재 여부만 검증하고 출처 소제목은 코드가 채우는 방식으로 바꿨다.
- 위험요인의 설명(`detail`)이 인용문과 일치하는지, 심각도(low/mid/high)가 타당한지는 검증하지
  못한다. 비교에서 `nemotron` 계열 두 모델은 5건 모두를 mid로 매겨 심각도 구분이 약했고,
  `ling-3.2-flash`는 low와 mid를 나눠 매겼다.

## 디자인 원칙

- 전체 톤은 파스텔 하늘색(`primaryColor #2a78d6`), 리스크 경고 배지(주의/위험)만
  선명한 상태 색상(주황/빨강)을 그대로 사용해 시선이 가도록 함
- 리스크 5개 카테고리(환율/규제/경쟁/원자재/기타)는 레이더·트렌드 차트 어디서든
  같은 색으로 고정 매핑 — 카테고리 색상 순서/조합은 CVD(색약) 안전성 검증을 거침
- 매출·영업이익처럼 단위 스케일이 다른 지표는 하나의 축에 억지로 겹치지 않고
  각각 축 타이틀·눈금·값 라벨이 있는 별도 차트로 분리
- 재무비율 비교 표는 pandas 없이 순수 HTML로 렌더링(위 "알려진 제약사항" 참고)
  하되 헤더 대비/지브라 스트라이핑/숫자 우측정렬로 가독성 확보

## 준비물 (API 키 발급)

1. **DART API Key**: https://opendart.fss.or.kr → 회원가입 후 무료 발급
2. **OpenRouter API Key**: https://openrouter.ai/keys → 발급 (기본 모델: `nvidia/nemotron-3-ultra-550b-a55b:free`, 아래 "LLM 모델 선택" 참고)
3. **네이버 검색 API Key**: https://developers.naver.com/apps → 애플리케이션 등록 시
   "검색" API 사용 설정 후 Client ID/Secret 무료 발급 (관련 뉴스 조회 기능용)

`.env.example`을 복사해 `.env`를 만들고 키를 채운다.

```bash
cp .env.example .env
```

## 설치 및 실행

```bash
python -m venv .venv
.venv\Scripts\activate        # (Windows)  /  source .venv/bin/activate (macOS/Linux)
pip install -r requirements.txt
```

### 1) 백엔드 (FastAPI)

```bash
cd backend
uvicorn app.main:app --reload --port 8000
```

- Swagger UI: http://localhost:8000/docs
- Health check: http://localhost:8000/health

### 2) 프론트엔드 (Streamlit)

새 터미널에서:

```bash
streamlit run frontend/streamlit_app.py
```

기본적으로 `http://localhost:8000`의 백엔드를 호출한다 (`.env`의 `BACKEND_URL`로 변경 가능).

### 3) 테스트

```bash
pytest backend/tests/ -q
```

외부 API 없이 모의 데이터로 실행되며, 재무비율 계산(`financial.py`), PER/PBR(`valuation.py`),
감사의견·배당 파싱(`disclosures.py`), LLM 응답 검증(`llm_client.py`: 수치 덮어쓰기, 인용문
대조, 재시도, 원문 없음 처리)을 검증한다.

## 다른 PC에서 시연하기

`.env`, 가상환경, 캐시가 없는 깨끗한 복사본에서 아래 순서로 설치·실행·분석까지 동작함을 확인했다
(Windows, Python 3.10).

### 사전 준비
- Python 3.10 이상, 인터넷 연결
- API 키 3종(DART, OpenRouter, 네이버)

### 실행 순서
1. 저장소를 내려받고 프로젝트 폴더로 이동한 뒤 가상환경을 만들어 설치한다.

   ```bash
   python -m venv .venv
   .venv\Scripts\activate
   pip install -r requirements.txt
   ```

2. `.env.example`을 `.env`로 복사하고 키 3종을 채운다 (Windows cmd는 `copy .env.example .env`).
3. 터미널 2개에서 각각 백엔드(`cd backend` → `uvicorn app.main:app --port 8000`)와
   프론트엔드(`streamlit run frontend/streamlit_app.py`)를 실행한다.
4. 브라우저에서 `http://localhost:8501`을 연다.

### 시연 시나리오
1. 기업명에 "삼성전자" 입력 → 검색 → 목록에서 **"삼성전자 (005930)"** 선택 (목록 첫 항목은
   비상장 계열사이므로 종목코드가 있는 항목을 고를 것)
2. 사업연도 2025 → "분석 실행". 재무비율, 감사의견 배지, PER/PBR·배당, 차트, 원문 인용이 붙은
   리스크 카드, 뉴스가 표시된다.
3. "트렌드 조회"로 3개년 리스크 추이 확인 (연도마다 LLM을 호출해 최초 조회는 약 35초 걸렸다).
4. "📄 전체 재무제표 원본 보기"에서 DART 원자료와 대조.

### 첫 실행 때 자동으로 일어나는 일
- 첫 기업 검색 시 DART 기업 코드 파일(`data/CORPCODE.xml`, 약 30MB)을 내려받는다 (수 초).
- 분석 결과는 `data/cache.db`에 24시간 캐시된다. 시연 전에 대상 기업(2~3곳)을 한 번씩 분석해
  두면 현장에서는 캐시로 바로 뜨고, 네트워크나 LLM 지연의 영향을 받지 않는다.

### 문제 해결
| 증상 | 원인과 해결 |
|---|---|
| "DART_API_KEY가 설정되지 않았습니다" 등 키 안내 | `.env`가 프로젝트 루트에 있는지, 키가 채워졌는지 확인 후 백엔드를 재시작 |
| 분석 실패: `429 Too Many Requests` | 무료 모델 제공사의 일시적 호출 한도 — 잠시 후 재시도하거나 `.env`의 `OPENROUTER_MODEL`을 다른 모델로 변경 |
| 분석 실패: `402 Payment Required` | `OPENROUTER_MODEL`을 크레딧이 필요한 모델로 바꾼 경우 — 크레딧을 충전하거나 `:free` 모델 사용 |
| 백엔드 시작 시 `KRX 로그인 실패...` 로그 | pykrx가 import 때 출력하는 안내이며 무시해도 된다 (종가 조회는 로그인 불필요) |
| 프론트에서 "백엔드 연결 실패" | 백엔드가 실행 중인지, `.env`의 `BACKEND_URL`이 백엔드 포트와 같은지 확인 |
| `pip install` 중 `WinError 206`(경로가 너무 김) | 프로젝트를 `C:\dart`처럼 짧은 경로에 두거나 Windows 긴 경로 지원을 켠다 |

## 사용 흐름

### 기업 분석 탭
1. 상단 "기업 검색 및 분석 설정" 패널에서 기업명 검색 (예: "삼성전자")
2. 검색 결과 중 기업 선택 (동명이인 대응을 위해 종목코드 함께 표시)
3. 사업연도와 뉴스 개수 입력 후 "분석 실행" 클릭
4. 재무비율 카드, 감사의견 배지(적정의견=초록/그 외=빨강), PER/PBR·배당수익률
   카드, 매출/영업이익 비교 차트, 리스크 레이더 차트, 리스크 요인 카드,
   관련 최근 뉴스 목록 확인
5. "📄 전체 재무제표 원본 보기"에서 재무제표 종류를 선택해 DART 원자료(계정별
   당기/전기/전전기 금액)를 직접 확인 가능
6. "트렌드 조회"로 최근 N개년(2~5) 리스크 카테고리별 심각도 라인 차트 확인
   (연도당 LLM 호출이 있어 시간이 다소 걸릴 수 있음)
7. "Markdown 리포트 다운로드"로 결과를 파일로 저장

### 기업 비교 탭
1. 기업명 검색 → 검색 결과에서 선택 → "비교 목록에 추가" (최대 3개)
2. 비교 사업연도 입력 후 "비교 실행" (2개 이상 추가해야 활성화)
3. 재무비율 + PER/PBR 비교 표 확인, "CSV로 다운로드"로 저장 (엑셀에서 한글 깨짐 없이 열림)

## 알려진 제약사항 (PRD 11절 참고)

- `report_parser.py`의 "사업의 위험" 섹션 추출은 기업별 보고서 문서 구조 차이로 인해
  best-effort 방식이다. 추출 실패 시 LLM에는 "(원문 없음)"으로 전달되며 에러가 아니다.
- 매출/영업이익 바 차트는 단일 조회(당기/전기 2개 시점) 기준이다 (리스크 트렌드와는
  별개 — 리스크 트렌드는 `/risk-trend`에서 연도별 반복 호출로 이미 구현됨).
- PER/PBR은 pykrx의 `get_market_fundamental`/`get_market_cap`이 최근 KRX 정책
  변경으로 개인 계정 로그인(KRX_ID/KRX_PW)을 요구해 사용하지 않는다. 대신 로그인이
  필요 없는 `get_market_ohlcv`(종가)와 DART 발행주식총수로 시가총액을 직접 계산한다
  (`valuation.py`). 비상장사이거나 해당 연도 거래 데이터가 없으면 N/A로 표시.
- 리스크 트렌드는 연도마다 LLM 호출이 발생한다(예: 3개년 조회 시 최대 3회). 캐시가
  있어 재조회는 빠르지만, 최초 조회는 시간이 걸릴 수 있다.
- 캐시(`cache.py`)는 `CompanyAnalysisResponse`를 그대로 직렬화해 저장한다. 응답
  스키마에 새 필드(예: `valuation`)를 추가하면, 그 이전에 캐시된 (기업, 연도)
  조합은 24시간 TTL이 지나기 전까지 새 필드가 비어 있는 채로 반환된다 — 개발 중
  실제로 겪은 문제로, 이럴 땐 "캐시 무시하고 새로 분석"으로 강제 재조회하면 된다.
- LLM 응답은 스키마 검증 또는 근거 검증에 실패하면 1회 재시도한다. 스키마를 끝내 지키지
  못하면 예외를 던지고(백엔드는 502 응답), 근거 검증에 실패한 위험요인은 결과에서 제외된다.
- 인용문 대조는 "인용문이 원문에 존재함"까지만 보장한다. 위험요인 설명(`detail`)이나
  심각도가 인용문에 부합하는지는 검증하지 못하므로, 화면에 원문 인용을 함께 보여줘 사용자가
  직접 확인하게 한다.
- 위험요인 원문은 3,000자로 잘려 LLM에 전달되므로, 긴 보고서는 뒷부분의 위험이 누락될 수 있다.
- 근거 인용 기능 추가 이전에 캐시된 결과에는 원문 인용이 없다. "캐시 무시하고 새로 분석"으로
  재조회하면 인용이 포함된다.
- 비교 결과 표는 의도적으로 `st.dataframe`/pandas를 쓰지 않고 순수 HTML로 렌더링한다
  (`report_utils.build_comparison_html_table`). 개발 중 시스템 Python 환경에서
  numpy/pandas 버전이 안 맞아(`numpy.dtype size changed` ABI 오류) `st.dataframe`이
  깨지는 것을 실제로 겪었음 — 반드시 `requirements.txt` 기준 가상환경(`.venv`)에서
  실행할 것.
