from __future__ import annotations

import argparse
import ast
import json
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Literal, Sequence

import pandas as pd


RagType = Literal["pgvector", "graph", "db_search", "web"]
AnswerMode = Literal["extractive", "llm"]

DEFAULT_METRICS = (
    "faithfulness",
    "answer_relevancy",
    "context_precision",
    "context_recall",
)


@dataclass(frozen=True)
class RagasRecord:
    question: str
    contexts: list[str]
    answer: str = ""
    ground_truth: str | None = None
    reference_contexts: list[str] = field(default_factory=list)
    rag_type: str | None = None
    sources: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, row: dict[str, Any]) -> "RagasRecord":
        question = row.get("question") or row.get("user_input") or ""
        ground_truth = row.get("ground_truth") or row.get("reference")
        contexts = row.get("contexts") or row.get("context") or row.get("retrieved_contexts")
        answer = row.get("answer") or row.get("response") or ""
        return cls(
            question=str(question),
            contexts=parse_contexts(contexts),
            answer=str(answer),
            ground_truth=str(ground_truth) if not _is_empty_scalar(ground_truth) else None,
            reference_contexts=parse_contexts(row.get("reference_contexts")),
            rag_type=str(row.get("rag_type")) if not _is_empty_scalar(row.get("rag_type")) else None,
            sources=parse_contexts(row.get("sources")),
            metadata=parse_metadata(row.get("metadata")),
        )

    def to_ragas_record(self) -> dict[str, Any]:
        record: dict[str, Any] = {
            "user_input": self.question,
            "retrieved_contexts": self.contexts,
            "response": self.answer,
        }
        if self.ground_truth is not None:
            record["reference"] = self.ground_truth
        return record

    def to_csv_record(self) -> dict[str, Any]:
        return {
            "rag_type": self.rag_type or "",
            "question": self.question,
            "contexts": _json_dumps(self.contexts),
            "answer": self.answer,
            "ground_truth": self.ground_truth or "",
            "reference_contexts": _json_dumps(self.reference_contexts),
            "sources": _json_dumps(self.sources),
            "metadata": _json_dumps(self.metadata),
            "user_input": self.question,
            "retrieved_contexts": _json_dumps(self.contexts),
            "response": self.answer,
            "reference": self.ground_truth or "",
        }


@dataclass(frozen=True)
class RAGContextResult:
    rag_type: str
    question: str
    contexts: list[str]
    sources: list[str]
    retrieved_docs: list[dict[str, Any]]
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_record(
        self,
        answer: str = "",
        ground_truth: str | None = None,
        reference_contexts: Sequence[str] | None = None,
    ) -> RagasRecord:
        return RagasRecord(
            rag_type=self.rag_type,
            question=self.question,
            contexts=self.contexts,
            answer=answer,
            ground_truth=ground_truth,
            reference_contexts=list(reference_contexts or []),
            sources=self.sources,
            metadata=self.metadata,
        )


def parse_contexts(value: Any) -> list[str]:
    if _is_empty_scalar(value):
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
    if _is_empty_scalar(value):
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


def retrieved_docs_to_contexts(docs: Iterable[dict[str, Any]]) -> list[str]:
    contexts = []
    for doc in docs:
        content = str(doc.get("page_content") or "").strip()
        if content:
            contexts.append(content)
    return contexts


def retrieved_docs_to_sources(docs: Iterable[dict[str, Any]]) -> list[str]:
    sources = []
    for doc in docs:
        metadata = doc.get("metadata") or {}
        source = (
            doc.get("source")
            or metadata.get("url")
            or metadata.get("source_url")
            or metadata.get("title")
        )
        if source and str(source) not in sources:
            sources.append(str(source))
    return sources


def collect_rag_contexts(
    rag_type: RagType,
    question: str,
    **kwargs: Any,
) -> RAGContextResult:
    top_k = int(kwargs.pop("top_k", 5))

    if rag_type == "pgvector":
        docs = _collect_pgvector_docs(question, top_k, **kwargs)
    elif rag_type == "graph":
        docs = _collect_graph_docs(question, top_k, **kwargs)
    elif rag_type == "db_search":
        docs = _collect_db_search_docs(question, top_k, **kwargs)
    elif rag_type == "web":
        docs = _collect_web_docs(question, top_k, **kwargs)
    else:
        raise ValueError(f"Unsupported rag_type: {rag_type}")

    return RAGContextResult(
        rag_type=rag_type,
        question=question,
        contexts=retrieved_docs_to_contexts(docs),
        sources=retrieved_docs_to_sources(docs),
        retrieved_docs=docs,
        metadata={"top_k": top_k, **kwargs},
    )


def build_rag_record(
    rag_type: RagType,
    question: str,
    answer: str = "",
    ground_truth: str | None = None,
    reference_contexts: Sequence[str] | None = None,
    **retrieve_kwargs: Any,
) -> RagasRecord:
    result = collect_rag_contexts(rag_type, question, **retrieve_kwargs)
    return result.to_record(
        answer=answer,
        ground_truth=ground_truth,
        reference_contexts=reference_contexts,
    )


def load_ragas_records(path: str | Path) -> list[RagasRecord]:
    frame = pd.read_csv(path)
    return [
        RagasRecord.from_mapping(row)
        for row in frame.to_dict(orient="records")
    ]


def save_ragas_records(records: Iterable[RagasRecord], path: str | Path) -> None:
    frame = pd.DataFrame([record.to_csv_record() for record in records])
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False)


def normalize_eval_csv(input_path: str | Path, output_path: str | Path) -> pd.DataFrame:
    records = load_ragas_records(input_path)
    frame = pd.DataFrame([record.to_csv_record() for record in records])
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(output_path, index=False)
    return frame


def build_context_dataset(
    input_path: str | Path,
    output_path: str | Path,
    rag_types: Sequence[RagType] = ("pgvector", "graph", "db_search", "web"),
    top_k: int = 5,
    **retrieve_kwargs: Any,
) -> pd.DataFrame:
    base_records = load_ragas_records(input_path)
    output_records: list[RagasRecord] = []

    for base_record in base_records:
        for rag_type in rag_types:
            context_result = collect_rag_contexts(
                rag_type=rag_type,
                question=base_record.question,
                top_k=top_k,
                **retrieve_kwargs,
            )
            output_records.append(
                context_result.to_record(
                    answer=base_record.answer,
                    ground_truth=base_record.ground_truth,
                    reference_contexts=base_record.reference_contexts,
                )
            )

    save_ragas_records(output_records, output_path)
    return pd.DataFrame([record.to_csv_record() for record in output_records])


def fill_answers_csv(
    input_path: str | Path,
    output_path: str | Path,
    mode: AnswerMode = "extractive",
    overwrite: bool = False,
    llm: Any | None = None,
    max_context_chars: int = 6000,
) -> pd.DataFrame:
    records = load_ragas_records(input_path)
    filled_records = [
        fill_answer_record(
            record,
            mode=mode,
            overwrite=overwrite,
            llm=llm,
            max_context_chars=max_context_chars,
        )
        for record in records
    ]
    save_ragas_records(filled_records, output_path)
    return pd.DataFrame([record.to_csv_record() for record in filled_records])


def fill_answer_record(
    record: RagasRecord,
    mode: AnswerMode = "extractive",
    overwrite: bool = False,
    llm: Any | None = None,
    max_context_chars: int = 6000,
) -> RagasRecord:
    if record.answer and not overwrite:
        return record

    if mode == "llm":
        resolved_llm = llm or load_default_answer_llm()
        answer = generate_llm_answer(record.question, record.contexts, resolved_llm, max_context_chars)
        metadata = {**record.metadata, "answer_mode": "llm"}
    else:
        answer = generate_extractive_answer(record.question, record.contexts)
        metadata = {**record.metadata, "answer_mode": "extractive"}

    return RagasRecord(
        question=record.question,
        contexts=record.contexts,
        answer=answer,
        ground_truth=record.ground_truth,
        reference_contexts=record.reference_contexts,
        rag_type=record.rag_type,
        sources=record.sources,
        metadata=metadata,
    )


def generate_llm_answer(
    question: str,
    contexts: Sequence[str],
    llm: Any,
    max_context_chars: int = 6000,
) -> str:
    context_text = format_numbered_contexts(contexts, max_context_chars=max_context_chars)
    prompt = (
        "다음 context만 근거로 한국어 답변을 작성하세요.\n"
        "context에 없는 내용은 추측하지 말고 정보가 부족하다고 말하세요.\n"
        "답변 끝에는 사용한 근거 번호를 [1], [2] 형식으로 표시하세요.\n\n"
        f"질문:\n{question}\n\n"
        f"context:\n{context_text}"
    )
    response = llm.invoke(prompt)
    return str(getattr(response, "content", response)).strip()


def generate_extractive_answer(question: str, contexts: Sequence[str]) -> str:
    if not contexts:
        return "제공된 문맥만으로는 답변할 근거가 부족합니다."

    terms = _query_terms(question)
    selected_sentences: list[tuple[int, str]] = []
    for context_index, context in enumerate(contexts, start=1):
        for sentence in split_sentences(context):
            if terms and not any(term in sentence.lower() for term in terms):
                continue
            selected_sentences.append((context_index, sentence))
            if len(selected_sentences) >= 3:
                break
        if len(selected_sentences) >= 3:
            break

    if not selected_sentences:
        first_context = contexts[0].strip()
        summary = first_context[:500].strip()
        return f"{summary} [1]"

    body = " ".join(sentence for _index, sentence in selected_sentences)
    citations = " ".join(f"[{index}]" for index in sorted({index for index, _ in selected_sentences}))
    return f"{body} {citations}".strip()


def split_sentences(text: str) -> list[str]:
    normalized = " ".join(str(text).split())
    if not normalized:
        return []
    sentences = []
    for part in normalized.replace("?", ".").replace("!", ".").split("."):
        sentence = part.strip()
        if len(sentence) >= 20:
            sentences.append(sentence)
    return sentences or [normalized[:500].strip()]


def format_numbered_contexts(contexts: Sequence[str], max_context_chars: int = 6000) -> str:
    blocks = []
    remaining_chars = max_context_chars
    for index, context in enumerate(contexts, start=1):
        content = str(context).strip()
        if not content or remaining_chars <= 0:
            continue
        content = content[:remaining_chars]
        blocks.append(f"[{index}] {content}")
        remaining_chars -= len(content)
    return "\n\n".join(blocks)


def generate_testset_from_csv(
    source_path: str | Path,
    output_path: str | Path,
    content_column: str = "content",
    testset_size: int = 20,
    llm: Any | None = None,
    embeddings: Any | None = None,
) -> pd.DataFrame:
    frame = pd.read_csv(source_path)
    if content_column not in frame.columns:
        raise ValueError(f"source CSV must contain content column: {content_column}")

    documents = []
    try:
        from langchain_core.documents import Document
    except ImportError as exc:
        raise RuntimeError("langchain-core is required for RAGAS testset generation.") from exc

    for row in frame.to_dict(orient="records"):
        content = str(row.get(content_column) or "").strip()
        if not content:
            continue
        metadata = {
            key: value
            for key, value in row.items()
            if key != content_column and not _is_empty_scalar(value)
        }
        documents.append(Document(page_content=content, metadata=metadata))

    if not documents:
        raise ValueError("No non-empty documents found for testset generation.")

    generator = create_testset_generator(llm=llm, embeddings=embeddings)
    testset = generator.generate_with_langchain_docs(
        documents=documents,
        testset_size=testset_size,
    )
    if hasattr(testset, "to_pandas"):
        testset_frame = testset.to_pandas()
    else:
        testset_frame = pd.DataFrame(testset)

    records = [RagasRecord.from_mapping(row) for row in testset_frame.to_dict(orient="records")]
    save_ragas_records(records, output_path)
    return pd.DataFrame([record.to_csv_record() for record in records])


def create_testset_generator(llm: Any | None = None, embeddings: Any | None = None) -> Any:
    try:
        from ragas.testset import TestsetGenerator
    except ImportError as exc:
        raise RuntimeError("RAGAS testset generation requires ragas.testset.") from exc

    ragas_llm, ragas_embeddings = wrap_ragas_models(llm=llm, embeddings=embeddings)
    return TestsetGenerator(llm=ragas_llm, embedding_model=ragas_embeddings)


def wrap_ragas_models(llm: Any | None = None, embeddings: Any | None = None) -> tuple[Any, Any]:
    try:
        from ragas.embeddings import LangchainEmbeddingsWrapper
        from ragas.llms import LangchainLLMWrapper
    except ImportError as exc:
        raise RuntimeError("RAGAS wrappers are unavailable in the installed ragas package.") from exc

    resolved_llm = llm or load_default_answer_llm()
    resolved_embeddings = embeddings or load_default_embeddings()
    return LangchainLLMWrapper(resolved_llm), LangchainEmbeddingsWrapper(resolved_embeddings)


def load_default_answer_llm() -> Any:
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:
        pass

    from common.get_model import get_llm

    return get_llm()


def load_default_embeddings() -> Any:
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:
        pass

    from common.get_model import get_embedding_model

    return get_embedding_model()


def run_full_pipeline(
    input_path: str | Path,
    output_dir: str | Path,
    rag_types: Sequence[RagType] = ("pgvector", "graph", "db_search", "web"),
    top_k: int = 5,
    answer_mode: AnswerMode = "extractive",
    run_ragas: bool = False,
    metrics: Iterable[str] = DEFAULT_METRICS,
    use_common_ragas_models: bool = False,
    **retrieve_kwargs: Any,
) -> dict[str, Path]:
    output_root = Path(output_dir)
    output_root.mkdir(parents=True, exist_ok=True)

    contexts_path = output_root / "evaluation_ragas_contexts.csv"
    answered_path = output_root / "evaluation_ragas_with_answer.csv"
    answer_scores_path = output_root / "answer_eval_scores.csv"
    answer_summary_path = output_root / "answer_eval_summary.csv"
    ragas_scores_path = output_root / "ragas_scores.csv"
    ragas_summary_path = output_root / "ragas_summary.csv"

    build_context_dataset(
        input_path=input_path,
        output_path=contexts_path,
        rag_types=rag_types,
        top_k=top_k,
        **retrieve_kwargs,
    )
    fill_answers_csv(
        input_path=contexts_path,
        output_path=answered_path,
        mode=answer_mode,
        overwrite=True,
    )

    from src.evaluation.answer_eval import evaluate_answer_csv, summarize_answer_eval

    answer_scores = evaluate_answer_csv(answered_path, answer_scores_path)
    summarize_answer_eval(answer_scores).to_csv(answer_summary_path, index=False)

    outputs = {
        "contexts": contexts_path,
        "answered": answered_path,
        "answer_scores": answer_scores_path,
        "answer_summary": answer_summary_path,
    }

    if run_ragas:
        ragas_llm = None
        ragas_embeddings = None
        if use_common_ragas_models:
            ragas_llm, ragas_embeddings = wrap_ragas_models()
        ragas_scores = evaluate_rag_csv(
            answered_path,
            output_path=ragas_scores_path,
            metrics=metrics,
            llm=ragas_llm,
            embeddings=ragas_embeddings,
        )
        summarize_by_rag_type(ragas_scores).to_csv(ragas_summary_path, index=False)
        outputs["ragas_scores"] = ragas_scores_path
        outputs["ragas_summary"] = ragas_summary_path

    return outputs


def evaluate_rag_records(
    records: Iterable[RagasRecord | dict[str, Any]],
    metrics: Iterable[str] = DEFAULT_METRICS,
    llm: Any | None = None,
    embeddings: Any | None = None,
) -> pd.DataFrame:
    normalized = [
        record if isinstance(record, RagasRecord) else RagasRecord.from_mapping(record)
        for record in records
    ]
    _validate_records_for_ragas(normalized)
    ragas_evaluate, metric_objects = _load_ragas(metrics)
    dataset = _to_dataset(record.to_ragas_record() for record in normalized)
    result = ragas_evaluate(
        dataset,
        metrics=metric_objects,
        llm=llm,
        embeddings=embeddings,
    )

    if hasattr(result, "to_pandas"):
        frame = result.to_pandas()
    elif hasattr(result, "scores"):
        frame = pd.DataFrame(result.scores)
    else:
        frame = pd.DataFrame(result)

    if "rag_type" in frame.columns:
        frame["rag_type"] = [record.rag_type or "" for record in normalized]
    else:
        frame.insert(0, "rag_type", [record.rag_type or "" for record in normalized])

    if "question" in frame.columns:
        frame["question"] = [record.question for record in normalized]
    else:
        frame.insert(1, "question", [record.question for record in normalized])
    return frame


def evaluate_rag_csv(
    input_path: str | Path,
    output_path: str | Path | None = None,
    metrics: Iterable[str] = DEFAULT_METRICS,
    llm: Any | None = None,
    embeddings: Any | None = None,
) -> pd.DataFrame:
    frame = evaluate_rag_records(
        load_ragas_records(input_path),
        metrics=metrics,
        llm=llm,
        embeddings=embeddings,
    )
    if output_path:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        frame.to_csv(output_path, index=False)
    return frame


def validate_ragas_csv(
    input_path: str | Path,
    metrics: Iterable[str] = DEFAULT_METRICS,
) -> dict[str, Any]:
    records = load_ragas_records(input_path)
    _validate_records_for_ragas(records)
    _, metric_objects = _load_ragas(metrics)
    dataset = _to_dataset(record.to_ragas_record() for record in records)

    required_columns: set[str] = set()
    for metric in metric_objects:
        for columns in getattr(metric, "_required_columns", {}).values():
            required_columns.update(columns)

    missing_columns = sorted(required_columns.difference(dataset.column_names))
    if missing_columns:
        raise ValueError(
            "RAGAS dataset missing required columns: " + ", ".join(missing_columns)
        )

    return {
        "rows": len(records),
        "metrics": list(metrics),
        "dataset_columns": list(dataset.column_names),
        "required_columns": sorted(required_columns),
    }


def summarize_by_rag_type(frame: pd.DataFrame) -> pd.DataFrame:
    if "rag_type" not in frame.columns:
        raise ValueError("score frame must contain a rag_type column.")
    metric_columns = [
        column
        for column in frame.columns
        if column not in {"rag_type", "question"} and pd.api.types.is_numeric_dtype(frame[column])
    ]
    if not metric_columns:
        return pd.DataFrame(columns=["rag_type"])
    return frame.groupby("rag_type", dropna=False)[metric_columns].mean().reset_index()


def _collect_pgvector_docs(question: str, top_k: int, **kwargs: Any) -> list[dict[str, Any]]:
    auto_create_embedding = kwargs.pop("auto_create_embedding", True)
    mode = kwargs.pop("mode", "hybrid")
    if auto_create_embedding and kwargs.get("query_embedding") is None and mode in {"auto", "vector", "hybrid"}:
        from src.rag.db_search import run_db_search_rag

        response = run_db_search_rag(
            query=question,
            top_k=top_k,
            reliability_filter=kwargs.pop("reliability_filter", "ALL"),
            mode=mode,
            dsn=kwargs.pop("dsn", None),
            embedding_model=kwargs.pop("embedding_model", "google/embeddinggemma-300m"),
            auto_create_embedding=True,
            include_graph=False,
        )
        return response.retrieved_docs

    from src.rag.retriever import search_db_state

    return search_db_state(
        query=question,
        query_embedding=kwargs.pop("query_embedding", None),
        top_k=top_k,
        reliability_filter=kwargs.pop("reliability_filter", "ALL"),
        dsn=kwargs.pop("dsn", None),
        mode=mode,
        embedding_model=kwargs.pop("embedding_model", "google/embeddinggemma-300m"),
    )


def _collect_graph_docs(question: str, top_k: int, **kwargs: Any) -> list[dict[str, Any]]:
    from src.rag.retriever import search_graph

    return [
        result.to_retrieved_document()
        for result in search_graph(
            query=question,
            top_k=top_k,
            reliability_filter=kwargs.pop("reliability_filter", "ALL"),
            retriever=kwargs.pop("retriever", None),
        )
    ]


def _collect_db_search_docs(question: str, top_k: int, **kwargs: Any) -> list[dict[str, Any]]:
    from src.rag.db_search import run_db_search_rag

    response = run_db_search_rag(
        query=question,
        top_k=top_k,
        reliability_filter=kwargs.pop("reliability_filter", "ALL"),
        mode=kwargs.pop("mode", "hybrid"),
        dsn=kwargs.pop("dsn", None),
        embedding_model=kwargs.pop("embedding_model", "google/embeddinggemma-300m"),
        auto_create_embedding=kwargs.pop("auto_create_embedding", True),
        include_graph=kwargs.pop("include_graph", True),
        graph_retriever=kwargs.pop("graph_retriever", None),
        graph_top_k=kwargs.pop("graph_top_k", None),
    )
    return response.retrieved_docs


def _collect_web_docs(question: str, top_k: int, **kwargs: Any) -> list[dict[str, Any]]:
    from src.rag.web_search import WebSearchRAG

    retriever = kwargs.pop("retriever", None) or WebSearchRAG()
    result = retriever.retrieve(
        question=question,
        character_context=kwargs.pop("character_context", None),
        official_only=kwargs.pop("official_only", True),
        max_results=kwargs.pop("max_results", top_k),
        max_contexts=kwargs.pop("max_contexts", top_k),
    )
    return web_result_to_retrieved_documents(result)


def web_result_to_retrieved_documents(result: dict[str, Any]) -> list[dict[str, Any]]:
    docs = []
    search_provider = result.get("search_provider")
    search_query = result.get("search_query")
    for context in result.get("contexts", []):
        content = str(context.get("content") or "").strip()
        source_url = context.get("url")
        if not content:
            continue
        docs.append(
            {
                "page_content": content,
                "metadata": {
                    "title": context.get("title"),
                    "source_url": source_url,
                    "chunk_index": context.get("chunk_index"),
                    "reliability": context.get("reliability"),
                    "freshness": context.get("freshness"),
                    "published_at": context.get("published_at"),
                    "retrieval_method": "web",
                    "search_provider": search_provider,
                    "search_query": search_query,
                },
                "score": float(context.get("score") or 0),
                "source": source_url or context.get("title") or "web",
            }
        )
    return docs


def _validate_records_for_ragas(records: Sequence[RagasRecord]) -> None:
    missing = []
    for index, record in enumerate(records):
        if not record.question:
            missing.append(f"row {index}: question")
        if not record.answer:
            missing.append(f"row {index}: answer")
        if not record.contexts:
            missing.append(f"row {index}: contexts")
    if missing:
        raise ValueError("RAGAS records missing required values: " + ", ".join(missing))


def _to_dataset(records: Iterable[dict[str, Any]]) -> Any:
    try:
        from datasets import Dataset
    except ImportError as exc:
        raise RuntimeError("RAGAS evaluation requires the datasets package.") from exc
    return Dataset.from_list(list(records))


def _load_ragas(metric_names: Iterable[str]) -> tuple[Any, list[Any]]:
    try:
        from ragas import evaluate
        from ragas import metrics as ragas_metrics
    except ImportError as exc:
        raise RuntimeError("RAGAS is not installed. Install project requirements.") from exc

    metric_objects = []
    for name in metric_names:
        try:
            with warnings.catch_warnings():
                warnings.filterwarnings("ignore", category=DeprecationWarning)
                metric_objects.append(getattr(ragas_metrics, name))
        except AttributeError as exc:
            raise ValueError(f"Unsupported RAGAS metric: {name}") from exc
    return evaluate, metric_objects


def _query_terms(query: str) -> list[str]:
    terms = []
    for raw_term in str(query).lower().replace(",", " ").replace("?", " ").split():
        term = raw_term.strip()
        if len(term) >= 2 and term not in terms:
            terms.append(term)
        if len(terms) >= 8:
            break
    return terms


def _is_empty_scalar(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, float) and pd.isna(value):
        return True
    if isinstance(value, str) and not value.strip():
        return True
    return False


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def _parse_rag_types(values: Sequence[str]) -> list[RagType]:
    allowed = {"pgvector", "graph", "db_search", "web"}
    rag_types = []
    for value in values:
        if value not in allowed:
            raise ValueError(f"Unsupported rag_type: {value}")
        rag_types.append(value)  # type: ignore[arg-type]
    return rag_types


def main() -> None:
    parser = argparse.ArgumentParser(description="Run or prepare RAGAS evaluation data.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    normalize_parser = subparsers.add_parser("normalize")
    normalize_parser.add_argument("input_csv")
    normalize_parser.add_argument("output_csv")

    testset_parser = subparsers.add_parser("generate-testset")
    testset_parser.add_argument("source_csv")
    testset_parser.add_argument("output_csv")
    testset_parser.add_argument("--content-column", default="content")
    testset_parser.add_argument("--testset-size", type=int, default=20)

    contexts_parser = subparsers.add_parser("make-contexts")
    contexts_parser.add_argument("input_csv")
    contexts_parser.add_argument("output_csv")
    contexts_parser.add_argument(
        "--rag-types",
        nargs="+",
        default=["pgvector", "graph", "db_search", "web"],
    )
    contexts_parser.add_argument("--top-k", type=int, default=5)
    contexts_parser.add_argument("--mode", default="hybrid")
    contexts_parser.add_argument("--reliability-filter", default="ALL")

    answer_parser = subparsers.add_parser("answer")
    answer_parser.add_argument("input_csv")
    answer_parser.add_argument("output_csv")
    answer_parser.add_argument("--mode", choices=["extractive", "llm"], default="extractive")
    answer_parser.add_argument("--overwrite", action="store_true")
    answer_parser.add_argument("--max-context-chars", type=int, default=6000)

    evaluate_parser = subparsers.add_parser("evaluate")
    evaluate_parser.add_argument("input_csv")
    evaluate_parser.add_argument("--output-csv")
    evaluate_parser.add_argument("--metrics", nargs="*", default=list(DEFAULT_METRICS))
    evaluate_parser.add_argument("--use-common-models", action="store_true")

    validate_parser = subparsers.add_parser("validate")
    validate_parser.add_argument("input_csv")
    validate_parser.add_argument("--metrics", nargs="*", default=list(DEFAULT_METRICS))

    summary_parser = subparsers.add_parser("summary")
    summary_parser.add_argument("score_csv")
    summary_parser.add_argument("--output-csv")

    full_parser = subparsers.add_parser("full")
    full_parser.add_argument("input_csv")
    full_parser.add_argument("output_dir")
    full_parser.add_argument(
        "--rag-types",
        nargs="+",
        default=["pgvector", "graph", "db_search", "web"],
    )
    full_parser.add_argument("--top-k", type=int, default=5)
    full_parser.add_argument("--answer-mode", choices=["extractive", "llm"], default="extractive")
    full_parser.add_argument("--run-ragas", action="store_true")
    full_parser.add_argument("--use-common-ragas-models", action="store_true")
    full_parser.add_argument("--metrics", nargs="*", default=list(DEFAULT_METRICS))
    full_parser.add_argument("--mode", default="hybrid")
    full_parser.add_argument("--reliability-filter", default="ALL")

    args = parser.parse_args()
    if args.command == "normalize":
        normalize_eval_csv(args.input_csv, args.output_csv)
    elif args.command == "generate-testset":
        frame = generate_testset_from_csv(
            source_path=args.source_csv,
            output_path=args.output_csv,
            content_column=args.content_column,
            testset_size=args.testset_size,
        )
        print(frame.to_string(index=False))
    elif args.command == "make-contexts":
        frame = build_context_dataset(
            input_path=args.input_csv,
            output_path=args.output_csv,
            rag_types=_parse_rag_types(args.rag_types),
            top_k=args.top_k,
            mode=args.mode,
            reliability_filter=args.reliability_filter,
        )
        print(frame.to_string(index=False))
    elif args.command == "answer":
        llm = load_default_answer_llm() if args.mode == "llm" else None
        frame = fill_answers_csv(
            input_path=args.input_csv,
            output_path=args.output_csv,
            mode=args.mode,
            overwrite=args.overwrite,
            llm=llm,
            max_context_chars=args.max_context_chars,
        )
        print(frame.to_string(index=False))
    elif args.command == "evaluate":
        llm = None
        embeddings = None
        if args.use_common_models:
            llm, embeddings = wrap_ragas_models()
        frame = evaluate_rag_csv(
            args.input_csv,
            args.output_csv,
            metrics=args.metrics,
            llm=llm,
            embeddings=embeddings,
        )
        print(frame.to_string(index=False))
    elif args.command == "validate":
        result = validate_ragas_csv(args.input_csv, metrics=args.metrics)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif args.command == "summary":
        frame = summarize_by_rag_type(pd.read_csv(args.score_csv))
        if args.output_csv:
            Path(args.output_csv).parent.mkdir(parents=True, exist_ok=True)
            frame.to_csv(args.output_csv, index=False)
        print(frame.to_string(index=False))
    elif args.command == "full":
        outputs = run_full_pipeline(
            input_path=args.input_csv,
            output_dir=args.output_dir,
            rag_types=_parse_rag_types(args.rag_types),
            top_k=args.top_k,
            answer_mode=args.answer_mode,
            run_ragas=args.run_ragas,
            metrics=args.metrics,
            use_common_ragas_models=args.use_common_ragas_models,
            mode=args.mode,
            reliability_filter=args.reliability_filter,
        )
        print(json.dumps({key: str(value) for key, value in outputs.items()}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
