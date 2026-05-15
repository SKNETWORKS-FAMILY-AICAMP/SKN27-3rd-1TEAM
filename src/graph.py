"""
메이플스토리 멀티 에이전트 챗봇용 LangGraph StateGraph 정의 모듈.

[그래프 토폴로지 개요]
    START
      └─> supervisor (라우팅 결정 노드)
            ├─> nexon_api      : 캐릭터 조회가 필요한 경우 Nexon Open API 호출
            │     └─> analystic / calculator / final_answer 로 분기
            ├─> research       : 외부 지식/문서 검색이 필요한 경우
            │     └─> evidence_formatter ─> supervisor (근거 정리 후 재라우팅)
            ├─> analystic      : 분석 에이전트 (─> supervisor)
            ├─> calculator     : 계산 에이전트 (─> supervisor)
            ├─> final_answer   : 최종 답변 생성 (─> evaluation)
            └─> end (END)      : 종료
      evaluation 노드:
            ├─> validation_passed=True 인 경우 END
            └─> 그렇지 않으면 supervisor 로 재시도 (MAX_RETRY_COUNT 까지)

각 노드는 AgentState 를 입출력으로 받아 상태를 갱신/전달한다.
"""

from __future__ import annotations

from typing import Any, Literal

from langgraph.graph import END, START, StateGraph

from common.state import AgentState


# === 라우팅/상수 정의 ===

# GraphRoute: 조건부 엣지에서 사용할 수 있는 라우팅 키 모음.
# - "supervisor"   : 슈퍼바이저로 되돌아감 (재계획/재시도)
# - "nexon_api"    : Nexon Open API 호출 노드로 이동
# - "research"     : 리서치(RAG/웹검색) 에이전트로 이동
# - "analystic"    : 분석 에이전트로 이동
# - "calculator"   : 계산 에이전트로 이동
# - "final_answer" : 최종 답변 생성 노드로 이동
# - "end"          : 그래프 종료 (END 상수에 매핑)
GraphRoute = Literal[
    "supervisor",
    "nexon_api",
    "research",
    "analystic",
    "calculator",
    "final_answer",
    "end",
]

# MAX_RETRY_COUNT: supervisor 진입 시 허용되는 최대 재시도 횟수.
# state["retry_count"] 가 이 값 이상이면 더 이상 재계획하지 않고 종료 처리한다.
MAX_RETRY_COUNT = 2
# RETRY_LIMIT_ANSWER: 재시도 한도를 초과했을 때 사용자에게 돌려줄 기본 안내 메시지.
RETRY_LIMIT_ANSWER = (
    "현재 질문에 맞는 근거를 충분히 확인하지 못해 정확한 답변을 드리기 어렵습니다. "
    "잘못된 정보를 드리지 않기 위해 답변을 중단합니다. "
    "대상 보스, 캐릭터 정보, 궁금한 항목을 조금 더 구체적으로 입력해 주세요."
)


# === 헬퍼 함수: 상태 빌더/조회 ===


def build_retry_limit_state(state: AgentState) -> AgentState:
    """재시도 한도 초과 시 그래프를 안전하게 종료시키기 위한 상태를 만든다.

    - 기존 final_answer 가 있으면 그대로 유지하고, 없으면 RETRY_LIMIT_ANSWER 로 채운다.
    - tool_results 에 supervisor_retry_limit 디버깅 정보를 남긴다.
    - is_complete=True, next_agent="FINISH" 로 설정해 종료 라우팅을 유도한다.
    """
    # 기존에 작성된 최종 답변이 있다면 우선 보존 (없으면 안내 문구 사용)
    existing_final_answer = str(state.get("final_answer") or "").strip()
    final_answer = existing_final_answer or RETRY_LIMIT_ANSWER
    # tool_results 에 종료 사유와 retry_count 를 기록 (디버깅/로그용)
    tool_results = dict(state.get("tool_results", {}))
    tool_results["supervisor_retry_limit"] = {
        "reason": "retry_count exceeded",
        "retry_count": int(state.get("retry_count", 0)),
        "preserved_final_answer": bool(existing_final_answer),
    }

    # 종료 신호를 담은 상태를 반환 (validation_passed=False 지만 is_complete=True 로 빠져나감)
    return {
        **state,
        "draft_answer": state.get("draft_answer") or final_answer,
        "final_answer": final_answer,
        "validation_passed": False,
        "is_complete": True,
        "next_agent": "FINISH",
        "retry_target": "FINISH",
        "tool_results": tool_results,
    }


def has_nexon_character_data(state: AgentState) -> bool:
    """Nexon API 로 이미 캐릭터 프로필/스탯을 받아둔 상태인지 확인한다."""
    # character_profile 과 character_stats 가 모두 채워져 있어야 True
    return bool(state.get("character_profile") and state.get("character_stats"))


def nexon_lookup_attempted(state: AgentState) -> bool:
    """이번 그래프 실행 중 Nexon API 호출이 한 번이라도 시도되었는지 확인한다."""
    # tool_results 에 nexon_api 키가 존재하면 호출 시도가 있었던 것으로 간주
    return bool((state.get("tool_results") or {}).get("nexon_api"))


def read_field(value: Any, key: str, default: Any = "") -> Any:
    """dict 또는 객체(attribute) 모두에서 안전하게 필드 값을 꺼내는 헬퍼."""
    if isinstance(value, dict):
        return value.get(key, default)
    return getattr(value, key, default)


# === Nexon API 근거(Evidence) 빌더 ===


def build_nexon_evidence_context(state: AgentState, error: str = "") -> str:
    """Nexon API 조회 결과(또는 실패 정보)를 LLM 컨텍스트용 문자열로 포맷한다.

    - error 가 비어 있지 않으면 실패 컨텍스트(LOW 신뢰도)를 생성한다.
    - 성공 시에는 캐릭터 프로필/스탯/장비/유니온 정보를 한국어 라벨로 요약한다.
    """
    # 실패 케이스: 캐릭터명/질문/오류 메시지를 담은 간단한 컨텍스트를 만든다.
    if error:
        character_name = state.get("character_name", "")
        query = state.get("user_query", "")
        lines = ["Nexon Open API 캐릭터 조회 실패"]
        if character_name:
            lines.append(f"- 캐릭터: {character_name}")
        if query:
            lines.append(f"- 사용자 질문: {query}")
        lines.append(f"- 오류: {error}")
        return "\n".join(lines)

    # 성공 케이스: state 내 캐릭터 관련 필드를 모아 사람이 읽기 좋은 컨텍스트로 정리.
    profile = state.get("character_profile") or {}
    stats = state.get("character_stats") or read_field(profile, "final_stats", {}) or {}
    equipment_items = state.get("equipment_items") or read_field(profile, "equipment_list", []) or []
    union_status = state.get("union_status") or read_field(profile, "union_info", {}) or {}

    lines = ["Nexon Open API 캐릭터 조회 결과"]
    # 캐릭터 기본 프로필 정보 (캐릭터명, 월드, 직업, 레벨)
    profile_fields = (
        ("캐릭터", read_field(profile, "character_name", state.get("character_name", ""))),
        ("월드", read_field(profile, "world_name", state.get("world_name", ""))),
        ("직업", read_field(profile, "job_name", "")),
        ("레벨", read_field(profile, "level", "")),
    )
    for label, value in profile_fields:
        if value not in ("", None):
            lines.append(f"- {label}: {value}")

    # 전투 스탯 정보 (전투력, 데미지 계열, 주요 스탯, 크리티컬 등)
    stat_fields = (
        ("전투력", read_field(stats, "combat_power", "")),
        ("스탯 공격력", _format_damage_range(stats)),
        ("STR", read_field(stats, "str_val", "")),
        ("DEX", read_field(stats, "dex", "")),
        ("INT", read_field(stats, "int_val", "")),
        ("LUK", read_field(stats, "luk", "")),
        ("데미지", _format_percent(read_field(stats, "damage", ""))),
        ("보스 데미지", _format_percent(read_field(stats, "boss_damage", ""))),
        ("최종 데미지", _format_percent(read_field(stats, "final_damage", ""))),
        ("방어율 무시", _format_percent(read_field(stats, "ignore_def", ""))),
        ("크리티컬 확률", _format_percent(read_field(stats, "crit_rate", ""))),
        ("크리티컬 데미지", _format_percent(read_field(stats, "crit_damage", ""))),
        ("공격력", read_field(stats, "attack_power", "")),
        ("마력", read_field(stats, "magic_power", "")),
        ("아케인포스", read_field(stats, "arcane_force", "")),
        ("어센틱포스", read_field(stats, "authentic_force", "")),
    )
    for label, value in stat_fields:
        if value not in ("", None):
            lines.append(f"- {label}: {value}")

    # 장비 개수 요약 (세부 장비 정보는 별도 노드에서 다룸)
    if equipment_items:
        lines.append(f"- 장착 장비 수: {len(equipment_items)}")

    # 유니온 관련 정보
    union_fields = (
        ("유니온 레벨", read_field(union_status, "union_level", "")),
        ("유니온 등급", read_field(union_status, "union_grade", "")),
        ("아티팩트 레벨", read_field(union_status, "artifact_level", "")),
    )
    for label, value in union_fields:
        if value not in ("", None):
            lines.append(f"- {label}: {value}")

    lines.append("- 출처: Nexon Open API")
    return "\n".join(lines)


def attach_nexon_evidence(state: AgentState, error: str = "") -> AgentState:
    """Nexon API 결과 컨텍스트를 state 의 RAG 관련 필드들에 일관되게 주입한다.

    읽는 필드:
      - context, retrieved_docs, selected_evidence, evidence_summary, character_profile
    갱신하는 필드:
      - context              : 기존 컨텍스트에 nexon 컨텍스트를 병합
      - retrieved_docs       : 기존 nexon_api 문서를 제거한 뒤 새 문서로 교체
      - selected_evidence    : nexon 문서를 추가
      - evidence_summary     : nexon_api 요약을 갱신
      - relevance_reason     : 비어있을 경우에만 기본값 설정
    """
    context = build_nexon_evidence_context(state, error)
    # 기존 컨텍스트가 있고 중복되지 않을 때만 nexon 컨텍스트를 뒤에 붙인다.
    existing_context = str(state.get("context") or "").strip()
    merged_context = (
        f"{existing_context}\n\n{context}"
        if existing_context and context not in existing_context
        else context or existing_context
    )

    # retrieved_docs 등에서 사용할 표준 문서 구조 생성 (RAG 파이프라인 포맷)
    profile = state.get("character_profile") or {}
    document = {
        "page_content": context,
        "metadata": {
            "source": "nexon_api",
            "retrieval_method": "nexon_open_api",
            "reliability": "LOW" if error else "HIGH",
            "character_name": str(read_field(profile, "character_name", state.get("character_name", "")) or ""),
            "world_name": str(read_field(profile, "world_name", state.get("world_name", "")) or ""),
            "ocid": str(state.get("ocid") or ""),
            "error": error,
        },
        "source": "nexon_api",
        "score": 0.2 if error else 1.0,
    }
    # 이전 nexon_api 문서는 모두 제거하고, 새로 만든 document 로 교체한다 (중복 방지).
    retrieved_docs = [
        doc
        for doc in list(state.get("retrieved_docs") or [])
        if not (
            isinstance(doc, dict)
            and (
                doc.get("source") == "nexon_api"
                or (doc.get("metadata") or {}).get("source") == "nexon_api"
            )
        )
    ]
    retrieved_docs.append(document)

    return {
        **state,
        "context": merged_context,
        "retrieved_docs": retrieved_docs,
        "selected_evidence": [
            *list(state.get("selected_evidence") or []),
            document,
        ],
        "evidence_summary": {
            **dict(state.get("evidence_summary") or {}),
            "nexon_api": {
                "source": "nexon_api",
                "reliability": "LOW" if error else "HIGH",
                "summary": context,
            },
        },
        "relevance_reason": state.get("relevance_reason")
        or ("nexon_api_error_context" if error else "nexon_api_character_lookup"),
    }


def _format_damage_range(stats: Any) -> str:
    """최소/최대 스탯 공격력을 'min ~ max' 형태로 표시한다."""
    min_damage = read_field(stats, "min_stat_damage", "")
    max_damage = read_field(stats, "max_stat_damage", "")
    # 둘 다 없으면 빈 문자열을 반환해 상위 포매터에서 라인 자체를 생략하게 한다.
    if min_damage in ("", None) and max_damage in ("", None):
        return ""
    return f"{min_damage} ~ {max_damage}"


def _format_percent(value: Any) -> str:
    """숫자형 스탯 값을 퍼센트 표기 문자열로 바꾼다."""
    if value in ("", None):
        return ""
    return f"{value}%"


def nexon_api_node(state: AgentState) -> AgentState:
    """캐릭터 조회가 필요한 흐름에서 Nexon Open API를 호출하고 근거 문서로 붙인다.

    이미 캐릭터 데이터가 state에 있으면 API를 다시 호출하지 않고,
    실패해도 그래프를 중단하지 않도록 오류 컨텍스트를 evidence로 남긴다.
    """
    tool_results = dict(state.get("tool_results") or {})

    # 이전 노드나 세션 메모리에서 이미 캐릭터 데이터가 넘어온 경우 중복 조회를 피한다.
    if has_nexon_character_data(state):
        tool_results["nexon_api"] = {
            **dict(tool_results.get("nexon_api") or {}),
            "lookup_attempted": True,
            "skipped": True,
            "reason": "character_data_already_available",
        }
        return attach_nexon_evidence({
            **state,
            "requires_character_lookup": False,
            "tool_results": tool_results,
        })

    try:
        # 실제 수집 로직은 collector 모듈에 두고, graph 노드는 상태 결합만 담당한다.
        from src.collectors.nexon_api import nexon_api_node as run_nexon_api_node

        next_state = run_nexon_api_node(state)
        next_tool_results = dict(next_state.get("tool_results") or {})
        nexon_result = dict(next_tool_results.get("nexon_api") or {})
        # LangSmith/디버깅에서 API 호출 여부를 일관되게 볼 수 있도록 플래그를 보강한다.
        next_tool_results["nexon_api"] = {
            **nexon_result,
            "lookup_attempted": True,
        }
        return attach_nexon_evidence({
            **next_state,
            "requires_character_lookup": False,
            "tool_results": next_tool_results,
        })
    except Exception as exc:
        # API 키 누락/네트워크/캐릭터명 오류가 나도 최종 답변에서 설명할 수 있게 상태에 남긴다.
        error = str(exc)
        tool_results["nexon_api"] = {
            "lookup_attempted": True,
            "data_reliability": "unavailable",
            "error": error,
        }
        return attach_nexon_evidence({
            **state,
            "requires_character_lookup": False,
            "tool_results": tool_results,
            "errors": [
                *list(state.get("errors", []) or []),
                f"nexon_api failed: {error}",
            ],
        }, error=error)


def supervisor(state: AgentState) -> AgentState:
    """재시도 한도를 확인한 뒤 실제 supervisor 에이전트로 상태를 넘긴다."""
    plan = list(state.get("plan") or [])
    # final_answer 직전처럼 근거가 이미 있고 마지막 답변만 남은 상황은 한도 초과라도 마무리 허용.
    has_research_evidence = bool(
        str(state.get("context") or "").strip()
        or state.get("retrieved_docs")
    )
    has_final_answer = bool(str(state.get("final_answer") or "").strip())
    can_finish_forced_plan = (
        has_research_evidence
        and "final_answer" in plan
        and not has_final_answer
    )
    if int(state.get("retry_count", 0)) >= MAX_RETRY_COUNT and not can_finish_forced_plan:
        return build_retry_limit_state(state)

    # 무거운 LLM 의존성은 그래프 빌드 시점이 아니라 실행 시점에 로드한다.
    from src.agents.supervisor import supervisor as supervisor_agent

    return supervisor_agent(state)


def research(state: AgentState) -> AgentState:
    """RAG/웹 검색 에이전트 실행 래퍼."""
    from src.agents.research_agent import research_agent

    # research_agent는 character_name/world_name 키가 없으면 불안정할 수 있어 기본값을 보장한다.
    next_state = {
        **state,
        "character_name": state.get("character_name", ""),
        "world_name": state.get("world_name", ""),
    }
    return research_agent(next_state)


def evidence_formatter(state: AgentState) -> AgentState:
    """검색 결과를 최종 답변 프롬프트에 넣기 좋은 근거 컨텍스트로 정리한다."""
    from src.rag.evidence_formatter import format_evidence_for_answer

    return format_evidence_for_answer(state)


def analystic(state: AgentState) -> AgentState:
    """성장 방향/추천 액션을 만드는 분석 에이전트 실행 래퍼."""
    from src.agents.analytics import analytics_agent

    return analytics_agent(state=state)


def calculator(state: AgentState) -> AgentState:
    """스탯/장비/보스 가능성 계산 에이전트 실행 래퍼."""
    from src.agents.calculator import calculator_agent

    return calculator_agent(state=state)


def final_answer(state: AgentState) -> AgentState:
    """최종 답변 생성 에이전트 실행 래퍼."""
    from src.agents.final_answer import run_final_answer_agent

    # final_answer는 빈 context/recommended_actions에도 안전하게 동작하도록 기본값을 채운다.
    next_state = {
        **state,
        "context": state.get("context", ""),
        "recommended_actions": state.get("recommended_actions", []),
    }
    return run_final_answer_agent(next_state)


def evaluation(state: AgentState) -> AgentState:
    """최종 답변을 검증하고 통과/재계획 라우팅 신호를 만든다."""
    final_answer_text = str(state.get("final_answer") or "").strip()
    has_context = bool(str(state.get("context") or "").strip())
    has_retrieved_docs = bool(state.get("retrieved_docs") or [])
    # 근거 없이 답변이 만들어진 경우: 잡담은 허용, 정보성 답변은 supervisor로 되돌린다.
    if final_answer_text and not has_context and not has_retrieved_docs:
        if state.get("task_type") == "chitchat":
            tool_results = dict(state.get("tool_results", {}))
            tool_results["evaluation"] = {
                "agent": "evaluation",
                "is_pass": True,
                "route": "PASS",
                "next_agent": "FINISH",
                "retry_target": "FINISH",
                "feedback": "Chitchat does not require retrieved context.",
                "warnings": [],
            }
            return {
                **state,
                "tool_results": tool_results,
                "validation_passed": True,
                "feedback": "Chitchat does not require retrieved context.",
                "is_complete": True,
                "next_agent": "FINISH",
                "retry_target": "FINISH",
            }

        retry_count = int(state.get("retry_count", 0))
        tool_results = dict(state.get("tool_results", {}))
        # missing_context를 명시해 supervisor가 research를 다시 plan에 넣을 수 있게 한다.
        tool_results["evaluation"] = {
            "agent": "evaluation",
            "is_pass": False,
            "route": "REPLAN",
            "next_agent": "supervisor",
            "retry_target": "supervisor",
            "feedback": (
                "missing_context: no retrieved context or documents were available. "
                "Send back to supervisor and run research with web fallback before final_answer."
            ),
            "warnings": ["contexts are empty", "retrieved_docs are empty"],
            "failure_type": "missing_context",
            "retry_count": retry_count,
            "max_retry_count": MAX_RETRY_COUNT,
        }
        return {
            **state,
            "tool_results": tool_results,
            "validation_passed": False,
            "feedback": tool_results["evaluation"]["feedback"],
            "is_complete": False,
            "next_agent": "supervisor",
            "retry_target": "supervisor",
            "retry_count": retry_count + 1,
        }

    # 일반 케이스는 별도 평가 모듈에 위임한다.
    from src.evaluation.final_answer_eval import run_final_answer_evaluation

    return run_final_answer_evaluation(
        state,
        apply_route=True,
        max_retry_count=MAX_RETRY_COUNT,
    )


def route_from_supervisor(state: AgentState) -> GraphRoute:
    """supervisor가 정한 next_agent와 캐릭터 조회 필요 여부에 따라 다음 노드를 고른다."""
    if state.get("is_complete") or state.get("next_agent") == "FINISH":
        return "end"

    next_agent = state.get("next_agent", "final_answer")

    # 분석/계산/최종답변 전에 캐릭터 데이터가 필요하면 nexon_api를 끼워 넣는다.
    if (
        next_agent in ("analystic", "calculator", "final_answer")
        and state.get("requires_character_lookup")
        and not has_nexon_character_data(state)
        and not nexon_lookup_attempted(state)
    ):
        return "nexon_api"

    if next_agent in ("research", "analystic", "calculator", "final_answer"):
        return next_agent

    # LLM이 예상 밖 next_agent를 주면 최종답변으로 안전하게 폴백한다.
    return "final_answer"


def route_from_nexon_api(state: AgentState) -> GraphRoute:
    """Nexon API 조회 뒤 원래 supervisor가 의도한 후속 노드로 복귀한다."""
    next_agent = state.get("next_agent", "final_answer")
    if next_agent in ("analystic", "calculator", "final_answer"):
        return next_agent
    return "final_answer"


def route_from_evaluation(state: AgentState) -> GraphRoute:
    """평가 통과 여부에 따라 종료 또는 supervisor 재계획으로 보낸다."""
    if state.get("validation_passed"):
        return "end"

    return "supervisor"


def maple_chat_graph():
    """Maple Guide LangGraph 워크플로를 구성하고 compile된 그래프를 반환한다."""
    graph = StateGraph(AgentState)
    # 노드 등록: 각 노드는 AgentState를 받아 필요한 필드를 갱신한다.
    graph.add_node("supervisor", supervisor)
    graph.add_node("research", research)
    graph.add_node("evidence_formatter", evidence_formatter)
    graph.add_node("analystic", analystic)
    graph.add_node("calculator", calculator)
    graph.add_node("final_answer", final_answer)
    graph.add_node("evaluation", evaluation)
    graph.add_node("nexon_api", nexon_api_node)

    # 시작점은 항상 supervisor. 이후 조건부 라우팅이 전체 플로우를 결정한다.
    graph.add_edge(START, "supervisor")
    graph.add_conditional_edges(
        "supervisor",
        route_from_supervisor,
        {
            "nexon_api": "nexon_api",
            "research": "research",
            "analystic": "analystic",
            "calculator": "calculator",
            "final_answer": "final_answer",
            "end": END,
        },
    )
    # Nexon API는 보조 노드라서 끝나면 분석/계산/답변 중 원래 목적지로 바로 이동한다.
    graph.add_conditional_edges(
        "nexon_api",
        route_from_nexon_api,
        {
            "analystic": "analystic",
            "calculator": "calculator",
            "final_answer": "final_answer",
        },
    )
    # research 결과는 evidence_formatter에서 LLM 입력용 컨텍스트로 정리한 뒤 재라우팅한다.
    graph.add_edge("research", "evidence_formatter")
    graph.add_edge("evidence_formatter", "supervisor")
    # 분석/계산 결과도 supervisor가 남은 plan을 보고 다음 노드를 결정한다.
    graph.add_edge("analystic", "supervisor")
    graph.add_edge("calculator", "supervisor")
    # 최종 답변은 항상 평가를 통과해야 END로 갈 수 있다.
    graph.add_edge("final_answer", "evaluation")
    graph.add_conditional_edges(
        "evaluation",
        route_from_evaluation,
        {
            "supervisor": "supervisor",
            "end": END,
        },
    )
    # compile 결과를 Streamlit 쪽에서 캐싱해 재사용한다.
    return graph.compile()
