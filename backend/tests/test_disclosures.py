import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.disclosures import parse_audit_opinion, parse_dividend_info  # noqa: E402


def test_parse_audit_opinion_picks_current_year_record():
    items = [
        {"bsns_year": "제57기 \n(당기)", "adt_opinion": "적정의견", "adtor": "삼정회계법인",
         "adt_reprt_spcmnt_matter": "-", "emphs_matter": "해당사항 없음"},
        {"bsns_year": "제56기\n(전기)", "adt_opinion": "적정의견", "adtor": "삼정회계법인",
         "adt_reprt_spcmnt_matter": "-", "emphs_matter": "-"},
    ]
    result = parse_audit_opinion(items)
    assert result.opinion == "적정의견"
    assert result.auditor == "삼정회계법인"
    assert result.special_note is None
    assert result.emphasis == "해당사항 없음"


def test_parse_audit_opinion_empty_returns_all_none():
    result = parse_audit_opinion([])
    assert result.opinion is None
    assert result.auditor is None


def test_parse_audit_opinion_flags_special_note():
    items = [
        {"bsns_year": "제57기(당기)", "adt_opinion": "한정의견", "adtor": "A회계법인",
         "adt_reprt_spcmnt_matter": "계속기업 불확실성", "emphs_matter": "-"},
    ]
    result = parse_audit_opinion(items)
    assert result.opinion == "한정의견"
    assert result.special_note == "계속기업 불확실성"


def test_parse_dividend_info_filters_by_common_stock():
    items = [
        {"se": "(연결)현금배당성향(%)", "stock_knd": "-", "thstrm": "25.10"},
        {"se": "현금배당수익률(%)", "stock_knd": "보통주", "thstrm": "1.50"},
        {"se": "현금배당수익률(%)", "stock_knd": "우선주", "thstrm": "1.90"},
        {"se": "주당 현금배당금(원)", "stock_knd": "보통주", "thstrm": "1,668"},
    ]
    result = parse_dividend_info(items)
    assert result.cash_dividend_yield_pct == 1.50
    assert result.dividend_payout_ratio_pct == 25.10
    assert result.dividend_per_share == 1668.0


def test_parse_dividend_info_missing_data_returns_none():
    result = parse_dividend_info([])
    assert result.cash_dividend_yield_pct is None
    assert result.dividend_payout_ratio_pct is None
    assert result.dividend_per_share is None
