# python 3.12

# 데이터

docs/openapi.yaml파일을 참고하여 어떤 값이 필요한지, 어떤 데이터가 나오는지 파악하세요
아래의 링크에 들어가서 파일의 내용을 복사 붙여넣기 하면 됩니다
https://editor.swagger.io/

common/domain.py 파일은 기준 데이터 구조 정의 파일입니다
모든 로직은 이 domain 모델을 기준으로 작성해주시면 됩니다

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
│  ├─ ML/
│  │  ├─ feature engineering.py
│  │  ├─ training.py
│  │  ├─ modeling.py
│  │  └─ evaluator.py
│  │
│  └─ evaluation/
│     ├─ ragas_eval.py
│     └─ answer_eval.py
│
├─ requirements.txt
├─ README.md
└─ setup-guide.md

```