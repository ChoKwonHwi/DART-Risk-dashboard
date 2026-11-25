"""SQLite 기반 캐시. DART/LLM 재호출을 줄이기 위해 분석 결과를 저장한다."""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta

from . import config

_SCHEMA = """
CREATE TABLE IF NOT EXISTS analysis_cache (
    corp_code TEXT NOT NULL,
    bsns_year TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (corp_code, bsns_year)
);
"""


@contextmanager
def _connect():
    conn = sqlite3.connect(config.CACHE_DB_PATH)
    try:
        conn.execute(_SCHEMA)
        yield conn
        conn.commit()
    finally:
        conn.close()


def get_cached_analysis(corp_code: str, bsns_year: str, ttl_hours: int = 24) -> dict | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT payload_json, created_at FROM analysis_cache WHERE corp_code = ? AND bsns_year = ?",
            (corp_code, bsns_year),
        ).fetchone()

    if row is None:
        return None

    payload_json, created_at = row
    created = datetime.fromisoformat(created_at)
    if datetime.utcnow() - created > timedelta(hours=ttl_hours):
        return None

    return json.loads(payload_json)


def set_cached_analysis(corp_code: str, bsns_year: str, payload: dict) -> None:
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO analysis_cache (corp_code, bsns_year, payload_json, created_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(corp_code, bsns_year) DO UPDATE SET
                payload_json = excluded.payload_json,
                created_at = excluded.created_at
            """,
            (corp_code, bsns_year, json.dumps(payload, ensure_ascii=False), datetime.utcnow().isoformat()),
        )
