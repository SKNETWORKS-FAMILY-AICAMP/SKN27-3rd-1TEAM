import streamlit as st
import random
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from dataclasses import dataclass, field

# ═══════════════════════════════════════════════════════
# 1. 스타포스 데이터 (KMS 30성 기준)
# ═══════════════════════════════════════════════════════

def calc_cost(item_level: int, star: int) -> int:
    """KMS 공식 기반 강화 비용 계산"""
    base = round(item_level ** 3 * (star + 1) / 2500 + 10) * 1000
    return base

# 성수별 확률 테이블 [성공%, 유지%, 하락%, 파괴%]
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
    11: [45.0,  0.0, 55.0,  0.0],
    12: [40.0,  0.0, 59.4,  0.6],
    13: [35.0,  0.0, 64.1,  0.9],
    14: [30.0,  0.0, 68.6,  1.4],
    15: [30.0,  0.0, 67.9,  2.1],
    16: [30.0,  0.0, 66.4,  3.6],
    17: [30.0,  0.0, 63.7,  6.3],
    18: [30.0,  0.0, 58.1, 11.9],
    19: [30.0,  0.0, 55.6, 14.4],
    20: [30.0,  0.0, 53.0, 17.0],
    21: [30.0,  0.0, 44.0, 26.0],
    22: [3.0,   0.0, 77.6, 19.4],
    23: [2.0,   0.0, 77.6, 20.4],
    24: [1.0,   0.0, 75.6, 23.4],
    25: [1.0,   0.0, 75.6, 23.4],
    26: [0.7,   0.0, 74.4, 24.9],
    27: [0.5,   0.0, 74.0, 25.5],
    28: [0.3,   0.0, 73.6, 26.1],
    29: [0.1,   0.0, 72.9, 27.0],
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
                if current in SAFE_STARS:
                    result = 'maintain'
                    next_star = current
                    consecutive_fail += 1
                else:
                    result = 'down'
                    next_star = current - 1
                    consecutive_fail += 1
            else:
                if current in SAFE_STARS:
                    result = 'maintain'
                    next_star = current
                    consecutive_fail += 1
                elif current in cfg.safeguard:
                    result = 'safeguard'
                    next_star = current - 1
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
            '하락': f"{p[2]:.2f}%",
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

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;500;700;900&display=swap');
*, html, body { font-family: 'Noto Sans KR', sans-serif !important; }

.sf-header {
    background: linear-gradient(135deg, #0d0d1a, #1a0d2e, #0d1a2e);
    border-bottom: 2px solid #FFD70033;
    padding: 1.5rem 2rem;
    margin: -1rem -1rem 1.5rem -1rem;
}
.sf-header h1 {
    font-size: 2rem; font-weight: 900; margin: 0;
    background: linear-gradient(90deg, #FFD700, #FFA500);
    -webkit-background-clip: text; -webkit-text-fill-color: transparent;
}
.sf-header p { color: #888; font-size: 0.85rem; margin: 0.3rem 0 0 0; }

.section-label {
    font-size: 0.72rem; font-weight: 700; letter-spacing: 0.1em;
    color: #FFD700; text-transform: uppercase;
    margin: 1rem 0 0.4rem 0;
}
.metric-card {
    background: #111827; border: 1px solid #1f2937;
    border-radius: 12px; padding: 1rem 1.2rem; text-align: center;
}
.metric-card .m-label { color: #6b7280; font-size: 0.78rem; margin-bottom: 0.3rem; }
.metric-card .m-value { font-size: 1.6rem; font-weight: 900; color: #FFD700; }
.metric-card .m-sub { color: #9ca3af; font-size: 0.75rem; margin-top: 0.2rem; }
</style>
""", unsafe_allow_html=True)

st.markdown("""
<div class="sf-header">
    <h1>⭐ 스타포스 시뮬레이터</h1>
    <p>KMS 공식 확률 기반 · 30성 지원 · 파괴방지 · 흔적복구 · 이벤트/할인 반영</p>
</div>
""", unsafe_allow_html=True)

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
            paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(17,24,39,1)',
            font=dict(color='#d1d5db', family='Noto Sans KR'),
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
            paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(17,24,39,1)',
            font=dict(color='#d1d5db', family='Noto Sans KR'),
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
                'destroy': '💥 파괴', 'safeguard': '🛡 파방(하락)',
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
        st.info("👆 위 설정을 마치고 **강화 시작** 또는 **100회 평균** 버튼을 누르세요")

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
            paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(17,24,39,1)',
            font=dict(color='#d1d5db', family='Noto Sans KR'),
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
            paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(17,24,39,1)',
            font=dict(color='#d1d5db', family='Noto Sans KR'),
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
        st.info("👆 시뮬레이션 횟수를 선택하고 **분석** 버튼을 누르세요")

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
            paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(17,24,39,1)',
            font=dict(color='#d1d5db', family='Noto Sans KR'),
            xaxis=dict(gridcolor='#1f2937'),
            yaxis=dict(gridcolor='#1f2937', title='기댓값 (억 메소)'),
            coloraxis_showscale=False, height=300,
            margin=dict(l=40, r=40, t=40, b=40),
        )
        st.plotly_chart(fig5, use_container_width=True)
    else:
        st.warning("목표 성수를 현재 성수보다 높게 설정해주세요")

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
            '하락': f"{ep[2]:.2f}%",
            '파괴': f"{ep[3]:.2f}%",
            '1회 비용': f"{base_cost:,}",
        }
        if show_event:
            row['적용 비용'] = f"{applied_cost:,}"
        rows.append(row)

    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True, height=500)
    st.caption("※ KMS 공식 확률 기준 · 패치에 따라 변경될 수 있습니다")

st.divider()
st.markdown("""<div style="text-align:center; color:#4b5563; font-size:0.78rem; padding: 0.5rem 0 1rem;">
    ⭐ 스타포스 시뮬레이터 · KMS 공식 확률 기반<br>
    메수라이브 · 환산주스탯 · 메애기 참고 · 실제 게임 결과와 다를 수 있음 · 파괴 없는 강화를 빕니다 🍀
</div>""", unsafe_allow_html=True)
