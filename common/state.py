from __future__ import annotations

from typing import Literal, TypeAlias, TypedDict

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
    user_query: str  # 사용자가 입력한 원문 질문
    messages: list[BaseMessage]  # 대화 메시지 히스토리

    # Request analysis
    intent: str  # supervisor가 해석한 사용자 의도
    task_type: str  # 요청 처리를 위한 작업 유형
    plan: list[str]  # supervisor가 세운 처리 계획

    # Supervisor routing
    next_agent: NextAgent  # 다음에 실행할 agent 또는 종료 상태
    completed_agents: list[str]  # 실행이 완료된 agent 목록
    retry_count: int  # evaluation 실패 등으로 재시도한 횟수

    # Character identity
    character_name: str  # 조회 대상 캐릭터 이름
    world_name: str  # 캐릭터가 속한 월드 이름
    ocid: str  # 외부 API에서 사용하는 캐릭터 고유 ID

    # Raw external results
    tool_results: dict[str, JsonValue]  # tool 호출 결과 원본
    raw_api_results: dict[str, JsonValue]  # 외부 API 응답 원본

    # Normalized character data
    character_profile: ProcessedCharacter  # 정규화된 캐릭터 기본 정보
    character_stats: CharacterStatDetail  # 정규화된 캐릭터 스탯 정보
    equipment_items: list[EquipmentDetail]  # 정규화된 장착 장비 목록
    union_status: UnionStatus  # 정규화된 유니온 정보

    # Search/RAG context
    retrieved_docs: list[RetrievedDocument]  # RAG 검색으로 가져온 문서 목록
    context: str  # 답변 생성에 사용할 병합 컨텍스트

    # Stat/equipment analysis
    stat_summary: dict[str, JsonValue]  # calculator가 만든 스탯 요약
    equipment_summary: dict[str, JsonValue]  # calculator가 만든 장비 요약
    bottleneck_analysis: dict[str, float]  # 성장 병목 요소와 점수

    # Growth recommendation
    growth_report: GrowthEfficiencyReport  # analystic이 만든 성장 효율 리포트
    recommended_actions: list[ActionPlan]  # 사용자에게 제안할 추천 액션 목록

    # Answer generation
    draft_answer: str  # final_answer agent가 만든 초안 답변
    final_answer: str  # 사용자에게 제공할 최종 답변

    # Validation/errors
    validation_passed: bool  # evaluation node의 최종 답변 통과 여부
    confidence_score: float  # evaluation node가 계산한 품질 점수
    feedback: str  # evaluation node가 남긴 보완 피드백
    retry_target: NextAgent  # evaluation 실패 시 다시 실행할 대상
    errors: list[str]  # 실행 중 발생한 오류 메시지 목록

    # Graph termination
    is_complete: bool  # 전체 그래프 처리 완료 여부

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
    "feedback",
    "retry_target",
    "errors",
    "is_complete",
]


class AgentFieldContract(TypedDict):
    required_inputs: tuple[AgentStateField, ...]
    optional_inputs: tuple[AgentStateField, ...]
    required_outputs: tuple[AgentStateField, ...]


# Field contract for each agent.
# Update this table whenever an agent or AgentState key changes.
AGENT_FIELD_CONTRACTS: dict[AgentName, AgentFieldContract] = {
    "supervisor": {
        "required_inputs": ("user_query", "messages"),
        "optional_inputs": (),
        "required_outputs": ("intent", "task_type", "plan", "next_agent"),
    },
    "calculator": {
        "required_inputs": (),
        "optional_inputs": ("character_stats", "equipment_items", "union_status"),
        "required_outputs": ("stat_summary", "equipment_summary", "bottleneck_analysis"),
    },
    "analystic": {
        "required_inputs": (),
        "optional_inputs": ("character_profile", "stat_summary", "equipment_summary"),
        "required_outputs": ("growth_report", "recommended_actions"),
    },
    "research": {
        "required_inputs": ("user_query", "character_name", "world_name"),
        "optional_inputs": (),
        "required_outputs": ("retrieved_docs", "context"),
    },
    "final_answer": {
        "required_inputs": ("user_query", "recommended_actions", "context"),
        "optional_inputs": (),
        "required_outputs": (
            "draft_answer",
            "final_answer",
        ),
    },
}
