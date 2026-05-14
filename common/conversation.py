from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any


ROLE_ALIASES = {
    "human": "user",
    "ai": "assistant",
}
RECALL_REFERENCE_TOKENS = ("방금", "아까", "처음", "맨처음", "이전", "앞에서")
RECALL_ACTION_TOKENS = ("말", "질문", "물어", "얘기", "했", "뭐", "무슨")
RECALL_STANDALONE_TOKENS = ("기억나", "기억해")
FIRST_RECALL_TOKENS = ("처음", "맨처음")


def normalize_compact_text(value: Any) -> str:
    return "".join(str(value or "").strip().lower().split())


def contains_any(text: str, tokens: Iterable[str]) -> bool:
    return any(token in text for token in tokens)


def is_conversation_recall_query(query: str) -> bool:
    normalized = normalize_compact_text(query)
    if not normalized:
        return False

    if contains_any(normalized, RECALL_STANDALONE_TOKENS):
        return True

    return contains_any(normalized, RECALL_REFERENCE_TOKENS) and contains_any(
        normalized,
        RECALL_ACTION_TOKENS,
    )


def is_first_message_recall_query(query: str) -> bool:
    return contains_any(normalize_compact_text(query), FIRST_RECALL_TOKENS)


def message_role(message: Any) -> str:
    if isinstance(message, Mapping):
        role = str(message.get("type") or message.get("role") or "")
    else:
        role = str(getattr(message, "type", "") or message.__class__.__name__)
    return ROLE_ALIASES.get(role, role)


def message_content(message: Any) -> str:
    if isinstance(message, Mapping):
        content = message.get("content", "")
        return "" if content is None else str(content).strip()
    return str(getattr(message, "content", message)).strip()


def user_message_contents(messages: Iterable[Any]) -> list[str]:
    return [
        content
        for message in messages
        if message_role(message) == "user"
        for content in [message_content(message)]
        if content
    ]


def format_messages_for_prompt(messages: Iterable[Any]) -> str:
    lines = []
    for message in messages:
        content = message_content(message)
        if content:
            lines.append(f"{message_role(message) or 'message'}: {content}")
    return "\n".join(lines)
