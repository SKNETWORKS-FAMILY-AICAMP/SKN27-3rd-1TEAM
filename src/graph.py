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
    tool_results = dict(state.get("tool_results", {}))
    tool_results["supervisor_retry_limit"] = {
        "reason": "retry_count exceeded",
        "retry_count": int(state.get("retry_count", 0)),
    }

    return {
        **state,
        "draft_answer": RETRY_LIMIT_ANSWER,
        "final_answer": RETRY_LIMIT_ANSWER,
        "validation_passed": False,
        "is_complete": True,
        "next_agent": "FINISH",
        "retry_target": "FINISH",
        "tool_results": tool_results,
    }


def supervisor(state: AgentState) -> AgentState:
    if int(state.get("retry_count", 0)) >= MAX_RETRY_COUNT:
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
    graph.add_edge("research", "supervisor")
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
