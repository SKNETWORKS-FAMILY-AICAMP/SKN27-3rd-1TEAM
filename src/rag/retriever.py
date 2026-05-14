from __future__ import annotations

import os
from dataclasses import dataclass, replace
from typing import Any, Iterable, Literal, Sequence

import psycopg2
from dotenv import load_dotenv
from pgvector.psycopg2 import register_vector
from psycopg2.extras import RealDictCursor

from common.state import AgentState, RetrievedDocument
from src.rag.web_search import WebSearchRAG, to_retrieved_documents


ReliabilityFilter = Literal["ALL", "HIGH_ONLY"]
GraphReliabilityFilter = ReliabilityFilter
SearchMode = Literal["auto", "text", "vector", "hybrid"]
DEFAULT_EMBEDDING_MODEL = "google/embeddinggemma-300m"
DEFAULT_VECTOR_WEIGHT = 0.65
DEFAULT_TEXT_WEIGHT = 0.35
DEFAULT_CANDIDATE_MULTIPLIER = 3
DEFAULT_DB_CONNECT_TIMEOUT_SECONDS = 3
DEFAULT_NEO4J_CONNECTION_TIMEOUT_SECONDS = 3
GRAPH_RELIABILITY = "MEDIUM"


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
    category: str | None = None
    collection_scope: str | None = None
    source_type: str | None = None
    trust_level: str | None = None
    chunk_index: int | None = None
    embedding_model: str | None = None
    entity_type: str | None = None

    def to_source(self) -> dict[str, str | float | None]:
        return {
            "title": self.title,
            "url": self.source_url,
            "reliability": self.reliability,
            "score": self.score,
            "retrieval_method": self.retrieval_method,
            "entity_type": self.entity_type,
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
                "category": self.category,
                "collection_scope": self.collection_scope,
                "source_type": self.source_type,
                "trust_level": self.trust_level,
                "chunk_index": self.chunk_index,
                "embedding_model": self.embedding_model,
                "entity_type": self.entity_type,
            },
            "score": self.score,
            "source": self.source_url or self.document_id,
        }


@dataclass(frozen=True)
class GraphSearchResult:
    graph_id: str
    title: str
    content: str
    source_url: str | None
    reliability: str | None
    score: float
    entity_type: str | None = None
    retrieval_method: str = "graph"

    def to_source(self) -> dict[str, str | float | None]:
        return {
            "title": self.title,
            "url": self.source_url,
            "reliability": self.reliability,
            "score": self.score,
            "retrieval_method": self.retrieval_method,
            "entity_type": self.entity_type,
        }

    def to_retrieved_document(self) -> RetrievedDocument:
        return {
            "page_content": self.content,
            "metadata": {
                "chunk_id": self.graph_id,
                "document_id": self.graph_id,
                "title": self.title,
                "source_url": self.source_url,
                "reliability": self.reliability,
                "entity_type": self.entity_type,
                "retrieval_method": self.retrieval_method,
            },
            "score": self.score,
            "source": self.source_url or self.graph_id,
        }


def get_connection(dsn: str | None = None):
    conn = psycopg2.connect(
        dsn or _database_url(),
        cursor_factory=RealDictCursor,
        connect_timeout=_env_int(
            "POSTGRES_CONNECT_TIMEOUT_SECONDS",
            DEFAULT_DB_CONNECT_TIMEOUT_SECONDS,
        ),
    )
    register_vector(conn)
    return conn


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
                d.category,
                d.collection_scope,
                d.source_type,
                d.trust_level,
                dc.chunk_index,
                de.embedding_model,
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
        candidate_k = max(top_k * DEFAULT_CANDIDATE_MULTIPLIER, top_k)
        chunk_results = self._chunk_text_search(query, candidate_k, reliability_filter)
        entity_results = self.entity_search(query, candidate_k, reliability_filter)
        return _merge_ranked_results([*chunk_results, *entity_results], top_k)

    def _chunk_text_search(
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
                d.category,
                d.collection_scope,
                d.source_type,
                d.trust_level,
                dc.chunk_index,
                NULL AS embedding_model,
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

    def entity_search(
        self,
        query: str,
        top_k: int = 5,
        reliability_filter: ReliabilityFilter = "ALL",
    ) -> list[DBSearchResult]:
        trust_sql, trust_params = _trust_clause(reliability_filter)
        terms = _search_terms(query)
        token_patterns = [f"%{term}%" for term in terms]
        token_score_sql, token_score_params = _entity_token_score_sql(token_patterns)
        normalized_query = " ".join(query.strip().lower().split())
        like_query = f"%{query}%"
        entity_type_like = f"%{normalized_query}%"
        sql = f"""
            SELECT
                'wiki_entity::' || we.id::text AS chunk_id,
                d.doc_id AS document_id,
                we.entity_name || ' (' || we.entity_type || ')' AS title,
                concat_ws(
                    E'\\n',
                    'Wiki entity index',
                    'entity_type: ' || we.entity_type,
                    'entity_name: ' || we.entity_name,
                    CASE
                        WHEN we.level IS NOT NULL THEN 'level: ' || we.level::text
                        ELSE NULL
                    END,
                    'category: ' || coalesce(we.category, d.category, 'unknown'),
                    'summary: ' || coalesce(we.description, d.text_preview, '')
                ) AS content,
                d.source_url,
                d.trust_level AS reliability,
                d.category,
                d.collection_scope,
                d.source_type,
                d.trust_level,
                NULL::int AS chunk_index,
                NULL::text AS embedding_model,
                we.entity_type,
                (
                    CASE WHEN we.normalized_name = %s THEN 3.0 ELSE 0 END
                    + CASE WHEN we.entity_name ILIKE %s OR d.title ILIKE %s THEN 1.5 ELSE 0 END
                    + CASE WHEN we.entity_type ILIKE %s THEN 0.5 ELSE 0 END
                    + CASE WHEN coalesce(we.description, '') ILIKE %s THEN 0.5 ELSE 0 END
                    {token_score_sql}
                ) AS score
            FROM wiki_entities we
            JOIN documents d ON d.id = we.document_id
            WHERE d.rag_ready = true
              {trust_sql}
              AND (
                  we.normalized_name = %s
                  OR we.entity_name ILIKE %s
                  OR we.normalized_name ILIKE %s
                  OR we.entity_type ILIKE %s
                  OR coalesce(we.description, '') ILIKE %s
                  OR d.title ILIKE %s
                  OR we.entity_name ILIKE ANY(%s)
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
                we.entity_name ASC
            LIMIT %s
        """
        params = [
            normalized_query,
            like_query,
            like_query,
            entity_type_like,
            like_query,
            *token_score_params,
            *trust_params,
            normalized_query,
            like_query,
            like_query,
            entity_type_like,
            like_query,
            like_query,
            token_patterns,
            token_patterns,
            top_k,
        ]
        return self._fetch(sql, params, retrieval_method="entity")

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
                category=row.get("category"),
                collection_scope=row.get("collection_scope"),
                source_type=row.get("source_type"),
                trust_level=row.get("trust_level"),
                chunk_index=row.get("chunk_index"),
                embedding_model=row.get("embedding_model"),
                entity_type=row.get("entity_type"),
            )
            for row in rows
        ]


class Neo4jGraphRetriever:
    """Neo4j retriever that returns graph facts as RetrievedDocument-compatible rows."""

    def __init__(
        self,
        uri: str | None = None,
        user: str | None = None,
        password: str | None = None,
        database: str | None = None,
    ) -> None:
        load_dotenv()
        self.uri = uri or os.getenv("NEO4J_URI", "bolt://localhost:7687")
        self.user = user or os.getenv("NEO4J_USER", "neo4j")
        self.password = password or os.getenv("NEO4J_PASSWORD", "admin123")
        self.database = database or os.getenv("NEO4J_DATABASE", "mapledb")
        self.connection_timeout = _env_int(
            "NEO4J_CONNECT_TIMEOUT_SECONDS",
            DEFAULT_NEO4J_CONNECTION_TIMEOUT_SECONDS,
        )

    def search(
        self,
        query: str,
        top_k: int = 5,
        reliability_filter: GraphReliabilityFilter = "ALL",
    ) -> list[GraphSearchResult]:
        terms = _graph_terms(query)
        if not terms:
            terms = [query.strip().lower()]

        try:
            from neo4j import GraphDatabase
        except ImportError as exc:
            raise RuntimeError("neo4j package is required for GraphDB search.") from exc

        driver = GraphDatabase.driver(
            self.uri,
            auth=(self.user, self.password),
            connection_timeout=self.connection_timeout,
        )
        try:
            with driver.session(database=self.database) as session:
                requirement_rows = []
                if _is_requirement_query(query):
                    requirement_rows = session.run(
                        _GRAPH_BOSS_REQUIREMENT_QUERY,
                        terms=terms,
                        limit=max(top_k * 2, top_k),
                    ).data()
                relation_rows = session.run(
                    _GRAPH_RELATION_FACT_QUERY,
                    terms=terms,
                    limit=max(top_k * 2, top_k),
                ).data()
                reward_rows = session.run(
                    _GRAPH_BOSS_REWARD_QUERY,
                    terms=terms,
                    limit=max(top_k * 2, top_k),
                ).data()
        finally:
            driver.close()

        results = [
            _graph_requirement_row_to_result(row, terms)
            for row in requirement_rows
        ] + [
            _graph_relation_row_to_result(row, terms)
            for row in relation_rows
        ] + [
            _graph_reward_row_to_result(row, terms)
            for row in reward_rows
        ]
        return _dedupe_and_rank_graph_results(results, top_k)

    def build_context(self, results: Iterable[GraphSearchResult]) -> str:
        blocks = []
        for index, result in enumerate(results, start=1):
            source = result.source_url or result.graph_id
            blocks.append(
                f"[graph:{index}] {result.title}\n"
                f"source: {source}\n"
                f"reliability: {result.reliability or 'unknown'}\n"
                f"retrieval_method: {result.retrieval_method}\n"
                f"score: {result.score:.4f}\n"
                f"{result.content}"
            )
        return "\n\n".join(blocks)


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


def search_graph(
    query: str,
    top_k: int = 5,
    reliability_filter: GraphReliabilityFilter = "ALL",
    retriever: Neo4jGraphRetriever | None = None,
) -> list[GraphSearchResult]:
    return (retriever or Neo4jGraphRetriever()).search(
        query=query,
        top_k=top_k,
        reliability_filter=reliability_filter,
    )


def graph_result_to_db_result(result: GraphSearchResult) -> DBSearchResult:
    return DBSearchResult(
        chunk_id=result.graph_id,
        document_id=result.graph_id,
        title=result.title,
        content=result.content,
        source_url=result.source_url,
        reliability=result.reliability,
        score=float(result.score or 0),
        retrieval_method=result.retrieval_method,
        entity_type=result.entity_type,
    )


def merge_db_and_graph_results(
    db_results: Sequence[DBSearchResult],
    graph_results: Sequence[DBSearchResult],
    top_k: int,
) -> list[DBSearchResult]:
    merged: dict[str, DBSearchResult] = {}
    for result in list(db_results) + list(graph_results):
        current = merged.get(result.chunk_id)
        if current is None or result.score > current.score:
            merged[result.chunk_id] = result
    return sorted(
        merged.values(),
        key=lambda result: (
            _retrieval_priority(result.retrieval_method),
            result.score,
            _trust_priority(result.reliability),
            result.title,
        ),
        reverse=True,
    )[:top_k]


def _merge_ranked_results(
    results: Sequence[DBSearchResult],
    top_k: int,
) -> list[DBSearchResult]:
    merged: dict[str, DBSearchResult] = {}
    for result in results:
        current = merged.get(result.chunk_id)
        if current is None or result.score > current.score:
            merged[result.chunk_id] = result

    return sorted(
        merged.values(),
        key=lambda result: (
            result.score,
            _trust_priority(result.reliability),
            _retrieval_priority(result.retrieval_method),
            result.title,
        ),
        reverse=True,
    )[:top_k]


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


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _trust_clause(reliability_filter: ReliabilityFilter) -> tuple[str, list[object]]:
    if reliability_filter == "HIGH_ONLY":
        return "AND d.trust_level = ANY(%s)", [["S", "A"]]
    return "", []


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


def _entity_token_score_sql(token_patterns: Sequence[str]) -> tuple[str, list[object]]:
    if not token_patterns:
        return "", []

    sql_parts = []
    params: list[object] = []
    for _pattern in token_patterns:
        sql_parts.append(
            """
                    + CASE
                        WHEN we.entity_name ILIKE %s
                          OR we.normalized_name ILIKE %s
                          OR coalesce(we.description, '') ILIKE %s
                          OR d.title ILIKE %s
                        THEN 0.1
                        ELSE 0
                      END
            """
        )
        params.extend([_pattern, _pattern, _pattern, _pattern])
    return "".join(sql_parts), params


_GRAPH_BOSS_REQUIREMENT_QUERY = """
MATCH (boss:Boss)-[:HAS_REQUIREMENT]->(requirement:StatRequirement)
OPTIONAL MATCH (alias:BossAlias)-[:ALIAS_OF]->(boss)
WITH boss, requirement, collect(DISTINCT alias) AS aliases
WHERE any(term IN $terms WHERE
    toLower(coalesce(boss.name, '')) CONTAINS term OR
    toLower(coalesce(requirement.boss_name, '')) CONTAINS term OR
    any(alias IN aliases WHERE
        toLower(coalesce(alias.name, '')) CONTAINS term OR
        toLower(coalesce(alias.normalized_name, '')) CONTAINS term
    )
)
RETURN
    elementId(boss) + ':HAS_REQUIREMENT:' + elementId(requirement) AS graph_id,
    boss.name AS boss_name,
    boss.difficulty AS difficulty,
    boss.required_level AS required_level,
    boss.boss_type AS boss_type,
    properties(boss) AS boss_props,
    properties(requirement) AS requirement_props,
    [alias IN aliases WHERE alias.name IS NOT NULL | alias.name] AS aliases
LIMIT $limit
"""


_GRAPH_RELATION_FACT_QUERY = """
MATCH (start)-[rel]->(finish)
WHERE any(term IN $terms WHERE
    toLower(coalesce(start.name, '')) CONTAINS term OR
    toLower(coalesce(start.code, '')) CONTAINS term OR
    toLower(coalesce(start.description, '')) CONTAINS term OR
    toLower(coalesce(finish.name, '')) CONTAINS term OR
    toLower(coalesce(finish.code, '')) CONTAINS term OR
    toLower(coalesce(finish.description, '')) CONTAINS term OR
    toLower(coalesce(finish.boss_name, '')) CONTAINS term
)
AND type(rel) <> 'MENTIONED_IN'
AND type(rel) <> 'DROPS_REWARD'
RETURN
    elementId(start) + ':' + type(rel) + ':' + elementId(finish) AS graph_id,
    labels(start)[0] AS start_type,
    coalesce(start.name, start.code, start.boss_name, 'unknown') AS start_name,
    type(rel) AS relationship,
    labels(finish)[0] AS end_type,
    coalesce(finish.name, finish.code, finish.boss_name, 'unknown') AS end_name,
    properties(start) AS start_props,
    properties(finish) AS end_props
LIMIT $limit
"""


_GRAPH_BOSS_REWARD_QUERY = """
MATCH (boss:Boss)-[:DROPS_REWARD]->(reward:Reward)
OPTIONAL MATCH (alias:BossAlias)-[:ALIAS_OF]->(boss)
WITH boss, reward, collect(DISTINCT alias) AS aliases
WHERE any(term IN $terms WHERE
    toLower(coalesce(boss.name, '')) CONTAINS term OR
    toLower(coalesce(boss.difficulty, '')) CONTAINS term OR
    toLower(coalesce(reward.name, '')) CONTAINS term OR
    toLower(coalesce(reward.reward_type, '')) CONTAINS term OR
    toLower(coalesce(reward.value_type, '')) CONTAINS term OR
    toLower(coalesce(reward.description, '')) CONTAINS term OR
    any(alias IN aliases WHERE
        toLower(coalesce(alias.name, '')) CONTAINS term OR
        toLower(coalesce(alias.normalized_name, '')) CONTAINS term
    )
)
RETURN
    elementId(boss) + ':DROPS_REWARD:' + elementId(reward) AS graph_id,
    boss.name AS boss_name,
    boss.difficulty AS difficulty,
    properties(boss) AS boss_props,
    properties(reward) AS reward_props,
    [alias IN aliases WHERE alias.name IS NOT NULL | alias.name] AS aliases
LIMIT $limit
"""


def _graph_requirement_row_to_result(
    row: dict[str, Any],
    terms: list[str],
) -> GraphSearchResult:
    boss_name = row.get("boss_name") or "unknown"
    difficulty = row.get("difficulty") or "unknown"
    requirement_props = _compact_graph_props(row.get("requirement_props"))
    boss_props = _compact_graph_props(row.get("boss_props"))
    aliases = [item for item in row.get("aliases", []) if item]
    title = f"{boss_name} - HAS_REQUIREMENT"
    content = (
        f"Graph boss requirement fact\n"
        f"Boss: {boss_name}\n"
        f"aliases: {', '.join(aliases)}\n"
        f"difficulty: {difficulty}\n"
        f"relationship: HAS_REQUIREMENT\n"
        f"required_level: {requirement_props.get('level') or row.get('required_level') or ''}\n"
        f"main_stat: {requirement_props.get('main_stat') or ''}\n"
        f"arcane_force: {requirement_props.get('arcane_force') or ''}\n"
        f"authentic_force: {requirement_props.get('authentic_force') or ''}\n"
        f"boss_damage: {requirement_props.get('boss_damage') or ''}\n"
        f"ignore_def: {requirement_props.get('ignore_def') or ''}\n"
        f"confidence: {requirement_props.get('confidence') or ''}\n"
        f"boss_properties: {boss_props}\n"
        f"requirement_properties: {requirement_props}"
    )
    return GraphSearchResult(
        graph_id=f"graph::requirement::{row.get('graph_id')}",
        title=title,
        content=content,
        source_url=None,
        reliability=GRAPH_RELIABILITY,
        score=_score_graph_text(f"{title} {content}", terms) + 1.0,
        entity_type="Boss->StatRequirement",
        retrieval_method="graph_requirement",
    )


def _graph_reward_row_to_result(
    row: dict[str, Any],
    terms: list[str],
) -> GraphSearchResult:
    boss_name = row.get("boss_name") or "unknown"
    difficulty = row.get("difficulty") or "unknown"
    reward_props = _compact_graph_props(row.get("reward_props"))
    boss_props = _compact_graph_props(row.get("boss_props"))
    aliases = [item for item in row.get("aliases", []) if item]
    reward_name = reward_props.get("name") or "unknown"
    title = f"{boss_name} - DROPS_REWARD - {reward_name}"
    content = (
        f"Graph boss reward fact\n"
        f"Boss: {boss_name}\n"
        f"aliases: {', '.join(aliases)}\n"
        f"difficulty: {difficulty}\n"
        f"relationship: DROPS_REWARD\n"
        f"Reward: {reward_name}\n"
        f"reward_type: {reward_props.get('reward_type') or ''}\n"
        f"value_type: {reward_props.get('value_type') or ''}\n"
        f"description: {reward_props.get('description') or ''}\n"
        f"boss_properties: {boss_props}\n"
        f"reward_properties: {reward_props}"
    )
    return GraphSearchResult(
        graph_id=f"graph::reward::{row.get('graph_id')}",
        title=title,
        content=content,
        source_url=None,
        reliability=GRAPH_RELIABILITY,
        score=_score_graph_text(f"{title} {content}", terms) + 0.8,
        entity_type="Boss->Reward",
        retrieval_method="graph_reward",
    )


def _graph_relation_row_to_result(
    row: dict[str, Any],
    terms: list[str],
) -> GraphSearchResult:
    start_name = row.get("start_name") or "unknown"
    end_name = row.get("end_name") or "unknown"
    relationship = row.get("relationship") or "RELATED_TO"
    start_type = row.get("start_type") or "Node"
    end_type = row.get("end_type") or "Node"
    title = f"{start_name} - {relationship} - {end_name}"
    content = (
        f"Graph relation fact\n"
        f"{start_type}: {start_name}\n"
        f"relationship: {relationship}\n"
        f"{end_type}: {end_name}\n"
        f"start_properties: {_compact_graph_props(row.get('start_props'))}\n"
        f"end_properties: {_compact_graph_props(row.get('end_props'))}"
    )
    return GraphSearchResult(
        graph_id=f"graph::relation::{row.get('graph_id')}",
        title=title,
        content=content,
        source_url=None,
        reliability=GRAPH_RELIABILITY,
        score=_score_graph_text(f"{title} {content}", terms),
        entity_type=f"{start_type}->{end_type}",
    )


def _dedupe_and_rank_graph_results(
    results: Iterable[GraphSearchResult],
    top_k: int,
) -> list[GraphSearchResult]:
    deduped: dict[str, GraphSearchResult] = {}
    for result in results:
        if result.graph_id not in deduped or result.score > deduped[result.graph_id].score:
            deduped[result.graph_id] = result
    return sorted(
        deduped.values(),
        key=lambda item: (item.score, _trust_priority(item.reliability), item.title),
        reverse=True,
    )[:top_k]


def _score_graph_text(text: str, terms: list[str]) -> float:
    lowered = text.lower()
    if not terms:
        return 0.0
    hits = sum(1 for term in terms if term and term in lowered)
    return round(hits / len(terms), 6)


def _graph_terms(query: str) -> list[str]:
    terms = []
    normalized_query = "".join(str(query or "").lower().split())
    if len(normalized_query) >= 2:
        terms.append(normalized_query)
    for raw_term in query.replace(",", " ").replace("?", " ").split():
        term = raw_term.strip().lower()
        if len(term) >= 2 and term not in terms:
            terms.append(term)
        if len(terms) >= 8:
            break
    return terms


def _is_requirement_query(query: str) -> bool:
    normalized_query = str(query or "").lower()
    requirement_keywords = (
        "필요스펙",
        "필요 스펙",
        "요구스펙",
        "요구 스펙",
        "스펙컷",
        "필요조건",
        "필요 조건",
        "요구조건",
        "요구 조건",
        "입장조건",
        "입장 조건",
        "요구",
        "필요",
    )
    return any(keyword in normalized_query for keyword in requirement_keywords)


def _compact_graph_props(props: dict[str, Any] | None) -> dict[str, Any]:
    if not props:
        return {}
    return {
        key: value
        for key, value in props.items()
        if value not in (None, "")
        and key not in {"embedding", "content"}
    }


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
        "HIGH": 3,
        "graph_seed": 2,
        "B": 2,
        "MEDIUM": 2,
        "C": 1,
        "LOW": 1,
    }.get(reliability or "", 0)


def _retrieval_priority(retrieval_method: str) -> int:
    if "graph" in retrieval_method:
        return 2
    return 1


class Wrapper:
    """Wrapper that combines DB Search RAG and Web Search RAG documents."""

    def __init__(self, web_retriever: WebSearchRAG | None = None) -> None:
        self.web_retriever = web_retriever or WebSearchRAG()

    def retrieve_docs(
        self,
        query: str,
        **kwargs: Any,
    ) -> list[RetrievedDocument]:
        db_top_k = kwargs.pop("db_top_k", kwargs.pop("top_k", 5))
        web_max_results = kwargs.pop("web_max_results", 5)
        web_max_contexts = kwargs.pop("web_max_contexts", 5)
        official_only = kwargs.pop("official_only", True)
        character_context = kwargs.pop("character_context", None)
        db_docs = search_db_state(query=query, top_k=db_top_k, **kwargs)
        web_result = self.web_retriever.retrieve(
            question=query,
            character_context=character_context,
            official_only=official_only,
            max_results=web_max_results,
            max_contexts=web_max_contexts,
        )
        web_docs = to_retrieved_documents(web_result)
        return [*db_docs, *web_docs]

    def update_state(self, state: AgentState, **kwargs: Any) -> AgentState:
        kwargs.setdefault("character_context", state.get("character_profile") or state)
        retrieved_docs = self.retrieve_docs(state["user_query"], **kwargs)
        return {
            **state,
            "retrieved_docs": retrieved_docs,
            "context": self.build_context(retrieved_docs),
        }

    def build_context(self, docs: Iterable[RetrievedDocument]) -> str:
        blocks = []
        for index, doc in enumerate(docs, start=1):
            metadata = doc.get("metadata", {})
            title = metadata.get("title") or doc.get("source") or "retrieved document"
            source = metadata.get("url") or metadata.get("source_url") or doc.get("source") or ""
            reliability = metadata.get("reliability") or "unknown"
            blocks.append(
                f"[{index}] {title}\n"
                f"source: {source}\n"
                f"reliability: {reliability}\n"
                f"{doc.get('page_content', '')}"
            )
        return "\n\n".join(blocks)
