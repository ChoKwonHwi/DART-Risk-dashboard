"""네이버 뉴스 검색 API 클라이언트. 기업 관련 최근 기사를 조회한다.

공식 문서: https://developers.naver.com/docs/serviceapi/search/news/news.md
"""
from __future__ import annotations

import html
import re
from dataclasses import dataclass
from email.utils import parsedate_to_datetime

import requests

from . import config

NAVER_NEWS_URL = "https://openapi.naver.com/v1/search/news.json"

_TAG_RE = re.compile(r"<[^>]+>")


@dataclass
class NewsArticle:
    title: str
    link: str
    description: str
    pub_date: str  # "YYYY-MM-DD HH:MM" 포맷. 파싱 실패 시 원본 문자열 그대로.


def _clean_text(raw: str) -> str:
    """네이버 응답의 <b> 강조 태그와 HTML 엔티티(&quot; 등)를 제거한다."""
    return html.unescape(_TAG_RE.sub("", raw)).strip()


def _format_pub_date(raw: str) -> str:
    try:
        return parsedate_to_datetime(raw).strftime("%Y-%m-%d %H:%M")
    except (TypeError, ValueError):
        return raw


def search_news(query: str, display: int = 5) -> list[NewsArticle]:
    """기업명으로 최신 뉴스를 검색한다 (최신순 정렬)."""
    display = max(1, min(display, 20))
    client_id, client_secret = config.require_naver_credentials()

    resp = requests.get(
        NAVER_NEWS_URL,
        headers={
            "X-Naver-Client-Id": client_id,
            "X-Naver-Client-Secret": client_secret,
        },
        params={"query": query, "display": display, "start": 1, "sort": "date"},
        timeout=15,
    )
    resp.raise_for_status()
    items = resp.json().get("items", [])

    return [
        NewsArticle(
            title=_clean_text(item.get("title", "")),
            link=item.get("originallink") or item.get("link", ""),
            description=_clean_text(item.get("description", "")),
            pub_date=_format_pub_date(item.get("pubDate", "")),
        )
        for item in items
    ]
