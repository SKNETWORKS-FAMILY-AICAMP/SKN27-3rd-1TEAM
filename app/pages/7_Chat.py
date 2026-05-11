from __future__ import annotations

import streamlit as st

from app.common.maple_paths import ensure_app_import_paths

ensure_app_import_paths()

from app.common.chat_render import (  # noqa: E402
    render_chat_page,
    render_style,
    render_top_navigation,
)
from app.maple_chat import (  # noqa: E402
    PAGE_CONFIG,
    handle_user_input,
    init_session_state,
    process_pending_response,
)


st.set_page_config(**PAGE_CONFIG)

init_session_state()
st.session_state.active_page = "chat"

render_style()
render_chat_page()
render_top_navigation(active_menu_key="chat")
handle_user_input()
process_pending_response()
