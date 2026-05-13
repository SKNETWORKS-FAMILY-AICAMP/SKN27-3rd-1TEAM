from __future__ import annotations

import streamlit as st

from app.common.maple_paths import ensure_app_import_paths

ensure_app_import_paths()

from app.common.chat_render import (  # noqa: E402
    render_chat_page,
    render_style,
    render_top_navigation,
)
from app.common.bgm import render_bgm_control_button, render_page_bgm  # noqa: E402
from app.maple_chat import (  # noqa: E402
    PAGE_CONFIG,
    handle_user_input,
    init_session_state,
    load_chat_session,
    process_pending_response,
)

st.set_page_config(**{**PAGE_CONFIG, "initial_sidebar_state": "collapsed"})

init_session_state()
st.session_state.active_page = "chat"
if not st.session_state.get("current_chat_id") and st.session_state.chat_sessions:
    load_chat_session(st.session_state.chat_sessions[0]["id"])

render_style()
render_page_bgm("chat")
handle_user_input()
process_pending_response(rerun=False)
render_chat_page()
render_top_navigation(active_menu_key="chat")
render_bgm_control_button()
