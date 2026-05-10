from __future__ import annotations

from html import escape

import streamlit as st

from app.common.chat_style import (
    ASSISTANT_AVATAR_PATH,
    INPUT_PET_PATH,
    USER_AVATAR_PATH,
    get_maple_chat_css,
    image_to_data_uri,
)


MENU_ITEMS = (
    ("assistant", ASSISTANT_AVATAR_PATH, "Chat"),
    ("friend", None, "Friends"),
    ("guild", None, "Guild"),
    ("party", None, "Party"),
    ("setting", USER_AVATAR_PATH, "Settings"),
)


def render_style() -> None:
    st.markdown(get_maple_chat_css(), unsafe_allow_html=True)


def render_top_navigation() -> None:
    user_icon = image_to_data_uri(USER_AVATAR_PATH)
    input_pet = image_to_data_uri(INPUT_PET_PATH)
    menu_parts = []
    for key, icon_path, label in MENU_ITEMS:
        icon = image_to_data_uri(icon_path) if icon_path else ""
        fallback_icon = {
            "friend": "🌱",
            "guild": "🐱",
            "party": "🐧",
        }.get(key, "")
        icon_html = (
            f'<img class="maple-menu-icon" src="{icon}" alt="">'
            if icon
            else f'<span class="maple-menu-emoji">{fallback_icon}</span>'
        )
        active = " is-active" if key == "assistant" else ""
        menu_parts.append(
            f'<span class="maple-menu-item{active}">'
            f"{icon_html}"
            f"<span>{label}</span>"
            f"</span>"
        )
    menu_html = "".join(menu_parts)
    st.markdown(
        (
            f'<div class="maple-home">'
            f'<img class="maple-home-icon" src="{user_icon}" alt="">'
            f"<span>홈</span>"
            f"</div>"
            f'<div class="maple-topbar">'
            f'<nav class="maple-menu">{menu_html}</nav>'
            f"</div>"
            f'<div class="maple-actions">'
            f'<span class="maple-action-icon">♧</span>'
            f'<span class="maple-action-icon">⚙</span>'
            f"</div>"
            f'<div class="maple-input-pet">'
            f'<img src="{input_pet}" alt="">'
            f"</div>"
        ),
        unsafe_allow_html=True,
    )


def render_messages() -> None:
    assistant_icon = image_to_data_uri(ASSISTANT_AVATAR_PATH)
    user_icon = image_to_data_uri(USER_AVATAR_PATH)
    message_html = [
        '<div class="maple-room-notice">⌁ Welcome to the <b>Henesys</b> region chat. Keep it friendly!</div>'
    ]

    for index, message in enumerate(st.session_state.messages):
        role = message["role"]
        content = escape(message["content"]).replace("\n", "<br>")

        if role == "user":
            message_html.append(
                f'<div class="maple-message-row is-user">'
                f'<div class="maple-message-meta">방금</div>'
                f'<div class="maple-message-bubble">{content}</div>'
                f'<img class="maple-message-avatar" src="{user_icon}" alt="">'
                f"</div>"
            )
            continue

        sender = "Maple Guide" if index == 0 else "SlimeKing"
        time_text = "온라인" if index == 0 else "방금"
        message_html.append(
            f'<div class="maple-message-row is-assistant">'
            f'<img class="maple-message-avatar" src="{assistant_icon}" alt="">'
            f'<div class="maple-message-body">'
            f'<div class="maple-message-name">{sender} <span>{time_text}</span></div>'
            f'<div class="maple-message-bubble">{content}</div>'
            f"</div>"
            f"</div>"
        )

    st.markdown("".join(message_html), unsafe_allow_html=True)
