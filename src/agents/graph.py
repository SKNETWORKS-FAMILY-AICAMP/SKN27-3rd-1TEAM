from langgraph.graph import StateGraph, START, END
from common.state import AgentState
from agents.supervisor import supervisor


def research(state: AgentState):
    # TODO: research agent 구현이 들어오면 이 placeholder를 실제 함수 import로 교체
    return state


def analystic(state: AgentState):
    # TODO: analystic agent 구현이 들어오면 이 placeholder를 실제 함수 import로 교체
    return state


def calculator(state: AgentState):
    # TODO: calculator agent 구현이 들어오면 이 placeholder를 실제 함수 import로 교체
    return state


def final_answer(state: AgentState):
    # TODO: final_answer agent 구현이 들어오면 이 placeholder를 실제 함수 import로 교체
    return state


def evaluation(state: AgentState):
    # TODO: evaluation agent 구현이 들어오면 이 placeholder를 실제 함수 import로 교체
    return state


def route_from_supervisor(state: AgentState):
    if state.get("retry_count", 0) >= 2:
        return "final_answer"

    next_agent = state.get("next_agent", "final_answer")

    if next_agent in ["research", "analystic", "calculator", "final_answer"]:
        return next_agent

    return "final_answer"


def route_from_evaluation(state: AgentState):
    if state.get("validation_passed"):
        return "end"

    if state.get("retry_count", 0) >= 2:
        return "end"

    retry_target = state.get("retry_target")

    # 단순 어투/구문 문제면 final_answer에서 자체 재생성
    if retry_target == "final_answer":
        return "final_answer"

    # 근거 부족처럼 다른 agent 작업이 필요하면 supervisor가 feedback을 보고 재라우팅
    return "supervisor"

def maple_chat_graph():
    graph = StateGraph(AgentState)
    graph.add_node("supervisor", supervisor)
    graph.add_node("calculator", calculator)
    graph.add_node("analystic", analystic)
    graph.add_node("research", research)
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
            "final_answer": "final_answer",
            "end": END,
        },
    )
    return graph.compile()
