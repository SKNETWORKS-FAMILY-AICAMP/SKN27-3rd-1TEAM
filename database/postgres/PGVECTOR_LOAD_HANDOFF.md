# PGVector 적재 작업 정리

## 목적

D 파트의 DB RAG에서 사용할 PostgreSQL + PGVector 검색 기반을 구축했다.
RDB에는 전체 handoff CSV를 보존하고, PGVector에는 캐릭터/API 샘플 데이터를 제외한 문서형 RAG 대상만 임베딩했다.

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
| `src/rag/pgvector_store.py` | PGVector similarity/hybrid 검색 및 `RetrievedDocument` 변환 |
| `src/rag/db_search.py` | DB 검색 wrapper 및 common state adapter |
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

스크립트는 이미 같은 모델로 적재된 chunk를 건너뛴다.
중간에 중단되어도 같은 명령을 다시 실행하면 남은 chunk부터 이어서 적재된다.

## 최종 검증 결과

최종 적재 후 확인한 값은 다음과 같다.

```text
document_chunks: 10069
document_embeddings: 10069
remaining: 0
embedding_model: google/embeddinggemma-300m
vector dimension: 768
```

검증 SQL:

```sql
select count(*) as chunks from document_chunks;
select count(*) as embeddings from document_embeddings;
select count(*) - (select count(*) from document_embeddings) as remaining from document_chunks;
select embedding_model, count(*) from document_embeddings group by embedding_model order by embedding_model;
select min(vector_dims(embedding)) as min_dim, max(vector_dims(embedding)) as max_dim from document_embeddings;
```

## 검색 테스트

전체 적재 후 `이벤트 보상` 질의로 PGVector 검색을 확인했다.

예시 결과:

```text
official_document_collection | 클라이언트 1.2.198 릴리즈 | 0.5480 | https://maplestory.nexon.com/testworld/news/update/156?p=1
official_document_collection | 수정 클라이언트 1.2.413 업데이트 안내 (이벤트) | 0.5439 | https://maplestory.nexon.com/news/update/798?p=1
official_document_collection | 수정 클라이언트 1.2.414 업데이트 안내 (이벤트, 컨텐츠, 개선사항 및 오류 수정) | 0.5359 | https://maplestory.nexon.com/news/update/802?p=1
```

## 공유 시 권장 사항

팀원에게 빠르게 동일한 DB 상태를 전달하려면 DB dump를 공유하는 것이 좋다.
CSV와 스크립트만 공유하면 임베딩을 다시 생성해야 해서 시간이 오래 걸린다.

덤프 생성 예시:

```powershell
docker exec maplestory-postgres pg_dump -U admin -d mapledb -Fc -f /tmp/mapledb_pgvector.dump
docker cp maplestory-postgres:/tmp/mapledb_pgvector.dump .\database\postgres\mapledb_pgvector.dump
```

복원 예시:

```powershell
docker cp .\database\postgres\mapledb_pgvector.dump maplestory-postgres:/tmp/mapledb_pgvector.dump
docker exec maplestory-postgres pg_restore -U admin -d mapledb --clean --if-exists /tmp/mapledb_pgvector.dump
```
