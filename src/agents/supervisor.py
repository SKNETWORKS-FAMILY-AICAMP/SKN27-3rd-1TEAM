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



TASK_AGENT_MAP = {
    "character_status_analysis": ["analystic", "final_answer"],
    "recommendation": ["research", "analystic", "final_answer"],
    "system_explanation": ["research", "final_answer"],
    "story_explanation": ["research", "final_answer"],
    "reward_explanation": ["research", "final_answer"],
    "event_information": ["research", "final_answer"],
    "boss_strategy": ["research", "analystic", "final_answer"],
    "skill_explanation": ["research", "analystic", "final_answer"],
    "quest_guide": ["research", "final_answer"],
    "market_price": ["research", "final_answer"],
    "patch_information": ["research", "final_answer"],
    "general_qa": ["final_answer"],
    "chitchat": ["final_answer"],
    "unknown": ["final_answer"],
}


def supervisor(state:AgentState):
    """사용자의 질문을 분석하여 의도를 파악하고, 작업 유형을 결정하고, 처리 계획을 세우고, 다음 에이전트를 결정합니다."""
    llm = get_llm()

    existing_plan = state.get("plan") or []
    feedback = state.get("feedback", "")
    retry_count = state.get("retry_count", 0)
    errors = state.get("errors", [])

    completed_agent = None
    remaining_plan = []

    if existing_plan:
        # supervisor로 다시 돌아온 경우, plan의 첫 번째 agent는 방금 실행된 agent로 보고 제거
        completed_agent = existing_plan[0]
        remaining_plan = existing_plan[1:]
    elif state.get("next_agent") in ["research", "analystic", "calculator", "final_answer"]:
        remaining_plan = []


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

에이전트 실행 순서는 research -> analystic -> calculator -> final_answer 입니다.
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
    ordered_plan = []
    for agent in ["research", "analystic", "calculator", "final_answer"]:
        if agent in plan and agent not in ordered_plan:
            ordered_plan.append(agent)

    plan = ordered_plan
    if not plan and state.get("next_agent") in ["research", "analystic", "calculator", "final_answer"]:
        # plan이 비어도 이전 next_agent가 있으면 기존 라우팅을 이어감
        plan = [state["next_agent"]]

    if "final_answer" not in plan:
        plan.append("final_answer")

    if completed_agent and not feedback and plan and plan[0] == completed_agent:
        # feedback 없이 정상 진행 중이면 이미 실행한 agent를 다시 실행하지 않도록 제거
        plan = plan[1:]

    next_agent = response_dict.get("next_agent") or plan[0]
    if next_agent not in plan:
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
