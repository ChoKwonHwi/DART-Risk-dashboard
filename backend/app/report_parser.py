"""사업보고서 원문에서 위험 관련 섹션 텍스트를 추출한다.

DART의 document.xml API는 접수번호(rcept_no) 기준으로 보고서 원문을
zip(XML)으로 반환한다. 실제 문서는 "사업의 위험"이라는 고정 문구 대신
"II. 사업의 내용" 하위에 "N. 위험관리 및 파생거래", "N. 위험요인" 등
회사마다 다른 이름의 서브섹션으로 위험 정보를 담고 있다. 따라서 문자열
검색이 아니라 <TITLE> 태그로 만들어지는 목차 구조를 기준으로, "사업의
내용" 대분류 안에서 제목에 "위험"이 포함된 서브섹션만 골라 추출하는
방식을 사용한다 (PRD 11절 리스크 대응 방안 참고). 그래도 회사별 서식
차이로 못 찾는 경우가 있을 수 있어 best-effort로 취급한다.
"""
from __future__ import annotations

import io
import re
import zipfile

import requests

from . import config, dart_client

DOCUMENT_URL = "https://opendart.fss.or.kr/api/document.xml"

_TAG_RE = re.compile(r"<[^>]+>")
_WHITESPACE_RE = re.compile(r"\s+")
_TITLE_RE = re.compile(r"<TITLE[^>]*>([^<]*)</TITLE>")
_TOP_LEVEL_RE = re.compile(r"^(I{1,3}|IV|V)\.\s*")
_BUSINESS_SECTION_RE = re.compile(r"^(I{1,3}|IV|V)\.\s*사업의\s*내용")

_MAX_SNIPPET_CHARS = 3000


def _strip_tags(raw: str) -> str:
    text = _TAG_RE.sub(" ", raw)
    return _WHITESPACE_RE.sub(" ", text).strip()


def _extract_risk_section(raw_xml: str) -> str:
    """<TITLE> 목차 구조를 이용해 'II. 사업의 내용' 하위의 위험 관련
    서브섹션(제목에 '위험' 포함)만 골라 텍스트를 이어붙인다."""
    titles = list(_TITLE_RE.finditer(raw_xml))
    if not titles:
        return ""

    section_start_i: int | None = None
    section_end_i: int | None = None
    for i, m in enumerate(titles):
        label = m.group(1).strip()
        if section_start_i is None:
            if _BUSINESS_SECTION_RE.match(label):
                section_start_i = i
            continue
        if _TOP_LEVEL_RE.match(label):
            section_end_i = i
            break

    if section_start_i is None:
        return ""
    end_i = section_end_i if section_end_i is not None else len(titles)

    chunks: list[str] = []
    for i in range(section_start_i, end_i):
        label = titles[i].group(1).strip()
        if "위험" not in label:
            continue
        body_start = titles[i].end()
        body_end = titles[i + 1].start() if i + 1 < len(titles) else len(raw_xml)
        chunks.append(f"[{label}] {_strip_tags(raw_xml[body_start:body_end])}")

    return "\n".join(chunks)[:_MAX_SNIPPET_CHARS]


def _find_latest_business_report_rcept_no(corp_code: str, bsns_year: str) -> str | None:
    bgn_de = f"{bsns_year}0101"
    end_de = f"{int(bsns_year) + 1}0430"
    disclosures = dart_client.get_disclosure_list(corp_code, bgn_de, end_de)
    reports = [d for d in disclosures if "사업보고서" in (d.get("report_nm") or "")]
    if not reports:
        return None
    reports.sort(key=lambda d: d.get("rcept_dt", ""), reverse=True)
    return reports[0].get("rcept_no")


def get_business_report_risk_text(corp_code: str, bsns_year: str) -> str:
    """최신 사업보고서에서 위험 관련 서브섹션 텍스트를 반환한다.

    보고서를 찾지 못하거나 파싱에 실패하면 빈 문자열을 반환한다(에러로
    취급하지 않음) — LLM 프롬프트에서는 "(원문 없음)"으로 처리된다.
    """
    rcept_no = _find_latest_business_report_rcept_no(corp_code, bsns_year)
    if not rcept_no:
        return ""

    resp = requests.get(
        DOCUMENT_URL,
        params={"crtfc_key": config.require_dart_key(), "rcept_no": rcept_no},
        timeout=30,
    )
    resp.raise_for_status()

    try:
        with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
            # 본문 사업보고서는 통상 "{rcept_no}.xml" 이름으로 들어있고,
            # 감사보고서 등 첨부 XML은 "{rcept_no}_XXXXX.xml" 형태다.
            # 본문 파일을 우선 사용하고, 없으면 전체 파일을 훑는다.
            names = zf.namelist()
            main_name = f"{rcept_no}.xml"
            candidates = [main_name] if main_name in names else names

            for name in candidates:
                raw_xml = zf.read(name).decode("utf-8", errors="ignore")
                section = _extract_risk_section(raw_xml)
                if section:
                    return section
    except zipfile.BadZipFile:
        return ""

    return ""
