import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import valuation  # noqa: E402


def test_calculate_valuation_formula(monkeypatch):
    monkeypatch.setattr(
        valuation.dart_client,
        "get_stock_total_status",
        lambda corp_code, bsns_year: [{"se": "보통주", "istc_totqy": "1,000,000"}],
    )
    monkeypatch.setattr(
        valuation.pykrx_stock,
        "get_market_ohlcv",
        lambda start, end, code: SimpleNamespace(
            empty=False, iloc=[{"종가": 10_000}]
        ),
    )

    result = valuation.calculate_valuation(
        corp_code="00000000",
        stock_code="000000",
        bsns_year="2024",
        net_income=2_000_000_000,
        total_equity=5_000_000_000,
    )

    # 시가총액 = 10,000 * 1,000,000 = 10,000,000,000
    assert result.close_price == 10_000
    assert result.per == 5.0  # 10e9 / 2e9
    assert result.pbr == 2.0  # 10e9 / 5e9


def test_calculate_valuation_unlisted_returns_none():
    result = valuation.calculate_valuation(
        corp_code="00000000",
        stock_code="",
        bsns_year="2024",
        net_income=1000,
        total_equity=1000,
    )
    assert result.per is None
    assert result.pbr is None


def test_calculate_valuation_missing_shares_returns_none(monkeypatch):
    monkeypatch.setattr(
        valuation.dart_client, "get_stock_total_status", lambda corp_code, bsns_year: []
    )
    result = valuation.calculate_valuation(
        corp_code="00000000",
        stock_code="000000",
        bsns_year="2024",
        net_income=1000,
        total_equity=1000,
    )
    assert result.per is None
    assert result.pbr is None
