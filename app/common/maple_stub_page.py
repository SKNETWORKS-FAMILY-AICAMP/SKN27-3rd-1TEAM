from __future__ import annotations

from html import escape

import streamlit as st

from app.common.bgm import render_global_bgm
from app.common.chat_render import render_style, render_top_navigation


def render_stub_body(
    *, title: str, body: str, active_menu_key: str | None = None
) -> None:
    render_style()
    render_global_bgm()
    render_top_navigation(active_menu_key=active_menu_key)
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
