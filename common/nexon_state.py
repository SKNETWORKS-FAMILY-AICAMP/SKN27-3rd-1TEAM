from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from common.state import AgentState, JsonValue, RetrievedDocument


NEXON_API_TOOL_KEY = "nexon_api"


def has_nexon_character_data(state: AgentState) -> bool:
    """Return whether normalized character profile/stat data is already present."""

    return bool(state.get("character_profile") and state.get("character_stats"))


def nexon_api_attempted(state: AgentState) -> bool:
    """Return whether any Nexon API branch has already recorded a tool result."""

    return bool((state.get("tool_results") or {}).get(NEXON_API_TOOL_KEY))


def is_nexon_api_document(document: Any) -> bool:
    if not isinstance(document, dict):
        return False
    metadata = document.get("metadata") if isinstance(document.get("metadata"), dict) else {}
    return (
        document.get("source") == NEXON_API_TOOL_KEY
        or metadata.get("source") == NEXON_API_TOOL_KEY
    )


def filter_nexon_api_documents(documents: Iterable[Any]) -> list[RetrievedDocument]:
    return [
        document
        for document in documents
        if isinstance(document, dict) and is_nexon_api_document(document)
    ]


def has_external_research_evidence(state: AgentState) -> bool:
    """Return whether state has non-Nexon research evidence.

    Nexon Open API character data is useful context, but it should not satisfy
    questions that also need boss requirements, rewards, or other game facts.
    """

    documents = [
        document
        for document in [
            *list(state.get("retrieved_docs") or []),
            *list(state.get("selected_evidence") or []),
        ]
        if isinstance(document, dict)
    ]
    if any(not is_nexon_api_document(document) for document in documents):
        return True

    tool_results = state.get("tool_results") or {}
    research_result = tool_results.get("research") if isinstance(tool_results, dict) else {}
    if isinstance(research_result, dict):
        research_documents = [
            *list(research_result.get("docs") or []),
            *list(research_result.get("retrieved_docs") or []),
            *list(research_result.get("selected_evidence") or []),
        ]
        if any(
            isinstance(document, dict) and not is_nexon_api_document(document)
            for document in research_documents
        ):
            return True
        if (
            research_result.get("web_success")
            or research_result.get("web_fallback_used")
            or research_result.get("graph_success")
            or research_result.get("db_success")
        ):
            return True

    context = str(state.get("context") or "").strip()
    return bool(context and not documents and not nexon_api_attempted(state))


def requires_nexon_api_task(state: AgentState) -> bool:
    return bool(state.get("requires_api") or state.get("api_task_type"))


def read_field(value: Any, key: str, default: Any = "") -> Any:
    if isinstance(value, dict):
        return value.get(key, default)
    return getattr(value, key, default)


def make_nexon_document(
    *,
    content: str,
    metadata: dict[str, JsonValue] | None = None,
    score: float = 1.0,
) -> RetrievedDocument:
    return {
        "page_content": content,
        "source": NEXON_API_TOOL_KEY,
        "score": score,
        "metadata": {
            "source": NEXON_API_TOOL_KEY,
            **(metadata or {}),
        },
    }


def attach_nexon_evidence(
    state: AgentState,
    *,
    content: str,
    document: RetrievedDocument,
    summary: str | None = None,
    reliability: str = "HIGH",
    relevance_reason: str = "nexon_api",
    replace_sources: Iterable[str] = (NEXON_API_TOOL_KEY,),
) -> AgentState:
    """Attach a Nexon API document to shared RAG/evidence state fields."""

    existing_context = str(state.get("context") or "").strip()
    next_context = (
        f"{existing_context}\n\n{content}"
        if existing_context and content and content not in existing_context
        else content or existing_context
    )
    replace_source_set = set(replace_sources)
    retrieved_docs = [
        doc
        for doc in list(state.get("retrieved_docs") or [])
        if not (
            isinstance(doc, dict)
            and (
                doc.get("source") in replace_source_set
                or (doc.get("metadata") or {}).get("source") in replace_source_set
            )
        )
    ]
    retrieved_docs.append(document)

    return {
        **state,
        "context": next_context,
        "retrieved_docs": retrieved_docs,
        "selected_evidence": [
            *list(state.get("selected_evidence") or []),
            document,
        ],
        "evidence_summary": {
            **dict(state.get("evidence_summary") or {}),
            NEXON_API_TOOL_KEY: {
                "source": NEXON_API_TOOL_KEY,
                "reliability": reliability,
                "summary": summary if summary is not None else content,
            },
        },
        "relevance_reason": state.get("relevance_reason") or relevance_reason,
    }
