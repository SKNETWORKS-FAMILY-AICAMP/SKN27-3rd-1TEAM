"""에이전트가 참고할 대화 메모리(요약/이력) 관리 모듈.

대화가 길어질수록 LLM 컨텍스트가 부담되므로
- 일정 길이 이상이면 과거 대화를 LLM 으로 요약하고
- 최근 N개의 메시지 + 요약문만 다음 호출에 함께 전달한다.
"""

from __future__ import annotations

from typing import Callable

from langchain_core.messages import HumanMessage


# === 메모리 관리 임계값 ===
MAX_AGENT_HISTORY_MESSAGES = 12      # 에이전트에 전달할 최근 메시지 최대 개수
SUMMARY_TRIGGER_MESSAGES = 16        # 이 개수를 넘으면 요약 트리거
SUMMARY_KEEP_RECENT_MESSAGES = 8     # 요약 후에도 그대로 보존할 최근 메시지 수
SUMMARY_FALLBACK_LIMIT = 3000        # LLM 요약 실패 시 잘라낼 문자열 최대 길이

# 메시지 role 값을 한국어 화자 라벨로 변환할 때 사용
SUMMARY_ROLE_LABELS = {
    "user": "사용자",
    "assistant": "어시스턴트",
}

# 요약 LLM 에 전달할 프롬프트 템플릿
# - 무엇을 포함/제외해야 하는지 명확히 지시
# - {previous_summary} : 직전까지 누적된 요약, {conversation} : 새로 요약할 대화
SUMMARY_PROMPT_TEMPLATE = """
다음은 메이플스토리 상담 챗봇의 이전 대화입니다.
에이전트가 이후 답변에 참고해야 할 정보만 한국어로 간결하게 요약하세요.

요약에 포함할 것:
- 사용자의 캐릭터명, 월드명, 직업, 목표 보스, 스펙 등 유지해야 하는 사실
- 이미 설명했거나 추천한 내용 중 다음 답변에 영향을 주는 내용
- 사용자의 선호나 제약

요약에서 제외할 것:
- 단순 인사
- 실패한 시스템 오류 메시지
- 오래된 잡담

기존 요약:
{previous_summary}

새로 요약할 대화:
{conversation}
""".strip()


def format_messages_for_summary(messages: list[dict[str, str]]) -> str:
    """요약 프롬프트에 넣을 수 있도록 메시지 목록을 "화자: 내용" 형식 텍스트로 변환."""
    lines = []
    for message in messages:
        # role 값이 알 수 없는 경우 기본값으로 "어시스턴트" 사용
        speaker = SUMMARY_ROLE_LABELS.get(message.get("role"), "어시스턴트")
        lines.append(f"{speaker}: {message.get('content', '')}")
    return "\n".join(lines)


def summarize_agent_memory(
    messages_to_summarize: list[dict[str, str]],
    previous_summary: str,
    add_error: Callable[[str], None],
) -> str:
    """LLM 으로 이전 대화를 요약한다.

    실패하면 기존 요약 + 원문을 이어 붙여 마지막 SUMMARY_FALLBACK_LIMIT 글자만 보존.
    """
    # 1) 메시지를 텍스트로 변환
    conversation = format_messages_for_summary(messages_to_summarize)
    # 2) 프롬프트 완성 (기존 요약이 없으면 "없음" 표시)
    prompt = SUMMARY_PROMPT_TEMPLATE.format(
        previous_summary=previous_summary or "없음",
        conversation=conversation,
    )

    try:
        # 지연 import: 모듈 로딩 시점에 LLM 클라이언트가 초기화되는 것을 피함
        from common.get_model import get_llm

        # 3) LLM 호출하여 요약 생성
        response = get_llm().invoke([HumanMessage(content=prompt)])
        # AIMessage 객체 또는 문자열 모두 대응
        return str(getattr(response, "content", response)).strip()
    except Exception as exc:
        # LLM 요약이 실패하면 호출자에게 에러를 알리고
        # 최소한 원문 대화라도 보존하도록 fallback 처리
        add_error(f"summary failed: {exc}")
        fallback_summary = "\n".join(
            part for part in (previous_summary, conversation) if part
        )
        # 너무 길어지지 않도록 뒤에서부터 제한된 길이만 잘라 반환
        return fallback_summary[-SUMMARY_FALLBACK_LIMIT:]


def compact_agent_history(
    agent_messages: list[dict[str, str]],
    memory_summary: str,
    add_error: Callable[[str], None],
) -> tuple[list[dict[str, str]], str]:
    """대화가 길어지면 앞쪽을 요약으로 압축해 길이를 조절한다.

    Returns:
        (압축 후의 메시지 리스트, 갱신된 요약 문자열)
    """
    # 임계치 미만이면 그대로 반환
    if len(agent_messages) <= SUMMARY_TRIGGER_MESSAGES:
        return agent_messages, memory_summary

    # 최근 SUMMARY_KEEP_RECENT_MESSAGES 개는 보존하고, 그 앞 부분만 요약 대상
    split_at = len(agent_messages) - SUMMARY_KEEP_RECENT_MESSAGES
    messages_to_summarize = agent_messages[:split_at]
    # 새 요약 생성
    next_summary = summarize_agent_memory(
        messages_to_summarize,
        memory_summary.strip(),
        add_error,
    )
    # 최근 메시지만 남기고 요약본을 별도로 반환
    return agent_messages[split_at:], next_summary


def build_agent_messages(
    user_input: str,
    agent_messages: list[dict[str, str]],
    memory_summary: str,
) -> list[dict[str, str]]:
    """에이전트 호출용 최종 메시지 리스트를 만든다.

    구성: [요약 system 메시지(있을 때)] + [최근 N개 메시지] + [이번 user 메시지]
    """
    messages = []

    # 1) 누적 요약이 있으면 system 메시지로 맨 앞에 삽입
    summary = memory_summary.strip()
    if summary:
        messages.append(
            {
                "role": "system",
                "content": f"이전 대화 요약:\n{summary}",
            }
        )

    # 2) 최근 N개 메시지만 컨텍스트로 사용 (오래된 대화는 잘라냄)
    messages.extend(agent_messages[-MAX_AGENT_HISTORY_MESSAGES:])
    # 3) 이번 턴 사용자 입력
    messages.append({"role": "user", "content": user_input})
    return messages
