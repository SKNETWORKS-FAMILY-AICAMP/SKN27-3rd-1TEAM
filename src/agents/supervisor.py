"""
메이플스토리 챗봇의 멀티 에이전트 supervisor 모듈.

이 supervisor는 다음과 같은 역할을 담당합니다:
  1. 사용자 질문의 의도(intent)와 작업 유형(task_type)을 분류
  2. 캐릭터 조회(Nexon Open API)가 필요한지, 외부 검색이 필요한지, 계산/분석이
     필요한지를 판단
  3. 하위 에이전트(research / calculator / analystic / final_answer)들의 실행 순서를
     담은 plan을 생성하고 다음 실행할 next_agent를 결정
  4. LLM 호출이 실패하거나 응답 파싱이 실패할 경우 keyword 기반 fallback 라우팅으로
     안전하게 대체

전체 흐름은 LLM이 결정한 plan을 다양한 규칙으로 검증/보정한 뒤 다시 AgentState dict에
반영하는 구조이며, 단일 supervisor 호출이 끝나면 LangGraph가 plan[0] 에이전트를 실행한 뒤
다시 supervisor로 돌아오게 됩니다.
"""

import json

from common.conversation import format_messages_for_prompt, is_conversation_recall_query
from common.state import AgentState, AgentName
from common.get_model import get_llm
from common.prompt import master_prompt

# === 상수: 작업 유형 / 트리거 키워드 ===

# LLM이 분류할 수 있는 task_type 화이트리스트.
# 이 dict의 key를 벗어난 값을 LLM이 반환하면 "unknown"으로 강제 치환한다.
TASK_TYPES = {
    "character_status_analysis": "캐릭터 상태/스펙/장비 분석",
    "recommendation": "추천(장비, 콘텐츠, 직업, 사냥터, 육성 방향 등)",
    "system_explanation": "게임 시스템 설명(스타포스, 아케인포스, 심볼, 추가 옵션 등)",
    "story_explanation": "게임 스토리/세계관/인물 설명",
    "reward_explanation": "보상/드랍/획득처 설명",
    "event_information": "이벤트 정보",
    "boss_strategy": "보스 공략/패턴/입장 조건/스펙컷 설명",
    "skill_explanation": "직업 스킬/코어강화/하이퍼스킬/6차 강화 설명",
    "quest_guide": "퀘스트/전직/길뚫 진행 방법 안내",
    "market_price": "아이템 시세/거래/메소마켓 정보",
    "patch_information": "패치노트/업데이트/밸런스 변경 정보",
    "general_qa": "분류가 애매한 메이플 일반 질문",
    "chitchat": "일상 대화/인사/비게임 질문",
    "unknown": "의도 불명확 또는 추가 질문 필요",
}

# 수치/효율/비교 등 계산기(calculator) 에이전트가 필요한지 판단할 때 사용하는 키워드.
# 예: "스타포스 25성 비용 얼마", "방무 차이", "보스 스펙컷" 같은 질문에서 매칭된다.
# LLM이 requires_calculation 판단에 실패해도 fallback 라우팅에서 이 키워드만으로
# calculator를 plan에 끼워 넣을 수 있게 한다.
CALCULATION_TRIGGER_KEYWORDS = [
    "얼마",
    "몇",
    "비용",
    "효율",
    "기대값",
    "확률",
    "데미지",
    "딜",
    "스펙컷",
    "전투력",
    "환산",
    "방무",
    "보공",
    "공격력",
    "마력",
    "주스탯",
    "비교",
    "차이",
    "증가량",
    "몇 개",
    "며칠",
    "걸려",
]


# 일상 대화/인사로 분류해 곧장 final_answer로 보내기 위한 패턴.
# 짧은 인사("안녕", "ㅎㅇ", "hi")나 감사 표현은 research/calculator를 거치지 않고
# 비용을 아낀다.
CHITCHAT_PATTERNS = (
    "안녕",
    "안녕하세요",
    "하이",
    "ㅎㅇ",
    "hello",
    "hi",
    "고마워",
    "감사",
    "땡큐",
    "잘자",
    "잘 자",
    "너 누구",
    "넌 누구",
)

# 에이전트 실행의 표준 순서: 외부 정보 수집(research) → 수치 계산(calculator) →
# 해석/추천(analystic) → 최종 답변 생성(final_answer).
# _finalize_plan에서 LLM이 만든 plan을 이 순서대로 재정렬할 때 기준으로 쓰인다.
AGENT_ORDER = ("research", "calculator", "analystic", "final_answer")

# 작업 유형을 agent capability로 변환할 때 쓰는 도메인 단위 분류.
# 사용자 입력 단어가 아니라 TASK_TYPES 의미 기준으로 plan 보정 여부를 판단한다.
PERSONAL_BENCHMARK_TASK_TYPES = {
    "character_status_analysis",
    "recommendation",
    "boss_strategy",
}

# LLM이 boolean 대신 문자열로 반환하는 경우(예: "true", "yes")를 boolean으로 변환하기 위한 집합.
TRUTHY_VALUES = {"true", "yes", "y", "1"}

# "내 캐릭터", "닉네임", "API 조회" 등 Nexon Open API 호출이 필요해 보이는 키워드.
# requires_character_lookup 플래그 결정에 사용된다.
CHARACTER_LOOKUP_KEYWORDS = (
    "내 캐릭터",
    "내캐릭",
    "내 스펙",
    "제 스펙",
    "내 장비",
    "제 장비",
    "내 전투력",
    "제 전투력",
    "내 주스탯",
    "제 주스탯",
    "내 유니온",
    "제 유니온",
    "닉네임",
    "캐릭터명",
    "캐릭터 조회",
    "캐릭터 정보",
    "캐릭터 스탯",
    "스탯조회",
    "스탯 조회",
    "스펙조회",
    "스펙 조회",
    "api조회",
    "api 조회",
    "API조회",
    "API 조회",
    "오픈api",
    "오픈 api",
    "전투력 조회",
    "장비 조회",
    "유니온 조회",
    "스펙 분석",
)
# CHARACTER_LOOKUP_KEYWORDS에는 안 걸렸지만, 본문에 캐릭터명이 포함되어 있을 가능성을
# 시사하는 보조 키워드. extract_character_name_from_query와 결합해 두 단계로 판정한다.
CHARACTER_NAME_HINT_KEYWORDS = (
    "닉네임",
    "캐릭터명",
    "캐릭터 이름",
    "캐릭 이름",
    "이름",
    "스펙",
    "스탯",
    "전투력",
    "장비",
    "유니온",
    "보스",
    "가능",
    "컷",
    "분석",
    "추천",
)
# 분석/추천 없이 "캐릭터 데이터만 그대로 보여줘" 류의 단순 API 조회를 식별하는 키워드.
# 이쪽으로 분류되면 research를 건너뛰고 calculator/analystic도 생략할 수 있다.
CHARACTER_DATA_LOOKUP_KEYWORDS = (
    "스탯조회",
    "스탯 조회",
    "스펙조회",
    "스펙 조회",
    "api조회",
    "api 조회",
    "API조회",
    "API 조회",
    "오픈api",
    "오픈 api",
    "캐릭터 조회",
    "캐릭터 정보",
    "캐릭터 스탯",
    "전투력 조회",
    "장비 조회",
    "유니온 조회",
)
# 캐릭터 데이터 조회에 더해 "추천/비교/가능 여부/계산" 같은 후처리가 필요함을
# 가리키는 키워드. simple_character_lookup인지 여부를 판별할 때 사용된다.
CHARACTER_PROCESSING_KEYWORDS = (
    "분석",
    "추천",
    "비교",
    "가능",
    "갈 수",
    "갈수",
    "보스",
    "효율",
    "계산",
    "컷",
    "성장",
    "개선",
    "바꿔",
    "뭐부터",
    "어떻게",
)
# 다른 에이전트(특히 research/final_answer)가 supervisor로 돌려보낸 feedback 문자열에
# 아래 마커가 포함되어 있으면 "검색 근거가 부족하다"는 신호로 해석하고 research를
# 다시 plan에 넣는다.
RESEARCH_FEEDBACK_MARKERS = (
    "missing_context",
    "no retrieved context",
    "retrieved_docs are empty",
    "contexts are empty",
    "web fallback",
    "근거",
)
# supervisor가 LLM에 재계획(replan)을 한 번 요청했음을 표시하는 마커.
# 이 마커가 feedback에 이미 들어 있으면 또 다시 LLM 재호출을 시도하지 않고
# 곧장 keyword 기반 fallback으로 research를 강제 삽입한다 (무한 루프 방지).
RESEARCH_REPLAN_MARKER = "plan omitted research"
EVALUATION_RESEARCH_FEEDBACK_MARKERS = (
    "not relevant",
    "not grounded",
    "has no source",
    "missing_source",
    "missing source",
    "question_mismatch",
    "question mismatch",
    "wrong_context",
    "wrong context",
    "context mismatch",
    "source missing",
)
EVALUATION_RESEARCH_FAILURE_TYPES = (
    "question_mismatch",
    "missing_context",
    "ungrounded",
    "missing_source",
    "invalid_source_reliability",
)
SUPERVISOR_RESEARCH_RETRY_RESULT_KEY = "supervisor_research_retry"
MAX_SUPERVISOR_RESEARCH_RETRY_COUNT = 1
# 위 replan을 요청할 때 LLM에게 전달할 영어 feedback 메시지.
# "research가 빠졌으니 다시 짜라, 근거 없으면 web fallback 써라"는 지시.
RESEARCH_REPLAN_FEEDBACK = (
    "requires_search is true, but the plan omitted research. "
    "Rebuild the remaining plan with research before final_answer. "
    "If local evidence is missing, research must use web fallback."
)


# === 분류 헬퍼: 질문 텍스트만 보고 즉시 판정할 수 있는 함수들 ===

def is_chitchat_query(query: str) -> bool:
    """질문이 일상 대화/인사인지 판단한다.

    공백을 제거한 compact 문자열이 CHITCHAT_PATTERNS와 정확히 일치하거나,
    짧은 문장(<=12자) 안에 패턴이 부분 포함되어 있으면 chitchat으로 본다.
    또한 "아까 뭐 물어봤지?" 같은 대화 회상 질문도 chitchat으로 묶어
    final_answer만으로 응답한다.
    """
    normalized = str(query or "").strip().lower()
    compact = "".join(normalized.split())
    if not compact:
        return False
    if is_conversation_recall_query(normalized):
        return True
    if compact in CHITCHAT_PATTERNS:
        return True
    if len(compact) <= 12 and any(pattern in normalized for pattern in CHITCHAT_PATTERNS):
        return True
    return False


def has_character_analysis_state(state: AgentState) -> bool:
    """analystic 에이전트가 동작할 수 있는 최소 정보가 state에 채워졌는지 확인한다.

    프로필/스탯요약/장비요약 세 가지가 모두 있어야 분석이 의미 있으므로,
    하나라도 비어 있으면 analystic을 plan에서 제거하는 데 사용된다.
    """
    return all(
        bool(state.get(key))
        for key in ("character_profile", "stat_summary", "equipment_summary")
    )


def has_character_lookup_state(state: AgentState) -> bool:
    """이미 Nexon API 조회가 끝나 캐릭터 데이터가 state에 있는지 여부.

    True면 requires_character_lookup을 다시 True로 만들지 않아 중복 API 호출을 막는다.
    """
    return bool(state.get("character_profile") and state.get("character_stats"))


def requires_character_lookup_query(query: str) -> bool:
    """질문 문자열이 Nexon Open API 캐릭터 조회를 필요로 하는지 추정한다.

    1단계: CHARACTER_LOOKUP_KEYWORDS에 직접 매칭되면 즉시 True.
    2단계: 직접 키워드는 없지만 CHARACTER_NAME_HINT_KEYWORDS가 있고, 본문에서
           실제 캐릭터명을 추출할 수 있으면 True. (예: "홍길동 보스 가능?")
    extract_character_name_from_query import 실패는 안전하게 False로 묻는다.
    """
    text = str(query or "").strip()
    if not text:
        return False
    normalized = text.lower()
    if any(keyword.lower() in normalized for keyword in CHARACTER_LOOKUP_KEYWORDS):
        return True
    if not any(keyword.lower() in normalized for keyword in CHARACTER_NAME_HINT_KEYWORDS):
        return False
    try:
        from src.collectors.nexon_api import extract_character_name_from_query

        return bool(extract_character_name_from_query(text))
    except Exception:
        # import 실패나 collector 내부 예외는 라우팅을 중단시키지 않도록 흡수한다.
        return False


def is_character_data_lookup_query(query: str) -> bool:
    """순수 캐릭터 데이터 조회(API 결과 그대로 보여주기) 질문인지 판단한다."""
    text = str(query or "").strip()
    normalized = text.lower()
    return any(keyword.lower() in normalized for keyword in CHARACTER_DATA_LOOKUP_KEYWORDS)


def requires_character_processing_query(query: str) -> bool:
    """조회 결과를 가지고 분석/추천/비교 같은 후처리가 필요한지 판단한다."""
    text = str(query or "").strip()
    normalized = text.lower()
    return any(keyword.lower() in normalized for keyword in CHARACTER_PROCESSING_KEYWORDS)


def coerce_bool(value) -> bool:
    """LLM/상태에서 들어오는 bool-like 값을 일관되게 bool로 해석한다."""
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in TRUTHY_VALUES


def response_bool(response_dict: dict, key: str) -> bool:
    return coerce_bool(response_dict.get(key, False))


def capability_bool(response_dict: dict, key: str) -> bool:
    capabilities = response_dict.get("required_capabilities") or {}
    if isinstance(capabilities, dict):
        return coerce_bool(capabilities.get(key, False))
    return coerce_bool(response_dict.get(key, False))


def has_research_evidence_state(state: AgentState) -> bool:
    return bool(str(state.get("context") or "").strip() or state.get("retrieved_docs"))


def evaluation_feedback_requires_research(state: AgentState, feedback: str) -> bool:
    if not str(feedback or "").strip():
        return False
    tool_results = state.get("tool_results") or {}
    evaluation_result = {}
    if isinstance(tool_results, dict):
        raw_evaluation_result = tool_results.get("evaluation") or {}
        if isinstance(raw_evaluation_result, dict):
            evaluation_result = raw_evaluation_result
    failure_type = str(evaluation_result.get("failure_type") or "").strip()
    if failure_type in EVALUATION_RESEARCH_FAILURE_TYPES:
        return True
    warnings = evaluation_result.get("warnings") or []
    warning_text = (
        " ".join(str(warning) for warning in warnings)
        if isinstance(warnings, list)
        else str(warnings)
    )
    lowered_feedback = str(feedback or "").lower()
    lowered_warning_text = warning_text.lower()
    return any(
        marker in lowered_feedback or marker in lowered_warning_text
        for marker in EVALUATION_RESEARCH_FEEDBACK_MARKERS
    )


def feedback_requires_research_signal(state: AgentState, feedback: str) -> bool:
    lowered_feedback = str(feedback or "").lower()
    return any(
        marker in lowered_feedback
        for marker in RESEARCH_FEEDBACK_MARKERS
    ) or evaluation_feedback_requires_research(state, feedback)


def supervisor_research_retry_count(state: AgentState) -> int:
    tool_results = state.get("tool_results") or {}
    if not isinstance(tool_results, dict):
        return 0
    retry_result = tool_results.get(SUPERVISOR_RESEARCH_RETRY_RESULT_KEY)
    if not isinstance(retry_result, dict):
        return 0
    try:
        return int(retry_result.get("count") or 0)
    except (TypeError, ValueError):
        return 0


def research_web_already_attempted(state: AgentState) -> bool:
    tool_results = state.get("tool_results") or {}
    if not isinstance(tool_results, dict):
        return False
    research_result = tool_results.get("research") or {}
    if not isinstance(research_result, dict):
        return False
    return bool(
        research_result.get("web_success")
        or research_result.get("web_fallback_used")
        or research_result.get("web_reason")
    )


def should_retry_research_after_evaluation(state: AgentState, feedback: str) -> bool:
    if not evaluation_feedback_requires_research(state, feedback):
        return False
    if research_web_already_attempted(state):
        return False
    return supervisor_research_retry_count(state) < MAX_SUPERVISOR_RESEARCH_RETRY_COUNT


def mark_supervisor_research_retry(
    state: AgentState,
    tool_results: dict,
    feedback: str,
) -> dict:
    retry_count = supervisor_research_retry_count(state) + 1
    updated_tool_results = dict(tool_results)
    updated_tool_results[SUPERVISOR_RESEARCH_RETRY_RESULT_KEY] = {
        "count": retry_count,
        "reason": "evaluation_feedback_requires_research",
        "feedback": str(feedback or "")[:500],
    }
    return updated_tool_results


def research_route_task_type(query: str, task_type: str) -> str:
    if is_chitchat_query(query):
        return ""
    normalized_task_type = str(task_type or "").strip()
    if normalized_task_type in {"", "unknown", "chitchat"}:
        return "general_qa"
    if normalized_task_type not in TASK_TYPES:
        return "general_qa"
    return normalized_task_type


def research_route_requires_evidence(
    query: str,
    task_type: str,
    *,
    requires_character_lookup: bool = False,
) -> bool:
    text = str(query or "").strip()
    if not text or is_chitchat_query(text):
        return False
    if requires_character_lookup and is_character_data_lookup_query(text):
        return False

    route_task_type = research_route_task_type(text, task_type)
    if not route_task_type:
        return False
    if route_task_type == "character_status_analysis" and is_character_data_lookup_query(text):
        return False

    from src.agents.research_agent import classify_research_route

    route = classify_research_route(text, task_type=route_task_type)
    return bool(route.get("use_db") or route.get("use_graph") or route.get("use_web"))


def agent_result_available(state: AgentState, agent: str) -> bool:
    if agent == "research":
        return has_research_evidence_state(state)
    if agent == "calculator":
        tool_results = state.get("tool_results") or {}
        return bool(
            state.get("stat_summary")
            or state.get("equipment_summary")
            or (isinstance(tool_results, dict) and tool_results.get("calculator"))
        )
    if agent == "analystic":
        return bool(state.get("growth_report") or state.get("recommended_actions"))
    if agent == "final_answer":
        return bool(str(state.get("final_answer") or "").strip())
    return False


def agent_already_satisfied(
    state: AgentState,
    agent: str,
    completed_agent: str | None,
) -> bool:
    return bool(
        completed_agent == agent
        or agent in list(state.get("completed_agents") or [])
        or agent_result_available(state, agent)
    )


def append_required_agent(
    plan: list[str],
    agent: str,
    state: AgentState,
    completed_agent: str | None,
) -> list[str]:
    if agent in plan or agent_already_satisfied(state, agent, completed_agent):
        return plan
    agent_order = AGENT_ORDER.index(agent)
    insert_at = len(plan)
    for index, planned_agent in enumerate(plan):
        if planned_agent in AGENT_ORDER and AGENT_ORDER.index(planned_agent) > agent_order:
            insert_at = index
            break
    return [*plan[:insert_at], agent, *plan[insert_at:]]


def infer_required_capabilities(
    state: AgentState,
    response_dict: dict,
    plan: list[str],
    task_type: str,
    requires_character_lookup: bool,
) -> dict[str, bool]:
    """Convert supervisor outputs and current state into workflow capabilities.

    This intentionally avoids matching user wording. The plan is derived from
    whether the answer needs current character data, external criteria, and a
    comparison/judgement step.
    """

    query_for_route = str(
        response_dict.get("contextualized_query")
        or state.get("contextualized_query")
        or state.get("user_query")
        or ""
    ).strip()
    needs_character_api = bool(
        capability_bool(response_dict, "needs_character_api")
        or requires_character_lookup
        or has_character_lookup_state(state)
    )
    try:
        route_needs_external_criteria = research_route_requires_evidence(
            query_for_route,
            task_type,
            requires_character_lookup=needs_character_api,
        )
    except Exception:
        route_needs_external_criteria = False

    needs_external_criteria = bool(
        capability_bool(response_dict, "needs_external_criteria")
        or response_bool(response_dict, "requires_search")
        or "research" in plan
        or has_research_evidence_state(state)
        or route_needs_external_criteria
    )
    needs_comparison = bool(
        capability_bool(response_dict, "needs_comparison")
        or (
            needs_character_api
            and needs_external_criteria
            and task_type in PERSONAL_BENCHMARK_TASK_TYPES
        )
    )
    needs_recommendation = bool(
        capability_bool(response_dict, "needs_recommendation")
        or response_bool(response_dict, "requires_analytics")
        or "analystic" in plan
    )
    needs_calculation = bool(
        response_bool(response_dict, "requires_calculation")
        or "calculator" in plan
        or needs_comparison
    )

    return {
        "needs_character_api": needs_character_api,
        "needs_external_criteria": needs_external_criteria,
        "needs_comparison": needs_comparison,
        "needs_recommendation": needs_recommendation,
        "needs_calculation": needs_calculation,
        "needs_interpretation": needs_comparison or needs_recommendation,
    }


def apply_capability_plan_guard(
    state: AgentState,
    response_dict: dict,
    plan: list[str],
    task_type: str,
    requires_character_lookup: bool,
    completed_agent: str | None,
) -> list[str]:
    capabilities = infer_required_capabilities(
        state,
        response_dict,
        plan,
        task_type,
        requires_character_lookup,
    )
    guarded_plan = list(plan)
    if capabilities["needs_external_criteria"]:
        guarded_plan = append_required_agent(guarded_plan, "research", state, completed_agent)
    if capabilities["needs_calculation"]:
        guarded_plan = append_required_agent(guarded_plan, "calculator", state, completed_agent)
    if capabilities["needs_interpretation"]:
        guarded_plan = append_required_agent(guarded_plan, "analystic", state, completed_agent)
    if "final_answer" not in guarded_plan:
        guarded_plan.append("final_answer")
    return guarded_plan


def _fallback_supervisor_response(state: AgentState, error: Exception | None = None) -> dict:
    """LLM supervisor가 실패했을 때 키워드/상태 기반으로 최소 plan을 만든다.

    이 함수는 답변 품질을 최고로 만드는 용도가 아니라, 그래프가 멈추지 않도록
    research/calculator/final_answer 중 필요한 최소 노드를 안전하게 고르는 fallback이다.
    """
    # 원문 질문과 맥락 보강 질문을 모두 확보한다. contextualized_query가 비어 있으면 user_query 사용.
    user_query = str(state.get("user_query") or "")
    contextualized_query = str(state.get("contextualized_query") or user_query).strip() or user_query
    # supervisor 재진입 시 기존 plan의 첫 항목은 방금 실행된 agent로 보고 나머지만 이어간다.
    existing_plan = list(state.get("plan") or [])
    feedback = str(state.get("feedback") or "")
    tool_results = dict(state.get("tool_results") or {})
    feedback_requires_research = feedback_requires_research_signal(state, feedback)
    retry_research_after_evaluation = should_retry_research_after_evaluation(state, feedback)
    completed_agents = list(state.get("completed_agents", []) or [])
    completed_agent = existing_plan[0] if existing_plan else None
    remaining_plan = existing_plan[1:] if existing_plan else []
    # 이미 context/retrieved_docs가 있으면 research를 다시 강제하지 않는다.
    has_research_evidence = bool(
        str(state.get("context") or "").strip()
        or state.get("retrieved_docs")
    )
    if completed_agent == "research" and has_research_evidence:
        feedback = ""
        tool_results.pop("evaluation", None)
        feedback_requires_research = False
        retry_research_after_evaluation = False
    requires_search = False
    # 계산 키워드는 LLM 없이도 판정 가능하므로 fallback에서 직접 체크한다.
    requires_calculation = any(keyword in contextualized_query for keyword in CALCULATION_TRIGGER_KEYWORDS)
    lookup_attempted = bool((state.get("tool_results") or {}).get("nexon_api"))
    requires_character_lookup = bool(
        state.get("requires_character_lookup")
        or requires_character_lookup_query(contextualized_query)
    )
    character_data_lookup = requires_character_lookup and is_character_data_lookup_query(contextualized_query)
    simple_character_lookup = (
        character_data_lookup
        and not requires_character_processing_query(contextualized_query)
    )
    if has_character_lookup_state(state) or lookup_attempted:
        requires_character_lookup = False
        character_data_lookup = False
        simple_character_lookup = False
    if character_data_lookup:
        feedback_requires_research = False
    task_type = "general_qa"
    errors = list(state.get("errors", []) or [])

    if completed_agent and completed_agent not in completed_agents:
        completed_agents.append(completed_agent)

    should_continue_plan = bool(
        existing_plan
        and (
            not feedback_requires_research
            or (has_research_evidence and not retry_research_after_evaluation)
        )
    )

    if is_chitchat_query(contextualized_query):
        # 잡담/대화 회상은 외부 검색 없이 final_answer만 실행한다.
        task_type = "chitchat"
        requires_character_lookup = False
        plan = ["final_answer"]
    elif should_continue_plan:
        # 정상 재진입이면 remaining_plan을 표준 순서에 맞춰 계속 진행한다.
        plan = [
            agent
            for agent in remaining_plan
            if agent in AGENT_ORDER
        ]
        if (
            "analystic" in plan
            and "calculator" not in plan
            and not has_character_analysis_state(state)
        ):
            plan = [agent for agent in plan if agent != "analystic"]
        if not plan:
            plan = ["final_answer"]
    elif character_data_lookup:
        # 캐릭터 데이터 단순 조회는 RAG 검색보다 Nexon API 결과를 우선한다.
        requires_search = False
        task_type = "character_status_analysis"
        if not simple_character_lookup:
            requires_calculation = True
        # 필요 신호를 순서대로 plan에 반영한다. final_answer는 항상 마지막에 붙인다.
        plan = []
        if requires_search or (
            feedback_requires_research
            and (not has_research_evidence or retry_research_after_evaluation)
        ):
            plan.append("research")
        if requires_calculation:
            plan.append("calculator")
        plan.append("final_answer")
    elif not character_data_lookup:
        try:
            # research route classifier는 DB/그래프/웹 검색 필요 여부를 빠르게 추정한다.
            from src.agents.research_agent import classify_research_route

            route_task_hint = str(state.get("task_type") or "general_qa").strip()
            route = classify_research_route(contextualized_query, task_type=route_task_hint)
            route_task_type = str(route.get("task_type") or "").strip()
            requires_search = bool(
                route.get("use_graph")
                or route.get("use_web")
                or (route.get("use_db") and route_task_type not in {"", "unknown"})
            )
            if requires_search:
                task_type = route_task_type if route_task_type in TASK_TYPES else "general_qa"
                if route.get("use_graph"):
                    task_type = "boss_strategy"
        except Exception as exc:
            errors.append(f"supervisor fallback route classification failed: {exc}")

        # 필요 신호를 순서대로 plan에 반영한다. final_answer는 항상 마지막에 붙인다.
        plan = []
        if requires_search or (
            feedback_requires_research
            and (not has_research_evidence or retry_research_after_evaluation)
        ):
            plan.append("research")
        if requires_calculation:
            plan.append("calculator")
        plan.append("final_answer")

    if character_data_lookup:
        # 캐릭터 API 조회형 질문에서는 research를 제거하고, 분석 필요 여부에 따라 calculator만 남긴다.
        plan = [agent for agent in plan if agent != "research"]
        if simple_character_lookup:
            plan = [agent for agent in plan if agent not in ("calculator", "analystic")]
        elif "calculator" not in plan:
            plan = ["calculator", *plan]
        task_type = "character_status_analysis"

    fallback_response_dict = {
        "requires_search": requires_search,
        "requires_calculation": requires_calculation,
        "requires_analytics": "analystic" in plan,
    }
    plan = apply_capability_plan_guard(
        state,
        fallback_response_dict,
        plan,
        task_type,
        requires_character_lookup,
        completed_agent,
    )

    if error is not None:
        errors.append(f"supervisor llm failed; used fallback route: {error}")

    if plan and plan[0] == "research" and retry_research_after_evaluation:
        tool_results = mark_supervisor_research_retry(state, tool_results, feedback)

    # supervisor 노드가 평소 반환하는 AgentState 필드와 같은 형태로 맞춰 downstream 노드를 단순화한다.
    return {
        **state,
        "intent": "fallback supervisor routing",
        "contextualized_query": contextualized_query,
        "task_type": task_type,
        "requires_character_lookup": requires_character_lookup,
        "plan": plan,
        "next_agent": plan[0],
        "feedback": feedback,
        "tool_results": tool_results,
        "completed_agents": completed_agents,
        "retry_count": state.get("retry_count", 0),
        "errors": errors,
    }


def _parse_supervisor_response(
    content,
    state: AgentState,
    remaining_plan: list[str],
    retry_count: int,
    errors: list[str],
) -> tuple[dict, str, str, bool, list[str], int, list[str]]:
    """LLM이 반환한 JSON 리스트를 supervisor 라우팅 필드로 파싱한다."""
    try:
        response_list = json.loads(content)
        if not isinstance(response_list, list):
            raise ValueError("supervisor response is not a JSON list")
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        # JSON 파싱 실패 시 원본 일부를 남겨 supervisor 라우팅 실패 원인을 추적
        retry_count += 1
        errors = [*errors, f"supervisor json parse failed: {exc}: {str(content)[:200]}"]
        response_list = []

    # [{"key": "...", "value": ...}] 형태를 dict로 납작하게 바꾼다.
    response_dict = {
        item.get("key"): item.get("value")
        for item in response_list
        if isinstance(item, dict)
    }

    # task_type은 화이트리스트 밖이면 unknown으로 강제해 downstream 분기를 단순화한다.
    intent = response_dict.get("intent", state.get("intent", ""))
    task_type = response_dict.get("task_type", state.get("task_type", "unknown"))
    if task_type not in TASK_TYPES:
        task_type = "unknown"

    # requires_character_lookup은 LLM이 문자열로 줄 수 있어 bool로 정규화한다.
    lookup_value = response_dict.get(
        "requires_character_lookup",
        state.get("requires_character_lookup", False),
    )
    requires_character_lookup = (
        lookup_value
        if isinstance(lookup_value, bool)
        else str(lookup_value).strip().lower() in TRUTHY_VALUES
    )
    lookup_query = str(
        response_dict.get("contextualized_query")
        or state.get("contextualized_query")
        or state.get("user_query")
        or ""
    )
    # LLM이 False로 놓쳐도 키워드/캐릭터명 추출 기준으로 한 번 더 보정한다.
    requires_character_lookup = (
        requires_character_lookup
        or requires_character_lookup_query(lookup_query)
        or requires_character_lookup_query(str(state.get("user_query") or ""))
    )
    lookup_attempted = bool((state.get("tool_results") or {}).get("nexon_api"))
    # 이미 조회 데이터가 있거나 조회 시도가 끝난 상태면 중복 API 호출을 막는다.
    if has_character_lookup_state(state) or lookup_attempted:
        requires_character_lookup = False

    plan = response_dict.get("plan")
    if plan is None:
        # LLM이 plan을 반환하지 못한 경우 기존 흐름을 최대한 유지
        retry_count += 1
        plan = remaining_plan
    elif not isinstance(plan, list):
        # plan은 반드시 list여야 하므로 형식이 틀리면 안전하게 final_answer로 보냄
        retry_count += 1
        plan = ["final_answer"]

    return response_dict, intent, task_type, requires_character_lookup, plan, retry_count, errors


def _guard_research_plan(
    state: AgentState,
    response_dict: dict,
    plan: list[str],
    completed_agent: str | None,
    feedback: str,
    retry_count: int,
    errors: list[str],
) -> tuple[list[str], int, list[str], AgentState | None]:
    """검색이 필요한데 plan에서 research가 빠진 경우 재계획 또는 강제 보정한다.

    Returns:
        (보정된 plan, retry_count, errors, replan_state)
        replan_state가 있으면 caller가 supervisor(replan_state)를 다시 호출한다.
    """
    # requires_search 역시 LLM이 문자열로 반환할 수 있어 bool로 정규화한다.
    requires_search = response_dict.get("requires_search")
    requires_search = (
        requires_search
        if isinstance(requires_search, bool)
        else str(requires_search).strip().lower() in TRUTHY_VALUES
    )
    contextualized_query = str(
        response_dict.get("contextualized_query")
        or state.get("contextualized_query")
        or state.get("user_query")
        or ""
    ).strip()
    task_type = str(response_dict.get("task_type") or state.get("task_type") or "").strip()
    route_requires_research = False
    try:
        route_requires_research = research_route_requires_evidence(
            contextualized_query,
            task_type,
            requires_character_lookup=(
                response_bool(response_dict, "requires_character_lookup")
                or coerce_bool(state.get("requires_character_lookup", False))
                or requires_character_lookup_query(contextualized_query)
            ),
        )
    except Exception as exc:
        errors = [*errors, f"supervisor route research guard failed: {exc}"]

    feedback_requires_research = feedback_requires_research_signal(state, feedback)
    retry_research_after_evaluation = should_retry_research_after_evaluation(state, feedback)
    has_research_evidence = bool(
        str(state.get("context") or "").strip()
        or state.get("retrieved_docs")
    )
    # 이미 research가 끝났고 근거가 있으면 같은 검색을 반복하지 않는다.
    research_already_done = (
        completed_agent == "research"
        or ("research" in state.get("completed_agents", []) and has_research_evidence)
    )
    if retry_research_after_evaluation:
        research_already_done = False
    # 검색 필요 신호가 있는데 plan에 research가 없고 아직 검색도 안 끝난 경우만 보정 대상.
    needs_research_replan = (
        (requires_search or route_requires_research or feedback_requires_research)
        and "research" not in plan
        and not research_already_done
    )

    if not needs_research_replan:
        return plan, retry_count, errors, None

    if retry_research_after_evaluation:
        errors = [*errors, "supervisor evaluation feedback required research retry"]
        plan = ["research", *[agent for agent in plan if agent != "research"]]
        return plan, retry_count, errors, None

    if route_requires_research and not requires_search:
        errors = [*errors, "supervisor task route required research; inserted research"]
        plan = ["research", *[agent for agent in plan if agent != "research"]]
        return plan, retry_count, errors, None

    if RESEARCH_REPLAN_MARKER not in feedback:
        # 첫 누락이면 바로 강제 삽입하지 않고 LLM에게 한 번 더 재계획 기회를 준다.
        retry_count += 1
        next_feedback = f"{feedback}\n{RESEARCH_REPLAN_FEEDBACK}" if feedback else RESEARCH_REPLAN_FEEDBACK
        replan_state = {
            **state,
            "plan": [],
            "feedback": next_feedback,
            "retry_count": retry_count,
            "errors": errors,
        }
        return plan, retry_count, errors, replan_state

    # 이미 한 번 재계획했는데도 빠졌다면 무한 루프 방지를 위해 research를 직접 앞에 삽입한다.
    retry_count += 1
    errors = [*errors, "supervisor replan still omitted research; applied research fallback"]
    plan = ["research", *[agent for agent in plan if agent != "research"]]
    return plan, retry_count, errors, None


def _finalize_plan(
    plan: list[str],
    state: AgentState,
    completed_agent: str | None,
    feedback: str,
) -> list[str]:
    """LLM/fallback이 만든 plan을 표준 실행 순서와 안전 규칙에 맞게 정리한다."""
    # 허용된 agent만 AGENT_ORDER 순서대로 남긴다.
    ordered_plan = [
        agent
        for agent in AGENT_ORDER
        if agent in plan
    ]

    if not ordered_plan and state.get("next_agent") in AGENT_ORDER:
        # plan이 비어도 이전 next_agent가 있으면 기존 라우팅을 이어감
        ordered_plan = [state["next_agent"]]

    if (
        "analystic" in ordered_plan
        and "calculator" not in ordered_plan
        and not has_character_analysis_state(state)
    ):
        # analystic은 calculator 산출물에 의존하므로 준비되지 않았으면 제거한다.
        ordered_plan = [agent for agent in ordered_plan if agent != "analystic"]

    if "final_answer" not in ordered_plan:
        # 어떤 흐름이든 사용자에게 답변을 돌려줘야 하므로 final_answer는 보장한다.
        ordered_plan.append("final_answer")

    if completed_agent and ordered_plan and ordered_plan[0] == completed_agent:
        # plan 첫 항목이 이미 실행된 agent면 feedback 유무와 관계없이 반복 실행을 막는다.
        ordered_plan = ordered_plan[1:]

    return ordered_plan or ["final_answer"]


def supervisor(state:AgentState):
    """사용자의 질문을 분석하여 의도를 파악하고, 작업 유형을 결정하고, 처리 계획을 세우고, 다음 에이전트를 결정합니다."""
    # 원문 질문과 현재까지의 contextualized_query를 준비한다.
    # contextualized_query는 대명사/생략 표현이 보강된 검색용 질문으로 쓰인다.
    user_query = str(state.get("user_query") or "")
    contextualized_query = str(state.get("contextualized_query") or user_query).strip() or user_query
    if is_chitchat_query(user_query):
        # 인사/짧은 잡담/대화 회상은 검색·계산 없이 final_answer만 실행한다.
        return {
            **state,
            "intent": "일상 대화 또는 인사",
            "contextualized_query": contextualized_query,
            "task_type": "chitchat",
            "requires_character_lookup": False,
            "plan": ["final_answer"],
            "next_agent": "final_answer",
            "completed_agents": state.get("completed_agents", []),
            "retry_count": state.get("retry_count", 0),
            "errors": state.get("errors", []),
        }

    # 일반 질문은 LLM supervisor가 의도/필요 도구/plan을 판단한다.
    llm = get_llm()

    existing_plan = list(state.get("plan") or [])
    feedback = str(state.get("feedback", "") or "")
    tool_results = dict(state.get("tool_results") or {})
    retry_count = int(state.get("retry_count", 0) or 0)
    errors = list(state.get("errors", []) or [])

    completed_agent = None
    remaining_plan = []

    if existing_plan:
        # supervisor로 다시 돌아온 경우, plan의 첫 번째 agent는 방금 실행된 agent로 보고 제거
        completed_agent = existing_plan[0]
        remaining_plan = existing_plan[1:]

    if (
        completed_agent == "research"
        and (
            str(state.get("context") or "").strip()
            or state.get("retrieved_docs")
        )
    ):
        feedback = ""
        tool_results.pop("evaluation", None)


    # 최근 대화 메시지를 텍스트로 변환해 supervisor가 생략 표현을 보강할 수 있게 한다.
    messages = state["messages"]
    formatted_messages = format_messages_for_prompt(messages)
    # prompt는 JSON 리스트만 반환하도록 강하게 제한한다.
    # 파싱 실패 시 _parse_supervisor_response에서 retry_count를 올리고 fallback plan으로 이어간다.
    prompt = f"""
# System
당신은 메이플스토리 게임 전문가이자 agent에게 지시를 내리는 supervisor입니다.
사용자의 질문을 분석하여 의도를 파악하고, 작업 유형을 결정하고, 처리 계획을 세우고, 다음 에이전트를 결정합니다.


# Rules
다음과 같은 규칙을 지켜주세요.
{master_prompt}

아래의 목록에서만 에이전트를 결정할 수 있습니다.
{AgentName}

아래의 형식에 맞춰 사용자의 질문을 분류하고 plan을 세웁니다.
- task_type은 반드시 아래 TASK_TYPES의 key 중 하나만 선택합니다.
- intent는 task_type key가 아니라, 사용자의 질문 의도를 한 문장으로 요약한 자연어입니다.
- task_type을 새로 만들거나 TASK_TYPES에 없는 값을 사용하지 않습니다.
- 보스/캐릭터 이름이 포함되어도 질문의 중심이 스토리, 세계관, 인물 배경 설명이면 boss_strategy가 아니라 story_explanation을 선택합니다.
- story_explanation은 DB/RAG 근거가 필요한 게임 지식 설명이므로 requires_search=True로 두고 research를 plan에 포함합니다.
- general_qa처럼 메이플 지식 자체를 묻는 질문도 DB/RAG 근거가 필요하므로 requires_search=True로 두고 research를 plan에 포함합니다.

TASK_TYPES:
{TASK_TYPES}

"requires_search" : 최신 정보, 외부 정보, DB/RAG 조회가 필요한 경우 True, 필요하지 않은 경우 False
"requires_character_lookup" : 특정 유저 캐릭터의 현재 스펙, 장비, 전투력, 유니온, 보스 가능 여부처럼 Nexon Open API 캐릭터 조회가 필요한 경우 True, 일반 보스 정보/보상/요구 스탯처럼 캐릭터 조회가 필요 없는 경우 False
"requires_calculation" : 사용자 질문에 {CALCULATION_TRIGGER_KEYWORDS}가 포함되어 있거나 calculator가 필요한 경우 True, 필요하지 않은 경우 False
"requires_analytics" : 캐릭터 상태, 장비, 스펙, 선택지 비교, 성장 방향 판단처럼 analystic의 해석이 필요한 경우 True, 필요하지 않은 경우 False
"required_capabilities" : 아래 capability를 구조화합니다. 단어 매칭이 아니라 답변에 필요한 작업 의존성 기준입니다.
  - needs_character_api: 현재 특정 캐릭터의 Nexon API 데이터가 필요하면 true
  - needs_external_criteria: 보스 요구치, 장비 기준, 이벤트/공지, 게임 지식처럼 외부 기준/근거 조회가 필요하면 true
  - needs_comparison: 현재 캐릭터 데이터와 외부 기준/다른 선택지를 비교해 가능 여부, 우선순위, 적합도를 판단해야 하면 true
  - needs_recommendation: 단순 사실 전달을 넘어 성장 방향/액션/판정 문구가 필요하면 true
"contextualized_query" : 원문 질문이 이전 대화의 지시어/생략 표현에 의존하면 messages를 참고해 검색과 판단에 쓸 수 있는 완전한 질문으로 다시 씁니다. 독립 질문이면 원문과 동일하게 둡니다.

#plan
plan에는 아래 목록의 에이전트만 포함할 수 있습니다.
{AgentName}

에이전트 실행 순서는 research -> calculator -> analystic -> final_answer 입니다.
- requires_search가 True이면 research를 추가합니다.
- requires_calculation이 True이면 calculator를 추가합니다.
- requires_analytics가 True이면 analystic을 추가합니다.
- required_capabilities.needs_external_criteria=True이면 research가 필요합니다.
- required_capabilities.needs_character_api=True이고 needs_comparison=True이면 calculator가 필요합니다.
- required_capabilities.needs_comparison=True 또는 needs_recommendation=True이면 analystic이 필요합니다.
- requires_character_lookup은 plan에 nexon_api를 추가하지 않고 state에만 저장합니다.
- 캐릭터 스탯조회/API조회/캐릭터 정보 조회처럼 특정 캐릭터의 현재 API 데이터만 필요한 단순 조회 질문은 requires_character_lookup=True, requires_search=False로 두고 final_answer만 실행합니다.
- 캐릭터 조회가 필요하더라도 분석/추천/비교/보스 가능 여부 판단이 함께 있으면 calculator 또는 analystic을 추가합니다.
- final_answer는 항상 plan의 마지막에 추가합니다.
- next_agent는 plan의 첫 번째 에이전트입니다.
- 처음 실행이면 사용자 질문을 기준으로 새 plan을 만듭니다.
- 재실행이면 completed_agent는 이미 실행된 것으로 보고 remaining_plan에서 다음 plan을 결정합니다.
- feedback이 있으면 feedback을 반영해 remaining_plan에 필요한 에이전트를 추가하거나 순서를 조정합니다.
- 재실행 시 plan은 이미 완료된 completed_agent를 제외한 남은 에이전트 리스트로 반환합니다.

# Current routing state
completed_agent: {completed_agent}
remaining_plan: {remaining_plan}
feedback: {feedback}

# User
원문 질문 user_query: {user_query}
현재 contextualized_query: {contextualized_query}
대화 메시지 messages:
{formatted_messages}

#output format
아래 JSON 리스트 형식으로만 답변하세요.
[
  {{"key": "intent", "value": "사용자 질문 의도 요약"}},
  {{"key": "contextualized_query", "value": "맥락을 반영해 완성한 질문. 독립 질문이면 원문과 동일"}},
  {{"key": "task_type", "value": "TASK_TYPES key 중 하나"}},
  {{"key": "requires_search", "value": true}},
  {{"key": "requires_character_lookup", "value": false}},
  {{"key": "requires_analytics", "value": false}},
  {{"key": "requires_calculation", "value": false}},
  {{"key": "required_capabilities", "value": {{"needs_character_api": false, "needs_external_criteria": false, "needs_comparison": false, "needs_recommendation": false}}}},
  {{"key": "plan", "value": ["에이전트명", "에이전트명", ...]}},
  {{"key": "next_agent", "value": "plan의 첫 번째 에이전트. 만약 plan이 비어있다면 final_answer"}}
]
"""

    try:
        response = llm.invoke(prompt)
        content = getattr(response, "content", response)
    except Exception as exc:
        # LLM 호출 자체가 실패하면 키워드 기반 fallback 라우팅으로 진행한다.
        return _fallback_supervisor_response(state, exc)

    # LLM 응답을 정규화된 supervisor 필드들로 변환한다.
    (
        response_dict,
        intent,
        task_type,
        requires_character_lookup,
        plan,
        retry_count,
        errors,
    ) = _parse_supervisor_response(
        content,
        state,
        remaining_plan,
        retry_count,
        errors,
    )
    # contextualized_query는 LLM 결과를 우선하되, 없으면 기존 state/원문으로 폴백한다.
    contextualized_query = str(
        response_dict.get("contextualized_query")
        or state.get("contextualized_query")
        or user_query
    ).strip() or user_query
    # 캐릭터 데이터 단순 조회는 research를 끼우지 않는 별도 흐름으로 다룬다.
    character_data_lookup = (
        requires_character_lookup
        and is_character_data_lookup_query(contextualized_query)
    )
    simple_character_lookup = (
        character_data_lookup
        and not requires_character_processing_query(contextualized_query)
    )
    if character_data_lookup:
        response_dict["requires_search"] = False
        task_type = "character_status_analysis"

    # 검색이 필요한데 plan에 누락된 경우 재계획하거나 research를 강제 삽입한다.
    plan, retry_count, errors, replan_state = _guard_research_plan(
        state,
        response_dict,
        plan,
        completed_agent,
        "" if character_data_lookup else feedback,
        retry_count,
        errors,
    )
    if replan_state:
        # 첫 누락은 feedback을 더해 supervisor를 한 번 재호출한다.
        return supervisor(replan_state)

    if character_data_lookup:
        # API 조회형 질문은 RAG를 제거하고, 단순 조회면 계산/분석도 제거한다.
        plan = [agent for agent in plan if agent != "research"]
        if simple_character_lookup:
            plan = [agent for agent in plan if agent not in ("calculator", "analystic")]
        elif "calculator" not in plan:
            plan = ["calculator", *plan]

    plan = apply_capability_plan_guard(
        state,
        response_dict,
        plan,
        task_type,
        requires_character_lookup,
        completed_agent,
    )

    # agent 순서/중복/최종답변 보장을 마지막으로 정리한다.
    plan = _finalize_plan(
        plan,
        state,
        completed_agent,
        "" if character_data_lookup else feedback,
    )

    next_agent = response_dict.get("next_agent") or plan[0]
    if next_agent != plan[0]:
        # next_agent와 plan[0]이 어긋나면 plan을 진실의 원천으로 사용한다.
        errors = [*errors, "supervisor next_agent did not match first plan item; using plan[0]"]
        next_agent = plan[0]

    completed_agents = state.get("completed_agents", [])
    if completed_agent and completed_agent not in completed_agents:
        # 이번 supervisor 재진입 직전에 끝난 agent를 완료 목록에 기록한다.
        completed_agents = [*completed_agents, completed_agent]

    if next_agent == "research" and should_retry_research_after_evaluation(state, feedback):
        tool_results = mark_supervisor_research_retry(state, tool_results, feedback)

    # downstream 노드가 읽을 라우팅 필드를 state에 병합해 반환한다.
    return {
        **state,
        "intent": intent,
        "contextualized_query": contextualized_query,
        "task_type": task_type,
        "requires_character_lookup": requires_character_lookup,
        "plan": plan,
        "next_agent": next_agent,
        "feedback": feedback,
        "tool_results": tool_results,
        "completed_agents": completed_agents,
        "retry_count": retry_count,
        "errors": errors,
    }
