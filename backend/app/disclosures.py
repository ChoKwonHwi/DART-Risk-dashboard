"""감사의견/배당 정보 파싱.

DART 원자료의 숫자/문자열 정제만 수행하고 해석은 하지 않는다 — 리스크
판단(예: 감사의견이 "적정"이 아니면 위험)은 프론트엔드/사용자의 몫으로
남겨두고, 여기서는 사실만 추출한다.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass


def _parse_amount(raw: str | None) -> float | None:
    if raw is None or raw in ("", "-"):
        return None
    try:
        return float(raw.replace(",", ""))
    except ValueError:
        return None


def _none_if_dash(raw: str | None) -> str | None:
    if raw is None or raw.strip() in ("", "-"):
        return None
    return raw.strip()


@dataclass
class AuditOpinion:
    opinion: str | None
    auditor: str | None
    special_note: str | None  # 감사보고서 특기사항 — 있으면 주의 신호
    emphasis: str | None  # 강조사항

    def to_dict(self) -> dict:
        return asdict(self)


def parse_audit_opinion(items: list[dict]) -> AuditOpinion:
    """당기(연결 기준 레코드가 먼저 옴) 감사의견 레코드 하나를 골라 반환한다."""
    current = [item for item in items if "당기" in (item.get("bsns_year") or "")]
    if not current:
        return AuditOpinion(None, None, None, None)

    item = current[0]
    return AuditOpinion(
        opinion=_none_if_dash(item.get("adt_opinion")),
        auditor=_none_if_dash(item.get("adtor")),
        special_note=_none_if_dash(item.get("adt_reprt_spcmnt_matter")),
        emphasis=_none_if_dash(item.get("emphs_matter")),
    )


@dataclass
class DividendInfo:
    cash_dividend_yield_pct: float | None
    dividend_payout_ratio_pct: float | None
    dividend_per_share: float | None

    def to_dict(self) -> dict:
        return asdict(self)


def _find_se(items: list[dict], se_name_contains: str, stock_knd: str | None = None) -> float | None:
    for item in items:
        se = item.get("se") or ""
        if se_name_contains in se and (stock_knd is None or item.get("stock_knd") == stock_knd):
            return _parse_amount(item.get("thstrm"))
    return None


def parse_dividend_info(items: list[dict]) -> DividendInfo:
    """보통주 기준 배당수익률/배당성향/주당배당금을 추출한다."""
    return DividendInfo(
        cash_dividend_yield_pct=_find_se(items, "현금배당수익률", stock_knd="보통주"),
        dividend_payout_ratio_pct=_find_se(items, "현금배당성향"),
        dividend_per_share=_find_se(items, "주당 현금배당금", stock_knd="보통주"),
    )
