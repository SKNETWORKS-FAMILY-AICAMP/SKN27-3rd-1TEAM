from typing import Any

from common.state import AGENT_FIELD_CONTRACTS, AgentName, AgentState


STATE_FIELDS = set(AgentState.__annotations__.keys())
NEXT_AGENT_VALUES = {
    "calculator",
    "analystic",
    "research",
    "final_answer",
    "supervisor",
    "FINISH",
}


STATE_FIELD_TYPES = {
    "user_query": "str",
    "messages": "list",
    "intent": "str",
    "task_type": "str",
    "requires_character_lookup": "bool",
    "plan": "list[str]",
    "next_agent": "NextAgent",
    "completed_agents": "list[str]",
    "retry_count": "int",
    "character_name": "str",
    "world_name": "str",
    "ocid": "str",
    "tool_results": "dict",
    "raw_api_results": "dict",
    "character_profile": "state_object",
    "character_stats": "state_object",
    "equipment_items": "list",
    "union_status": "state_object",
    "retrieved_docs": "list[RetrievedDocument]",
    "context": "str",
    "evidence_summary": "dict",
    "selected_evidence": "list[RetrievedDocument]",
    "relevance_reason": "str",
    "stat_summary": "dict",
    "equipment_summary": "dict",
    "bottleneck_analysis": "dict",
    "growth_report": "state_object",
    "recommended_actions": "list",
    "draft_answer": "str",
    "final_answer": "str",
    "validation_passed": "bool",
    "confidence_score": "number",
    "feedback": "str",
    "retry_target": "NextAgent",
    "errors": "list[str]",
    "is_complete": "bool",
}


def validate_agent_inputs(agent_name: AgentName, state: AgentState) -> None:
    required_fields = AGENT_FIELD_CONTRACTS[agent_name]["required_inputs"]
    validate_required_fields(agent_name, state, required_fields, "input")


def validate_agent_outputs(agent_name: AgentName, state: AgentState) -> None:
    required_fields = AGENT_FIELD_CONTRACTS[agent_name]["required_outputs"]
    validate_required_fields(agent_name, state, required_fields, "output")


def validate_required_fields(
    agent_name: str,
    state: AgentState,
    required_fields: tuple[str, ...],
    phase: str,
) -> None:
    missing_fields = [
        field
        for field in required_fields
        if field not in state or state[field] is None
    ]

    if missing_fields:
        raise ValueError(
            f"{agent_name} {phase} state missing fields: {missing_fields}"
        )

    validate_state_field_types(state, required_fields)


def validate_state_field_types(
    state: AgentState,
    fields: tuple[str, ...] | list[str] | None = None,
) -> None:
    target_fields = fields if fields is not None else state.keys()
    invalid_fields = []

    for field in target_fields:
        if field not in state or state[field] is None:
            continue
        expected_type = STATE_FIELD_TYPES.get(field)
        if expected_type is None:
            continue
        value = state[field]
        if not _matches_type(value, expected_type):
            invalid_fields.append(
                f"{field} expected {expected_type}, got {type(value).__name__}"
            )

    if invalid_fields:
        raise TypeError(f"Invalid state field types: {invalid_fields}")


def _matches_type(value: Any, expected_type: str) -> bool:
    if expected_type == "str":
        return isinstance(value, str)
    if expected_type == "bool":
        return type(value) is bool
    if expected_type == "int":
        return type(value) is int
    if expected_type == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected_type == "dict":
        return isinstance(value, dict)
    if expected_type == "list":
        return isinstance(value, list)
    if expected_type == "list[str]":
        return isinstance(value, list) and all(isinstance(item, str) for item in value)
    if expected_type == "NextAgent":
        return isinstance(value, str) and value in NEXT_AGENT_VALUES
    if expected_type == "state_object":
        return isinstance(value, dict) or hasattr(value, "__dict__")
    if expected_type == "list[RetrievedDocument]":
        return isinstance(value, list) and all(_is_retrieved_document(item) for item in value)
    return True


def _is_retrieved_document(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    expected_fields = {
        "page_content": "str",
        "metadata": "dict",
        "score": "number",
        "source": "str",
    }
    return all(
        field not in value or _matches_type(value[field], expected_type)
        for field, expected_type in expected_fields.items()
    )


def validate_state_keys(state: AgentState) -> None:
    unknown_fields = [field for field in state if field not in STATE_FIELDS]

    if unknown_fields:
        raise ValueError(f"Unknown state fields: {unknown_fields}")

    validate_state_field_types(state)
