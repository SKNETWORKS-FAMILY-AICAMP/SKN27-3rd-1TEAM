# Web Search RAG 설계 문서

## 1. 목적

Web Search RAG는 메이플스토리 관련 질문에 대해 최신성이 필요한 웹 문서를 검색하고, 답변 생성에 사용할 수 있는 근거 컨텍스트를 제공하기 위한 검색 모듈이다.

본 모듈은 최종 답변을 직접 생성하지 않는다. 검색 결과, 문서 본문, 청크, 출처 정보를 구조화하여 Research Agent 또는 Final Answer Agent가 사용할 수 있는 형태로 반환한다.

## 2. 설계 기준

본 설계는 다음 프로젝트 기준을 따른다.

- `common/` 폴더 안의 모든 파일을 공통 규칙으로 사용한다.
- `common/domain.py`를 기준 데이터 구조로 사용한다.
- `common/state.py`의 `RetrievedDocument`, `AgentState`, `AGENT_FIELD_CONTRACTS`를 에이전트 연동 계약으로 사용한다.
- `common/validator.py`의 state 검증 규칙과 충돌하지 않도록 입력/출력 필드를 구성한다.
- `common/prompt.py`의 "모르면 모른다고 답한다", "state에 없는 정보는 추측하지 않는다" 원칙을 Final Answer 전달 context에도 반영한다.
- 모델 호출이 필요한 확장 단계에서는 `common/get_model.py`의 공통 헬퍼를 우선 확인한다.
- 로그가 필요한 확장 단계에서는 `common/logging_config.py`의 공통 로깅 설정을 우선 확인한다.
- `docs/openapi.yaml`에 정의된 캐릭터/API 데이터 흐름을 보조 기준으로 참고한다.
- Web RAG 로직은 `src/rag/web_search.py`에 배치한다.
- 새 데이터 클래스를 임의로 만들지 않고, dict 기반의 단순 구조로 검색 결과를 전달한다.
- API 키, 검색 URL, 타임아웃, 검색 도메인 등 설정값은 환경변수로 조정할 수 있게 한다.

## 3. Web RAG 처리 흐름

```text
사용자 질문
  ↓
검색 쿼리 생성
  ↓
Tavily Search API 요청
  ↓
공식/커뮤니티 허용 도메인 필터링
  ↓
문서 HTML 수집
  ↓
본문 정제
  ↓
청킹
  ↓
질문과 청크 간 단순 관련도 점수화
  ↓
출처 포함 context 반환
```

## 4. 입력 데이터

### 4.1 질문

사용자의 자연어 질문을 입력으로 받는다.

```python
question = "하이퍼 버닝 보상 알려줘"
```

### 4.2 캐릭터 컨텍스트

캐릭터 컨텍스트는 `common/domain.py`의 `ProcessedCharacter`와 같은 필드 구조를 기준으로 한다.

현재 1차 구현에서는 `domain.py`를 직접 import하지 않고, 다음 필드를 가진 객체 또는 dict를 받을 수 있게 한다.

| 필드 | 설명 |
|---|---|
| `character_name` | 캐릭터명 |
| `job_name` | 직업명 |
| `level` | 캐릭터 레벨 |
| `world_name` | 월드명 |

예시:

```python
character_context = {
    "character_name": "예시캐릭터",
    "job_name": "아델",
    "level": 260,
    "world_name": "스카니아",
}
```

## 5. 출력 데이터

`WebSearchRAG.retrieve()`는 다음 구조의 dict를 반환한다.

```json
{
  "question": "하이퍼 버닝 보상 알려줘",
  "search_query": "하이퍼 버닝 보상 알려줘 메이플스토리 ...",
  "documents": [
    {
      "title": "문서 제목",
      "url": "https://maplestory.nexon.com/...",
      "reliability": "HIGH",
      "freshness": "HIGH",
      "published_at": "2026-04-16"
    }
  ],
  "contexts": [
    {
      "title": "문서 제목",
      "url": "https://maplestory.nexon.com/...",
      "chunk_index": 0,
      "content": "검색된 문서 본문 청크",
      "score": 0.5,
      "reliability": "HIGH",
      "freshness": "HIGH",
      "published_at": "2026-04-16"
    }
  ]
}
```

## 6. 주요 구성 요소

| 구성 요소 | 설명 |
|---|---|
| `build_search_query` | 사용자 질문과 캐릭터 컨텍스트를 조합하여 검색 쿼리 생성 |
| `WebSearchRAG.search` | 설정된 검색 provider를 사용하여 허용 도메인의 검색 결과 URL 추출 |
| `WebSearchRAG.search_tavily` | Tavily Search API 요청 및 JSON 응답 파싱 |
| `WebSearchRAG.search_duckduckgo` | 로컬 POC용 DuckDuckGo HTML 검색 fallback |
| `WebSearchRAG.fetch_document` | 검색 결과 URL의 HTML 수집 및 본문 추출 |
| `chunk_text` | 긴 본문을 일정 길이의 청크로 분할 |
| `score_text` | 질문 토큰과 청크 토큰의 겹침 비율로 1차 관련도 계산 |
| `WebSearchRAG.retrieve` | 검색, 수집, 청킹, 점수화를 묶어 context 반환 |
| `format_contexts_for_prompt` | Final Answer Agent가 사용할 수 있는 프롬프트용 문자열 생성 |
| `to_retrieved_documents` | `common/state.py`의 `RetrievedDocument` 목록으로 context 변환 |
| `retrieve_for_agent_state` | Research Agent가 `retrieved_docs`, `context`, `tool_results` 형태로 state에 병합할 수 있는 결과 반환 |

## 7. 공식 출처 우선 전략

1차 구현에서는 기본적으로 공식 출처를 우선한다.

기본 공식 도메인은 다음과 같다.

```text
maplestory.nexon.com
openapi.nexon.com
notice.nexon.com
```

공식 도메인에서 가져온 문서는 `reliability = "HIGH"`로 표시한다.
`reliability`는 출처의 공식성이고, `freshness`는 최신성이다. 오래된 공식 문서는 여전히 `reliability = "HIGH"`일 수 있지만 `freshness = "LOW"`로 표시한다.
단, `maplestory.nexon.com` 안에서도 `/Community` 경로는 유저 게시글 영역이므로 공식-only 검색에서는 제외하고 `HIGH`로 평가하지 않는다.
스크린샷의 뉴스 메뉴에 해당하는 공지사항, 업데이트, 이벤트, 캐시샵 공지, 메이플 알림판, with maple 등 `/News` 하위 공식 콘텐츠는 공식 근거로 사용한다.
그 외 `/Promotion/Event`, `/Guide` 같은 공식 콘텐츠 경로도 공식 근거로 사용한다.
코어 개편처럼 검색어가 특정 공식 프로모션 페이지와 강하게 연결되는 경우에는 우선 URL 규칙으로 해당 공식 페이지를 검색 결과 앞쪽에 보강한다.
메이플 인벤과 같은 커뮤니티 문서는 공식 출처가 아니므로 공식 도메인에 포함하지 않고, 별도의 커뮤니티 도메인으로 분리한다.
커뮤니티 문서는 보조 자료로만 사용하며 `reliability = "MEDIUM"`으로 표시한다.

커뮤니티 문서까지 포함하려면 `official_only=False` 또는 CLI 옵션 `--include-community`를 사용한다.
이 경우에도 전체 웹을 모두 허용하지 않고, 공식 도메인과 커뮤니티 허용 도메인만 검색한다.
Tavily provider에서는 검색어에 `site:` 연산자를 직접 넣지 않고, Tavily의 `include_domains` 요청 필드로 허용 도메인을 전달한다.
DuckDuckGo fallback에서는 HTML 검색 특성상 검색어에 `site:` 필터를 포함한다.

최신성 기준은 다음과 같다.

| freshness | 기준 |
|---|---|
| `HIGH` | 발행일 기준 90일 이내 또는 미래/진행 예정 문서 |
| `MEDIUM` | 발행일 기준 1년 이내 |
| `LOW` | 발행일 기준 1년 초과 |
| `UNKNOWN` | 발행일을 추출하지 못한 경우 |

기본 커뮤니티 도메인은 다음과 같다.

```text
maple.inven.co.kr
www.inven.co.kr
```

## 8. 환경변수

| 환경변수 | 기본값 | 설명 |
|---|---|---|
| `WEB_RAG_SEARCH_PROVIDER` | `tavily` | 검색 provider. `tavily` 또는 `duckduckgo` |
| `WEB_RAG_SEARCH_URL` | `https://api.tavily.com/search` | 검색 요청 URL |
| `WEB_RAG_USER_AGENT` | `SKN27-MapleStory-WebRAG/0.1` | 요청 User-Agent |
| `WEB_RAG_TIMEOUT_SECONDS` | `10` | 요청 타임아웃 |
| `WEB_RAG_MAX_RESULTS` | `5` | 검색 결과 최대 개수 |
| `WEB_RAG_MAX_CONTEXTS` | `5` | 반환 context 최대 개수 |
| `WEB_RAG_OFFICIAL_DOMAINS` | 기본 공식 도메인 목록 | 쉼표로 구분한 공식 도메인 목록 |
| `WEB_RAG_COMMUNITY_DOMAINS` | 기본 커뮤니티 도메인 목록 | 쉼표로 구분한 커뮤니티/보조 도메인 목록 |
| `TAVILY_API_KEY` | 없음 | Tavily Search API 키 |
| `TAVILY_SEARCH_DEPTH` | `basic` | Tavily 검색 깊이. 필요 시 `advanced` |
| `TAVILY_INCLUDE_RAW_CONTENT` | `false` | Tavily raw content 포함 여부 |

## 9. 실행 예시

```bash
.venv\Scripts\python.exe -m src.rag.web_search "하이퍼 버닝 보상 알려줘" --max-results 3 --max-contexts 3
```

프롬프트에 바로 넣을 문자열 형태가 필요하면 다음처럼 실행한다.

```bash
.venv\Scripts\python.exe -m src.rag.web_search "하이퍼 버닝 보상 알려줘" --prompt-format
```

## 10. Agent 연동 방식

Web RAG는 Research Agent 또는 Final Answer Agent 앞단에서 사용할 수 있다.

```text
Supervisor Agent
  ↓
Research Agent
  ↓
retrieve_for_agent_state()
  ↓
retrieved_docs + context + tool_results 반환
  ↓
Final Answer Agent
```

Research Agent는 `common/state.py`의 계약에 맞춰 `retrieved_docs`와 `context`를 채운다.
Final Answer Agent는 `context`와 `retrieved_docs.metadata`의 `title`, `url`, `reliability`, `freshness`, `published_at`을 함께 사용하여 답변과 출처를 구성한다.

## 11. 공통 에이전트 흐름 내 Web RAG 위치

Web RAG는 공통 에이전트 흐름에서 `research` 단계의 RAG 근거 중 `vector`, `graph`, `postgre`와 함께 검색 근거를 제공하는 역할을 담당한다.

```text
질문
→ supervisor Agent
→ validation
→ research / analystic / calculator
→ 각 작업 에이전트 결과는 supervisor Agent로 반환
→ supervisor Agent가 다음 에이전트 또는 final_answer 진행 결정
→ final_answer
→ evaluation
→ is_pass == False이면 final_answer로 재생성
→ is_pass == True이면 답변 반환
```

Web RAG는 `validation` 이후 Research Agent가 호출하며, 검색 결과를 `retrieved_docs`, `context`, `tool_results` 형태로 정리한 뒤 supervisor로 반환한다. Supervisor Agent는 해당 state를 확인한 뒤 다음 에이전트 실행 또는 Final Answer Agent 진행 여부를 결정한다. Final Answer Agent의 답변이 Evaluation Agent에서 실패하면 `final_answer`가 보완 답변을 생성할 때 동일한 Web RAG 근거를 다시 사용한다.

## 12. 1차 구현 한계

현재 구현은 1차 POC 수준이므로 다음 한계가 있다.

- Tavily API 키가 필요하다.
- Tavily 응답 품질은 검색 API 결과와 허용 도메인 설정에 영향을 받는다.
- DuckDuckGo fallback 사용 시 검색 엔진 HTML 구조 변경에 영향을 받을 수 있다.
- 관련도 점수는 임베딩 기반이 아니라 단순 토큰 겹침 기반이다.
- 공식 문서의 동적 렌더링 영역은 완전히 추출되지 않을 수 있다.
- 중복 문서 제거와 날짜 기반 최신성 판단은 최소 수준이다.
- 수집 결과를 PGVector나 PostgreSQL에 저장하지 않고 메모리에서만 반환한다.

## 13. 다음 개선 방향

향후 개선 시 다음 항목을 추가할 수 있다.

- 문서 날짜 추출 및 최신성 가중치 반영
- PGVector 기반 문서 임베딩 검색 연동
- 공식 문서와 커뮤니티 문서 신뢰도 분리 강화
- 검색 결과 캐싱
- RAGAS 기반 Web RAG 검색 품질 평가
- Final Answer Agent용 출처 포맷 표준화
