from __future__ import annotations

from typing import Literal

from langgraph.graph import END, START, StateGraph

from common.state import AgentState


GraphRoute = Literal[
    "supervisor",
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

def nexon_api_node(state: AgentState) -> AgentState:
    from src.collectors.nexon_api import nexon_api_node
    return nexon_api_node(state)


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

    if next_agent in ("research", "analystic", "calculator", "final_answer"):
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

    graph.add_edge(START, "supervisor")
    graph.add_conditional_edges(
        "supervisor",
        route_from_supervisor,
        {
            "research": "research",
            "analystic": "analystic",
            "calculator": "calculator",
            "final_answer": "final_answer",
            "end": END,
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
