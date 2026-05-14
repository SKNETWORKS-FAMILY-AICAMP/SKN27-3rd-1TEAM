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

AGENT_ORDER = ("research", "calculator", "analystic", "final_answer")
TRUTHY_VALUES = {"true", "yes", "y", "1"}
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
    "내가",
    "제가",
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
RESEARCH_FEEDBACK_MARKERS = (
    "missing_context",
    "no retrieved context",
    "retrieved_docs are empty",
    "contexts are empty",
    "web fallback",
    "근거",
)
RESEARCH_REPLAN_MARKER = "plan omitted research"
RESEARCH_REPLAN_FEEDBACK = (
    "requires_search is true, but the plan omitted research. "
    "Rebuild the remaining plan with research before final_answer. "
    "If local evidence is missing, research must use web fallback."
)


def is_chitchat_query(query: str) -> bool:
    normalized = str(query or "").strip().lower()
    compact = "".join(normalized.split())
    if not compact:
        return False
    if compact in CHITCHAT_PATTERNS:
        return True
    if len(compact) <= 12 and any(pattern in normalized for pattern in CHITCHAT_PATTERNS):
        return True
    return False


def has_character_analysis_state(state: AgentState) -> bool:
    return all(
        bool(state.get(key))
        for key in ("character_profile", "stat_summary", "equipment_summary")
    )


def has_character_lookup_state(state: AgentState) -> bool:
    return bool(state.get("character_profile") and state.get("character_stats"))


def requires_character_lookup_query(query: str) -> bool:
    text = str(query or "").strip()
    if not text:
        return False
    normalized = text.lower()
    if any(keyword.lower() in normalized for keyword in CHARACTER_LOOKUP_KEYWORDS):
        return True
    try:
        from src.collectors.nexon_api import extract_character_name_from_query

        return bool(extract_character_name_from_query(text))
    except Exception:
        return False


def is_character_data_lookup_query(query: str) -> bool:
    text = str(query or "").strip()
    normalized = text.lower()
    return any(keyword.lower() in normalized for keyword in CHARACTER_DATA_LOOKUP_KEYWORDS)


def requires_character_processing_query(query: str) -> bool:
    text = str(query or "").strip()
    normalized = text.lower()
    return any(keyword.lower() in normalized for keyword in CHARACTER_PROCESSING_KEYWORDS)


def _fallback_supervisor_response(state: AgentState, error: Exception | None = None) -> dict:
    user_query = str(state.get("user_query") or "")
    existing_plan = list(state.get("plan") or [])
    feedback = str(state.get("feedback") or "")
    feedback_requires_research = any(
        marker in feedback.lower()
        for marker in RESEARCH_FEEDBACK_MARKERS
    )
    completed_agents = list(state.get("completed_agents", []) or [])
    completed_agent = existing_plan[0] if existing_plan else None
    remaining_plan = existing_plan[1:] if existing_plan else []
    has_research_evidence = bool(
        str(state.get("context") or "").strip()
        or state.get("retrieved_docs")
    )
    requires_search = False
    requires_calculation = any(keyword in user_query for keyword in CALCULATION_TRIGGER_KEYWORDS)
    lookup_attempted = bool((state.get("tool_results") or {}).get("nexon_api"))
    requires_character_lookup = bool(
        state.get("requires_character_lookup")
        or requires_character_lookup_query(user_query)
    )
    character_data_lookup = requires_character_lookup and is_character_data_lookup_query(user_query)
    simple_character_lookup = (
        character_data_lookup
        and not requires_character_processing_query(user_query)
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

    if is_chitchat_query(user_query):
        task_type = "chitchat"
        requires_character_lookup = False
        plan = ["final_answer"]
    elif existing_plan and (not feedback_requires_research or has_research_evidence):
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
    else:
        if character_data_lookup:
            requires_search = False
            task_type = "character_status_analysis"
            if not simple_character_lookup:
                requires_calculation = True
        else:
            try:
                from src.agents.research_agent import classify_research_route

                route = classify_research_route(user_query)
                requires_search = bool(route.get("use_graph") or route.get("use_web"))
                if requires_search:
                    task_type = "boss_strategy" if route.get("use_graph") else "general_qa"
            except Exception as exc:
                errors.append(f"supervisor fallback route classification failed: {exc}")

        plan = []
        if requires_search or (feedback_requires_research and not has_research_evidence):
            plan.append("research")
        if requires_calculation:
            plan.append("calculator")
        plan.append("final_answer")

    if character_data_lookup:
        plan = [agent for agent in plan if agent != "research"]
        if simple_character_lookup:
            plan = [agent for agent in plan if agent not in ("calculator", "analystic")]
        elif "calculator" not in plan:
            plan = ["calculator", *plan]
        task_type = "character_status_analysis"

    if error is not None:
        errors.append(f"supervisor llm failed; used fallback route: {error}")

    return {
        **state,
        "intent": "fallback supervisor routing",
        "task_type": task_type,
        "requires_character_lookup": requires_character_lookup,
        "plan": plan,
        "next_agent": plan[0],
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
    try:
        response_list = json.loads(content)
        if not isinstance(response_list, list):
            raise ValueError("supervisor response is not a JSON list")
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        # JSON 파싱 실패 시 원본 일부를 남겨 supervisor 라우팅 실패 원인을 추적
        retry_count += 1
        errors = [*errors, f"supervisor json parse failed: {exc}: {str(content)[:200]}"]
        response_list = []

    response_dict = {
        item.get("key"): item.get("value")
        for item in response_list
        if isinstance(item, dict)
    }

    intent = response_dict.get("intent", state.get("intent", ""))
    task_type = response_dict.get("task_type", state.get("task_type", "unknown"))
    if task_type not in TASK_TYPES:
        task_type = "unknown"

    lookup_value = response_dict.get(
        "requires_character_lookup",
        state.get("requires_character_lookup", False),
    )
    requires_character_lookup = (
        lookup_value
        if isinstance(lookup_value, bool)
        else str(lookup_value).strip().lower() in TRUTHY_VALUES
    )
    requires_character_lookup = (
        requires_character_lookup
        or requires_character_lookup_query(str(state.get("user_query") or ""))
    )
    lookup_attempted = bool((state.get("tool_results") or {}).get("nexon_api"))
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
    requires_search = response_dict.get("requires_search")
    requires_search = (
        requires_search
        if isinstance(requires_search, bool)
        else str(requires_search).strip().lower() in TRUTHY_VALUES
    )
    feedback_requires_research = any(
        marker in feedback.lower()
        for marker in RESEARCH_FEEDBACK_MARKERS
    )
    has_research_evidence = bool(
        str(state.get("context") or "").strip()
        or state.get("retrieved_docs")
    )
    research_already_done = (
        completed_agent == "research"
        or ("research" in state.get("completed_agents", []) and has_research_evidence)
    )
    needs_research_replan = (
        (requires_search or feedback_requires_research)
        and "research" not in plan
        and not research_already_done
    )

    if not needs_research_replan:
        return plan, retry_count, errors, None

    if RESEARCH_REPLAN_MARKER not in feedback:
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
        ordered_plan = [agent for agent in ordered_plan if agent != "analystic"]

    if "final_answer" not in ordered_plan:
        ordered_plan.append("final_answer")

    if completed_agent and not feedback and ordered_plan and ordered_plan[0] == completed_agent:
        # feedback 없이 정상 진행 중이면 이미 실행한 agent를 다시 실행하지 않도록 제거
        ordered_plan = ordered_plan[1:]

    return ordered_plan or ["final_answer"]


def supervisor(state:AgentState):
    """사용자의 질문을 분석하여 의도를 파악하고, 작업 유형을 결정하고, 처리 계획을 세우고, 다음 에이전트를 결정합니다."""
    user_query = str(state.get("user_query") or "")
    if is_chitchat_query(user_query):
        return {
            **state,
            "intent": "일상 대화 또는 인사",
            "task_type": "chitchat",
            "requires_character_lookup": False,
            "plan": ["final_answer"],
            "next_agent": "final_answer",
            "completed_agents": state.get("completed_agents", []),
            "retry_count": state.get("retry_count", 0),
            "errors": state.get("errors", []),
        }

    llm = get_llm()

    existing_plan = list(state.get("plan") or [])
    feedback = str(state.get("feedback", "") or "")
    retry_count = int(state.get("retry_count", 0) or 0)
    errors = list(state.get("errors", []) or [])

    completed_agent = None
    remaining_plan = []

    if existing_plan:
        # supervisor로 다시 돌아온 경우, plan의 첫 번째 agent는 방금 실행된 agent로 보고 제거
        completed_agent = existing_plan[0]
        remaining_plan = existing_plan[1:]


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
"requires_character_lookup" : 특정 유저 캐릭터의 현재 스펙, 장비, 전투력, 유니온, 보스 가능 여부처럼 Nexon Open API 캐릭터 조회가 필요한 경우 True, 일반 보스 정보/보상/요구 스탯처럼 캐릭터 조회가 필요 없는 경우 False
"requires_calculation" : 사용자 질문에 {CALCULATION_TRIGGER_KEYWORDS}가 포함되어 있거나 calculator가 필요한 경우 True, 필요하지 않은 경우 False
"requires_analytics" : 캐릭터 상태, 장비, 스펙, 선택지 비교, 성장 방향 판단처럼 analystic의 해석이 필요한 경우 True, 필요하지 않은 경우 False

#plan
plan에는 아래 목록의 에이전트만 포함할 수 있습니다.
{AgentName}

에이전트 실행 순서는 research -> calculator -> analystic -> final_answer 입니다.
- requires_search가 True이면 research를 추가합니다.
- requires_calculation이 True이면 calculator를 추가합니다.
- requires_analytics가 True이면 analystic을 추가합니다.
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
사용자의 질문: {messages}

#output format
아래 JSON 리스트 형식으로만 답변하세요.
[
  {{"key": "intent", "value": "사용자 질문 의도 요약"}},
  {{"key": "task_type", "value": "TASK_TYPES key 중 하나"}},
  {{"key": "requires_search", "value": true}},
  {{"key": "requires_character_lookup", "value": false}},
  {{"key": "requires_analytics", "value": false}},
  {{"key": "requires_calculation", "value": false}},
  {{"key": "plan", "value": ["에이전트명", "에이전트명", ...]}},
  {{"key": "next_agent", "value": "plan의 첫 번째 에이전트. 만약 plan이 비어있다면 final_answer"}}
]
"""

    try:
        response = llm.invoke(prompt)
        content = getattr(response, "content", response)
    except Exception as exc:
        return _fallback_supervisor_response(state, exc)

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
    character_data_lookup = (
        requires_character_lookup
        and is_character_data_lookup_query(user_query)
    )
    simple_character_lookup = (
        character_data_lookup
        and not requires_character_processing_query(user_query)
    )
    if character_data_lookup:
        response_dict["requires_search"] = False
        task_type = "character_status_analysis"

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
        return supervisor(replan_state)

    if character_data_lookup:
        plan = [agent for agent in plan if agent != "research"]
        if simple_character_lookup:
            plan = [agent for agent in plan if agent not in ("calculator", "analystic")]
        elif "calculator" not in plan:
            plan = ["calculator", *plan]

    plan = _finalize_plan(
        plan,
        state,
        completed_agent,
        "" if character_data_lookup else feedback,
    )

    next_agent = response_dict.get("next_agent") or plan[0]
    if next_agent != plan[0]:
        errors = [*errors, "supervisor next_agent did not match first plan item; using plan[0]"]
        next_agent = plan[0]

    completed_agents = state.get("completed_agents", [])
    if completed_agent and completed_agent not in completed_agents:
        completed_agents = [*completed_agents, completed_agent]

    return {
        **state,
        "intent": intent,
        "task_type": task_type,
        "requires_character_lookup": requires_character_lookup,
        "plan": plan,
        "next_agent": next_agent,
        "completed_agents": completed_agents,
        "retry_count": retry_count,
        "errors": errors,
    }
