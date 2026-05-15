from __future__ import annotations

from typing import Any

from common.conversation import (
    format_messages_for_prompt,
    is_conversation_recall_query,
    is_first_message_recall_query,
    user_message_contents,
)
from common.get_model import get_llm
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
FRESHNESS_ORDER = {"HIGH": 0, "MEDIUM": 1, "UNKNOWN": 2, "LOW": 3}
MAX_SOURCE_COUNT = 5
MAX_RETRY_COUNT = 2
MAX_FINAL_ANSWER_MESSAGE_CONTEXT = 10
MAX_RECALL_MESSAGE_CHARS = 700

EVALUATION_TOOL_KEY = "evaluation"
FINAL_ANSWER_TOOL_KEY = "final_answer"
EVALUATION_PASS = "PASS"
EVALUATION_REWRITE = "REWRITE"
EVALUATION_REPLAN = "REPLAN"
EVALUATION_PENDING = "PENDING"


def run_final_answer_agent(state: AgentState) -> AgentState:
    """Build the final answer fields required by common.state."""

    validate_state_keys(state)
    validate_agent_inputs("final_answer", state)

    sources = collect_sources(state)
    draft_answer = build_draft_answer(state, sources)
    final_answer = generate_final_answer(state, draft_answer)
    confidence_score = calculate_confidence(state, sources)

    next_state: AgentState = {
        **state,
        "draft_answer": draft_answer,
        "final_answer": final_answer,
        "validation_passed": bool(state.get("validation_passed", False)),
        "confidence_score": confidence_score,
        "tool_results": merge_tool_result(
            state,
            FINAL_ANSWER_TOOL_KEY,
            build_final_answer_tool_result(state, sources, confidence_score),
        ),
    }
    validate_agent_outputs("final_answer", next_state)
    return next_state


def route_after_evaluation(state: AgentState) -> AgentState:
    """Route evaluation result to FINISH, final_answer rewrite, or supervisor replan."""

    validate_state_keys(state)

    evaluation = get_evaluation_result(state)
    route = normalize_evaluation_route(evaluation)
    feedback = extract_evaluation_feedback(evaluation, state)
    retry_count = int(state.get("retry_count") or 0)

    if route == EVALUATION_PASS:
        return {
            **state,
            "validation_passed": True,
            "next_agent": "FINISH",
            "retry_target": "FINISH",
            "feedback": feedback,
            "is_complete": True,
            "tool_results": merge_tool_result(
                state,
                FINAL_ANSWER_TOOL_KEY,
                build_evaluation_route_result(route, "FINISH", retry_count),
            ),
        }

    if route == EVALUATION_REPLAN or retry_count >= MAX_RETRY_COUNT:
        next_retry_count = retry_count + 1
        return {
            **state,
            "validation_passed": False,
            "next_agent": "supervisor",
            "retry_target": "supervisor",
            "retry_count": next_retry_count,
            "feedback": feedback,
            "is_complete": False,
            "tool_results": merge_tool_result(
                state,
                FINAL_ANSWER_TOOL_KEY,
                build_evaluation_route_result(
                    EVALUATION_REPLAN,
                    "supervisor",
                    next_retry_count,
                ),
            ),
        }

    if route == EVALUATION_REWRITE:
        next_retry_count = retry_count + 1
        return {
            **state,
            "validation_passed": False,
            "next_agent": "final_answer",
            "retry_target": "final_answer",
            "retry_count": next_retry_count,
            "feedback": feedback,
            "is_complete": False,
            "tool_results": merge_tool_result(
                state,
                FINAL_ANSWER_TOOL_KEY,
                build_evaluation_route_result(
                    route,
                    "final_answer",
                    next_retry_count,
                ),
            ),
        }

    return {
        **state,
        "validation_passed": False,
        "feedback": feedback,
        "is_complete": False,
    }


def build_chat_response(state: AgentState) -> dict[str, JsonValue]:
    """Return an OpenAPI ApiResponseChat-compatible dictionary."""

    final_answer = state.get("final_answer", "")
    confidence = state.get("confidence_score", DEFAULT_CONFIDENCE)
    success = bool(final_answer) and bool(state.get("validation_passed", False))

    return {
        "success": success,
        "message": (
            "챗봇 응답 메시지 반환"
            if success
            else "답변 검증이 완료되지 않았거나 실패했습니다."
        ),
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
    if state.get("task_type") == "chitchat":
        if is_conversation_recall_query(str(state.get("user_query") or "")):
            return build_conversation_recall_answer(state)
        return build_chitchat_answer(state)

    question = str(state.get("contextualized_query") or state["user_query"]).strip()
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
    if is_conversation_recall_query(str(state.get("user_query") or "")):
        return finalize_answer(draft_answer)

    if not should_use_llm():
        return finalize_answer(draft_answer)

    try:
        messages = build_final_answer_messages(state, draft_answer)
        response = get_llm().invoke(messages)
    except Exception as exc:
        errors = list(state.get("errors") or [])
        errors.append(f"final_answer LLM call failed: {exc}")
        state["errors"] = errors
        return finalize_answer(draft_answer)

    content = getattr(response, "content", response)
    if isinstance(content, list):
        content = "\n".join(str(item) for item in content)

    return str(content).strip() or finalize_answer(draft_answer)


def should_use_llm() -> bool:
    return True


def build_final_answer_messages(
    state: AgentState,
    draft_answer: str = "",
) -> list[Any]:
    from langchain_core.messages import HumanMessage, SystemMessage

    return [
        SystemMessage(content=build_final_answer_system_prompt()),
        HumanMessage(content=build_final_answer_user_prompt(state, draft_answer)),
    ]


def build_final_answer_system_prompt() -> str:
    return "\n".join(
        [
            master_prompt.strip(),
            "",
            "당신은 메이플스토리 RAG 멀티 에이전트 챗봇의 Final Answer Agent입니다.",
            "제공된 AgentState와 근거 context만 사용하여 한국어로 답변하세요.",
            "단, task_type이 chitchat이면 최근 대화를 주된 근거로 사용해도 됩니다.",
            "그 외에는 최근 대화를 사용자 질문의 생략된 대상과 답변 범위를 파악하는 데만 사용하세요.",
            "state에 없는 정보는 추측하지 말고, 근거가 부족하면 한계를 명시하세요.",
        ]
    ).strip()


def truncate_recall_message(content: str) -> str:
    if len(content) <= MAX_RECALL_MESSAGE_CHARS:
        return content
    return content[:MAX_RECALL_MESSAGE_CHARS].rstrip() + "..."


def build_conversation_recall_answer(state: AgentState) -> str:
    query = str(state.get("user_query") or "")
    user_messages = user_message_contents(state.get("messages") or [])
    prior_messages = user_messages[:-1] if user_messages else []
    if not prior_messages:
        return "아직 이 대화에서 이전에 하신 말은 확인되지 않습니다."

    if is_first_message_recall_query(query):
        target = prior_messages[0]
        return f"맨 처음에는 이렇게 말씀하셨어요:\n\n{truncate_recall_message(target)}"

    target = prior_messages[-1]
    return f"방금 전에는 이렇게 말씀하셨어요:\n\n{truncate_recall_message(target)}"


def build_chitchat_answer(state: AgentState) -> str:
    query = str(state.get("user_query") or "").strip()
    if not query:
        return "편하게 말씀해 주세요."
    return "네, 대화 흐름을 보고 답변드릴게요."


def format_messages_for_final_answer(state: AgentState) -> str:
    messages = list(state.get("messages") or [])[-MAX_FINAL_ANSWER_MESSAGE_CONTEXT:]
    return format_messages_for_prompt(messages)


def build_final_answer_user_prompt(state: AgentState, draft_answer: str = "") -> str:
    evaluation = get_evaluation_result(state)
    return "\n".join(
        [
            f"사용자 질문: {state.get('user_query', '')}",
            f"맥락 반영 질문: {state.get('contextualized_query') or state.get('user_query', '')}",
            f"최근 대화:\n{format_messages_for_final_answer(state) or '없음'}",
            f"근거 context: {state.get('context', '')}",
            f"추천 액션: {format_recommendations(state)}",
            f"Evaluation route: {normalize_evaluation_route(evaluation)}",
            f"Evaluation feedback: {extract_evaluation_feedback(evaluation, state)}",
            f"초안 답변: {draft_answer}",
        ]
    ).strip()


def format_recommendations(state: AgentState) -> str:
    actions = state.get("recommended_actions", [])
    if not actions:
        return ""

    sorted_actions = sorted(actions, key=get_action_priority)
    return "\n".join(
        (
            f"{get_action_priority(action)}. "
            f"{get_action_value(action, 'category')} - "
            f"{get_action_value(action, 'target')}: "
            f"{get_action_value(action, 'description')}"
        )
        for action in sorted_actions
    )


def get_action_priority(action: Any) -> int:
    value = get_action_value(action, "priority", default=999)
    try:
        return int(value)
    except (TypeError, ValueError):
        return 999


def get_action_value(action: Any, field: str, default: Any = "") -> Any:
    if isinstance(action, dict):
        return action.get(field, default)
    return getattr(action, field, default)


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
        key=source_sort_key,
    )[:MAX_SOURCE_COUNT]


def source_sort_key(source: dict[str, JsonValue]) -> tuple[int, int, float]:
    reliability = str(source.get("reliability") or "LOW")
    freshness = str(source.get("freshness") or "UNKNOWN")
    score = source.get("score")
    try:
        normalized_score = float(score or 0)
    except (TypeError, ValueError):
        normalized_score = 0.0
    return (
        RELIABILITY_ORDER.get(reliability, 99),
        FRESHNESS_ORDER.get(freshness, 99),
        -normalized_score,
    )


def source_from_document(document: RetrievedDocument) -> dict[str, JsonValue]:
    metadata = document.get("metadata", {})
    title = metadata.get("title") or document.get("source") or "출처 미상"
    url = metadata.get("url") or metadata.get("source") or document.get("source") or ""
    reliability = normalize_reliability(metadata.get("reliability"))

    return {
        "title": str(title),
        "url": str(url),
        "reliability": reliability,
        "freshness": normalize_freshness(metadata.get("freshness")),
        "published_at": metadata.get("published_at"),
        "score": document.get("score", 0.0),
    }


def normalize_reliability(value: Any) -> str:
    reliability = str(value or "LOW").upper()
    if reliability not in RELIABILITY_ORDER:
        return "LOW"
    return reliability


def normalize_freshness(value: Any) -> str:
    freshness = str(value or "UNKNOWN").upper()
    if freshness not in FRESHNESS_ORDER:
        return "UNKNOWN"
    return freshness


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

    evaluation = get_evaluation_result(state)
    if evaluation:
        route = normalize_evaluation_route(evaluation)
        steps.append(
            {
                "agent": "evaluation",
                "action": "route",
                "log": f"Evaluation 결과에 따라 {route} 경로로 판단했습니다.",
            }
        )

    return steps


def get_evaluation_result(state: AgentState) -> dict[str, JsonValue]:
    tool_results = state.get("tool_results") or {}
    if not isinstance(tool_results, dict):
        return {}

    evaluation = tool_results.get(EVALUATION_TOOL_KEY)
    if isinstance(evaluation, dict):
        return evaluation
    return {}


def normalize_evaluation_route(evaluation: dict[str, JsonValue]) -> str:
    if not evaluation:
        return EVALUATION_PENDING

    if is_truthy(evaluation.get("is_pass")):
        return EVALUATION_PASS

    explicit_route = str(
        evaluation.get("route")
        or evaluation.get("decision")
        or evaluation.get("next_route")
        or ""
    ).strip().upper()
    if explicit_route in {EVALUATION_PASS, EVALUATION_REWRITE, EVALUATION_REPLAN}:
        return explicit_route

    retry_target = str(
        evaluation.get("retry_target")
        or evaluation.get("next_agent")
        or ""
    ).strip().lower()
    if retry_target == "supervisor":
        return EVALUATION_REPLAN
    if retry_target == "final_answer":
        return EVALUATION_REWRITE

    if is_irrelevant_evaluation(evaluation):
        return EVALUATION_REPLAN

    if "is_pass" in evaluation and not is_truthy(evaluation.get("is_pass")):
        return EVALUATION_REWRITE

    return EVALUATION_PENDING


def extract_evaluation_feedback(
    evaluation: dict[str, JsonValue],
    state: AgentState,
) -> str:
    for key in ("feedback", "reason", "comment", "message"):
        value = evaluation.get(key)
        if value:
            return str(value)

    return str(state.get("feedback") or "")


def is_irrelevant_evaluation(evaluation: dict[str, JsonValue]) -> bool:
    for key in (
        "is_relevant",
        "context_relevant",
        "answer_relevant",
        "question_relevant",
    ):
        if is_falsy(evaluation.get(key)):
            return True

    failure_type = str(evaluation.get("failure_type") or "").strip().lower()
    return failure_type in {
        "irrelevant",
        "question_mismatch",
        "routing_error",
        "wrong_intent",
        "wrong_context",
    }


def is_truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in {"true", "pass", "passed", "yes", "1"}
    return False


def is_falsy(value: Any) -> bool:
    if isinstance(value, bool):
        return not value
    if isinstance(value, (int, float)):
        return value == 0
    if isinstance(value, str):
        return value.strip().lower() in {"false", "fail", "failed", "no", "0"}
    return False


def merge_tool_result(
    state: AgentState,
    key: str,
    result: dict[str, JsonValue],
) -> dict[str, JsonValue]:
    tool_results = dict(state.get("tool_results") or {})
    tool_results[key] = result
    return tool_results


def build_final_answer_tool_result(
    state: AgentState,
    sources: list[dict[str, JsonValue]],
    confidence_score: float,
) -> dict[str, JsonValue]:
    evaluation = get_evaluation_result(state)
    return {
        "next_step": "evaluation",
        "source_count": len(sources),
        "confidence_score": confidence_score,
        "evaluation_route": normalize_evaluation_route(evaluation),
        "used_evaluation_feedback": bool(
            extract_evaluation_feedback(evaluation, state)
        ),
    }


def build_evaluation_route_result(
    route: str,
    next_agent: str,
    retry_count: int,
) -> dict[str, JsonValue]:
    return {
        "evaluation_route": route,
        "next_agent": next_agent,
        "retry_count": retry_count,
    }
