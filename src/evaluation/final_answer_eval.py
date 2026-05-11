from __future__ import annotations

import argparse
import ast
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable


EVALUATION_PASS = "PASS"
EVALUATION_REPLAN = "REPLAN"
EVALUATION_TOOL_KEY = "evaluation"
DEFAULT_MIN_ANSWER_CHARS = 20
DEFAULT_CONTEXT_OVERLAP_THRESHOLD = 0.05
DEFAULT_QUESTION_OVERLAP_THRESHOLD = 0.05
DEFAULT_REFERENCE_OVERLAP_THRESHOLD = 0.10
DEFAULT_MIN_CONFIDENCE_ON_PASS = 0.50
DEFAULT_MAX_RETRY_COUNT = 2

INSUFFICIENT_INFO_PATTERNS = (
    "\uc815\ubcf4\uac00 \ubd80\uc871",
    "\uadfc\uac70\uac00 \ubd80\uc871",
    "\uadfc\uac70\ub9cc\uc73c\ub85c\ub294",
    "\ud655\uc815\ud558\uae30 \uc5b4\ub835",
    "\ud655\uc778\ud558\uae30 \uc5b4\ub835",
    "\ucd94\uac00 \uc815\ubcf4",
    "insufficient",
    "not enough",
)


def parse_contexts(value: Any) -> list[str]:
    if is_empty_scalar(value):
        return []
    if isinstance(value, list | tuple):
        return [str(item).strip() for item in value if str(item).strip()]

    text = str(value).strip()
    if not text:
        return []

    if text.startswith("[") and text.endswith("]"):
        for loader in (json.loads, ast.literal_eval):
            try:
                parsed = loader(text)
            except (ValueError, SyntaxError, TypeError, json.JSONDecodeError):
                continue
            if isinstance(parsed, list | tuple):
                return [str(item).strip() for item in parsed if str(item).strip()]

    if "\n\n" in text:
        return [part.strip() for part in text.split("\n\n") if part.strip()]
    return [text]


def parse_metadata(value: Any) -> dict[str, Any]:
    if is_empty_scalar(value):
        return {}
    if isinstance(value, dict):
        return value
    text = str(value).strip()
    if not text:
        return {}
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        try:
            parsed = ast.literal_eval(text)
        except (ValueError, SyntaxError):
            return {"raw": text}
    return parsed if isinstance(parsed, dict) else {"raw": parsed}


@dataclass(frozen=True)
class FinalAnswerEvalResult:
    eval_id: str
    rag_type: str
    task_type: str
    question: str
    has_answer: bool
    answer_relevant: bool
    grounded_in_context: bool
    has_source_citation: bool
    handles_insufficient_context: bool
    confidence_consistent: bool
    final_pass: bool
    final_answer_chars: int
    source_citation_count: int
    question_overlap: float
    context_overlap: float
    reference_overlap: float
    confidence_score: float | None = None
    validation_passed: bool | None = None
    warnings: list[str] = field(default_factory=list)

    def to_record(self) -> dict[str, Any]:
        return {
            "eval_id": self.eval_id,
            "rag_type": self.rag_type,
            "task_type": self.task_type,
            "question": self.question,
            "has_answer": self.has_answer,
            "answer_relevant": self.answer_relevant,
            "grounded_in_context": self.grounded_in_context,
            "has_source_citation": self.has_source_citation,
            "handles_insufficient_context": self.handles_insufficient_context,
            "confidence_consistent": self.confidence_consistent,
            "final_pass": self.final_pass,
            "final_answer_chars": self.final_answer_chars,
            "source_citation_count": self.source_citation_count,
            "question_overlap": self.question_overlap,
            "context_overlap": self.context_overlap,
            "reference_overlap": self.reference_overlap,
            "confidence_score": self.confidence_score,
            "validation_passed": self.validation_passed,
            "warnings": json.dumps(self.warnings, ensure_ascii=False),
        }


def evaluate_final_answer_record(
    row: dict[str, Any],
    require_source_citation: bool = True,
    min_answer_chars: int = DEFAULT_MIN_ANSWER_CHARS,
    context_overlap_threshold: float = DEFAULT_CONTEXT_OVERLAP_THRESHOLD,
    question_overlap_threshold: float = DEFAULT_QUESTION_OVERLAP_THRESHOLD,
    reference_overlap_threshold: float = DEFAULT_REFERENCE_OVERLAP_THRESHOLD,
    min_confidence_on_pass: float = DEFAULT_MIN_CONFIDENCE_ON_PASS,
) -> FinalAnswerEvalResult:
    eval_id = get_first_text(row, "eval_id", "case_id", "id")
    rag_type = get_first_text(row, "rag_type")
    task_type = get_first_text(row, "task_type", "intent", "query_type")
    question = get_first_text(row, "question", "user_query", "user_input")
    answer = get_first_text(row, "final_answer", "answer", "response")
    reference = get_first_text(row, "reference", "ground_truth", "expected_answer")
    contexts = parse_contexts(
        get_first_value(row, "contexts", "context", "retrieved_contexts")
    )
    sources = parse_contexts(get_first_value(row, "sources", "source_urls"))
    metadata = parse_metadata(row.get("metadata"))
    confidence_score = parse_optional_float(
        get_first_value(row, "confidence_score", "confidence")
    )
    validation_passed = parse_optional_bool(row.get("validation_passed"))

    warnings: list[str] = []
    answer_text = answer.strip()
    has_answer = len(answer_text) >= min_answer_chars
    says_insufficient_info = contains_insufficient_info_phrase(answer_text)

    question_overlap = compute_overlap(answer_text, [question])
    context_overlap = compute_overlap(answer_text, contexts)
    reference_overlap = compute_overlap(answer_text, [reference] if reference else [])

    answer_relevant = is_answer_relevant(
        question_overlap=question_overlap,
        reference_overlap=reference_overlap,
        has_reference=bool(reference.strip()),
        question_overlap_threshold=question_overlap_threshold,
        reference_overlap_threshold=reference_overlap_threshold,
    )
    grounded_in_context = (
        bool(contexts) and context_overlap >= context_overlap_threshold
    ) or says_insufficient_info
    handles_insufficient_context = bool(contexts) or says_insufficient_info

    source_citation_count = count_source_citations(answer_text)
    has_source_citation = source_citation_count > 0
    source_required = should_require_source_citation(
        metadata=metadata,
        default_required=require_source_citation,
        has_sources=bool(sources),
    )

    confidence_consistent = is_confidence_consistent(
        validation_passed=validation_passed,
        confidence_score=confidence_score,
        min_confidence_on_pass=min_confidence_on_pass,
    )

    if not has_answer:
        warnings.append("final answer is empty or too short")
    if not answer_relevant:
        warnings.append("final answer does not sufficiently overlap the question/reference")
    if not grounded_in_context:
        warnings.append("final answer is not sufficiently grounded in contexts")
    if source_required and not has_source_citation:
        warnings.append("final answer has no source citation")
    if not handles_insufficient_context:
        warnings.append("final answer should state that evidence is insufficient")
    if validation_passed is False and metadata.get("enforce_validation_passed") is True:
        warnings.append("state validation_passed is false")
    if not confidence_consistent:
        warnings.append("confidence score is inconsistent with validation result")

    final_pass = not warnings
    return FinalAnswerEvalResult(
        eval_id=eval_id,
        rag_type=rag_type,
        task_type=task_type,
        question=question,
        has_answer=has_answer,
        answer_relevant=answer_relevant,
        grounded_in_context=grounded_in_context,
        has_source_citation=has_source_citation,
        handles_insufficient_context=handles_insufficient_context,
        confidence_consistent=confidence_consistent,
        final_pass=final_pass,
        final_answer_chars=len(answer_text),
        source_citation_count=source_citation_count,
        question_overlap=round(question_overlap, 6),
        context_overlap=round(context_overlap, 6),
        reference_overlap=round(reference_overlap, 6),
        confidence_score=confidence_score,
        validation_passed=validation_passed,
        warnings=warnings,
    )


def evaluate_final_answer_records(
    rows: Iterable[dict[str, Any]],
    require_source_citation: bool = True,
    min_answer_chars: int = DEFAULT_MIN_ANSWER_CHARS,
    context_overlap_threshold: float = DEFAULT_CONTEXT_OVERLAP_THRESHOLD,
    question_overlap_threshold: float = DEFAULT_QUESTION_OVERLAP_THRESHOLD,
    reference_overlap_threshold: float = DEFAULT_REFERENCE_OVERLAP_THRESHOLD,
    min_confidence_on_pass: float = DEFAULT_MIN_CONFIDENCE_ON_PASS,
) -> Any:
    import pandas as pd

    return pd.DataFrame(
        [
            evaluate_final_answer_record(
                row,
                require_source_citation=require_source_citation,
                min_answer_chars=min_answer_chars,
                context_overlap_threshold=context_overlap_threshold,
                question_overlap_threshold=question_overlap_threshold,
                reference_overlap_threshold=reference_overlap_threshold,
                min_confidence_on_pass=min_confidence_on_pass,
            ).to_record()
            for row in rows
        ]
    )


def evaluate_final_answer_csv(
    input_path: str | Path,
    output_path: str | Path | None = None,
    require_source_citation: bool = True,
    min_answer_chars: int = DEFAULT_MIN_ANSWER_CHARS,
    context_overlap_threshold: float = DEFAULT_CONTEXT_OVERLAP_THRESHOLD,
    question_overlap_threshold: float = DEFAULT_QUESTION_OVERLAP_THRESHOLD,
    reference_overlap_threshold: float = DEFAULT_REFERENCE_OVERLAP_THRESHOLD,
    min_confidence_on_pass: float = DEFAULT_MIN_CONFIDENCE_ON_PASS,
) -> Any:
    import pandas as pd

    frame = pd.read_csv(input_path)
    result = evaluate_final_answer_records(
        frame.to_dict(orient="records"),
        require_source_citation=require_source_citation,
        min_answer_chars=min_answer_chars,
        context_overlap_threshold=context_overlap_threshold,
        question_overlap_threshold=question_overlap_threshold,
        reference_overlap_threshold=reference_overlap_threshold,
        min_confidence_on_pass=min_confidence_on_pass,
    )
    if output_path:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        result.to_csv(output_path, index=False)
    return result


def summarize_final_answer_eval(
    frame: Any,
    group_by: str | None = None,
) -> Any:
    metric_columns = [
        "has_answer",
        "answer_relevant",
        "grounded_in_context",
        "has_source_citation",
        "handles_insufficient_context",
        "confidence_consistent",
        "final_pass",
        "question_overlap",
        "context_overlap",
        "reference_overlap",
        "final_answer_chars",
    ]
    existing_metrics = [column for column in metric_columns if column in frame.columns]
    if not existing_metrics:
        raise ValueError(
            "summary requires an evaluated CSV. Run the evaluate command first."
        )
    if group_by:
        if group_by not in frame.columns:
            raise ValueError(f"summary group column does not exist: {group_by}")
        summary = frame.groupby(group_by, dropna=False)[existing_metrics].mean().reset_index()
        summary.insert(1, "row_count", frame.groupby(group_by, dropna=False).size().values)
        return summary

    summary = frame[existing_metrics].mean(numeric_only=True).to_frame().T
    summary.insert(0, "row_count", len(frame))
    return summary


def run_final_answer_evaluation(
    state: dict[str, Any],
    *,
    apply_route: bool = False,
    max_retry_count: int = DEFAULT_MAX_RETRY_COUNT,
    require_source_citation: bool = True,
    min_answer_chars: int = DEFAULT_MIN_ANSWER_CHARS,
    context_overlap_threshold: float = DEFAULT_CONTEXT_OVERLAP_THRESHOLD,
    question_overlap_threshold: float = DEFAULT_QUESTION_OVERLAP_THRESHOLD,
    reference_overlap_threshold: float = DEFAULT_REFERENCE_OVERLAP_THRESHOLD,
    min_confidence_on_pass: float = DEFAULT_MIN_CONFIDENCE_ON_PASS,
) -> dict[str, Any]:
    """Evaluate AgentState after final_answer and write an evaluation tool result.

    When apply_route is False, this function is a pure evaluation node: it stores
    tool_results["evaluation"], then lets src.agents.final_answer.route_after_evaluation
    decide the next graph hop. When apply_route is True, it also writes next_agent,
    retry_target, retry_count, and is_complete for simpler pipelines.
    """

    result = evaluate_final_answer_record(
        final_answer_state_to_record(state),
        require_source_citation=require_source_citation,
        min_answer_chars=min_answer_chars,
        context_overlap_threshold=context_overlap_threshold,
        question_overlap_threshold=question_overlap_threshold,
        reference_overlap_threshold=reference_overlap_threshold,
        min_confidence_on_pass=min_confidence_on_pass,
    )
    retry_count = int(state.get("retry_count") or 0)
    evaluation = build_evaluation_tool_result(
        result,
        retry_count=retry_count,
        max_retry_count=max_retry_count,
    )

    next_state = {
        **state,
        "validation_passed": result.final_pass,
        "feedback": evaluation["feedback"],
        "tool_results": merge_evaluation_tool_result(state, evaluation),
    }

    if not apply_route:
        return next_state

    routed_state = dict(next_state)
    route = evaluation["route"]
    next_agent = evaluation["next_agent"]
    routed_state["next_agent"] = next_agent
    routed_state["retry_target"] = next_agent
    routed_state["is_complete"] = route == EVALUATION_PASS
    if route != EVALUATION_PASS:
        routed_state["retry_count"] = retry_count + 1
    return routed_state


def final_answer_state_to_record(state: dict[str, Any]) -> dict[str, Any]:
    retrieved_docs = state.get("retrieved_docs") or []
    sources = state.get("sources") or sources_from_retrieved_docs(retrieved_docs)
    metadata = {
        "requires_source_citation": bool(sources),
        "state_eval": True,
    }
    return {
        "eval_id": state.get("eval_id") or state.get("request_id") or "",
        "rag_type": state.get("rag_type") or "",
        "task_type": state.get("task_type") or state.get("intent") or "",
        "question": state.get("user_query") or state.get("question") or "",
        "final_answer": state.get("final_answer") or "",
        "contexts": state.get("context") or contexts_from_retrieved_docs(retrieved_docs),
        "sources": sources,
        "reference": state.get("reference") or state.get("ground_truth") or "",
        "confidence_score": state.get("confidence_score"),
        "metadata": metadata,
    }


def build_evaluation_tool_result(
    result: FinalAnswerEvalResult,
    *,
    retry_count: int,
    max_retry_count: int = DEFAULT_MAX_RETRY_COUNT,
) -> dict[str, Any]:
    route = choose_evaluation_route(
        result,
        retry_count=retry_count,
        max_retry_count=max_retry_count,
    )
    next_agent = next_agent_for_route(route)
    feedback = build_evaluation_feedback(result, route)
    return {
        "agent": "evaluation",
        "is_pass": result.final_pass,
        "route": route,
        "next_agent": next_agent,
        "retry_target": next_agent,
        "feedback": feedback,
        "reason": feedback,
        "warnings": result.warnings,
        "failure_type": infer_failure_type(result),
        "score": calculate_quality_score(result),
        "metrics": result.to_record(),
        "retry_count": retry_count,
        "max_retry_count": max_retry_count,
    }


def choose_evaluation_route(
    result: FinalAnswerEvalResult,
    *,
    retry_count: int,
    max_retry_count: int,
) -> str:
    if result.final_pass:
        return EVALUATION_PASS
    return EVALUATION_REPLAN


def next_agent_for_route(route: str) -> str:
    if route == EVALUATION_PASS:
        return "FINISH"
    return "supervisor"


def build_evaluation_feedback(result: FinalAnswerEvalResult, route: str) -> str:
    if result.final_pass:
        return "Final answer passed rule-based evaluation."
    warning_text = "; ".join(result.warnings) if result.warnings else "unknown failure"
    return f"Send back to supervisor: {warning_text}"


def infer_failure_type(result: FinalAnswerEvalResult) -> str:
    if result.final_pass:
        return ""
    if not result.answer_relevant:
        return "question_mismatch"
    if not result.handles_insufficient_context:
        return "missing_context"
    if not result.grounded_in_context:
        return "ungrounded"
    if not result.has_source_citation:
        return "missing_source"
    if not result.has_answer:
        return "empty_answer"
    return "quality_rule_failed"


def calculate_quality_score(result: FinalAnswerEvalResult) -> float:
    checks = [
        result.has_answer,
        result.answer_relevant,
        result.grounded_in_context,
        result.has_source_citation,
        result.handles_insufficient_context,
        result.confidence_consistent,
    ]
    return round(sum(1 for check in checks if check) / len(checks), 6)


def merge_evaluation_tool_result(
    state: dict[str, Any],
    evaluation: dict[str, Any],
) -> dict[str, Any]:
    tool_results = dict(state.get("tool_results") or {})
    tool_results[EVALUATION_TOOL_KEY] = evaluation
    return tool_results


def contexts_from_retrieved_docs(retrieved_docs: Any) -> list[str]:
    contexts: list[str] = []
    if not isinstance(retrieved_docs, list):
        return contexts
    for document in retrieved_docs:
        if not isinstance(document, dict):
            continue
        content = str(document.get("page_content") or "").strip()
        if content:
            contexts.append(content)
    return contexts


def sources_from_retrieved_docs(retrieved_docs: Any) -> list[str]:
    sources: list[str] = []
    if not isinstance(retrieved_docs, list):
        return sources
    for document in retrieved_docs:
        if not isinstance(document, dict):
            continue
        metadata = document.get("metadata") or {}
        source = (
            metadata.get("url")
            or metadata.get("source_url")
            or metadata.get("source")
            or metadata.get("title")
            or document.get("source")
        )
        if source and str(source) not in sources:
            sources.append(str(source))
    return sources


def is_answer_relevant(
    question_overlap: float,
    reference_overlap: float,
    has_reference: bool,
    question_overlap_threshold: float,
    reference_overlap_threshold: float,
) -> bool:
    if has_reference and reference_overlap >= reference_overlap_threshold:
        return True
    return question_overlap >= question_overlap_threshold


def should_require_source_citation(
    metadata: dict[str, Any],
    default_required: bool,
    has_sources: bool,
) -> bool:
    if metadata.get("requires_source_citation") is False:
        return False
    if metadata.get("requires_source_citation") is True:
        return True
    return default_required and has_sources


def is_confidence_consistent(
    validation_passed: bool | None,
    confidence_score: float | None,
    min_confidence_on_pass: float,
) -> bool:
    if validation_passed is None or confidence_score is None:
        return True
    if validation_passed and confidence_score < min_confidence_on_pass:
        return False
    return True


def count_source_citations(answer: str) -> int:
    bracket_citations = re.findall(r"\[\d+\]", answer)
    urls = re.findall(r"https?://\S+", answer)
    source_words = re.findall(
        r"(?:source|\ucd9c\ucc98|\uadfc\uac70)\s*[:：]?",
        answer,
        flags=re.IGNORECASE,
    )
    return len(bracket_citations) + len(urls) + len(source_words)


def contains_insufficient_info_phrase(answer: str) -> bool:
    lower_answer = answer.lower()
    return any(pattern.lower() in lower_answer for pattern in INSUFFICIENT_INFO_PATTERNS)


def compute_overlap(answer: str, references: list[str]) -> float:
    answer_tokens = tokenize(answer)
    if not answer_tokens:
        return 0.0
    reference_tokens = tokenize("\n".join(references))
    if not reference_tokens:
        return 0.0
    return len(answer_tokens.intersection(reference_tokens)) / len(answer_tokens)


def tokenize(text: str) -> set[str]:
    return {
        token.lower()
        for token in re.findall(r"[A-Za-z0-9\uac00-\ud7a3]+", text)
        if len(token) > 1
    }


def get_first_value(row: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = row.get(key)
        if not is_empty_scalar(value):
            return value
    return ""


def get_first_text(row: dict[str, Any], *keys: str) -> str:
    value = get_first_value(row, *keys)
    return "" if is_empty_scalar(value) else str(value)


def is_empty_scalar(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, float):
        return value != value
    return False


def parse_optional_float(value: Any) -> float | None:
    if is_empty_scalar(value):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def parse_optional_bool(value: Any) -> bool | None:
    if is_empty_scalar(value):
        return None
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"true", "1", "yes", "y", "pass", "passed"}:
        return True
    if text in {"false", "0", "no", "n", "fail", "failed"}:
        return False
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description="Run rule-based final answer evaluation.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    evaluate_parser = subparsers.add_parser("evaluate")
    evaluate_parser.add_argument("input_csv")
    evaluate_parser.add_argument("--output-csv")
    evaluate_parser.add_argument("--no-source-required", action="store_true")
    evaluate_parser.add_argument("--min-answer-chars", type=int, default=DEFAULT_MIN_ANSWER_CHARS)
    evaluate_parser.add_argument(
        "--context-overlap-threshold",
        type=float,
        default=DEFAULT_CONTEXT_OVERLAP_THRESHOLD,
    )
    evaluate_parser.add_argument(
        "--question-overlap-threshold",
        type=float,
        default=DEFAULT_QUESTION_OVERLAP_THRESHOLD,
    )
    evaluate_parser.add_argument(
        "--reference-overlap-threshold",
        type=float,
        default=DEFAULT_REFERENCE_OVERLAP_THRESHOLD,
    )
    evaluate_parser.add_argument(
        "--min-confidence-on-pass",
        type=float,
        default=DEFAULT_MIN_CONFIDENCE_ON_PASS,
    )

    summary_parser = subparsers.add_parser("summary")
    summary_parser.add_argument("final_answer_eval_csv")
    summary_parser.add_argument("--output-csv")
    summary_parser.add_argument("--group-by")

    state_parser = subparsers.add_parser("evaluate-state")
    state_parser.add_argument("state_json")
    state_parser.add_argument("--output-json")
    state_parser.add_argument("--apply-route", action="store_true")
    state_parser.add_argument("--no-source-required", action="store_true")
    state_parser.add_argument("--max-retry-count", type=int, default=DEFAULT_MAX_RETRY_COUNT)

    args = parser.parse_args()
    if args.command == "evaluate":
        frame = evaluate_final_answer_csv(
            args.input_csv,
            output_path=args.output_csv,
            require_source_citation=not args.no_source_required,
            min_answer_chars=args.min_answer_chars,
            context_overlap_threshold=args.context_overlap_threshold,
            question_overlap_threshold=args.question_overlap_threshold,
            reference_overlap_threshold=args.reference_overlap_threshold,
            min_confidence_on_pass=args.min_confidence_on_pass,
        )
        print(frame.to_string(index=False))
    elif args.command == "summary":
        import pandas as pd

        frame = summarize_final_answer_eval(
            pd.read_csv(args.final_answer_eval_csv),
            group_by=args.group_by,
        )
        if args.output_csv:
            Path(args.output_csv).parent.mkdir(parents=True, exist_ok=True)
            frame.to_csv(args.output_csv, index=False)
        print(frame.to_string(index=False))
    elif args.command == "evaluate-state":
        state = json.loads(Path(args.state_json).read_text(encoding="utf-8"))
        result = run_final_answer_evaluation(
            state,
            apply_route=args.apply_route,
            max_retry_count=args.max_retry_count,
            require_source_citation=not args.no_source_required,
        )
        output = json.dumps(result, ensure_ascii=False, indent=2)
        if args.output_json:
            Path(args.output_json).parent.mkdir(parents=True, exist_ok=True)
            Path(args.output_json).write_text(output, encoding="utf-8")
        print(output)


if __name__ == "__main__":
    main()
