from __future__ import annotations

from html import escape

import streamlit as st

from app.common.bgm import render_bgm_control_button, render_page_bgm
from app.common.chat_render import render_style, render_top_navigation


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
    st.set_page_config(
        page_title=page_title,
        page_icon=page_icon,
        **STUB_PAGE_CONFIG,
    )
    render_style()
    render_page_bgm(bgm_page_key or active_menu_key)
    render_top_navigation(active_menu_key=active_menu_key)
    render_bgm_control_button()
    t = escape(title)
    b = escape(body).replace("\n", "<br>")
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
