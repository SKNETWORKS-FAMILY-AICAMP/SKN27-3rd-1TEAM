from __future__ import annotations

from typing import TYPE_CHECKING, Literal, TypeAlias, TypedDict

if TYPE_CHECKING:
    from langchain_core.messages import BaseMessage

from common.domain import (
    ActionPlan,
    CharacterStatDetail,
    EquipmentDetail,
    GrowthEfficiencyReport,
    ProcessedCharacter,
    UnionStatus,
)


NextAgent = Literal[
    "calculator",
    "analystic",
    "research",
    "final_answer",
    "supervisor",
    "FINISH",
]

JsonPrimitive: TypeAlias = str | int | float | bool | None
JsonValue: TypeAlias = JsonPrimitive | list["JsonValue"] | dict[str, "JsonValue"]


class RetrievedDocument(TypedDict, total=False):
    page_content: str
    metadata: dict[str, JsonValue]
    score: float
    source: str


class AgentState(TypedDict, total=False):
    # Shared input
    user_query: str
    messages: list[BaseMessage]

    # Request analysis
    intent: str
    task_type: str
    plan: list[str]

    # Supervisor routing
    next_agent: NextAgent
    completed_agents: list[str]
    retry_count: int

    # Character identity
    character_name: str
    world_name: str
    ocid: str

    # Raw external results
    tool_results: dict[str, JsonValue]
    raw_api_results: dict[str, JsonValue]

    # Normalized character data
    character_profile: ProcessedCharacter
    character_stats: CharacterStatDetail
    equipment_items: list[EquipmentDetail]
    union_status: UnionStatus

    # Search/RAG context
    retrieved_docs: list[RetrievedDocument]
    context: str

    # Stat/equipment analysis
    stat_summary: dict[str, JsonValue]
    equipment_summary: dict[str, JsonValue]
    bottleneck_analysis: dict[str, float]

    # Growth recommendation
    growth_report: GrowthEfficiencyReport
    recommended_actions: list[ActionPlan]

    # Answer generation
    draft_answer: str
    final_answer: str

    # Validation/errors
    validation_passed: bool
    confidence_score: float
    errors: list[str]

    # Graph termination
    is_complete: bool

AgentName = Literal[
    "supervisor",
    "calculator",
    "analystic",
    "research",
    "final_answer",
]

AgentStateField = Literal[
    "user_query",
    "messages",
    "intent",
    "task_type",
    "plan",
    "next_agent",
    "completed_agents",
    "retry_count",
    "character_name",
    "world_name",
    "ocid",
    "tool_results",
    "raw_api_results",
    "character_profile",
    "character_stats",
    "equipment_items",
    "union_status",
    "retrieved_docs",
    "context",
    "stat_summary",
    "equipment_summary",
    "bottleneck_analysis",
    "growth_report",
    "recommended_actions",
    "draft_answer",
    "final_answer",
    "validation_passed",
    "confidence_score",
    "errors",
    "is_complete",
]


class AgentFieldContract(TypedDict):
    required_inputs: tuple[AgentStateField, ...]
    required_outputs: tuple[AgentStateField, ...]


# Field contract for each agent.
# Update this table whenever an agent or AgentState key changes.
AGENT_FIELD_CONTRACTS: dict[AgentName, AgentFieldContract] = {
    "supervisor": {
        "required_inputs": ("user_query", "messages"),
        "required_outputs": ("intent", "task_type", "plan", "next_agent"),
    },
    "calculator": {
        "required_inputs": ("character_stats", "equipment_items", "union_status"),
        "required_outputs": ("stat_summary", "equipment_summary", "bottleneck_analysis"),
    },
    "analystic": {
        "required_inputs": ("character_profile", "stat_summary", "equipment_summary"),
        "required_outputs": ("growth_report", "recommended_actions"),
    },
    "research": {
        "required_inputs": ("user_query", "character_name", "world_name"),
        "required_outputs": ("retrieved_docs", "context"),
    },
    "final_answer": {
        "required_inputs": ("user_query", "recommended_actions", "context"),
        "required_outputs": (
            "draft_answer",
            "final_answer",
            "validation_passed",
            "confidence_score",
        ),
    },
}
