from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable

from common.state import AgentState, NextAgent, RetrievedDocument
from common.validator import validate_agent_inputs, validate_agent_outputs


DEFAULT_PASS_THRESHOLD = 0.72
DEFAULT_MAX_RETRY_COUNT = 2

STOPWORDS = {
    "그리고",
    "그래서",
    "하지만",
    "또는",
    "있는",
    "없는",
    "하는",
    "하면",
    "해서",
    "관련",
    "알려줘",
    "추천",
    "어떻게",
    "무엇",
    "뭐야",
    "해주세요",
}


@dataclass(frozen=True)
class EvaluationScores:
    relevance: float
    faithfulness: float
    completeness: float
    reliability: float

    @property
    def confidence(self) -> float:
        return round(
            self.relevance * 0.35
            + self.faithfulness * 0.35
            + self.completeness * 0.20
            + self.reliability * 0.10,
            4,
        )


@dataclass(frozen=True)
class EvaluationDecision:
    passed: bool
    retry_target: NextAgent
    feedback: str
    scores: EvaluationScores


def evaluation_agent(
    state: AgentState,
    *,
    pass_threshold: float = DEFAULT_PASS_THRESHOLD,
    max_retry_count: int = DEFAULT_MAX_RETRY_COUNT,
) -> AgentState:
    """LangGraph-compatible evaluation node.

    The first version is intentionally rule-based so it can run without an
    external judge model. A future LLM/RAGAS judge can be added behind the same
    state contract.
    """

    validate_agent_inputs("evaluation", state)
    decision = evaluate_answer(
        state,
        pass_threshold=pass_threshold,
        max_retry_count=max_retry_count,
    )

    retry_count = int(state.get("retry_count") or 0)
    can_retry = (
        not decision.passed
        and decision.retry_target != "FINISH"
        and retry_count < max_retry_count
    )
    next_retry_count = retry_count + 1 if can_retry else retry_count
    next_agent: NextAgent = decision.retry_target if can_retry else "FINISH"

    next_state: AgentState = {
        **state,
        "validation_passed": decision.passed,
        "confidence_score": decision.scores.confidence,
        "feedback": decision.feedback,
        "retry_target": decision.retry_target,
        "retry_count": next_retry_count,
        "next_agent": next_agent,
        "is_complete": next_agent == "FINISH",
        "completed_agents": _append_completed_agent(
            state.get("completed_agents", []),
            "evaluation",
        ),
        "tool_results": {
            **state.get("tool_results", {}),
            "evaluation": {
                "scores": {
                    "relevance": decision.scores.relevance,
                    "faithfulness": decision.scores.faithfulness,
                    "completeness": decision.scores.completeness,
                    "reliability": decision.scores.reliability,
                    "confidence": decision.scores.confidence,
                },
                "passed": decision.passed,
                "retry_target": decision.retry_target,
            },
        },
    }
    validate_agent_outputs("evaluation", next_state)
    return next_state


def evaluate_answer(
    state: AgentState,
    *,
    pass_threshold: float = DEFAULT_PASS_THRESHOLD,
    max_retry_count: int = DEFAULT_MAX_RETRY_COUNT,
) -> EvaluationDecision:
    question = _clean_text(state.get("user_query"))
    answer = _clean_text(state.get("final_answer") or state.get("draft_answer"))
    context = _combined_context(state.get("context"), state.get("retrieved_docs", []))
    errors = [str(error) for error in state.get("errors", [])]

    if not answer:
        scores = EvaluationScores(0.0, 0.0, 0.0, _error_reliability(errors))
        return EvaluationDecision(
            passed=False,
            retry_target="final_answer",
            feedback="최종 답변이 비어 있어 final_answer 단계에서 답변을 다시 생성해야 합니다.",
            scores=scores,
        )

    relevance = _question_relevance(question, answer)
    faithfulness = _faithfulness(answer, context, question)
    completeness = _completeness(question, answer)
    reliability = _error_reliability(errors)

    scores = EvaluationScores(
        relevance=relevance,
        faithfulness=faithfulness,
        completeness=completeness,
        reliability=reliability,
    )
    retry_target = _select_retry_target(
        scores=scores,
        has_context=bool(context),
        errors=errors,
    )
    if retry_target == "FINISH" and scores.confidence < pass_threshold:
        retry_target = "final_answer"
    passed = scores.confidence >= pass_threshold and retry_target == "FINISH"
    feedback = _build_feedback(
        scores=scores,
        passed=passed,
        retry_target=retry_target,
        retry_count=int(state.get("retry_count") or 0),
        max_retry_count=max_retry_count,
        errors=errors,
    )
    return EvaluationDecision(
        passed=passed,
        retry_target=retry_target,
        feedback=feedback,
        scores=scores,
    )


def _select_retry_target(
    *,
    scores: EvaluationScores,
    has_context: bool,
    errors: list[str],
) -> NextAgent:
    error_target = _target_from_errors(errors)
    if error_target != "FINISH":
        return error_target
    if scores.faithfulness < 0.45 and not has_context:
        return "research"
    if scores.faithfulness < 0.55:
        return "final_answer"
    if scores.relevance < 0.55:
        return "final_answer"
    if scores.completeness < 0.45:
        return "final_answer"
    if scores.reliability < 0.5:
        return "supervisor"
    return "FINISH"


def _build_feedback(
    *,
    scores: EvaluationScores,
    passed: bool,
    retry_target: NextAgent,
    retry_count: int,
    max_retry_count: int,
    errors: list[str],
) -> str:
    details = [
        f"relevance={scores.relevance:.2f}",
        f"faithfulness={scores.faithfulness:.2f}",
        f"completeness={scores.completeness:.2f}",
        f"reliability={scores.reliability:.2f}",
        f"confidence={scores.confidence:.2f}",
    ]
    if passed:
        return "평가 통과: " + ", ".join(details)

    reasons = []
    if scores.relevance < 0.55:
        reasons.append("질문 의도 반영이 부족합니다")
    if scores.faithfulness < 0.55:
        reasons.append("검색 근거와의 연결이 부족합니다")
    if scores.completeness < 0.45:
        reasons.append("답변의 필수 정보가 부족합니다")
    if errors:
        reasons.append(f"실행 오류가 있습니다: {'; '.join(errors[:2])}")
    if not reasons:
        reasons.append("종합 점수가 통과 기준에 미달했습니다")

    if retry_count >= max_retry_count:
        reasons.append("최대 재시도 횟수에 도달해 종료 대상으로 표시합니다")

    return (
        f"평가 실패: {'; '.join(reasons)}. "
        f"retry_target={retry_target}. "
        + ", ".join(details)
    )


def _question_relevance(question: str, answer: str) -> float:
    question_tokens = set(_tokens(question))
    answer_tokens = set(_tokens(answer))
    if not question_tokens:
        return 1.0
    if not answer_tokens:
        return 0.0

    hits = len(question_tokens & answer_tokens)
    denominator = max(1, min(len(question_tokens), 8))
    score = hits / denominator
    if question and question in answer:
        score += 0.15
    return _clamp(score)


def _faithfulness(answer: str, context: str, question: str) -> float:
    answer_tokens = set(_tokens(answer))
    context_tokens = set(_tokens(context))
    question_tokens = set(_tokens(question))

    if not answer_tokens:
        return 0.0
    if not context_tokens:
        return 0.35 if _is_cautious_answer(answer) else 0.15

    content_tokens = answer_tokens - question_tokens
    if not content_tokens:
        return 0.7

    grounded_hits = len(content_tokens & context_tokens)
    denominator = max(1, min(len(content_tokens), 14))
    score = grounded_hits / denominator

    if _has_source_marker(answer):
        score += 0.10
    if _has_unsupported_certainty(answer, context):
        score -= 0.15
    return _clamp(score)


def _completeness(question: str, answer: str) -> float:
    answer_length = len(answer.replace(" ", ""))
    length_score = min(answer_length / 180, 1.0)
    relevance_score = _question_relevance(question, answer)
    structure_score = 0.0
    if any(marker in answer for marker in ("1.", "-", ":", "때문", "기준", "추천", "필요")):
        structure_score = 0.2
    return _clamp(length_score * 0.45 + relevance_score * 0.35 + structure_score)


def _error_reliability(errors: list[str]) -> float:
    if not errors:
        return 1.0
    if len(errors) == 1:
        return 0.65
    return 0.35


def _target_from_errors(errors: list[str]) -> NextAgent:
    joined = " ".join(errors).lower()
    if not joined:
        return "FINISH"
    if "research" in joined or "rag" in joined or "db_search" in joined:
        return "research"
    if "analystic" in joined or "analytics" in joined:
        return "analystic"
    if "final_answer" in joined or "answer" in joined:
        return "final_answer"
    if "calculator" in joined:
        return "calculator"
    return "supervisor"


def _combined_context(
    context: object,
    retrieved_docs: Iterable[RetrievedDocument],
) -> str:
    parts = []
    if context:
        parts.append(str(context))
    for document in retrieved_docs:
        content = document.get("page_content")
        if content:
            parts.append(str(content))
    return "\n\n".join(parts)


def _append_completed_agent(completed_agents: object, agent_name: str) -> list[str]:
    agents = list(completed_agents) if isinstance(completed_agents, list) else []
    if agent_name not in agents:
        agents.append(agent_name)
    return agents


def _tokens(text: str) -> list[str]:
    return [
        token
        for token in re.findall(r"[0-9A-Za-z가-힣]+", text.lower())
        if len(token) > 1 and token not in STOPWORDS
    ]


def _clean_text(value: object) -> str:
    return str(value or "").strip()


def _clamp(value: float) -> float:
    return round(max(0.0, min(1.0, value)), 4)


def _has_source_marker(answer: str) -> bool:
    return bool(re.search(r"\[[0-9]+\]|출처|근거|context|source", answer, re.IGNORECASE))


def _is_cautious_answer(answer: str) -> bool:
    return any(
        marker in answer
        for marker in ("확인되지", "근거가 부족", "알 수 없", "제공된 정보", "추정")
    )


def _has_unsupported_certainty(answer: str, context: str) -> bool:
    certainty_markers = ("반드시", "확실", "무조건", "항상", "절대")
    if not any(marker in answer for marker in certainty_markers):
        return False
    return not any(marker in context for marker in certainty_markers)


__all__ = [
    "DEFAULT_MAX_RETRY_COUNT",
    "DEFAULT_PASS_THRESHOLD",
    "EvaluationDecision",
    "EvaluationScores",
    "evaluate_answer",
    "evaluation_agent",
]
