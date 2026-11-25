"""분석 결과를 Markdown/CSV로 변환하는 프론트엔드 전용 유틸.

백엔드 API 응답(JSON)을 그대로 받아 문자열로 직렬화하는 순수 함수만
포함한다 — 새 백엔드 엔드포인트 없이 다운로드 버튼에서 바로 사용한다.
"""
from __future__ import annotations

import csv
import io

import theme

# financial.py의 STATEMENT_ORDER와 동일한 순서 (백엔드에 의존하지 않고
# 프론트엔드에서 재무제표 종류 선택 순서를 맞추기 위한 사본)
STATEMENT_ORDER = ["재무상태표", "손익계산서", "포괄손익계산서", "현금흐름표", "자본변동표"]


def build_markdown_report(analysis: dict, news: list[dict] | None = None) -> str:
    """단일 기업 분석 결과를 Markdown 리포트 문자열로 변환한다."""
    report = analysis["report"]
    ratios = analysis["raw_ratios"]
    summary = report["financial_summary"]

    lines = [
        f"# {analysis['corp_name']} 리스크 분석 리포트",
        "",
        f"- 사업연도: {report['fiscal_period']}",
        f"- 매출 YoY: {summary['revenue_yoy_change_pct']}%",
        f"- 영업이익률: {summary['operating_margin_pct']}%",
        f"- 부채비율: {summary['debt_ratio_pct']}%",
        f"- ROE: {summary['roe_pct']}%",
        f"- 유동비율: {summary['current_ratio_pct']}%",
        "",
        "## 재무 변화 요약",
        "",
        summary["commentary"],
        "",
        "## 리스크 요인",
        "",
    ]

    if not report["risk_factors"]:
        lines.append("추출된 리스크 요인이 없습니다.")
    for rf in report["risk_factors"]:
        lines.append(f"- **[{rf['category']}/{rf['severity']}]** {rf['detail']} (출처: {rf['source']})")
        if rf.get("evidence_quote"):
            lines.append(f"  - 원문: “{rf['evidence_quote']}”")

    if news:
        lines += ["", "## 관련 최근 뉴스", ""]
        for a in news:
            lines.append(f"- [{a['title']}]({a['link']}) — {a['pub_date']}")

    lines += [
        "",
        "---",
        "",
        f"참고 재무 원자료: 매출액 {ratios.get('revenue')}, 영업이익 {ratios.get('operating_income')}, "
        f"자산총계 {ratios.get('total_assets')}, 부채총계 {ratios.get('total_liabilities')}",
        "",
        f"> {report['disclaimer']}",
    ]
    return "\n".join(lines)


def build_comparison_csv(rows: list[dict]) -> str:
    """기업 비교 결과(dict 리스트)를 CSV 문자열로 변환한다."""
    if not rows:
        return ""
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=list(rows[0].keys()))
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue()


def build_comparison_html_table(rows: list[dict]) -> str:
    """기업 비교 결과를 순수 HTML 표로 변환한다.

    st.dataframe/st.table은 내부적으로 pandas를 거치는데, 실행 환경에 따라
    pandas가 numpy와 ABI 버전이 맞지 않아 깨지는 경우가 있어(로컬에서 실제
    발생) 의존성 없이 직접 렌더링한다. 첫 컬럼(기업명)은 좌측 정렬, 나머지
    숫자 컬럼은 우측 정렬 + 고정폭 숫자(tabular-nums)로 자릿수를 맞춘다.
    """
    if not rows:
        return "<p>표시할 데이터가 없습니다.</p>"

    columns = list(rows[0].keys())
    header_cells = "".join(
        f"<th style='padding:8px 14px;text-align:{'left' if i == 0 else 'right'};"
        "background:#e4eff9;color:#0b0b0b;"
        "border-bottom:2px solid #b9d4ec;font-weight:700;white-space:nowrap'>"
        f"{c}</th>"
        for i, c in enumerate(columns)
    )
    body_rows = []
    for row_idx, row in enumerate(rows):
        row_bg = "#ffffff" if row_idx % 2 == 0 else "#f6fafd"
        cells = []
        for i, c in enumerate(columns):
            value = row[c]
            text = "N/A" if value is None else value
            align = "left" if i == 0 else "right"
            numeric_style = "font-variant-numeric:tabular-nums;" if i > 0 else ""
            color = theme.CHART_INK_MUTED if value is None else theme.CHART_INK_PRIMARY
            cells.append(
                f"<td style='padding:8px 14px;text-align:{align};{numeric_style}"
                f"color:{color};border-bottom:1px solid #e1e0d9'>{text}</td>"
            )
        body_rows.append(f"<tr style='background:{row_bg}'>{''.join(cells)}</tr>")

    return (
        "<table style='width:100%;border-collapse:collapse;font-size:14px'>"
        f"<thead><tr>{header_cells}</tr></thead><tbody>{''.join(body_rows)}</tbody></table>"
    )


def build_statement_html_table(rows: list[dict]) -> str:
    """재무제표 원본 행(계정명/당기/전기/전전기 금액)을 HTML 표로 변환한다.

    금액은 천 단위 콤마만 적용하고 단위 변환은 하지 않는다 — "원자료 그대로"가
    이 화면의 목적이므로 계산된 조원 단위 등으로 가공하지 않는다.
    """
    if not rows:
        return "<p>표시할 데이터가 없습니다.</p>"

    columns = [
        ("account_nm", "계정명", "left"),
        ("thstrm_amount", "당기금액", "right"),
        ("frmtrm_amount", "전기금액", "right"),
        ("bfefrmtrm_amount", "전전기금액", "right"),
    ]
    header_cells = "".join(
        f"<th style='padding:8px 14px;text-align:{align};"
        "background:#e4eff9;color:#0b0b0b;"
        "border-bottom:2px solid #b9d4ec;font-weight:700;white-space:nowrap'>"
        f"{label}</th>"
        for _, label, align in columns
    )
    body_rows = []
    for row_idx, row in enumerate(rows):
        row_bg = "#ffffff" if row_idx % 2 == 0 else "#f6fafd"
        cells = []
        for key, _, align in columns:
            value = row.get(key)
            if key == "account_nm":
                text = value or ""
                numeric_style = ""
            else:
                text = "N/A" if value is None else f"{value:,.0f}"
                numeric_style = "font-variant-numeric:tabular-nums;"
            color = theme.CHART_INK_MUTED if value is None else theme.CHART_INK_PRIMARY
            cells.append(
                f"<td style='padding:6px 14px;text-align:{align};{numeric_style}"
                f"color:{color};border-bottom:1px solid #e1e0d9'>{text}</td>"
            )
        body_rows.append(f"<tr style='background:{row_bg}'>{''.join(cells)}</tr>")

    return (
        "<table style='width:100%;border-collapse:collapse;font-size:13.5px'>"
        f"<thead><tr>{header_cells}</tr></thead><tbody>{''.join(body_rows)}</tbody></table>"
    )
