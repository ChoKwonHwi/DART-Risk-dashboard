import requests
from fastapi import APIRouter, HTTPException, Query

from .. import cache, dart_client, disclosures, financial, llm_client, news_client, report_parser, valuation
from ..schemas import (
    CompanyAnalysisResponse,
    CorpCandidateOut,
    NewsArticleOut,
    RiskTrendResponse,
    RiskTrendYear,
    RiskYearScore,
)

router = APIRouter(prefix="/companies", tags=["companies"])

_RISK_CATEGORIES = ["환율", "규제", "경쟁", "원자재", "기타"]
_SEVERITY_SCORE = {"low": 1, "mid": 2, "high": 3}


@router.get("/search", response_model=list[CorpCandidateOut])
def search_companies(name: str = Query(..., min_length=1)):
    candidates = dart_client.search_corp_code(name)
    if not candidates:
        raise HTTPException(
            status_code=404, detail=f"'{name}'과(와) 일치하는 기업을 찾을 수 없습니다."
        )
    return [
        CorpCandidateOut(corp_code=c.corp_code, corp_name=c.corp_name, stock_code=c.stock_code)
        for c in candidates
    ]


def _run_analysis(
    corp_code: str,
    corp_name: str,
    bsns_year: str,
    stock_code: str,
    force_refresh: bool,
) -> CompanyAnalysisResponse:
    """단일 기업 분석 파이프라인. /analysis 엔드포인트와 /risk-trend에서 공유한다."""
    if not force_refresh:
        cached = cache.get_cached_analysis(corp_code, bsns_year)
        if cached is not None:
            return CompanyAnalysisResponse(**cached, from_cache=True)

    accounts = dart_client.get_financial_statements(corp_code, bsns_year)
    if not accounts:
        raise HTTPException(
            status_code=404,
            detail=f"{bsns_year}년 재무제표를 찾을 수 없습니다. 사업연도를 확인해주세요.",
        )

    ratios = financial.calculate_ratios(accounts)
    risk_text = report_parser.get_business_report_risk_text(corp_code, bsns_year)

    try:
        report = llm_client.generate_analysis_report(
            company=corp_name,
            fiscal_period=f"{bsns_year} 사업연도",
            ratios=ratios.to_dict(),
            risk_section_text=risk_text,
        )
    except requests.HTTPError as exc:
        status = exc.response.status_code if exc.response is not None else 502
        if status == 429:
            raise HTTPException(
                status_code=502,
                detail="LLM 분석 요청이 일시적으로 많아 거부되었습니다(429 Too Many Requests). 잠시 후 다시 시도해주세요.",
            ) from exc
        raise HTTPException(
            status_code=502, detail=f"LLM 분석 호출에 실패했습니다: {exc}"
        ) from exc
    except requests.RequestException as exc:
        raise HTTPException(
            status_code=502, detail=f"LLM 서버 연결에 실패했습니다: {exc}"
        ) from exc

    val = valuation.calculate_valuation(
        corp_code=corp_code,
        stock_code=stock_code,
        bsns_year=bsns_year,
        net_income=ratios.net_income,
        total_equity=ratios.total_equity,
    )

    # 감사의견/배당정보는 보조 정보라, 조회 실패가 핵심 분석 흐름을 막지 않게 한다.
    try:
        audit_items = dart_client.get_audit_opinion(corp_code, bsns_year)
    except dart_client.DartApiError:
        audit_items = []
    audit = disclosures.parse_audit_opinion(audit_items)

    try:
        dividend_items = dart_client.get_dividend_info(corp_code, bsns_year)
    except dart_client.DartApiError:
        dividend_items = []
    dividend = disclosures.parse_dividend_info(dividend_items)

    raw_statements = financial.build_raw_statement_rows(accounts)

    response = CompanyAnalysisResponse(
        corp_code=corp_code,
        corp_name=corp_name,
        bsns_year=bsns_year,
        raw_ratios=ratios.to_dict(),
        report=report,
        valuation=val.to_dict(),
        audit_opinion=audit.to_dict(),
        dividend=dividend.to_dict(),
        raw_statements=raw_statements,
        from_cache=False,
    )
    cache.set_cached_analysis(
        corp_code, bsns_year, response.model_dump(exclude={"from_cache"})
    )
    return response


@router.get("/{corp_code}/analysis", response_model=CompanyAnalysisResponse)
def analyze_company(
    corp_code: str,
    corp_name: str = Query(..., description="표시용 기업명 (검색 결과에서 전달)"),
    bsns_year: str = Query(..., description="사업연도, 예: 2024"),
    stock_code: str = Query("", description="종목코드 (PER/PBR 계산용, 비상장이면 빈 값)"),
    force_refresh: bool = Query(False, description="캐시를 무시하고 재분석"),
):
    return _run_analysis(corp_code, corp_name, bsns_year, stock_code, force_refresh)


@router.get("/{corp_code}/risk-trend", response_model=RiskTrendResponse)
def get_risk_trend(
    corp_code: str,
    corp_name: str = Query(..., description="표시용 기업명"),
    bsns_year: str = Query(..., description="기준 사업연도 (이 해부터 과거로 조회)"),
    stock_code: str = Query("", description="종목코드 (캐시 일관성을 위해 /analysis와 동일하게 전달)"),
    years: int = Query(3, ge=2, le=5, description="조회할 연도 수"),
):
    """최근 N개년 사업보고서 기준 리스크 카테고리별 심각도 점수 추이."""
    result_years: list[RiskTrendYear] = []
    for offset in range(years):
        year = str(int(bsns_year) - offset)
        try:
            analysis = _run_analysis(corp_code, corp_name, year, stock_code, force_refresh=False)
        except HTTPException:
            continue  # 해당 연도 데이터가 없으면 건너뜀 (에러로 취급하지 않음)

        scores = {cat: 0 for cat in _RISK_CATEGORIES}
        for rf in analysis.report.risk_factors:
            scores[rf.category] = max(scores[rf.category], _SEVERITY_SCORE.get(rf.severity, 0))

        result_years.append(
            RiskTrendYear(
                bsns_year=year,
                scores=[RiskYearScore(category=cat, severity_score=score) for cat, score in scores.items()],
            )
        )

    result_years.reverse()  # 오래된 연도 -> 최신 연도 순으로 정렬
    return RiskTrendResponse(corp_code=corp_code, corp_name=corp_name, years=result_years)


@router.get("/{corp_code}/news", response_model=list[NewsArticleOut])
def get_company_news(
    corp_code: str,
    corp_name: str = Query(..., description="뉴스 검색에 사용할 기업명"),
    count: int = Query(5, ge=1, le=20, description="가져올 최신 기사 개수"),
):
    del corp_code  # 네이버 뉴스 검색은 corp_name으로만 조회한다 (경로 일관성을 위해 유지)
    articles = news_client.search_news(corp_name, display=count)
    return [
        NewsArticleOut(
            title=a.title, link=a.link, description=a.description, pub_date=a.pub_date
        )
        for a in articles
    ]
