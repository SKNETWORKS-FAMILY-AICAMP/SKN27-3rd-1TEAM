# DB Search RAG 설계 및 작업 정리

## 목적

DB Search RAG는 프로젝트 내부 PostgreSQL/PGVector에 적재된 문서 데이터를 검색하여 Research Agent와 Final Answer Agent가 사용할 근거 문맥을 제공하는 모듈이다.

이 모듈은 답변을 직접 생성하지 않는다. 역할은 다음 두 값을 안정적으로 만드는 것이다.

- `common.state.AgentState["retrieved_docs"]`
- `common.state.AgentState["context"]`

## 담당 범위

D 파트 기준 담당 범위는 다음과 같다.

- PostgreSQL RDB
- PGVector
- DB Search RAG
- RAGAS 평가 유틸
- ERD 문서

DB Search RAG는 `src/rag/db_search.py`를 중심으로 구현되어 있다.

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

### GraphDB 검색을 이 문서 범위에 넣지 않은 이유

참고 노트북은 Graph Search와 Vector Search를 결합하는 GraphRAG 구조까지 다룬다. 하지만 현재 프로젝트 분담에서 GraphDB는 B/F 파트와 연결되어 있다.

D 파트에서 Neo4j 검색까지 직접 구현하면 파트 간 책임이 겹칠 수 있다. 그래서 현재 DB Search RAG 문서는 PostgreSQL/PGVector 내부의 hybrid 검색까지만 다룬다.

GraphDB 결과와 DB Search RAG 결과를 합치는 상위 전략은 Supervisor 또는 Research Agent 단계에서 B/F 파트와 협의해서 정하는 것이 맞다.

## 사용 데이터

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
| `wiki_entities` | 위키 문서에서 추출 가능한 엔티티 |

현재 검색의 핵심 조인은 다음 구조다.

```text
document_embeddings
  -> document_chunks
  -> documents
```

## 임베딩 모델

현재 적재된 PGVector 임베딩은 다음 모델을 사용한다.

```text
model: google/embeddinggemma-300m
dimension: 768
provider: embeddinggemma
```

따라서 `document_embeddings.embedding`은 `vector(768)`이다.

## 파일 구성

| 파일 | 역할 |
| --- | --- |
| `src/rag/db_search.py` | DB Search RAG 메인 wrapper, hybrid 검색, AgentState adapter |
| `src/rag/pgvector_store.py` | PGVector similarity/keyword/hybrid 검색 store |
| `src/evaluation/ragas_eval.py` | RAGAS 평가 유틸 |
| `database/postgres/schema.sql` | PostgreSQL + PGVector schema |
| `database/postgres/load_mapleqa_dataset.py` | CSV -> RDB/chunk 적재 |
| `database/postgres/embed_document_chunks.py` | chunk -> embedding 적재 |

## 검색 모드

`src/rag/db_search.py`는 다음 검색 모드를 지원한다.

| mode | 설명 |
| --- | --- |
| `text` | PostgreSQL full-text + `ILIKE` 기반 키워드 검색 |
| `vector` | PGVector cosine distance 기반 의미 검색 |
| `hybrid` | vector 검색과 keyword 검색 결과를 통합 |
| `auto` | query embedding이 있으면 hybrid, 없으면 text 검색 |

기본 권장 모드는 `hybrid`다.

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

프로젝트에는 GraphDB 파트가 별도 담당 영역이므로, D 파트에서는 다음 범위만 적용했다.

```text
Vector Search + Keyword Search
  -> score normalization
  -> weighted fusion
  -> rerank
  -> RetrievedDocument/context 반환
```

## Hybrid 검색 흐름

```text
사용자 질문
  -> query embedding 생성
  -> PGVector vector search
  -> PostgreSQL text/keyword search
  -> 각 검색 결과 score를 0~1로 정규화
  -> vector/text 가중치 적용
  -> chunk_id 기준 중복 제거
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
        "retrieval_method": "keyword+vector"
    },
    "score": 0.0,
    "source": "..."
}
```

`retrieval_method`는 어떤 검색 방식으로 선택되었는지 나타낸다.

| 값 | 의미 |
| --- | --- |
| `vector` | 벡터 검색에서만 선택 |
| `keyword` | 키워드 검색에서만 선택 |
| `keyword+vector` | 두 검색 방식 모두에서 선택 |

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

## 현재 검증 결과

다음 명령으로 문법 검사를 통과했다.

```powershell
.\.venv\Scripts\python.exe -m py_compile src\rag\db_search.py
```

다음 질의로 실제 DB 검색을 확인했다.

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

1. `src/rag/db_search_smoke.py` 한글 깨짐 수정
2. RAGAS 평가용 질문 10~20개 작성
3. DB Search RAG와 Web Search RAG 결과 통합 규칙 정의
4. GraphDB 검색 결과와 DB RAG 결과를 합치는 상위 hybrid 전략은 B/F 파트와 협의
5. `retrieval_method`, `score`, `source_url`을 Final Answer citation 규칙과 맞추기

## 수정 또는 확인이 필요한 부분

현재 설계에서 바로 수정하거나 팀과 확인하면 좋은 부분은 다음과 같다.

### 1. `db_search_smoke.py` 한글 깨짐 수정

현재 smoke test 파일의 샘플 질문 문자열이 깨져 있다. 기능 자체보다 팀원이 테스트할 때 신뢰도를 떨어뜨릴 수 있으므로 우선 수정이 필요하다.

권장 방향:

```text
정상 한글 질문 5~10개로 교체
text / vector / hybrid 모드별 실행 예시 추가
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
```

Final Answer Agent가 출처를 어떤 형식으로 보여줄지 정해지면, metadata key 이름을 더 엄격히 맞추는 것이 좋다.

예를 들어 최종 답변에서 `source`, `title`, `url`, `trust_level`을 요구한다면 `reliability`를 `trust_level`로 맞추거나 둘 다 제공하는 방식이 필요하다.

### 5. DB dump와 원본 데이터 공유 정책 확인

PGVector 데이터는 DB dump로 별도 공유하는 방향이 좋다. 원본 handoff/raw 데이터 폴더를 GitHub에 올리면 저장소가 무거워지고 파트 간 관리가 어려워질 수 있다.

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
