from __future__ import annotations

import csv
import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal, TypedDict

from common.state import AgentState, RetrievedDocument
from common.validator import validate_agent_inputs, validate_agent_outputs


ResearchMode = Literal["auto", "text", "vector", "hybrid"]
ResearchIntent = Literal[
    "general",
    "boss_strategy",
    "boss_requirement",
    "boss_reward",
    "time_sensitive",
]


class ResearchRouting(TypedDict):
    """Research Agent가 어떤 검색기를 사용할지 담는 설정값입니다."""

    use_db: bool
    use_graph: bool
    use_web: bool
    db_mode: ResearchMode
    top_k: int
    graph_top_k: int
    web_max_results: int
    web_max_contexts: int
    official_only: bool
    reason: str
    search_query: str
    parser_source: str
    intent_tags: list[ResearchIntent]
    task_type: str


RESEARCH_ROUTE_PARSER_PROMPT = """
You are a MapleStory Korean research route parser.
Extract only retrieval strategy for a Research Agent. Do not answer the user.
Return only one JSON object with these keys:
- use_db: boolean
- use_graph: boolean
- use_web: boolean
- db_mode: auto | text | vector | hybrid
- top_k: integer from 1 to 10
- graph_top_k: integer from 1 to 10
- web_max_results: integer from 1 to 10
- web_max_contexts: integer from 1 to 10
- official_only: boolean
- search_query: concise Korean search query preserving game terms and character names
- intent_tags: array using only general, boss_strategy, boss_requirement, boss_reward, time_sensitive
- reason: short snake_case string

Rules:
- use_db should usually be true for MapleStory knowledge questions.
- use_graph should be true for structured facts such as bosses, rewards, equipment sets, stats, requirements, drops, jobs, or content relationships.
- use_web should be true for latest/current/today/recent notices, patches, events, cash shop, test world, market prices, or time-sensitive questions.
- use_web should also be true when the question needs external facts that may not be covered by local DB/Graph evidence.
- If use_web is false but local DB/Graph retrieval returns no usable evidence, the Research Agent will run a web fallback.
- official_only should be true for official notices, patches, events, and current factual claims.
- Prefer db_mode text unless semantic/vector search is clearly needed.
- Do not invent facts or answer the user.
""".strip()

REPO_ROOT = Path(__file__).resolve().parents[2]
BOSS_ALIAS_CSV_PATH = REPO_ROOT / "database" / "data" / "neo4j_import" / "boss_aliases.csv"


GRAPH_KEYWORDS = (
    "boss",
    "\ubcf4\uc2a4",
    "\uc7a5\ube44",
    "\uc138\ud2b8",
    "\uc138\ud2b8\ud6a8\uacfc",
    "\ubcf4\uc0c1",
    "\ub4dc\ub86d",
    "\uc694\uad6c",
    "\uc2a4\ud399",
    "\uc8fc\uc2a4\ud0ef",
)

REQUIREMENT_KEYWORDS = (
    "\uc694\uad6c",
    "\ud544\uc694",
    "\uc785\uc7a5",
    "\uc870\uac74",
    "\uc2a4\ud399",
    "\uc8fc\uc2a4\ud0ef",
)

WEB_KEYWORDS = (
    "\ucd5c\uc2e0",
    "\ud604\uc7ac",
    "\uc624\ub298",
    "\uc774\ubc88",
    "\uc9c4\ud589",
    "\uacf5\uc9c0",
    "\ud328\uce58",
    "\uc5c5\ub370\uc774\ud2b8",
    "\uc774\ubca4\ud2b8",
    "\ubc84\ub2dd",
    "\ud14c\uc12d",
    "\ud14c\uc2a4\ud2b8\uc6d4\ub4dc",
    "\uce90\uc2dc\uc0f5",
)
OFFICIAL_SOURCE_TASK_TYPES = {
    "event_information",
    "patch_information",
}
QUERY_BOILERPLATE_TERMS = {
    "대해",
    "대해서",
    "대한",
    "알려줘",
    "알려줘요",
    "알려",
    "설명",
    "설명해줘",
    "무엇",
    "무엇인가",
    "뭐야",
    "뭔가",
    "정보",
    "정리",
    "좀",
    "해줘",
    "해주세요",
    "주세요",
}
KOREAN_PARTICLE_SUFFIXES = (
    "으로부터",
    "에게서",
    "에서는",
    "으로는",
    "에게",
    "에서",
    "부터",
    "까지",
    "으로",
    "로서",
    "로써",
    "와",
    "과",
    "을",
    "를",
    "은",
    "는",
    "이",
    "가",
    "에",
    "도",
    "만",
    "로",
)

BOSS_REWARD_KEYWORDS = (
    "\ubcf4\uc0c1",
    "\ub4dc\ub86d",
    "\uacb0\uc815\uc11d",
    "\uac15\ub82c\ud55c \ud798\uc758 \uacb0\uc815",
)
BOSS_STRATEGY_KEYWORDS = (
    "공략",
    "패턴",
    "기믹",
    "방법",
    "잡는법",
    "잡는 법",
    "깨는법",
    "깨는 법",
    "클리어",
    "생존",
    "피하는",
    "피하기",
)
VALID_INTENT_TAGS: tuple[ResearchIntent, ...] = (
    "general",
    "boss_strategy",
    "boss_requirement",
    "boss_reward",
    "time_sensitive",
)
GRAPH_INTENT_TAGS = {"boss_strategy", "boss_requirement", "boss_reward"}
DOCUMENT_CATEGORY_INTENT_TAGS: dict[str, tuple[ResearchIntent, ...]] = {
    "boss_recommendation_rule": ("boss_strategy", "boss_requirement"),
    "reward_priority_rule": ("boss_reward",),
    "official_event": ("time_sensitive",),
    "official_notice": ("time_sensitive",),
    "official_update": ("time_sensitive",),
    "testworld_update": ("time_sensitive",),
}
RETRIEVAL_METHOD_INTENT_TAGS: dict[str, tuple[ResearchIntent, ...]] = {
    "graph_requirement": ("boss_requirement", "boss_strategy"),
    "graph_reward": ("boss_reward",),
}
WEB_PATH_INTENT_TAGS: dict[str, tuple[ResearchIntent, ...]] = {
    "/news/update": ("time_sensitive",),
    "/news/event": ("time_sensitive",),
    "/news/notice": ("time_sensitive",),
    "/news/cashshop": ("time_sensitive",),
    "/promotion/event": ("time_sensitive",),
    "/guide": ("general",),
}
TITLE_INTENT_HINTS: tuple[tuple[str, tuple[ResearchIntent, ...]], ...] = (
    ("업데이트", ("time_sensitive",)),
    ("이벤트", ("time_sensitive",)),
    ("공지", ("time_sensitive",)),
    ("캐시샵", ("time_sensitive",)),
)


@lru_cache(maxsize=1)
def load_boss_alias_keywords(path: str | None = None) -> tuple[str, ...]:
    alias_path = Path(path) if path else BOSS_ALIAS_CSV_PATH
    if not alias_path.exists():
        return ()

    keywords: set[str] = set()
    with alias_path.open("r", encoding="utf-8-sig", newline="") as csv_file:
        reader = csv.DictReader(csv_file)
        for row in reader:
            for field_name in ("name", "normalized_name"):
                value = str(row.get(field_name) or "").strip().lower()
                if len(value) >= 2:
                    keywords.add(value)
    return tuple(sorted(keywords, key=len, reverse=True))


def graph_route_keywords() -> tuple[str, ...]:
    return (*GRAPH_KEYWORDS, *load_boss_alias_keywords())


def derive_intent_tags(query: str) -> list[ResearchIntent]:
    normalized_query = str(query or "").lower()
    has_boss_reference = "보스" in normalized_query or any(
        keyword.lower() in normalized_query
        for keyword in load_boss_alias_keywords()
    )
    tags: list[ResearchIntent] = []

    if has_boss_reference and any(keyword in normalized_query for keyword in BOSS_STRATEGY_KEYWORDS):
        tags.extend(["boss_strategy", "boss_requirement"])
    if has_boss_reference and any(keyword in normalized_query for keyword in REQUIREMENT_KEYWORDS):
        tags.append("boss_requirement")
    if has_boss_reference and any(keyword in normalized_query for keyword in BOSS_REWARD_KEYWORDS):
        tags.append("boss_reward")
    if any(keyword.lower() in normalized_query for keyword in WEB_KEYWORDS):
        tags.append("time_sensitive")

    return normalize_intent_tags(tags)


def normalize_intent_tags(value: Any) -> list[ResearchIntent]:
    raw_tags = value if isinstance(value, list) else []
    tags: list[ResearchIntent] = []
    for raw_tag in raw_tags:
        tag = str(raw_tag or "").strip().lower()
        if tag in VALID_INTENT_TAGS and tag not in tags:
            tags.append(tag)  # type: ignore[arg-type]
    return tags or ["general"]


def merge_intent_tags(*tag_lists: list[ResearchIntent]) -> list[ResearchIntent]:
    merged: list[ResearchIntent] = []
    for tag_list in tag_lists:
        for tag in tag_list:
            if tag == "general" and len(tag_list) > 1:
                continue
            if tag not in merged:
                merged.append(tag)
    return merged or ["general"]


def route_tags_have_graph_intent(intent_tags: list[ResearchIntent]) -> bool:
    return bool(set(intent_tags).intersection(GRAPH_INTENT_TAGS))


def route_requires_official_sources(route: ResearchRouting) -> bool:
    task_type = str(route.get("task_type") or "").strip()
    intent_tags = set(normalize_intent_tags(route.get("intent_tags")))
    return bool(
        task_type in OFFICIAL_SOURCE_TASK_TYPES
        or "time_sensitive" in intent_tags
    )


def classify_research_route(query: str, task_type: str = "") -> ResearchRouting:
    """질문을 보고 DB/Graph/Web 중 어떤 검색을 쓸지 고릅니다.

    여기서는 LLM에게 판단을 맡기지 않고 키워드로만 판단합니다.
    """

    normalized_query = query.lower()
    normalized_task_type = str(task_type or "").strip()
    intent_tags = derive_intent_tags(query)

    structured_boss_reward = "boss_reward" in intent_tags and "time_sensitive" not in intent_tags

    needs_graph = normalized_task_type != "story_explanation" and (
        route_tags_have_graph_intent(intent_tags)
        or any(keyword.lower() in normalized_query for keyword in graph_route_keywords())
    )

    needs_web = "time_sensitive" in intent_tags
    if structured_boss_reward:
        needs_web = False

    reason = "document_research"
    if normalized_task_type == "story_explanation":
        reason = "task_type_story_explanation"
    elif needs_web and needs_graph:
        reason = "latest_structured_fact"
    elif structured_boss_reward:
        reason = "boss_reward_graph_fact"
    elif needs_web:
        reason = "latest_or_notice"
    elif needs_graph:
        reason = "structured_fact"

    return {
        "use_db": True,
        "use_graph": needs_graph,
        "use_web": needs_web,
        "db_mode": "text",
        "top_k": 5,
        "graph_top_k": 3,
        "web_max_results": 5,
        "web_max_contexts": 5,
        "official_only": bool(needs_web or normalized_task_type in OFFICIAL_SOURCE_TASK_TYPES),
        "reason": reason,
        "search_query": normalize_search_query(query, query, task_type=normalized_task_type),
        "parser_source": "keyword",
        "intent_tags": intent_tags,
        "task_type": normalized_task_type,
    }


def parse_research_route_with_llm(query: str) -> ResearchRouting:
    """Use an LLM to parse the Research Agent retrieval plan."""

    from common.get_model import get_llm
    from langchain_core.messages import HumanMessage, SystemMessage

    response = get_llm().invoke(
        [
            SystemMessage(content=RESEARCH_ROUTE_PARSER_PROMPT),
            HumanMessage(content=f"User query: {query}\nJSON only:"),
        ]
    )
    content = getattr(response, "content", response)
    return normalize_research_route_parse(query, parse_json_object(str(content)))


def build_research_route(
    query: str,
    *,
    task_type: str = "",
    use_llm: bool = True,
) -> tuple[ResearchRouting, dict[str, Any]]:
    """Return a research route plus parser metadata for tool_results."""

    fallback_route = classify_research_route(query, task_type=task_type)
    if not use_llm:
        return fallback_route, {"used_llm": False, "fallback_used": False}

    try:
        route = normalize_research_task_type(parse_research_route_with_llm(query), task_type)
    except Exception as exc:
        return fallback_route, {
            "used_llm": True,
            "fallback_used": True,
            "error": str(exc),
        }

    route["use_db"] = route["use_db"] or fallback_route["use_db"]
    route["use_graph"] = route["use_graph"] or fallback_route["use_graph"]
    route["use_web"] = route["use_web"] or fallback_route["use_web"]
    route["intent_tags"] = merge_intent_tags(
        normalize_intent_tags(route.get("intent_tags")),
        fallback_route["intent_tags"],
    )
    route = apply_route_intent_guards(query, route)
    if route["use_web"] and route_requires_official_sources(route):
        route["official_only"] = True
    route["parser_source"] = "llm"
    return route, {"used_llm": True, "fallback_used": False}


def parse_json_object(text: str) -> dict[str, Any]:
    """Parse a JSON object, allowing fenced or lightly wrapped LLM output."""

    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped, flags=re.IGNORECASE)
        stripped = re.sub(r"\s*```$", "", stripped).strip()

    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", stripped, flags=re.DOTALL)
        if not match:
            raise
        parsed = json.loads(match.group(0))

    if not isinstance(parsed, dict):
        raise ValueError("research route parser returned non-object JSON")
    return parsed


def normalize_research_route_parse(
    query: str,
    parsed: dict[str, Any],
    task_type: str = "",
) -> ResearchRouting:
    normalized_task_type = str(task_type or "").strip()
    fallback = classify_research_route(query, task_type=normalized_task_type)
    db_mode = str(parsed.get("db_mode") or fallback["db_mode"]).lower()
    if db_mode not in {"auto", "text", "vector", "hybrid"}:
        db_mode = fallback["db_mode"]

    use_graph = coerce_bool(parsed.get("use_graph"), fallback["use_graph"])
    intent_tags = merge_intent_tags(
        normalize_intent_tags(parsed.get("intent_tags")),
        fallback["intent_tags"],
    )
    return {
        "use_db": coerce_bool(parsed.get("use_db"), fallback["use_db"]) or use_graph,
        "use_graph": use_graph,
        "use_web": coerce_bool(parsed.get("use_web"), fallback["use_web"]),
        "db_mode": db_mode,  # type: ignore[typeddict-item]
        "top_k": clamp_int(parsed.get("top_k"), fallback["top_k"], 1, 10),
        "graph_top_k": clamp_int(parsed.get("graph_top_k"), fallback["graph_top_k"], 1, 10),
        "web_max_results": clamp_int(parsed.get("web_max_results"), fallback["web_max_results"], 1, 10),
        "web_max_contexts": clamp_int(parsed.get("web_max_contexts"), fallback["web_max_contexts"], 1, 10),
        "official_only": coerce_bool(parsed.get("official_only"), fallback["official_only"]),
        "reason": normalize_reason(parsed.get("reason"), fallback["reason"]),
        "search_query": normalize_search_query(
            parsed.get("search_query"),
            query,
            task_type=normalized_task_type,
        ),
        "parser_source": "llm",
        "intent_tags": intent_tags,
        "task_type": normalized_task_type,
    }


def coerce_bool(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "yes", "y", "1"}:
            return True
        if lowered in {"false", "no", "n", "0"}:
            return False
    return default


def clamp_int(value: Any, default: int, minimum: int, maximum: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = default
    return max(minimum, min(maximum, number))


def normalize_reason(value: Any, default: str) -> str:
    reason = re.sub(r"[^0-9A-Za-z_]+", "_", str(value or default).strip().lower())
    return reason.strip("_") or default


def normalize_search_query(value: Any, default: str, task_type: str = "") -> str:
    query = str(value or "").strip()
    normalized_task_type = str(task_type or "").strip()
    normalized_query = normalize_query_boss_aliases(query or default, task_type=normalized_task_type)
    if normalized_task_type != "story_explanation":
        return normalized_query

    graph_terms = {keyword.lower() for keyword in GRAPH_KEYWORDS}
    terms = [
        term
        for term in normalized_query.split()
        if term.lower() not in graph_terms
    ]
    return " ".join(terms) or normalized_query


def normalize_query_boss_aliases(query: str, task_type: str = "") -> str:
    """기존 boss_aliases.csv를 이용해 짧은 보스명 오타를 검색어에서 보정한다."""
    normalized_query = str(query or "").strip()
    lower_query = normalized_query.lower()
    can_use_aliases = (
        str(task_type or "").strip() == "story_explanation"
        or any(keyword.lower() in lower_query for keyword in GRAPH_KEYWORDS)
    )
    if not can_use_aliases:
        return normalized_query

    aliases = load_boss_alias_keywords()
    terms = []
    for raw_term in normalized_query.split():
        term = raw_term.strip()
        replacement = term
        for alias in aliases:
            if len(term) == len(alias) and term != alias:
                distance = sum(left != right for left, right in zip(term, alias))
                if distance == 1:
                    replacement = alias
                    break
        terms.append(replacement)
    return " ".join(terms).strip()


def normalize_research_task_type(route: ResearchRouting, task_type: str) -> ResearchRouting:
    normalized_task_type = str(task_type or "").strip()
    if not normalized_task_type:
        return route
    return {
        **route,
        "task_type": normalized_task_type,
        "search_query": normalize_search_query(
            route.get("search_query"),
            route.get("search_query") or "",
            task_type=normalized_task_type,
        ),
    }


def apply_route_intent_guards(
    query: str,
    route: ResearchRouting,
) -> ResearchRouting:
    intent_tags = merge_intent_tags(normalize_intent_tags(route.get("intent_tags")), derive_intent_tags(query))
    guarded_route: ResearchRouting = {
        **route,
        "intent_tags": intent_tags,
    }

    if route.get("task_type") == "story_explanation":
        return {
            **guarded_route,
            "use_db": True,
            "use_graph": False,
            "intent_tags": ["general"],
            "reason": "task_type_story_explanation",
            "search_query": normalize_search_query(
                guarded_route.get("search_query"),
                query,
                task_type="story_explanation",
            ),
        }

    if route_tags_have_graph_intent(intent_tags):
        guarded_route["use_graph"] = True

    if "boss_reward" in intent_tags and "time_sensitive" not in intent_tags:
        guarded_route["use_graph"] = True
        guarded_route["use_web"] = False
        guarded_route["reason"] = "boss_reward_graph_fact"

    return guarded_route


def is_structured_boss_reward_query(query: str) -> bool:
    intent_tags = derive_intent_tags(query)
    return "boss_reward" in intent_tags and "time_sensitive" not in intent_tags


def filter_documents_for_route(
    documents: list[RetrievedDocument],
    *,
    route: ResearchRouting,
) -> tuple[list[RetrievedDocument], dict[str, Any]]:
    desired_tags = set(normalize_intent_tags(route.get("intent_tags")))
    if not documents or desired_tags == {"general"}:
        return documents, {}

    filtered_documents = []
    rejected_count = 0
    unknown_count = 0
    for document in documents:
        document_tags = set(document_intent_tags(document))
        if not document_tags:
            unknown_count += 1
            filtered_documents.append(document)
            continue
        if document_tags.intersection(desired_tags):
            filtered_documents.append(document)
            continue
        rejected_count += 1

    result = {
        "reason": "route_intent_tags",
        "intent_tags": sorted(desired_tags),
        "before_count": len(documents),
        "after_count": len(filtered_documents),
        "rejected_count": rejected_count,
        "unknown_count": unknown_count,
        "dropped_all_irrelevant": not bool(filtered_documents),
    }

    return filtered_documents, result


def document_intent_tags(document: RetrievedDocument) -> list[ResearchIntent]:
    metadata = document.get("metadata", {}) or {}
    tags: list[ResearchIntent] = []

    category = str(metadata.get("category") or "").strip()
    tags.extend(DOCUMENT_CATEGORY_INTENT_TAGS.get(category, ()))

    retrieval_method = str(metadata.get("retrieval_method") or "").strip()
    for method_key, method_tags in RETRIEVAL_METHOD_INTENT_TAGS.items():
        if method_key in retrieval_method:
            tags.extend(method_tags)

    url = str(
        metadata.get("url")
        or metadata.get("source_url")
        or document.get("source")
        or ""
    )
    normalized_url = url.lower()
    for path_prefix, path_tags in WEB_PATH_INTENT_TAGS.items():
        if path_prefix in normalized_url:
            tags.extend(path_tags)

    title = str(metadata.get("title") or "").lower()
    for title_hint, title_tags in TITLE_INTENT_HINTS:
        if title_hint in title:
            tags.extend(title_tags)

    return normalize_intent_tags(tags) if tags else []


def retrieve_web_evidence(
    *,
    state: AgentState,
    search_query: str,
    route: ResearchRouting,
) -> tuple[list[RetrievedDocument], dict[str, Any]]:
    from src.rag.web_search import retrieve_for_agent_state

    web_state = retrieve_for_agent_state(
        question=search_query,
        character_context=state.get("character_profile") or state,
        official_only=route["official_only"],
        max_results=route["web_max_results"],
        max_contexts=route["web_max_contexts"],
    )
    return mark_web_documents(web_state.get("retrieved_docs", [])), web_state


def mark_web_documents(documents: list[RetrievedDocument]) -> list[RetrievedDocument]:
    marked: list[RetrievedDocument] = []
    for document in documents:
        metadata = dict(document.get("metadata", {}) or {})
        metadata.setdefault("retrieval_method", "web")
        marked.append({**document, "metadata": metadata})
    return marked


def web_fallback_reason(
    route: ResearchRouting,
    documents: list[RetrievedDocument],
    research_result: dict[str, Any],
) -> str:
    search_query = str(route.get("search_query") or "")
    if documents:
        if route["use_graph"] and not any(_is_graph_document(document) for document in documents):
            return "no_graph_evidence"
        if search_query and local_evidence_is_weak(documents, search_query):
            return "low_local_relevance"
        return ""

    if route["use_db"] or route["use_graph"]:
        if research_result.get("errors"):
            return "local_retrieval_failed"
        return "no_local_evidence"

    return ""


def local_evidence_is_weak(documents: list[RetrievedDocument], query: str) -> bool:
    content_terms = _query_content_terms(query)
    if not content_terms:
        return False
    return not any(
        _keyword_overlap_score(document, query, terms=content_terms) > 0
        for document in documents
    )


def run_research(
    state: AgentState,
    *,
    route: ResearchRouting | None = None,
    auto_create_embedding: bool = True,
    use_llm_parser: bool = True,
) -> AgentState:
    """멀티에이전트 그래프에서 호출할 Research Agent 본체입니다.

    입력 state에서 질문을 읽고, 필요한 RAG 검색을 실행한 뒤,
    다음 에이전트가 사용할 수 있도록 retrieved_docs와 context를 채워 반환합니다.
    """

    validate_agent_inputs("research", state)

    user_query = state["user_query"]
    effective_query = str(state.get("contextualized_query") or user_query).strip() or user_query

    parser_result: dict[str, Any] = {"used_llm": False, "fallback_used": False}
    if route is None:
        route, parser_result = build_research_route(
            effective_query,
            task_type=str(state.get("task_type") or ""),
            use_llm=use_llm_parser,
        )
    elif route is not None:
        route = normalize_research_task_type(route, str(state.get("task_type") or ""))
        route = apply_route_intent_guards(effective_query, route)

    docs: list[RetrievedDocument] = []
    search_query = route.get("search_query") or effective_query

    tool_results = dict(state.get("tool_results", {}))
    research_result: dict[str, Any] = {
        "route": route,
        "parser": parser_result,
        "db_success": False,
        "graph_success": False,
        "web_success": False,
        "web_fallback_used": False,
        "document_count": 0,
        "errors": [],
    }

    errors = list(state.get("errors", []))

    if route["use_db"]:
        try:
            from src.rag.db_search import run_db_search_rag

            db_response = run_db_search_rag(
                query=search_query,
                top_k=route["top_k"],
                mode=route["db_mode"],
                auto_create_embedding=auto_create_embedding,
                include_graph=False,
            )
            docs.extend(db_response.retrieved_docs)
            tool_results["db_search_rag"] = {
                "query": db_response.query,
                "search_query": search_query,
                "sources": db_response.sources,
                "route": route,
            }
            research_result["db_success"] = True
            research_result["db_document_count"] = len(db_response.retrieved_docs)
        except Exception as exc:
            message = f"research db_search_rag failed: {exc}"
            errors.append(message)
            research_result["errors"].append(message)
    if not route["use_db"]:
        research_result["db_skipped"] = True

    if route["use_graph"]:
        try:
            from src.rag.retriever import search_graph

            graph_results = search_graph(
                query=search_query,
                top_k=route["graph_top_k"],
                reliability_filter="ALL",
                intent_tags=route.get("intent_tags"),
            )
            graph_docs = [result.to_retrieved_document() for result in graph_results]
            docs.extend(graph_docs)
            tool_results["graph_search_rag"] = {
                "query": search_query,
                "sources": [result.to_source() for result in graph_results],
                "route": route,
            }
            research_result["graph_success"] = True
            research_result["graph_document_count"] = len(graph_docs)
        except Exception as exc:
            message = f"research graph_search_rag failed: {exc}"
            errors.append(message)
            research_result["errors"].append(message)
    if not route["use_graph"]:
        research_result["graph_skipped"] = True

    structured_boss_reward_query = (
        is_structured_boss_reward_query(user_query)
        or is_structured_boss_reward_query(effective_query)
        or is_structured_boss_reward_query(search_query)
    )
    if structured_boss_reward_query and any(_is_graph_document(document) for document in docs):
        docs = [document for document in docs if _is_graph_document(document)]
        route = apply_route_intent_guards(effective_query, route)
        research_result["structured_boss_reward_guard"] = True

    docs, intent_filter_result = filter_documents_for_route(docs, route=route)
    if intent_filter_result:
        research_result["intent_filter"] = intent_filter_result

    web_reason = "route_requested" if route["use_web"] else web_fallback_reason(
        route,
        docs,
        research_result,
    )

    if web_reason:
        try:
            web_docs, web_state = retrieve_web_evidence(
                state=state,
                search_query=search_query,
                route=route,
            )
            if web_reason == "low_local_relevance" and web_docs:
                research_result["weak_local_document_count"] = len(docs)
                docs = web_docs
            else:
                docs.extend(web_docs)
            tool_results.update(web_state.get("tool_results", {}))
            research_result["web_success"] = True
            research_result["web_document_count"] = len(web_docs)
            research_result["web_reason"] = web_reason
            research_result["web_fallback_used"] = web_reason != "route_requested"
        except Exception as exc:
            message = f"research web_search_rag failed: {exc}"
            errors.append(message)
            research_result["errors"].append(message)
            research_result["web_reason"] = web_reason
    if not web_reason:
        research_result["web_skipped"] = True
        research_result["web_skip_reason"] = "local_evidence_available"

    docs, intent_filter_result = filter_documents_for_route(docs, route=route)
    if intent_filter_result:
        research_result["intent_filter_after_web"] = intent_filter_result

    merged_docs = merge_retrieved_documents(docs, query=search_query, route=route)
    selected_evidence = build_selected_evidence(
        merged_docs,
        query=search_query,
        route=route,
    )
    evidence_summary = build_evidence_summary(
        search_query,
        route,
        selected_evidence,
    )
    evidence_summary["web_fallback_used"] = bool(research_result.get("web_fallback_used"))
    evidence_summary["web_reason"] = str(research_result.get("web_reason") or "")
    relevance_reason = build_overall_relevance_reason(selected_evidence)
    research_result["document_count"] = len(merged_docs)
    research_result["selected_evidence_count"] = len(selected_evidence)
    research_result["evidence_summary"] = evidence_summary
    research_result["has_context"] = bool(merged_docs)
    tool_results["research"] = research_result

    next_state: AgentState = {
        **state,
        "retrieved_docs": merged_docs,
        "selected_evidence": selected_evidence,
        "evidence_summary": evidence_summary,
        "relevance_reason": relevance_reason,
        "context": build_research_context(selected_evidence),
        "tool_results": tool_results,
    }
    if errors:
        next_state["errors"] = errors

    validate_agent_outputs("research", next_state)
    return next_state


def research_agent(state: AgentState, **kwargs: Any) -> AgentState:
    """LangGraph에 노드로 등록할 때 쓰기 좋은 별칭 함수입니다."""

    return run_research(state, **kwargs)


def merge_retrieved_documents(
    documents: list[RetrievedDocument],
    *,
    max_docs: int = 8,
    query: str = "",
    route: ResearchRouting | None = None,
) -> list[RetrievedDocument]:
    """검색 결과 문서를 중복 제거하고 점수가 높은 순서로 정렬합니다."""

    deduped: dict[str, RetrievedDocument] = {}
    for document in documents:
        key = _document_key(document)
        current = deduped.get(key)

        if current is None or _document_rank(document, query=query, route=route) > _document_rank(
            current,
            query=query,
            route=route,
        ):
            deduped[key] = document

    return sorted(
        deduped.values(),
        key=lambda document: _document_rank(document, query=query, route=route),
        reverse=True,
    )[:max_docs]


def build_selected_evidence(
    documents: list[RetrievedDocument],
    *,
    query: str,
    route: ResearchRouting | None,
    max_evidence: int = 5,
) -> list[RetrievedDocument]:
    selected: list[RetrievedDocument] = []
    for index, document in enumerate(documents[:max_evidence], start=1):
        metadata = dict(document.get("metadata", {}) or {})
        metadata["evidence_rank"] = index
        metadata["relevance_reason"] = build_relevance_reason(
            document,
            query=query,
            route=route,
        )
        selected.append({**document, "metadata": metadata})
    return selected


def build_evidence_summary(
    query: str,
    route: ResearchRouting | None,
    documents: list[RetrievedDocument],
) -> dict[str, Any]:
    retrieval_methods = []
    top_titles = []
    graph_count = 0
    web_count = 0
    db_count = 0

    for document in documents:
        metadata = document.get("metadata", {}) or {}
        retrieval_method = str(metadata.get("retrieval_method") or "unknown")
        title = str(metadata.get("title") or document.get("source") or "Untitled source")
        if retrieval_method not in retrieval_methods:
            retrieval_methods.append(retrieval_method)
        top_titles.append(title)
        is_graph_document = _is_graph_document(document)
        is_web_document = _is_web_document(document)
        if is_graph_document:
            graph_count += 1
        elif is_web_document:
            web_count += 1
        elif not is_graph_document and not is_web_document:
            db_count += 1

    return {
        "query": query,
        "search_query": route.get("search_query", query) if route else query,
        "selected_count": len(documents),
        "graph_evidence_count": graph_count,
        "web_evidence_count": web_count,
        "db_evidence_count": db_count,
        "retrieval_methods": retrieval_methods,
        "top_titles": top_titles,
    }


def build_overall_relevance_reason(documents: list[RetrievedDocument]) -> str:
    if not documents:
        return "no_evidence_selected"
    metadata = documents[0].get("metadata", {}) or {}
    return str(metadata.get("relevance_reason") or "selected_by_research_rank")


def build_relevance_reason(
    document: RetrievedDocument,
    *,
    query: str,
    route: ResearchRouting | None,
) -> str:
    metadata = document.get("metadata", {}) or {}
    retrieval_method = str(metadata.get("retrieval_method") or "unknown")
    if _is_graph_requirement_document(document) and _query_mentions_requirement(query):
        return "graph_requirement_priority_for_requirement_query"
    if _is_graph_document(document):
        return "graph_fact_matches_structured_query"
    if _is_snippet_fallback_document(document):
        return "web_snippet_fallback_low_confidence"
    if route and route.get("use_web") and _is_web_document(document):
        return "web_source_selected_for_time_sensitive_query"
    if _keyword_overlap_score(document, query) > 0:
        return "content_matches_query_terms"
    return f"selected_by_{retrieval_method}_rank"


def build_research_context(documents: list[RetrievedDocument]) -> str:
    """Final Answer Agent가 읽을 수 있도록 문서 목록을 문자열로 바꿉니다."""

    blocks = []
    for index, document in enumerate(documents, start=1):
        metadata = document.get("metadata", {})
        title = metadata.get("title") or "Untitled source"
        source_url = (
            metadata.get("source_url")
            or metadata.get("url")
            or document.get("source")
            or "unknown"
        )
        reliability = metadata.get("reliability") or metadata.get("trust_level") or "unknown"
        retrieval_method = metadata.get("retrieval_method") or "unknown"
        freshness = metadata.get("freshness")
        content_source = metadata.get("content_source")
        fetch_status = metadata.get("fetch_status")
        relevance_reason = metadata.get("relevance_reason")

        header_lines = [

            f"[{index}] {title}",
            f"source: {source_url}",
            f"reliability: {reliability}",
            f"retrieval_method: {retrieval_method}",
            f"score: {float(document.get('score') or 0):.4f}",
        ]
        if freshness:
            header_lines.append(f"freshness: {freshness}")
        if content_source:
            header_lines.append(f"content_source: {content_source}")
        if fetch_status:
            header_lines.append(f"fetch_status: {fetch_status}")
        if relevance_reason:
            header_lines.append(f"relevance_reason: {relevance_reason}")
        blocks.append("\n".join([*header_lines, str(document.get("page_content", ""))]))
    return "\n\n".join(blocks)


def _document_key(document: RetrievedDocument) -> str:
    """중복 제거에 사용할 문서 고유값을 고릅니다."""

    metadata = document.get("metadata", {})
    for key in ("chunk_id", "document_id", "source_url", "url"):
        value = metadata.get(key)
        if value:
            return str(value)
    return str(document.get("source") or document.get("page_content") or id(document))


def _document_rank(
    document: RetrievedDocument,
    *,
    query: str = "",
    route: ResearchRouting | None = None,
) -> tuple[int, int, int, int, float]:
    """문서를 정렬하기 위한 점수를 만듭니다.

    Python tuple 비교는 앞의 값부터 비교합니다.
    즉 라우팅 적합도 -> 본문 출처 -> 신뢰도 -> 최신성 -> 검색 점수 순서로 중요하게 봅니다.
    """

    metadata = document.get("metadata", {})
    reliability = str(metadata.get("reliability") or metadata.get("trust_level") or "")
    freshness = str(metadata.get("freshness") or "")
    return (
        _route_relevance_rank(document, query=query, route=route),
        _content_source_rank(document),
        _reliability_rank(reliability),
        _freshness_rank(freshness),
        float(document.get("score") or 0),
    )


def _route_relevance_rank(
    document: RetrievedDocument,
    *,
    query: str,
    route: ResearchRouting | None,
) -> int:
    if route:
        desired_tags = set(normalize_intent_tags(route.get("intent_tags")))
        document_tags = set(document_intent_tags(document))
        if document_tags and document_tags.intersection(desired_tags):
            return 6
        if document_tags:
            return 0

    if route and route.get("use_graph") and _is_graph_document(document):
        if _query_mentions_requirement(query) and _is_graph_requirement_document(document):
            return 5
        if _is_graph_requirement_document(document):
            return 4
        return 3

    if route and route.get("use_web") and _is_web_document(document):
        return 2

    return min(1, _keyword_overlap_score(document, query))


def _content_source_rank(document: RetrievedDocument) -> int:
    metadata = document.get("metadata", {}) or {}
    content_source = str(metadata.get("content_source") or "")
    if content_source == "tavily_snippet_fallback":
        return 0
    if content_source in {"fetched_page", "tavily_raw_content"}:
        return 2
    return 1


def _is_snippet_fallback_document(document: RetrievedDocument) -> bool:
    metadata = document.get("metadata", {}) or {}
    return str(metadata.get("content_source") or "") == "tavily_snippet_fallback"


def _keyword_overlap_score(
    document: RetrievedDocument,
    query: str,
    *,
    terms: list[str] | None = None,
) -> int:
    terms = terms if terms is not None else _query_content_terms(query)
    if not terms:
        return 0

    metadata = document.get("metadata", {}) or {}
    haystack = " ".join(
        [
            str(metadata.get("title") or ""),
            str(metadata.get("entity_type") or ""),
            str(document.get("page_content") or ""),
        ]
    ).lower()
    return sum(1 for term in terms if term in haystack)


def _query_content_terms(query: str) -> list[str]:
    terms: list[str] = []
    for raw_term in re.split(r"[\s,?!.:;()\[\]{}\"'`~]+", str(query or "")):
        term = _normalize_query_term(raw_term)
        if len(term) < 2 or term in QUERY_BOILERPLATE_TERMS or term in terms:
            continue
        terms.append(term)
    return terms


def _normalize_query_term(raw_term: str) -> str:
    term = re.sub(r"^[^\w가-힣]+|[^\w가-힣]+$", "", str(raw_term or "").strip().lower())
    if not term:
        return ""
    if term in QUERY_BOILERPLATE_TERMS:
        return ""
    for suffix in KOREAN_PARTICLE_SUFFIXES:
        if len(term) > len(suffix) + 1 and term.endswith(suffix):
            candidate = term[: -len(suffix)]
            if candidate and candidate not in QUERY_BOILERPLATE_TERMS:
                return candidate
    return term


def _query_mentions_requirement(query: str) -> bool:
    normalized_query = str(query or "").lower()
    return any(keyword in normalized_query for keyword in REQUIREMENT_KEYWORDS)


def _is_graph_requirement_document(document: RetrievedDocument) -> bool:
    metadata = document.get("metadata", {}) or {}
    retrieval_method = str(metadata.get("retrieval_method") or "")
    entity_type = str(metadata.get("entity_type") or "")
    return "graph_requirement" in retrieval_method or "StatRequirement" in entity_type


def _is_graph_document(document: RetrievedDocument) -> bool:
    metadata = document.get("metadata", {}) or {}
    retrieval_method = str(metadata.get("retrieval_method") or "")
    source = str(document.get("source") or "")
    return "graph" in retrieval_method or source.startswith("graph::")


def _is_web_document(document: RetrievedDocument) -> bool:
    metadata = document.get("metadata", {}) or {}
    retrieval_method = str(metadata.get("retrieval_method") or "")
    source = str(document.get("source") or "")
    url = str(metadata.get("url") or metadata.get("source_url") or "")
    return "web" in retrieval_method or source.startswith("http") or url.startswith("http")


def _reliability_rank(value: str) -> int:
    """문자열 신뢰도를 숫자 점수로 바꿉니다."""

    return {
        "S": 5,
        "A": 4,
        "HIGH": 4,
        "graph_seed": 3,
        "B": 3,
        "MEDIUM": 2,
        "C": 1,
        "LOW": 1,
    }.get(value, 0)


def _freshness_rank(value: str) -> int:
    """문자열 최신성을 숫자 점수로 바꿉니다."""

    return {
        "HIGH": 3,
        "MEDIUM": 2,
        "UNKNOWN": 1,
        "LOW": 0,
    }.get(value, 0)
