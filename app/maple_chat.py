from __future__ import annotations
from dotenv import load_dotenv
load_dotenv()

import sys
import time
from copy import deepcopy
from pathlib import Path
from typing import Any

import streamlit as st
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
for path in (PROJECT_ROOT, SRC_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))


from app.common.bgm import render_bgm_control_button, render_page_bgm  # noqa: E402
from app.common.chat_memory import (  # noqa: E402
    build_agent_messages,
    compact_agent_history,
)
from app.common.chat_render import (  # noqa: E402
    render_chat_page,
    render_messages,
    render_style,
    render_top_navigation,
)


PAGE_CONFIG = {
    "page_title": "Maple Chat",
    "page_icon": "🍁",
    "layout": "wide",
    "initial_sidebar_state": "collapsed",
}

WELCOME_MESSAGE = {
    "role": "assistant",
    "content": (
        "안녕하세요! 캐릭터 성장, 보스 도전, 장비 세팅, 이벤트 보상까지 "
        "궁금한 걸 편하게 물어봐 주세요."
    ),
}

ANSWER_KEYS = ("final_answer", "answer", "analysis", "draft_answer")
RANKING_TOP100_PROMPT = "전체 랭킹 100위까지 보여줘."
WEEKLY_EVENT_PROMPT = "이번주 이벤트 내용 알려줘."
CASH_UPDATE_PROMPT = "캐시샵 업데이트 내용 알려줘."
CHAT_STATE_KEYS = (
    "messages",
    "agent_messages",
    "agent_memory_summary",
    "agent_errors",
    "pending_user_input",
)
SESSION_DEFAULTS = {
    "chat_sessions": [],
    "current_chat_id": None,
}


def new_chat_state(user_input: str | None = None) -> dict[str, Any]:
    messages = [WELCOME_MESSAGE.copy()]
    if user_input is not None:
        messages.append({"role": "user", "content": user_input})

    return {
        "messages": messages,
        "agent_messages": [],
        "agent_memory_summary": "",
        "agent_errors": [],
        "pending_user_input": user_input,
    }


def apply_chat_state(chat_state: dict[str, Any]) -> None:
    default_state = new_chat_state()
    for key in CHAT_STATE_KEYS:
        value = chat_state.get(key, default_state[key])
        st.session_state[key] = deepcopy(value)


def init_session_state() -> None:
    for key, value in new_chat_state().items():
        if key not in st.session_state:
            st.session_state[key] = deepcopy(value)

    for key, value in SESSION_DEFAULTS.items():
        if key not in st.session_state:
            st.session_state[key] = deepcopy(value)


def make_chat_title(user_input: str) -> str:
    compact = " ".join(user_input.split())
    if not compact:
        return "New chat"
    return compact[:24] + ("..." if len(compact) > 24 else "")


def save_current_chat() -> None:
    chat_id = st.session_state.get("current_chat_id")
    if not chat_id:
        return

    for session in st.session_state.chat_sessions:
        if session["id"] == chat_id:
            for key in CHAT_STATE_KEYS:
                session[key] = deepcopy(st.session_state.get(key))
            return


def load_chat_session(chat_id: str) -> None:
    save_current_chat()
    for session in st.session_state.chat_sessions:
        if session["id"] == chat_id:
            st.session_state.current_chat_id = chat_id
            apply_chat_state(session)
            return


def start_new_chat(user_input: str) -> None:
    chat_id = f"chat-{int(time.time() * 1000)}"
    session = {
        "id": chat_id,
        "title": make_chat_title(user_input),
        "created_at": time.time(),
        **new_chat_state(user_input),
    }
    st.session_state.chat_sessions.insert(0, session)
    st.session_state.current_chat_id = chat_id
    apply_chat_state(session)


@st.cache_resource(show_spinner=False)
def load_graph() -> Any:
    from src.graph import maple_chat_graph

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


def is_ranking_top100_request(user_input: str) -> bool:
    normalized = " ".join(str(user_input or "").split())
    return normalized == RANKING_TOP100_PROMPT or (
        "랭킹" in normalized
        and "100" in normalized
        and any(keyword in normalized for keyword in ("전체", "top", "TOP"))
    )


def format_ranking_top100_answer() -> str:
    from src.collectors.nexon_api import fetch_overall_ranking_top100

    rankings = fetch_overall_ranking_top100()
    if not rankings:
        return "전체 랭킹 정보를 가져오지 못했습니다. API 기준 날짜 또는 API 키를 확인해 주세요."

    lines = [
        "전체 랭킹 TOP 100입니다.",
        "",
    ]
    for index, row in enumerate(rankings, start=1):
        rank = row.get("ranking") or index
        character_name = row.get("character_name") or "-"
        world_name = row.get("world_name") or "-"
        class_name = row.get("class_name") or row.get("class") or "-"
        level = row.get("character_level") or "-"
        lines.append(f"{rank}. {character_name} / {world_name} / {class_name} / Lv.{level}")
    return "\n".join(lines)


def is_weekly_event_request(user_input: str) -> bool:
    normalized = " ".join(str(user_input or "").split())
    return normalized == WEEKLY_EVENT_PROMPT or (
        "이벤트" in normalized
        and any(keyword in normalized for keyword in ("이번주", "이번 주", "현재", "진행"))
    )


def format_weekly_event_answer() -> str:
    from src.collectors.nexon_api import fetch_current_event_notices

    events = fetch_current_event_notices(max_events=5)
    if not events:
        return "이번주 이벤트 정보를 가져오지 못했습니다. Nexon API 키와 이벤트 공지 데이터를 확인해 주세요."

    lines = ["이번주 진행 중인 메이플스토리 이벤트입니다.", ""]
    for event in events:
        title = str(event.get("title") or "제목 없음").strip()
        url = str(event.get("url") or "").strip()
        start_date = str(event.get("date_event_start") or "").strip()[:10] or "unknown"
        end_date = str(event.get("date_event_end") or "").strip()[:10] or "unknown"
        link = f"[바로가기]({url})" if url else "URL 없음"
        lines.extend(
            [
                f"## {title}",
                f"### 이벤트 기간",
                f"{start_date} ~ {end_date}",
                f"### URL",
                link,
                "",
            ]
        )
    return "\n".join(lines)


def is_cash_update_request(user_input: str) -> bool:
    normalized = " ".join(str(user_input or "").split())
    return normalized == CASH_UPDATE_PROMPT or (
        "캐시" in normalized
        and any(keyword in normalized for keyword in ("업데이트", "공지", "신규", "코디"))
    )


def format_cash_update_answer() -> str:
    from src.collectors.nexon_api import fetch_recent_update_cash_sections

    latest_only = bool(st.session_state.pop("cash_update_latest_only_once", False))
    notices = fetch_recent_update_cash_sections(max_notices=1 if latest_only else 3)
    if not notices:
        return "최근 업데이트 공지에서 캐시 관련 내용을 찾지 못했습니다. Nexon API 키와 업데이트 공지 데이터를 확인해 주세요."

    lines = ["최근 업데이트 공지의 캐시 관련 내용입니다.", ""]
    for notice in notices:
        title = str(notice.get("title") or "제목 없음").strip()
        url = str(notice.get("url") or "").strip()
        notice_date = str(notice.get("date") or "").strip()[:10] or "unknown"
        link = f"[바로가기]({url})" if url else "URL 없음"
        lines.extend(
            [
                f"## {title}",
                f"### 공지일",
                notice_date,
                f"### URL",
                link,
                f"### 캐시 관련 내용",
            ]
        )
        for section in notice.get("cash_sections", []):
            lines.append(section)
            lines.append("")
    return "\n".join(lines)


def get_assistant_response(user_input: str) -> str:
    try:
        if is_ranking_top100_request(user_input):
            return format_ranking_top100_answer()
        if is_weekly_event_request(user_input):
            return format_weekly_event_answer()
        if is_cash_update_request(user_input):
            return format_cash_update_answer()

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
            "contextualized_query": user_input,
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
    apply_chat_state(new_chat_state())


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

    if st.session_state.get("active_page") != "chat":
        start_new_chat(user_input)
        st.switch_page("pages/7_Chat.py")

    if not st.session_state.get("current_chat_id"):
        start_new_chat(user_input)
    else:
        st.session_state.messages.append({"role": "user", "content": user_input})
        st.session_state.pending_user_input = user_input
        save_current_chat()


def process_pending_response(rerun: bool = True) -> None:
    user_input = st.session_state.pending_user_input
    if not user_input:
        return

    with st.spinner("답변을 준비하고 있습니다..."):
        started_at = time.perf_counter()
        answer = get_assistant_response(user_input)
        st.session_state.last_response_seconds = round(
            time.perf_counter() - started_at,
            2,
        )

    st.session_state.messages.append({"role": "assistant", "content": answer})
    append_agent_turn(user_input, answer)
    st.session_state.pending_user_input = None
    save_current_chat()
    if rerun:
        st.rerun()


def render_home_app() -> None:
    init_session_state()
    st.session_state.active_page = "home"
    render_style()
    render_page_bgm("home")
    render_messages()
    render_top_navigation(active_menu_key="home")
    render_bgm_control_button()


def render_chat_app() -> None:
    init_session_state()
    st.session_state.active_page = "chat"
    if not st.session_state.get("current_chat_id") and st.session_state.chat_sessions:
        load_chat_session(st.session_state.chat_sessions[0]["id"])

    render_style()
    render_page_bgm("chat")
    handle_user_input()
    render_chat_page()
    render_top_navigation(active_menu_key="chat")
    render_bgm_control_button()
    process_pending_response(rerun=True)


def main() -> None:
    st.set_page_config(**PAGE_CONFIG)
    render_home_app()


if __name__ == "__main__":
    main()
