from __future__ import annotations

import re
from typing import Any

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
MAX_FINAL_CONTEXT_CHARS = 3500
MAX_LLM_ERROR_CHARS = 500

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
    final_answer, generation_result = generate_final_answer(state, draft_answer)
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
            build_final_answer_tool_result(
                state,
                sources,
                confidence_score,
                generation_result,
            ),
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
    boss_readiness_answer = build_boss_readiness_draft_answer(state)
    if boss_readiness_answer:
        return boss_readiness_answer

    question = state["user_query"]
    context = compact_text(state["context"].strip(), MAX_FINAL_CONTEXT_CHARS)
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


STAT_LABELS = {
    "level": "레벨",
    "combat_power": "전투력",
    "main_stat": "주스탯",
    "boss_damage": "보스 데미지",
    "ignore_def": "방어 무시",
    "force": "포스",
    "starforce": "스타포스",
    "union_level": "유니온",
}


def build_boss_readiness_draft_answer(state: AgentState) -> str:
    tool_results = state.get("tool_results") or {}
    if not isinstance(tool_results, dict):
        return ""

    analysis = tool_results.get("analystic") or {}
    if not isinstance(analysis, dict) or not analysis.get("clear_status"):
        return ""

    requirements = analysis.get("boss_requirements") or {}
    if not isinstance(requirements, dict) or not requirements:
        return ""

    profile = state.get("character_profile") or {}
    stat_summary = state.get("stat_summary") or {}
    character_name = str(
        read_field(profile, "character_name")
        or state.get("character_name")
        or "해당 캐릭터"
    )
    job_name = str(read_field(profile, "job_name") or read_field(stat_summary, "job_name") or "")
    target_boss = format_target_boss(analysis, requirements)
    status = str(analysis.get("clear_status") or "unknown")
    challengeable = bool(analysis.get("challengeable", status in {"recommended", "challengeable"}))
    verdict = "도전 가능" if challengeable else "아직 어려움"
    score = format_number(analysis.get("challenge_fit_score"), digits=4)

    current_stats = collect_current_stats(state)
    requirement_stats = collect_requirement_stats(requirements)
    enough_lines, lacking_lines = split_stat_comparisons(current_stats, requirement_stats)
    lacking_names = [
        STAT_LABELS.get(str(item), str(item))
        for item in (analysis.get("lacking_stats") or [])
    ]
    lacking_text = ", ".join(lacking_names) if lacking_names else "뚜렷한 부족 항목 없음"

    lines = [
        f"결론: {character_name}은 {target_boss} 기준으로 {verdict}으로 판단됩니다.",
    ]
    if job_name:
        lines.append(f"캐릭터: {character_name} / 직업: {job_name}")
    lines.extend(
        [
            f"판정: {status} / challenge_fit_score={score}",
            f"부족 항목: {lacking_text}",
        ]
    )

    if enough_lines:
        lines.extend(["", "충족한 기준:", *[f"- {line}" for line in enough_lines]])
    if lacking_lines:
        lines.extend(["", "주의할 기준:", *[f"- {line}" for line in lacking_lines]])

    growth_options = ((state.get("equipment_summary") or {}).get("growth_forecast") or [])[:3]
    if growth_options:
        lines.extend(
            [
                "",
                "우선 성장 후보:",
                *[
                    (
                        f"- {option.get('category', '성장')} {option.get('target', '')}: "
                        f"예상 상승 {format_number(option.get('expected_damage_gain_percent'))}%"
                    ).strip()
                    for option in growth_options
                ],
            ]
        )

    source_name = requirements.get("source_name") or analysis.get("data_reliability") or "unknown"
    reliability = requirements.get("reliability") or "unknown"
    lines.extend(
        [
            "",
            f"요구치 출처/신뢰도: {source_name} / {reliability}",
            "요약: 도전은 가능하지만, 안정성을 올리려면 주스탯, 보스 데미지, 방어 무시를 먼저 보강하는 쪽이 좋습니다.",
        ]
    )
    return "\n".join(lines).strip()


def format_target_boss(analysis: dict[str, Any], requirements: dict[str, Any]) -> str:
    boss_name = str(read_field(analysis, "target_boss") or read_field(requirements, "boss_name") or "대상 보스")
    difficulty = str(read_field(requirements, "difficulty") or "").strip().lower()
    difficulty_label = {
        "easy": "이지",
        "normal": "노멀",
        "hard": "하드",
        "chaos": "카오스",
        "extreme": "익스트림",
    }.get(difficulty, "")
    if difficulty_label and difficulty_label not in boss_name:
        return f"{difficulty_label} {boss_name}"
    return boss_name


def collect_current_stats(state: AgentState) -> dict[str, float]:
    stat_summary = state.get("stat_summary") or {}
    character_stats = state.get("character_stats") or {}
    profile = state.get("character_profile") or {}
    union_status = state.get("union_status") or {}
    equipment_summary = state.get("equipment_summary") or {}
    return {
        "level": float(read_field(profile, "level") or read_field(stat_summary, "character_level") or 0),
        "combat_power": float(read_field(stat_summary, "combat_power") or read_field(character_stats, "combat_power") or 0),
        "main_stat": float(read_field(stat_summary, "main_stat") or read_field(character_stats, "main_stat") or 0),
        "boss_damage": float(read_field(stat_summary, "boss_damage") or read_field(character_stats, "boss_damage") or 0),
        "ignore_def": float(read_field(stat_summary, "ignore_def") or read_field(character_stats, "ignore_def") or 0),
        "force": float(read_field(stat_summary, "arcane_force") or read_field(character_stats, "arcane_force") or 0)
        + float(read_field(stat_summary, "authentic_force") or read_field(character_stats, "authentic_force") or 0),
        "starforce": float(read_field(equipment_summary, "total_starforce") or 0),
        "union_level": float(read_field(union_status, "union_level") or 0),
    }


def collect_requirement_stats(requirements: dict[str, Any]) -> dict[str, float]:
    return {
        "level": float(requirements.get("required_level") or 0),
        "combat_power": float(requirements.get("required_combat_power") or 0),
        "main_stat": float(requirements.get("required_main_stat") or 0),
        "boss_damage": float(requirements.get("required_boss_damage") or 0),
        "ignore_def": float(requirements.get("required_ignore_def") or 0),
        "force": float(requirements.get("required_arcane_force") or 0)
        + float(requirements.get("required_authentic_force") or 0),
        "starforce": float(requirements.get("required_starforce") or 0),
        "union_level": float(requirements.get("required_union_level") or 0),
    }


def split_stat_comparisons(
    current_stats: dict[str, float],
    requirement_stats: dict[str, float],
) -> tuple[list[str], list[str]]:
    enough: list[str] = []
    lacking: list[str] = []
    for key, required in requirement_stats.items():
        if required <= 0:
            continue
        current = current_stats.get(key, 0.0)
        label = STAT_LABELS.get(key, key)
        text = f"{label}: 현재 {format_number(current)} / 요구 {format_number(required)}"
        if current >= required:
            enough.append(text)
        else:
            gap = required - current
            lacking.append(f"{text} / 부족 {format_number(gap)}")
    return enough, lacking


def format_number(value: Any, *, digits: int = 2) -> str:
    if value in (None, ""):
        return "0"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    if number.is_integer():
        return f"{int(number):,}"
    return f"{number:,.{digits}f}".rstrip("0").rstrip(".")


def read_field(source: Any, field: str, default: Any = "") -> Any:
    if source is None:
        return default
    if isinstance(source, dict):
        return source.get(field, default)
    return getattr(source, field, default)


def finalize_answer(draft_answer: str) -> str:
    if not draft_answer:
        return ""

    return draft_answer


def generate_final_answer(state: AgentState, draft_answer: str) -> tuple[str, dict[str, JsonValue]]:
    generation_result: dict[str, JsonValue] = {
        "llm_called": False,
        "llm_succeeded": False,
        "fallback_used": False,
        "answer_source": "draft",
    }

    if not should_use_llm():
        generation_result["fallback_used"] = True
        generation_result["skip_reason"] = "should_use_llm returned false"
        return finalize_answer(draft_answer), generation_result

    try:
        messages = build_final_answer_messages(state, draft_answer)
        generation_result["llm_called"] = True
        generation_result["prompt_message_count"] = len(messages)
        response = get_llm().invoke(messages)
    except Exception as exc:
        error_message = redact_error_text(exc)
        errors = list(state.get("errors") or [])
        errors.append(f"final_answer LLM call failed: {error_message}")
        state["errors"] = errors
        generation_result.update(
            {
                "fallback_used": True,
                "error_type": type(exc).__name__,
                "error_message": error_message,
            }
        )
        return finalize_answer(draft_answer), generation_result

    content = getattr(response, "content", response)
    if isinstance(content, list):
        content = "\n".join(str(item) for item in content)

    answer = str(content).strip()
    generation_result["llm_succeeded"] = True
    if answer:
        generation_result["answer_source"] = "llm"
        return answer, generation_result

    generation_result["fallback_used"] = True
    generation_result["empty_response"] = True
    return finalize_answer(draft_answer), generation_result


def redact_error_text(error: Exception) -> str:
    text = str(error)
    for pattern in (
        r"gsk_[A-Za-z0-9_-]+",
        r"sk-[A-Za-z0-9_-]+",
        r"test_[A-Za-z0-9_-]+",
        r"tvly-[A-Za-z0-9_-]+",
    ):
        text = re.sub(pattern, "[REDACTED]", text)
    return text[:MAX_LLM_ERROR_CHARS]


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
            "state에 없는 정보는 추측하지 말고, 근거가 부족하면 한계를 명시하세요.",
            "용어는 고정해서 쓰세요: authentic_force/sacred_force는 어센틱포스, arcane_force는 아케인포스, ignore_def는 방어율 무시입니다.",
            "'오쎈', '인증 포스'처럼 메이플스토리에서 쓰지 않는 번역어는 사용하지 마세요.",
        ]
    ).strip()


def build_final_answer_user_prompt(state: AgentState, draft_answer: str = "") -> str:
    evaluation = get_evaluation_result(state)
    return "\n".join(
        [
            f"사용자 질문: {state.get('user_query', '')}",
            f"근거 context: {compact_text(state.get('context', ''), MAX_FINAL_CONTEXT_CHARS)}",
            f"추천 액션: {format_recommendations(state)}",
            f"Evaluation route: {normalize_evaluation_route(evaluation)}",
            f"Evaluation feedback: {extract_evaluation_feedback(evaluation, state)}",
            f"초안 답변: {compact_text(draft_answer, MAX_FINAL_CONTEXT_CHARS)}",
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
    }.get(reliability, "LOW")


def compact_text(value: Any, max_chars: int) -> str:
    text = str(value or "").strip()
    if len(text) <= max_chars:
        return text
    return f"{text[:max_chars].rstrip()}\n...[truncated]"


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
    generation_result: dict[str, JsonValue],
) -> dict[str, JsonValue]:
    evaluation = get_evaluation_result(state)
    return {
        "next_step": "evaluation",
        "source_count": len(sources),
        "confidence_score": confidence_score,
        "generation": generation_result,
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
