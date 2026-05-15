"""Nexon Open API task parsing and execution for graph-routed API requests."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, asdict
from typing import Any

from common.keyword_config import load_keyword_tuple
from common.nexon_state import (
    NEXON_API_TOOL_KEY,
    attach_nexon_evidence,
    make_nexon_document,
)
from common.state import AgentState, RetrievedDocument


API_TASK_CHARACTER_LOOKUP = "character_lookup"
API_TASK_RANKING_OVERALL = "ranking_overall"
API_TASK_EVENT_NOTICE = "event_notice"
API_TASK_CASH_UPDATE = "cash_update"
SUPPORTED_API_TASKS = frozenset(
    (
        API_TASK_RANKING_OVERALL,
        API_TASK_EVENT_NOTICE,
        API_TASK_CASH_UPDATE,
    )
)

RANKING_SOURCE_URL = "https://open.api.nexon.com/maplestory/v1/ranking/overall"
EVENT_SOURCE_URL = "https://open.api.nexon.com/maplestory/v1/notice-event"
CASH_UPDATE_SOURCE_URL = "https://open.api.nexon.com/maplestory/v1/notice-update"


def load_int_setting(
    env_name: str,
    default: int,
    *,
    minimum: int = 1,
    maximum: int | None = None,
) -> int:
    raw_value = os.getenv(env_name, "").strip()
    if not raw_value:
        return default
    try:
        value = int(raw_value)
    except ValueError:
        return default
    value = max(value, minimum)
    if maximum is not None:
        value = min(value, maximum)
    return value


MAX_RANKING_LIMIT = load_int_setting("MAPLE_API_MAX_RANKING_LIMIT", 100)
MAX_EVENT_LIMIT = load_int_setting("MAPLE_API_MAX_EVENT_LIMIT", 5)
MAX_CASH_NOTICE_LIMIT = load_int_setting("MAPLE_API_MAX_CASH_NOTICE_LIMIT", 3)
DEFAULT_RANKING_LIMIT = load_int_setting(
    "MAPLE_API_DEFAULT_RANKING_LIMIT",
    MAX_RANKING_LIMIT,
    maximum=MAX_RANKING_LIMIT,
)
DEFAULT_EVENT_LIMIT = load_int_setting(
    "MAPLE_API_DEFAULT_EVENT_LIMIT",
    MAX_EVENT_LIMIT,
    maximum=MAX_EVENT_LIMIT,
)
DEFAULT_CASH_NOTICE_LIMIT = load_int_setting(
    "MAPLE_API_DEFAULT_CASH_NOTICE_LIMIT",
    MAX_CASH_NOTICE_LIMIT,
    maximum=MAX_CASH_NOTICE_LIMIT,
)

RANKING_TASK_KEYWORDS = load_keyword_tuple(
    "MAPLE_API_RANKING_TASK_KEYWORDS",
    ("랭킹", "순위"),
)
EVENT_TASK_KEYWORDS = load_keyword_tuple(
    "MAPLE_API_EVENT_TASK_KEYWORDS",
    ("이벤트",),
)
EVENT_CURRENT_KEYWORDS = load_keyword_tuple(
    "MAPLE_API_EVENT_CURRENT_KEYWORDS",
    ("이번주", "이번 주", "현재", "진행중", "진행 중", "오늘", "지금"),
)
CASH_TASK_KEYWORDS = load_keyword_tuple(
    "MAPLE_API_CASH_TASK_KEYWORDS",
    ("캐시", "캐시샵"),
)
CASH_UPDATE_KEYWORDS = load_keyword_tuple(
    "MAPLE_API_CASH_UPDATE_KEYWORDS",
    ("업데이트", "공지", "신규", "최근", "최신"),
)
CASH_LATEST_KEYWORDS = load_keyword_tuple(
    "MAPLE_API_CASH_LATEST_KEYWORDS",
    ("최신", "가장 최근", "마지막"),
)
RANKING_LIMIT_PATTERNS = load_keyword_tuple(
    "MAPLE_API_RANKING_LIMIT_PATTERNS",
    (
        r"\btop\s*(?P<value>\d+)",
        r"(?P<value>\d+)\s*(?:위\s*까지|위까지|등\s*까지|명)",
    ),
)
RANKING_TARGET_PATTERNS = load_keyword_tuple(
    "MAPLE_API_RANKING_TARGET_PATTERNS",
    (r"(?P<value>\d+)\s*(?:위|등)(?!\s*까지)",),
)


@dataclass(frozen=True)
class RankingAPIQuery:
    world_name: str = ""
    target_rank: int | None = None
    limit: int = DEFAULT_RANKING_LIMIT


@dataclass(frozen=True)
class EventNoticeAPIQuery:
    max_events: int = DEFAULT_EVENT_LIMIT


@dataclass(frozen=True)
class CashUpdateAPIQuery:
    max_notices: int = DEFAULT_CASH_NOTICE_LIMIT


@dataclass(frozen=True)
class NexonAPITask:
    api_task_type: str
    api_params: dict[str, Any]


def normalize_api_query(user_input: str) -> str:
    return " ".join(str(user_input or "").split()).strip()


def contains_any(text: str, keywords: tuple[str, ...]) -> bool:
    lowered = text.lower()
    return any(keyword.lower() in lowered for keyword in keywords)


def parse_int_text(value: Any, default: int = 0) -> int:
    match = re.search(r"\d+", str(value or "").replace(",", ""))
    if not match:
        return default
    return int(match.group(0))


def bounded_int(value: Any, default: int, maximum: int) -> int:
    parsed = parse_int_text(value, default)
    if parsed <= 0:
        return default
    return min(parsed, maximum)


def extract_pattern_int(query: str, patterns: tuple[str, ...]) -> int | None:
    for pattern in patterns:
        match = re.search(pattern, query, flags=re.IGNORECASE)
        if match:
            return parse_int_text(match.groupdict().get("value") or match.group(0))
    return None


def parse_nexon_api_task(user_input: str) -> NexonAPITask | None:
    ranking_query = parse_ranking_api_query(user_input)
    if ranking_query is not None:
        return NexonAPITask(API_TASK_RANKING_OVERALL, asdict(ranking_query))

    event_query = parse_current_event_api_query(user_input)
    if event_query is not None:
        return NexonAPITask(API_TASK_EVENT_NOTICE, asdict(event_query))

    cash_query = parse_cash_update_api_query(user_input)
    if cash_query is not None:
        return NexonAPITask(API_TASK_CASH_UPDATE, asdict(cash_query))

    return None


def parse_ranking_api_query(user_input: str) -> RankingAPIQuery | None:
    normalized = normalize_api_query(user_input)
    if not normalized:
        return None

    limit = extract_ranking_limit(normalized)
    if not contains_any(normalized, RANKING_TASK_KEYWORDS) and limit is None:
        return None

    target_rank = None if limit else extract_ranking_target_rank(normalized)
    if limit is None and target_rank is None:
        return None

    from src.collectors.nexon_api import extract_world_name_from_query

    world_name = extract_world_name_from_query(normalized)
    fetch_limit = bounded_int(
        limit or target_rank or DEFAULT_RANKING_LIMIT,
        DEFAULT_RANKING_LIMIT,
        MAX_RANKING_LIMIT,
    )
    return RankingAPIQuery(
        world_name=world_name,
        target_rank=target_rank,
        limit=fetch_limit,
    )


def extract_ranking_limit(query: str) -> int | None:
    return extract_pattern_int(query, RANKING_LIMIT_PATTERNS)


def extract_ranking_target_rank(query: str) -> int | None:
    return extract_pattern_int(query, RANKING_TARGET_PATTERNS)


def parse_current_event_api_query(user_input: str) -> EventNoticeAPIQuery | None:
    normalized = normalize_api_query(user_input)
    if not normalized:
        return None
    if not contains_any(normalized, EVENT_TASK_KEYWORDS):
        return None
    if not contains_any(normalized, EVENT_CURRENT_KEYWORDS):
        return None
    return EventNoticeAPIQuery(
        max_events=bounded_int(
            normalized,
            DEFAULT_EVENT_LIMIT,
            MAX_EVENT_LIMIT,
        )
    )


def parse_cash_update_api_query(user_input: str) -> CashUpdateAPIQuery | None:
    normalized = normalize_api_query(user_input)
    if not normalized:
        return None
    if not contains_any(normalized, CASH_TASK_KEYWORDS):
        return None
    if not contains_any(normalized, CASH_UPDATE_KEYWORDS):
        return None

    requested_count = parse_int_text(normalized, 0)
    max_notices = requested_count or DEFAULT_CASH_NOTICE_LIMIT
    if contains_any(normalized, CASH_LATEST_KEYWORDS):
        max_notices = 1
    return CashUpdateAPIQuery(
        max_notices=bounded_int(max_notices, DEFAULT_CASH_NOTICE_LIMIT, MAX_CASH_NOTICE_LIMIT)
    )


def run_nexon_api_task(state: AgentState) -> AgentState:
    api_task_type = str(state.get("api_task_type") or "").strip()
    api_params = dict(state.get("api_params") or {})
    if not api_task_type:
        parsed = parse_nexon_api_task(
            str(state.get("contextualized_query") or state.get("user_query") or "")
        )
        if parsed is None:
            return state
        api_task_type = parsed.api_task_type
        api_params = parsed.api_params

    if api_task_type not in SUPPORTED_API_TASKS:
        return state

    if api_task_type == API_TASK_RANKING_OVERALL:
        result = run_ranking_task(api_params)
    elif api_task_type == API_TASK_EVENT_NOTICE:
        result = run_event_notice_task(api_params)
    elif api_task_type == API_TASK_CASH_UPDATE:
        result = run_cash_update_task(api_params)

    return attach_api_task_result(state, api_task_type, api_params, result)


def run_ranking_task(api_params: dict[str, Any]) -> dict[str, Any]:
    from src.collectors.nexon_api import fetch_overall_ranking

    query = RankingAPIQuery(
        world_name=str(api_params.get("world_name") or ""),
        target_rank=to_optional_int(api_params.get("target_rank")),
        limit=bounded_int(
            api_params.get("limit"),
            DEFAULT_RANKING_LIMIT,
            MAX_RANKING_LIMIT,
        ),
    )
    rankings = fetch_overall_ranking(
        world_name=query.world_name or None,
        limit=query.limit,
    )
    return {
        "result_kind": "ranking_list",
        "answer": build_ranking_answer(rankings, query),
        "raw": rankings,
        "source_url": RANKING_SOURCE_URL,
    }


def run_event_notice_task(api_params: dict[str, Any]) -> dict[str, Any]:
    from src.collectors.nexon_api import fetch_current_event_notices

    max_events = bounded_int(
        api_params.get("max_events"),
        DEFAULT_EVENT_LIMIT,
        MAX_EVENT_LIMIT,
    )
    events = fetch_current_event_notices(max_events=max_events)
    return {
        "result_kind": "notice_list",
        "answer": build_event_answer(events),
        "raw": events,
        "source_url": EVENT_SOURCE_URL,
    }


def run_cash_update_task(api_params: dict[str, Any]) -> dict[str, Any]:
    from src.collectors.nexon_api import fetch_recent_update_cash_sections

    max_notices = bounded_int(
        api_params.get("max_notices"),
        DEFAULT_CASH_NOTICE_LIMIT,
        MAX_CASH_NOTICE_LIMIT,
    )
    notices = fetch_recent_update_cash_sections(max_notices=max_notices)
    return {
        "result_kind": "notice_list",
        "answer": build_cash_update_answer(notices),
        "raw": notices,
        "source_url": CASH_UPDATE_SOURCE_URL,
    }


def to_optional_int(value: Any) -> int | None:
    if value in ("", None):
        return None
    parsed = parse_int_text(value, 0)
    return parsed or None


def build_ranking_answer(rankings: list[dict[str, Any]], query: RankingAPIQuery) -> str:
    scope = f"{query.world_name} 월드" if query.world_name else "전체"
    if not rankings:
        return f"{scope} 랭킹 정보를 가져오지 못했습니다. API 기준 날짜 또는 API 키를 확인해 주세요."

    if query.target_rank:
        target = find_ranking_target(rankings, query.target_rank)
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


def find_ranking_target(rankings: list[dict[str, Any]], target_rank: int) -> dict[str, Any] | None:
    for index, row in enumerate(rankings, start=1):
        if parse_int_text(row.get("ranking"), index) == target_rank:
            return row
    if 0 < target_rank <= len(rankings):
        return rankings[target_rank - 1]
    return None


def format_ranking_row(row: dict[str, Any], index: int) -> str:
    rank = row.get("ranking") or index
    character_name = row.get("character_name") or "-"
    world_name = row.get("world_name") or "-"
    class_name = row.get("class_name") or row.get("class") or "-"
    level = row.get("character_level") or "-"
    return f"{rank}. {character_name} / {world_name} / {class_name} / Lv.{level}"


def build_event_answer(events: list[dict[str, Any]]) -> str:
    if not events:
        return "진행 중인 이벤트 정보를 가져오지 못했습니다. Nexon API 설정을 확인해 주세요."
    lines = ["현재 진행 중인 메이플스토리 이벤트입니다.", ""]
    for event in events:
        title = str(event.get("title") or "제목 없음").strip()
        url = str(event.get("url") or "").strip()
        start_date = str(event.get("date_event_start") or "").strip()[:10] or "unknown"
        end_date = str(event.get("date_event_end") or "").strip()[:10] or "unknown"
        lines.extend([f"## {title}", f"- 기간: {start_date} ~ {end_date}"])
        if url:
            lines.append(f"- URL: {url}")
        lines.append("")
    return "\n".join(lines).strip()


def build_cash_update_answer(notices: list[dict[str, Any]]) -> str:
    if not notices:
        return "최근 업데이트 공지에서 캐시 관련 내용을 찾지 못했습니다. Nexon API 설정을 확인해 주세요."
    lines = ["최근 업데이트 공지의 캐시 관련 내용입니다.", ""]
    for notice in notices:
        title = str(notice.get("title") or "제목 없음").strip()
        url = str(notice.get("url") or "").strip()
        notice_date = str(notice.get("date") or "").strip()[:10] or "unknown"
        lines.extend([f"## {title}", f"- 공지일: {notice_date}"])
        if url:
            lines.append(f"- URL: {url}")
        for section in notice.get("cash_sections", []):
            lines.extend(["", str(section).strip()])
        lines.append("")
    return "\n".join(lines).strip()


def attach_api_task_result(
    state: AgentState,
    api_task_type: str,
    api_params: dict[str, Any],
    result: dict[str, Any],
) -> AgentState:
    answer = str(result.get("answer") or "").strip()
    document = build_api_task_document(api_task_type, result, answer)
    tool_results = dict(state.get("tool_results") or {})
    tool_results[NEXON_API_TOOL_KEY] = {
        "api_attempted": True,
        "lookup_attempted": False,
        "api_task_type": api_task_type,
        "api_params": api_params,
        "result_kind": result.get("result_kind", ""),
        "data_reliability": "HIGH",
        "answer": answer,
        "source_url": result.get("source_url", ""),
        "raw": result.get("raw", []),
    }
    return attach_nexon_evidence(
        {
            **state,
            "api_task_type": api_task_type,
            "api_params": api_params,
            "requires_api": False,
            "requires_character_lookup": False,
            "tool_results": tool_results,
        },
        content=answer,
        document=document,
        summary=answer,
        reliability="HIGH",
        relevance_reason=f"nexon_api_{api_task_type}",
    )


def build_api_task_document(
    api_task_type: str,
    result: dict[str, Any],
    answer: str,
) -> RetrievedDocument:
    return make_nexon_document(
        content=answer,
        score=1.0,
        metadata={
            "title": f"Nexon Open API {api_task_type}",
            "url": str(result.get("source_url") or ""),
            "reliability": "HIGH",
            "trust_level": "HIGH",
            "content_source": "nexon_open_api",
            "api_task_type": api_task_type,
            "result_kind": str(result.get("result_kind") or ""),
        },
    )
