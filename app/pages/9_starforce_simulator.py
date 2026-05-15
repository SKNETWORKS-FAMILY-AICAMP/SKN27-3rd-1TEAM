import streamlit as st
import streamlit.components.v1 as components
import random
import sys
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from dataclasses import dataclass, field
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = PROJECT_ROOT / "src"
for path in (PROJECT_ROOT, SRC_ROOT):
    path_text = str(path)
    if path_text not in sys.path:
        sys.path.insert(0, path_text)

from app.common.assets import asset_path, path_to_data_uri  # noqa: E402
from app.common.bgm import render_bgm_control_button, render_page_bgm  # noqa: E402
from app.common.chat_render import render_manual_page_if_requested, render_top_navigation  # noqa: E402
from app.common.chat_style import render_style  # noqa: E402

render_manual_page_if_requested("starforce")

# ═══════════════════════════════════════════════════════
# 1. 스타포스 데이터 (KMS 30성 기준)
# ═══════════════════════════════════════════════════════

def calc_cost(item_level: int, star: int) -> int:
    """강화 비용 추정치 계산."""
    base = round(item_level ** 3 * (star + 1) / 2500 + 10) * 1000
    return base

# 성수별 확률 테이블 [성공%, 유지%, 실패(유지)%, 파괴%]
PROB_TABLE = {
    0:  [95.0,  5.0,  0.0,  0.0],
    1:  [90.0, 10.0,  0.0,  0.0],
    2:  [85.0, 15.0,  0.0,  0.0],
    3:  [85.0, 15.0,  0.0,  0.0],
    4:  [80.0, 20.0,  0.0,  0.0],
    5:  [75.0, 25.0,  0.0,  0.0],
    6:  [70.0, 30.0,  0.0,  0.0],
    7:  [65.0, 35.0,  0.0,  0.0],
    8:  [60.0, 40.0,  0.0,  0.0],
    9:  [55.0, 45.0,  0.0,  0.0],
    10: [50.0, 50.0,  0.0,  0.0],
    11: [45.0, 55.0,  0.0,  0.0],
    12: [40.0, 60.0,  0.0,  0.0],
    13: [35.0, 65.0,  0.0,  0.0],
    14: [30.0, 70.0,  0.0,  0.0],
    15: [30.0,  0.0, 67.9,  2.1],
    16: [30.0,  0.0, 67.9,  2.1],
    17: [15.0,  0.0, 78.2,  6.8],
    18: [15.0,  0.0, 78.2,  6.8],
    19: [15.0,  0.0, 76.5,  8.5],
    20: [30.0,  0.0, 59.5, 10.5],
    21: [15.0,  0.0, 72.25, 12.75],
    22: [15.0,  0.0, 68.0, 17.0],
    23: [10.0,  0.0, 72.0, 18.0],
    24: [10.0,  0.0, 72.0, 18.0],
    25: [10.0,  0.0, 72.0, 18.0],
    26: [7.0,   0.0, 74.4, 18.6],
    27: [5.0,   0.0, 76.0, 19.0],
    28: [3.0,   0.0, 77.6, 19.4],
    29: [1.0,   0.0, 79.2, 19.8],
}

SAFE_STARS = {5, 10, 15}
DESTROY_RETURN_STAR = 12
ITEM_LEVELS = [80, 100, 110, 120, 130, 135, 140, 145, 150, 160, 200, 250]

def max_star(item_level: int) -> int:
    if item_level < 95: return 5
    if item_level < 108: return 8
    if item_level < 118: return 10
    if item_level < 128: return 15
    if item_level < 138: return 20
    return 30

# ═══════════════════════════════════════════════════════
# 2. 강화 로직
# ═══════════════════════════════════════════════════════

@dataclass
class EnhanceConfig:
    item_level: int = 150
    current_star: int = 0
    target_star: int = 17
    item_price: int = 0
    safeguard: list = field(default_factory=list)
    restore: list = field(default_factory=list)
    event_1plus1: bool = False
    event_30pct_off: bool = False
    event_5_10_15: bool = False
    event_destroy_30: bool = False
    mvp_discount: float = 0.0
    pc_cafe: bool = False

def get_cost(star: int, cfg: EnhanceConfig) -> int:
    base = calc_cost(cfg.item_level, star)
    mult = 1.0
    if cfg.event_30pct_off:
        mult *= 0.7
    if cfg.mvp_discount > 0:
        mult *= (1 - cfg.mvp_discount)
    if cfg.pc_cafe:
        mult *= 0.95
    cost = int(base * mult)
    if star in cfg.safeguard:
        cost *= 2
    return cost

def get_prob(star: int, cfg: EnhanceConfig) -> list:
    p = list(PROB_TABLE.get(star, [1.0, 0.0, 75.6, 23.4]))
    if cfg.event_5_10_15 and star in SAFE_STARS:
        return [100.0, 0.0, 0.0, 0.0]
    if cfg.event_destroy_30 and star <= 21:
        reduced = p[3] * 0.3
        p[2] += reduced
        p[3] -= reduced
    return p

def simulate_once(cfg: EnhanceConfig) -> dict:
    current = cfg.current_star
    total_cost = 0
    total_attempts = 0
    destroys = 0
    restore_count = 0
    restore_cost = 0
    history = []
    consecutive_fail = 0

    while current < cfg.target_star:
        cost = get_cost(current, cfg)
        probs = get_prob(current, cfg)
        is_chance = consecutive_fail >= 2

        if is_chance:
            result = 'success'
            next_star = current + 1
            consecutive_fail = 0
        else:
            roll = random.uniform(0, 100)
            s, m, d, x = probs
            if roll < s:
                result = 'success'
                next_star = current + 1
                consecutive_fail = 0
            elif roll < s + m:
                result = 'maintain'
                next_star = current
                consecutive_fail += 1
            elif roll < s + m + d:
                result = 'maintain'
                next_star = current
                consecutive_fail += 1
            else:
                if current in SAFE_STARS:
                    result = 'maintain'
                    next_star = current
                    consecutive_fail += 1
                elif current in cfg.safeguard:
                    result = 'safeguard'
                    next_star = current
                    consecutive_fail += 1
                else:
                    result = 'destroy'
                    next_star = DESTROY_RETURN_STAR
                    destroys += 1
                    consecutive_fail = 0
                    if current in cfg.restore:
                        rc = int(cfg.item_price * 0.3) if cfg.item_price > 0 else 0
                        restore_cost += rc
                        restore_count += 1

        extra_success = cfg.event_1plus1 and current <= 10 and result == 'success'
        total_cost += cost
        total_attempts += 1
        history.append({
            'attempt': total_attempts,
            'from_star': current,
            'to_star': next_star,
            'result': result,
            'cost': cost,
            'cumulative_cost': total_cost,
            'chance_time': is_chance,
        })
        current = next_star

        if extra_success and current < cfg.target_star:
            cost2 = get_cost(current, cfg)
            total_cost += cost2
            total_attempts += 1
            next2 = current + 1
            history.append({
                'attempt': total_attempts,
                'from_star': current,
                'to_star': next2,
                'result': 'success_bonus',
                'cost': cost2,
                'cumulative_cost': total_cost,
                'chance_time': False,
            })
            current = next2

    return {
        'total_cost': total_cost,
        'total_attempts': total_attempts,
        'destroys': destroys,
        'restore_count': restore_count,
        'restore_cost': restore_cost,
        'history': history,
    }

def run_bulk(cfg: EnhanceConfig, n: int = 1000) -> pd.DataFrame:
    rows = []
    for _ in range(n):
        r = simulate_once(cfg)
        rows.append({
            '총 비용': r['total_cost'],
            '총 시도': r['total_attempts'],
            '파괴 횟수': r['destroys'],
        })
    return pd.DataFrame(rows)

def calc_expected(cfg: EnhanceConfig) -> pd.DataFrame:
    rows = []
    cumulative = 0
    for s in range(cfg.current_star, cfg.target_star):
        p = get_prob(s, cfg)
        suc = p[0] / 100
        cost = get_cost(s, cfg)
        expected_tries = 1 / suc if suc > 0 else float('inf')
        expected_cost = cost * expected_tries
        expected_destroy = (p[3]/100) * expected_tries
        cumulative += expected_cost
        rows.append({
            '강화 단계': f"{s}⭐ → {s+1}⭐",
            '성공률': f"{p[0]:.2f}%",
            '유지': f"{p[1]:.2f}%",
            '실패(유지)': f"{p[2]:.2f}%",
            '파괴': f"{p[3]:.2f}%",
            '1회 비용': f"{cost:,}",
            '구간 기댓값': f"{expected_cost/1e8:.2f}억",
            '평균 파괴': f"{expected_destroy:.3f}회",
            '누적 기댓값': f"{cumulative/1e8:.2f}억",
        })
    return pd.DataFrame(rows)

# ═══════════════════════════════════════════════════════
# 3. Streamlit UI
# ═══════════════════════════════════════════════════════

st.set_page_config(page_title="스타포스 시뮬레이터", page_icon="⭐", layout="wide")

render_style()
render_page_bgm("starforce")
st.markdown(
    '<div class="maple-sub-page-marker maple-starforce-page-marker"></div>',
    unsafe_allow_html=True,
)
render_top_navigation(active_menu_key="starforce")
render_bgm_control_button()

meisterville_background = path_to_data_uri(asset_path("마이스터빌.webp"), "image/webp")
if meisterville_background:
    st.markdown(
        f"""
<style>
[data-testid="stAppViewContainer"]:has(.maple-starforce-page-marker) {{
    background:
        linear-gradient(180deg, rgba(8, 7, 6, 0.24), rgba(8, 7, 6, 0.62)),
        url("{meisterville_background}") center top / cover fixed no-repeat !important;
}}

[data-testid="stAppViewContainer"]:has(.maple-starforce-page-marker)::before {{
    content: "";
    position: fixed;
    inset: 0;
    pointer-events: none;
    background:
        radial-gradient(circle at 50% 18%, rgba(255, 211, 145, 0.15), transparent 34%),
        rgba(0, 0, 0, 0.04);
    z-index: 0;
}}

[data-testid="stAppViewContainer"]:has(.maple-starforce-page-marker) .main,
[data-testid="stAppViewContainer"]:has(.maple-starforce-page-marker) .block-container {{
    position: relative;
    z-index: 1;
}}
</style>
""",
        unsafe_allow_html=True,
    )

st.markdown("""
<style>
[data-testid="stAppViewContainer"]:has(.maple-starforce-page-marker) .st-key-maple-brand-bar,
[data-testid="stAppViewContainer"]:has(.maple-starforce-page-marker) .st-key-maple-home-badge {
    display: none !important;
}

[data-testid="stAppViewContainer"]:has(.maple-starforce-page-marker) .block-container {
    max-width: 1180px !important;
    padding: calc(4.1rem - 10px) 1.25rem 2rem !important;
}

.sf-header {
    background: rgba(8, 7, 6, 0.86) !important;
    border: 1px solid rgba(255, 200, 137, 0.26) !important;
    border-radius: 8px !important;
    padding: 1.2rem 1.35rem !important;
    margin: 0 0 1rem 0 !important;
    box-shadow: 0 18px 44px rgba(0, 0, 0, 0.28) !important;
}

.sf-header h1 {
    font-family: "MaplestoryBold", Inter, ui-sans-serif, system-ui, sans-serif !important;
    font-size: 1.45rem !important;
    font-weight: 400 !important;
    margin: 0 !important;
    color: #ffc889 !important;
    background: none !important;
    -webkit-text-fill-color: #ffc889 !important;
}

.sf-header p {
    color: rgba(255, 247, 232, 0.72) !important;
    font-size: 0.82rem !important;
    margin: 0.42rem 0 0 0 !important;
}

.section-label {
    font-family: "MaplestoryBold", Inter, ui-sans-serif, system-ui, sans-serif !important;
    font-size: 0.72rem !important;
    letter-spacing: 0.05em !important;
    color: #ffc889 !important;
    margin: 1rem 0 0.45rem 0 !important;
    text-transform: none !important;
}

.metric-card {
    background: rgba(8, 7, 6, 0.84) !important;
    border: 1px solid rgba(255, 200, 137, 0.22) !important;
    border-radius: 8px !important;
    padding: 0.95rem 1rem !important;
}

.metric-card .m-label { color: rgba(255, 247, 232, 0.6) !important; font-size: 0.76rem !important; }
.metric-card .m-value { color: #ffc889 !important; font-size: 1.45rem !important; }
.metric-card .m-sub { color: rgba(255, 247, 232, 0.56) !important; font-size: 0.73rem !important; }

[data-testid="stExpander"] {
    background: rgba(8, 7, 6, 0.84) !important;
    border: 1px solid rgba(255, 200, 137, 0.2) !important;
    border-radius: 8px !important;
    box-shadow: 0 18px 44px rgba(0, 0, 0, 0.26) !important;
}

[data-testid="stExpander"] details,
[data-testid="stDataFrame"],
[data-testid="stPlotlyChart"],
[data-testid="stTabs"] [data-testid="stVerticalBlockBorderWrapper"] {
    background: rgba(8, 7, 6, 0.82) !important;
}

[data-testid="stTabs"] {
    background: rgba(8, 7, 6, 0.82) !important;
    border: 1px solid rgba(255, 200, 137, 0.2) !important;
    border-radius: 8px !important;
    padding: 0.95rem !important;
    box-shadow: 0 18px 44px rgba(0, 0, 0, 0.28) !important;
    backdrop-filter: blur(3px);
}

[data-testid="stTabs"] [role="tablist"] {
    background: rgba(13, 11, 9, 0.74) !important;
    border: 1px solid rgba(255, 200, 137, 0.14) !important;
    border-radius: 8px !important;
    padding: 0.3rem !important;
    gap: 0.25rem;
}

[data-testid="stTabs"] button[role="tab"] {
    border-radius: 7px !important;
    color: rgba(255, 247, 232, 0.72) !important;
}

[data-testid="stTabs"] button[role="tab"][aria-selected="true"] {
    background: rgba(255, 200, 137, 0.18) !important;
    color: #ffc889 !important;
}

button[kind="primary"],
.stButton button[kind="primary"] {
    background: rgba(255, 200, 137, 0.92) !important;
    color: #130d08 !important;
    border: 1px solid rgba(255, 232, 190, 0.68) !important;
    border-radius: 8px !important;
}

.stButton button,
[data-testid="stBaseButton-secondary"],
[data-testid="stBaseButton-tertiary"] {
    border-radius: 8px !important;
}

label,
[data-testid="stWidgetLabel"],
[data-testid="stMarkdownContainer"],
[data-testid="stCaptionContainer"] {
    color: rgba(255, 247, 232, 0.82) !important;
}

div[data-baseweb="select"] > div,
div[data-testid="stNumberInput"] input {
    background: #0d0b09 !important;
    border-color: rgba(255, 200, 137, 0.28) !important;
    color: #fff7e8 !important;
}

div[data-testid="stCheckbox"] label {
    min-height: 2rem;
    align-items: center;
}

div[data-testid="stCheckbox"] p {
    margin: 0 !important;
    white-space: normal !important;
    overflow-wrap: anywhere !important;
}

svg[aria-label^="_arrow"],
svg[aria-label*="_arrow"],
[aria-label^="_arrow"],
[aria-label*="_arrow"],
[title^="_arrow"],
[title*="_arrow"] {
    color: transparent !important;
    font-size: 0 !important;
    overflow: hidden !important;
}

.stSelectSlider [data-baseweb="slider"] {
    padding-top: 0.75rem;
}

hr {
    border-color: rgba(255, 200, 137, 0.18) !important;
}

.sf-guide {
    margin-top: 1rem;
    padding: 1rem 1.1rem;
    border: 1px solid rgba(255, 200, 137, 0.22);
    border-radius: 8px;
    background: rgba(8, 7, 6, 0.84);
    box-shadow: 0 18px 44px rgba(0, 0, 0, 0.24);
}

.sf-source-note {
    margin: 0 0 1rem 0;
    padding: 0.8rem 0.95rem;
    border: 1px solid rgba(255, 200, 137, 0.18);
    border-radius: 8px;
    background: rgba(8, 7, 6, 0.82);
    color: rgba(255, 247, 232, 0.72);
    font-size: 0.8rem;
    line-height: 1.65;
    box-shadow: 0 14px 34px rgba(0, 0, 0, 0.18);
}

.sf-guide-title {
    margin: 0 0 0.6rem 0;
    color: #ffc889;
    font-family: "MaplestoryBold", Inter, ui-sans-serif, system-ui, sans-serif !important;
    font-size: 0.95rem;
}

.sf-guide-list {
    margin: 0;
    padding-left: 1.1rem;
    color: rgba(255, 247, 232, 0.76);
    font-size: 0.82rem;
    line-height: 1.7;
}

.sf-guide-grid {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 0.8rem;
}

.sf-guide-card {
    padding: 0.85rem 0.9rem;
    border: 1px solid rgba(255, 200, 137, 0.16);
    border-radius: 8px;
    background: rgba(13, 11, 9, 0.82);
}

.sf-guide-card strong {
    display: block;
    margin-bottom: 0.35rem;
    color: #ffc889;
    font-family: "MaplestoryBold", Inter, ui-sans-serif, system-ui, sans-serif !important;
    font-size: 0.78rem;
}

.sf-guide-card p {
    margin: 0;
    color: rgba(255, 247, 232, 0.72);
    font-size: 0.8rem;
    line-height: 1.65;
}

@media (max-width: 760px) {
    .sf-guide-grid {
        grid-template-columns: 1fr;
    }
}
</style>
""", unsafe_allow_html=True)

components.html(
    """
<script>
(() => {
  const parentDoc = window.parent.document;
  const hiddenAttr = "data-maple-arrow-hidden";

  const hideElement = (element) => {
    if (!element || element.getAttribute(hiddenAttr) === "true") return;
    element.style.setProperty("font-size", "0", "important");
    element.style.setProperty("color", "transparent", "important");
    element.style.setProperty("line-height", "0", "important");
    element.style.setProperty("max-width", "0", "important");
    element.style.setProperty("overflow", "hidden", "important");
    element.setAttribute("aria-hidden", "true");
    element.setAttribute(hiddenAttr, "true");
  };

  const cleanArrowText = () => {
    parentDoc
      .querySelectorAll('[aria-label*="_arrow"], [title*="_arrow"], [data-testid*="_arrow"]')
      .forEach(hideElement);

    const walker = parentDoc.createTreeWalker(parentDoc.body, NodeFilter.SHOW_TEXT);
    const nodes = [];
    while (walker.nextNode()) {
      const node = walker.currentNode;
      if (node.nodeValue && node.nodeValue.includes("_arrow")) nodes.push(node);
    }
    for (const node of nodes) {
      const element = node.parentElement;
      if (!element) continue;
      hideElement(element);
    }
  };

  cleanArrowText();
  [100, 250, 700, 1200, 2200].forEach((delay) => {
    parentDoc.defaultView.setTimeout(cleanArrowText, delay);
  });

  if (parentDoc.defaultView.__mapleStarforceArrowObserver) {
    parentDoc.defaultView.__mapleStarforceArrowObserver.disconnect();
  }
  const observer = new MutationObserver(() => cleanArrowText());
  observer.observe(parentDoc.body, { childList: true, subtree: true, characterData: true });
  parentDoc.defaultView.__mapleStarforceArrowObserver = observer;
})();
</script>
""",
    height=0,
)

st.markdown("""
<div class="sf-header">
    <h1>스타포스 시뮬레이터</h1>
    <p>공식 안내와 업데이트 확률표를 기준으로 강화 비용과 편차를 가볍게 확인하는 도구입니다.</p>
</div>
""", unsafe_allow_html=True)

st.markdown(
    """
<div class="sf-source-note">
근거: 최대 스타포스/파괴방지/흔적 복구 규칙은 메이플스토리 공식 가이드,
15~30성 확률표와 21성 이하 파괴확률 30% 감소 이벤트는 스타포스 개편 업데이트 공지 기준입니다.
메소 비용은 페이지 내부 공식으로 계산한 추정치이므로 실제 게임 UI와 차이가 있을 수 있습니다.
</div>
""",
    unsafe_allow_html=True,
)

# ─── 설정 패널 ────────────────────────────────────────
with st.expander("⚙️ 강화 설정", expanded=True):
    col1, col2, col3 = st.columns(3)

    with col1:
        st.markdown('<div class="section-label">장비 정보</div>', unsafe_allow_html=True)
        item_level = st.selectbox("장비 레벨", ITEM_LEVELS, index=ITEM_LEVELS.index(150))
        max_s = max_star(item_level)
        item_price = st.number_input(
            "노작 가격 (메소)", min_value=0, value=0, step=100_000_000, format="%d",
            help="장비 무강화 시세. 흔적 복구 비용 계산에 사용됩니다."
        )
        st.markdown('<div class="section-label">성수 설정</div>', unsafe_allow_html=True)
        ca, cb = st.columns(2)
        with ca: current_star = st.number_input("현재 성수", 0, max_s-1, 0)
        with cb: target_star = st.number_input("목표 성수", 1, max_s, min(17, max_s))
        if current_star >= target_star:
            st.error("목표 성수 > 현재 성수 이어야 합니다")

    with col2:
        st.markdown('<div class="section-label">파괴방지 (12성↑, 비용 2배)</div>', unsafe_allow_html=True)
        safeguard_stars = []
        sg_c = st.columns(3)
        for i, s in enumerate([15, 16, 17]):
            with sg_c[i]:
                if current_star <= s < target_star:
                    if st.checkbox(f"{s}성", key=f"sg{s}"): safeguard_stars.append(s)

        st.markdown('<div class="section-label">흔적 복구 (파괴 시 복구)</div>', unsafe_allow_html=True)
        restore_stars = []
        rs_c = st.columns(4)
        rs_options = [s for s in [15,16,17,18,19,20,21,22] if current_star <= s < target_star]
        for i, s in enumerate(rs_options):
            with rs_c[i % 4]:
                if st.checkbox(f"{s}성", key=f"rs{s}"): restore_stars.append(s)

        st.markdown('<div class="section-label">이벤트</div>', unsafe_allow_html=True)
        ev_1p1   = st.checkbox("10성 이하 강화 성공 시 1+1")
        ev_30off = st.checkbox("강화 비용 30% 할인 (샤타포스)")
        ev_51015 = st.checkbox("5 · 10 · 15성 성공확률 100%")
        ev_des30 = st.checkbox("파괴 확률 30% 감소 (21성 이하)")

    with col3:
        st.markdown('<div class="section-label">강화비용 할인</div>', unsafe_allow_html=True)
        mvp_opt = st.selectbox("MVP 등급", ["없음", "실버 (5%)", "골드 (10%)", "다이아/레드 (15%)"])
        mvp_map = {"없음": 0.0, "실버 (5%)": 0.05, "골드 (10%)": 0.10, "다이아/레드 (15%)": 0.15}
        mvp_disc = mvp_map[mvp_opt]
        pc_cafe = st.checkbox("PC방 할인 (5%)")

        st.markdown('<div class="section-label">예상 비용 미리보기</div>', unsafe_allow_html=True)
        # 설정 반영 비용 미리보기
        preview_cfg = EnhanceConfig(
            item_level=item_level, current_star=int(current_star),
            target_star=int(target_star), item_price=int(item_price),
            safeguard=[], restore=[],
            event_30pct_off=ev_30off, mvp_discount=mvp_disc, pc_cafe=pc_cafe,
        )
        if int(current_star) < int(target_star):
            preview_costs = [get_cost(s, preview_cfg) for s in range(int(current_star), int(target_star))]
            probs_suc = [get_prob(s, preview_cfg)[0]/100 for s in range(int(current_star), int(target_star))]
            rough_exp = sum(c / max(p, 0.001) for c, p in zip(preview_costs, probs_suc))
            st.metric("이론 기댓값 (파방 미적용)", f"{rough_exp/1e8:.1f}억")
        else:
            st.metric("이론 기댓값", "-")

cfg = EnhanceConfig(
    item_level=item_level, current_star=int(current_star),
    target_star=int(target_star), item_price=int(item_price),
    safeguard=safeguard_stars, restore=restore_stars,
    event_1plus1=ev_1p1, event_30pct_off=ev_30off,
    event_5_10_15=ev_51015, event_destroy_30=ev_des30,
    mvp_discount=mvp_disc, pc_cafe=pc_cafe,
)

st.divider()

tab_single, tab_bulk, tab_expect, tab_prob = st.tabs([
    "🎮 단일 시뮬", "📊 통계 분석", "📈 기댓값 테이블", "📋 확률표"
])

# ════════ 탭1: 단일 ════════════════════════════════════
with tab_single:
    cb1, cb2, _ = st.columns([1, 1, 4])
    with cb1:
        run_single = st.button("▶ 강화 시작", type="primary",
                               use_container_width=True, disabled=(int(current_star) >= int(target_star)))
    with cb2:
        run_100 = st.button("⚡ 100회 평균", use_container_width=True,
                            disabled=(int(current_star) >= int(target_star)))

    if run_single or run_100:
        if run_100:
            with st.spinner("⭐ 100회 시뮬레이션 중..."):
                results = [simulate_once(cfg) for _ in range(100)]
            r = {
                'total_cost': int(sum(x['total_cost'] for x in results) / 100),
                'total_attempts': int(sum(x['total_attempts'] for x in results) / 100),
                'destroys': round(sum(x['destroys'] for x in results) / 100, 2),
                'restore_count': round(sum(x['restore_count'] for x in results) / 100, 2),
                'restore_cost': int(sum(x['restore_cost'] for x in results) / 100),
                'history': results[0]['history'],
            }
            st.caption("📊 100회 평균값 · 그래프는 1번째 시뮬 결과")
        else:
            r = simulate_once(cfg)

        # 결과 카드
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            st.markdown(f"""<div class="metric-card">
                <div class="m-label">💰 총 소모 메소</div>
                <div class="m-value">{r['total_cost']/1e8:.2f}억</div>
                <div class="m-sub">{r['total_cost']:,} 메소</div>
            </div>""", unsafe_allow_html=True)
        with c2:
            st.markdown(f"""<div class="metric-card">
                <div class="m-label">🔨 총 강화 횟수</div>
                <div class="m-value">{r['total_attempts']:,}회</div>
                <div class="m-sub">1회당 {r['total_cost']//max(r['total_attempts'],1):,}메소</div>
            </div>""", unsafe_allow_html=True)
        with c3:
            dc = "#f87171" if r['destroys'] > 0 else "#34d399"
            dv = f"{r['destroys']:.1f}" if isinstance(r['destroys'], float) else str(r['destroys'])
            msg = "파괴 없이 성공! 🎉" if r['destroys'] == 0 else "파괴 발생 😭"
            st.markdown(f"""<div class="metric-card">
                <div class="m-label">💥 파괴 횟수</div>
                <div class="m-value" style="color:{dc}">{dv}회</div>
                <div class="m-sub">{msg}</div>
            </div>""", unsafe_allow_html=True)
        with c4:
            rc_v = r.get('restore_count', 0)
            rc_c = r.get('restore_cost', 0)
            st.markdown(f"""<div class="metric-card">
                <div class="m-label">🔄 흔적 복구</div>
                <div class="m-value">{rc_v}회</div>
                <div class="m-sub">복구 비용 {rc_c/1e8:.2f}억</div>
            </div>""", unsafe_allow_html=True)

        st.markdown("---")

        df_h = pd.DataFrame(r['history'])
        color_map = {
            'success': '#34d399', 'success_bonus': '#6ee7b7',
            'maintain': '#60a5fa', 'down': '#fb923c',
            'destroy': '#f87171', 'safeguard': '#a78bfa',
        }

        # 성수 변화 그래프
        fig1 = go.Figure()
        fig1.add_trace(go.Scatter(
            x=df_h['attempt'], y=df_h['to_star'],
            mode='lines+markers',
            line=dict(color='#FFD700', width=1.5),
            marker=dict(color=[color_map.get(r, '#888') for r in df_h['result']], size=5),
            hovertemplate='%{x}회차 · %{y}⭐<extra></extra>',
        ))
        dest_rows = df_h[df_h['result'] == 'destroy']
        if not dest_rows.empty:
            fig1.add_trace(go.Scatter(
                x=dest_rows['attempt'], y=dest_rows['to_star'],
                mode='markers', marker=dict(color='#f87171', size=14, symbol='x'),
                name='파괴', hovertemplate='💥 파괴 %{x}회차<extra></extra>',
            ))
        fig1.add_hline(y=int(target_star), line_dash="dash", line_color="#FFD700",
                       annotation_text=f"목표 {target_star}⭐",
                       annotation_font_color="#FFD700", annotation_font_size=11)
        fig1.update_layout(
            title=f"성수 변화 ({current_star}⭐ → {target_star}⭐)",
            paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(8,7,6,0.62)',
            font=dict(color='#d1d5db', family='MaplestoryLight, Inter, sans-serif'),
            xaxis=dict(gridcolor='#1f2937', title='시도 횟수', zeroline=False),
            yaxis=dict(gridcolor='#1f2937', title='성수', range=[-0.5, max_s+0.5]),
            height=320, showlegend=False, margin=dict(l=40, r=40, t=40, b=40),
        )
        st.plotly_chart(fig1, use_container_width=True)

        # 누적 비용 그래프
        fig2 = go.Figure()
        fig2.add_trace(go.Scatter(
            x=df_h['attempt'], y=df_h['cumulative_cost']/1e8,
            fill='tozeroy', fillcolor='rgba(255,165,0,0.1)',
            line=dict(color='#FFA500', width=2),
            hovertemplate='%{x}회차 · 누적 %{y:.2f}억<extra></extra>',
        ))
        fig2.update_layout(
            title="누적 메소 소모",
            paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(8,7,6,0.62)',
            font=dict(color='#d1d5db', family='MaplestoryLight, Inter, sans-serif'),
            xaxis=dict(gridcolor='#1f2937', title='시도 횟수', zeroline=False),
            yaxis=dict(gridcolor='#1f2937', title='억 메소'),
            height=240, showlegend=False, margin=dict(l=40, r=40, t=40, b=40),
        )
        st.plotly_chart(fig2, use_container_width=True)

        # 강화 로그
        with st.expander(f"📜 강화 로그 (총 {len(df_h)}회, 최근 100개)"):
            emoji_map = {
                'success': '✅ 성공', 'success_bonus': '✅ 성공(1+1)',
                'maintain': '🔵 유지', 'down': '🔻 하락',
                'destroy': '💥 파괴', 'safeguard': '🛡 파방(유지)',
            }
            ds = df_h.tail(100).copy()
            ds['결과'] = ds['result'].map(emoji_map)
            ds['성수 변화'] = ds.apply(lambda r: f"{r['from_star']}⭐ → {r['to_star']}⭐", axis=1)
            ds['비용'] = ds['cost'].apply(lambda x: f"{x:,}")
            ds['누적'] = ds['cumulative_cost'].apply(lambda x: f"{x/1e8:.2f}억")
            ds['찬스'] = ds['chance_time'].apply(lambda x: "⚡찬스" if x else "")
            st.dataframe(
                ds[['attempt', '성수 변화', '결과', '찬스', '비용', '누적']].rename(
                    columns={'attempt': '회차'}),
                use_container_width=True, hide_index=True,
            )
    else:
        st.markdown(
            '<div class="sf-source-note">위 설정을 마치고 강화 시작 또는 100회 평균 버튼을 눌러주세요.</div>',
            unsafe_allow_html=True,
        )

# ════════ 탭2: 통계 분석 ═══════════════════════════════
with tab_bulk:
    cn, cr = st.columns([2, 1])
    with cn:
        sim_n = st.select_slider("시뮬레이션 횟수",
                                 options=[100, 500, 1000, 3000, 5000, 10000], value=1000)
    with cr:
        run_bulk_btn = st.button(f"📊 {sim_n:,}회 분석", type="primary",
                                 use_container_width=True,
                                 disabled=(int(current_star) >= int(target_star)))

    if run_bulk_btn:
        with st.spinner(f"⭐ {sim_n:,}회 시뮬레이션 중..."):
            df_bulk = run_bulk(cfg, sim_n)

        costs = df_bulk['총 비용']

        c1, c2, c3, c4 = st.columns(4)
        stats = [
            ("💰 평균 비용", costs.mean(), f"중앙값 {costs.median()/1e8:.1f}억"),
            ("📈 75%ile", costs.quantile(0.75), f"90%ile {costs.quantile(0.9)/1e8:.1f}억"),
            ("😱 95%ile", costs.quantile(0.95), f"최대 {costs.max()/1e8:.1f}억"),
        ]
        for col, (label, val, sub) in zip([c1, c2, c3], stats):
            with col:
                st.markdown(f"""<div class="metric-card">
                    <div class="m-label">{label}</div>
                    <div class="m-value">{val/1e8:.1f}억</div>
                    <div class="m-sub">{sub}</div>
                </div>""", unsafe_allow_html=True)
        with c4:
            avg_d = df_bulk['파괴 횟수'].mean()
            no_d = (df_bulk['파괴 횟수'] == 0).mean() * 100
            st.markdown(f"""<div class="metric-card">
                <div class="m-label">💥 평균 파괴</div>
                <div class="m-value">{avg_d:.2f}회</div>
                <div class="m-sub">파괴 0회 {no_d:.0f}%</div>
            </div>""", unsafe_allow_html=True)

        st.markdown("---")

        # 비용 분포 히스토그램
        fig3 = go.Figure()
        fig3.add_trace(go.Histogram(
            x=costs/1e8, nbinsx=60,
            marker=dict(color='#FFD700', opacity=0.85), name='빈도',
        ))
        for val, color, label in [
            (costs.mean(), '#fb923c', '평균'),
            (costs.median(), '#34d399', '중앙값'),
            (costs.quantile(0.95), '#f87171', '95%ile'),
        ]:
            fig3.add_vline(x=val/1e8, line_dash="dash", line_color=color,
                           annotation_text=label, annotation_font_color=color)
        fig3.update_layout(
            title=f"{target_star}성 달성 비용 분포 ({sim_n:,}회)",
            paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(8,7,6,0.62)',
            font=dict(color='#d1d5db', family='MaplestoryLight, Inter, sans-serif'),
            xaxis=dict(gridcolor='#1f2937', title='소모 비용 (억 메소)'),
            yaxis=dict(gridcolor='#1f2937', title='횟수'),
            height=350, margin=dict(l=40, r=40, t=40, b=40),
        )
        st.plotly_chart(fig3, use_container_width=True)

        # 누적 확률 곡선
        sorted_costs = costs.sort_values().values
        cum_prob = [i / len(sorted_costs) * 100 for i in range(len(sorted_costs))]
        fig4 = go.Figure()
        fig4.add_trace(go.Scatter(
            x=sorted_costs/1e8, y=cum_prob,
            fill='tozeroy', fillcolor='rgba(99,102,241,0.1)',
            line=dict(color='#818cf8', width=2),
            hovertemplate='%{x:.1f}억 이하 달성 확률: %{y:.1f}%<extra></extra>',
        ))
        fig4.update_layout(
            title="누적 달성 확률 곡선",
            paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(8,7,6,0.62)',
            font=dict(color='#d1d5db', family='MaplestoryLight, Inter, sans-serif'),
            xaxis=dict(gridcolor='#1f2937', title='비용 (억 메소)'),
            yaxis=dict(gridcolor='#1f2937', title='누적 확률 (%)', range=[0, 100]),
            height=270, margin=dict(l=40, r=40, t=40, b=40),
        )
        st.plotly_chart(fig4, use_container_width=True)

        # 구간별 달성 확률 표
        st.subheader("구간별 달성 확률")
        q_rows = [{'달성 확률': f"{p}%ile 이하", '필요 메소': f"{costs.quantile(p/100)/1e8:.2f}억",
                   '정확한 메소': f"{int(costs.quantile(p/100)):,}"}
                  for p in [10, 25, 50, 75, 90, 95, 99]]
        st.dataframe(pd.DataFrame(q_rows), use_container_width=True, hide_index=True)

    else:
        st.markdown(
            '<div class="sf-source-note">시뮬레이션 횟수를 선택하고 분석 버튼을 눌러주세요.</div>',
            unsafe_allow_html=True,
        )

# ════════ 탭3: 기댓값 테이블 ═══════════════════════════
with tab_expect:
    st.markdown(f"**{current_star}⭐ → {target_star}⭐** 구간별 이론 기댓값 (이벤트/할인 설정 반영)")
    st.caption("찬스타임 미적용 단순 이론값 · 참고용")

    if int(current_star) < int(target_star):
        df_exp = calc_expected(cfg)
        st.dataframe(df_exp, use_container_width=True, hide_index=True, height=500)

        # 구간별 기댓값 막대그래프
        stage_data = []
        for s in range(cfg.current_star, cfg.target_star):
            p = get_prob(s, cfg)
            suc = p[0] / 100
            cost = get_cost(s, cfg)
            exp_cost = cost / suc if suc > 0 else 0
            stage_data.append({'구간': f"{s}→{s+1}⭐", '기댓값(억)': round(exp_cost/1e8, 3)})

        df_bar = pd.DataFrame(stage_data)
        fig5 = px.bar(df_bar, x='구간', y='기댓값(억)',
                      color='기댓값(억)',
                      color_continuous_scale=['#34d399', '#fbbf24', '#f87171'],
                      title="구간별 기댓값 비용")
        fig5.update_layout(
            paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(8,7,6,0.62)',
            font=dict(color='#d1d5db', family='MaplestoryLight, Inter, sans-serif'),
            xaxis=dict(gridcolor='#1f2937'),
            yaxis=dict(gridcolor='#1f2937', title='기댓값 (억 메소)'),
            coloraxis_showscale=False, height=300,
            margin=dict(l=40, r=40, t=40, b=40),
        )
        st.plotly_chart(fig5, use_container_width=True)
    else:
        st.markdown(
            '<div class="sf-source-note">목표 성수를 현재 성수보다 높게 설정해주세요.</div>',
            unsafe_allow_html=True,
        )

# ════════ 탭4: 확률표 ═════════════════════════════════
with tab_prob:
    st.subheader("📋 스타포스 확률표")
    show_all = st.checkbox("15성 미만도 표시", value=False)
    show_event = st.checkbox("현재 이벤트/할인 설정 반영", value=False)

    rows = []
    for s, p in PROB_TABLE.items():
        if not show_all and s < 15: continue
        if s >= max_s: continue
        ep = get_prob(s, cfg) if show_event else p
        base_cost = calc_cost(item_level, s)
        applied_cost = get_cost(s, cfg) if show_event else base_cost
        row = {
            '성수': f"{s}⭐ → {s+1}⭐",
            '성공': f"{ep[0]:.2f}%",
            '유지': f"{ep[1]:.2f}%",
            '실패(유지)': f"{ep[2]:.2f}%",
            '파괴': f"{ep[3]:.2f}%",
            '1회 비용': f"{base_cost:,}",
        }
        if show_event:
            row['적용 비용'] = f"{applied_cost:,}"
        rows.append(row)

    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True, height=500)
    st.caption("※ 메이플스토리 공식 가이드/업데이트 공지 기준 · 패치에 따라 변경될 수 있습니다")

st.divider()
st.markdown(
    """
<section class="sf-guide">
  <p class="sf-guide-title">시뮬레이터 사용법</p>
  <div class="sf-guide-grid">
    <div class="sf-guide-card">
      <strong>1. 장비 레벨</strong>
      <p>강화하려는 장비의 착용 레벨입니다. 예를 들어 카루타 장비는 보통 150, 앱솔랩스는 160, 아케인셰이드는 200을 고르면 됩니다. 장비 레벨에 따라 가능한 최대 스타포스와 1회 강화 비용이 달라집니다.</p>
    </div>
    <div class="sf-guide-card">
      <strong>2. 현재 성수와 목표 성수</strong>
      <p>현재 성수는 지금 장비에 붙어 있는 별 개수, 목표 성수는 도착하고 싶은 별 개수입니다. 처음 써본다면 10성에서 15성, 15성에서 17성처럼 짧은 구간부터 보는 게 이해하기 쉽습니다.</p>
    </div>
    <div class="sf-guide-card">
      <strong>3. 파괴방지</strong>
      <p>파괴가 가능한 구간에서 장비가 터지는 일을 막는 설정입니다. 대신 해당 성수의 강화 비용이 2배로 계산됩니다. 비싼 장비를 15성, 16성, 17성 근처에서 올릴 때 켜는 상황을 가정하면 됩니다.</p>
    </div>
    <div class="sf-guide-card">
      <strong>4. 흔적 복구</strong>
      <p>장비가 파괴됐을 때 같은 장비를 다시 구해 복구하는 상황을 비용에 넣는 옵션입니다. 입력한 장비 가격의 일부를 복구 비용처럼 더합니다. 장비 가격을 0으로 두면 복구 횟수만 집계됩니다.</p>
    </div>
    <div class="sf-guide-card">
      <strong>5. 이벤트와 할인</strong>
      <p>샤타포스 30% 할인, 5/10/15성 100%, 파괴 확률 감소 같은 이벤트를 켜고 끌 수 있습니다. 지금 게임에서 실제로 진행 중인 이벤트만 켜야 현실과 비슷한 결과가 나옵니다.</p>
    </div>
    <div class="sf-guide-card">
      <strong>6. 어떤 탭을 보면 되나</strong>
      <p>단일 시뮬은 한 번 강화했을 때의 흐름을 보여줍니다. 통계 분석은 여러 번 반복해서 평균, 최악에 가까운 비용, 파괴 횟수를 봅니다. 실제 예산을 잡을 때는 통계 분석의 75%~95% 구간을 같이 보는 편이 좋습니다.</p>
    </div>
    <div class="sf-guide-card">
      <strong>7. 기댓값과 실제 결과 차이</strong>
      <p>기댓값은 확률상 평균에 가까운 계산입니다. 하지만 스타포스는 운이 크게 흔들리기 때문에 실제 한 번의 결과는 평균보다 훨씬 싸거나 비쌀 수 있습니다. 그래서 기댓값 표보다 통계 분석의 분포가 뉴비에게 더 직관적입니다.</p>
    </div>
    <div class="sf-guide-card">
      <strong>8. 추천 첫 사용법</strong>
      <p>장비 레벨을 고르고, 현재 10성 목표 15성으로 맞춘 뒤 단일 시뮬을 한 번 눌러보세요. 그다음 목표를 17성으로 바꾸고 통계 분석을 1,000회로 돌리면 강화 비용이 왜 넉넉히 필요하다는 말이 나오는지 감이 옵니다.</p>
    </div>
  </div>
</section>
""",
    unsafe_allow_html=True,
)

st.divider()
st.markdown("""<div style="text-align:center; color:#4b5563; font-size:0.78rem; padding: 0.5rem 0 1rem;">
    스타포스 시뮬레이터 · 공식 가이드/업데이트 확률표 기반<br>
    메소 비용과 기댓값은 앱 내부 계산식 기반 추정치이며 실제 게임 결과와 다를 수 있습니다.
</div>""", unsafe_allow_html=True)
