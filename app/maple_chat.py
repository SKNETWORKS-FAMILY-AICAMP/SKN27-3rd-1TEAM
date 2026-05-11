from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

import streamlit as st
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
for path in (PROJECT_ROOT, SRC_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))


from app.common.chat_memory import (  # noqa: E402
    build_agent_messages,
    compact_agent_history,
)
from app.common.chat_render import (  # noqa: E402
    ASSISTANT_AVATAR_PATH,
    USER_AVATAR_PATH,
    render_messages,
    render_style,
    render_top_navigation,
)
from app.common.youtube_embed import render_youtube_embed  # noqa: E402


PAGE_CONFIG = {
    "page_title": "Maple Chat",
    "page_icon": "🍁",
    "layout": "wide",
    "initial_sidebar_state": "collapsed",
}

# 기본 BGM 영상 ID. ``MAPLE_YOUTUBE_BGM`` 으로 다른 id를 주거나, 빈 문자열이면 BGM 끔.
_DEFAULT_YOUTUBE_BGM = "cMTdq4VGqoI"
_env_bgm = os.environ.get("MAPLE_YOUTUBE_BGM")
if _env_bgm is None:
    YOUTUBE_BGM_VIDEO_ID = _DEFAULT_YOUTUBE_BGM
else:
    YOUTUBE_BGM_VIDEO_ID = _env_bgm.strip() or None

WELCOME_MESSAGE = {
    "role": "assistant",
    "content": (
        "안녕하세요! 캐릭터 성장, 보스 도전, 장비 세팅, 이벤트 보상까지 "
        "궁금한 걸 편하게 물어봐 주세요."
    ),
}

ANSWER_KEYS = ("final_answer", "answer", "analysis", "draft_answer")


def init_session_state() -> None:
    if "messages" not in st.session_state:
        st.session_state.messages = [WELCOME_MESSAGE.copy()]
    if "agent_messages" not in st.session_state:
        st.session_state.agent_messages = []
    if "agent_memory_summary" not in st.session_state:
        st.session_state.agent_memory_summary = ""
    if "agent_errors" not in st.session_state:
        st.session_state.agent_errors = []
    if "pending_user_input" not in st.session_state:
        st.session_state.pending_user_input = None


@st.cache_resource(show_spinner=False)
def load_graph() -> Any:
    from src.agents.graph import maple_chat_graph

    return maple_chat_graph()


def to_langchain_messages(messages: list[dict[str, str]]) -> list[BaseMessage]:
    converted = []
    for message in messages:
        role = message["role"]
        content = message["content"]

        if role == "system":
            converted.append(SystemMessage(content=content))
        elif role == "user":
            converted.append(HumanMessage(content=content))
        elif role == "assistant":
            converted.append(AIMessage(content=content))
    return converted


def extract_answer(result: Any) -> str:
    if isinstance(result, dict):
        for key in ANSWER_KEYS:
            value = result.get(key)
            if value:
                return str(value)

        messages = result.get("messages")
        if messages:
            last_message = messages[-1]
            return str(getattr(last_message, "content", last_message))

    if result:
        return str(result)

    return "답변을 생성하지 못했습니다. 잠시 후 다시 시도해 주세요."


def fallback_answer(user_input: str, error: Exception) -> str:
    st.session_state.agent_errors.append(str(error))
    return (
        "현재 에이전트 그래프를 실행하지 못했습니다.\n\n"
        f"- 입력한 질문: {user_input}\n"
        "- 확인할 것: 필요한 에이전트 모듈, API 키, DB 연결 설정이 준비되어 있는지 확인해 주세요."
    )


def get_assistant_response(user_input: str) -> str:
    try:
        graph = load_graph()
        compacted_messages, memory_summary = compact_agent_history(
            st.session_state.agent_messages,
            st.session_state.agent_memory_summary,
            st.session_state.agent_errors.append,
        )
        st.session_state.agent_messages = compacted_messages
        st.session_state.agent_memory_summary = memory_summary

        agent_messages = build_agent_messages(
            user_input,
            st.session_state.agent_messages,
            st.session_state.agent_memory_summary,
        )
        state = {
            "user_query": user_input,
            "messages": to_langchain_messages(agent_messages),
            "completed_agents": [],
            "retry_count": 0,
            "errors": [],
            "is_complete": False,
        }
        result = graph.invoke(state)
        return extract_answer(result)
    except Exception as exc:
        return fallback_answer(user_input, exc)


def reset_chat() -> None:
    st.session_state.messages = [WELCOME_MESSAGE.copy()]
    st.session_state.agent_messages = []
    st.session_state.agent_memory_summary = ""
    st.session_state.agent_errors = []


def append_agent_turn(user_input: str, answer: str) -> None:
    st.session_state.agent_messages.extend(
        [
            {"role": "user", "content": user_input},
            {"role": "assistant", "content": answer},
        ]
    )


def handle_user_input() -> None:
    user_input = st.chat_input("Type your question here...")
    if not user_input:
        return

    st.session_state.messages.append({"role": "user", "content": user_input})
    st.session_state.pending_user_input = user_input
    if st.session_state.get("active_page") != "chat":
        st.switch_page("pages/7_Chat.py")
    st.rerun()


def process_pending_response() -> None:
    user_input = st.session_state.pending_user_input
    if not user_input:
        return

    with st.spinner("답변을 준비하고 있습니다..."):
        answer = get_assistant_response(user_input)

    st.session_state.messages.append({"role": "assistant", "content": answer})
    append_agent_turn(user_input, answer)
    st.session_state.pending_user_input = None
    st.rerun()


def main() -> None:
    st.set_page_config(**PAGE_CONFIG)

    init_session_state()
    st.session_state.active_page = "home"
    if YOUTUBE_BGM_VIDEO_ID:
        with st.sidebar:
            st.caption("배경 음악 (자동 재생은 음소거로 시작합니다)")
            render_youtube_embed(
                YOUTUBE_BGM_VIDEO_ID,
                height=88,
                muted=True,
                loop=True,
                controls=False,
            )
    render_style()
    render_messages()
    render_top_navigation(active_menu_key="chat")
    handle_user_input()


if __name__ == "__main__":
    main()
