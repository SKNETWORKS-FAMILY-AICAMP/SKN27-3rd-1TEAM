from __future__ import annotations

import json
import re
from typing import Any, Literal, TypedDict

from common.state import AgentState, RetrievedDocument
from common.validator import validate_agent_inputs, validate_agent_outputs


ResearchMode = Literal["auto", "text", "vector", "hybrid"]
MAX_CONTEXT_DOC_CHARS = 1200
MAX_RESEARCH_CONTEXT_CHARS = 5000


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
- reason: short snake_case string

Rules:
- use_db should usually be true for MapleStory knowledge questions.
- use_graph should be true for structured facts such as bosses, rewards, equipment sets, stats, requirements, drops, jobs, or content relationships.
- use_web should be true for latest/current/today/recent notices, patches, events, cash shop, test world, market prices, or time-sensitive questions.
- official_only should be true for official notices, patches, events, and current factual claims.
- Prefer db_mode hybrid unless the query is a direct keyword lookup where text is enough.
- Do not invent facts or answer the user.
""".strip()

GRAPH_KEYWORDS = (
    "boss",
    "\ubcf4\uc2a4",
    "\uc2a4\uc6b0",
    "\ub370\ubbf8\uc548",
    "\ub8e8\uc2dc\ub4dc",
    "\uc70c",
    "\ub354\uc2a4\ud06c",
    "\ub4c4\ucf08",
    "\uc9c4\ud790\ub77c",
    "검은 마법사",
    "\uac80\uc740\ub9c8\ubc95\uc0ac",
    "\uc138\ub80c",
    "\uce7c\ub85c\uc2a4",
    "\uce74\ub9c1",
    "\ub9bc\ubcf4",
    "\ubc1c\ub4dc\ub9ad\uc2a4",
    "\uc7a5\ube44",
    "\uc138\ud2b8",
    "\uc138\ud2b8\ud6a8\uacfc",
    "\ubcf4\uc0c1",
    "\ub4dc\ub86d",
    "\uc694\uad6c",
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
    "\ubcf4\uc0c1",
    "\ud14c\uc12d",
    "\ud14c\uc2a4\ud2b8\uc6d4\ub4dc",
    "\uce90\uc2dc\uc0f5",
)


def classify_research_route(query: str) -> ResearchRouting:
    """질문을 보고 DB/Graph/Web 중 어떤 검색을 쓸지 고릅니다.

    여기서는 LLM에게 판단을 맡기지 않고 키워드로만 판단합니다.
    """

    normalized_query = query.lower()

    needs_graph = any(keyword.lower() in normalized_query for keyword in GRAPH_KEYWORDS)

    needs_web = any(keyword.lower() in normalized_query for keyword in WEB_KEYWORDS)

    if needs_web and needs_graph:
        reason = "latest_structured_fact"
    elif needs_web:
        reason = "latest_or_notice"
    elif needs_graph:
        reason = "structured_fact"
    else:
        reason = "document_research"

    return {
        "use_db": True,
        "use_graph": needs_graph,
        "use_web": needs_web,
        "db_mode": "text",
        "top_k": 5,
        "graph_top_k": 3,
        "web_max_results": 5,
        "web_max_contexts": 5,
        "official_only": True,
        "reason": reason,
        "search_query": query,
        "parser_source": "keyword",
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


def build_research_route(query: str, *, use_llm: bool = True) -> tuple[ResearchRouting, dict[str, Any]]:
    """Return a research route plus parser metadata for tool_results."""

    fallback_route = classify_research_route(query)
    if not use_llm:
        return fallback_route, {"used_llm": False, "fallback_used": False}

    try:
        route = parse_research_route_with_llm(query)
    except Exception as exc:
        return fallback_route, {
            "used_llm": True,
            "fallback_used": True,
            "error": str(exc),
        }

    route["use_graph"] = route["use_graph"] or fallback_route["use_graph"]
    route["use_web"] = route["use_web"] or fallback_route["use_web"]
    if route["use_web"]:
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


def normalize_research_route_parse(query: str, parsed: dict[str, Any]) -> ResearchRouting:
    fallback = classify_research_route(query)
    db_mode = str(parsed.get("db_mode") or fallback["db_mode"]).lower()
    if db_mode not in {"auto", "text", "vector", "hybrid"}:
        db_mode = fallback["db_mode"]

    use_graph = coerce_bool(parsed.get("use_graph"), fallback["use_graph"])
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
        "search_query": normalize_search_query(parsed.get("search_query"), query),
        "parser_source": "llm",
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


def normalize_search_query(value: Any, default: str) -> str:
    query = str(value or "").strip()
    return query or default


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

    parser_result: dict[str, Any] = {"used_llm": False, "fallback_used": False}
    if route is None:
        route, parser_result = build_research_route(
            state["user_query"],
            use_llm=use_llm_parser,
        )

    docs: list[RetrievedDocument] = []
    search_query = route.get("search_query") or state["user_query"]

    tool_results = dict(state.get("tool_results", {}))
    research_result: dict[str, Any] = {
        "route": route,
        "parser": parser_result,
        "db_success": False,
        "web_success": False,
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
                include_graph=route["use_graph"],
                graph_top_k=route["graph_top_k"],
            )
            docs.extend(db_response.retrieved_docs)
            tool_results["db_search_rag"] = {
                "query": db_response.query,
                "sources": db_response.sources,
                "route": route,
            }
            research_result["db_success"] = True
            research_result["db_document_count"] = len(db_response.retrieved_docs)
        except Exception as exc:
            message = f"research db_search_rag failed: {exc}"
            errors.append(message)
            research_result["errors"].append(message)
    else:
        research_result["db_skipped"] = True

    if route["use_web"]:
        try:
            from src.rag.web_search import retrieve_for_agent_state

            web_state = retrieve_for_agent_state(
                question=search_query,
                character_context=state.get("character_profile") or state,
                official_only=route["official_only"],
                max_results=route["web_max_results"],
                max_contexts=route["web_max_contexts"],
            )
            docs.extend(web_state.get("retrieved_docs", []))
            tool_results.update(web_state.get("tool_results", {}))
            research_result["web_success"] = True
            research_result["web_document_count"] = len(web_state.get("retrieved_docs", []))
        except Exception as exc:
            message = f"research web_search_rag failed: {exc}"
            errors.append(message)
            research_result["errors"].append(message)
    else:
        research_result["web_skipped"] = True

    merged_docs = merge_retrieved_documents(docs)
    research_result["document_count"] = len(merged_docs)
    research_result["has_context"] = bool(merged_docs)
    tool_results["research"] = research_result

    next_state: AgentState = {
        **state,
        "retrieved_docs": merged_docs,
        "context": build_research_context(merged_docs),
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
) -> list[RetrievedDocument]:
    """검색 결과 문서를 중복 제거하고 점수가 높은 순서로 정렬합니다."""

    deduped: dict[str, RetrievedDocument] = {}
    for document in documents:
        key = _document_key(document)
        current = deduped.get(key)

        if current is None or _document_rank(document) > _document_rank(current):
            deduped[key] = document

    return sorted(deduped.values(), key=_document_rank, reverse=True)[:max_docs]


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
        reliability = normalize_research_reliability(
            metadata.get("reliability") or metadata.get("trust_level")
        )
        retrieval_method = metadata.get("retrieval_method") or "unknown"
        freshness = metadata.get("freshness")

        header_lines = [

            f"[{index}] {title}",
            f"source: {source_url}",
            f"reliability: {reliability}",
            f"retrieval_method: {retrieval_method}",
            f"score: {float(document.get('score') or 0):.4f}",
        ]
        if freshness:
            header_lines.append(f"freshness: {freshness}")
        content = clip_research_text(
            str(document.get("page_content", "")),
            MAX_CONTEXT_DOC_CHARS,
        )
        blocks.append("\n".join([*header_lines, content]))
    return clip_research_text("\n\n".join(blocks), MAX_RESEARCH_CONTEXT_CHARS)


def normalize_research_reliability(value: Any) -> str:
    text = str(value or "LOW").strip().upper()
    return {
        "A": "HIGH",
        "B": "MEDIUM",
        "C": "LOW",
        "HIGH": "HIGH",
        "MEDIUM": "MEDIUM",
        "LOW": "LOW",
        "GRAPH_SEED": "MEDIUM",
        "DRAFT": "LOW",
        "PROJECT_DRAFT_RULE_NEEDS_REVIEW": "LOW",
    }.get(text, "LOW")


def clip_research_text(text: str, max_chars: int) -> str:
    text = str(text or "").strip()
    if len(text) <= max_chars:
        return text
    return f"{text[:max_chars].rstrip()}\n...[truncated]"


def _document_key(document: RetrievedDocument) -> str:
    """중복 제거에 사용할 문서 고유값을 고릅니다."""

    metadata = document.get("metadata", {})
    for key in ("chunk_id", "document_id", "source_url", "url"):
        value = metadata.get(key)
        if value:
            return str(value)
    return str(document.get("source") or document.get("page_content") or id(document))


def _document_rank(document: RetrievedDocument) -> tuple[int, int, float]:
    """문서를 정렬하기 위한 점수를 만듭니다.

    Python tuple 비교는 앞의 값부터 비교합니다.
    즉 신뢰도 -> 최신성 -> 검색 점수 순서로 중요하게 봅니다.
    """

    metadata = document.get("metadata", {})
    reliability = str(metadata.get("reliability") or metadata.get("trust_level") or "")
    freshness = str(metadata.get("freshness") or "")
    return (
        _reliability_rank(reliability),
        _freshness_rank(freshness),
        float(document.get("score") or 0),
    )


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
