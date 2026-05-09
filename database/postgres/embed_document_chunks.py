from __future__ import annotations

import argparse
import hashlib
import os
import sys
from pathlib import Path
from typing import Any

import psycopg2
from dotenv import load_dotenv
from pgvector.psycopg2 import register_vector
from psycopg2.extras import RealDictCursor

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from common.get_model import get_embedding_model
from common.logging_config import set_logging


DEFAULT_MODEL = "google/embeddinggemma-300m"
DEFAULT_OPENAI_MODEL = "text-embedding-3-small"
LOCAL_HASH_MODEL = "local-hash-embedding-768"
EMBEDDING_DIMENSION = 768
logger = set_logging()


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


def create_openai_embeddings(model: str = DEFAULT_OPENAI_MODEL) -> Any:
    try:
        from langchain_openai import OpenAIEmbeddings
    except ImportError as exc:
        raise RuntimeError("langchain-openai is required for OpenAI embeddings.") from exc
    return OpenAIEmbeddings(model=model)


class SentenceTransformerEmbeddings:
    def __init__(self, model_name: str = DEFAULT_MODEL) -> None:
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise RuntimeError(
                "sentence-transformers is required for google/embeddinggemma-300m."
            ) from exc

        self.model_name = model_name
        self.model = SentenceTransformer(model_name)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if hasattr(self.model, "encode_document"):
            embeddings = self.model.encode_document(texts, normalize_embeddings=True)
        else:
            embeddings = self.model.encode(texts, normalize_embeddings=True)
        return [embedding.tolist() for embedding in embeddings]

    def embed_query(self, text: str) -> list[float]:
        if hasattr(self.model, "encode_query"):
            embedding = self.model.encode_query(text, normalize_embeddings=True)
        else:
            embedding = self.model.encode(text, normalize_embeddings=True)
        return embedding.tolist()


class LocalHashEmbeddings:
    """Deterministic offline embedding for PGVector smoke tests and local RAG demos."""

    def __init__(self, dimension: int = EMBEDDING_DIMENSION) -> None:
        self.dimension = dimension

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self.embed_query(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        vector = [0.0] * self.dimension
        tokens = [token for token in text.lower().split() if token]
        if not tokens:
            tokens = [text]

        for token in tokens:
            digest = hashlib.blake2b(token.encode("utf-8"), digest_size=16).digest()
            index = int.from_bytes(digest[:4], "big") % self.dimension
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vector[index] += sign

        norm = sum(value * value for value in vector) ** 0.5
        if norm == 0:
            return vector
        return [value / norm for value in vector]


def connect(dsn: str):
    conn = psycopg2.connect(dsn, cursor_factory=RealDictCursor)
    register_vector(conn)
    return conn


def fetch_unembedded_chunks(conn, embedding_model: str, batch_size: int) -> list[dict[str, Any]]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT dc.id, dc.content
            FROM document_chunks dc
            JOIN documents d ON d.id = dc.document_id
            LEFT JOIN document_embeddings de
                ON de.chunk_id = dc.id
               AND de.embedding_model = %s
            WHERE d.rag_ready = true
              AND de.id IS NULL
            ORDER BY d.trust_level ASC NULLS LAST, dc.created_at ASC
            LIMIT %s
            """,
            (embedding_model, batch_size),
        )
        return list(cur.fetchall())


def upsert_embeddings(conn, rows: list[dict[str, Any]], embeddings: list[list[float]], embedding_model: str) -> None:
    with conn.cursor() as cur:
        for row, embedding in zip(rows, embeddings):
            cur.execute(
                """
                INSERT INTO document_embeddings (chunk_id, embedding, embedding_model)
                VALUES (%s, %s, %s)
                ON CONFLICT (chunk_id) DO UPDATE SET
                    embedding = EXCLUDED.embedding,
                    embedding_model = EXCLUDED.embedding_model,
                    updated_at = now()
                """,
                (row["id"], embedding, embedding_model),
            )
    conn.commit()


def embed_pending_chunks(
    embedding_fn: Any,
    dsn: str,
    embedding_model: str,
    batch_size: int = 64,
    max_batches: int | None = None,
) -> int:
    total = 0
    batch_no = 0
    with connect(dsn) as conn:
        while True:
            rows = fetch_unembedded_chunks(conn, embedding_model, batch_size)
            if not rows:
                break

            texts = [row["content"] for row in rows]
            vectors = embedding_fn.embed_documents(texts)
            upsert_embeddings(conn, rows, vectors, embedding_model)

            total += len(rows)
            batch_no += 1
            logger.info("embedded batch=%s chunks=%s total=%s", batch_no, len(rows), total)

            if max_batches is not None and batch_no >= max_batches:
                break
    return total


def main() -> None:
    parser = argparse.ArgumentParser(description="Embed PostgreSQL document_chunks into PGVector.")
    parser.add_argument("--dsn", default=database_url())
    parser.add_argument(
        "--provider",
        choices=["embeddinggemma", "local-hash", "openai", "common"],
        default="embeddinggemma",
    )
    parser.add_argument("--model")
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--max-batches", type=int)
    args = parser.parse_args()

    if args.provider == "embeddinggemma":
        embedding_model = args.model or DEFAULT_MODEL
        embedding_fn = SentenceTransformerEmbeddings(embedding_model)
    elif args.provider == "local-hash":
        embedding_model = args.model or LOCAL_HASH_MODEL
        embedding_fn = LocalHashEmbeddings()
    elif args.provider == "openai":
        embedding_model = args.model or DEFAULT_OPENAI_MODEL
        embedding_fn = create_openai_embeddings(embedding_model)
    elif args.provider == "common":
        embedding_model = args.model or "common.get_model"
        embedding_fn = get_embedding_model()
    else:
        raise ValueError(f"Unsupported provider: {args.provider}")

    total = embed_pending_chunks(
        embedding_fn=embedding_fn,
        dsn=args.dsn,
        embedding_model=embedding_model,
        batch_size=args.batch_size,
        max_batches=args.max_batches,
    )
    logger.info("embedded total=%s", total)


if __name__ == "__main__":
    main()
