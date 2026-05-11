from __future__ import annotations

from typing import Any, TypedDict

from common.state import AgentState, RetrievedDocument
from src.agents.research import run_research


class ChatServiceResponse(TypedDict, total=False):
    answer: str
    context: str
    retrieved_docs: list[RetrievedDocument]
    sources: list[dict[str, Any]]
    tool_results: dict[str, Any]
    errors: list[str]
    state: AgentState


def run_research_chat(
    message: str,
    *,
    character_name: str | None = None,
    world_name: str | None = None,
    include_state: bool = False,
    auto_create_embedding: bool = False,
) -> ChatServiceResponse:
    """Service entry point for chat requests that need the Research Agent."""

    normalized_message = message.strip()
    if not normalized_message:
        raise ValueError("message is required")

    state: AgentState = {"user_query": normalized_message}
    if character_name:
        state["character_name"] = character_name
    if world_name:
        state["world_name"] = world_name

    researched_state = run_research(
        state,
        auto_create_embedding=auto_create_embedding,
    )
    response = build_chat_response(researched_state)
    if include_state:
        response["state"] = researched_state
    return response


def build_chat_response(state: AgentState) -> ChatServiceResponse:
    """Convert Research Agent state into a service-friendly chat payload."""

    retrieved_docs = state.get("retrieved_docs", [])
    response: ChatServiceResponse = {
        "answer": _research_answer(state),
        "context": state.get("context", ""),
        "retrieved_docs": retrieved_docs,
        "sources": [_source_from_document(document) for document in retrieved_docs],
        "tool_results": state.get("tool_results", {}),
    }
    if state.get("errors"):
        response["errors"] = state["errors"]
    return response


def _research_answer(state: AgentState) -> str:
    query = state.get("user_query", "")
    docs = state.get("retrieved_docs", [])
    if not docs:
        return (
            "No supporting evidence was found. Check DB/Web search configuration "
            "and loaded data, then try again."
        )

    lines = [f"Found {len(docs)} supporting documents for '{query}'."]
    for index, document in enumerate(docs[:3], start=1):
        metadata = document.get("metadata", {})
        title = metadata.get("title") or "Untitled source"
        content = " ".join(str(document.get("page_content", "")).split())
        preview = content[:180]
        lines.append(f"[{index}] {title}: {preview}")
    return "\n".join(lines)


def _source_from_document(document: RetrievedDocument) -> dict[str, Any]:
    metadata = document.get("metadata", {})
    return {
        "title": metadata.get("title") or "Untitled source",
        "url": metadata.get("source_url") or metadata.get("url") or document.get("source"),
        "reliability": metadata.get("reliability") or metadata.get("trust_level"),
        "retrieval_method": metadata.get("retrieval_method"),
        "score": document.get("score"),
    }
