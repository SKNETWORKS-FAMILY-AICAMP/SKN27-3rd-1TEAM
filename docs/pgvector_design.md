# PGVector 설계 및 적재 작업 정리

## 목적

D 파트의 DB Search RAG에서 사용할 PostgreSQL + PGVector 기반 검색 저장소를 구축했다.

이 작업의 핵심 목적은 다음 세 가지다.

- RDB에는 전체 handoff CSV를 보존해서 원본 추적성을 유지한다.
- PGVector에는 답변 근거로 쓸 문서형 데이터만 임베딩해서 검색 품질을 유지한다.
- 검색 결과는 `common.state.RetrievedDocument` 형식으로 변환해서 Research Agent와 Final Answer Agent가 안정적으로 사용할 수 있게 한다.

## 현재 DB 확인 결과

2026-05-09 기준 Docker PostgreSQL 컨테이너 `maplestory-postgres`의 `mapledb`에서 확인한 값은 다음과 같다.

| 항목 | 값 |
| --- | ---: |
| `documents` | 3567 |
| `document_chunks` | 10069 |
| `document_embeddings` | 10069 |
| 미임베딩 chunk | 0 |
| embedding model | `google/embeddinggemma-300m` |
| vector dimension | 768 |

확인 SQL:

```sql
select 'documents' as name, count(*) from documents
union all
select 'document_chunks', count(*) from document_chunks
union all
select 'document_embeddings', count(*) from document_embeddings;

select embedding_model, count(*)
from document_embeddings
group by embedding_model
order by embedding_model;

select min(vector_dims(embedding)) as min_dim,
       max(vector_dims(embedding)) as max_dim
from document_embeddings;
```

## 사용 데이터

- 원본 CSV: `database/mapleqa_full_handoff_with_raw_2026-05-06/handoff_simplified/maple_chatbot_final_dataset.csv`
- 전체 문서 수: 3567
- PGVector chunk 수: 10069
- PGVector embedding 수: 10069

## PGVector 포함 범위

아래 데이터만 `document_chunks`, `document_embeddings`에 적재했다.

| collection_scope | 설명 | chunk 수 |
| --- | --- | ---: |
| `official_document_collection` | 공식 공지, 이벤트, 업데이트, 테스트월드 문서 | 369 |
| `wiki_additional_collection` | 위키형 보조 문서 | 9362 |
| `supplemental_recommendation_rules` | 정제된 추천/룰 문서 | 197 |
| `supplemental_class_6th_hexa_priority` | 6차 HEXA 우선순위 룰 | 47 |
| `supplemental_class_5th_core_priority` | 5차 코어 우선순위 룰 | 47 |
| `supplemental_recommendation_review_support` | 추천 검토 보조 문서 | 27 |
| `supplemental_korean_story_summary` | 한국어 스토리 요약 문서 | 12 |
| `supplemental_market_event_upgrade_timing` | 이벤트/시장/업그레이드 타이밍 문서 | 8 |

`official_document_collection` 내부 분포는 다음과 같다.

| category | chunk 수 |
| --- | ---: |
| `testworld_update` | 163 |
| `official_update` | 150 |
| `official_event` | 45 |
| `official_notice` | 11 |

## PGVector 제외 범위

아래 데이터는 벡터 검색 대상에서 제외했다.

- 캐릭터/API 샘플 데이터
- `collection_scope = 'api_static_sample'`

단, 원본 추적을 위해 `documents` 테이블에는 전체 CSV row를 유지한다.

## 왜 이렇게 설계했는가

### RDB에는 전체 CSV를 저장하고 PGVector에는 일부만 넣은 이유

`documents`는 원본 추적과 데이터 감사 용도다. 어떤 row가 들어왔는지, 출처와 URL이 무엇인지, 어떤 collection에서 온 데이터인지 확인할 수 있어야 한다.

반면 `document_chunks`와 `document_embeddings`는 DB Search RAG의 검색 대상이다. 캐릭터/API 샘플처럼 답변 근거 문서가 아닌 데이터까지 임베딩하면 검색 결과에 raw payload나 특정 캐릭터 예시가 섞일 수 있다. 그래서 RDB에는 전체를 보존하고, PGVector에는 공식 문서, 위키형 문서, 정제 룰 문서만 넣었다.

### `api_static_sample`을 제외한 이유

`api_static_sample`은 캐릭터 상태 분석, Calculator, Analystic Agent 쪽 입력에 더 가깝다. DB Search RAG는 Final Answer에 들어갈 근거 문서를 찾는 역할이므로, 특정 캐릭터 샘플 데이터가 검색 결과에 섞이면 답변 근거의 성격이 흐려진다.

따라서 캐릭터 데이터는 RDB 추적 대상으로만 유지하고, 벡터 검색 대상에서는 제외했다.

### 테이블을 `documents -> document_chunks -> document_embeddings`로 분리한 이유

세 테이블의 책임을 분리하면 재적재와 재임베딩을 독립적으로 처리할 수 있다.

| 테이블 | 책임 |
| --- | --- |
| `documents` | 원본 문서, 출처, URL, 신뢰도, collection metadata 보존 |
| `document_chunks` | RAG 검색 단위로 자른 chunk 저장 |
| `document_embeddings` | chunk별 embedding vector와 embedding model 저장 |

이 구조 덕분에 문서 metadata가 바뀌어도 chunk와 embedding을 분리해서 관리할 수 있고, embedding model을 바꿀 때도 원본 문서를 다시 적재하지 않고 재임베딩 전략을 세울 수 있다.

### chunk를 삭제 후 재삽입하지 않고 upsert 방식으로 둔 이유

초기 구조에서 chunk를 전부 삭제한 뒤 다시 넣으면 `document_embeddings.chunk_id`의 `ON DELETE CASCADE` 때문에 이미 만든 embedding이 모두 삭제될 수 있다.

현재 `database/postgres/load_mapleqa_dataset.py`는 `chunk_id` 기준으로 기존 chunk를 확인하고, content가 바뀐 경우에만 해당 embedding을 삭제한다. content가 그대로면 기존 embedding을 보존한다.

이렇게 한 이유는 다음과 같다.

- CSV loader를 여러 번 실행해도 불필요한 재임베딩을 막는다.
- 중간에 적재가 끊겨도 이어서 작업하기 쉽다.
- PGVector embedding 생성 시간이 길기 때문에 이미 만든 벡터를 최대한 보존한다.

### `google/embeddinggemma-300m`을 사용한 이유

처음에는 OpenAI embedding도 고려할 수 있었지만, 현재 작업에서는 API 없이 실행 가능한 로컬/Hugging Face embedding이 필요했다.

그래서 `google/embeddinggemma-300m`을 사용했다.

| 항목 | 값 |
| --- | --- |
| provider | `embeddinggemma` |
| model | `google/embeddinggemma-300m` |
| dimension | 768 |
| DB column | `document_embeddings.embedding vector(768)` |

이 모델을 사용했기 때문에 schema의 vector 차원도 `vector(768)`로 맞췄다. 만약 팀에서 `common.get_model.get_embedding_model()`의 OpenAI embedding을 표준으로 쓰기로 합의하면, embedding dimension과 저장된 vector를 함께 재검토해야 한다.

### `common/`을 직접 수정하지 않은 이유

`common/` 폴더는 팀 공용 규칙이다. 함수명, 변수명, 입출력 contract가 바뀌면 다른 파트 코드에 영향을 줄 수 있다.

따라서 PGVector 적재 스크립트에서는 필요한 provider를 선택할 수 있게 하되, `common/`의 함수나 state 정의는 수정하지 않았다. 검색 결과만 `common.state.RetrievedDocument` 형식에 맞춰 변환한다.

### metadata에 출처 정보를 넣은 이유

Final Answer Agent가 답변에 근거를 붙이려면 검색 결과가 단순 text만 반환하면 부족하다.

현재 검색 결과 metadata에는 다음 값을 담는다.

| metadata | 이유 |
| --- | --- |
| `chunk_id` | 중복 제거와 디버깅용 |
| `doc_id` 또는 `document_id` | 원본 문서 추적용 |
| `title` | 최종 답변 출처 표시용 |
| `category` | 공지/이벤트/업데이트 등 필터링용 |
| `collection_scope` | 공식/위키/룰 문서 구분용 |
| `source_url` | citation과 원문 확인용 |
| `trust_level` 또는 `reliability` | 신뢰도 기반 필터링용 |
| `retrieval_method` | keyword/vector/hybrid 결과 분석용 |

`chunk_index`와 `embedding_model`은 사용자 답변에 직접 노출할 값은 아니지만, 검색 디버깅과 재임베딩 확인에는 유용하다. 최종 답변 단계에서는 필요하면 숨겨도 된다.

### HNSW index를 둔 이유

`document_embeddings.embedding`에는 HNSW index를 적용했다.

```sql
create index if not exists idx_document_embeddings_vector
    on document_embeddings using hnsw (embedding vector_cosine_ops);
```

PGVector 검색은 cosine distance 기반으로 동작한다. chunk 수가 늘어날수록 순차 검색 비용이 커지므로, 유사도 검색 성능을 위해 vector index를 둔다.

## 임베딩 모델

- 모델: `google/embeddinggemma-300m`
- provider: `embeddinggemma`
- 벡터 차원: 768
- DB 컬럼: `document_embeddings.embedding vector(768)`
- OpenAI API는 사용하지 않는다.
- Hugging Face gated model이므로 최초 실행 환경에는 `HF_TOKEN`이 필요하다.

## 관련 파일

| 파일 | 역할 |
| --- | --- |
| `database/postgres/schema.sql` | PostgreSQL/PGVector 테이블 및 인덱스 정의 |
| `database/postgres/load_mapleqa_dataset.py` | CSV를 RDB 문서/청크 테이블에 적재 |
| `database/postgres/embed_document_chunks.py` | chunk를 임베딩하여 `document_embeddings`에 적재 |
| `src/rag/pgvector_store.py` | PGVector similarity/keyword/hybrid 검색 및 `RetrievedDocument` 변환 |
| `src/rag/db_search.py` | DB Search RAG wrapper, hybrid fusion, common state adapter |
| `src/evaluation/ragas_eval.py` | RAGAS 평가용 유틸 |

## 실행 순서

### 1. PostgreSQL 실행

```powershell
docker compose -f database\docker-compose.yml up -d postgres
```

### 2. CSV 적재

```powershell
.\.venv\Scripts\python.exe database\postgres\load_mapleqa_dataset.py
```

이미 schema가 적용되어 있고 데이터만 다시 맞출 때는 다음처럼 실행할 수 있다.

```powershell
.\.venv\Scripts\python.exe database\postgres\load_mapleqa_dataset.py --skip-schema
```

### 3. PGVector 임베딩 적재

```powershell
.\.venv\Scripts\python.exe database\postgres\embed_document_chunks.py --provider embeddinggemma --model google/embeddinggemma-300m --batch-size 64
```

스크립트는 이미 같은 모델로 적재된 chunk를 건너뛴다. 중간에 중단되어도 같은 명령을 다시 실행하면 남은 chunk부터 이어서 적재된다.

## 검색 테스트

전체 적재 후 `이벤트 보상` 질의로 PGVector 검색을 확인했다.

예시 결과:

```text
official_document_collection | 클라이언트 1.2.198 릴리즈 | 0.5480 | https://maplestory.nexon.com/testworld/news/update/156?p=1
official_document_collection | 수정 클라이언트 1.2.413 업데이트 안내 (이벤트) | 0.5439 | https://maplestory.nexon.com/news/update/798?p=1
official_document_collection | 수정 클라이언트 1.2.414 업데이트 안내 (이벤트, 컨텐츠, 개선사항 및 오류 수정) | 0.5359 | https://maplestory.nexon.com/news/update/802?p=1
```

## 공유 시 권장 사항

팀원에게 빠르게 동일한 DB 상태를 전달하려면 DB dump를 공유하는 것이 좋다. CSV와 스크립트만 공유하면 임베딩을 다시 생성해야 해서 시간이 오래 걸린다.

PGVector 데이터 용량이 커서 GitHub에는 올리지 않았고, 추후 수정이나 관리가 더 편하도록 dump 파일은 별도로 Google Drive에 공유한다.

**dump 파일 Google Drive 공유 링크: [mapledb_pgvector.dump](https://drive.google.com/file/d/1CffatAn-UpNGx6-eLe-G6563yOqMRCuL/view?usp=drive_link&utm_source=chatgpt.com)**

현재 공유 기준:

| 항목 | 내용 |
| --- | --- |
| 브랜치 | `feature-postgre` |
| 커밋 | `323d165 feat: add postgres pgvector rag pipeline` |
| GitHub 제외 파일 | `data/raw_files.csv` |
| DB dump 파일 | `database/postgres/mapledb_pgvector.dump` |

`data/raw_files.csv`는 GitHub 용량 제한 문제로 히스토리에서 제거했다. `mapledb_pgvector.dump` 파일은 Git에는 포함하지 않고 로컬에서만 생성했으며, 팀원 공유는 Google Drive 링크를 사용한다.

권장 공유 방식:

| 공유 대상 | 방식 |
| --- | --- |
| 코드, schema, 문서 | GitHub |
| 적재 완료된 DB 데이터 | `mapledb_pgvector.dump` 별도 공유 |
| 원본 raw/handoff dataset | GitHub 제외 권장 |
| dump 파일 | GitHub 제외 권장 |

덤프 생성 예시:

```powershell
docker exec maplestory-postgres pg_dump -U admin -d mapledb -Fc -f /tmp/mapledb_pgvector.dump
docker cp maplestory-postgres:/tmp/mapledb_pgvector.dump .\database\postgres\mapledb_pgvector.dump
```

복원 예시:

```powershell
docker compose -f database\docker-compose.yml up -d postgres
docker cp .\database\postgres\mapledb_pgvector.dump maplestory-postgres:/tmp/mapledb_pgvector.dump
docker exec maplestory-postgres pg_restore -U admin -d mapledb --clean --if-exists /tmp/mapledb_pgvector.dump
```

## 수정 또는 확인이 필요한 부분

### 1. README의 chunk 재적재 설명 보완

`database/postgres/README.md`에는 "replaces chunks per document"라고 적혀 있다. 실제 구현은 단순 전체 교체가 아니라 `chunk_id` 기준 upsert에 가깝고, content가 바뀐 chunk의 embedding만 삭제한다.

문서 정확도를 위해 README에는 다음처럼 바꾸는 것이 좋다.

```text
The script is safe to re-run. It upserts documents and chunks by stable IDs,
and only removes embeddings when chunk content changes.
```

### 2. `pgvector_store.py`와 `db_search.py`의 역할 구분 명확화

현재 `src/rag/pgvector_store.py`도 `hybrid_retrieve()`를 제공하고, `src/rag/db_search.py`도 hybrid fusion을 제공한다.

실제 AgentState 연동, score normalization, weighted fusion은 `db_search.py` 쪽이 더 완성된 흐름이다. 팀원이 사용할 기본 진입점은 다음처럼 정하는 것이 좋다.

```text
Agent/LangGraph 연동: src.rag.db_search.db_search_rag_node
직접 DB 검색 테스트: src.rag.db_search.run_db_search_rag
저수준 PGVector wrapper: src.rag.pgvector_store.MaplePGVectorStore
```

### 3. metadata key 이름 통일

`pgvector_store.py`는 `trust_level`, `doc_id`를 사용하고, `db_search.py`는 `reliability`, `document_id`를 사용한다.

둘 다 의미는 통하지만 Final Answer Agent가 출처를 표시할 때 key가 갈리면 adapter 코드가 늘어날 수 있다. 팀 최종 규칙에 맞춰 아래 중 하나로 통일하는 것이 좋다.

```text
권장: source_url, title, trust_level, doc_id, retrieval_method
```

당장 기능 장애는 아니지만, final answer citation 규칙이 정해지면 정리하는 편이 좋다.

### 4. embedding provider 정책 합의

현재 DB에는 `google/embeddinggemma-300m`으로 만든 768차원 벡터가 들어 있다. 반면 `common.get_model.get_embedding_model()`은 OpenAI embedding을 반환한다.

이번 작업에서는 API 없이 실행하기 위해 로컬 embedding을 사용했고, `common/`은 수정하지 않았다. 다만 팀 전체가 하나의 embedding provider를 표준으로 정한다면 다음 중 하나를 선택해야 한다.

| 선택지 | 영향 |
| --- | --- |
| 현재 유지 | API 없이 PGVector 재현 가능, `vector(768)` 유지 |
| OpenAI 공통 모델로 통일 | `common/`과 맞지만 재임베딩 및 vector dimension 변경 가능성 있음 |

### 5. Git 공유 정책 확인

PGVector dump와 원본 dataset은 용량이 크고 변경 이력이 의미 있게 관리되기 어렵다.

권장 정책:

```text
GitHub: 코드, schema, migration, docs
별도 공유: mapledb_pgvector.dump
Git 제외: database/postgres/*.dump, 원본 handoff/raw dataset, __pycache__
```

현재 팀 저장소에 원본 데이터나 dump가 들어가지 않도록 `.gitignore`와 commit 내역을 확인하는 것이 좋다.
