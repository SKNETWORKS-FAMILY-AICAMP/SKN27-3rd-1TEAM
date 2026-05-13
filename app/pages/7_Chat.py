from __future__ import annotations

import streamlit as st

from app.common.maple_paths import ensure_app_import_paths

ensure_app_import_paths()

from app.maple_chat import (  # noqa: E402
    PAGE_CONFIG,
    render_chat_app,
)

st.set_page_config(**{**PAGE_CONFIG, "initial_sidebar_state": "collapsed"})
render_chat_app()
