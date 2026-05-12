"""보조 페이지: 사이드바에서 선택하거나 ``/Lounge`` 로 진입."""

from __future__ import annotations

import streamlit as st

from app.common.maple_paths import ensure_app_import_paths
from app.common.maple_stub_page import render_stub_body

ensure_app_import_paths()

st.set_page_config(
    page_title="Maple Lounge",
    page_icon="🍁",
    layout="wide",
    initial_sidebar_state="collapsed",
)

render_stub_body(
    title="라운지",
    body="상단 Maple Guide·메뉴로 채팅 및 다른 탭으로 이동할 수 있습니다.",
)
