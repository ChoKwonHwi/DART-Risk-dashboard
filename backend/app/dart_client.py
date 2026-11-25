"""DART(전자공시시스템) OpenAPI 클라이언트.

공식 문서: https://opendart.fss.or.kr/guide/main.do
"""
from __future__ import annotations

import io
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass

import requests

from . import config

BASE_URL = "https://opendart.fss.or.kr/api"
REPORT_CODE_ANNUAL = "11011"  # 사업보고서(연간)


class DartApiError(RuntimeError):
    """DART API가 status != '000' 을 반환했을 때 발생."""


@dataclass
class CorpCandidate:
    corp_code: str
    corp_name: str
    stock_code: str  # 비상장사는 빈 문자열


def _get(path: str, params: dict) -> dict:
    params = {**params, "crtfc_key": config.require_dart_key()}
    resp = requests.get(f"{BASE_URL}/{path}", params=params, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    status = data.get("status")
    if status not in ("000", "013"):  # 013 = 조회된 데이터 없음(에러 아님)
        raise DartApiError(f"DART API 오류 [{status}]: {data.get('message')}")
    return data


def _download_corp_code_xml() -> bytes:
    """corpCode.xml(zip)을 내려받아 로컬에 캐싱한다."""
    if config.CORP_CODE_XML_PATH.exists():
        return config.CORP_CODE_XML_PATH.read_bytes()

    resp = requests.get(
        f"{BASE_URL}/corpCode.xml",
        params={"crtfc_key": config.require_dart_key()},
        timeout=30,
    )
    resp.raise_for_status()

    with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
        xml_bytes = zf.read("CORPCODE.xml")

    config.CORP_CODE_XML_PATH.write_bytes(xml_bytes)
    return xml_bytes


def search_corp_code(company_name: str, limit: int = 10) -> list[CorpCandidate]:
    """기업명으로 corp_code 후보를 검색한다 (동명이인/유사 기업명 대응)."""
    xml_bytes = _download_corp_code_xml()
    root = ET.fromstring(xml_bytes)

    matches: list[CorpCandidate] = []
    query = company_name.strip().lower()
    for elem in root.iter("list"):
        name = (elem.findtext("corp_name") or "").strip()
        if query in name.lower():
            matches.append(
                CorpCandidate(
                    corp_code=(elem.findtext("corp_code") or "").strip(),
                    corp_name=name,
                    stock_code=(elem.findtext("stock_code") or "").strip(),
                )
            )
            if len(matches) >= limit:
                break
    return matches


def get_disclosure_list(
    corp_code: str, bgn_de: str, end_de: str, pblntf_ty: str = "A"
) -> list[dict]:
    """공시 목록 조회 (기본: 정기공시 A 유형 - 사업/분기/반기보고서 등)."""
    data = _get(
        "list.json",
        {
            "corp_code": corp_code,
            "bgn_de": bgn_de,
            "end_de": end_de,
            "pblntf_ty": pblntf_ty,
            "page_count": 100,
        },
    )
    return data.get("list", [])


def get_financial_statements(
    corp_code: str, bsns_year: str, reprt_code: str = REPORT_CODE_ANNUAL
) -> list[dict]:
    """단일회사 전체 재무제표 조회 (fnlttSinglAcntAll)."""
    data = _get(
        "fnlttSinglAcntAll.json",
        {
            "corp_code": corp_code,
            "bsns_year": bsns_year,
            "reprt_code": reprt_code,
            "fs_div": "CFS",  # 연결재무제표, 없으면 OFS(개별)로 재시도 필요
        },
    )
    accounts = data.get("list", [])
    if accounts:
        return accounts

    # 연결재무제표가 없는 기업(자회사 없음 등)은 개별재무제표로 재시도
    data = _get(
        "fnlttSinglAcntAll.json",
        {
            "corp_code": corp_code,
            "bsns_year": bsns_year,
            "reprt_code": reprt_code,
            "fs_div": "OFS",
        },
    )
    return data.get("list", [])


def get_stock_total_status(
    corp_code: str, bsns_year: str, reprt_code: str = REPORT_CODE_ANNUAL
) -> list[dict]:
    """주식의 총수 현황 조회 (발행주식총수 등, stockTotqySttus). PER/PBR 계산용."""
    data = _get(
        "stockTotqySttus.json",
        {"corp_code": corp_code, "bsns_year": bsns_year, "reprt_code": reprt_code},
    )
    return data.get("list", [])


def get_audit_opinion(
    corp_code: str, bsns_year: str, reprt_code: str = REPORT_CODE_ANNUAL
) -> list[dict]:
    """회계감사인의 명칭 및 감사의견 조회 (accnutAdtorNmNdAdtOpinion)."""
    data = _get(
        "accnutAdtorNmNdAdtOpinion.json",
        {"corp_code": corp_code, "bsns_year": bsns_year, "reprt_code": reprt_code},
    )
    return data.get("list", [])


def get_dividend_info(
    corp_code: str, bsns_year: str, reprt_code: str = REPORT_CODE_ANNUAL
) -> list[dict]:
    """배당에 관한 사항 조회 (alotMatter)."""
    data = _get(
        "alotMatter.json",
        {"corp_code": corp_code, "bsns_year": bsns_year, "reprt_code": reprt_code},
    )
    return data.get("list", [])
