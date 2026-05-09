from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import pandas as pd


DEFAULT_METRICS = (
    "faithfulness",
    "answer_relevancy",
    "context_precision",
    "context_recall",
)


@dataclass(frozen=True)
class RagasSample:
    question: str
    answer: str
    contexts: list[str]
    ground_truth: str | None = None

    def to_record(self) -> dict[str, Any]:
        record: dict[str, Any] = {
            "question": self.question,
            "answer": self.answer,
            "contexts": self.contexts,
        }
        if self.ground_truth is not None:
            record["ground_truth"] = self.ground_truth
        return record


def load_eval_csv(path: str | Path) -> list[RagasSample]:
    frame = pd.read_csv(path)
    samples = []
    for row in frame.to_dict(orient="records"):
        contexts = row.get("contexts") or row.get("context") or ""
        if isinstance(contexts, str):
            context_list = [part.strip() for part in contexts.split("\n\n") if part.strip()]
        else:
            context_list = list(contexts)

        samples.append(
            RagasSample(
                question=str(row["question"]),
                answer=str(row["answer"]),
                contexts=context_list,
                ground_truth=row.get("ground_truth") or row.get("reference"),
            )
        )
    return samples


def evaluate_rag_samples(
    samples: Iterable[RagasSample | dict[str, Any]],
    metrics: Iterable[str] = DEFAULT_METRICS,
    llm: Any | None = None,
    embeddings: Any | None = None,
) -> pd.DataFrame:
    ragas_evaluate, metric_objects = _load_ragas(metrics)
    dataset = _to_dataset(samples)
    result = ragas_evaluate(
        dataset,
        metrics=metric_objects,
        llm=llm,
        embeddings=embeddings,
    )

    if hasattr(result, "to_pandas"):
        return result.to_pandas()
    if hasattr(result, "scores"):
        return pd.DataFrame(result.scores)
    return pd.DataFrame(result)


def evaluate_rag_csv(
    input_path: str | Path,
    output_path: str | Path | None = None,
    metrics: Iterable[str] = DEFAULT_METRICS,
    llm: Any | None = None,
    embeddings: Any | None = None,
) -> pd.DataFrame:
    frame = evaluate_rag_samples(
        load_eval_csv(input_path),
        metrics=metrics,
        llm=llm,
        embeddings=embeddings,
    )
    if output_path:
        frame.to_csv(output_path, index=False)
    return frame


def _to_dataset(samples: Iterable[RagasSample | dict[str, Any]]) -> Any:
    records = [
        sample.to_record() if isinstance(sample, RagasSample) else dict(sample)
        for sample in samples
    ]
    try:
        from datasets import Dataset
    except ImportError as exc:
        raise RuntimeError(
            "RAGAS evaluation requires the 'datasets' package. "
            "Install project requirements before running evaluation."
        ) from exc
    return Dataset.from_list(records)


def _load_ragas(metric_names: Iterable[str]) -> tuple[Any, list[Any]]:
    try:
        from ragas import evaluate
        from ragas import metrics as ragas_metrics
    except ImportError as exc:
        raise RuntimeError(
            "RAGAS is not installed. Install project requirements before running evaluation."
        ) from exc

    metric_objects = []
    for name in metric_names:
        try:
            metric_objects.append(getattr(ragas_metrics, name))
        except AttributeError as exc:
            raise ValueError(f"Unsupported RAGAS metric: {name}") from exc
    return evaluate, metric_objects
