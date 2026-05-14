# python 3.12

# 데이터
### neo4j
> graph_loader.py 실행

### postgreSQL(pgvector)
> 다운로드  https://drive.google.com/file/d/1lBz-kOiFt2uR9iZnszeOCZ0tpAkTxz-7/view
```
docker compose -f database\docker-compose.yml up -d postgres

docker cp .\database\postgres\mapledb_pgvector.dump maplestory-postgres:/tmp/mapledb_pgvector.dump

docker exec maplestory-postgres pg_restore -U admin -d mapledb --clean --if-exists /tmp/mapledb_pgvector.dump

docker exec maplestory-postgres psql -U admin -d mapledb -c "select 'documents' as table_name, count() from documents union all select 'document_chunks', count() from document_chunks union all select 'document_embeddings', count(*) from document_embeddings;"
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