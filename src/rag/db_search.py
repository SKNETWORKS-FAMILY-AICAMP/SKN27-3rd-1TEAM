from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Iterable, Literal, Sequence

import psycopg2
from dotenv import load_dotenv
from psycopg2.extras import RealDictCursor
from pgvector.psycopg2 import register_vector

from common.state import RetrievedDocument


ReliabilityFilter = Literal["ALL", "HIGH_ONLY"]


@dataclass(frozen=True)
class DBSearchResult:
    chunk_id: str
    document_id: str
    title: str
    content: str
    source_url: str | None
    reliability: str | None
    score: float

    def to_source(self) -> dict[str, str | float | None]:
        return {
            "title": self.title,
            "url": self.source_url,
            "reliability": self.reliability,
            "score": self.score,
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
            },
            "score": self.score,
            "source": self.source_url or self.document_id,
        }


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


def _trust_clause(reliability_filter: ReliabilityFilter) -> tuple[str, list[str]]:
    if reliability_filter == "HIGH_ONLY":
        return "AND d.trust_level = ANY(%s)", [["S", "A"]]
    return "", []


class PGVectorDBRetriever:
    def __init__(self, dsn: str | None = None) -> None:
        self.dsn = dsn

    def search(
        self,
        query: str,
        query_embedding: Sequence[float] | None = None,
        top_k: int = 5,
        reliability_filter: ReliabilityFilter = "ALL",
    ) -> list[DBSearchResult]:
        if query_embedding:
            return self.vector_search(query_embedding, top_k, reliability_filter)
        return self.text_search(query, top_k, reliability_filter)

    def vector_search(
        self,
        query_embedding: Sequence[float],
        top_k: int = 5,
        reliability_filter: ReliabilityFilter = "ALL",
    ) -> list[DBSearchResult]:
        trust_sql, trust_params = _trust_clause(reliability_filter)
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
            ORDER BY de.embedding <=> %s::vector
            LIMIT %s
        """
        params = [list(query_embedding), *trust_params, list(query_embedding), top_k]
        return self._fetch(sql, params)

    def text_search(
        self,
        query: str,
        top_k: int = 5,
        reliability_filter: ReliabilityFilter = "ALL",
    ) -> list[DBSearchResult]:
        trust_sql, trust_params = _trust_clause(reliability_filter)
        sql = f"""
            SELECT
                dc.chunk_id,
                d.doc_id AS document_id,
                d.title,
                dc.content,
                d.source_url,
                d.trust_level AS reliability,
                ts_rank_cd(to_tsvector('simple', dc.content), plainto_tsquery('simple', %s)) AS score
            FROM document_chunks dc
            JOIN documents d ON d.id = dc.document_id
            WHERE d.rag_ready = true
              {trust_sql}
              AND (
                  to_tsvector('simple', dc.content) @@ plainto_tsquery('simple', %s)
                  OR dc.content ILIKE %s
                  OR d.title ILIKE %s
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
        params = [query, *trust_params, query, like_query, like_query, top_k]
        return self._fetch(sql, params)

    def build_context(self, results: Iterable[DBSearchResult]) -> str:
        blocks = []
        for index, result in enumerate(results, start=1):
            source = result.source_url or result.document_id
            blocks.append(f"[{index}] {result.title}\nsource: {source}\n{result.content}")
        return "\n\n".join(blocks)

    def _fetch(self, sql: str, params: Sequence[object]) -> list[DBSearchResult]:
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
            )
            for row in rows
        ]


def search_db(
    query: str,
    query_embedding: Sequence[float] | None = None,
    top_k: int = 5,
    reliability_filter: ReliabilityFilter = "ALL",
    dsn: str | None = None,
) -> list[DBSearchResult]:
    return PGVectorDBRetriever(dsn=dsn).search(
        query=query,
        query_embedding=query_embedding,
        top_k=top_k,
        reliability_filter=reliability_filter,
    )


def search_db_state(
    query: str,
    query_embedding: Sequence[float] | None = None,
    top_k: int = 5,
    reliability_filter: ReliabilityFilter = "ALL",
    dsn: str | None = None,
) -> list[RetrievedDocument]:
    return [
        result.to_retrieved_document()
        for result in search_db(
            query=query,
            query_embedding=query_embedding,
            top_k=top_k,
            reliability_filter=reliability_filter,
            dsn=dsn,
        )
    ]
