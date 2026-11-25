"""OpenRouter 경유 LLM 호출. 재무비율(계산된 값)과 위험요인 원문을 입력받아
PRD 7절의 AnalysisReport JSON 스키마로 강제 출력받는다.

신뢰성 설계:
1. 여기서 LLM에 넘기는 숫자는 전부 financial.py에서 계산이 끝난 값이다.
   LLM은 "해석"과 "정성적 텍스트에서 리스크 태깅"만 수행한다.
2. LLM이 출력한 재무 수치는 신뢰하지 않고, 검증 후 항상 계산값으로 덮어쓴다.
3. 위험요인은 원문 인용문(evidence_quote)과 소제목(section)을 함께 요구하고,
   인용문이 해당 소제목의 원문에 실제로 존재하는지 문자열 대조로 검증한다.
   통과하지 못한 항목은 재요청하거나, 끝내 통과하지 못하면 버린다.
"""
from __future__ import annotations

import json
import logging
import re

import requests

from . import config
from .schemas import AnalysisReport, RiskFactor

logger = logging.getLogger(__name__)

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

MIN_QUOTE_CHARS = 15  # 공백 제거 기준. 너무 짧은 인용은 어디에나 있어 검증 의미가 없다.
_RATIO_KEYS = (
    "revenue_yoy_change_pct",
    "operating_margin_pct",
    "debt_ratio_pct",
    "roe_pct",
    "current_ratio_pct",
)
_SECTION_LINE_RE = re.compile(r"^\[(?P<label>.+?)\]\s?(?P<body>.*)$")

_SYSTEM_PROMPT = """\
당신은 금융 애널리스트 보조 AI입니다. 아래 JSON 스키마를 정확히 따르는 \
JSON만 출력하세요. 스키마 외의 텍스트(설명, 마크다운 코드블록 등)를 \
절대 포함하지 마세요.

스키마:
{
  "company": string,
  "fiscal_period": string,
  "financial_summary": {
    "commentary": string
  },
  "risk_factors": [
    {
      "category": "환율" | "규제" | "경쟁" | "원자재" | "기타",
      "detail": string,
      "severity": "low" | "mid" | "high",
      "evidence_quote": string
    }
  ],
  "disclaimer": string
}

규칙:
- 재무 수치는 출력하지 마세요. 수치는 시스템이 계산값으로 채웁니다.
- commentary는 입력된 재무비율의 수준과 변화를 2~3문장으로 서술하세요. \
원인은 사업보고서 원문에 명시된 내용일 때만 언급하고, 원문에 없으면 \
원인을 단정하지 마세요. 증가·감소·개선·악화 같은 변화 표현은 입력에 \
비교 대상(전기 값 또는 증감률)이 있는 항목(매출액, 영업이익)에만 쓰고, \
그 외 항목은 현재 수준만 서술하세요.
- risk_factors는 입력된 "사업의 위험" 원문에서 실제로 근거를 찾을 수 있는 \
항목만 최대 5개까지 추출하세요. 근거 없는 리스크를 지어내지 마세요. \
원문이 "(원문 없음)"이면 빈 배열로 두세요.
- evidence_quote는 입력 원문에서 한 문장 이상(15자 이상)을 한 글자도 바꾸지 \
말고 그대로 복사하세요. 요약하거나 의역하면 안 됩니다.
"""


def _build_user_prompt(
    company: str,
    fiscal_period: str,
    ratios: dict,
    risk_section_text: str,
) -> str:
    return (
        f"기업명: {company}\n"
        f"보고 기간: {fiscal_period}\n\n"
        f"계산된 재무비율(JSON, 이 값을 그대로 사용):\n{json.dumps(ratios, ensure_ascii=False, indent=2)}\n\n"
        f"사업보고서 '사업의 위험' 원문 발췌:\n{risk_section_text or '(원문 없음)'}\n"
    )


def _call_openrouter(messages: list[dict]) -> str:
    resp = requests.post(
        OPENROUTER_URL,
        headers={
            "Authorization": f"Bearer {config.require_openrouter_key()}",
            "Content-Type": "application/json",
        },
        json={
            "model": config.OPENROUTER_MODEL,
            "messages": messages,
            "response_format": {"type": "json_object"},
            "temperature": 0.2,
        },
        timeout=60,
    )
    resp.raise_for_status()
    data = resp.json()
    return data["choices"][0]["message"]["content"]


def generate_analysis_report(
    company: str,
    fiscal_period: str,
    ratios: dict,
    risk_section_text: str,
    max_retries: int = 1,
) -> AnalysisReport:
    """LLM 호출 후 AnalysisReport로 검증. 스키마 불일치 시 오류를 알려주며 재시도."""
    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {
            "role": "user",
            "content": _build_user_prompt(company, fiscal_period, ratios, risk_section_text),
        },
    ]

    last_error: Exception | None = None
    best_effort: AnalysisReport | None = None  # 근거 검증을 통과한 항목만 담은 가장 최근 결과
    for attempt in range(max_retries + 1):
        raw_content = _call_openrouter(messages)
        try:
            report = _parse_report(raw_content, ratios)
        except ValueError as exc:  # JSONDecodeError, ValidationError 포함
            last_error = exc
            messages.append({"role": "assistant", "content": raw_content})
            messages.append(
                {
                    "role": "user",
                    "content": (
                        f"이전 출력이 스키마를 위반했습니다: {exc}\n"
                        "스키마를 정확히 지켜 JSON만 다시 출력하세요."
                    ),
                }
            )
            continue

        kept, rejected = _verify_risk_factors(report.risk_factors, risk_section_text)
        report.risk_factors = kept
        best_effort = report

        # 원문이 없으면 전부 걸러지는 게 정상이라 재요청하지 않는다.
        if not rejected or not risk_section_text:
            return report

        logger.warning("근거 검증 실패 %d건 (시도 %d): %s", len(rejected), attempt + 1, rejected)
        messages.append({"role": "assistant", "content": raw_content})
        messages.append(
            {
                "role": "user",
                "content": (
                    "다음 위험요인은 원문 근거 검증에 실패했습니다:\n"
                    + "\n".join(f"- {reason}" for reason in rejected)
                    + "\n원문에 실제로 있는 문장만 evidence_quote에 그대로 복사하고, "
                    "근거를 찾을 수 없는 항목은 제외해서 JSON을 다시 출력하세요."
                ),
            }
        )

    if best_effort is not None:
        return best_effort  # 검증을 통과한 항목만 남긴 결과 (실패 항목은 이미 버려짐)

    raise RuntimeError(f"LLM이 유효한 AnalysisReport JSON을 생성하지 못했습니다: {last_error}")


def _parse_report(raw_content: str, ratios: dict) -> AnalysisReport:
    """JSON 파싱 + 스키마 검증 후, 재무 수치는 LLM 출력이 아닌 계산값으로 덮어쓴다."""
    payload = json.loads(raw_content)
    if not isinstance(payload, dict):
        raise ValueError("최상위 JSON은 객체여야 합니다.")

    llm_summary = payload.get("financial_summary")
    commentary = llm_summary.get("commentary") if isinstance(llm_summary, dict) else None
    payload["financial_summary"] = {
        **{key: ratios.get(key) for key in _RATIO_KEYS},
        "commentary": commentary,
    }
    return AnalysisReport.model_validate(payload)


def _normalize(text: str) -> str:
    return re.sub(r"\s+", "", text)


def _split_sections(risk_section_text: str) -> list[tuple[str, str]]:
    """report_parser가 만든 '[소제목] 본문' 줄들을 [(소제목, 공백 제거한 본문)]으로 나눈다."""
    sections: list[tuple[str, str]] = []
    for line in risk_section_text.splitlines():
        match = _SECTION_LINE_RE.match(line.strip())
        if match:
            sections.append((match["label"].strip(), _normalize(match["body"])))
    return sections


def _verify_risk_factors(
    risk_factors: list[RiskFactor], risk_section_text: str
) -> tuple[list[RiskFactor], list[str]]:
    """인용문이 입력 원문에 실제로 존재하는 위험요인만 남긴다.

    출처 소제목은 LLM의 주장을 믿지 않고, 인용문이 실제로 발견된 소제목으로 코드가
    채운다. 반환: (통과한 항목, 탈락 사유 목록). 인용문이 존재함은 보장하지만
    해석이 인용문과 일치하는지(의미 타당성)까지는 검증하지 못한다.
    """
    if not risk_section_text:
        return [], []

    sections = _split_sections(risk_section_text)
    kept: list[RiskFactor] = []
    rejected: list[str] = []

    for rf in risk_factors:
        quote = _normalize(rf.evidence_quote)
        label = f"[{rf.category}] {rf.detail[:30]}"

        if len(quote) < MIN_QUOTE_CHARS:
            rejected.append(f"{label} — 인용문이 없거나 너무 짧음")
            continue

        found = next((name for name, body in sections if quote in body), None)
        if found is None:
            rejected.append(f"{label} — 인용문이 입력 원문에 존재하지 않음")
            continue

        kept.append(rf.model_copy(update={"section": found, "source": f"사업보고서 - {found}"}))

    return kept, rejected
