"""색상/스타일 상수. dataviz 스킬의 색상 공식으로 검증된 팔레트를 사용한다.

카테고리 색상은 5개 리스크 카테고리(환율/규제/경쟁/원자재/기타)에 고정 순서로
매핑한다 — 어떤 차트에서든 같은 카테고리는 항상 같은 색이어야 한다("색상은
데이터를 따라가지, 순위를 따라가지 않는다"). severity(low/mid/high)는 색상이
아니라 "상태"이므로 별도의 status 팔레트를 쓰고, 텍스트 컬러가 아니라
아이콘+배지로만 사용한다.
"""
from __future__ import annotations

# 카테고리 팔레트 (고정 순서 — 절대 순환/재배정하지 않음)
RISK_CATEGORIES = ["환율", "규제", "경쟁", "원자재", "기타"]
CATEGORY_COLORS = {
    "환율": "#2a78d6",   # blue
    "규제": "#1baf7a",   # aqua
    "경쟁": "#eda100",   # yellow
    "원자재": "#008300",  # green
    "기타": "#4a3aa7",   # violet
}

# status 팔레트 (고정 — 테마와 무관, 경고 의미를 담당하므로 파스텔화하지 않음)
STATUS_COLORS = {
    "low": "#0ca30c",     # good
    "mid": "#fab219",     # warning
    "high": "#d03b3b",    # critical
}
STATUS_LABELS = {"low": "낮음", "mid": "주의", "high": "위험"}
STATUS_ICONS = {"low": "🟢", "mid": "🟡", "high": "🔴"}

# 차트 크롬(축/그리드/잉크)
CHART_INK_PRIMARY = "#0b0b0b"
CHART_INK_MUTED = "#898781"
CHART_GRIDLINE = "#e1e0d9"
CHART_SURFACE = "#ffffff"

# 시리즈 단일색(매출/영업이익처럼 차트당 시리즈가 하나뿐인 경우)
SINGLE_SERIES_COLOR = "#2a78d6"

CUSTOM_CSS = """
<style>
/* 카드형 컨테이너 - 파스텔 하늘색 톤과 어울리는 은은한 경계선 */
div[data-testid="stMetric"] {
    background: #f6fafd;
    border: 1px solid #d7e6f5;
    border-radius: 10px;
    padding: 12px 14px;
}
div[data-testid="stMetricLabel"] {
    font-weight: 600;
    color: #52514e;
}
/* 컨테이너 카드(리스크 요인, 뉴스 등 st.container(border=True)) 은은하게 */
div[data-testid="stVerticalBlockBorderWrapper"] {
    border-radius: 10px;
    border-color: #d7e6f5 !important;
}
/* 탭 밑줄 강조색 */
button[data-baseweb="tab"] {
    font-weight: 600;
}
</style>
"""

# 홈페이지형 히어로 배너 - st.title 대신 사용해 Streamlit 기본 heading의
# hover 앵커링크(노션 스타일)를 피하고, 실제 웹서비스 랜딩 헤더에 가깝게 구성
HERO_HTML = """
<div style="
    background: linear-gradient(135deg, #eaf4fc 0%, #f7fbfe 60%, #ffffff 100%);
    border: 1px solid #d7e6f5;
    border-radius: 18px;
    padding: 28px 36px;
    margin-bottom: 22px;
">
  <div style="display:flex; align-items:center; gap:12px;">
    <span style="font-size:32px; line-height:1;">📊</span>
    <span style="font-size:26px; font-weight:800; color:#0b0b0b; letter-spacing:-0.3px;">
        DART Risk Insight
    </span>
  </div>
  <div style="font-size:15px; color:#52514e; margin-top:10px;">
    DART 공시 데이터를 기반으로 재무비율과 리스크 요인을 자동 분석하는 대시보드
  </div>
  <div style="font-size:12.5px; color:#898781; margin-top:10px; line-height:1.5;">
    재무 수치는 DART 공시 데이터를 코드로 직접 계산한 값이며, 리스크 요약과 해석은 LLM이 생성합니다.
    투자 판단 근거로 사용할 수 없습니다.
  </div>
</div>
"""

# 라벨이 있는 입력창 옆에 나란히 놓이는 버튼의 높이를 맞추기 위한 스페이서
BUTTON_ALIGN_SPACER = "<div style='height:1.85em'></div>"


def audit_badge_color(opinion: str | None) -> str:
    """감사의견 문자열에 따라 배지 색상(상태 팔레트)을 반환한다.

    "적정의견"이 아니면(한정/부적정/의견거절 등) 위험 신호이므로 critical로 표시.
    """
    if not opinion:
        return CHART_INK_MUTED
    return STATUS_COLORS["low"] if opinion == "적정의견" else STATUS_COLORS["high"]
