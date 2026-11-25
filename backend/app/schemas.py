"""API 요청/응답 및 LLM 강제 출력 스키마 (PRD 7절 기준)."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class CorpCandidateOut(BaseModel):
    corp_code: str
    corp_name: str
    stock_code: str


class FinancialSummary(BaseModel):
    revenue_yoy_change_pct: float | None = None
    operating_margin_pct: float | None = None
    debt_ratio_pct: float | None = None
    roe_pct: float | None = None
    current_ratio_pct: float | None = None
    commentary: str = Field(..., description="LLM이 생성한 재무 변화 원인 추정 텍스트")


class RiskFactor(BaseModel):
    category: Literal["환율", "규제", "경쟁", "원자재", "기타"]
    detail: str
    severity: Literal["low", "mid", "high"]
    section: str = ""
    evidence_quote: str = ""
    source: str = Field(default="사업보고서 - 사업의 위험")


class AnalysisReport(BaseModel):
    """LLM에 강제하는 최종 출력 스키마. 이 형태를 벗어나면 검증 실패로 재시도한다."""

    company: str
    fiscal_period: str
    financial_summary: FinancialSummary
    risk_factors: list[RiskFactor]
    disclaimer: str = (
        "본 분석은 공시 자료 기반 자동 생성 결과이며 투자 판단의 근거로 사용될 수 없습니다."
    )


class ValuationOut(BaseModel):
    per: float | None = None
    pbr: float | None = None
    close_price: float | None = None
    trade_date: str | None = None


class AuditOpinionOut(BaseModel):
    opinion: str | None = None
    auditor: str | None = None
    special_note: str | None = None
    emphasis: str | None = None


class DividendInfoOut(BaseModel):
    cash_dividend_yield_pct: float | None = None
    dividend_payout_ratio_pct: float | None = None
    dividend_per_share: float | None = None


class RawStatementRow(BaseModel):
    sj_nm: str
    account_nm: str
    thstrm_amount: float | None = None
    frmtrm_amount: float | None = None
    bfefrmtrm_amount: float | None = None
    ord: int = 0


class CompanyAnalysisResponse(BaseModel):
    corp_code: str
    corp_name: str
    bsns_year: str
    raw_ratios: dict
    report: AnalysisReport
    valuation: ValuationOut = ValuationOut()
    audit_opinion: AuditOpinionOut = AuditOpinionOut()
    dividend: DividendInfoOut = DividendInfoOut()
    raw_statements: list[RawStatementRow] = []
    from_cache: bool = False


class NewsArticleOut(BaseModel):
    title: str
    link: str
    description: str
    pub_date: str


class RiskYearScore(BaseModel):
    category: Literal["환율", "규제", "경쟁", "원자재", "기타"]
    severity_score: int  # 0(없음)~3(high)


class RiskTrendYear(BaseModel):
    bsns_year: str
    scores: list[RiskYearScore]


class RiskTrendResponse(BaseModel):
    corp_code: str
    corp_name: str
    years: list[RiskTrendYear]
