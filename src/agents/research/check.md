# Research Agent

이 폴더는 멀티에이전트 구조에서 **리서치 에이전트**를 담당합니다.

리서치 에이전트의 역할은 사용자의 질문에 답을 바로 생성하는 것이 아니라,
답변에 필요한 근거 자료를 찾아서 다음 에이전트가 사용할 수 있는 형태로 정리하는 것입니다.

## 역할

`run_research(state)` 함수는 `common/state.py`에 정의된 Research Agent 계약을 따릅니다.

입력으로 필요한 값:

- `user_query`: 사용자의 질문
- `character_name`: 캐릭터 이름
- `world_name`: 월드 이름

출력으로 채우는 값:

- `retrieved_docs`: 검색으로 찾은 문서 목록
- `context`: 최종 답변 에이전트가 읽을 수 있도록 정리한 근거 문자열

즉, 리서치 에이전트는 아래처럼 동작합니다.

```text
사용자 질문
  -> 필요한 검색 방식 선택
  -> DB / Graph / Web RAG 실행
  -> 검색 결과 병합
  -> 중복 제거
  -> context 생성
  -> 다음 에이전트로 전달
```

## 검색 방식 선택 기준

현재 1차 구현은 LLM에게 판단을 맡기지 않고, 질문 안의 키워드를 보고 검색 방식을 선택합니다.

처음부터 LLM 라우터를 쓰면 결과가 매번 달라질 수 있고 디버깅이 어려워집니다.
그래서 초반에는 단순하고 예측 가능한 규칙 기반 방식으로 구성했습니다.

### DB Search RAG

DB RAG는 기본 검색기로 항상 실행합니다.

프로젝트 내부에 저장된 공식 문서, 위키 보조 문서, 추천 규칙, 강화 우선순위 같은
기존 지식 기반 자료를 찾는 역할입니다.

### Graph RAG

다음처럼 관계형 정보가 필요한 질문이면 Graph RAG를 함께 사용합니다.

- 보스 요구 스펙
- 보스 보상
- 장비 세트 효과
- 직업과 주요 스탯 관계
- 특정 콘텐츠와 보상 관계

예시 질문:

```text
노말 스우 요구 스펙 알려줘
카루타 세트효과 알려줘
보스 보상 뭐가 있어?
```

### Web Search RAG

다음처럼 최신성이 중요한 질문이면 Web RAG를 함께 사용합니다.

- 최신 공지
- 현재 진행 중인 이벤트
- 이번 패치
- 하이퍼 버닝 보상
- 테스트월드 업데이트
- 캐시샵 공지

예시 질문:

```text
이번 하이퍼 버닝 보상 알려줘
최신 패치 내용 알려줘
오늘 올라온 이벤트 공지 있어?
```

## 주요 파일

```text
src/agents/research/
  __init__.py
  agent.py
  README.md
  notebooks/
    research_agent_validation.ipynb
```

### `agent.py`

리서치 에이전트의 핵심 코드입니다.

주요 함수:

- `classify_research_route()`: 질문을 보고 DB / Graph / Web 중 어떤 검색을 사용할지 결정합니다.
- `run_research()`: 실제 리서치 에이전트 본체입니다.
- `research_agent()`: LangGraph 노드에 등록하기 쉽게 만든 별칭 함수입니다.
- `merge_retrieved_documents()`: 여러 검색 결과를 합치고 중복 문서를 제거합니다.
- `build_research_context()`: 최종 답변 에이전트가 읽을 수 있는 문자열 context를 만듭니다.

### `notebooks/research_agent_validation.ipynb`

리서치 에이전트를 공부하고 검증하기 위한 노트북입니다.

노트북에서 확인할 수 있는 것:

- 라우팅 규칙이 잘 동작하는지
- 문서 병합과 중복 제거가 잘 되는지
- context가 어떤 형태로 만들어지는지
- Docker / PostgreSQL / Neo4j 상태가 어떤지
- 실제 `run_research()` 실행 결과가 어떤지
