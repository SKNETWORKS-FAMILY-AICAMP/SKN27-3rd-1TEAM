# python 3.12

# 실행
```
cd app
streamlit run maple_chat.py
```

# 데이터
### neo4j
> graph_loader.py 실행

### postgreSQL(pgvector)
> 다운로드  https://drive.google.com/file/d/1lBz-kOiFt2uR9iZnszeOCZ0tpAkTxz-7/view
```
docker compose -f database\docker-compose.yml up -d postgres

docker cp .\database\data\postgre\mapledb_pgvector.dump maplestory-postgres:/tmp/mapledb_pgvector.dump

docker exec maplestory-postgres pg_restore -U admin -d mapledb --clean --if-exists /tmp/mapledb_pgvector.dump

docker exec maplestory-postgres psql -U admin -d mapledb -c "select 'documents' as table_name, count(*) from documents union all select 'document_chunks', count(*) from document_chunks union all select 'document_embeddings', count(*) from document_embeddings;"
```

# 폴더 구조
```
SKN27-3rd-1TEAM/
├─ app/
│  └─ streamlit_app.py              # Streamlit 화면
│
├─ common/
│  ├─ domain.py                     # 공통 데이터 모델
│  ├─ config.py                     # 환경변수, 설정
│  └─ constants.py                  # 공통 상수
│
├─ database/
│  ├─ data                  
│  ├─ postgres/                  # PostgreSQL + PGVector
│  ├─ neo4j/                     # GraphDB    
│  └─ docker-compose.yml
│
├─ docs/
│  ├─ openapi.yaml
│  ├─ wbs.csv
│  ├─ erd.md
│  └─ graph_schema.md
│
├─ src/
│  ├─ collectors/                   # 공식 API, 공지, 이벤트, 패치노트 수집
│  │  ├─ nexon_api.py
│  │  ├─ notice_crawler.py
│  │  └─ event_crawler.py
│  │
│  ├─ preprocessing/                # 정제, 청킹
│  │
│  ├─ rag/
│  │  ├─ db_search.py               # DB Search RAG
│  │  ├─ web_search.py              # Web Search RAG
│  │  └─ retriever.py
│  │
│  ├─ agents/
│  │  ├─ supervisor.py
│  │  ├─ researcher.py
│  │  ├─ analyst.py
│  │  ├─ calculator.py
│  │  └─ final_answer.py
│  │
│  ├─ services/
│  │  ├─ character_service.py       # 캐릭터 조회/통합
│  │  ├─ analysis_service.py        # 보스 판단, 병목 분석
│  │  └─ recommendation_service.py  # 성장 추천
│  │
│  └─ evaluation/
│     ├─ ragas_eval.py
│     └─ answer_eval.py
│
├─ requirements.txt
├─ README.md
└─ setup-guide.md

```



# 예시 질문

## 기본 질문

- 안녕
- 스타포스가 뭐야?
- 아케인포스가 뭐야?
- 파란버섯에 대해 알려줘

## DB / RAG 검색 예시

- 노멀 스우 요구 스펙 알려줘
- 스우 보상 알려줘
- 앱솔랩스 세트에 대해 알려줘
- 아케인셰이드 세트는 어떤 장비야?
- 노멀 루시드 요구 스펙 알려줘
- 검은 마법사 요구 스펙 알려줘

## Nexon Open API 예시

> Nexon Open API 키가 설정되어 있어야 정상 조회됩니다.

- 엘리시움 서버 랭킹 1위 누구야?
- 엘리시움 서버의 버터 조회해줘
- 엘리시움 서버의 버터 정보조회해줘
- 현재 진행 중인 이벤트 알려줘

## 캐릭터 조회 후 이어서 물어보기

먼저 아래처럼 캐릭터를 조회합니다.

- 엘리시움 서버의 버터 조회해줘

그 다음 이어서 아래 질문을 할 수 있습니다.

- 이 캐릭터로 노멀 스우 가능해?
- 이 캐릭터 스펙 요약해줘
- 지금 내가 더 성장하려면 어떤 콘텐츠를 시작해야 할까?
- 노멀 스우 공략 가능해?

## 주의할 질문

아래처럼 대상이 불명확하거나 DB에 없는 보스명을 쓰면 답변 품질이 떨어질 수 있습니다.

- 이거 잡을 수 있어?
- 버터 정보 알려줘
- 하드 오스카 잡을 수 있어?



1. 엘리시움 서버의 버터 조회해줘
2. 이 캐릭터로 노멀 스우 가능해?
3. 노멀 스우 요구 스펙 알려줘
4. 엘리시움 서버 랭킹 1위 누구야?
5. 파란버섯에 대해 알려줘