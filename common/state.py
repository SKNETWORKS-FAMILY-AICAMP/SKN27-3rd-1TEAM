from typing import Any, Literal, TypedDict

from common.domain import (
    ActionPlan,
    CharacterStatDetail,
    EquipmentDetail,
    GrowthEfficiencyReport,
    ProcessedCharacter,
    UnionStatus,
)


NextAgent = Literal[
    "character_collector",
    "equipment_analyzer",
    "stat_analyzer",
    "growth_planner",
    "answer_generator",
    "FINISH",
]


class AgentState(TypedDict, total=False):
    # 공통 입력
    # 사용자가 입력한 질문과 LangGraph 메시지 히스토리를 저장한다.
    user_query: str
    messages: list[Any]

    # 사용자 요청 분석
    # supervisor가 어떤 작업인지 판단하고 필요한 정보 수집 계획을 세울 때 사용한다.
    intent: str
    task_type: str
    plan: list[str]

    # supervisor 라우팅
    # supervisor가 다음에 호출할 worker agent를 고른 결과다.
    next_agent: NextAgent
    completed_agents: list[str]
    retry_count: int

    # 캐릭터 식별 정보
    # Nexon API 조회나 캐릭터 분석의 기준이 되는 값이다.
    character_name: str
    world_name: str
    ocid: str

    # 외부 조회 원본 결과
    # API, DB, tool 호출 결과를 원본에 가깝게 보관한다.
    tool_results: dict[str, Any]
    raw_api_results: dict[str, Any]

    # 캐릭터 정규화 결과
    # 여러 API 응답을 분석하기 쉬운 도메인 모델로 정리한 값이다.
    character_profile: ProcessedCharacter
    character_stats: CharacterStatDetail
    equipment_items: list[EquipmentDetail]
    union_status: UnionStatus

    # 검색/RAG 컨텍스트
    # 가이드 문서나 정책 문서 검색 결과와 답변 생성용 요약 context를 담는다.
    retrieved_docs: list[dict[str, Any]]
    context: str

    # 스탯/장비 분석 결과
    # 현재 캐릭터의 강점, 약점, 병목 구간을 분석한 결과다.
    stat_summary: dict[str, Any]
    equipment_summary: dict[str, Any]
    bottleneck_analysis: dict[str, float]

    # 성장 추천 결과
    # 성장 효율 리포트와 사용자가 바로 실행할 수 있는 추천 액션 목록이다.
    growth_report: GrowthEfficiencyReport
    recommended_actions: list[ActionPlan]

    # 응답 생성
    # 초안과 최종 사용자 응답을 분리해서 검증/수정 단계를 거칠 수 있게 한다.
    draft_answer: str
    final_answer: str

    # 검증/예외
    # 답변 품질 판단, 재시도 여부, 에러 정보를 저장한다.
    validation_passed: bool
    confidence_score: float
    errors: list[str]

    # 종료 제어
    # supervisor가 그래프를 종료해도 되는지 판단할 때 사용한다.
    is_complete: bool
