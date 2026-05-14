from __future__ import annotations

from typing import Any, Literal

from langgraph.graph import END, START, StateGraph

from common.state import AgentState


GraphRoute = Literal[
    "supervisor",
    "nexon_api",
    "research",
    "analystic",
    "calculator",
    "final_answer",
    "end",
]

MAX_RETRY_COUNT = 2
RETRY_LIMIT_ANSWER = (
    "현재 질문에 맞는 근거를 충분히 확인하지 못해 정확한 답변을 드리기 어렵습니다. "
    "잘못된 정보를 드리지 않기 위해 답변을 중단합니다. "
    "대상 보스, 캐릭터 정보, 궁금한 항목을 조금 더 구체적으로 입력해 주세요."
)


def build_retry_limit_state(state: AgentState) -> AgentState:
    existing_final_answer = str(state.get("final_answer") or "").strip()
    final_answer = existing_final_answer or RETRY_LIMIT_ANSWER
    tool_results = dict(state.get("tool_results", {}))
    tool_results["supervisor_retry_limit"] = {
        "reason": "retry_count exceeded",
        "retry_count": int(state.get("retry_count", 0)),
        "preserved_final_answer": bool(existing_final_answer),
    }

    return {
        **state,
        "draft_answer": state.get("draft_answer") or final_answer,
        "final_answer": final_answer,
        "validation_passed": False,
        "is_complete": True,
        "next_agent": "FINISH",
        "retry_target": "FINISH",
        "tool_results": tool_results,
    }


def has_nexon_character_data(state: AgentState) -> bool:
    return bool(state.get("character_profile") and state.get("character_stats"))


def nexon_lookup_attempted(state: AgentState) -> bool:
    return bool((state.get("tool_results") or {}).get("nexon_api"))


def read_field(value: Any, key: str, default: Any = "") -> Any:
    if isinstance(value, dict):
        return value.get(key, default)
    return getattr(value, key, default)


def build_nexon_evidence_context(state: AgentState, error: str = "") -> str:
    if error:
        character_name = state.get("character_name", "")
        query = state.get("user_query", "")
        lines = ["Nexon Open API 캐릭터 조회 실패"]
        if character_name:
            lines.append(f"- 캐릭터: {character_name}")
        if query:
            lines.append(f"- 사용자 질문: {query}")
        lines.append(f"- 오류: {error}")
        return "\n".join(lines)

    profile = state.get("character_profile") or {}
    stats = state.get("character_stats") or read_field(profile, "final_stats", {}) or {}
    equipment_items = state.get("equipment_items") or read_field(profile, "equipment_list", []) or []
    union_status = state.get("union_status") or read_field(profile, "union_info", {}) or {}

    lines = ["Nexon Open API 캐릭터 조회 결과"]
    profile_fields = (
        ("캐릭터", read_field(profile, "character_name", state.get("character_name", ""))),
        ("월드", read_field(profile, "world_name", state.get("world_name", ""))),
        ("직업", read_field(profile, "job_name", "")),
        ("레벨", read_field(profile, "level", "")),
    )
    for label, value in profile_fields:
        if value not in ("", None):
            lines.append(f"- {label}: {value}")

    stat_fields = (
        ("전투력", read_field(stats, "combat_power", "")),
        ("스탯 공격력", _format_damage_range(stats)),
        ("STR", read_field(stats, "str_val", "")),
        ("DEX", read_field(stats, "dex", "")),
        ("INT", read_field(stats, "int_val", "")),
        ("LUK", read_field(stats, "luk", "")),
        ("데미지", _format_percent(read_field(stats, "damage", ""))),
        ("보스 데미지", _format_percent(read_field(stats, "boss_damage", ""))),
        ("최종 데미지", _format_percent(read_field(stats, "final_damage", ""))),
        ("방어율 무시", _format_percent(read_field(stats, "ignore_def", ""))),
        ("크리티컬 확률", _format_percent(read_field(stats, "crit_rate", ""))),
        ("크리티컬 데미지", _format_percent(read_field(stats, "crit_damage", ""))),
        ("공격력", read_field(stats, "attack_power", "")),
        ("마력", read_field(stats, "magic_power", "")),
        ("아케인포스", read_field(stats, "arcane_force", "")),
        ("어센틱포스", read_field(stats, "authentic_force", "")),
    )
    for label, value in stat_fields:
        if value not in ("", None):
            lines.append(f"- {label}: {value}")

    if equipment_items:
        lines.append(f"- 장착 장비 수: {len(equipment_items)}")

    union_fields = (
        ("유니온 레벨", read_field(union_status, "union_level", "")),
        ("유니온 등급", read_field(union_status, "union_grade", "")),
        ("아티팩트 레벨", read_field(union_status, "artifact_level", "")),
    )
    for label, value in union_fields:
        if value not in ("", None):
            lines.append(f"- {label}: {value}")

    lines.append("- 출처: Nexon Open API")
    return "\n".join(lines)


def attach_nexon_evidence(state: AgentState, error: str = "") -> AgentState:
    context = build_nexon_evidence_context(state, error)
    existing_context = str(state.get("context") or "").strip()
    merged_context = (
        f"{existing_context}\n\n{context}"
        if existing_context and context not in existing_context
        else context or existing_context
    )

    profile = state.get("character_profile") or {}
    document = {
        "page_content": context,
        "metadata": {
            "source": "nexon_api",
            "retrieval_method": "nexon_open_api",
            "reliability": "LOW" if error else "HIGH",
            "character_name": str(read_field(profile, "character_name", state.get("character_name", "")) or ""),
            "world_name": str(read_field(profile, "world_name", state.get("world_name", "")) or ""),
            "ocid": str(state.get("ocid") or ""),
            "error": error,
        },
        "source": "nexon_api",
        "score": 0.2 if error else 1.0,
    }
    retrieved_docs = [
        doc
        for doc in list(state.get("retrieved_docs") or [])
        if not (
            isinstance(doc, dict)
            and (
                doc.get("source") == "nexon_api"
                or (doc.get("metadata") or {}).get("source") == "nexon_api"
            )
        )
    ]
    retrieved_docs.append(document)

    return {
        **state,
        "context": merged_context,
        "retrieved_docs": retrieved_docs,
        "selected_evidence": [
            *list(state.get("selected_evidence") or []),
            document,
        ],
        "evidence_summary": {
            **dict(state.get("evidence_summary") or {}),
            "nexon_api": {
                "source": "nexon_api",
                "reliability": "LOW" if error else "HIGH",
                "summary": context,
            },
        },
        "relevance_reason": state.get("relevance_reason")
        or ("nexon_api_error_context" if error else "nexon_api_character_lookup"),
    }


def _format_damage_range(stats: Any) -> str:
    min_damage = read_field(stats, "min_stat_damage", "")
    max_damage = read_field(stats, "max_stat_damage", "")
    if min_damage in ("", None) and max_damage in ("", None):
        return ""
    return f"{min_damage} ~ {max_damage}"


def _format_percent(value: Any) -> str:
    if value in ("", None):
        return ""
    return f"{value}%"


def nexon_api_node(state: AgentState) -> AgentState:
    tool_results = dict(state.get("tool_results") or {})

    if has_nexon_character_data(state):
        tool_results["nexon_api"] = {
            **dict(tool_results.get("nexon_api") or {}),
            "lookup_attempted": True,
            "skipped": True,
            "reason": "character_data_already_available",
        }
        return attach_nexon_evidence({
            **state,
            "requires_character_lookup": False,
            "tool_results": tool_results,
        })

    try:
        from src.collectors.nexon_api import nexon_api_node as run_nexon_api_node

        next_state = run_nexon_api_node(state)
        next_tool_results = dict(next_state.get("tool_results") or {})
        nexon_result = dict(next_tool_results.get("nexon_api") or {})
        next_tool_results["nexon_api"] = {
            **nexon_result,
            "lookup_attempted": True,
        }
        return attach_nexon_evidence({
            **next_state,
            "requires_character_lookup": False,
            "tool_results": next_tool_results,
        })
    except Exception as exc:
        error = str(exc)
        tool_results["nexon_api"] = {
            "lookup_attempted": True,
            "data_reliability": "unavailable",
            "error": error,
        }
        return attach_nexon_evidence({
            **state,
            "requires_character_lookup": False,
            "tool_results": tool_results,
            "errors": [
                *list(state.get("errors", []) or []),
                f"nexon_api failed: {error}",
            ],
        }, error=error)


def supervisor(state: AgentState) -> AgentState:
    plan = list(state.get("plan") or [])
    has_research_evidence = bool(
        str(state.get("context") or "").strip()
        or state.get("retrieved_docs")
    )
    has_final_answer = bool(str(state.get("final_answer") or "").strip())
    can_finish_forced_plan = (
        has_research_evidence
        and "final_answer" in plan
        and not has_final_answer
    )
    if int(state.get("retry_count", 0)) >= MAX_RETRY_COUNT and not can_finish_forced_plan:
        return build_retry_limit_state(state)

    from src.agents.supervisor import supervisor as supervisor_agent

    return supervisor_agent(state)


def research(state: AgentState) -> AgentState:
    from src.agents.research_agent import research_agent

    next_state = {
        **state,
        "character_name": state.get("character_name", ""),
        "world_name": state.get("world_name", ""),
    }
    return research_agent(next_state)


def evidence_formatter(state: AgentState) -> AgentState:
    from src.rag.evidence_formatter import format_evidence_for_answer

    return format_evidence_for_answer(state)


def analystic(state: AgentState) -> AgentState:
    from src.agents.analytics import analytics_agent

    return analytics_agent(state=state)


def calculator(state: AgentState) -> AgentState:
    from src.agents.calculator import calculator_agent

    return calculator_agent(state=state)


def final_answer(state: AgentState) -> AgentState:
    from src.agents.final_answer import run_final_answer_agent

    next_state = {
        **state,
        "context": state.get("context", ""),
        "recommended_actions": state.get("recommended_actions", []),
    }
    return run_final_answer_agent(next_state)


def evaluation(state: AgentState) -> AgentState:
    final_answer_text = str(state.get("final_answer") or "").strip()
    has_context = bool(str(state.get("context") or "").strip())
    has_retrieved_docs = bool(state.get("retrieved_docs") or [])
    if final_answer_text and not has_context and not has_retrieved_docs:
        if state.get("task_type") == "chitchat":
            tool_results = dict(state.get("tool_results", {}))
            tool_results["evaluation"] = {
                "agent": "evaluation",
                "is_pass": True,
                "route": "PASS",
                "next_agent": "FINISH",
                "retry_target": "FINISH",
                "feedback": "Chitchat does not require retrieved context.",
                "warnings": [],
            }
            return {
                **state,
                "tool_results": tool_results,
                "validation_passed": True,
                "feedback": "Chitchat does not require retrieved context.",
                "is_complete": True,
                "next_agent": "FINISH",
                "retry_target": "FINISH",
            }

        retry_count = int(state.get("retry_count", 0))
        tool_results = dict(state.get("tool_results", {}))
        tool_results["evaluation"] = {
            "agent": "evaluation",
            "is_pass": False,
            "route": "REPLAN",
            "next_agent": "supervisor",
            "retry_target": "supervisor",
            "feedback": (
                "missing_context: no retrieved context or documents were available. "
                "Send back to supervisor and run research with web fallback before final_answer."
            ),
            "warnings": ["contexts are empty", "retrieved_docs are empty"],
            "failure_type": "missing_context",
            "retry_count": retry_count,
            "max_retry_count": MAX_RETRY_COUNT,
        }
        return {
            **state,
            "tool_results": tool_results,
            "validation_passed": False,
            "feedback": tool_results["evaluation"]["feedback"],
            "is_complete": False,
            "next_agent": "supervisor",
            "retry_target": "supervisor",
            "retry_count": retry_count + 1,
        }

    from src.evaluation.final_answer_eval import run_final_answer_evaluation

    return run_final_answer_evaluation(
        state,
        apply_route=True,
        max_retry_count=MAX_RETRY_COUNT,
    )


def route_from_supervisor(state: AgentState) -> GraphRoute:
    if state.get("is_complete") or state.get("next_agent") == "FINISH":
        return "end"

    next_agent = state.get("next_agent", "final_answer")

    if (
        next_agent in ("analystic", "calculator", "final_answer")
        and state.get("requires_character_lookup")
        and not has_nexon_character_data(state)
        and not nexon_lookup_attempted(state)
    ):
        return "nexon_api"

    if next_agent in ("research", "analystic", "calculator", "final_answer"):
        return next_agent

    return "final_answer"


def route_from_nexon_api(state: AgentState) -> GraphRoute:
    next_agent = state.get("next_agent", "final_answer")
    if next_agent in ("analystic", "calculator", "final_answer"):
        return next_agent
    return "final_answer"


def route_from_evaluation(state: AgentState) -> GraphRoute:
    if state.get("validation_passed"):
        return "end"

    return "supervisor"


def maple_chat_graph():
    graph = StateGraph(AgentState)
    graph.add_node("supervisor", supervisor)
    graph.add_node("research", research)
    graph.add_node("evidence_formatter", evidence_formatter)
    graph.add_node("analystic", analystic)
    graph.add_node("calculator", calculator)
    graph.add_node("final_answer", final_answer)
    graph.add_node("evaluation", evaluation)
    graph.add_node("nexon_api", nexon_api_node)

    graph.add_edge(START, "supervisor")
    graph.add_conditional_edges(
        "supervisor",
        route_from_supervisor,
        {
            "nexon_api": "nexon_api",
            "research": "research",
            "analystic": "analystic",
            "calculator": "calculator",
            "final_answer": "final_answer",
            "end": END,
        },
    )
    graph.add_conditional_edges(
        "nexon_api",
        route_from_nexon_api,
        {
            "analystic": "analystic",
            "calculator": "calculator",
            "final_answer": "final_answer",
        },
    )
    graph.add_edge("research", "evidence_formatter")
    graph.add_edge("evidence_formatter", "supervisor")
    graph.add_edge("analystic", "supervisor")
    graph.add_edge("calculator", "supervisor")
    graph.add_edge("final_answer", "evaluation")
    graph.add_conditional_edges(
        "evaluation",
        route_from_evaluation,
        {
            "supervisor": "supervisor",
            "end": END,
        },
    )
    return graph.compile()
