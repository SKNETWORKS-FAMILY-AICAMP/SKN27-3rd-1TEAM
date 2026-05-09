from __future__ import annotations

import os
from dataclasses import dataclass, replace
from typing import Any, Iterable, Literal, Sequence

import psycopg2
from dotenv import load_dotenv
from psycopg2.extras import RealDictCursor
from pgvector.psycopg2 import register_vector

from common.state import AgentState, RetrievedDocument
from common.validator import validate_agent_inputs, validate_agent_outputs


ReliabilityFilter = Literal["ALL", "HIGH_ONLY"]
SearchMode = Literal["auto", "text", "vector", "hybrid"]
DEFAULT_EMBEDDING_MODEL = "google/embeddinggemma-300m"
DEFAULT_VECTOR_WEIGHT = 0.65
DEFAULT_TEXT_WEIGHT = 0.35
DEFAULT_CANDIDATE_MULTIPLIER = 3


@dataclass(frozen=True)
class DBSearchResult:
    chunk_id: str
    document_id: str
    title: str
    content: str
    source_url: str | None
    reliability: str | None
    score: float
    retrieval_method: str = "unknown"

    def to_source(self) -> dict[str, str | float | None]:
        return {
            "title": self.title,
            "url": self.source_url,
            "reliability": self.reliability,
            "score": self.score,
            "retrieval_method": self.retrieval_method,
        }

    def to_retrieved_document(self) -> RetrievedDocument:
        return {
            "page_content": self.content,
            "metadata": {
                "chunk_id": self.chunk_id,
                "document_id": self.document_id,
                "title": self.title,
                "source_url": self.source_url,
                "reliability": self.reliability,
                "retrieval_method": self.retrieval_method,
            },
            "score": self.score,
            "source": self.source_url or self.document_id,
        }


@dataclass(frozen=True)
class DBSearchRAGResponse:
    query: str
    context: str
    retrieved_docs: list[RetrievedDocument]
    sources: list[dict[str, str | float | None]]


def _database_url() -> str:
    load_dotenv()
    return os.getenv("POSTGRES_URI") or os.getenv("DATABASE_URL") or (
        "postgresql://"
        f"{os.getenv('POSTGRES_USER', 'admin')}:"
        f"{os.getenv('POSTGRES_PASSWORD', 'admin123')}@"
        f"{os.getenv('POSTGRES_HOST', 'localhost')}:"
        f"{os.getenv('POSTGRES_PORT', '5432')}/"
        f"{os.getenv('POSTGRES_DB', 'mapledb')}"
    )


def get_connection(dsn: str | None = None):
    conn = psycopg2.connect(dsn or _database_url(), cursor_factory=RealDictCursor)
    register_vector(conn)
    return conn


def _trust_clause(reliability_filter: ReliabilityFilter) -> tuple[str, list[object]]:
    if reliability_filter == "HIGH_ONLY":
        return "AND d.trust_level = ANY(%s)", [["S", "A"]]
    return "", []


class PGVectorDBRetriever:
    def __init__(
        self,
        dsn: str | None = None,
        embedding_model: str | None = DEFAULT_EMBEDDING_MODEL,
    ) -> None:
        self.dsn = dsn
        self.embedding_model = embedding_model

    def search(
        self,
        query: str,
        query_embedding: Sequence[float] | None = None,
        top_k: int = 5,
        reliability_filter: ReliabilityFilter = "ALL",
        mode: SearchMode = "auto",
    ) -> list[DBSearchResult]:
        if mode == "text":
            return self.text_search(query, top_k, reliability_filter)
        if mode == "vector":
            if query_embedding is None:
                raise ValueError("query_embedding is required for vector search.")
            return self.vector_search(query_embedding, top_k, reliability_filter)
        if mode == "hybrid":
            return self.hybrid_search(query, query_embedding, top_k, reliability_filter)
        if query_embedding is not None:
            return self.hybrid_search(query, query_embedding, top_k, reliability_filter)
        return self.text_search(query, top_k, reliability_filter)

    def hybrid_search(
        self,
        query: str,
        query_embedding: Sequence[float] | None = None,
        top_k: int = 5,
        reliability_filter: ReliabilityFilter = "ALL",
        vector_weight: float = DEFAULT_VECTOR_WEIGHT,
        text_weight: float = DEFAULT_TEXT_WEIGHT,
    ) -> list[DBSearchResult]:
        vector_results: list[DBSearchResult] = []
        candidate_k = max(top_k * DEFAULT_CANDIDATE_MULTIPLIER, top_k)
        if query_embedding is not None:
            vector_results = self.vector_search(query_embedding, candidate_k, reliability_filter)

        text_results = self.text_search(query, candidate_k, reliability_filter)
        return _merge_hybrid_results(
            vector_results=vector_results,
            text_results=text_results,
            top_k=top_k,
            vector_weight=vector_weight,
            text_weight=text_weight,
        )

    def vector_search(
        self,
        query_embedding: Sequence[float],
        top_k: int = 5,
        reliability_filter: ReliabilityFilter = "ALL",
    ) -> list[DBSearchResult]:
        trust_sql, trust_params = _trust_clause(reliability_filter)
        model_sql, model_params = _embedding_model_clause(self.embedding_model)
        sql = f"""
            SELECT
                dc.chunk_id,
                d.doc_id AS document_id,
                d.title,
                dc.content,
                d.source_url,
                d.trust_level AS reliability,
                1 - (de.embedding <=> %s::vector) AS score
            FROM document_embeddings de
            JOIN document_chunks dc ON dc.id = de.chunk_id
            JOIN documents d ON d.id = dc.document_id
            WHERE d.rag_ready = true
              {trust_sql}
              {model_sql}
            ORDER BY de.embedding <=> %s::vector
            LIMIT %s
        """
        params = [
            list(query_embedding),
            *trust_params,
            *model_params,
            list(query_embedding),
            top_k,
        ]
        return self._fetch(sql, params, retrieval_method="vector")

    def text_search(
        self,
        query: str,
        top_k: int = 5,
        reliability_filter: ReliabilityFilter = "ALL",
    ) -> list[DBSearchResult]:
        trust_sql, trust_params = _trust_clause(reliability_filter)
        token_patterns = [f"%{term}%" for term in _search_terms(query)]
        token_score_sql, token_score_params = _token_score_sql(token_patterns)
        sql = f"""
            SELECT
                dc.chunk_id,
                d.doc_id AS document_id,
                d.title,
                dc.content,
                d.source_url,
                d.trust_level AS reliability,
                (
                    ts_rank_cd(
                        to_tsvector('simple', dc.content),
                        plainto_tsquery('simple', %s)
                    )
                    + CASE
                        WHEN dc.content ILIKE %s OR d.title ILIKE %s THEN 0.5
                        ELSE 0
                      END
                    {token_score_sql}
                ) AS score
            FROM document_chunks dc
            JOIN documents d ON d.id = dc.document_id
            WHERE d.rag_ready = true
              {trust_sql}
              AND (
                  to_tsvector('simple', dc.content) @@ plainto_tsquery('simple', %s)
                  OR dc.content ILIKE %s
                  OR d.title ILIKE %s
                  OR dc.content ILIKE ANY(%s)
                  OR d.title ILIKE ANY(%s)
              )
            ORDER BY score DESC,
                CASE d.trust_level
                    WHEN 'S' THEN 1
                    WHEN 'A' THEN 2
                    WHEN 'B' THEN 3
                    WHEN 'C' THEN 4
                    ELSE 5
                END,
                dc.chunk_index ASC
            LIMIT %s
        """
        like_query = f"%{query}%"
        params = [
            query,
            like_query,
            like_query,
            *token_score_params,
            *trust_params,
            query,
            like_query,
            like_query,
            token_patterns,
            token_patterns,
            top_k,
        ]
        return self._fetch(sql, params, retrieval_method="keyword")

    def build_context(self, results: Iterable[DBSearchResult]) -> str:
        blocks = []
        for index, result in enumerate(results, start=1):
            source = result.source_url or result.document_id
            blocks.append(
                f"[{index}] {result.title}\n"
                f"source: {source}\n"
                f"reliability: {result.reliability or 'unknown'}\n"
                f"retrieval_method: {result.retrieval_method}\n"
                f"score: {result.score:.4f}\n"
                f"{result.content}"
            )
        return "\n\n".join(blocks)

    def _fetch(
        self,
        sql: str,
        params: Sequence[object],
        retrieval_method: str,
    ) -> list[DBSearchResult]:
        with get_connection(self.dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                rows = cur.fetchall()

        return [
            DBSearchResult(
                chunk_id=row["chunk_id"],
                document_id=row["document_id"],
                title=row["title"],
                content=row["content"],
                source_url=row["source_url"],
                reliability=row["reliability"],
                score=float(row["score"] or 0),
                retrieval_method=retrieval_method,
            )
            for row in rows
        ]


class DBSearchRAG:
    """DB Search RAG adapter that only fills research state outputs."""

    def __init__(
        self,
        retriever: PGVectorDBRetriever | None = None,
        embedding_fn: Any | None = None,
        dsn: str | None = None,
        embedding_model: str | None = DEFAULT_EMBEDDING_MODEL,
        auto_create_embedding: bool = False,
    ) -> None:
        self.retriever = retriever or PGVectorDBRetriever(
            dsn=dsn,
            embedding_model=embedding_model,
        )
        self.embedding_fn = embedding_fn
        self.embedding_model = embedding_model or DEFAULT_EMBEDDING_MODEL
        self.auto_create_embedding = auto_create_embedding

    def retrieve(
        self,
        query: str,
        top_k: int = 5,
        reliability_filter: ReliabilityFilter = "ALL",
        mode: SearchMode = "hybrid",
    ) -> list[DBSearchResult]:
        query_embedding = (
            self._embed_query(query)
            if mode in {"auto", "vector", "hybrid"}
            else None
        )
        return self.retriever.search(
            query=query,
            query_embedding=query_embedding,
            top_k=top_k,
            reliability_filter=reliability_filter,
            mode=mode,
        )

    def search_context(
        self,
        query: str,
        top_k: int = 5,
        reliability_filter: ReliabilityFilter = "ALL",
        mode: SearchMode = "hybrid",
    ) -> DBSearchRAGResponse:
        results = self.retrieve(
            query=query,
            top_k=top_k,
            reliability_filter=reliability_filter,
            mode=mode,
        )
        return DBSearchRAGResponse(
            query=query,
            context=self.retriever.build_context(results),
            retrieved_docs=[result.to_retrieved_document() for result in results],
            sources=[result.to_source() for result in results],
        )

    def update_state(
        self,
        state: AgentState,
        top_k: int = 5,
        reliability_filter: ReliabilityFilter = "ALL",
        mode: SearchMode = "hybrid",
    ) -> AgentState:
        validate_agent_inputs("research", state)
        response = self.search_context(
            query=state["user_query"],
            top_k=top_k,
            reliability_filter=reliability_filter,
            mode=mode,
        )
        next_state: AgentState = {
            **state,
            "retrieved_docs": response.retrieved_docs,
            "context": response.context,
        }
        validate_agent_outputs("research", next_state)
        return next_state

    def invoke(self, query: str) -> DBSearchRAGResponse:
        return self.search_context(query)

    def _embed_query(self, query: str) -> Sequence[float] | None:
        if self.embedding_fn is None:
            if not self.auto_create_embedding:
                return None
            self.embedding_fn = create_default_embedding_fn(self.embedding_model)
        return self.embedding_fn.embed_query(query)


def search_db(
    query: str,
    query_embedding: Sequence[float] | None = None,
    top_k: int = 5,
    reliability_filter: ReliabilityFilter = "ALL",
    dsn: str | None = None,
    mode: SearchMode = "auto",
    embedding_model: str | None = DEFAULT_EMBEDDING_MODEL,
) -> list[DBSearchResult]:
    return PGVectorDBRetriever(dsn=dsn, embedding_model=embedding_model).search(
        query=query,
        query_embedding=query_embedding,
        top_k=top_k,
        reliability_filter=reliability_filter,
        mode=mode,
    )


def search_db_state(
    query: str,
    query_embedding: Sequence[float] | None = None,
    top_k: int = 5,
    reliability_filter: ReliabilityFilter = "ALL",
    dsn: str | None = None,
    mode: SearchMode = "auto",
    embedding_model: str | None = DEFAULT_EMBEDDING_MODEL,
) -> list[RetrievedDocument]:
    return [
        result.to_retrieved_document()
        for result in search_db(
            query=query,
            query_embedding=query_embedding,
            top_k=top_k,
            reliability_filter=reliability_filter,
            dsn=dsn,
            mode=mode,
            embedding_model=embedding_model,
        )
    ]


def create_default_embedding_fn(model_name: str = DEFAULT_EMBEDDING_MODEL) -> Any:
    from database.postgres.embed_document_chunks import SentenceTransformerEmbeddings

    return SentenceTransformerEmbeddings(model_name)


def run_db_search_rag(
    query: str,
    embedding_fn: Any | None = None,
    top_k: int = 5,
    reliability_filter: ReliabilityFilter = "ALL",
    mode: SearchMode = "hybrid",
    dsn: str | None = None,
    embedding_model: str | None = DEFAULT_EMBEDDING_MODEL,
    auto_create_embedding: bool = True,
) -> DBSearchRAGResponse:
    return DBSearchRAG(
        embedding_fn=embedding_fn,
        dsn=dsn,
        embedding_model=embedding_model,
        auto_create_embedding=auto_create_embedding,
    ).search_context(
        query=query,
        top_k=top_k,
        reliability_filter=reliability_filter,
        mode=mode,
    )


def db_search_rag_node(
    state: AgentState,
    embedding_fn: Any | None = None,
    top_k: int = 5,
    reliability_filter: ReliabilityFilter = "ALL",
    mode: SearchMode = "hybrid",
    dsn: str | None = None,
    embedding_model: str | None = DEFAULT_EMBEDDING_MODEL,
    auto_create_embedding: bool = True,
) -> AgentState:
    return DBSearchRAG(
        embedding_fn=embedding_fn,
        dsn=dsn,
        embedding_model=embedding_model,
        auto_create_embedding=auto_create_embedding,
    ).update_state(
        state=state,
        top_k=top_k,
        reliability_filter=reliability_filter,
        mode=mode,
    )


def _embedding_model_clause(embedding_model: str | None) -> tuple[str, list[object]]:
    if not embedding_model:
        return "", []
    return "AND de.embedding_model = %s", [embedding_model]


def _search_terms(query: str) -> list[str]:
    terms = []
    for raw_term in query.replace(",", " ").replace("?", " ").split():
        term = raw_term.strip()
        if len(term) >= 2 and term not in terms:
            terms.append(term)
        if len(terms) >= 8:
            break
    return terms


def _token_score_sql(token_patterns: Sequence[str]) -> tuple[str, list[object]]:
    if not token_patterns:
        return "", []

    sql_parts = []
    params: list[object] = []
    for _pattern in token_patterns:
        sql_parts.append(
            """
                    + CASE
                        WHEN dc.content ILIKE %s OR d.title ILIKE %s THEN 0.1
                        ELSE 0
                      END
            """
        )
        params.extend([_pattern, _pattern])
    return "".join(sql_parts), params


def _merge_hybrid_results(
    vector_results: Sequence[DBSearchResult],
    text_results: Sequence[DBSearchResult],
    top_k: int,
    vector_weight: float,
    text_weight: float,
) -> list[DBSearchResult]:
    vector_scores = _normalize_scores(vector_results)
    text_scores = _normalize_scores(text_results)
    fused: dict[str, DBSearchResult] = {}
    fused_scores: dict[str, float] = {}
    fused_methods: dict[str, set[str]] = {}

    for result in vector_results:
        score = vector_weight * vector_scores.get(result.chunk_id, 0.0)
        _add_fused_result(result, score, fused, fused_scores, fused_methods)

    for result in text_results:
        score = text_weight * text_scores.get(result.chunk_id, 0.0)
        _add_fused_result(result, score, fused, fused_scores, fused_methods)

    reranked = sorted(
        fused.values(),
        key=lambda result: (
            fused_scores[result.chunk_id],
            _trust_priority(result.reliability),
            result.title,
        ),
        reverse=True,
    )

    return [
        replace(
            result,
            score=round(fused_scores[result.chunk_id], 6),
            retrieval_method="+".join(sorted(fused_methods[result.chunk_id])),
        )
        for result in reranked[:top_k]
    ]


def _add_fused_result(
    result: DBSearchResult,
    weighted_score: float,
    fused: dict[str, DBSearchResult],
    fused_scores: dict[str, float],
    fused_methods: dict[str, set[str]],
) -> None:
    if result.chunk_id not in fused:
        fused[result.chunk_id] = result
        fused_scores[result.chunk_id] = 0.0
        fused_methods[result.chunk_id] = set()
    fused_scores[result.chunk_id] += weighted_score
    fused_methods[result.chunk_id].add(result.retrieval_method)


def _normalize_scores(results: Sequence[DBSearchResult]) -> dict[str, float]:
    if not results:
        return {}

    scores = [result.score for result in results]
    min_score = min(scores)
    max_score = max(scores)
    if max_score == min_score:
        return {result.chunk_id: 1.0 for result in results}

    return {
        result.chunk_id: (result.score - min_score) / (max_score - min_score)
        for result in results
    }


def _trust_priority(reliability: str | None) -> int:
    return {
        "S": 4,
        "A": 3,
        "B": 2,
        "C": 1,
    }.get(reliability or "", 0)
