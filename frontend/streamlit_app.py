"""DART Risk Insight 프론트엔드 (Streamlit).

FastAPI 백엔드(backend/app)를 호출해 기업 검색 → 재무비율/리스크 분석
결과를 카드와 차트로 보여준다. "기업 분석" 탭은 단일 기업 심층 분석을,
"기업 비교" 탭은 최대 3개 기업의 재무비율을 나란히 비교한다.
"""
import os

import plotly.graph_objects as go
import requests
import streamlit as st
from dotenv import load_dotenv

import report_utils
import theme

load_dotenv()
BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")

SEVERITY_SCORE = {"low": 1, "mid": 2, "high": 3}
RISK_CATEGORIES = theme.RISK_CATEGORIES
MAX_COMPARE = 3


def _to_jo(value: float | None) -> float | None:
    """원 단위 금액을 조원 단위로 변환한다 (차트 축 스케일 표기용)."""
    return None if value is None else round(value / 1e12, 1)


def _bar_chart(x_labels: list[str], y_values: list[float | None], axis_title: str) -> go.Figure:
    """단일 시리즈 막대 차트. 축 타이틀/눈금/막대 끝 값 라벨로 스케일을 명확히 표기한다."""
    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            x=x_labels,
            y=y_values,
            marker_color=theme.SINGLE_SERIES_COLOR,
            marker_cornerradius=4,
            width=0.45,
            text=[f"{v:,.1f}" if v is not None else "N/A" for v in y_values],
            textposition="outside",
            cliponaxis=False,
        )
    )
    fig.update_layout(
        height=210,
        showlegend=False,
        margin=dict(t=10, b=10, l=10, r=10),
        plot_bgcolor=theme.CHART_SURFACE,
        paper_bgcolor=theme.CHART_SURFACE,
        font=dict(color=theme.CHART_INK_PRIMARY),
        yaxis=dict(
            title=axis_title,
            rangemode="tozero",
            gridcolor=theme.CHART_GRIDLINE,
            griddash="solid",
            tickformat=",.0f",
        ),
        xaxis=dict(showgrid=False, color=theme.CHART_INK_MUTED),
    )
    return fig


st.set_page_config(page_title="DART Risk Insight", layout="wide")
st.markdown(theme.CUSTOM_CSS, unsafe_allow_html=True)
st.markdown(theme.HERO_HTML, unsafe_allow_html=True)

if "candidates" not in st.session_state:
    st.session_state.candidates = []
if "compare_list" not in st.session_state:
    st.session_state.compare_list = []
if "compare_candidates" not in st.session_state:
    st.session_state.compare_candidates = []

with st.container(border=True):
    st.markdown("##### 🔍 기업 검색 및 분석 설정")

    search_col, search_btn_col, select_col = st.columns([3, 1, 3])
    with search_col:
        query = st.text_input("기업명", placeholder="예: 삼성전자")
    with search_btn_col:
        st.markdown(theme.BUTTON_ALIGN_SPACER, unsafe_allow_html=True)
        search_clicked = st.button("검색", use_container_width=True)
    if search_clicked and query:
        try:
            resp = requests.get(f"{BACKEND_URL}/companies/search", params={"name": query}, timeout=15)
            resp.raise_for_status()
            st.session_state.candidates = resp.json()
        except requests.HTTPError as exc:
            st.session_state.candidates = []
            st.error(f"검색 실패: {exc.response.json().get('detail', exc)}")
        except requests.RequestException as exc:
            st.error(f"백엔드 연결 실패: {exc}")

    selected = None
    with select_col:
        if st.session_state.candidates:
            options = {
                f"{c['corp_name']} ({c['stock_code'] or '비상장'})": c
                for c in st.session_state.candidates
            }
            label = st.selectbox("기업 선택", list(options.keys()))
            selected = options[label]
        else:
            st.caption("먼저 기업명을 검색하세요.")

    year_col, news_col, cache_col, analyze_col = st.columns([1, 1, 1.4, 1.6])
    with year_col:
        bsns_year = st.text_input("사업연도", value="2025")
    with news_col:
        news_count = st.number_input("뉴스 개수", min_value=1, max_value=20, value=5)
    with cache_col:
        st.markdown(theme.BUTTON_ALIGN_SPACER, unsafe_allow_html=True)
        force_refresh = st.checkbox("캐시 무시하고 새로 분석", value=False)
    with analyze_col:
        st.markdown(theme.BUTTON_ALIGN_SPACER, unsafe_allow_html=True)
        analyze_clicked = st.button(
            "분석 실행", type="primary", use_container_width=True, disabled=selected is None
        )

if analyze_clicked and selected:
    with st.spinner("DART 재무제표 수집 및 LLM 분석 중..."):
        try:
            resp = requests.get(
                f"{BACKEND_URL}/companies/{selected['corp_code']}/analysis",
                params={
                    "corp_name": selected["corp_name"],
                    "bsns_year": bsns_year,
                    "stock_code": selected["stock_code"],
                    "force_refresh": force_refresh,
                },
                timeout=90,
            )
            resp.raise_for_status()
            st.session_state.analysis = resp.json()
        except requests.HTTPError as exc:
            try:
                detail = exc.response.json().get("detail", str(exc))
            except ValueError:
                detail = exc.response.text or str(exc)
            st.error(f"분석 실패: {detail}")
            st.session_state.pop("analysis", None)
        except requests.RequestException as exc:
            st.error(f"백엔드 연결 실패: {exc}")
            st.session_state.pop("analysis", None)

    try:
        news_resp = requests.get(
            f"{BACKEND_URL}/companies/{selected['corp_code']}/news",
            params={"corp_name": selected["corp_name"], "count": news_count},
            timeout=15,
        )
        news_resp.raise_for_status()
        st.session_state.news = news_resp.json()
    except requests.HTTPError as exc:
        st.warning(f"뉴스 조회 실패: {exc.response.json().get('detail', exc)}")
        st.session_state.pop("news", None)
    except requests.RequestException as exc:
        st.warning(f"뉴스 조회 중 백엔드 연결 실패: {exc}")
        st.session_state.pop("news", None)

tab_single, tab_compare = st.tabs(["🏢 기업 분석", "🆚 기업 비교"])

with tab_single:
    analysis = st.session_state.get("analysis")
    if not analysis:
        st.info("위쪽 '기업 검색 및 분석 설정' 패널에서 기업을 검색하고 분석을 실행하세요.")
    else:
        report = analysis["report"]
        ratios = analysis["raw_ratios"]
        summary = report["financial_summary"]
        news = st.session_state.get("news")

        st.subheader(f"{analysis['corp_name']} — {report['fiscal_period']}")
        if analysis.get("from_cache"):
            st.caption("⚡ 캐시된 결과입니다 (24시간 이내 재조회).")

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("매출 YoY", f"{summary['revenue_yoy_change_pct']}%" if summary["revenue_yoy_change_pct"] is not None else "N/A")
        col2.metric("영업이익률", f"{summary['operating_margin_pct']}%" if summary["operating_margin_pct"] is not None else "N/A")
        col3.metric("부채비율", f"{summary['debt_ratio_pct']}%" if summary["debt_ratio_pct"] is not None else "N/A")
        col4.metric("ROE", f"{summary['roe_pct']}%" if summary["roe_pct"] is not None else "N/A")

        audit = analysis.get("audit_opinion") or {}
        if audit.get("opinion"):
            badge_color = theme.audit_badge_color(audit["opinion"])
            st.markdown(
                f"<div style='margin:4px 0 12px 0;'>"
                f"<span style='background:{badge_color};color:#fff;padding:3px 12px;"
                "border-radius:999px;font-size:13px;font-weight:700;'>"
                f"🧾 감사의견: {audit['opinion']}</span>"
                f"<span style='color:#52514e;font-size:13px;margin-left:10px;'>"
                f"감사인: {audit.get('auditor') or 'N/A'}</span></div>",
                unsafe_allow_html=True,
            )
            if audit.get("special_note"):
                st.warning(f"⚠️ 감사보고서 특기사항: {audit['special_note']}")

        valuation = analysis.get("valuation") or {}
        dividend = analysis.get("dividend") or {}
        if valuation.get("per") is not None or valuation.get("pbr") is not None:
            val_col1, val_col2, val_col3, val_col4 = st.columns(4)
            val_col1.metric("PER", f"{valuation['per']}배" if valuation.get("per") is not None else "N/A")
            val_col2.metric("PBR", f"{valuation['pbr']}배" if valuation.get("pbr") is not None else "N/A")
            val_col3.metric(
                "기준 종가",
                f"{valuation['close_price']:,.0f}원" if valuation.get("close_price") is not None else "N/A",
                help=f"거래일: {valuation.get('trade_date', 'N/A')}",
            )
            val_col4.metric(
                "배당수익률",
                f"{dividend['cash_dividend_yield_pct']}%" if dividend.get("cash_dividend_yield_pct") is not None else "N/A",
                help=(
                    f"배당성향: {dividend.get('dividend_payout_ratio_pct', 'N/A')}% · "
                    f"주당배당금: {dividend.get('dividend_per_share', 'N/A')}원"
                ),
            )

        st.markdown("#### 재무 변화 요약 (LLM 해석)")
        st.write(summary["commentary"])

        chart_col, radar_col = st.columns(2)

        with chart_col:
            st.markdown("#### 매출·영업이익: 당기 vs 전기")
            st.caption("단위가 다른 두 지표를 각각의 축으로 나눠 표시합니다 (조원).")
            st.plotly_chart(
                _bar_chart(
                    ["전기", "당기"],
                    [_to_jo(ratios.get("revenue_prior")), _to_jo(ratios.get("revenue"))],
                    "매출액 (조원)",
                ),
                use_container_width=True,
            )
            st.plotly_chart(
                _bar_chart(
                    ["전기", "당기"],
                    [_to_jo(ratios.get("operating_income_prior")), _to_jo(ratios.get("operating_income"))],
                    "영업이익 (조원)",
                ),
                use_container_width=True,
            )

        with radar_col:
            st.markdown("#### 리스크 카테고리 레이더")
            st.caption("바깥쪽일수록 심각도가 높습니다 (0=없음 ~ 3=높음).")
            scores = {cat: 0 for cat in RISK_CATEGORIES}
            for rf in report["risk_factors"]:
                scores[rf["category"]] = max(scores[rf["category"]], SEVERITY_SCORE.get(rf["severity"], 0))
            radar = go.Figure()
            radar.add_trace(
                go.Scatterpolar(
                    r=list(scores.values()) + [list(scores.values())[0]],
                    theta=RISK_CATEGORIES + [RISK_CATEGORIES[0]],
                    fill="toself",
                    fillcolor="rgba(42,120,214,0.15)",
                    line=dict(color=theme.SINGLE_SERIES_COLOR, width=2),
                    marker=dict(
                        size=9,
                        color=[theme.CATEGORY_COLORS[c] for c in RISK_CATEGORIES] + [theme.CATEGORY_COLORS[RISK_CATEGORIES[0]]],
                    ),
                    name="심각도",
                )
            )
            radar.update_layout(
                height=330,
                showlegend=False,
                paper_bgcolor=theme.CHART_SURFACE,
                font=dict(color=theme.CHART_INK_PRIMARY),
                polar=dict(
                    bgcolor=theme.CHART_SURFACE,
                    radialaxis=dict(
                        visible=True,
                        range=[0, 3],
                        tickvals=[0, 1, 2, 3],
                        ticktext=["없음", "낮음", "중간", "높음"],
                        gridcolor=theme.CHART_GRIDLINE,
                    ),
                    angularaxis=dict(gridcolor=theme.CHART_GRIDLINE),
                ),
            )
            st.plotly_chart(radar, use_container_width=True)

        raw_statements = analysis.get("raw_statements") or []
        if raw_statements:
            with st.expander("📄 전체 재무제표 원본 보기 (검증용)"):
                available_statements = sorted(
                    {row["sj_nm"] for row in raw_statements},
                    key=lambda name: (
                        report_utils.STATEMENT_ORDER.index(name)
                        if name in report_utils.STATEMENT_ORDER
                        else len(report_utils.STATEMENT_ORDER)
                    ),
                )
                statement_choice = st.selectbox(
                    "재무제표 종류", available_statements, key="statement_choice"
                )
                filtered_rows = [row for row in raw_statements if row["sj_nm"] == statement_choice]
                st.markdown(
                    report_utils.build_statement_html_table(filtered_rows), unsafe_allow_html=True
                )
                st.caption("금액 단위: 원. DART 사업보고서 원자료를 그대로 표시합니다(단위 변환 없음).")

        st.markdown("#### 리스크 트렌드 (연도별)")
        trend_col1, trend_col2 = st.columns([1, 3])
        with trend_col1:
            trend_years = st.number_input("조회 연도 수", min_value=2, max_value=5, value=3, key="trend_years")
            if st.button("트렌드 조회", key="risk_trend_btn"):
                with st.spinner(f"최근 {trend_years}개년 리스크 분석 중... (연도당 LLM 호출 포함, 시간이 걸릴 수 있습니다)"):
                    try:
                        trend_resp = requests.get(
                            f"{BACKEND_URL}/companies/{analysis['corp_code']}/risk-trend",
                            params={
                                "corp_name": analysis["corp_name"],
                                "bsns_year": analysis["bsns_year"],
                                "stock_code": selected["stock_code"] if selected else "",
                                "years": trend_years,
                            },
                            timeout=180,
                        )
                        trend_resp.raise_for_status()
                        st.session_state.risk_trend = trend_resp.json()
                    except requests.HTTPError as exc:
                        st.error(f"트렌드 조회 실패: {exc.response.json().get('detail', exc)}")
                    except requests.RequestException as exc:
                        st.error(f"백엔드 연결 실패: {exc}")

        risk_trend = st.session_state.get("risk_trend")
        with trend_col2:
            if risk_trend and risk_trend.get("years"):
                trend_fig = go.Figure()
                trend_years_labels = [y["bsns_year"] for y in risk_trend["years"]]
                for cat in RISK_CATEGORIES:
                    cat_scores = [
                        next((s["severity_score"] for s in y["scores"] if s["category"] == cat), 0)
                        for y in risk_trend["years"]
                    ]
                    trend_fig.add_trace(
                        go.Scatter(
                            x=trend_years_labels,
                            y=cat_scores,
                            mode="lines+markers",
                            name=cat,
                            line=dict(color=theme.CATEGORY_COLORS[cat], width=2),
                            marker=dict(size=9, color=theme.CATEGORY_COLORS[cat]),
                        )
                    )
                trend_fig.update_layout(
                    height=300,
                    plot_bgcolor=theme.CHART_SURFACE,
                    paper_bgcolor=theme.CHART_SURFACE,
                    font=dict(color=theme.CHART_INK_PRIMARY),
                    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
                    yaxis=dict(
                        title="심각도",
                        range=[-0.2, 3.2],
                        tickvals=[0, 1, 2, 3],
                        ticktext=["없음", "낮음", "중간", "높음"],
                        gridcolor=theme.CHART_GRIDLINE,
                    ),
                    xaxis=dict(title="사업연도", type="category", showgrid=False, color=theme.CHART_INK_MUTED),
                )
                st.plotly_chart(trend_fig, use_container_width=True)
            else:
                st.caption("왼쪽에서 '트렌드 조회'를 누르면 연도별 리스크 심각도 추이가 표시됩니다.")

        st.markdown("#### 리스크 요인")
        if not report["risk_factors"]:
            st.write("추출된 리스크 요인이 없습니다.")
        for rf in report["risk_factors"]:
            sev = rf["severity"]
            badge_color = theme.STATUS_COLORS.get(sev, theme.CHART_INK_MUTED)
            badge_label = theme.STATUS_LABELS.get(sev, sev)
            badge_icon = theme.STATUS_ICONS.get(sev, "⚪")
            with st.container(border=True):
                # 배지는 고정된 상태 팔레트 값만 사용 — LLM이 생성한 자유 텍스트는
                # 아래 별도의 st.markdown(escape 적용)으로만 렌더링해 XSS 위험을 피한다.
                st.markdown(
                    f"<span style='background:{badge_color};color:#fff;padding:2px 10px;"
                    "border-radius:999px;font-size:12px;font-weight:700;'>"
                    f"{badge_icon} {badge_label}</span>",
                    unsafe_allow_html=True,
                )
                st.markdown(f"**[{rf['category']}]** {rf['detail']}")
                if rf.get("evidence_quote"):
                    st.markdown(f"> 원문: “{rf['evidence_quote']}”")
                st.caption(f"출처: {rf['source']}")

        if news is not None:
            st.markdown(f"#### 관련 최근 뉴스 ({len(news)}건)")
            if not news:
                st.write("관련 뉴스를 찾지 못했습니다.")
            for article in news:
                with st.container(border=True):
                    st.markdown(f"**[{article['title']}]({article['link']})**")
                    st.caption(f"{article['pub_date']}  ·  {article['description']}")

        st.divider()
        st.caption(report["disclaimer"])

        st.download_button(
            "📥 Markdown 리포트 다운로드",
            data=report_utils.build_markdown_report(analysis, news).encode("utf-8"),
            file_name=f"{analysis['corp_name']}_{analysis['bsns_year']}_report.md",
            mime="text/markdown",
        )

with tab_compare:
    st.subheader(f"최대 {MAX_COMPARE}개 기업 재무비율 비교")

    search_col, select_col = st.columns([1, 2])
    with search_col:
        compare_query = st.text_input("추가할 기업명", placeholder="예: SK하이닉스", key="compare_query")
        if st.button("검색", key="compare_search_btn") and compare_query:
            try:
                resp = requests.get(
                    f"{BACKEND_URL}/companies/search", params={"name": compare_query}, timeout=15
                )
                resp.raise_for_status()
                st.session_state.compare_candidates = resp.json()
            except requests.HTTPError as exc:
                st.session_state.compare_candidates = []
                st.error(f"검색 실패: {exc.response.json().get('detail', exc)}")
            except requests.RequestException as exc:
                st.error(f"백엔드 연결 실패: {exc}")

    with select_col:
        if st.session_state.compare_candidates:
            compare_options = {
                f"{c['corp_name']} ({c['stock_code'] or '비상장'})": c
                for c in st.session_state.compare_candidates
            }
            compare_label = st.selectbox("검색 결과에서 선택", list(compare_options.keys()), key="compare_select")
            if st.button("비교 목록에 추가", key="compare_add_btn"):
                pick = compare_options[compare_label]
                existing_codes = {c["corp_code"] for c in st.session_state.compare_list}
                if len(st.session_state.compare_list) >= MAX_COMPARE:
                    st.warning(f"최대 {MAX_COMPARE}개 기업까지 비교할 수 있습니다.")
                elif pick["corp_code"] in existing_codes:
                    st.warning(f"{pick['corp_name']}은(는) 이미 목록에 있습니다.")
                else:
                    st.session_state.compare_list.append(pick)

    if st.session_state.compare_list:
        st.write("**현재 비교 목록:**")
        for c in list(st.session_state.compare_list):
            row_col, remove_col = st.columns([4, 1])
            row_col.write(f"- {c['corp_name']} ({c['stock_code'] or '비상장'})")
            if remove_col.button("제거", key=f"remove_{c['corp_code']}"):
                st.session_state.compare_list = [
                    x for x in st.session_state.compare_list if x["corp_code"] != c["corp_code"]
                ]
                st.rerun()

    compare_bsns_year = st.text_input("비교 사업연도", value="2025", key="compare_bsns_year")
    run_compare = st.button(
        "비교 실행",
        type="primary",
        disabled=len(st.session_state.compare_list) < 2,
        help="2개 이상 기업을 목록에 추가해야 실행할 수 있습니다.",
    )

    if run_compare:
        rows = []
        progress = st.progress(0.0, text="비교 분석 중...")
        total = len(st.session_state.compare_list)
        for idx, c in enumerate(st.session_state.compare_list):
            try:
                resp = requests.get(
                    f"{BACKEND_URL}/companies/{c['corp_code']}/analysis",
                    params={
                        "corp_name": c["corp_name"],
                        "bsns_year": compare_bsns_year,
                        "stock_code": c["stock_code"],
                        "force_refresh": False,
                    },
                    timeout=90,
                )
                resp.raise_for_status()
                data = resp.json()
                fs = data["report"]["financial_summary"]
                val = data.get("valuation") or {}
                rows.append(
                    {
                        "기업명": data["corp_name"],
                        "매출YoY(%)": fs["revenue_yoy_change_pct"],
                        "영업이익률(%)": fs["operating_margin_pct"],
                        "부채비율(%)": fs["debt_ratio_pct"],
                        "ROE(%)": fs["roe_pct"],
                        "유동비율(%)": fs["current_ratio_pct"],
                        "PER(배)": val.get("per"),
                        "PBR(배)": val.get("pbr"),
                    }
                )
            except requests.HTTPError as exc:
                st.error(f"{c['corp_name']} 분석 실패: {exc.response.json().get('detail', exc)}")
            except requests.RequestException as exc:
                st.error(f"{c['corp_name']} 분석 중 백엔드 연결 실패: {exc}")
            progress.progress((idx + 1) / total, text=f"{c['corp_name']} 완료 ({idx + 1}/{total})")
        st.session_state.compare_rows = rows
        st.session_state.compare_bsns_year_done = compare_bsns_year

    compare_rows = st.session_state.get("compare_rows")
    if compare_rows:
        st.markdown("#### 재무비율 비교 결과")
        st.markdown(report_utils.build_comparison_html_table(compare_rows), unsafe_allow_html=True)
        st.download_button(
            "📥 CSV로 다운로드",
            data=report_utils.build_comparison_csv(compare_rows).encode("utf-8-sig"),
            file_name=f"company_comparison_{st.session_state.get('compare_bsns_year_done', compare_bsns_year)}.csv",
            mime="text/csv",
        )
