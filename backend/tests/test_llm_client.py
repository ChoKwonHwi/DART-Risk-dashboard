import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import llm_client  # noqa: E402

RISK_TEXT = (
    "[시장위험과 위험관리] 당사는 수출 비중이 높아 원화 환율이 하락하면 매출과 이익이 감소할 수 있습니다. "
    "당사는 환위험을 줄이기 위해 선물환 계약을 체결하고 있습니다.\n"
    "[규제 위험] 각국의 환경 규제가 강화되면 추가적인 설비 투자 비용이 발생할 수 있습니다."
)
FX_QUOTE = "원화 환율이 하락하면 매출과 이익이 감소할 수 있습니다"
REG_QUOTE = "각국의 환경 규제가 강화되면 추가적인 설비 투자 비용이 발생할 수 있습니다"

RATIOS = {
    "revenue_yoy_change_pct": 10.0,
    "operating_margin_pct": 20.0,
    "debt_ratio_pct": 30.0,
    "roe_pct": 15.0,
    "current_ratio_pct": 150.0,
}


def _risk(category="환율", section="시장위험과 위험관리", quote=FX_QUOTE, **extra):
    return {
        "category": category,
        "detail": "환율 하락 시 실적 악화 가능성",
        "severity": "mid",
        "section": section,
        "evidence_quote": quote,
        **extra,
    }


def _response(risk_factors, financial_summary=None):
    return json.dumps(
        {
            "company": "테스트기업",
            "fiscal_period": "2025 사업연도",
            "financial_summary": financial_summary or {"commentary": "수치 요약"},
            "risk_factors": risk_factors,
        },
        ensure_ascii=False,
    )


def _run(monkeypatch, responses, risk_text=RISK_TEXT, ratios=RATIOS):
    calls = []
    queue = list(responses)

    def fake_call(messages):
        calls.append(messages)
        return queue.pop(0)

    monkeypatch.setattr(llm_client, "_call_openrouter", fake_call)
    report = llm_client.generate_analysis_report("테스트기업", "2025 사업연도", ratios, risk_text)
    return report, calls


def test_llm_numbers_are_overwritten_by_computed_ratios(monkeypatch):
    wrong = {"commentary": "요약", "revenue_yoy_change_pct": 999.0, "roe_pct": -5.0}
    report, _ = _run(monkeypatch, [_response([_risk()], financial_summary=wrong)])

    assert report.financial_summary.revenue_yoy_change_pct == 10.0
    assert report.financial_summary.roe_pct == 15.0
    assert report.financial_summary.debt_ratio_pct == 30.0


def test_valid_quote_is_kept_and_source_is_built_from_section(monkeypatch):
    report, calls = _run(monkeypatch, [_response([_risk()])])

    assert len(calls) == 1
    assert len(report.risk_factors) == 1
    assert report.risk_factors[0].source == "사업보고서 - 시장위험과 위험관리"


def test_quote_matches_despite_whitespace_differences(monkeypatch):
    spaced = "원화  환율이 하락하면\n매출과 이익이   감소할 수 있습니다"
    report, _ = _run(monkeypatch, [_response([_risk(quote=spaced)])])

    assert len(report.risk_factors) == 1


def test_section_name_from_llm_is_ignored_and_resolved_by_code(monkeypatch):
    wrong_name = _risk(section="(1) 시장위험 (환율변동위험)")
    report, calls = _run(monkeypatch, [_response([wrong_name])])

    assert len(calls) == 1  # 소제목 표기가 틀려도 재요청하지 않는다
    assert report.risk_factors[0].section == "시장위험과 위험관리"
    assert report.risk_factors[0].source == "사업보고서 - 시장위험과 위험관리"


def test_fabricated_quote_is_dropped_after_retry(monkeypatch):
    fake = _risk(quote="환율 변동으로 인해 당사의 영업이익이 크게 악화될 것으로 예상됩니다")
    good = _risk(category="규제", section="규제 위험", quote=REG_QUOTE)
    report, calls = _run(monkeypatch, [_response([fake, good]), _response([fake, good])])

    assert len(calls) == 2  # 탈락 항목이 있어 1회 재요청
    assert [rf.category for rf in report.risk_factors] == ["규제"]


def test_retry_with_corrected_quote_recovers_item(monkeypatch):
    fake = _risk(quote="원문에 전혀 없는 그럴듯한 문장을 만들어낸 인용문입니다")
    report, calls = _run(monkeypatch, [_response([fake]), _response([_risk()])])

    assert len(calls) == 2
    assert "근거 검증에 실패" in calls[1][-1]["content"]
    assert len(report.risk_factors) == 1


def test_short_quote_is_rejected(monkeypatch):
    report, _ = _run(monkeypatch, [_response([_risk(quote="환율")])] * 2)

    assert report.risk_factors == []


def test_source_is_the_section_where_quote_actually_appears(monkeypatch):
    misattributed = _risk(section="규제 위험", quote=FX_QUOTE)
    report, _ = _run(monkeypatch, [_response([misattributed])])

    assert report.risk_factors[0].source == "사업보고서 - 시장위험과 위험관리"


def test_quote_missing_from_every_section_is_rejected(monkeypatch):
    fake = _risk(section="규제 위험", quote="어느 소제목에도 존재하지 않는 완전히 꾸며낸 문장입니다")
    report, _ = _run(monkeypatch, [_response([fake])] * 2)

    assert report.risk_factors == []


def test_empty_risk_text_forces_empty_risks_without_retry(monkeypatch):
    report, calls = _run(monkeypatch, [_response([_risk()])], risk_text="")

    assert len(calls) == 1
    assert report.risk_factors == []


def test_schema_failure_on_retry_returns_previous_verified_result(monkeypatch):
    fake = _risk(quote="원문에 전혀 없는 그럴듯한 문장을 만들어낸 인용문입니다")
    good = _risk(category="규제", section="규제 위험", quote=REG_QUOTE)
    report, calls = _run(monkeypatch, [_response([fake, good]), "이건 JSON이 아닙니다"])

    assert len(calls) == 2
    assert [rf.category for rf in report.risk_factors] == ["규제"]


def test_invalid_json_every_time_raises(monkeypatch):
    with pytest.raises(RuntimeError):
        _run(monkeypatch, ["not json", "still not json"])
