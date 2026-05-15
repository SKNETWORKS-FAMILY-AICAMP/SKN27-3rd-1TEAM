"""
메이플스토리 챗봇 Streamlit 앱의 채팅 UI 렌더링 모듈입니다.

이 모듈은 다음 화면 구성 요소를 그려냅니다.
- 상단 고정 내비게이션(홈/채팅/스타포스/게임)과 홈 배지/로고
- 홈 화면의 빠른 질문 프롬프트 칩과 입력창
- 채팅 페이지의 메시지 말풍선, 아바타, 배경/오버레이 이미지
- 메시지 자동 스크롤과 포털(둥근) 캔버스 애니메이션 스크립트

순수 렌더링/이벤트 큐 처리만 담당하며, 실제 답변 생성·저장 로직은
`app.maple_chat`(start_new_chat, save_current_chat) 쪽에 위임합니다.
"""

from __future__ import annotations

from html import escape
import json

import streamlit as st
import streamlit.components.v1 as components

# 채팅 스타일 자원: 아바타/배경 이미지 경로와 data URI 변환 헬퍼.
from app.common.chat_style import (
    ASSISTANT_AVATAR_PATH,
    CHAT_BACKGROUND_PATH,
    CHAT_BACKGROUND_OVERLAY_PATH,
    USER_AVATAR_PATH,
    image_to_data_uri,
    render_style,
)
# 어시스턴트 답변을 안전한 HTML로 변환하기 위한 마크다운 렌더러.
from app.common.markdown_render import markdown_to_html


# === 내비게이션/프롬프트 상수 ===

# 상단 내비게이션 항목입니다.
# 튜플 형식: 내부 키, 화면에 보이는 라벨, Streamlit 페이지 경로.
MENU_ITEMS = (
    ("home", "Home", "maple_chat.py"),
    ("chat", "Chat", "pages/7_Chat.py"),
    ("starforce", "Starforce", "pages/9_starforce_simulator.py"),
    ("game", "Game", "pages/8_game.py"),
)

# 홈 화면 프롬프트 칩입니다.
# 튜플 형식: 위젯 키, 버튼 라벨, 채팅에 넣을 프롬프트 문구.
PROMPT_CHIPS = (
    ("chip_ranking", "랭킹 TOP 100", "전체 랭킹 100위까지 보여줘."),
    ("chip_weekly_event", "이번주 이벤트", "이번주 이벤트 내용 알려줘."),
    ("chip_cash_update", "캐시샵 업데이트", "캐시샵 업데이트 내용 알려줘."),
)
# 채팅 말풍선으로 한 번에 그릴 최근 메시지 개수 상한입니다(오래된 메시지는 잘라냅니다).
VISIBLE_MESSAGE_LIMIT = 20


# === 프롬프트 큐잉 헬퍼 ===


def _queue_prompt(prompt: str) -> None:
    """홈 프롬프트 칩으로 채팅을 시작하거나 이어간 뒤 화면을 새로고침합니다."""
    # 채팅 페이지 밖에서 누르면 새 대화를 만들고 채팅 화면으로 이동합니다.
    if st.session_state.get("active_page") != "chat":
        from app.maple_chat import start_new_chat

        start_new_chat(prompt)
        st.switch_page("pages/7_Chat.py")
        return

    from app.maple_chat import save_current_chat, start_new_chat

    # 채팅 페이지에서는 첫 대화를 만들거나 현재 대화에 프롬프트를 추가하고
    # 답변 생성을 기다리는 입력으로 표시합니다.
    if not st.session_state.get("current_chat_id"):
        start_new_chat(prompt)
    elif st.session_state.get("current_chat_id"):
        st.session_state.messages.append({"role": "user", "content": prompt})
        st.session_state.pending_user_input = prompt
        save_current_chat()

    # session_state 변경 사항이 바로 반영되도록 Streamlit을 다시 실행합니다.
    st.rerun()


def _submit_home_prompt() -> None:
    """홈 입력창에서 Enter로 제출된 텍스트를 큐에 옮겨 담는 콜백입니다."""
    # 입력값을 정리한 뒤 별도 session_state 키에 보관해 다음 rerun에서 처리합니다.
    prompt = st.session_state.get("home_prompt_input", "").strip()
    if prompt:
        st.session_state.home_prompt_to_queue = prompt
    # 위젯에 남은 텍스트는 비워두어 동일 입력의 중복 제출을 막습니다.
    st.session_state.home_prompt_input = ""


# === 상단 내비게이션 / 홈 영역 ===


def render_top_navigation(active_menu_key: str | None = "chat") -> None:
    """고정 상단 내비게이션과 홈 배지를 렌더링합니다."""
    # 고정 메뉴 배경입니다. 크기와 색상은 CSS에서 조정합니다.
    st.markdown('<div class="maple-nav-bg"></div>', unsafe_allow_html=True)

    # 좌상단의 작은 홈 배지 버튼입니다.
    with st.container(key="maple-home-badge"):
        if st.button("Home", key="home_badge_button", type="tertiary", use_container_width=True):
            st.switch_page("maple_chat.py")

    # 큰 홈 로고 이미지입니다. 채팅/서브 페이지에서는 CSS로 숨깁니다.
    with st.container(key="maple-brand-bar"):
        st.markdown('<div class="maple-brand-logo" aria-label="Maple AI"></div>', unsafe_allow_html=True)

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
                    if st.session_state.get("active_page") != "chat":
                        st.session_state.scroll_chat_top_once = True
                        if key == "chip_cash_update":
                            st.session_state.cash_update_latest_only_once = True
                    _queue_prompt(prompt)


def render_messages() -> None:
    """홈 레이아웃 기준 영역과 프롬프트 칩을 렌더링합니다."""
    # 숨겨진 제목과 spacer가 고정 입력창 주변의 레이아웃 공간을 잡아줍니다.
    # aria-hidden h1과 maple-input-space는 시각적으로는 빈 공간이지만 CSS가
    # 이 요소들을 기준으로 hero 섹션 높이와 입력창 위치를 잡습니다.
    st.markdown(
        """
<section class="maple-hero">
    <h1 class="maple-title" aria-hidden="true"></h1>
    <div class="maple-input-space"></div>
</section>
""",
        unsafe_allow_html=True,
    )

    # 홈 입력창: Enter 키 입력 시 _submit_home_prompt 콜백이 호출됩니다.
    with st.container(key="maple-home-input"):
        st.text_input(
            "질문 입력",
            key="home_prompt_input",
            placeholder="궁금한 메이플 정보를 물어보세요",
            label_visibility="collapsed",
            on_change=_submit_home_prompt,
        )
        # 이전 rerun에서 콜백이 남겨 둔 프롬프트가 있으면 꺼내 채팅 큐로 보냅니다.
        prompt = st.session_state.pop("home_prompt_to_queue", None)
        if prompt:
            _queue_prompt(prompt)

    # 프롬프트 칩은 입력창 근처에 배치되도록 hero 뒤에 렌더링합니다.
    render_prompt_buttons()


# === 채팅 페이지(말풍선/스크롤/포털 효과) ===


def render_chat_page() -> None:
    """채팅 캔버스, 아바타, 메시지 말풍선을 렌더링합니다."""
    # messages[0]은 시스템 프롬프트라 화면에는 인덱스 1부터 노출합니다.
    messages = st.session_state.get("messages", [])
    visible_messages = messages[1:]
    # 칩으로 새 대화를 시작한 직후에는 채팅창을 상단으로 한 번 스크롤하라는 플래그.
    scroll_top_requested = bool(st.session_state.get("scroll_chat_top_once", False))
    # 답변 대기 중일 때(pending_user_input)는 자동 상단 스크롤을 미뤄, 답변 도착 후 처리합니다.
    scroll_top_once = scroll_top_requested and not st.session_state.get("pending_user_input")
    if scroll_top_once:
        st.session_state.pop("scroll_chat_top_once", None)

    # 이미지 자원을 data URI로 인라인 임베드해 외부 요청을 줄이고 깜빡임을 방지합니다.
    assistant_avatar = image_to_data_uri(ASSISTANT_AVATAR_PATH)
    user_avatar = image_to_data_uri(USER_AVATAR_PATH)
    chat_background = image_to_data_uri(CHAT_BACKGROUND_PATH)
    chat_overlay = image_to_data_uri(CHAT_BACKGROUND_OVERLAY_PATH)

    html_messages = []
    # 메모리/렌더 비용 절감을 위해 최근 VISIBLE_MESSAGE_LIMIT개만 그립니다.
    for message in visible_messages[-VISIBLE_MESSAGE_LIMIT:]:
        raw_role = str(message.get("role", "assistant"))
        # 알 수 없는 role은 모두 assistant로 취급해 화면이 깨지지 않게 합니다.
        role = "user" if raw_role == "user" else "assistant"
        raw_content = str(message.get("content", ""))
        content = markdown_to_html(raw_content)
        if role == "user":
            # 사용자 입력은 escape 후 줄바꿈만 <br>로 치환(XSS 방지).
            content = escape(raw_content).replace("\n", "<br>")
        avatar = user_avatar if role == "user" else assistant_avatar
        html_messages.append(
            f'<div class="maple-chat-row {role}">'
            f'<img class="maple-chat-avatar" src="{avatar}" alt="">'
            f'<div class="maple-chat-bubble {role}">{content}</div>'
            f"</div>"
        )

    # 답변 생성 중이면 어시스턴트 자리에 로딩 스피너 말풍선을 임시로 끼워 넣습니다.
    if st.session_state.get("pending_user_input"):
        html_messages.append(
            '<div class="maple-chat-row assistant maple-chat-thinking-row">'
            f'<img class="maple-chat-avatar" src="{assistant_avatar}" alt="">'
            '<div class="maple-chat-bubble assistant maple-chat-thinking">'
            '<span class="maple-thinking-spinner"></span>'
            '<span>답변 생성 중입니다...</span>'
            "</div>"
            "</div>"
        )

    thread_html = ""
    if html_messages:
        # 마지막 anchor는 JS에서 scrollIntoView 대상으로 사용됩니다.
        thread_html = "".join(html_messages) + '<div class="maple-chat-scroll-anchor"></div>'

    # 채팅 페이지 컨테이너: 포털 캔버스(배경 왜곡 효과)와 오버레이 PNG, 그리고 말풍선 thread를 함께 배치합니다.
    # page-marker는 CSS가 채팅 페이지인지 식별하는 데 쓰는 빈 표식입니다.
    st.markdown(
        f"""
<div class="maple-chat-page-marker"></div>
<section class="maple-chat-page">
    <canvas class="maple-portal-canvas" aria-hidden="true"></canvas>
    <img class="maple-chat-overlay" src="{chat_overlay}" alt="">
    <div class="maple-chat-thread">{thread_html}</div>
</section>
""",
        unsafe_allow_html=True,
    )

    # --- 스크롤 동기화 스크립트 ---
    # 새 사용자 메시지가 추가됐을 때만 하단으로 자동 스크롤하기 위해
    # 사용자 메시지 누적 개수를 sessionStorage에 비교용으로 저장합니다.
    user_message_count = sum(1 for message in visible_messages if message.get("role") == "user")
    components.html(
        f"""
<script>
(() => {{
  const userMessageCount = {user_message_count};
  const suppressBottomScroll = {json.dumps(scroll_top_requested)};
  const scrollTopOnce = {json.dumps(scroll_top_once)};
  const storageKey = "mapleChatLastUserMessageCount";
  const getThread = () => {{
    try {{
      return window.parent.document.querySelector(".maple-chat-thread");
    }} catch {{
      return null;
    }}
  }};

  const scrollThreadToBottom = () => {{
    const thread = getThread();
    if (!thread) return false;
    thread.scrollTop = thread.scrollHeight;
    const anchor = thread.querySelector(".maple-chat-scroll-anchor");
    if (anchor) {{
      anchor.scrollIntoView({{ block: "end" }});
    }}
    return true;
  }};

  const scrollThreadToTop = () => {{
    const thread = getThread();
    if (!thread) return false;
    thread.scrollTop = 0;
    window.parent.scrollTo(0, 0);
    return true;
  }};

  const previousCount = Number(window.parent.sessionStorage.getItem(storageKey) || "0");
  window.parent.sessionStorage.setItem(storageKey, String(userMessageCount));
  if (scrollTopOnce) {{
    let attempts = 0;
    const timer = window.setInterval(() => {{
      attempts += 1;
      const didScroll = scrollThreadToTop();
      if (didScroll || attempts >= 20) {{
        window.clearInterval(timer);
      }}
    }}, 50);
    return;
  }}
  if (!suppressBottomScroll && userMessageCount > previousCount) {{
    let attempts = 0;
    const timer = window.setInterval(() => {{
      attempts += 1;
      const didScroll = scrollThreadToBottom();
      if (didScroll || attempts >= 20) {{
        window.clearInterval(timer);
      }}
    }}, 50);
  }}
}})();
</script>
""",
        height=1,
    )

    # --- 포털 배경 애니메이션 스크립트 ---
    # 채팅 페이지의 둥근 캔버스 안에 배경 이미지를 잘라 넣고 가로 라인을 sin파로
    # 흔들어 "포털이 일렁이는" 듯한 효과를 매 프레임 그립니다.
    portal_script = """
<script>
(() => {
  const parentWindow = window.parent;
  const parentDocument = parentWindow.document;
  if (parentWindow.__maplePortalFrame) {
    parentWindow.cancelAnimationFrame(parentWindow.__maplePortalFrame);
    parentWindow.__maplePortalFrame = null;
  }

  const canvas = parentDocument.querySelector(".maple-portal-canvas");
  if (!canvas) return;

  const ctx = canvas.getContext("2d");
  const img = new Image();
  img.src = __CHAT_BACKGROUND_SRC__;

  const draw = (time) => {
    const rect = canvas.getBoundingClientRect();
    if (!rect.width || !rect.height || !img.naturalWidth || !img.naturalHeight) {
      parentWindow.__maplePortalFrame = parentWindow.requestAnimationFrame(draw);
      return;
    }

    const dpr = Math.min(parentWindow.devicePixelRatio || 1, 2);
    const width = Math.max(1, Math.round(rect.width * dpr));
    const height = Math.max(1, Math.round(rect.height * dpr));
    if (canvas.width !== width || canvas.height !== height) {
      canvas.width = width;
      canvas.height = height;
    }

    ctx.clearRect(0, 0, width, height);
    ctx.save();
    ctx.scale(dpr, dpr);
    ctx.beginPath();
    ctx.ellipse(rect.width * 0.5, rect.height * 0.51, rect.width * 0.39, rect.height * 0.48, 0, 0, Math.PI * 2);
    ctx.clip();

    const viewportW = parentWindow.innerWidth;
    const viewportH = parentWindow.innerHeight;
    const bgScale = Math.max(viewportW / img.naturalWidth, viewportH / img.naturalHeight);
    const bgW = img.naturalWidth * bgScale;
    const bgH = img.naturalHeight * bgScale;
    const bgLeft = (viewportW - bgW) / 2;
    const bgTop = (viewportH - bgH) / 2 - 16;

    const sourceX = (rect.left - bgLeft) / bgScale;
    const sourceY = (rect.top - bgTop) / bgScale;
    const sourceW = rect.width / bgScale;
    const sourceH = rect.height / bgScale;
    const lines = Math.ceil(rect.height);

    for (let y = 0; y < lines; y += 1) {
      const ratio = y / Math.max(1, rect.height);
      const sourceLineY = sourceY + ratio * sourceH;
      const wave =
        Math.sin(y * 0.13 + time * 0.0048) * 2.2 +
        Math.sin(y * 0.31 + time * 0.0028) * 0.9;
      const pulse = Math.sin(time * 0.002 + ratio * 6.2) * 0.45;
      ctx.drawImage(
        img,
        sourceX,
        sourceLineY,
        sourceW,
        sourceH / Math.max(1, rect.height) + 0.7 / bgScale,
        wave + pulse,
        y,
        rect.width,
        1.7
      );
    }

    ctx.restore();
    parentWindow.__maplePortalFrame = parentWindow.requestAnimationFrame(draw);
  };

  img.onload = () => {
    parentWindow.__maplePortalFrame = parentWindow.requestAnimationFrame(draw);
  };
  if (img.complete) {
    parentWindow.__maplePortalFrame = parentWindow.requestAnimationFrame(draw);
  }
})();
</script>
""".replace("__CHAT_BACKGROUND_SRC__", json.dumps(chat_background))
    components.html(portal_script, height=1, scrolling=False)
