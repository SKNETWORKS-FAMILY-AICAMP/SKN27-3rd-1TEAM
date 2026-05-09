# CODEX.md (AI Agent System Instructions)

## 프로젝트 개요 및 기술 스택
- **프로젝트:** 메이플스토리 데이터 기반 RAG 멀티 에이전트 챗봇
- **기술 스택:** Python 3.12, Streamlit, Neo4j (GraphDB), PostgreSQL (PGVector), LLM (`common/get_model.py` 기준)

## 역할
- 본 프로젝트의 코딩 및 아키텍처 관리를 돕는 전용 에이전트로 동작한다.
- 구현, 디버깅, 테스트, 코드 리뷰 지원을 우선한다.

## 데이터 및 설계 절대 원칙 (Single Source of Truth)
- **공통 규칙:** `common/` 폴더 안의 모든 파일은 프로젝트 공통 규칙으로 간주하며, 구현 전에 반드시 관련 파일을 확인한다.
- **도메인 모델:** 모든 데이터 구조와 타입은 반드시 `common/domain.py`를 기준으로 작성하며, 임의로 데이터 클래스를 창조하지 않는다.
- **에이전트 상태:** 에이전트 간 데이터 전달은 반드시 `common/state.py`의 `AgentState`, `RetrievedDocument`, `AGENT_FIELD_CONTRACTS`를 기준으로 맞춘다.
- **검증 규칙:** 상태 입력/출력 검증은 `common/validator.py`의 규칙을 우선 사용한다.
- **공통 프롬프트:** 답변 생성 및 에이전트 프롬프트는 `common/prompt.py`의 원칙을 우선 반영한다.
- **모델 호출:** LLM/임베딩 모델 호출 방식은 `common/get_model.py`의 공통 헬퍼를 우선 확인한다.
- **로깅:** 로그가 필요한 모듈은 `common/logging_config.py`의 공통 로깅 설정을 우선 따른다.
- **API 규격:** 넥슨 오픈 API 및 내부 API 로직을 작성할 때는 반드시 `docs/openapi.yaml`에 정의된 요청/응답 스키마를 엄격히 따른다.
- **GraphDB/Web RAG 설계:** 담당 브랜치 병합 후 `docs/graph_schema.md`, `docs/web_rag_design.md`가 존재하면 해당 설계 문서를 추가 기준으로 확인한다.

## 코드 스타일
- 항상 간결하고 보기 쉬운 코드를 작성한다.
- 구현은 작고 이해하기 쉬운 단위로 유지한다.
- 불필요한 추상화는 피한다.
- 주석은 코드만으로 의도가 분명하지 않을 때만 짧게 작성한다.

## 모듈화
- 항상 책임 단위로 명확하게 모듈화한다.
- 각 모듈은 하나의 목적에 집중한다.
- 새 구조를 만들기 전에 기존 프로젝트 패턴을 우선 따른다.
- 단순한 로컬 함수로 충분한 경우 과하게 분리하지 않는다.

## 하드코딩 금지 및 보안 규칙
- 값, 경로, 반복 문자열, 매직 넘버를 소스 코드 내에 하드코딩하지 않는다. 상수, 설정, 헬퍼 함수, 데이터 구조를 적극 사용한다.
- **환경변수 사용:** API 키, DB 접속 정보 등 모든 민감 정보는 `os.environ.get()` 또는 기존 공통 헬퍼를 통해 호출한다.
- **.env 원칙:** 환경변수의 키값과 더미(Dummy) 데이터는 `.env.example` 파일에만 작성한다. 실제 민감한 값이 들어가는 `.env` 또는 `secrets.toml` 파일은 에이전트가 직접 읽거나 수정하려고 시도해서는 안 된다.

## 구현 규칙
- 작은 단위로 나누어 구현한다.
- 각 단계 후 실행 가능한 상태를 유지한다.
- 넓은 리팩터링보다 목적에 맞는 집중된 변경을 우선한다.
- 필요한 경우가 아니면 관련 없는 파일이나 동작은 수정하지 않는다.

## 멀티 에이전트 기준 흐름
모든 런타임 에이전트 설계는 아래 흐름을 기준 규칙으로 따른다.

```text
질문
→ supervisor Agent
→ 입력 state 계약 검증 후 research / analystic / calculator 실행
→ research는 RAG(vector, graph, postgre) 조회 수행
→ research / analystic / calculator는 출력 state 계약 검증 후 supervisor Agent로 반환
→ supervisor Agent가 다음 에이전트 또는 final_answer 진행 결정
→ 입력 state 계약 검증 후 final_answer
→ evaluation
→ is_pass == True이면 답변 반환
→ is_pass == False이고 근거/문맥은 맞으면 final_answer로 재생성
→ 질문과 상관없는 답변이면 supervisor Agent로 돌아가 멀티 에이전트 재진입
```

- `supervisor`: 사용자 질문을 분석하고 실행할 에이전트와 작업 순서를 정한다.
- `supervisor 재진입`: `research`, `analystic`, `calculator`의 결과는 supervisor로 반환되며, supervisor가 state를 확인한 뒤 다음 단계 또는 `final_answer` 진행 여부를 결정한다.
- `state 계약 검증`: 독립 에이전트가 아니라 `common/validator.py` 기준으로 각 에이전트 호출 전 필수 입력 state와 반환 전 필수 출력 state를 확인하는 과정이다.
- `research`: RAG 검색을 담당하며 vector, graph, postgre 기반 검색 결과를 `retrieved_docs`, `context`로 정리한다.
- `analystic`: 코드 기준 이름은 `common/state.py`의 `analystic`이며, 캐릭터 상태 분석과 진단 결과를 생성한다.
- `calculator`: 장비, 스탯, 성장 수치 계산을 수행하고 계산 결과를 state에 기록한다.
- `final_answer`: 각 에이전트 결과를 종합해 `draft_answer`, `final_answer`, `confidence_score`를 생성한다.
- `evaluation`: 답변 품질과 질문 관련성을 평가한다. `is_pass == False`이면서 근거/문맥은 맞으면 `final_answer`로 되돌려 보완하고, 질문과 상관없는 답변이면 supervisor로 돌려보내 에이전트 계획부터 다시 수행하게 한다.
- `답변`: 평가를 통과한 결과만 `ApiResponseChat` 호환 응답으로 반환한다.

## 검증 (Feedback Loop)
- 코드 변경 후 가능한 경우 프로젝트에 존재하는 검증 스크립트를 우선 실행한다.
- 검증 스크립트가 없는 경우 `python -m compileall` 및 `common/validator.py` 기반 상태 계약 검증처럼 현재 구조에서 실행 가능한 검증을 수행한다.
- 자동화 검증이 가능한 경우 수동 확인에만 의존하지 않는다.
- 실행하지 못한 검증 항목이나 린트(Lint) 에러가 발생한 경우 무시하지 말고 반드시 보고하고 스스로 수정한다.

## 프로젝트 구조 및 파일 배치 규칙
새로운 파일을 생성할 때는 아래 구조의 역할에 맞게 배치한다.

- `app/`: Streamlit 챗봇 UI 및 화면 렌더링 로직
- `common/`: 시스템 전반에서 쓰이는 도메인 모델(`domain.py`), 공유 상태(`state.py`), 검증(`validator.py`), 프롬프트(`prompt.py`), 모델 헬퍼(`get_model.py`), 로깅 설정(`logging_config.py`)
- `database/`: Neo4j, Postgres 연동 및 초기 데이터 적재 로직
- `docs/`: API 명세서, WBS, ERD, Graph 스키마 등 기획/설계 문서
- `scripts/`: 검증 및 테스트 자동화 스크립트
- `src/collectors/`: 외부 데이터 수집 모듈
- `src/preprocessing/`: 데이터 정제 및 청킹 로직
- `src/rag/`: Vector DB / Graph DB / Web Search 기반 검색 및 Retriever 로직
- `src/agents/`: 챗봇 서비스 내부에서 유저의 질문을 처리하는 런타임 에이전트들
- `src/services/`: 캐릭터 조회, 보스 분석, 성장 추천 등 핵심 비즈니스 로직
- `src/ML/` & `src/evaluation/`: 머신러닝 모델링 및 RAG 성능 평가 스크립트
