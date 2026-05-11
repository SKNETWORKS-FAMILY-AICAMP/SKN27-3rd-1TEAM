from __future__ import annotations

import streamlit as st

from app.common.maple_paths import ensure_app_import_paths
from app.common.maple_stub_page import render_stub_body

ensure_app_import_paths()

st.set_page_config(
    page_title="Party",
    page_icon="🐧",
    layout="wide",
    initial_sidebar_state="collapsed",
)

render_stub_body(
    title="Party",
    body="상단 메뉴에서 다른 탭이나 Maple Guide 로 채팅 홈으로 이동할 수 있습니다.",
    active_menu_key="party",
)
