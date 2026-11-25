"""DART 재무제표 원자료로부터 재무비율을 계산한다.

설계 원칙(PRD 7절): 숫자 계산은 반드시 이 모듈에서 수행하고, LLM에는
계산이 끝난 값만 입력으로 넘긴다. LLM이 재무 수치를 직접 계산/암산하게
하지 않음으로써 환각(hallucination) 리스크를 없앤다.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict

# account_id(XBRL 표준 계정과목 ID) 우선 매칭, 실패 시 account_nm 텍스트로 폴백.
# DART는 기업마다 계정과목명이 조금씩 다르므로 후보를 여러 개 둔다.
_ACCOUNT_MATCHERS: dict[str, dict[str, list[str]]] = {
    "revenue": {
        "ids": ["ifrs-full:revenue", "ifrs-full:Revenue"],
        "names": ["매출액", "수익(매출액)", "영업수익"],
    },
    "operating_income": {
        "ids": ["dart:OperatingIncomeLoss"],
        "names": ["영업이익", "영업이익(손실)"],
    },
    "net_income": {
        "ids": ["ifrs-full:ProfitLoss"],
        "names": ["당기순이익", "당기순이익(손실)"],
    },
    "total_assets": {
        "ids": ["ifrs-full:Assets"],
        "names": ["자산총계"],
    },
    "total_liabilities": {
        "ids": ["ifrs-full:Liabilities"],
        "names": ["부채총계"],
    },
    "total_equity": {
        "ids": ["ifrs-full:Equity"],
        "names": ["자본총계"],
    },
    "current_assets": {
        "ids": ["ifrs-full:CurrentAssets"],
        "names": ["유동자산"],
    },
    "current_liabilities": {
        "ids": ["ifrs-full:CurrentLiabilities"],
        "names": ["유동부채"],
    },
}


def _parse_amount(raw: str | None) -> float | None:
    if raw is None or raw == "":
        return None
    try:
        return float(raw.replace(",", ""))
    except ValueError:
        return None


def _extract_account(accounts: list[dict], key: str) -> tuple[float | None, float | None]:
    """(당기금액, 전기금액) 튜플을 반환. 못 찾으면 (None, None)."""
    matcher = _ACCOUNT_MATCHERS[key]
    for item in accounts:
        account_id = (item.get("account_id") or "").strip()
        account_nm = (item.get("account_nm") or "").strip()
        if account_id in matcher["ids"] or account_nm in matcher["names"]:
            return (
                _parse_amount(item.get("thstrm_amount")),
                _parse_amount(item.get("frmtrm_amount")),
            )
    return None, None


def _pct_change(current: float | None, prior: float | None) -> float | None:
    if current is None or prior is None or prior == 0:
        return None
    return round((current - prior) / abs(prior) * 100, 2)


def _safe_div_pct(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator is None or denominator == 0:
        return None
    return round(numerator / denominator * 100, 2)


@dataclass
class FinancialRatios:
    revenue: float | None
    revenue_prior: float | None
    revenue_yoy_change_pct: float | None

    operating_income: float | None
    operating_income_prior: float | None
    operating_income_yoy_change_pct: float | None
    operating_margin_pct: float | None

    net_income: float | None
    roe_pct: float | None

    total_assets: float | None
    total_liabilities: float | None
    total_equity: float | None
    debt_ratio_pct: float | None

    current_assets: float | None
    current_liabilities: float | None
    current_ratio_pct: float | None

    def to_dict(self) -> dict:
        return asdict(self)


def calculate_ratios(accounts: list[dict]) -> FinancialRatios:
    """DART fnlttSinglAcntAll 응답(list)에서 주요 재무비율을 계산한다."""
    revenue, revenue_prior = _extract_account(accounts, "revenue")
    operating_income, operating_income_prior = _extract_account(accounts, "operating_income")
    net_income, _ = _extract_account(accounts, "net_income")
    total_assets, _ = _extract_account(accounts, "total_assets")
    total_liabilities, _ = _extract_account(accounts, "total_liabilities")
    total_equity, _ = _extract_account(accounts, "total_equity")
    current_assets, _ = _extract_account(accounts, "current_assets")
    current_liabilities, _ = _extract_account(accounts, "current_liabilities")

    return FinancialRatios(
        revenue=revenue,
        revenue_prior=revenue_prior,
        revenue_yoy_change_pct=_pct_change(revenue, revenue_prior),
        operating_income=operating_income,
        operating_income_prior=operating_income_prior,
        operating_income_yoy_change_pct=_pct_change(operating_income, operating_income_prior),
        operating_margin_pct=_safe_div_pct(operating_income, revenue),
        net_income=net_income,
        roe_pct=_safe_div_pct(net_income, total_equity),
        total_assets=total_assets,
        total_liabilities=total_liabilities,
        total_equity=total_equity,
        debt_ratio_pct=_safe_div_pct(total_liabilities, total_equity),
        current_assets=current_assets,
        current_liabilities=current_liabilities,
        current_ratio_pct=_safe_div_pct(current_assets, current_liabilities),
    )


# 화면에 표시할 재무제표 종류 순서 (재무상태표를 가장 먼저)
STATEMENT_ORDER = ["재무상태표", "손익계산서", "포괄손익계산서", "현금흐름표", "자본변동표"]


def build_raw_statement_rows(accounts: list[dict]) -> list[dict]:
    """원본 재무제표 항목을 표시용으로 정리한다.

    계산된 비율만 보여주는 대신, 사용자가 원자료를 직접 훑어보고 검증할 수
    있도록 DART가 준 항목을 그대로(단위 변환 없이) 노출한다.
    """
    rows = [
        {
            "sj_nm": item.get("sj_nm", ""),
            "account_nm": item.get("account_nm", ""),
            "thstrm_amount": _parse_amount(item.get("thstrm_amount")),
            "frmtrm_amount": _parse_amount(item.get("frmtrm_amount")),
            "bfefrmtrm_amount": _parse_amount(item.get("bfefrmtrm_amount")),
            "ord": int(item["ord"]) if (item.get("ord") or "").isdigit() else 0,
        }
        for item in accounts
    ]

    def _sort_key(row: dict) -> tuple[int, int]:
        try:
            stmt_idx = STATEMENT_ORDER.index(row["sj_nm"])
        except ValueError:
            stmt_idx = len(STATEMENT_ORDER)
        return (stmt_idx, row["ord"])

    rows.sort(key=_sort_key)
    return rows
