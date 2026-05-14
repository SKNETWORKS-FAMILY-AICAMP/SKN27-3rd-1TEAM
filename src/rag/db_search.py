from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

from common.state import AgentState, RetrievedDocument
from common.validator import validate_agent_inputs, validate_agent_outputs

from src.rag.retriever import (
    DBSearchResult,
    DEFAULT_EMBEDDING_MODEL,
    GraphReliabilityFilter,
    GraphSearchResult,
    Neo4jGraphRetriever,
    PGVectorDBRetriever,
    ReliabilityFilter,
    SearchMode,
    graph_result_to_db_result,
    merge_db_and_graph_results,
    search_db,
    search_db_state,
    search_graph,
)


@dataclass(frozen=True)
class DBSearchRAGResponse:
    query: str
    context: str
    retrieved_docs: list[RetrievedDocument]
    sources: list[dict[str, str | float | None]]


class DBSearchRAG:
    """DB Search RAG adapter that only fills research state outputs."""

    def __init__(
        self,
        retriever: PGVectorDBRetriever | None = None,
        embedding_fn: Any | None = None,
        dsn: str | None = None,
        embedding_model: str | None = DEFAULT_EMBEDDING_MODEL,
        auto_create_embedding: bool = False,
        graph_retriever: Any | None = None,
        include_graph: bool = False,
    ) -> None:
        self.retriever = retriever or PGVectorDBRetriever(
            dsn=dsn,
            embedding_model=embedding_model,
        )
        self.embedding_fn = embedding_fn
        self.embedding_model = embedding_model or DEFAULT_EMBEDDING_MODEL
        self.auto_create_embedding = auto_create_embedding
        self.graph_retriever = graph_retriever
        self.include_graph = include_graph

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
        graph_top_k: int | None = None,
    ) -> DBSearchRAGResponse:
        results = self.retrieve(
            query=query,
            top_k=top_k,
            reliability_filter=reliability_filter,
            mode=mode,
        )
        if self.include_graph:
            graph_results = self.retrieve_graph(
                query=query,
                top_k=graph_top_k or top_k,
                reliability_filter=reliability_filter,
            )
            results = merge_db_and_graph_results(results, graph_results, top_k)

        return DBSearchRAGResponse(
            query=query,
            context=self.retriever.build_context(results),
            retrieved_docs=[result.to_retrieved_document() for result in results],
            sources=[result.to_source() for result in results],
        )

    def retrieve_graph(
        self,
        query: str,
        top_k: int = 5,
        reliability_filter: ReliabilityFilter = "ALL",
    ) -> list[DBSearchResult]:
        graph_retriever = self.graph_retriever or Neo4jGraphRetriever()
        return [
            graph_result_to_db_result(result)
            for result in graph_retriever.search(
                query=query,
                top_k=top_k,
                reliability_filter=reliability_filter,
            )
        ]

    def update_state(
        self,
        state: AgentState,
        top_k: int = 5,
        reliability_filter: ReliabilityFilter = "ALL",
        mode: SearchMode = "hybrid",
        graph_top_k: int | None = None,
    ) -> AgentState:
        validate_agent_inputs("research", state)
        query = str(state.get("contextualized_query") or state["user_query"])
        response = self.search_context(
            query=query,
            top_k=top_k,
            reliability_filter=reliability_filter,
            mode=mode,
            graph_top_k=graph_top_k,
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
    include_graph: bool = False,
    graph_retriever: Any | None = None,
    graph_top_k: int | None = None,
) -> DBSearchRAGResponse:
    return DBSearchRAG(
        embedding_fn=embedding_fn,
        dsn=dsn,
        embedding_model=embedding_model,
        auto_create_embedding=auto_create_embedding,
        include_graph=include_graph,
        graph_retriever=graph_retriever,
    ).search_context(
        query=query,
        top_k=top_k,
        reliability_filter=reliability_filter,
        mode=mode,
        graph_top_k=graph_top_k,
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
    include_graph: bool = False,
    graph_retriever: Any | None = None,
    graph_top_k: int | None = None,
) -> AgentState:
    return DBSearchRAG(
        embedding_fn=embedding_fn,
        dsn=dsn,
        embedding_model=embedding_model,
        auto_create_embedding=auto_create_embedding,
        include_graph=include_graph,
        graph_retriever=graph_retriever,
    ).update_state(
        state=state,
        top_k=top_k,
        reliability_filter=reliability_filter,
        mode=mode,
        graph_top_k=graph_top_k,
    )


__all__ = [
    "DBSearchRAG",
    "DBSearchRAGResponse",
    "DBSearchResult",
    "DEFAULT_EMBEDDING_MODEL",
    "GraphReliabilityFilter",
    "GraphSearchResult",
    "Neo4jGraphRetriever",
    "PGVectorDBRetriever",
    "ReliabilityFilter",
    "SearchMode",
    "create_default_embedding_fn",
    "db_search_rag_node",
    "run_db_search_rag",
    "search_db",
    "search_db_state",
    "search_graph",
]
