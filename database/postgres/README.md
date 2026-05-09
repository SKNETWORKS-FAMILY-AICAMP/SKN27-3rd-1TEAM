# PostgreSQL + PGVector

This folder is owned by the D task scope: PostgreSQL, PGVector, DB RAG, and RAGAS.

## Source Dataset

The PostgreSQL RAG source is:

```text
database/mapleqa_full_handoff_with_raw_2026-05-06/handoff_simplified/maple_chatbot_final_dataset.csv
```

The loader stores this CSV into:

- `source_catalog`
- `documents`
- `tags`
- `document_tags`
- `document_chunks`

`documents` keeps the full handoff CSV for traceability. `document_chunks` and
`document_embeddings` are only for DB RAG vector search.

Vector search includes document-like data:

- `official_document_collection`
- `wiki_additional_collection`
- `supplemental_recommendation_rules`
- `supplemental_recommendation_review_support`
- `supplemental_korean_story_summary`
- `supplemental_class_5th_core_priority`
- `supplemental_class_6th_hexa_priority`
- `supplemental_market_event_upgrade_timing`

Vector search excludes character/API static samples:

- `api_static_sample`

Embeddings are stored later in `document_embeddings` after an embedding pipeline is connected.

## Load

Start PostgreSQL from `database/docker-compose.yml`, then run:

```powershell
.\.venv\Scripts\python.exe database\postgres\load_mapleqa_dataset.py
```

If the schema was already applied:

```powershell
.\.venv\Scripts\python.exe database\postgres\load_mapleqa_dataset.py --skip-schema
```

The script is safe to re-run. It upserts documents and replaces chunks per document.

## Embed Chunks

After loading the CSV, create PGVector embeddings:

```powershell
.\.venv\Scripts\python.exe database\postgres\embed_document_chunks.py --provider embeddinggemma --model google/embeddinggemma-300m
```

For a quick smoke test with only one batch:

```powershell
.\.venv\Scripts\python.exe database\postgres\embed_document_chunks.py --max-batches 1
```

`google/embeddinggemma-300m` is 768 dimensions, matching `document_embeddings.embedding vector(768)`.

## Search

Use the project retriever directly:

```python
from database.postgres.embed_document_chunks import SentenceTransformerEmbeddings
from src.rag.pgvector_store import create_pgvector_store

embeddings = SentenceTransformerEmbeddings("google/embeddinggemma-300m")
store = create_pgvector_store(embeddings)

docs = store.similarity_search(
    "보스 몬스터 공격 시 데미지 옵션 알려줘",
    k=3,
    filters={"trust_level": ["S", "A"]},
)
```

The store follows the custom PGVector pattern from the course material, but uses this project's ERD tables instead of LangChain's auto-created tables.
