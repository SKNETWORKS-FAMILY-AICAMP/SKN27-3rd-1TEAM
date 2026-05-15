"""메이플스토리 챗봇 Streamlit 앱의 메인 진입점.

이 모듈은 채팅 세션 상태 관리, 메시지 렌더링, LangGraph 기반 에이전트 호출,
넥슨 API 직접 호출(랭킹/이벤트/캐시 업데이트) 등 챗봇의 전체 흐름을 담당한다.
홈 페이지(`render_home_app`)와 채팅 페이지(`render_chat_app`)에서 공통으로 사용된다.
"""

from __future__ import annotations
from dotenv import load_dotenv
load_dotenv()  # .env 파일에서 API 키 등 환경변수를 미리 로드

import sys
import time
import re
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import streamlit as st
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage


# === 프로젝트 경로 설정 ===
# Streamlit 실행 시점에 `src/` 패키지를 import 할 수 있도록 sys.path에 추가
PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
for path in (PROJECT_ROOT, SRC_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))


# sys.path 설정 이후에 import해야 하므로 noqa: E402 처리
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


# === 상수 정의 ===
PAGE_CONFIG = {
    "page_title": "Maple Chat",
    "page_icon": "🍁",
    "layout": "wide",
    "initial_sidebar_state": "collapsed",
}

# 새 채팅을 시작할 때 첫 줄에 노출되는 어시스턴트의 환영 메시지
WELCOME_MESSAGE = {
    "role": "assistant",
    "content": (
        "안녕하세요! 캐릭터 성장, 보스 도전, 장비 세팅, 이벤트 보상까지 "
        "궁금한 걸 편하게 물어봐 주세요."
    ),
}

# LangGraph 결과 dict에서 답변 본문을 찾을 때 순서대로 확인할 키 목록
ANSWER_KEYS = ("final_answer", "answer", "analysis", "draft_answer")

# === 응답 출처 태그 (어떤 경로로 답변이 생성되었는지 식별) ===
RESPONSE_TAG_AGENT_GRAPH = "agent.graph"          # LangGraph 에이전트 흐름
RESPONSE_TAG_API_CHARACTER = "api.character"      # 캐릭터 조회 API 결과
RESPONSE_TAG_API_RANKING_TOP100 = "api.ranking_top100"  # 랭킹 TOP100 직접 호출
RESPONSE_TAG_API_WEEKLY_EVENT = "api.weekly_event"      # 주간 이벤트 직접 호출
RESPONSE_TAG_API_CASH_UPDATE = "api.cash_update"        # 캐시샵 업데이트 직접 호출
RESPONSE_TAG_SYSTEM_FALLBACK = "system.fallback"        # 예외 발생 시 폴백 응답

# 위 응답 태그를 트리거하는 정확한 입력 프롬프트(단축어처럼 동작)
RANKING_TOP100_PROMPT = "전체 랭킹 100위까지 보여줘."
WEEKLY_EVENT_PROMPT = "이번주 이벤트 내용 알려줘."
CASH_UPDATE_PROMPT = "캐시샵 업데이트 내용 알려줘."

DEFAULT_RANKING_LIMIT = 100
DEFAULT_EVENT_LIMIT = 5
DEFAULT_CASH_NOTICE_LIMIT = 3

# 채팅 한 세션을 구성하는 session_state 키 목록 (저장/복원 시 함께 다룸)
CHAT_STATE_KEYS = (
    "messages",                 # UI에 보여줄 메시지 목록
    "agent_messages",           # 에이전트 호출 시 사용할 전체 히스토리
    "agent_memory_summary",     # 토큰 절약용 과거 대화 요약본
    "agent_errors",             # 에이전트 실행 중 발생한 오류 누적
    "pending_user_input",       # 아직 응답 처리되지 않은 사용자 입력
    "last_response_tag",        # 마지막 응답의 출처 태그
    "last_response_metadata",   # 마지막 응답의 부가 메타데이터
)

# 채팅 세션 목록 등 전역 수준의 기본값
SESSION_DEFAULTS = {
    "chat_sessions": [],
    "current_chat_id": None,
}


def new_chat_state(user_input: str | None = None) -> dict[str, Any]:
    """새 채팅 세션의 초기 상태 dict를 생성한다.

    `user_input`이 주어지면 환영 메시지 뒤에 사용자 입력을 함께 넣어
    바로 응답 처리 단계로 넘어갈 수 있게 한다.
    """
    messages = [WELCOME_MESSAGE.copy()]
    if user_input is not None:
        # 새 채팅을 첫 입력과 함께 시작하는 흐름에서는 user 메시지를 미리 push
        messages.append({"role": "user", "content": user_input})

    return {
        "messages": messages,
        "agent_messages": [],
        "agent_memory_summary": "",
        "agent_errors": [],
        "pending_user_input": user_input,
        "last_response_tag": "",
        "last_response_metadata": {},
    }


@dataclass(frozen=True)
class AssistantResponse:
    """어시스턴트가 생성한 응답을 표준화한 컨테이너.

    answer는 화면에 출력될 본문, response_tag는 출처 분류,
    metadata는 캐릭터명/월드/소스 등 부가 정보를 담는다.
    """
    answer: str
    response_tag: str = RESPONSE_TAG_AGENT_GRAPH
    metadata: dict[str, str] = field(default_factory=dict)

    @classmethod
    def create(
        cls,
        answer: str,
        response_tag: str = RESPONSE_TAG_AGENT_GRAPH,
        **metadata: Any,
    ) -> "AssistantResponse":
        """빈 값이 제거된 표준 응답 객체를 만든다."""
        return cls(
            answer=answer,
            response_tag=response_tag,
            metadata={
                key: str(value)
                for key, value in metadata.items()
                if value not in ("", None)
            },
        )


@dataclass(frozen=True)
class RankingAPIQuery:
    """Parsed parameters for Nexon ranking/overall."""

    world_name: str = ""
    target_rank: int | None = None
    limit: int = DEFAULT_RANKING_LIMIT


@dataclass(frozen=True)
class EventNoticeAPIQuery:
    """Parsed parameters for active event notices."""

    max_events: int = DEFAULT_EVENT_LIMIT


@dataclass(frozen=True)
class CashUpdateAPIQuery:
    """Parsed parameters for cash update notice sections."""

    max_notices: int = DEFAULT_CASH_NOTICE_LIMIT


def apply_chat_state(chat_state: dict[str, Any]) -> None:
    """저장된 채팅 세션 dict를 현재 session_state에 적용한다."""
    default_state = new_chat_state()
    for key in CHAT_STATE_KEYS:
        # 누락된 키는 기본값으로 채워서 KeyError를 방지
        value = chat_state.get(key, default_state[key])
        # deepcopy로 세션 간 참조 공유를 차단해 상호 오염을 막음
        st.session_state[key] = deepcopy(value)


def init_session_state() -> None:
    """session_state에 필요한 키가 없을 때만 기본값을 세팅한다."""
    # 채팅 단위 키 초기화
    for key, value in new_chat_state().items():
        if key not in st.session_state:
            st.session_state[key] = deepcopy(value)

    # 전역(세션 목록, 현재 채팅 ID) 키 초기화
    for key, value in SESSION_DEFAULTS.items():
        if key not in st.session_state:
            st.session_state[key] = deepcopy(value)


def make_chat_title(user_input: str) -> str:
    """첫 사용자 입력으로부터 채팅 사이드바에 표시할 짧은 제목을 만든다."""
    compact = " ".join(user_input.split())
    if not compact:
        return "New chat"
    # 24자를 넘으면 말줄임표로 잘라서 사이드바 폭에 맞춤
    return compact[:24] + ("..." if len(compact) > 24 else "")


def save_current_chat() -> None:
    """현재 session_state의 채팅 내용을 chat_sessions 목록에 다시 저장한다."""
    chat_id = st.session_state.get("current_chat_id")
    if not chat_id:
        return

    for session in st.session_state.chat_sessions:
        if session["id"] == chat_id:
            for key in CHAT_STATE_KEYS:
                # 저장 시점의 스냅샷을 deepcopy로 보관
                session[key] = deepcopy(st.session_state.get(key))
            return


def load_chat_session(chat_id: str) -> None:
    """사이드바에서 다른 채팅을 선택했을 때 호출되는 진입점."""
    # 현재 채팅을 먼저 저장한 뒤 새 채팅으로 전환 (작업 손실 방지)
    save_current_chat()
    for session in st.session_state.chat_sessions:
        if session["id"] == chat_id:
            st.session_state.current_chat_id = chat_id
            apply_chat_state(session)
            return


def start_new_chat(user_input: str) -> None:
    """입력 한 줄로 새 채팅 세션을 즉시 만들고 활성화한다."""
    # 밀리초 단위 timestamp로 충돌 가능성이 낮은 id 생성
    chat_id = f"chat-{int(time.time() * 1000)}"
    session = {
        "id": chat_id,
        "title": make_chat_title(user_input),
        "created_at": time.time(),
        **new_chat_state(user_input),
    }
    # 최신 세션이 사이드바 최상단에 노출되도록 맨 앞에 삽입
    st.session_state.chat_sessions.insert(0, session)
    st.session_state.current_chat_id = chat_id
    apply_chat_state(session)


@st.cache_resource(show_spinner=False)
def load_graph() -> Any:
    """LangGraph 인스턴스를 캐싱해서 재사용한다.

    `@st.cache_resource` 덕분에 그래프 빌드 비용을 한 번만 지불한다.
    """
    # 무거운 의존성이므로 함수 안에서 lazy import
    from src.graph import maple_chat_graph

    return maple_chat_graph()


def to_langchain_messages(messages: list[dict[str, str]]) -> list[BaseMessage]:
    """dict 기반 메시지 히스토리를 LangChain BaseMessage 객체로 변환한다."""
    converted = []
    for message in messages:
        role = message["role"]
        content = message["content"]

        # role 문자열을 LangChain 메시지 클래스에 1:1로 매핑
        if role == "system":
            converted.append(SystemMessage(content=content))
        elif role == "user":
            converted.append(HumanMessage(content=content))
        elif role == "assistant":
            converted.append(AIMessage(content=content))
    return converted


def extract_answer(result: Any) -> str:
    """LangGraph 실행 결과에서 사용자에게 보여줄 답변 문자열을 추출한다."""
    if isinstance(result, dict):
        # ANSWER_KEYS의 우선순위대로 채워진 필드를 찾는다
        for key in ANSWER_KEYS:
            value = result.get(key)
            if value:
                return str(value)

        # 명시적 answer 필드가 없으면 messages 마지막 항목을 사용
        messages = result.get("messages")
        if messages:
            last_message = messages[-1]
            return str(getattr(last_message, "content", last_message))

    if result:
        return str(result)

    # 모든 경로가 실패한 경우의 안전한 안내문
    return "답변을 생성하지 못했습니다. 잠시 후 다시 시도해 주세요."


def fallback_answer(user_input: str, error: Exception) -> str:
    """에이전트 그래프 실행 중 예외가 발생했을 때 사용자에게 줄 응답."""
    # 디버깅을 위해 에러 메시지는 session_state에 누적해 둔다
    st.session_state.agent_errors.append(str(error))
    return (
        "현재 에이전트 그래프를 실행하지 못했습니다.\n\n"
        f"- 입력한 질문: {user_input}\n"
        "- 확인할 것: 필요한 에이전트 모듈, API 키, DB 연결 설정이 준비되어 있는지 확인해 주세요."
    )


def normalize_direct_api_query(user_input: str) -> str:
    """직접 API 라우팅에서 공통으로 쓰는 가벼운 질의 정규화."""

    return " ".join(str(user_input or "").split()).strip()


def parse_int_text(value: Any, default: int = 0) -> int:
    match = re.search(r"\d+", str(value or "").replace(",", ""))
    if not match:
        return default
    return int(match.group(0))


def clamp_positive(value: int, default: int, maximum: int) -> int:
    if value <= 0:
        return default
    return min(value, maximum)


def parse_ranking_api_query(user_input: str) -> RankingAPIQuery | None:
    """Return ranking API parameters only when the query maps to ranking/overall."""

    normalized = normalize_direct_api_query(user_input)
    if not normalized:
        return None

    lower_query = normalized.lower()
    if "랭킹" not in normalized and "순위" not in normalized and not re.search(r"\btop\s*\d+", lower_query):
        return None

    limit = extract_ranking_limit(normalized)
    target_rank = None if limit else extract_ranking_target_rank(normalized)
    if limit is None and target_rank is None:
        return None

    from src.collectors.nexon_api import extract_world_name_from_query

    world_name = extract_world_name_from_query(normalized)
    fetch_limit = clamp_positive(
        limit or target_rank or DEFAULT_RANKING_LIMIT,
        DEFAULT_RANKING_LIMIT,
        DEFAULT_RANKING_LIMIT,
    )
    return RankingAPIQuery(
        world_name=world_name,
        target_rank=target_rank,
        limit=fetch_limit,
    )


def extract_ranking_limit(query: str) -> int | None:
    patterns = (
        r"\btop\s*(?P<limit>\d+)",
        r"(?P<limit>\d+)\s*(?:위|등)\s*까지",
    )
    for pattern in patterns:
        match = re.search(pattern, query, flags=re.IGNORECASE)
        if match:
            return parse_int_text(match.group("limit"))
    return None


def extract_ranking_target_rank(query: str) -> int | None:
    match = re.search(r"(?P<rank>\d+)\s*(?:위|등)(?!\s*까지)", query)
    if not match:
        return None
    return parse_int_text(match.group("rank"))


def parse_current_event_api_query(user_input: str) -> EventNoticeAPIQuery | None:
    """Return active-event API parameters when the query asks for current events."""

    normalized = normalize_direct_api_query(user_input)
    if not normalized:
        return None
    if normalized == WEEKLY_EVENT_PROMPT:
        return EventNoticeAPIQuery()
    if "이벤트" not in normalized:
        return None
    if not re.search(r"이번\s*주|현재|진행\s*중|오늘|지금", normalized):
        return None
    return EventNoticeAPIQuery(
        max_events=clamp_positive(
            parse_int_text(normalized, DEFAULT_EVENT_LIMIT),
            DEFAULT_EVENT_LIMIT,
            DEFAULT_EVENT_LIMIT,
        )
    )


def parse_cash_update_api_query(user_input: str, *, latest_only_once: bool = False) -> CashUpdateAPIQuery | None:
    """Return cash-update API parameters when the query maps to update notices."""

    normalized = normalize_direct_api_query(user_input)
    if not normalized:
        return None
    if normalized == CASH_UPDATE_PROMPT:
        return CashUpdateAPIQuery(max_notices=1 if latest_only_once else DEFAULT_CASH_NOTICE_LIMIT)
    if "캐시" not in normalized:
        return None
    if not re.search(r"업데이트|공지|신규|최근|최신", normalized):
        return None

    requested_count = parse_int_text(normalized, 0)
    max_notices = requested_count or (1 if latest_only_once else DEFAULT_CASH_NOTICE_LIMIT)
    if re.search(r"최신|가장\s*최근|마지막", normalized):
        max_notices = 1
    return CashUpdateAPIQuery(
        max_notices=clamp_positive(max_notices, DEFAULT_CASH_NOTICE_LIMIT, DEFAULT_CASH_NOTICE_LIMIT)
    )


def format_ranking_row(row: dict[str, Any], index: int) -> str:
    rank = row.get("ranking") or index
    character_name = row.get("character_name") or "-"
    world_name = row.get("world_name") or "-"
    class_name = row.get("class_name") or row.get("class") or "-"
    level = row.get("character_level") or "-"
    return f"{rank}. {character_name} / {world_name} / {class_name} / Lv.{level}"


def ranking_row_rank(row: dict[str, Any], index: int) -> int:
    return parse_int_text(row.get("ranking"), index)


def build_ranking_answer(rankings: list[dict[str, Any]], query: RankingAPIQuery) -> str:
    scope = f"{query.world_name} 월드" if query.world_name else "전체"
    if not rankings:
        return f"{scope} 랭킹 정보를 가져오지 못했습니다. API 기준 날짜 또는 API 키를 확인해 주세요."

    if query.target_rank:
        target = next(
            (
                row
                for index, row in enumerate(rankings, start=1)
                if ranking_row_rank(row, index) == query.target_rank
            ),
            None,
        )
        if target is None and 0 < query.target_rank <= len(rankings):
            target = rankings[query.target_rank - 1]
        if target is None:
            return f"{scope} 랭킹 {query.target_rank}위 정보를 가져오지 못했습니다."

        character_name = target.get("character_name") or "-"
        world_name = target.get("world_name") or query.world_name or "-"
        class_name = target.get("class_name") or target.get("class") or "-"
        level = target.get("character_level") or "-"
        rank = target.get("ranking") or query.target_rank
        return "\n".join(
            [
                f"{scope} 랭킹 {rank}위는 {character_name}입니다.",
                "",
                f"- 월드: {world_name}",
                f"- 직업: {class_name}",
                f"- 레벨: {level}",
                "- 출처: Nexon Open API ranking/overall",
            ]
        )

    lines = [f"{scope} 랭킹 TOP {query.limit}입니다.", ""]
    lines.extend(format_ranking_row(row, index) for index, row in enumerate(rankings[:query.limit], start=1))
    return "\n".join(lines)


def build_direct_api_response(user_input: str) -> AssistantResponse | None:
    """직접 API 파라미터로 해석되는 질문을 처리하고, 해당 없으면 None을 반환한다."""

    ranking_query = parse_ranking_api_query(user_input)
    if ranking_query is not None:
        from src.collectors.nexon_api import fetch_overall_ranking

        rankings = fetch_overall_ranking(
            world_name=ranking_query.world_name or None,
            limit=ranking_query.limit,
        )
        answer = build_ranking_answer(rankings, ranking_query)
        return AssistantResponse.create(
            answer,
            RESPONSE_TAG_API_RANKING_TOP100,
            source="nexon_open_api",
            result_kind="ranking_list",
            world_name=ranking_query.world_name,
            target_rank=ranking_query.target_rank,
            limit=ranking_query.limit,
        )

    event_query = parse_current_event_api_query(user_input)
    if event_query is not None:
        from src.collectors.nexon_api import fetch_current_event_notices

        events = fetch_current_event_notices(max_events=event_query.max_events)
        if not events:
            answer = "이번주 이벤트 정보를 가져오지 못했습니다. Nexon API 키와 이벤트 공지 데이터를 확인해 주세요."
        elif events:
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
                        "### 이벤트 기간",
                        f"{start_date} ~ {end_date}",
                        "### URL",
                        link,
                        "",
                    ]
                )
            answer = "\n".join(lines)
        return AssistantResponse.create(
            answer,
            RESPONSE_TAG_API_WEEKLY_EVENT,
            source="nexon_open_api",
            result_kind="notice_list",
            max_events=event_query.max_events,
        )

    latest_only = bool(st.session_state.get("cash_update_latest_only_once", False))
    cash_query = parse_cash_update_api_query(user_input, latest_only_once=latest_only)
    if cash_query is not None:
        st.session_state.pop("cash_update_latest_only_once", False)
        from src.collectors.nexon_api import fetch_recent_update_cash_sections

        notices = fetch_recent_update_cash_sections(max_notices=cash_query.max_notices)
        if not notices:
            answer = "최근 업데이트 공지에서 캐시 관련 내용을 찾지 못했습니다. Nexon API 키와 업데이트 공지 데이터를 확인해 주세요."
        elif notices:
            lines = ["최근 업데이트 공지의 캐시 관련 내용입니다.", ""]
            for notice in notices:
                title = str(notice.get("title") or "제목 없음").strip()
                url = str(notice.get("url") or "").strip()
                notice_date = str(notice.get("date") or "").strip()[:10] or "unknown"
                link = f"[바로가기]({url})" if url else "URL 없음"
                lines.extend(
                    [
                        f"## {title}",
                        "### 공지일",
                        notice_date,
                        "### URL",
                        link,
                        "### 캐시 관련 내용",
                    ]
                )
                for section in notice.get("cash_sections", []):
                    lines.extend([section, ""])
            answer = "\n".join(lines)
        return AssistantResponse.create(
            answer,
            RESPONSE_TAG_API_CASH_UPDATE,
            source="nexon_open_api",
            result_kind="notice_list",
            max_notices=cash_query.max_notices,
        )

    return None


def build_graph_response(result: Any) -> AssistantResponse:
    """LangGraph 결과에서 답변 본문, 응답 태그, 메타데이터를 한 번에 만든다."""
    if not isinstance(result, dict):
        return AssistantResponse.create(extract_answer(result), RESPONSE_TAG_AGENT_GRAPH, source="langgraph")

    def value_from(source: Any, key: str) -> Any:
        if isinstance(source, dict):
            return source.get(key, "")
        return getattr(source, key, "")

    profile = result.get("character_profile") or {}
    tool_results = result.get("tool_results") or {}
    nexon_result = tool_results.get("nexon_api") if isinstance(tool_results, dict) else {}
    is_character_response = bool(
        result.get("ocid")
        or result.get("character_profile")
        or (isinstance(nexon_result, dict) and nexon_result)
    )

    metadata: dict[str, Any] = {
        "source": "langgraph",
        "ocid": result.get("ocid"),
        "character_name": result.get("character_name") or value_from(profile, "character_name"),
        "world_name": result.get("world_name") or value_from(profile, "world_name"),
        "job_name": value_from(profile, "job_name"),
        "level": value_from(profile, "level"),
    }
    if isinstance(nexon_result, dict):
        metadata["nexon_lookup_attempted"] = nexon_result.get("lookup_attempted")
        metadata["nexon_data_reliability"] = nexon_result.get("data_reliability")

    return AssistantResponse.create(
        extract_answer(result),
        RESPONSE_TAG_API_CHARACTER if is_character_response else RESPONSE_TAG_AGENT_GRAPH,
        **metadata,
    )


def get_assistant_response(user_input: str) -> AssistantResponse:
    """사용자 입력 한 줄에 대한 어시스턴트 응답을 생성하는 핵심 디스패처.

    1) 단축 명령(랭킹/이벤트/캐시)이면 넥슨 API를 직접 호출
    2) 그 외엔 LangGraph 에이전트로 위임
    3) 어디서든 예외가 나면 폴백 응답으로 감싼다.
    """
    try:
        # 단축 명령 분기: API를 바로 두드려 빠르게 응답
        direct_response = build_direct_api_response(user_input)
        if direct_response is not None:
            return direct_response

        # 일반 흐름: LangGraph 호출
        graph = load_graph()
        # 히스토리가 길어지면 요약본으로 압축 (토큰 한도 보호)
        compacted_messages, memory_summary = compact_agent_history(
            st.session_state.agent_messages,
            st.session_state.agent_memory_summary,
            st.session_state.agent_errors.append,
        )
        st.session_state.agent_messages = compacted_messages
        st.session_state.agent_memory_summary = memory_summary

        # 시스템 프롬프트 + 요약 + 최근 메시지 + 신규 user 입력을 조립
        agent_messages = build_agent_messages(
            user_input,
            st.session_state.agent_messages,
            st.session_state.agent_memory_summary,
        )
        # LangGraph 노드들이 공유할 초기 state 구성
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
        return build_graph_response(result)
    except Exception as exc:
        # 예외 종류와 무관하게 사용자에게는 친절한 폴백 메시지로 응답
        return AssistantResponse.create(
            fallback_answer(user_input, exc),
            RESPONSE_TAG_SYSTEM_FALLBACK,
            error_type=type(exc).__name__,
        )


def reset_chat() -> None:
    """현재 채팅을 깨끗한 초기 상태로 되돌린다."""
    apply_chat_state(new_chat_state())


def append_agent_turn(user_input: str, response: AssistantResponse) -> None:
    """에이전트 히스토리에 (user, assistant) 한 턴을 추가한다.

    각 메시지에 response_tag/메타데이터를 함께 박아두어
    이후 분석이나 UI 표시(어떤 경로의 응답인지)에 활용한다.
    """
    tag_fields = {
        "response_tag": response.response_tag,
        # metadata는 response_<key> 접두사로 평탄화해 dict 1단계로 보관
        **{
            f"response_{key}": value
            for key, value in response.metadata.items()
        },
    }
    st.session_state.agent_messages.extend(
        [
            {"role": "user", "content": user_input, **tag_fields},
            {"role": "assistant", "content": response.answer, **tag_fields},
        ]
    )


def handle_user_input() -> None:
    """st.chat_input에서 들어온 신규 입력을 받아 적절한 채팅으로 라우팅한다."""
    user_input = st.chat_input("Type your question here...")
    if not user_input:
        return

    # 홈에서 입력한 경우 채팅 페이지를 새로 열고 거기서 응답 처리
    if st.session_state.get("active_page") != "chat":
        start_new_chat(user_input)
        st.switch_page("pages/7_Chat.py")
        return

    if not st.session_state.get("current_chat_id"):
        # 아직 선택된 채팅이 없으면 새 채팅을 만들어 첫 입력으로 사용
        start_new_chat(user_input)
        return

    # 기존 채팅에 이어붙이고, pending에 표시해 다음 rerun에서 응답 생성
    st.session_state.messages.append({"role": "user", "content": user_input})
    st.session_state.pending_user_input = user_input
    save_current_chat()


def process_pending_response(rerun: bool = True) -> None:
    """pending_user_input이 있으면 에이전트를 호출해 답변을 채워 넣는다."""
    user_input = st.session_state.pending_user_input
    if not user_input:
        return

    # 로딩 스피너로 응답 생성 중임을 사용자에게 알림
    with st.spinner("답변을 준비하고 있습니다..."):
        started_at = time.perf_counter()
        response = get_assistant_response(user_input)
        answer = response.answer
        # 응답 소요시간(초)을 별도로 저장해 디버깅/노출에 활용
        st.session_state.last_response_seconds = round(
            time.perf_counter() - started_at,
            2,
        )

    # 마지막 응답 메타정보 갱신 (UI 배지/태그 표시용)
    st.session_state.last_response_tag = response.response_tag
    st.session_state.last_response_metadata = response.metadata
    st.session_state.messages.append({"role": "assistant", "content": answer})
    append_agent_turn(user_input, response)
    # 처리 완료 후 pending을 비워야 다음 rerun에서 중복 호출되지 않음
    st.session_state.pending_user_input = None
    save_current_chat()
    if rerun:
        # 새 메시지를 즉시 화면에 반영하기 위한 강제 rerun
        st.rerun()


def render_home_app() -> None:
    """홈(랜딩) 페이지 렌더링 엔트리."""
    init_session_state()
    st.session_state.active_page = "home"
    render_style()
    render_page_bgm("home")
    render_messages()
    render_top_navigation(active_menu_key="home")
    render_bgm_control_button()


def render_chat_app() -> None:
    """채팅 페이지 렌더링 엔트리. 입력 수집 → 페이지 렌더 → pending 응답 처리 순."""
    init_session_state()
    st.session_state.active_page = "chat"
    # 채팅에 처음 들어왔을 때 자동으로 가장 최근 세션을 활성화
    if not st.session_state.get("current_chat_id") and st.session_state.chat_sessions:
        load_chat_session(st.session_state.chat_sessions[0]["id"])

    render_style()
    render_page_bgm("chat")
    handle_user_input()
    render_chat_page()
    render_top_navigation(active_menu_key="chat")
    render_bgm_control_button()
    # 렌더링 이후 pending 응답을 처리해야 사용자 메시지가 먼저 보인 뒤 답변이 따라옴
    process_pending_response(rerun=True)


def main() -> None:
    """단독 실행 시 진입점 (Streamlit run으로 직접 호출되는 경우)."""
    st.set_page_config(**PAGE_CONFIG)
    render_home_app()


if __name__ == "__main__":
    main()
