from __future__ import annotations

from typing import Callable

from langchain_core.messages import HumanMessage


MAX_AGENT_HISTORY_MESSAGES = 12
SUMMARY_TRIGGER_MESSAGES = 16
SUMMARY_KEEP_RECENT_MESSAGES = 8
SUMMARY_FALLBACK_LIMIT = 3000

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
    lines = []
    for message in messages:
        speaker = "사용자" if message["role"] == "user" else "어시스턴트"
        lines.append(f"{speaker}: {message['content']}")
    return "\n".join(lines)


def summarize_agent_memory(
    messages_to_summarize: list[dict[str, str]],
    previous_summary: str,
    add_error: Callable[[str], None],
) -> str:
    conversation = format_messages_for_summary(messages_to_summarize)
    prompt = SUMMARY_PROMPT_TEMPLATE.format(
        previous_summary=previous_summary or "없음",
        conversation=conversation,
    )

    try:
        from common.get_model import get_llm

        response = get_llm().invoke([HumanMessage(content=prompt)])
        return str(getattr(response, "content", response)).strip()
    except Exception as exc:
        add_error(f"summary failed: {exc}")
        fallback_summary = "\n".join(
            part for part in (previous_summary, conversation) if part
        )
        return fallback_summary[-SUMMARY_FALLBACK_LIMIT:]


def compact_agent_history(
    agent_messages: list[dict[str, str]],
    memory_summary: str,
    add_error: Callable[[str], None],
) -> tuple[list[dict[str, str]], str]:
    if len(agent_messages) <= SUMMARY_TRIGGER_MESSAGES:
        return agent_messages, memory_summary

    split_at = len(agent_messages) - SUMMARY_KEEP_RECENT_MESSAGES
    messages_to_summarize = agent_messages[:split_at]
    next_summary = summarize_agent_memory(
        messages_to_summarize,
        memory_summary.strip(),
        add_error,
    )
    return agent_messages[split_at:], next_summary


def build_agent_messages(
    user_input: str,
    agent_messages: list[dict[str, str]],
    memory_summary: str,
) -> list[dict[str, str]]:
    messages = []
    summary = memory_summary.strip()
    if summary:
        messages.append(
            {
                "role": "system",
                "content": f"이전 대화 요약:\n{summary}",
            }
        )

    messages.extend(agent_messages[-MAX_AGENT_HISTORY_MESSAGES:])
    messages.append({"role": "user", "content": user_input})
    return messages
