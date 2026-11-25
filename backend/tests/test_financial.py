import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.financial import build_raw_statement_rows, calculate_ratios  # noqa: E402


def _account(account_id, account_nm, thstrm, frmtrm):
    return {
        "account_id": account_id,
        "account_nm": account_nm,
        "thstrm_amount": thstrm,
        "frmtrm_amount": frmtrm,
    }


SAMPLE_ACCOUNTS = [
    _account("ifrs-full:Revenue", "매출액", "1,000,000", "800,000"),
    _account("dart:OperatingIncomeLoss", "영업이익", "150,000", "100,000"),
    _account("ifrs-full:ProfitLoss", "당기순이익", "120,000", "90,000"),
    _account("ifrs-full:Assets", "자산총계", "5,000,000", "4,500,000"),
    _account("ifrs-full:Liabilities", "부채총계", "2,000,000", "1,800,000"),
    _account("ifrs-full:Equity", "자본총계", "3,000,000", "2,700,000"),
    _account("ifrs-full:CurrentAssets", "유동자산", "1,500,000", "1,300,000"),
    _account("ifrs-full:CurrentLiabilities", "유동부채", "1,000,000", "900,000"),
]


def test_revenue_yoy_change():
    ratios = calculate_ratios(SAMPLE_ACCOUNTS)
    assert ratios.revenue == 1_000_000
    assert ratios.revenue_yoy_change_pct == 25.0


def test_operating_margin_and_debt_ratio():
    ratios = calculate_ratios(SAMPLE_ACCOUNTS)
    assert ratios.operating_margin_pct == 15.0
    assert ratios.debt_ratio_pct == 66.67


def test_operating_income_prior_is_exposed():
    ratios = calculate_ratios(SAMPLE_ACCOUNTS)
    assert ratios.operating_income == 150_000
    assert ratios.operating_income_prior == 100_000


def test_roe_and_current_ratio():
    ratios = calculate_ratios(SAMPLE_ACCOUNTS)
    assert ratios.roe_pct == 4.0
    assert ratios.current_ratio_pct == 150.0


def test_missing_account_returns_none():
    accounts = [_account("ifrs-full:Revenue", "매출액", "1,000,000", "800,000")]
    ratios = calculate_ratios(accounts)
    assert ratios.total_assets is None
    assert ratios.debt_ratio_pct is None


def test_zero_prior_value_avoids_division_by_zero():
    accounts = [_account("ifrs-full:Revenue", "매출액", "1,000,000", "0")]
    ratios = calculate_ratios(accounts)
    assert ratios.revenue_yoy_change_pct is None


def test_fallback_matches_by_account_name_when_id_unknown():
    accounts = [_account("custom:XYZ123", "매출액", "500,000", "400,000")]
    ratios = calculate_ratios(accounts)
    assert ratios.revenue == 500_000
    assert ratios.revenue_yoy_change_pct == 25.0


def _raw_item(sj_nm, account_nm, ord_, thstrm="1,000", frmtrm="900", bfefrmtrm="800"):
    return {
        "sj_nm": sj_nm,
        "account_nm": account_nm,
        "thstrm_amount": thstrm,
        "frmtrm_amount": frmtrm,
        "bfefrmtrm_amount": bfefrmtrm,
        "ord": ord_,
    }


def test_build_raw_statement_rows_orders_by_statement_then_ord():
    accounts = [
        _raw_item("손익계산서", "매출액", "2"),
        _raw_item("재무상태표", "부채총계", "5"),
        _raw_item("재무상태표", "자산총계", "1"),
    ]
    rows = build_raw_statement_rows(accounts)
    assert [r["sj_nm"] + ":" + r["account_nm"] for r in rows] == [
        "재무상태표:자산총계",
        "재무상태표:부채총계",
        "손익계산서:매출액",
    ]
    assert rows[0]["thstrm_amount"] == 1000.0


def test_build_raw_statement_rows_unknown_statement_sorts_last():
    accounts = [
        _raw_item("기타", "미분류항목", "1"),
        _raw_item("재무상태표", "자산총계", "1"),
    ]
    rows = build_raw_statement_rows(accounts)
    assert rows[0]["sj_nm"] == "재무상태표"
    assert rows[-1]["sj_nm"] == "기타"
