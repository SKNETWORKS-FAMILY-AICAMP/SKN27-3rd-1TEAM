"""기능 미구현 페이지(스텁)를 동일한 룩앤필로 렌더링해 주는 헬퍼."""

from __future__ import annotations

from html import escape

import streamlit as st

from app.common.bgm import render_bgm_control_button, render_page_bgm
from app.common.chat_render import render_style, render_top_navigation


# 모든 스텁 페이지에 공통으로 적용하는 Streamlit 페이지 설정
# - layout: 와이드(좌우 여백 최소화)
# - initial_sidebar_state: 사이드바를 접은 상태로 시작
STUB_PAGE_CONFIG = {
    "layout": "wide",
    "initial_sidebar_state": "collapsed",
}


def render_stub_page(
    *,
    page_title: str,
    page_icon: str,
    title: str,
    body: str,
    active_menu_key: str | None = None,
    bgm_page_key: str | None = None,
) -> None:
    """간단한 안내문만 표시하는 자리표시(스텁) 페이지를 렌더링.

    Args:
        page_title: 브라우저 탭 제목.
        page_icon: 파비콘으로 쓸 이모지/문자.
        title: 페이지 상단에 크게 표시할 제목.
        body: 본문 안내 문구(개행은 ``<br>`` 로 변환).
        active_menu_key: 상단 네비게이션에서 현재 활성화할 메뉴 키.
        bgm_page_key: 페이지별 BGM 식별 키. 없으면 ``active_menu_key`` 를 재사용.
    """
    # 1) Streamlit 페이지 메타 설정
    st.set_page_config(
        page_title=page_title,
        page_icon=page_icon,
        **STUB_PAGE_CONFIG,
    )
    # 2) 전역 CSS 주입
    render_style()
    # 3) 페이지별 배경음악 재생(있을 경우)
    render_page_bgm(bgm_page_key or active_menu_key)
    # 4) 상단 네비게이션 바 렌더링
    render_top_navigation(active_menu_key=active_menu_key)
    # 5) BGM 음소거/재생 토글 버튼
    render_bgm_control_button()

    # XSS 방지를 위해 HTML 이스케이프 처리
    # body 의 줄바꿈은 HTML 줄바꿈으로 치환
    t = escape(title)
    b = escape(body).replace("\n", "<br>")

    # 본문 영역: 가운데 정렬 카드 형태로 제목과 안내문 표시
    st.markdown(
        f"""
<div class="maple-sub-page-marker"></div>
<div style="max-width:720px;margin:6.5rem auto 2rem;padding:0 1.25rem;color:#e8e3e7;">
<h2 style="margin-bottom:0.5rem;">{t}</h2>
<p style="color:#a09ca8;line-height:1.6;">{b}</p>
</div>
""",
        unsafe_allow_html=True,
    )
