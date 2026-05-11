from __future__ import annotations

import streamlit as st

from app.common.maple_paths import ensure_app_import_paths

ensure_app_import_paths()

from app.common.chat_render import (  # noqa: E402
    render_chat_page,
    render_style,
    render_top_navigation,
)
from app.common.bgm import render_bgm_sidebar  # noqa: E402
from app.maple_chat import (  # noqa: E402
    PAGE_CONFIG,
    handle_user_input,
    init_session_state,
    load_chat_session,
    process_pending_response,
)


def render_chat_sidebar() -> None:
    with st.sidebar:
        render_bgm_sidebar()
        st.divider()
        st.markdown("### Chat list")
        sessions = st.session_state.get("chat_sessions", [])
        if not sessions:
            st.caption("No chats yet.")
            return

        current_chat_id = st.session_state.get("current_chat_id")
        for session in sessions:
            label = session.get("title") or "New chat"
            button_type = "primary" if session["id"] == current_chat_id else "secondary"
            if st.button(
                label,
                key=f"chat_session_{session['id']}",
                type=button_type,
                use_container_width=True,
            ):
                load_chat_session(session["id"])
                st.rerun()


st.set_page_config(**{**PAGE_CONFIG, "initial_sidebar_state": "expanded"})

init_session_state()
st.session_state.active_page = "chat"
if not st.session_state.get("current_chat_id") and st.session_state.chat_sessions:
    load_chat_session(st.session_state.chat_sessions[0]["id"])

render_style()
render_chat_sidebar()
handle_user_input()
render_chat_page()
render_top_navigation(active_menu_key="chat")
process_pending_response()
