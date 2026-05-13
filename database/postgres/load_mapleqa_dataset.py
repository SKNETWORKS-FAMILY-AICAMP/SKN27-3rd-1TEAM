from __future__ import annotations

import argparse
import ast
import csv
import hashlib
import os
import re
import sys
from pathlib import Path
from typing import Iterable

import psycopg2
from dotenv import load_dotenv
from psycopg2.extras import Json, RealDictCursor

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from common.logging_config import set_logging


logger = set_logging()

VECTOR_EXCLUDED_SCOPES = {"api_static_sample"}
COMMENT_TEXT = "\ub313\uae00"
REGISTER_TEXT = "\ub4f1\ub85d"
OFFICIAL_COMMENT_BLOCK_RE = re.compile(
    rf"(?:\s*-{{5,}})?\s*{COMMENT_TEXT}\s+\d+\s+.*$",
    re.DOTALL,
)
COMMENT_FORM_RE = re.compile(
    rf"{COMMENT_TEXT}\s*\n.*?(?=\n\s*관련 이벤트 목록|$)",
    re.DOTALL,
)
COMMENT_DATE_RE = re.compile(
    rf"\d{{4}}\.\d{{2}}\.\d{{2}}\s+\d{{2}}:\d{{2}}\s*{REGISTER_TEXT}.*$",
    re.DOTALL,
)
EVENT_DATE_RANGE_RE = re.compile(
    r"(\d{4}\.\d{2}\.\d{2})\s*(?:\([^)]+\))?\s*~\s*(\d{4}\.\d{2}\.\d{2})"
)
PARAGRAPH_BOUNDARY_RE = re.compile(r"\n{2,}|(?=\n\s*(?:[-■※]|\d+[.)]\s))")
SENTENCE_BOUNDARY_RE = re.compile(
    r"(?<=[.!?\u3002\uff01\uff1f])\s+"
    r"|(?<=[\uac00-\ud7a3][\ub2e4\uc694\uc8e0\uc74c\ub428\ud568])\s+"
)

DEFAULT_DATASET = (
    Path(__file__).resolve().parents[1]
    / "mapleqa_full_handoff_with_raw_2026-05-06"
    / "handoff_simplified"
    / "maple_chatbot_final_dataset.csv"
)


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


def parse_bool(value: str | None) -> bool:
    return str(value).strip().lower() in {"1", "true", "t", "yes", "y"}


def parse_int(value: str | None) -> int | None:
    if value is None or str(value).strip() == "":
        return None
    return int(float(value))


def parse_date(value: str | None) -> str | None:
    value = str(value or "").strip()
    return value or None


def parse_tags(value: str | None) -> list[str]:
    if not value:
        return []
    try:
        parsed = ast.literal_eval(value)
    except (SyntaxError, ValueError):
        parsed = [part.strip() for part in value.split(",")]
    return [str(tag).strip() for tag in parsed if str(tag).strip()]


def normalize_tag(value: str) -> str:
    return " ".join(value.strip().lower().split())


def truncate_preview(value: str, limit: int = 1000) -> str:
    value = " ".join((value or "").split())
    if len(value) <= limit:
        return value
    preview = value[:limit]
    last_sentence = max(preview.rfind(mark) for mark in (".", "!", "?", "。", "！", "？"))
    if last_sentence >= limit // 2:
        return preview[: last_sentence + 1].strip()
    last_space = preview.rfind(" ")
    if last_space >= limit // 2:
        return preview[:last_space].strip()
    return preview.strip()


def strip_official_comments(text: str) -> str:
    text = COMMENT_FORM_RE.sub("", text or "")
    text = COMMENT_DATE_RE.sub("", text)
    text = OFFICIAL_COMMENT_BLOCK_RE.sub("", text)
    return text.strip()


def official_event_fallback(row: dict[str, str], original: str, cleaned: str) -> str:
    if row.get("category") != "official_event" or cleaned.strip():
        return cleaned

    parts = [f"공식 이벤트: {row.get('title') or row['doc_id']}"]
    date_match = EVENT_DATE_RANGE_RE.search(original)
    if date_match:
        parts.append(f"이벤트 기간: {date_match.group(1)} ~ {date_match.group(2)}")
    if row.get("source_url"):
        parts.append(f"원문 URL: {row['source_url']}")
    parts.append("원문 본문 텍스트가 충분히 추출되지 않아 제목, 기간, 출처 정보를 기반으로 보존한 공식 이벤트 문서입니다.")
    return "\n".join(parts)


def clean_rag_text(row: dict[str, str]) -> str:
    text = row.get("rag_text") or row.get("text_preview") or ""
    if (
        row.get("source_type") == "official"
        and row.get("collection_scope") == "official_document_collection"
    ):
        text = official_event_fallback(row, text, strip_official_comments(text))
    return text.strip()


def raise_csv_field_limit() -> None:
    limit = sys.maxsize
    while True:
        try:
            csv.field_size_limit(limit)
            return
        except OverflowError:
            limit = int(limit / 10)


def source_id_for(row: dict[str, str]) -> str:
    raw = "|".join(
        [
            row.get("source_type", ""),
            row.get("collection_scope", ""),
            row.get("trust_level", ""),
        ]
    )
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]
    return f"mapleqa_{digest}"


def chunk_units(text: str, chunk_size: int) -> list[tuple[int, int]]:
    units: list[tuple[int, int]] = []
    paragraph_start = 0
    for match in PARAGRAPH_BOUNDARY_RE.finditer(text):
        paragraph_end = match.start()
        if paragraph_end > paragraph_start:
            units.extend(sentence_units(text, paragraph_start, paragraph_end, chunk_size))
        paragraph_start = match.end() if match.end() > match.start() else match.start()
    if paragraph_start < len(text):
        units.extend(sentence_units(text, paragraph_start, len(text), chunk_size))
    return units


def sentence_units(text: str, start: int, end: int, chunk_size: int) -> list[tuple[int, int]]:
    if end - start <= chunk_size:
        return [(start, end)]

    units: list[tuple[int, int]] = []
    sentence_start = start
    segment = text[start:end]
    for match in SENTENCE_BOUNDARY_RE.finditer(segment):
        sentence_end = start + match.end()
        if sentence_end > sentence_start:
            units.extend(word_units(text, sentence_start, sentence_end, chunk_size))
        sentence_start = sentence_end
    if sentence_start < end:
        units.extend(word_units(text, sentence_start, end, chunk_size))
    return units


def word_units(text: str, start: int, end: int, chunk_size: int) -> list[tuple[int, int]]:
    if end - start <= chunk_size:
        return [(start, end)]

    units: list[tuple[int, int]] = []
    for match in re.finditer(r"\S+\s*", text[start:end]):
        word_start = start + match.start()
        word_end = start + match.end()
        while word_end - word_start > chunk_size:
            units.append((word_start, word_start + chunk_size))
            word_start += chunk_size
        if word_end > word_start:
            units.append((word_start, word_end))
    return units


def chunks(text: str, chunk_size: int, overlap: int) -> Iterable[tuple[int, str, int, int]]:
    if chunk_size <= overlap:
        raise ValueError("chunk_size must be greater than overlap")

    index = 0
    text = text or ""
    units = chunk_units(text, chunk_size)
    current: list[tuple[int, int]] = []

    for unit_start, unit_end in units:
        if not current:
            current.append((unit_start, unit_end))
            continue

        if unit_end - current[0][0] <= chunk_size:
            current.append((unit_start, unit_end))
            continue

        start, end = current[0][0], current[-1][1]
        content = text[start:end].strip()
        if content:
            yield index, content, start, end
            index += 1

        overlap_units: list[tuple[int, int]] = []
        for previous in reversed(current):
            overlap_units.insert(0, previous)
            if end - previous[0] >= overlap:
                break
        while overlap_units and unit_end - overlap_units[0][0] > chunk_size:
            overlap_units.pop(0)

        current = overlap_units + [(unit_start, unit_end)]

    if current:
        start, end = current[0][0], current[-1][1]
        content = text[start:end].strip()
        if content:
            yield index, content, start, end
        index += 1


def apply_schema(conn, schema_path: Path) -> None:
    with schema_path.open("r", encoding="utf-8") as file:
        sql = file.read()
    with conn.cursor() as cur:
        cur.execute(sql)
    conn.commit()


def upsert_source(cur, row: dict[str, str]) -> str:
    source_id = source_id_for(row)
    cur.execute(
        """
        INSERT INTO source_catalog (
            source_id, source_name, source_type, category, trust_level,
            collection_method, notes
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (source_id) DO UPDATE SET
            source_name = EXCLUDED.source_name,
            source_type = EXCLUDED.source_type,
            category = EXCLUDED.category,
            trust_level = EXCLUDED.trust_level,
            collection_method = EXCLUDED.collection_method,
            notes = EXCLUDED.notes,
            updated_at = now()
        """,
        (
            source_id,
            f"{row.get('source_type') or 'unknown'} / {row.get('collection_scope') or 'unknown'}",
            row.get("source_type") or "unknown",
            row.get("category") or None,
            row.get("trust_level") or None,
            row.get("collection_scope") or None,
            "mapleqa_full_handoff_with_raw_2026-05-06",
        ),
    )
    return source_id


def upsert_document(cur, row: dict[str, str], source_id: str, content: str) -> str:
    cur.execute(
        """
        INSERT INTO documents (
            doc_id, source_id, unified_id, title, category, chatbot_purpose,
            collection_scope, source_type, source_url, normalized_url,
            trust_level, language, content_format, text_length, text_preview,
            content, rag_ready, is_final_keep, published_at, collected_at
        )
        VALUES (
            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
        )
        ON CONFLICT (doc_id) DO UPDATE SET
            source_id = EXCLUDED.source_id,
            unified_id = EXCLUDED.unified_id,
            title = EXCLUDED.title,
            category = EXCLUDED.category,
            chatbot_purpose = EXCLUDED.chatbot_purpose,
            collection_scope = EXCLUDED.collection_scope,
            source_type = EXCLUDED.source_type,
            source_url = EXCLUDED.source_url,
            normalized_url = EXCLUDED.normalized_url,
            trust_level = EXCLUDED.trust_level,
            language = EXCLUDED.language,
            content_format = EXCLUDED.content_format,
            text_length = EXCLUDED.text_length,
            text_preview = EXCLUDED.text_preview,
            content = EXCLUDED.content,
            rag_ready = EXCLUDED.rag_ready,
            is_final_keep = EXCLUDED.is_final_keep,
            published_at = EXCLUDED.published_at,
            collected_at = EXCLUDED.collected_at,
            updated_at = now()
        RETURNING id
        """,
        (
            row["doc_id"],
            source_id,
            row.get("unified_id") or None,
            row.get("title") or row["doc_id"],
            row.get("category") or None,
            row.get("chatbot_purpose") or None,
            row.get("collection_scope") or None,
            row.get("source_type") or None,
            row.get("source_url") or None,
            row.get("normalized_url") or None,
            row.get("trust_level") or None,
            row.get("language") or "ko",
            row.get("content_format") or None,
            len(content),
            truncate_preview(content) or None,
            content,
            parse_bool(row.get("rag_ready")),
            parse_bool(row.get("is_final_keep")),
            parse_date(row.get("published_at")),
            parse_date(row.get("collected_at")),
        ),
    )
    return cur.fetchone()["id"]


def replace_tags(cur, document_id: str, tags: list[str]) -> None:
    cur.execute("DELETE FROM document_tags WHERE document_id = %s", (document_id,))
    for tag in tags:
        normalized = normalize_tag(tag)
        cur.execute(
            """
            INSERT INTO tags (tag_name, normalized_name)
            VALUES (%s, %s)
            ON CONFLICT (normalized_name) DO UPDATE SET
                tag_name = EXCLUDED.tag_name,
                updated_at = now()
            RETURNING id
            """,
            (tag, normalized),
        )
        tag_id = cur.fetchone()["id"]
        cur.execute(
            """
            INSERT INTO document_tags (document_id, tag_id)
            VALUES (%s, %s)
            ON CONFLICT (document_id, tag_id) DO NOTHING
            """,
            (document_id, tag_id),
        )


def replace_chunks(
    cur,
    document_id: str,
    doc_id: str,
    text: str,
    chunk_size: int,
    overlap: int,
) -> int:
    current_chunk_ids: list[str] = []
    count = 0
    for index, content, start, end in chunks(text, chunk_size, overlap):
        chunk_id = f"{doc_id}::chunk::{index}"
        current_chunk_ids.append(chunk_id)
        token_count = len(content.split())

        cur.execute(
            """
            SELECT id, content
            FROM document_chunks
            WHERE chunk_id = %s
            """,
            (chunk_id,),
        )
        existing = cur.fetchone()

        if existing:
            content_changed = existing["content"] != content
            cur.execute(
                """
                UPDATE document_chunks
                SET document_id = %s,
                    chunk_index = %s,
                    content = %s,
                    token_count = %s,
                    char_start = %s,
                    char_end = %s,
                    updated_at = now()
                WHERE chunk_id = %s
                """,
                (document_id, index, content, token_count, start, end, chunk_id),
            )
            if content_changed:
                cur.execute(
                    "DELETE FROM document_embeddings WHERE chunk_id = %s",
                    (existing["id"],),
                )
            count += 1
            continue

        cur.execute(
            """
            INSERT INTO document_chunks (
                document_id, chunk_id, chunk_index, content,
                token_count, char_start, char_end
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (
                document_id,
                chunk_id,
                index,
                content,
                token_count,
                start,
                end,
            ),
        )
        count += 1

    cur.execute(
        """
        DELETE FROM document_chunks
        WHERE document_id = %s
          AND NOT (chunk_id = ANY(%s))
        """,
        (document_id, current_chunk_ids),
    )
    return count


def remove_chunks(cur, document_id: str) -> int:
    cur.execute(
        """
        DELETE FROM document_chunks
        WHERE document_id = %s
        RETURNING id
        """,
        (document_id,),
    )
    return len(cur.fetchall())


def load_dataset(
    dataset_path: Path,
    dsn: str,
    chunk_size: int,
    overlap: int,
    apply_schema_first: bool,
    commit_every: int,
) -> tuple[int, int]:
    schema_path = Path(__file__).with_name("schema.sql")
    with psycopg2.connect(dsn, cursor_factory=RealDictCursor) as conn:
        if apply_schema_first:
            apply_schema(conn, schema_path)

        document_count = 0
        chunk_count = 0
        raise_csv_field_limit()
        with dataset_path.open("r", encoding="utf-8-sig", newline="") as file:
            reader = csv.DictReader(file)
            with conn.cursor() as cur:
                for row in reader:
                    content = clean_rag_text(row)
                    source_id = upsert_source(cur, row)
                    document_id = upsert_document(cur, row, source_id, content)
                    replace_tags(cur, document_id, parse_tags(row.get("tags")))
                    if row.get("collection_scope") in VECTOR_EXCLUDED_SCOPES:
                        removed_count = remove_chunks(cur, document_id)
                        if removed_count:
                            logger.info(
                                "removed vector chunks doc_id=%s chunks=%s",
                                row["doc_id"],
                                removed_count,
                            )
                    else:
                        chunk_count += replace_chunks(
                            cur,
                            document_id,
                            row["doc_id"],
                            content,
                            chunk_size,
                            overlap,
                        )
                    document_count += 1
                    if document_count % commit_every == 0:
                        conn.commit()
                        logger.info("loaded documents=%s chunks=%s", document_count, chunk_count)
        conn.commit()
    return document_count, chunk_count


def main() -> None:
    parser = argparse.ArgumentParser(description="Load MapleQA handoff CSV into PostgreSQL.")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--dsn", default=database_url())
    parser.add_argument("--chunk-size", type=int, default=1805)
    parser.add_argument("--overlap", type=int, default=255)
    parser.add_argument("--commit-every", type=int, default=200)
    parser.add_argument("--skip-schema", action="store_true")
    args = parser.parse_args()

    document_count, chunk_count = load_dataset(
        dataset_path=args.dataset,
        dsn=args.dsn,
        chunk_size=args.chunk_size,
        overlap=args.overlap,
        commit_every=args.commit_every,
        apply_schema_first=not args.skip_schema,
    )
    logger.info("loaded documents=%s chunks=%s", document_count, chunk_count)


if __name__ == "__main__":
    main()
