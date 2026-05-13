import json

from common.state import AgentState, AgentName
from common.get_model import get_llm
from common.prompt import master_prompt

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



def has_character_analysis_state(state: AgentState) -> bool:
    return all(
        bool(state.get(key))
        for key in ("character_profile", "stat_summary", "equipment_summary")
    )


def _state_query_text(state: AgentState) -> str:
    values = [str(state.get("user_query") or "")]
    for message in state.get("messages", []) or []:
        values.append(str(getattr(message, "content", message)))
    return " ".join(values).lower()


def _contains_any(text: str, keywords: tuple[str, ...]) -> bool:
    return any(keyword.lower() in text for keyword in keywords)


def _looks_like_boss_readiness_query(state: AgentState) -> bool:
    text = _state_query_text(state)
    has_boss = _contains_any(
        text,
        (
            "보스",
            "검마",
            "검은 마법사",
            "검은마법사",
            "카링",
            "칼로스",
            "세렌",
            "루시드",
            "윌",
            "스우",
            "데미안",
            "진힐라",
            "듄켈",
            "더스크",
        ),
    )
    asks_readiness = _contains_any(
        text,
        ("가능", "될까", "되나", "클리어", "잡을", "깰", "격파", "도전"),
    )
    has_character = bool(state.get("character_profile") or state.get("character_name")) or _contains_any(
        text,
        ("내 캐릭터", "캐릭터명", "닉네임"),
    )
    return has_character and has_boss and asks_readiness


def _looks_like_calculation_query(state: AgentState) -> bool:
    return _contains_any(
        _state_query_text(state),
        (
            "계산",
            "효율",
            "비용",
            "기간",
            "전투력",
            "데미지 점수",
            "스펙",
            "주스탯",
            "장비",
            "강화",
            "스타포스",
            "병목",
        ),
    )


def _looks_like_explanation_query(state: AgentState) -> bool:
    text = _state_query_text(state)
    has_topic = _contains_any(
        text,
        (
            "검마",
            "검은 마법사",
            "검은마법사",
            "카링",
            "칼로스",
            "세렌",
            "루시드",
            "윌",
            "스우",
            "데미안",
            "진힐라",
            "듄켈",
            "더스크",
            "스토리",
            "세계관",
        ),
    )
    asks_explanation = _contains_any(
        text,
        ("뭐야", "무엇", "누구", "설명", "알려", "스토리", "세계관", "정체"),
    )
    return has_topic and asks_explanation


def _normalise_plan_order(plan: list[str]) -> list[str]:
    ordered_plan = []
    for agent in ["research", "calculator", "analystic", "final_answer"]:
        if agent in plan and agent not in ordered_plan:
            ordered_plan.append(agent)
    return ordered_plan


def _has_usable_calculator_state(state: AgentState) -> bool:
    tool_results = state.get("tool_results") or {}
    result = tool_results.get("calculator") if isinstance(tool_results, dict) else {}
    stat_summary = state.get("stat_summary") or {}
    equipment_summary = state.get("equipment_summary") or {}
    return (
        isinstance(result, dict)
        and not result.get("error")
        and stat_summary.get("data_reliability") != "calculation_failed_or_missing_data"
        and bool(stat_summary.get("damage_score") or equipment_summary.get("equipment_count"))
    )


def _has_usable_analytics_state(state: AgentState) -> bool:
    tool_results = state.get("tool_results") or {}
    result = tool_results.get("analystic") if isinstance(tool_results, dict) else {}
    return (
        isinstance(result, dict)
        and not result.get("error")
        and result.get("data_reliability") != "analysis_failed_or_missing_data"
        and bool(
            result.get("clear_status")
            or result.get("boss_requirements")
            or result.get("available_bosses")
            or result.get("boss_clear_prediction")
        )
    )


def _apply_deterministic_routing(state: AgentState, plan: list[str]) -> list[str]:
    if _looks_like_boss_readiness_query(state):
        plan = [agent for agent in plan if agent != "research"]
        if _has_usable_calculator_state(state):
            plan = [agent for agent in plan if agent != "calculator"]
        else:
            plan.append("calculator")
        if _has_usable_analytics_state(state):
            plan = [agent for agent in plan if agent != "analystic"]
        else:
            plan.append("analystic")
    elif _looks_like_calculation_query(state):
        if _has_usable_calculator_state(state):
            plan = [agent for agent in plan if agent != "calculator"]
        else:
            plan.append("calculator")
    elif _looks_like_explanation_query(state):
        if state.get("context") or state.get("retrieved_docs"):
            plan = [agent for agent in plan if agent != "research"]
        else:
            plan.append("research")
    if "final_answer" not in plan:
        plan.append("final_answer")
    return _normalise_plan_order(plan)


def supervisor(state:AgentState):
    """사용자의 질문을 분석하여 의도를 파악하고, 작업 유형을 결정하고, 처리 계획을 세우고, 다음 에이전트를 결정합니다."""
    existing_plan = state.get("plan") or []
    feedback = state.get("feedback", "")
    retry_count = state.get("retry_count", 0)
    errors = state.get("errors", [])
    tool_results = state.get("tool_results") or {}
    evaluation_result = (
        tool_results.get("evaluation") if isinstance(tool_results, dict) else {}
    )
    is_evaluation_retry = (
        state.get("retry_target") == "supervisor"
        and state.get("validation_passed") is False
        and bool(evaluation_result)
    )
    if not feedback and isinstance(evaluation_result, dict):
        feedback = str(
            evaluation_result.get("feedback")
            or evaluation_result.get("reason")
            or ""
        )

    completed_agent = None
    remaining_plan = []

    if is_evaluation_retry:
        remaining_plan = existing_plan
    elif existing_plan:
        # supervisor로 다시 돌아온 경우, plan의 첫 번째 agent는 방금 실행된 agent로 보고 제거
        completed_agent = existing_plan[0]
        remaining_plan = existing_plan[1:]

    if existing_plan and not is_evaluation_retry:
        plan = _normalise_plan_order(remaining_plan) or ["final_answer"]
        completed_agents = state.get("completed_agents", [])
        if completed_agent and completed_agent not in completed_agents:
            completed_agents = [*completed_agents, completed_agent]
        return {
            **state,
            "plan": plan,
            "next_agent": plan[0],
            "completed_agents": completed_agents,
            "retry_count": retry_count,
            "errors": errors,
        }

    if (
        _looks_like_boss_readiness_query(state)
        or _looks_like_calculation_query(state)
        or _looks_like_explanation_query(state)
    ):
        is_boss_query = _looks_like_boss_readiness_query(state)
        is_explanation_query = _looks_like_explanation_query(state)
        plan = _apply_deterministic_routing(state, remaining_plan)
        completed_agents = state.get("completed_agents", [])
        if completed_agent and completed_agent not in completed_agents:
            completed_agents = [*completed_agents, completed_agent]
        return {
            **state,
            "intent": (
                "캐릭터 스펙으로 보스 도전 가능 여부를 판단"
                if is_boss_query
                else "게임 세계관 또는 보스 정보를 설명"
                if is_explanation_query
                else "캐릭터 스펙 계산 및 성장 병목 분석"
            ),
            "task_type": (
                "boss_strategy"
                if is_boss_query
                else "story_explanation"
                if is_explanation_query
                else "character_status_analysis"
            ),
            "plan": plan,
            "next_agent": plan[0],
            "completed_agents": completed_agents,
            "retry_count": retry_count,
            "errors": errors,
        }

    messages = state["messages"]
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

TASK_TYPES:
{TASK_TYPES}

"requires_search" : 최신 정보, 외부 정보, DB/RAG 조회가 필요한 경우 True, 필요하지 않은 경우 False
"requires_calculation" : 사용자 질문에 {CALCULATION_TRIGGER_KEYWORDS}가 포함되어 있거나 calculator가 필요한 경우 True, 필요하지 않은 경우 False
"requires_analytics" : 캐릭터 상태, 장비, 스펙, 선택지 비교, 성장 방향 판단처럼 analystic의 해석이 필요한 경우 True, 필요하지 않은 경우 False

#plan
plan에는 아래 목록의 에이전트만 포함할 수 있습니다.
{AgentName}

에이전트 실행 순서는 research -> calculator -> analystic -> final_answer 입니다.
- requires_search가 True이면 research를 추가합니다.
- requires_analytics가 True이면 analystic을 추가합니다.
- requires_calculation이 True이면 calculator를 추가합니다.
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
사용자의 질문: {messages}

#output format
아래 JSON 리스트 형식으로만 답변하세요.
[
  {{"key": "intent", "value": "사용자 질문 의도 요약"}},
  {{"key": "task_type", "value": "TASK_TYPES key 중 하나"}},
  {{"key": "requires_search", "value": true}},
  {{"key": "requires_analytics", "value": false}},
  {{"key": "requires_calculation", "value": false}},
  {{"key": "plan", "value": ["에이전트명", "에이전트명", ...]}},
  {{"key": "next_agent", "value": "plan의 첫 번째 에이전트. 만약 plan이 비어있다면 final_answer"}}
]
"""

    llm = get_llm()
    response = llm.invoke(prompt)
    content = getattr(response, "content", response)

    try:
        response_list = json.loads(content)
    except json.JSONDecodeError:
        # JSON 파싱 실패 시 원본 일부를 남겨 supervisor 라우팅 실패 원인을 추적
        retry_count += 1
        errors = [*errors, f"supervisor json parse failed: {str(content)[:200]}"]
        response_list = []

    response_dict = {}
    for item in response_list:
        key = item.get("key")
        value = item.get("value")
        response_dict[key] = value

    intent = response_dict.get("intent", state.get("intent", ""))
    task_type = response_dict.get("task_type", state.get("task_type", "unknown"))
    if task_type not in TASK_TYPES:
        task_type = "unknown"

    if existing_plan and not is_evaluation_retry:
        plan = remaining_plan
    else:
        plan = response_dict.get("plan")
    if plan is None:
        # LLM이 plan을 반환하지 못한 경우 기존 흐름을 최대한 유지
        retry_count += 1
        plan = remaining_plan

    if not isinstance(plan, list):
        # plan은 반드시 list여야 하므로 형식이 틀리면 안전하게 final_answer로 보냄
        retry_count += 1
        plan = ["final_answer"]

    # 에이전트 실행 순서 고정
    plan = _normalise_plan_order(plan)
    if not (existing_plan and not is_evaluation_retry):
        plan = _apply_deterministic_routing(state, plan)
    if not plan and state.get("next_agent") in ["research", "analystic", "calculator", "final_answer"]:
        # plan이 비어도 이전 next_agent가 있으면 기존 라우팅을 이어감
        plan = [state["next_agent"]]

    if "final_answer" not in plan:
        plan.append("final_answer")

    if completed_agent and not feedback and plan and plan[0] == completed_agent:
        # feedback 없이 정상 진행 중이면 이미 실행한 agent를 다시 실행하지 않도록 제거
        plan = plan[1:]

    if not plan:
        plan = ["final_answer"]

    next_agent = plan[0]

    completed_agents = state.get("completed_agents", [])
    if completed_agent and completed_agent not in completed_agents:
        completed_agents = [*completed_agents, completed_agent]

    return {
        **state,
        "intent": intent,
        "task_type": task_type,
        "plan": plan,
        "next_agent": next_agent,
        "completed_agents": completed_agents,
        "retry_count": retry_count,
        "errors": errors,
    }
