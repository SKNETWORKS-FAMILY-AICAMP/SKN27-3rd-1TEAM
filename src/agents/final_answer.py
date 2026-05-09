from __future__ import annotations

from typing import Any

from common.get_model import get_llm, has_llm_config
from common.prompt import master_prompt
from common.state import AgentState, JsonValue, RetrievedDocument
from common.validator import (
    validate_agent_inputs,
    validate_agent_outputs,
    validate_state_keys,
)


DEFAULT_CONFIDENCE = 0.5
HIGH_CONFIDENCE = 0.8
LOW_CONFIDENCE = 0.3
RELIABILITY_ORDER = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
MAX_SOURCE_COUNT = 5


def run_final_answer_agent(state: AgentState) -> AgentState:
    """Build the final answer fields required by common.state."""

    validate_state_keys(state)
    validate_agent_inputs("final_answer", state)

    sources = collect_sources(state)
    draft_answer = build_draft_answer(state, sources)
    final_answer = generate_final_answer(state, draft_answer)

    next_state: AgentState = {
        **state,
        "draft_answer": draft_answer,
        "final_answer": final_answer,
        "validation_passed": bool(final_answer),
        "confidence_score": calculate_confidence(state, sources),
    }
    validate_agent_outputs("final_answer", next_state)
    return next_state


def build_chat_response(state: AgentState) -> dict[str, JsonValue]:
    """Return an OpenAPI ApiResponseChat-compatible dictionary."""

    final_answer = state.get("final_answer", "")
    confidence = state.get("confidence_score", DEFAULT_CONFIDENCE)

    return {
        "success": bool(final_answer),
        "message": "챗봇 응답 메시지 반환" if final_answer else "답변 생성에 실패했습니다.",
        "confidence": confidence,
        "data": {
            "response": final_answer,
            "sources": collect_sources(state),
            "steps": build_steps(state),
        },
    }


def build_draft_answer(
    state: AgentState,
    sources: list[dict[str, JsonValue]],
) -> str:
    question = state["user_query"]
    context = state["context"].strip()
    recommendations = format_recommendations(state)

    if not context:
        return (
            "현재 제공된 근거만으로는 확정 답변을 만들기 어렵습니다. "
            "공식 문서 또는 추가 분석 결과가 필요합니다."
        )

    answer_parts = [
        f"질문: {question}",
        "",
        context,
    ]

    if recommendations:
        answer_parts.extend(["", "추천:", recommendations])

    if sources:
        answer_parts.extend(["", "근거 출처를 함께 확인했습니다."])

    return "\n".join(answer_parts).strip()


def finalize_answer(draft_answer: str) -> str:
    if not draft_answer:
        return ""

    return draft_answer


def generate_final_answer(state: AgentState, draft_answer: str) -> str:
    if not should_use_llm():
        return finalize_answer(draft_answer)

    prompt = build_final_answer_prompt(state, draft_answer)
    response = get_llm().invoke(prompt)
    content = getattr(response, "content", response)
    if isinstance(content, list):
        content = "\n".join(str(item) for item in content)

    return str(content).strip() or finalize_answer(draft_answer)


def should_use_llm() -> bool:
    return has_llm_config()


def build_final_answer_prompt(state: AgentState, draft_answer: str = "") -> str:
    return "\n".join(
        [
            master_prompt.strip(),
            "",
            "당신은 메이플스토리 RAG 멀티 에이전트 챗봇의 Final Answer Agent입니다.",
            "제공된 AgentState와 근거 context만 사용하여 한국어로 답변하세요.",
            "state에 없는 정보는 추측하지 말고, 근거가 부족하면 한계를 명시하세요.",
            "",
            f"사용자 질문: {state.get('user_query', '')}",
            f"근거 context: {state.get('context', '')}",
            f"추천 액션: {format_recommendations(state)}",
            f"초안 답변: {draft_answer}",
        ]
    ).strip()


def format_recommendations(state: AgentState) -> str:
    actions = state.get("recommended_actions", [])
    if not actions:
        return ""

    sorted_actions = sorted(actions, key=lambda action: action.priority)
    return "\n".join(
        f"{action.priority}. {action.category} - {action.target}: {action.description}"
        for action in sorted_actions
    )


def collect_sources(state: AgentState) -> list[dict[str, JsonValue]]:
    documents = state.get("retrieved_docs", [])
    unique_sources: dict[str, dict[str, JsonValue]] = {}

    for document in documents:
        source = source_from_document(document)
        key = str(source.get("url") or source.get("title") or "")
        if not key or key in unique_sources:
            continue
        unique_sources[key] = source

    return sorted(
        unique_sources.values(),
        key=lambda source: RELIABILITY_ORDER.get(str(source.get("reliability")), 99),
    )[:MAX_SOURCE_COUNT]


def source_from_document(document: RetrievedDocument) -> dict[str, JsonValue]:
    metadata = document.get("metadata", {})
    title = metadata.get("title") or document.get("source") or "출처 미상"
    url = metadata.get("url") or metadata.get("source") or document.get("source") or ""
    reliability = normalize_reliability(metadata.get("reliability"))

    return {
        "title": str(title),
        "url": str(url),
        "reliability": reliability,
    }


def normalize_reliability(value: Any) -> str:
    reliability = str(value or "LOW").upper()
    if reliability not in RELIABILITY_ORDER:
        return "LOW"
    return reliability


def calculate_confidence(
    state: AgentState,
    sources: list[dict[str, JsonValue]],
) -> float:
    if not state.get("context"):
        return LOW_CONFIDENCE

    if any(source.get("reliability") == "HIGH" for source in sources):
        return HIGH_CONFIDENCE

    return DEFAULT_CONFIDENCE


def build_steps(state: AgentState) -> list[dict[str, JsonValue]]:
    completed_agents = state.get("completed_agents", [])
    steps = [
        {
            "agent": str(agent),
            "action": "complete",
            "log": f"{agent} 결과를 AgentState에서 확인했습니다.",
        }
        for agent in completed_agents
    ]
    steps.append(
        {
            "agent": "final_answer",
            "action": "synthesize",
            "log": "공통 state와 출처 정보를 기준으로 최종 답변을 생성했습니다.",
        }
    )
    return steps
