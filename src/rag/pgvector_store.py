from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Sequence

import psycopg2
from dotenv import load_dotenv
from pgvector.psycopg2 import register_vector
from psycopg2.extras import RealDictCursor

from common.state import RetrievedDocument


try:
    from langchain_core.documents import Document
except ImportError:
    @dataclass
    class Document:  # type: ignore[no-redef]
        page_content: str
        metadata: dict[str, Any]


def database_url() -> str:
    load_dotenv()
    return os.getenv("POSTGRES_URI") or os.getenv("DATABASE_URL") or (
        "postgresql://"
        f"{os.getenv('POSTGRES_USER', 'admin')}:"
        f"{os.getenv('POSTGRES_PASSWORD', 'admin123')}@"
        f"{os.getenv('POSTGRES_HOST', 'localhost')}:"
        f"{os.getenv('POSTGRES_PORT', '5432')}/"
        f"{os.getenv('POSTGRES_DB', 'mapledb')}"
    )


class MaplePGVectorStore:
    """Custom PGVector wrapper for the project's ERD tables."""

    def __init__(self, embedding_fn: Any, dsn: str | None = None) -> None:
        self.embedding_fn = embedding_fn
        self.dsn = dsn or database_url()

    def similarity_search(
        self,
        query: str,
        k: int = 4,
        filters: dict[str, Any] | None = None,
    ) -> list[Document]:
        return [doc for doc, _score in self.similarity_search_with_score(query, k, filters)]

    def similarity_search_with_score(
        self,
        query: str,
        k: int = 4,
        filters: dict[str, Any] | None = None,
    ) -> list[tuple[Document, float]]:
        query_embedding = self.embedding_fn.embed_query(query)
        rows = self._vector_rows(query_embedding, k, filters)
        return [(self._row_to_document(row), float(row["score"] or 0)) for row in rows]

    def retrieve_documents(
        self,
        query: str,
        k: int = 4,
        filters: dict[str, Any] | None = None,
    ) -> list[RetrievedDocument]:
        query_embedding = self.embedding_fn.embed_query(query)
        rows = self._vector_rows(query_embedding, k, filters)
        return [self._row_to_retrieved_document(row) for row in rows]

    def keyword_search(
        self,
        keyword: str,
        k: int = 4,
        filters: dict[str, Any] | None = None,
    ) -> list[Document]:
        rows = self._keyword_rows(keyword, k, filters)
        return [self._row_to_document(row) for row in rows]

    def keyword_retrieve(
        self,
        keyword: str,
        k: int = 4,
        filters: dict[str, Any] | None = None,
    ) -> list[RetrievedDocument]:
        rows = self._keyword_rows(keyword, k, filters)
        return [self._row_to_retrieved_document(row) for row in rows]

    def hybrid_search(
        self,
        query: str,
        keyword: str | None = None,
        k: int = 4,
        filters: dict[str, Any] | None = None,
    ) -> list[Document]:
        keyword = keyword or query
        seen: set[str] = set()
        merged: list[Document] = []
        for document in self.similarity_search(query, k, filters) + self.keyword_search(keyword, k, filters):
            chunk_id = str(document.metadata.get("chunk_id"))
            if chunk_id not in seen:
                merged.append(document)
                seen.add(chunk_id)
            if len(merged) >= k:
                break
        return merged

    def hybrid_retrieve(
        self,
        query: str,
        keyword: str | None = None,
        k: int = 4,
        filters: dict[str, Any] | None = None,
    ) -> list[RetrievedDocument]:
        keyword = keyword or query
        seen: set[str] = set()
        merged: list[RetrievedDocument] = []
        for document in self.retrieve_documents(query, k, filters) + self.keyword_retrieve(keyword, k, filters):
            chunk_id = str(document["metadata"].get("chunk_id"))
            if chunk_id not in seen:
                merged.append(document)
                seen.add(chunk_id)
            if len(merged) >= k:
                break
        return merged

    def as_retriever(self, search_kwargs: dict[str, Any] | None = None):
        return MaplePGVectorRetriever(self, search_kwargs or {})

    def _connect(self):
        conn = psycopg2.connect(self.dsn, cursor_factory=RealDictCursor)
        register_vector(conn)
        return conn

    def _vector_rows(
        self,
        query_embedding: Sequence[float],
        k: int,
        filters: dict[str, Any] | None,
    ) -> list[dict[str, Any]]:
        where_sql, params = _filters_to_sql(filters)
        sql = f"""
            SELECT
                dc.chunk_id,
                dc.content,
                dc.chunk_index,
                d.doc_id,
                d.title,
                d.category,
                d.collection_scope,
                d.source_type,
                d.source_url,
                d.trust_level,
                de.embedding_model,
                1 - (de.embedding <=> %s::vector) AS score
            FROM document_embeddings de
            JOIN document_chunks dc ON dc.id = de.chunk_id
            JOIN documents d ON d.id = dc.document_id
            WHERE d.rag_ready = true
              {where_sql}
            ORDER BY de.embedding <=> %s::vector
            LIMIT %s
        """
        query_vector = list(query_embedding)
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, [query_vector, *params, query_vector, k])
                return list(cur.fetchall())

    def _keyword_rows(
        self,
        keyword: str,
        k: int,
        filters: dict[str, Any] | None,
    ) -> list[dict[str, Any]]:
        where_sql, params = _filters_to_sql(filters)
        like_keyword = f"%{keyword}%"
        sql = f"""
            SELECT
                dc.chunk_id,
                dc.content,
                dc.chunk_index,
                d.doc_id,
                d.title,
                d.category,
                d.collection_scope,
                d.source_type,
                d.source_url,
                d.trust_level,
                NULL AS embedding_model,
                ts_rank_cd(to_tsvector('simple', dc.content), plainto_tsquery('simple', %s)) AS score
            FROM document_chunks dc
            JOIN documents d ON d.id = dc.document_id
            WHERE d.rag_ready = true
              {where_sql}
              AND (
                  to_tsvector('simple', dc.content) @@ plainto_tsquery('simple', %s)
                  OR dc.content ILIKE %s
                  OR d.title ILIKE %s
              )
            ORDER BY score DESC, dc.chunk_index ASC
            LIMIT %s
        """
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, [keyword, *params, keyword, like_keyword, like_keyword, k])
                return list(cur.fetchall())

    def _row_to_document(self, row: dict[str, Any]) -> Document:
        return Document(
            page_content=row["content"],
            metadata={
                "chunk_id": row["chunk_id"],
                "doc_id": row["doc_id"],
                "title": row["title"],
                "category": row["category"],
                "collection_scope": row["collection_scope"],
                "source_type": row["source_type"],
                "source_url": row["source_url"],
                "trust_level": row["trust_level"],
                "chunk_index": row["chunk_index"],
                "embedding_model": row["embedding_model"],
            },
        )

    def _row_to_retrieved_document(self, row: dict[str, Any]) -> RetrievedDocument:
        source = row["source_url"] or row["doc_id"]
        return {
            "page_content": row["content"],
            "metadata": {
                "chunk_id": row["chunk_id"],
                "doc_id": row["doc_id"],
                "title": row["title"],
                "category": row["category"],
                "collection_scope": row["collection_scope"],
                "source_type": row["source_type"],
                "source_url": row["source_url"],
                "trust_level": row["trust_level"],
                "chunk_index": row["chunk_index"],
                "embedding_model": row["embedding_model"],
            },
            "score": float(row["score"] or 0),
            "source": source,
        }


class MaplePGVectorRetriever:
    def __init__(self, store: MaplePGVectorStore, search_kwargs: dict[str, Any]) -> None:
        self.store = store
        self.search_kwargs = search_kwargs

    def invoke(self, query: str) -> list[RetrievedDocument]:
        return self.store.retrieve_documents(query, **self.search_kwargs)

    def get_relevant_documents(self, query: str) -> list[RetrievedDocument]:
        return self.invoke(query)


def _filters_to_sql(filters: dict[str, Any] | None) -> tuple[str, list[Any]]:
    if not filters:
        return "", []

    clauses: list[str] = []
    params: list[Any] = []
    allowed_columns = {
        "category": "d.category",
        "collection_scope": "d.collection_scope",
        "source_type": "d.source_type",
        "trust_level": "d.trust_level",
        "doc_id": "d.doc_id",
    }

    for key, value in filters.items():
        column = allowed_columns.get(key)
        if not column:
            raise ValueError(f"Unsupported metadata filter: {key}")
        if isinstance(value, (list, tuple, set)):
            clauses.append(f"{column} = ANY(%s)")
            params.append(list(value))
        else:
            clauses.append(f"{column} = %s")
            params.append(value)

    return "AND " + " AND ".join(clauses), params


def create_pgvector_store(embedding_fn: Any, dsn: str | None = None) -> MaplePGVectorStore:
    return MaplePGVectorStore(embedding_fn=embedding_fn, dsn=dsn)
