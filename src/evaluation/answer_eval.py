from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

from src.evaluation.ragas_eval import parse_contexts, parse_metadata


DEFAULT_MIN_ANSWER_CHARS = 20
DEFAULT_CONTEXT_OVERLAP_THRESHOLD = 0.05
INSUFFICIENT_INFO_PATTERNS = (
    "정보가 부족",
    "근거가 부족",
    "확인되지",
    "알 수 없",
    "제공된 context",
    "제공된 문맥",
    "문맥만으로",
)


@dataclass(frozen=True)
class AnswerEvalResult:
    question: str
    rag_type: str = ""
    has_answer: bool = False
    has_context: bool = False
    has_source_citation: bool = False
    source_citation_count: int = 0
    context_overlap: float = 0.0
    says_insufficient_info: bool = False
    rule_passed: bool = False
    warnings: list[str] = field(default_factory=list)

    def to_record(self) -> dict[str, Any]:
        return {
            "rag_type": self.rag_type,
            "question": self.question,
            "has_answer": self.has_answer,
            "has_context": self.has_context,
            "has_source_citation": self.has_source_citation,
            "source_citation_count": self.source_citation_count,
            "context_overlap": self.context_overlap,
            "says_insufficient_info": self.says_insufficient_info,
            "rule_passed": self.rule_passed,
            "warnings": json.dumps(self.warnings, ensure_ascii=False),
        }


def evaluate_answer_record(
    row: dict[str, Any],
    require_source_citation: bool = True,
    min_answer_chars: int = DEFAULT_MIN_ANSWER_CHARS,
    context_overlap_threshold: float = DEFAULT_CONTEXT_OVERLAP_THRESHOLD,
) -> AnswerEvalResult:
    question = str(row.get("question") or row.get("user_input") or "")
    rag_type = str(row.get("rag_type") or "")
    answer = str(row.get("answer") or "")
    contexts = parse_contexts(row.get("contexts") or row.get("context"))
    sources = parse_contexts(row.get("sources"))
    metadata = parse_metadata(row.get("metadata"))

    warnings: list[str] = []
    has_answer = len(answer.strip()) >= min_answer_chars
    has_context = bool(contexts)
    source_citation_count = count_source_citations(answer)
    has_source_citation = source_citation_count > 0
    says_insufficient_info = contains_insufficient_info_phrase(answer)
    context_overlap = compute_context_overlap(answer, contexts)

    if not has_answer:
        warnings.append("answer is empty or too short")
    if not has_context:
        warnings.append("contexts are empty")
    if require_source_citation and sources and not has_source_citation:
        warnings.append("answer has no source citation")
    if has_context and context_overlap < context_overlap_threshold and not says_insufficient_info:
        warnings.append("answer has low lexical overlap with contexts")
    if not has_context and has_answer and not says_insufficient_info:
        warnings.append("answer should state that evidence is insufficient")

    if metadata.get("requires_source_citation") is False:
        warnings = [warning for warning in warnings if warning != "answer has no source citation"]

    rule_passed = not warnings
    return AnswerEvalResult(
        question=question,
        rag_type=rag_type,
        has_answer=has_answer,
        has_context=has_context,
        has_source_citation=has_source_citation,
        source_citation_count=source_citation_count,
        context_overlap=round(context_overlap, 6),
        says_insufficient_info=says_insufficient_info,
        rule_passed=rule_passed,
        warnings=warnings,
    )


def evaluate_answer_records(
    rows: Iterable[dict[str, Any]],
    require_source_citation: bool = True,
    min_answer_chars: int = DEFAULT_MIN_ANSWER_CHARS,
    context_overlap_threshold: float = DEFAULT_CONTEXT_OVERLAP_THRESHOLD,
) -> pd.DataFrame:
    results = [
        evaluate_answer_record(
            row,
            require_source_citation=require_source_citation,
            min_answer_chars=min_answer_chars,
            context_overlap_threshold=context_overlap_threshold,
        ).to_record()
        for row in rows
    ]
    return pd.DataFrame(results)


def evaluate_answer_csv(
    input_path: str | Path,
    output_path: str | Path | None = None,
    require_source_citation: bool = True,
    min_answer_chars: int = DEFAULT_MIN_ANSWER_CHARS,
    context_overlap_threshold: float = DEFAULT_CONTEXT_OVERLAP_THRESHOLD,
) -> pd.DataFrame:
    frame = pd.read_csv(input_path)
    result = evaluate_answer_records(
        frame.to_dict(orient="records"),
        require_source_citation=require_source_citation,
        min_answer_chars=min_answer_chars,
        context_overlap_threshold=context_overlap_threshold,
    )
    if output_path:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        result.to_csv(output_path, index=False)
    return result


def summarize_answer_eval(frame: pd.DataFrame) -> pd.DataFrame:
    if "rag_type" not in frame.columns:
        raise ValueError("answer eval frame must contain a rag_type column.")
    metric_columns = [
        "has_answer",
        "has_context",
        "has_source_citation",
        "context_overlap",
        "says_insufficient_info",
        "rule_passed",
    ]
    existing_metrics = [column for column in metric_columns if column in frame.columns]
    return frame.groupby("rag_type", dropna=False)[existing_metrics].mean().reset_index()


def count_source_citations(answer: str) -> int:
    bracket_citations = re.findall(r"\[\d+\]", answer)
    url_citations = re.findall(r"https?://\S+", answer)
    source_words = re.findall(r"(?:출처|source)\s*[:：]", answer, flags=re.IGNORECASE)
    return len(bracket_citations) + len(url_citations) + len(source_words)


def contains_insufficient_info_phrase(answer: str) -> bool:
    return any(pattern in answer for pattern in INSUFFICIENT_INFO_PATTERNS)


def compute_context_overlap(answer: str, contexts: list[str]) -> float:
    answer_tokens = tokenize(answer)
    if not answer_tokens:
        return 0.0
    context_tokens = tokenize("\n".join(contexts))
    if not context_tokens:
        return 0.0
    return len(answer_tokens.intersection(context_tokens)) / len(answer_tokens)


def tokenize(text: str) -> set[str]:
    return {
        token.lower()
        for token in re.findall(r"[A-Za-z0-9가-힣]+", text)
        if len(token) > 1
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run rule-based answer evaluation.")
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

    summary_parser = subparsers.add_parser("summary")
    summary_parser.add_argument("answer_eval_csv")
    summary_parser.add_argument("--output-csv")

    args = parser.parse_args()
    if args.command == "evaluate":
        frame = evaluate_answer_csv(
            args.input_csv,
            output_path=args.output_csv,
            require_source_citation=not args.no_source_required,
            min_answer_chars=args.min_answer_chars,
            context_overlap_threshold=args.context_overlap_threshold,
        )
        print(frame.to_string(index=False))
    elif args.command == "summary":
        frame = summarize_answer_eval(pd.read_csv(args.answer_eval_csv))
        if args.output_csv:
            Path(args.output_csv).parent.mkdir(parents=True, exist_ok=True)
            frame.to_csv(args.output_csv, index=False)
        print(frame.to_string(index=False))


if __name__ == "__main__":
    main()
