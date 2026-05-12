from __future__ import annotations

import streamlit as st

from app.common.maple_paths import ensure_app_import_paths
from app.common.maple_stub_page import render_stub_body

ensure_app_import_paths()

st.set_page_config(
    page_title="Settings",
    page_icon="S",
    layout="wide",
    initial_sidebar_state="collapsed",
)

render_stub_body(
    title="Settings",
    body="Maple Guide 설정을 조정하는 페이지입니다.",
    active_menu_key="settings",
)
