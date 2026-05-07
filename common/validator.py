from common.state import AGENT_FIELD_CONTRACTS, AgentName, AgentState


STATE_FIELDS = set(AgentState.__annotations__.keys())


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


def validate_state_keys(state: AgentState) -> None:
    unknown_fields = [field for field in state if field not in STATE_FIELDS]

    if unknown_fields:
        raise ValueError(f"Unknown state fields: {unknown_fields}")
