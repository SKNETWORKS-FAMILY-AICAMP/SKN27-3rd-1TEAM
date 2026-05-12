from __future__ import annotations

from html import escape

import streamlit as st

from app.common.chat_style import (
    ASSISTANT_AVATAR_PATH,
    ITEM_BOX_PATH,
    USER_AVATAR_PATH,
    image_to_data_uri,
    render_style,
)


# 상단 내비게이션 항목입니다.
# 튜플 형식: 내부 키, 화면에 보이는 라벨, Streamlit 페이지 경로.
MENU_ITEMS = (
    ("chat", "Chat", "pages/7_Chat.py"),
    ("models", "Models", "pages/2_Friends.py"),
    ("history", "History", "pages/3_Guild.py"),
    ("settings", "Settings", "pages/6_Settings.py"),
)

# 홈 화면 프롬프트 칩입니다.
# 튜플 형식: 위젯 키, 버튼 라벨, 채팅에 넣을 프롬프트 문구.
PROMPT_CHIPS = (
    ("chip_story", "✣ Tell me a story", "메이플스토리 초보 모험가를 위한 짧은 모험 이야기를 들려줘."),
    ("chip_debug", "<> Help me debug code", "지금 메이플 가이드 챗봇 코드에서 확인해야 할 디버깅 포인트를 알려줘."),
    ("chip_quantum", "◉ Explain quantum physics", "양자 물리를 메이플스토리 비유로 쉽게 설명해줘."),
)


def _queue_prompt(prompt: str) -> None:
    """홈 프롬프트 칩으로 채팅을 시작하거나 이어간 뒤 화면을 새로고침합니다."""
    # 채팅 페이지 밖에서 누르면 새 대화를 만들고 채팅 화면으로 이동합니다.
    if st.session_state.get("active_page") != "chat":
        from app.maple_chat import start_new_chat

        start_new_chat(prompt)
        st.switch_page("pages/7_Chat.py")
    else:
        from app.maple_chat import save_current_chat, start_new_chat

        # 채팅 페이지에서는 첫 대화를 만들거나 현재 대화에 프롬프트를 추가하고
        # 답변 생성을 기다리는 입력으로 표시합니다.
        if not st.session_state.get("current_chat_id"):
            start_new_chat(prompt)
        else:
            st.session_state.messages.append({"role": "user", "content": prompt})
            st.session_state.pending_user_input = prompt
            save_current_chat()

    # session_state 변경 사항이 바로 반영되도록 Streamlit을 다시 실행합니다.
    st.rerun()


def render_top_navigation(active_menu_key: str | None = "chat") -> None:
    """고정 상단 내비게이션과 홈 배지를 렌더링합니다."""
    # 고정 메뉴 배경입니다. 크기와 색상은 CSS에서 조정합니다.
    st.markdown('<div class="maple-nav-bg"></div>', unsafe_allow_html=True)

    # 좌상단의 작은 홈 배지 버튼입니다.
    with st.container(key="maple-home-badge"):
        if st.button("Home", key="home_badge_button", type="tertiary", use_container_width=True):
            st.switch_page("maple_chat.py")

    # 큰 홈 로고 버튼입니다. 채팅/서브 페이지에서는 CSS로 숨깁니다.
    with st.container(key="maple-brand-bar"):
        st.button("Maple AI", key="brand_home", type="tertiary", use_container_width=True)

    # 중앙 내비게이션 메뉴입니다. 활성 버튼은 primary 타입으로 스타일을 구분합니다.
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
    """홈 화면 프롬프트 칩 행을 렌더링합니다."""
    # 컨테이너 키는 CSS의 .st-key-maple-chip-row 선택자와 연결됩니다.
    with st.container(key="maple-chip-row"):
        columns = st.columns(len(PROMPT_CHIPS), gap="medium")
        for column, (key, label, prompt) in zip(columns, PROMPT_CHIPS):
            with column:
                if st.button(label, key=key, type="tertiary", use_container_width=True):
                    _queue_prompt(prompt)


def render_messages() -> None:
    """홈 레이아웃 기준 영역과 프롬프트 칩을 렌더링합니다."""
    # 숨겨진 제목과 spacer가 고정 입력창 주변의 레이아웃 공간을 잡아줍니다.
    st.markdown(
        """
<section class="maple-hero">
    <h1 class="maple-title" aria-hidden="true"></h1>
    <div class="maple-input-space"></div>
</section>
""",
        unsafe_allow_html=True,
    )

    # 프롬프트 칩은 입력창 근처에 배치되도록 hero 뒤에 렌더링합니다.
    render_prompt_buttons()


def render_chat_page() -> None:
    """채팅 캔버스, 아바타, 메시지 말풍선을 렌더링합니다."""
    # 첫 메시지는 숨겨진 시스템/초기 컨텍스트로 취급하므로 표시하지 않습니다.
    messages = st.session_state.get("messages", [])
    visible_messages = messages[1:]

    # 커스텀 HTML에서 바로 쓸 수 있도록 아바타 이미지를 data URI로 변환합니다.
    assistant_avatar = image_to_data_uri(ASSISTANT_AVATAR_PATH)
    user_avatar = image_to_data_uri(USER_AVATAR_PATH)
    item_box = image_to_data_uri(ITEM_BOX_PATH)

    if visible_messages:
        html_messages = []

        # 긴 대화에서도 화면과 렌더링이 무거워지지 않도록 최근 메시지만 표시합니다.
        for message in visible_messages[-20:]:
            raw_role = str(message.get("role", "assistant"))
            role = "user" if raw_role == "user" else "assistant"

            # HTML 삽입 전에 내용을 이스케이프하고 줄바꿈은 유지합니다.
            content = escape(str(message.get("content", ""))).replace("\n", "<br>")
            avatar = user_avatar if role == "user" else assistant_avatar

            # role 클래스는 CSS에서 좌우 정렬과 말풍선 색상을 결정합니다.
            html_messages.append(
                f'<div class="maple-chat-row {role}">'
                f'<img class="maple-chat-avatar" src="{avatar}" alt="">'
                f'<div class="maple-chat-bubble {role}">{content}</div>'
                f"</div>"
            )
        thread_html = "".join(html_messages)
    else:
        # 아직 표시할 대화가 없을 때 보여주는 빈 상태 문구입니다.
        thread_html = (
            '<div class="maple-chat-empty">'
            "메이플 장비 추천, 육성 가이드, 보스 준비를 물어보세요."
            "</div>"
        )

    # marker는 CSS의 :has(...)로 채팅 페이지 여부를 감지하게 해줍니다.
    # section은 고정 채팅 배경이고, 안쪽 div는 스크롤되는 메시지 영역입니다.
    st.markdown(
        f"""
<div class="maple-chat-page-marker"></div>
<section class="maple-chat-page">
    <img class="maple-chat-item-box" src="{item_box}" alt="">
    <div class="maple-chat-thread">{thread_html}</div>
</section>
""",
        unsafe_allow_html=True,
    )
