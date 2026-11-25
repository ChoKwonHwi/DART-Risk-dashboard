"""주가 기반 밸류에이션(PER/PBR) 계산.

주가(종가)는 pykrx(비공식 KRX 스크래퍼)의 OHLCV 조회로, 발행주식총수는
DART 공식 API(stockTotqySttus.json)로 가져와 시가총액을 직접 계산한다.

pykrx의 get_market_fundamental/get_market_cap은 최근 KRX 정책 변경으로
개인 계정 로그인(KRX_ID/KRX_PW)이 필요해져 사용하지 않는다 — 로그인 없이
쓸 수 있는 get_market_ohlcv(종가)만 사용하고, 나머지는 이미 확보된 DART
재무 데이터(당기순이익/자본총계)로 직접 계산해 완전 무료로 동작한다.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from pykrx import stock as pykrx_stock

from . import dart_client

_MAX_LOOKBACK_DAYS = 10


def _parse_amount(raw: str | None) -> float | None:
    if raw is None or raw in ("", "-"):
        return None
    try:
        return float(raw.replace(",", ""))
    except ValueError:
        return None


def _get_outstanding_shares(corp_code: str, bsns_year: str) -> float | None:
    """DART 주식의 총수 현황에서 보통주 발행주식총수를 가져온다."""
    items = dart_client.get_stock_total_status(corp_code, bsns_year)
    for item in items:
        if item.get("se") == "보통주":
            return _parse_amount(item.get("istc_totqy"))
    return None


def _get_year_end_close_price(stock_code: str, bsns_year: str) -> tuple[float, str] | None:
    """사업연도 말 기준 최근 거래일 종가를 조회한다 (공휴일 대비 최대 10일 역탐색)."""
    end = dt.date(int(bsns_year), 12, 31)
    for offset in range(_MAX_LOOKBACK_DAYS):
        day = end - dt.timedelta(days=offset)
        date_str = day.strftime("%Y%m%d")
        df = pykrx_stock.get_market_ohlcv(date_str, date_str, stock_code)
        if not df.empty:
            return float(df.iloc[0]["종가"]), date_str
    return None


@dataclass
class Valuation:
    per: float | None
    pbr: float | None
    close_price: float | None
    trade_date: str | None

    def to_dict(self) -> dict:
        return {
            "per": self.per,
            "pbr": self.pbr,
            "close_price": self.close_price,
            "trade_date": self.trade_date,
        }


def calculate_valuation(
    corp_code: str,
    stock_code: str,
    bsns_year: str,
    net_income: float | None,
    total_equity: float | None,
) -> Valuation:
    """시가총액(종가 x 발행주식총수) 기준으로 PER/PBR을 계산한다.

    비상장사(stock_code 없음)이거나 데이터를 못 찾으면 전부 None 반환
    (에러로 취급하지 않음).
    """
    if not stock_code:
        return Valuation(None, None, None, None)

    shares = _get_outstanding_shares(corp_code, bsns_year)
    price_info = _get_year_end_close_price(stock_code, bsns_year)
    if shares is None or price_info is None:
        return Valuation(None, None, None, None)

    close_price, trade_date = price_info
    market_cap = close_price * shares

    per = round(market_cap / net_income, 2) if net_income else None
    pbr = round(market_cap / total_equity, 2) if total_equity else None
    return Valuation(per=per, pbr=pbr, close_price=close_price, trade_date=trade_date)
