from langgraph.graph import StateGraph, START, END

from common.state import AgentState


def supervisor(state: AgentState):
    from agents.supervisor import supervisor as supervisor_agent

    return supervisor_agent(state)


def research(state: AgentState):
    # TODO: replace this placeholder when the research agent is merged.
    return state


def analystic(state: AgentState):
    from agents.analytics import analytics_agent

    return analytics_agent(state=state)


def calculator(state: AgentState):
    from agents.calculator import calculator_agent

    return calculator_agent(state=state)


def final_answer(state: AgentState):
    from agents.final_answer import run_final_answer_agent

    next_state = {
        **state,
        "context": state.get("context", ""),
        "recommended_actions": state.get("recommended_actions", []),
    }
    return run_final_answer_agent(next_state)


def evaluation(state: AgentState):
    # TODO: replace this placeholder when the evaluation agent is merged.
    if state.get("final_answer"):
        return {
            **state,
            "validation_passed": True,
            "is_complete": True,
        }
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

    if retry_target == "final_answer":
        return "final_answer"

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
