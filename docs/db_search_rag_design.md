# DB Search RAG 설계 및 작업 정리

## 목적

DB Search RAG는 프로젝트 내부 PostgreSQL/PGVector와 Neo4j GraphDB에 적재된 데이터를 검색하여 Research Agent와 Final Answer Agent가 사용할 근거 문맥을 제공하는 모듈이다.

이 모듈은 답변을 직접 생성하지 않는다. 역할은 다음 두 값을 안정적으로 만드는 것이다.

- `common.state.AgentState["retrieved_docs"]`
- `common.state.AgentState["context"]`

## 담당 범위

D 파트 기준 담당 범위는 다음과 같다.

- PostgreSQL RDB
- PGVector
- Neo4j GraphDB 검색 연동
- DB Search RAG
- RAGAS 평가 유틸
- ERD 문서

DB Search RAG는 `src/rag/db_search.py`와 `src/rag/retriever.py`를 중심으로 구현되어 있다. PGVector/keyword 검색과 Neo4j GraphDB 검색은 `src/rag/retriever.py`가 담당하고, `src/rag/db_search.py`는 검색 결과를 AgentState의 `retrieved_docs`, `context`로 연결한다.

## 설계 근거

### DB Search RAG를 답변 생성기가 아니라 근거 검색기로 둔 이유

프로젝트의 공통 state 계약은 Research Agent와 Final Answer Agent의 역할을 분리한다.

`common/state.py` 기준으로 Research Agent는 다음 값을 출력해야 한다.

```python
retrieved_docs: list[RetrievedDocument]
context: str
```

반면 최종 답변은 Final Answer Agent의 출력이다.

```python
draft_answer: str
final_answer: str
```

따라서 DB Search RAG가 자연어 답변까지 생성하면 공통 AgentState 책임 경계가 흐려진다. DB Search RAG는 검색 결과와 근거 문맥만 만들고, 최종 문장 생성은 Final Answer Agent가 담당하는 구조가 팀 규칙에 더 맞다.

### PGVector와 GraphDB의 역할을 분리한 이유

역할을 분리한 가장 큰 이유는 저장소 기술 차이보다 데이터의 성격이 다르기 때문이다.

PGVector는 긴 문서에서 질문과 의미가 가까운 근거 문단을 찾는 데 강하다. 공식 공지, 이벤트 안내, 업데이트 내역, 위키형 문서, 정제 룰 문서는 자연어 설명이 길고 표현이 다양하다. 이런 데이터는 키워드가 정확히 일치하지 않아도 의미 기반으로 찾아야 하므로 PGVector 검색 대상이 된다.

GraphDB는 엔티티 간 관계를 정확히 따라가는 데 강하다. 보스가 어떤 요구 스펙을 갖는지, 어떤 보상을 드롭하는지, 직업이 어떤 주스탯을 쓰는지, 장비가 어떤 세트 효과에 포함되는지는 문서 유사도보다 관계 조회가 더 정확하다. 이런 데이터는 `MATCH (Boss)-[:HAS_REQUIREMENT]->(StatRequirement)`처럼 구조화된 관계로 찾는 편이 답변 근거가 흔들리지 않는다.

| 구분 | PGVector / PostgreSQL | Neo4j GraphDB |
| --- | --- | --- |
| 핵심 역할 | 문서 근거 검색 | 관계/사실 검색 |
| 데이터 형태 | 긴 자연어 문서, chunk, 출처 metadata | 엔티티 노드와 관계 |
| 강한 질문 | 이벤트 내용, 업데이트 변경점, 설명형 룰 | 보스 요구 스펙, 직업 주스탯, 장비 세트, 이벤트-보상 관계 |
| 검색 방식 | keyword + vector similarity | Cypher 관계 조회 |
| 반환 목적 | 답변에 인용할 문서 문맥 | 답변에 넣을 구조화된 사실 |
| 약점 | 관계를 정확히 계산하거나 따라가기 어려움 | 긴 문서의 의미 유사도 검색에는 약함 |

따라서 이 구조는 하이브리드 RAG가 맞다. 다만 단순히 "하이브리드라서 DB를 두 개 쓴 것"이 아니라, 하나의 질문에 필요한 근거가 문서형 근거와 관계형 근거로 나뉘기 때문에 저장소를 분리했다.

```text
문서형 근거가 필요한 질문
  -> PostgreSQL/PGVector 검색

관계형 사실이 필요한 질문
  -> Neo4j GraphDB 검색

최종 DB Search RAG context
  -> PGVector 결과 + GraphDB 결과를 RetrievedDocument 형식으로 통합
```

### PostgreSQL/PGVector를 사용한 이유

D 파트의 담당 범위가 PostgreSQL, PGVector, DB RAG, RAGAS로 정의되어 있다. 또한 ERD에 이미 RAG 문서 흐름이 다음처럼 분리되어 있다.

```text
documents
  -> document_chunks
  -> document_embeddings
```

이 구조는 원본 문서, 검색 단위 chunk, embedding을 분리해서 관리하기 좋다. 문서 metadata는 `documents`에 유지하고, 검색 단위는 `document_chunks`, 벡터는 `document_embeddings`에 두면 재적재와 재임베딩을 독립적으로 처리할 수 있다.

### 캐릭터/API 샘플 데이터를 제외한 이유

캐릭터/API 샘플 데이터는 특정 캐릭터 상태 분석이나 Calculator/Analystic Agent의 입력에 가깝다. 반면 DB Search RAG는 Final Answer의 근거가 되는 공식 문서, 위키형 문서, 정제 룰 문서를 찾는 역할이다.

그래서 `api_static_sample`을 벡터 검색 대상에서 제외했다. 이렇게 해야 검색 결과에 특정 캐릭터 raw API payload가 섞여 들어와 답변 근거가 흐려지는 문제를 줄일 수 있다.

### Hybrid 검색을 기본 방향으로 잡은 이유

참고 노트북의 Hybrid RAG 핵심은 여러 검색 방식을 결합하고, 결과를 정규화한 뒤 재순위화하는 것이다.

DB Search RAG에서도 같은 이유로 keyword 검색과 vector 검색을 함께 사용한다.

| 검색 방식 | 장점 | 약점 |
| --- | --- | --- |
| Keyword/Text Search | 정확한 용어, 이벤트명, 스킬명, 패치 버전 검색에 강함 | 표현이 달라지면 놓칠 수 있음 |
| Vector Search | 의미가 비슷한 문서 검색에 강함 | 고유명사, 버전명, 짧은 키워드에는 약할 수 있음 |

메이플스토리 질의는 고유명사와 의미 질의가 섞인다.

예시:

```text
하이퍼 버닝 보상
6차 HEXA 강화 우선순위
보스 방무 기준
테스트월드 이벤트 변경점
```

이런 질문은 keyword와 vector 중 하나만 쓰기보다 둘을 함께 쓰는 편이 안정적이다.

### score normalization을 적용한 이유

PGVector 유사도 점수와 PostgreSQL text search 점수는 계산 방식과 범위가 다르다.

- vector score: cosine distance를 `1 - distance`로 변환한 값
- text score: `ts_rank_cd`, `ILIKE`, token match 보정이 합쳐진 값

두 점수를 그대로 더하면 한쪽 검색 방식이 과도하게 유리해질 수 있다. 그래서 각 검색 결과 목록 안에서 점수를 `0~1`로 정규화한 뒤 가중치를 적용한다.

```text
normalized vector score * 0.65
+ normalized text score * 0.35
```

이 방식은 참고 노트북의 “정규화된 점수 기반 통합 및 재순위화” 흐름을 PostgreSQL/PGVector 구조에 맞게 적용한 것이다.

### candidate multiplier를 둔 이유

최종 `top_k`만큼만 vector/text 결과를 가져오면, 한 검색 방식에서 아슬아슬하게 밀린 좋은 후보가 재순위화 단계에 들어오지 못한다.

그래서 현재는 최종 `top_k`보다 넓게 후보를 가져온다.

```python
candidate_k = top_k * DEFAULT_CANDIDATE_MULTIPLIER
```

예를 들어 `top_k=5`이면 vector/text 각각 최대 15개를 가져와 통합한 뒤 최종 5개를 선택한다.

### GraphDB 검색을 DB Search RAG에 포함한 이유

참고 노트북은 Graph Search와 Vector Search를 결합하는 GraphRAG 구조를 다룬다. 팀 프로젝트의 DB Search RAG 범위에도 GraphDB가 포함되는 것으로 정리되었기 때문에, DB Search RAG는 PostgreSQL/PGVector 검색과 Neo4j GraphDB 검색을 함께 사용할 수 있어야 한다.

GraphDB는 문서 유사도 검색을 대체하는 저장소가 아니라 PGVector가 약한 부분을 보강하는 저장소다. 예를 들어 "노멀 스우 요구 스펙과 보상" 질문은 문서에서도 찾을 수 있지만, GraphDB에서는 보스 노드에서 요구 스펙과 보상 노드로 직접 이동할 수 있어 더 안정적이다.

| 질문 유형 | PGVector/Keyword | GraphDB |
| --- | --- | --- |
| 이벤트 보상, 업데이트 내용 | 공식 문서 chunk 검색 | 이벤트-보상-콘텐츠 관계 보강 |
| 보스 요구 스펙 | 룰/위키 문서 검색 | 보스-요구스탯 관계 조회 |
| 직업 주스탯 | 문서 근거 검색 | 직업-스탯 관계 조회 |
| 장비 세트 | 문서 근거 검색 | 장비-세트효과 관계 조회 |
| 5차/6차 강화 우선순위 | 정제 룰 문서 검색 | 직업-출처 문서 관계 보강 |

따라서 DB Search RAG는 기본적으로 문서 검색을 수행하고, `include_graph=True` 옵션을 켜면 GraphDB 결과까지 같은 `RetrievedDocument` 구조로 합친다. 이렇게 하면 Neo4j가 준비되지 않은 환경에서도 기존 PGVector RAG는 그대로 동작하고, 통합 환경에서는 Graph 결과를 함께 평가할 수 있다.

### 하이브리드 RAG를 두 단계로 나눈 이유

현재 DB Search RAG의 하이브리드는 두 층으로 나뉜다.

| 단계 | 결합 대상 | 이유 |
| --- | --- | --- |
| 1단계 | keyword search + vector search | 문서 검색 안에서 정확한 용어와 의미 유사도를 함께 잡기 위해 |
| 2단계 | PostgreSQL/PGVector + Neo4j GraphDB | 문서 근거와 관계형 사실을 함께 제공하기 위해 |

이렇게 나누면 검색 실패 원인을 분리해서 볼 수 있다. 이벤트 공지가 안 잡히면 PGVector/keyword 검색을 튜닝하고, 보스 요구 스펙이나 장비 세트 관계가 부족하면 GraphDB seed 데이터를 보강하면 된다.

## 사용 데이터

### 현재 DB 적재 현황

2026-05-12 기준 Docker PostgreSQL 컨테이너 `maplestory-postgres`의 `mapledb`에서 확인한 값은 다음과 같다.

| 항목 | 값 |
| --- | ---: |
| `documents` | 3567 |
| `document_chunks` | 10025 |
| `document_embeddings` | 10025 |
| `wiki_entities` | 1328 |
| 미임베딩 chunk | 0 |
| embedding model | `google/embeddinggemma-300m` |
| vector dimension | 768 |

확인 SQL:

```sql
select 'documents' as name, count(*) from documents
union all
select 'document_chunks', count(*) from document_chunks
union all
select 'document_embeddings', count(*) from document_embeddings
union all
select 'wiki_entities', count(*) from wiki_entities;

select embedding_model, count(*)
from document_embeddings
group by embedding_model
order by embedding_model;

select min(vector_dims(embedding)) as min_dim,
       max(vector_dims(embedding)) as max_dim
from document_embeddings;
```

원본 CSV는 다음 파일을 사용했다.

```text
database/mapleqa_full_handoff_with_raw_2026-05-06/handoff_simplified/maple_chatbot_final_dataset.csv
```

PGVector 검색 대상은 다음 문서형 데이터로 제한한다.

| 범위 | 설명 |
| --- | --- |
| 공식 공지 | 메이플스토리 공식 공지 |
| 공식 이벤트 | 공식 이벤트 안내 |
| 공식 업데이트 | 공식 업데이트 내역 |
| 테스트월드 업데이트 | 테스트월드 공지/업데이트 |
| 위키형 보조 문서 | 게임 지식 보조 문서 |
| 정제 룰 문서 | 추천, 강화 우선순위, 성장 판단 룰 |

캐릭터/API 샘플 데이터는 벡터 검색 대상에서 제외한다.

```text
excluded collection_scope:
- api_static_sample
```

### PGVector 포함 범위 상세

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

원본 추적을 위해 `documents` 테이블에는 전체 CSV row를 유지하지만, 검색 품질을 위해 PGVector에는 답변 근거로 사용할 문서형 데이터만 임베딩했다.

### wiki_entities 1차 색인

`wiki_entities`는 PGVector 검색용 임베딩이 아니라 위키 문서에서 보스, 몬스터, 아이템, 스킬, 퀘스트, 맵 같은 게임 엔티티를 구조적으로 찾기 위한 색인 테이블이다.

위키 문서 1,338건 중 제목과 본문 패턴으로 타입을 추정할 수 있는 1,328건을 적재했다. 타입이 애매한 10건은 잘못된 엔티티 색인을 피하기 위해 제외했다.

| entity_type | count |
| --- | ---: |
| `map` | 747 |
| `boss` | 359 |
| `item` | 156 |
| `monster` | 39 |
| `skill` | 14 |
| `quest` | 13 |

재현 SQL은 다음 파일에 둔다.

```text
database/postgres/load_wiki_entities.sql
```

## 관련 테이블

DB Search RAG는 다음 테이블을 사용한다.

| 테이블 | 역할 |
| --- | --- |
| `source_catalog` | 문서 출처 카탈로그 |
| `documents` | RAG 원본 문서 |
| `document_chunks` | 문서 검색 단위 chunk |
| `document_embeddings` | PGVector embedding |
| `tags` | 문서 태그 |
| `document_tags` | 문서-태그 연결 |
| `wiki_entities` | 위키 문서에서 1차 추출한 게임 엔티티 색인 |

현재 검색의 핵심 조인은 다음 구조다.

```text
document_embeddings
  -> document_chunks
  -> documents
```

Neo4j GraphDB 검색은 다음 노드/관계를 사용한다.

| Graph 요소 | 역할 |
| --- | --- |
| `Job` | 직업과 주스탯 검색 |
| `Boss` | 보스와 요구 스펙 검색 |
| `StatRequirement` | 보스/콘텐츠 요구 스탯 |
| `EquipmentCatalog` | 장비 카탈로그 |
| `SetEffect` | 장비 세트 효과 |
| `Event` | 이벤트 정보 |
| `Reward` | 보상 정보 |
| `Content` | 성장/일일/주간 콘텐츠 |
| `Source` | Graph entity가 언급된 문서 출처 |
| `MENTIONED_IN` | Graph entity와 Source 연결 |

## 임베딩 모델

현재 적재된 PGVector 임베딩은 다음 모델을 사용한다.

```text
model: google/embeddinggemma-300m
dimension: 768
provider: embeddinggemma
```

따라서 `document_embeddings.embedding`은 `vector(768)`이다.

`document_embeddings.embedding`에는 HNSW index를 적용했다.

```sql
create index if not exists idx_document_embeddings_vector
    on document_embeddings using hnsw (embedding vector_cosine_ops);
```

PGVector 검색은 cosine distance 기반으로 동작한다. chunk 수가 늘어날수록 순차 검색 비용이 커지므로, 유사도 검색 성능을 위해 vector index를 둔다.

## 파일 구성

| 파일 | 역할 |
| --- | --- |
| `src/rag/db_search.py` | DB Search RAG 실행 wrapper, AgentState adapter |
| `src/rag/retriever.py` | PGVector/keyword/hybrid 검색, Neo4j GraphDB 검색, `RetrievedDocument` 변환 |
| `src/evaluation/ragas_eval.py` | RAGAS 평가 유틸 |
| `database/postgres/schema.sql` | PostgreSQL + PGVector schema |
| `database/postgres/load_mapleqa_dataset.py` | CSV -> RDB/chunk 적재 |
| `database/postgres/embed_document_chunks.py` | chunk -> embedding 적재 |
| `database/postgres/load_wiki_entities.sql` | wiki 문서 -> 엔티티 1차 색인 적재 |

## 검색 모드

`src/rag/retriever.py`의 `PGVectorDBRetriever`는 다음 검색 모드를 지원한다. `src/rag/db_search.py`는 이 검색기를 호출해 RAG 흐름과 AgentState에 연결한다.

| mode | 설명 |
| --- | --- |
| `text` | PostgreSQL full-text + `ILIKE` 기반 키워드 검색, `wiki_entities` 엔티티 색인 검색 |
| `vector` | PGVector cosine distance 기반 의미 검색 |
| `hybrid` | vector 검색과 keyword 검색 결과를 통합 |
| `auto` | query embedding이 있으면 hybrid, 없으면 text 검색 |

기본 권장 모드는 `hybrid`다.

GraphDB 검색은 mode가 아니라 `include_graph` 옵션으로 켠다.

| 옵션 | 설명 |
| --- | --- |
| `include_graph=False` | PostgreSQL/PGVector 기반 DB Search RAG만 실행 |
| `include_graph=True` | PostgreSQL/PGVector 결과와 Neo4j GraphDB 결과를 함께 반환 |

## Hybrid RAG 적용 방식

참고 자료:

```text
C:\dev\course\course_LLM\5. RAG\1. colab\4. KAG(GraphRAG)\2. GraphRAG\2. kag_with_neoj4\4. Hybrid RAG.ipynb
```

참고 노트북의 핵심 아이디어는 다음과 같다.

- 여러 검색 방식을 함께 사용한다.
- 각 검색 결과의 점수를 정규화한다.
- 정규화된 점수를 기준으로 결과를 통합하고 재순위화한다.
- 이후 Agent나 LLM이 사용할 수 있는 문맥으로 변환한다.

프로젝트에는 다음 범위를 적용했다.

```text
Vector Search + Keyword Search
  -> score normalization
  -> weighted fusion
  -> wiki_entities entity search
  -> rerank
  -> optional GraphDB Search
  -> DB result + Graph result merge
  -> RetrievedDocument/context 반환
```

## Hybrid 검색 흐름

```text
사용자 질문
  -> query embedding 생성
  -> PGVector vector search
  -> PostgreSQL text/keyword search
  -> 필요 시 Neo4j graph search
  -> 각 검색 결과 score를 0~1로 정규화
  -> vector/text 가중치 적용
  -> DB result와 graph result 통합
  -> chunk_id/graph_id 기준 중복 제거
  -> 최종 top_k 재정렬
  -> RetrievedDocument + context 생성
```

현재 기본 가중치는 다음과 같다.

```python
DEFAULT_VECTOR_WEIGHT = 0.65
DEFAULT_TEXT_WEIGHT = 0.35
DEFAULT_CANDIDATE_MULTIPLIER = 3
```

`DEFAULT_CANDIDATE_MULTIPLIER`는 최종 `top_k`보다 더 많은 후보를 먼저 가져와 재순위화하기 위한 값이다.

예를 들어 `top_k=5`이면 vector/text 각각 최대 15개 후보를 가져온 뒤 최종 5개로 줄인다.

## 결과 구조

검색 결과는 공통 state 계약에 맞춰 `RetrievedDocument` 형태로 변환한다.

```python
{
    "page_content": "...",
    "metadata": {
        "chunk_id": "...",
        "document_id": "...",
        "title": "...",
        "source_url": "...",
        "reliability": "...",
        "retrieval_method": "keyword+vector",
        "category": "...",
        "collection_scope": "...",
        "source_type": "...",
        "trust_level": "...",
        "chunk_index": 0,
        "embedding_model": "google/embeddinggemma-300m",
        "entity_type": "Boss->Reward"
    },
    "score": 0.0,
    "source": "..."
}
```

`retrieval_method`는 어떤 검색 방식으로 선택되었는지 나타낸다.

`entity_type`은 GraphDB 결과와 `wiki_entities` 색인 결과에서 사용한다. 예를 들어 Graph 관계 fact는 `Boss->Reward`, 위키 색인 결과는 `boss`, `item`, `map`처럼 들어간다. 일반 PGVector/keyword 결과에서는 `None`일 수 있다.

| 값 | 의미 |
| --- | --- |
| `vector` | 벡터 검색에서만 선택 |
| `keyword` | 키워드 검색에서만 선택 |
| `entity` | `wiki_entities` 엔티티 색인에서 선택 |
| `keyword+vector` | 두 검색 방식 모두에서 선택 |
| `graph` | Neo4j GraphDB 검색에서 선택 |

## AgentState 연동

Research Agent의 공통 계약은 `common/state.py`에 정의되어 있다.

```python
"research": {
    "required_inputs": ("user_query", "character_name", "world_name"),
    "required_outputs": ("retrieved_docs", "context"),
}
```

DB Search RAG는 이 계약에 맞춰 다음 필드만 채운다.

```python
state["retrieved_docs"]
state["context"]
```

사용 예시:

```python
from src.rag.db_search import db_search_rag_node

next_state = db_search_rag_node(
    {
        "user_query": "이벤트 보상 알려줘",
        "character_name": "sample",
        "world_name": "sample",
    },
    top_k=5,
    mode="hybrid",
)
```

## 직접 실행 예시

```python
from src.rag.db_search import run_db_search_rag

response = run_db_search_rag(
    query="이벤트 보상 알려줘",
    top_k=3,
    mode="hybrid",
)

print(response.context)
print(response.retrieved_docs)
```

GraphDB까지 포함해서 실행하려면 `include_graph=True`를 사용한다.

```python
from src.rag.db_search import run_db_search_rag

response = run_db_search_rag(
    query="노멀 스우 요구 스펙과 보상 알려줘",
    top_k=5,
    mode="hybrid",
    include_graph=True,
    graph_top_k=3,
)

print(response.context)
print(response.retrieved_docs)
```

## 적재 및 복원 절차

PostgreSQL 컨테이너 실행:

```powershell
docker compose -f database\docker-compose.yml up -d postgres
```

CSV를 RDB 문서/청크 테이블에 적재:

```powershell
.\.venv\Scripts\python.exe database\postgres\load_mapleqa_dataset.py
```

이미 schema가 적용되어 있고 데이터만 다시 맞출 때는 다음처럼 실행할 수 있다.

```powershell
.\.venv\Scripts\python.exe database\postgres\load_mapleqa_dataset.py --skip-schema
```

PGVector 임베딩 적재:

```powershell
.\.venv\Scripts\python.exe database\postgres\embed_document_chunks.py --provider embeddinggemma --model google/embeddinggemma-300m --batch-size 64
```

임베딩 스크립트는 이미 같은 모델로 적재된 chunk를 건너뛴다. 중간에 중단되어도 같은 명령을 다시 실행하면 남은 chunk부터 이어서 적재한다.

팀원에게 동일한 DB 상태를 전달할 때는 CSV와 임베딩 스크립트를 다시 실행시키기보다 DB dump를 공유하는 편이 빠르다.

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

## 검증 방법

문법 검사는 다음 명령으로 확인한다.

```powershell
.\.venv\Scripts\python.exe -m py_compile src\rag\db_search.py src\rag\retriever.py
```

PostgreSQL/PGVector만 확인할 때는 `run_db_search_rag()`를 직접 호출한다.

```powershell
.\.venv\Scripts\python.exe -c "from src.rag.db_search import run_db_search_rag; r = run_db_search_rag(query='이벤트 보상', top_k=3, mode='text', auto_create_embedding=False); print(len(r.retrieved_docs)); print(r.context[:1000])"
```

Neo4j GraphDB까지 포함할 때는 Neo4j 컨테이너와 seed 데이터가 준비된 상태에서 `include_graph=True`로 실행한다.

```powershell
$env:NEO4J_USER = "neo4j"; $env:NEO4J_PASSWORD = "admin123"; .\.venv\Scripts\python.exe -c "from src.rag.db_search import run_db_search_rag; r = run_db_search_rag(query='노멀 스우 요구 스펙', top_k=5, mode='text', include_graph=True, graph_top_k=3, auto_create_embedding=False); print(len(r.retrieved_docs)); print(r.context[:1000])"
```

2026-05-10 기준 검증 결과는 다음과 같다.

| 검증 항목 | 결과 | 의미 |
| --- | --- | --- |
| `py_compile` | 통과 | DB Search RAG, Graph retriever 문법 이상 없음 |
| PGVector hybrid 직접 실행 | 통과 | `이벤트 보상` 질의에서 `vector`, `keyword+vector` 근거 3개 반환 |
| Graph 포함 직접 실행 | 통과 | `노멀 스우 요구 스펙` 질의에서 `graph`, `keyword` 근거 함께 반환 |
| GraphDB seed 적재 | 통과 | `Boss`, `Event`, `Job`, `Reward`, `Source` 등 노드와 관계 적재 확인 |

기존 PGVector 검색에서 확인한 예시는 다음과 같다.

```text
query: 이벤트 보상
top_k: 3
mode: hybrid
```

예시 결과:

```text
vector        | 클라이언트 1.2.198 릴리즈
vector        | 수정 클라이언트 1.2.413 업데이트 안내 (이벤트)
keyword+vector| 수정 클라이언트 1.2.414 업데이트 안내 (이벤트, 컨텐츠, 개선사항 및 오류 수정)
```

GraphDB 포함 실행에서 확인한 대표 결과는 다음과 같다.

```text
노멀 스우 - HAS_REQUIREMENT - 노멀 스우
노멀 스우 - DROPS_REWARD - 앱솔랩스 장비
노멀 스우 - DROPS_REWARD - 강렬한 힘의 결정
```

## Web RAG와의 역할 분리

DB Search RAG와 Web Search RAG는 경쟁 관계가 아니라 보완 관계다.

| 모듈 | 역할 |
| --- | --- |
| DB Search RAG | 이미 적재된 공식/위키/룰 문서 기반의 안정적인 내부 근거 검색 |
| Web Search RAG | 최신 웹 문서, 실시간성 높은 이벤트/공지 검색 |

권장 흐름:

```text
Research Agent
  -> DB Search RAG
  -> 필요 시 Web Search RAG
  -> 결과 통합
  -> Final Answer Agent
```

## 향후 개선 사항

우선순위가 높은 개선 사항은 다음과 같다.

1. RAGAS 평가용 질문 10~20개 작성
2. DB Search RAG와 Web Search RAG 결과 통합 규칙 정의
3. GraphDB 검색 결과와 DB RAG 결과의 최종 rerank 가중치 튜닝
4. `retrieval_method`, `score`, `source_url`을 Final Answer citation 규칙과 맞추기
5. Neo4j seed 데이터 보강 후 Graph 검색 회수율 평가

## 수정 또는 확인이 필요한 부분

현재 설계에서 바로 수정하거나 팀과 확인하면 좋은 부분은 다음과 같다.

### 1. Graph 검색 결과 rerank 기준 튜닝

현재 `include_graph=True`일 때 GraphDB 결과와 PostgreSQL/PGVector 결과를 하나의 목록으로 합친다. GraphDB는 관계 지식에 강하지만 모든 질문에 필요한 것은 아니므로, 평가셋을 만든 뒤 rerank 기준을 조정해야 한다.

권장 방향:

```text
이벤트/업데이트 질문: PGVector/keyword 비중 확인
보스 요구 스펙/장비 세트/직업 주스탯 질문: Graph 결과 비중 확인
top_k 안에서 graph 결과가 과하거나 부족하지 않은지 평가
```

### 2. hybrid 기본 실행 시 모델 로딩 비용 확인

`run_db_search_rag()`와 `db_search_rag_node()`는 기본적으로 embedding function이 없으면 `google/embeddinggemma-300m`을 자동 생성하도록 설계했다.

장점:

```text
mode="hybrid"일 때 실제로 vector + keyword 검색이 모두 실행됨
```

주의점:

```text
최초 실행 시 Hugging Face 모델 로딩 시간이 걸릴 수 있음
HF_TOKEN이 필요한 환경에서는 실행 전 인증이 필요함
```

Streamlit이나 LangGraph에서 매 요청마다 모델을 새로 만들면 느려질 수 있다. 실제 서비스 연결 시에는 앱 시작 시 embedding model을 1회 생성하고 재사용하는 방식이 좋다.

### 3. vector/text 가중치 튜닝 필요

현재 기본값은 다음과 같다.

```python
DEFAULT_VECTOR_WEIGHT = 0.65
DEFAULT_TEXT_WEIGHT = 0.35
```

이 값은 초기 기준값이다. RAGAS 평가셋이나 샘플 질문 테스트 결과에 따라 조정하는 것이 좋다.

추천 비교:

```text
0.50 / 0.50
0.65 / 0.35
0.75 / 0.25
```

### 4. Final Answer 출처 표기 규칙과 metadata 맞추기

현재 DB Search RAG는 다음 metadata를 반환한다.

```python
title
source_url
reliability
retrieval_method
score
category
collection_scope
source_type
trust_level
chunk_index
embedding_model
entity_type
```

Final Answer Agent가 출처를 어떤 형식으로 보여줄지 정해지면, metadata key 이름을 더 엄격히 맞추는 것이 좋다.

예를 들어 최종 답변에서 `source`, `title`, `url`, `trust_level`을 요구한다면 `reliability`를 `trust_level`로 맞추거나 둘 다 제공하는 방식이 필요하다.

### 5. DB dump와 원본 데이터 공유 정책 확인

PGVector 데이터는 DB dump로 별도 공유하는 방향이 좋다. 원본 handoff/raw 데이터 폴더를 GitHub에 올리면 저장소가 무거워지고 파트 간 관리가 어려워질 수 있다.

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

권장 정책:

```text
GitHub: 코드, schema, 문서
별도 공유: mapledb_pgvector.dump
Git 제외: 원본 raw/handoff dataset, dump, __pycache__
```

## 주의 사항

- `common` 폴더의 함수/변수는 수정하지 않았다.
- `common.state.RetrievedDocument` 출력 형식에 맞춰 결과를 반환한다.
- `common.validator`를 사용해 Research Agent 입력/출력 state 계약을 검증한다.
- PGVector dump 파일은 GitHub에 올리지 않고 별도 공유하는 것을 권장한다.
