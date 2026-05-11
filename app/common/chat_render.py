from __future__ import annotations

from html import escape

import streamlit as st

from app.common.chat_style import (
    ASSISTANT_AVATAR_PATH,
    USER_AVATAR_PATH,
    image_to_data_uri,
    render_style,
)


MENU_ITEMS = (
    ("chat", "Chat", "pages/7_Chat.py"),
    ("models", "Models", "pages/2_Friends.py"),
    ("history", "History", "pages/3_Guild.py"),
    ("settings", "Settings", "pages/6_Settings.py"),
)

PROMPT_CHIPS = (
    ("chip_story", "✣ Tell me a story", "메이플스토리 초보 모험가를 위한 짧은 모험 이야기를 들려줘."),
    ("chip_debug", "<> Help me debug code", "지금 메이플 가이드 챗봇 코드에서 확인해야 할 디버깅 포인트를 알려줘."),
    ("chip_quantum", "◉ Explain quantum physics", "양자 물리를 메이플스토리 비유로 쉽게 설명해줘."),
)


def _queue_prompt(prompt: str) -> None:
    st.session_state.messages.append({"role": "user", "content": prompt})
    st.session_state.pending_user_input = prompt
    if st.session_state.get("active_page") != "chat":
        st.switch_page("pages/7_Chat.py")
    st.rerun()


def render_top_navigation(active_menu_key: str | None = "chat") -> None:
    st.markdown('<div class="maple-nav-bg"></div>', unsafe_allow_html=True)

    with st.container(key="maple-home-badge"):
        if st.button("Home", key="home_badge_button", type="tertiary", use_container_width=True):
            st.switch_page("maple_chat.py")

    with st.container(key="maple-brand-bar"):
        st.button("Maple AI", key="brand_home", type="tertiary", use_container_width=True)

    with st.container(key="maple-nav-bar"):
        columns = st.columns(len(MENU_ITEMS), gap="small")
        for column, (key, label, page_path) in zip(columns, MENU_ITEMS):
            with column:
                button_type = "primary" if key == active_menu_key else "tertiary"
                if st.button(
                    label,
                    key=f"nav_{key}",
                    type=button_type,
                    use_container_width=True,
                ):
                    st.switch_page(page_path)


def render_prompt_buttons() -> None:
    with st.container(key="maple-chip-row"):
        columns = st.columns(len(PROMPT_CHIPS), gap="medium")
        for column, (key, label, prompt) in zip(columns, PROMPT_CHIPS):
            with column:
                if st.button(label, key=key, type="tertiary", use_container_width=True):
                    _queue_prompt(prompt)


def render_messages() -> None:
    st.markdown(
        """
<section class="maple-hero">
    <h1 class="maple-title" aria-hidden="true"></h1>
    <div class="maple-input-space"></div>
</section>
""",
        unsafe_allow_html=True,
    )

    render_prompt_buttons()


def render_chat_page() -> None:
    messages = st.session_state.get("messages", [])
    visible_messages = messages[1:]
    assistant_avatar = image_to_data_uri(ASSISTANT_AVATAR_PATH)
    user_avatar = image_to_data_uri(USER_AVATAR_PATH)

    if visible_messages:
        html_messages = []
        for message in visible_messages[-20:]:
            raw_role = str(message.get("role", "assistant"))
            role = "user" if raw_role == "user" else "assistant"
            content = escape(str(message.get("content", ""))).replace("\n", "<br>")
            avatar = user_avatar if role == "user" else assistant_avatar
            html_messages.append(
                f'<div class="maple-chat-row {role}">'
                f'<img class="maple-chat-avatar" src="{avatar}" alt="">'
                f'<div class="maple-chat-bubble {role}">{content}</div>'
                f"</div>"
            )
        thread_html = "".join(html_messages)
    else:
        thread_html = (
            '<div class="maple-chat-empty">'
            "메이플 장비 추천, 육성 가이드, 보스 준비를 물어보세요."
            "</div>"
        )

    st.markdown(
        f"""
<div class="maple-chat-page-marker"></div>
<section class="maple-chat-page">
    <div class="maple-chat-thread">{thread_html}</div>
</section>
""",
        unsafe_allow_html=True,
    )
