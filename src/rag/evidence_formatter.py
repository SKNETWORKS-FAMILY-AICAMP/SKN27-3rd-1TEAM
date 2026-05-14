from __future__ import annotations

from common.state import AgentState, RetrievedDocument


MAX_EVIDENCE_COUNT = 6
MAX_SNIPPET_CHARS = 300

RAW_CONTEXT_MARKERS = (
    "boss_properties:",
    "reward_properties:",
    "requirement_properties:",
    "retrieval_method:",
    "relevance_reason:",
    "source: graph::",
    "Graph boss",
)

RAW_FIELD_NAMES = {
    "source",
    "reliability",
    "retrieval_method",
    "score",
    "freshness",
    "relevance_reason",
    "boss_properties",
    "reward_properties",
    "requirement_properties",
}


def format_evidence_for_answer(state: AgentState) -> AgentState:
    documents = list(state.get("selected_evidence") or state.get("retrieved_docs") or [])
    original_context = str(state.get("context") or "")
    formatted_context = build_answer_context(
        question=str(state.get("contextualized_query") or state.get("user_query") or ""),
        documents=documents,
        original_context=original_context,
    )

    tool_results = dict(state.get("tool_results", {}) or {})
    tool_results["evidence_formatter"] = {
        "document_count": len(documents),
        "raw_context_detected": contains_raw_context(original_context),
        "context_rewritten": formatted_context != original_context,
    }

    return {
        **state,
        "context": formatted_context,
        "tool_results": tool_results,
    }


def build_answer_context(
    *,
    question: str,
    documents: list[RetrievedDocument],
    original_context: str,
) -> str:
    if not documents:
        return clean_context_snippet(original_context)

    lines = ["사용자 답변에 사용할 정리된 근거입니다."]
    mismatch_notice = build_query_mismatch_notice(question, documents)
    if mismatch_notice:
        lines.extend(["", mismatch_notice])

    lines.append("")
    for document in documents[:MAX_EVIDENCE_COUNT]:
        lines.append(format_document_summary(document))

    return "\n".join(line for line in lines if line is not None).strip()


def build_query_mismatch_notice(
    question: str,
    documents: list[RetrievedDocument],
) -> str:
    normalized_question = str(question or "").replace(" ", "").lower()
    if "진힐라" not in normalized_question:
        return ""

    evidence_text = " ".join(
        str(document.get("page_content") or "")
        for document in documents
    ).replace(" ", "").lower()
    if "진힐라" in evidence_text or "verushilla" in evidence_text:
        return ""

    return (
        "주의: 선택된 근거는 '진 힐라'가 아니라 '힐라/Hilla' 관련 정보입니다. "
        "이 근거만으로는 진 힐라 보상이라고 단정할 수 없습니다."
    )


def format_document_summary(document: RetrievedDocument) -> str:
    metadata = document.get("metadata", {}) or {}
    retrieval_method = str(metadata.get("retrieval_method") or "")
    fields = parse_context_fields(str(document.get("page_content") or ""))

    if "graph_reward" in retrieval_method:
        return format_graph_reward_summary(fields)
    if "graph_requirement" in retrieval_method:
        return format_graph_requirement_summary(fields)

    title = str(metadata.get("title") or document.get("source") or "근거")
    snippet = clean_context_snippet(str(document.get("page_content") or ""))
    source_note = format_content_source_note(metadata)
    return f"- {title}{source_note}: {snippet}"


def format_content_source_note(metadata: dict) -> str:
    content_source = str(metadata.get("content_source") or "")
    fetch_status = str(metadata.get("fetch_status") or "")
    if content_source == "tavily_snippet_fallback":
        return f" (검색 스니펫 기반, fetch_status={fetch_status or 'unknown'})"
    if content_source == "tavily_raw_content":
        return " (Tavily raw content)"
    if content_source == "fetched_page":
        return " (실제 페이지 본문)"
    return ""


def format_graph_reward_summary(fields: dict[str, str]) -> str:
    boss = fields.get("Boss") or "대상 보스"
    difficulty = fields.get("difficulty")
    reward = fields.get("Reward") or "확인된 보상"
    description = fields.get("description")
    reward_type = fields.get("reward_type")
    value_type = fields.get("value_type")

    boss_label = f"{boss}({difficulty})" if difficulty else boss
    details = [item for item in (description, reward_type, value_type) if item]
    detail_text = f" - {', '.join(details)}" if details else ""
    return f"- {boss_label}: {reward}{detail_text}"


def format_graph_requirement_summary(fields: dict[str, str]) -> str:
    boss = fields.get("Boss") or "대상 보스"
    difficulty = fields.get("difficulty")
    boss_label = f"{boss}({difficulty})" if difficulty else boss
    stat_parts = []

    for label, key in (
        ("요구 레벨", "required_level"),
        ("주스탯", "main_stat"),
        ("아케인포스", "arcane_force"),
        ("어센틱포스", "authentic_force"),
        ("보공", "boss_damage"),
        ("방무", "ignore_def"),
    ):
        value = fields.get(key)
        if value:
            stat_parts.append(f"{label} {value}")

    detail = ", ".join(stat_parts) if stat_parts else "요구 조건 근거가 확인되었습니다"
    return f"- {boss_label}: {detail}"


def parse_context_fields(content: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for line in content.splitlines():
        if ": " not in line:
            continue

        key, value = line.split(": ", 1)
        key = key.strip()
        if key in RAW_FIELD_NAMES or key.endswith("_properties"):
            continue

        value = value.strip()
        if value:
            fields[key] = value

    return fields


def clean_context_snippet(content: str) -> str:
    clean_lines = []
    for line in str(content or "").splitlines():
        stripped = line.strip()
        if not stripped or contains_raw_context(stripped):
            continue
        if ": " in stripped and stripped.split(": ", 1)[0] in RAW_FIELD_NAMES:
            continue
        clean_lines.append(stripped)

    snippet = " ".join(clean_lines).strip()
    if len(snippet) > MAX_SNIPPET_CHARS:
        return snippet[:MAX_SNIPPET_CHARS].rstrip() + "..."
    return snippet or "근거 내용을 요약할 수 없습니다."


def contains_raw_context(text: str) -> bool:
    return any(marker in str(text or "") for marker in RAW_CONTEXT_MARKERS)
