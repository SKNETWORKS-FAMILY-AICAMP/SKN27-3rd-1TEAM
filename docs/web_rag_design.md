# Web Search RAG 설계 문서

## 1. 목적

Web Search RAG는 메이플스토리 관련 질문에 대해 최신성이 필요한 웹 문서를 검색하고, 답변 생성에 사용할 수 있는 근거 컨텍스트를 제공하기 위한 검색 모듈이다.

본 모듈은 최종 답변을 직접 생성하지 않는다. 검색 결과, 문서 본문, 청크, 출처 정보를 구조화하여 Research Agent 또는 Final Answer Agent가 사용할 수 있는 형태로 반환한다.

## 2. 설계 기준

본 설계는 다음 프로젝트 기준을 따른다.

- `common/domain.py`를 기준 데이터 구조로 사용한다.
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
      "reliability": "HIGH"
    }
  ],
  "contexts": [
    {
      "title": "문서 제목",
      "url": "https://maplestory.nexon.com/...",
      "chunk_index": 0,
      "content": "검색된 문서 본문 청크",
      "score": 0.5,
      "reliability": "HIGH"
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

## 7. 공식 출처 우선 전략

1차 구현에서는 기본적으로 공식 출처를 우선한다.

기본 공식 도메인은 다음과 같다.

```text
maplestory.nexon.com
openapi.nexon.com
notice.nexon.com
```

공식 도메인에서 가져온 문서는 `reliability = "HIGH"`로 표시한다.
메이플 인벤과 같은 커뮤니티 문서는 공식 출처가 아니므로 공식 도메인에 포함하지 않고, 별도의 커뮤니티 도메인으로 분리한다.
커뮤니티 문서는 보조 자료로만 사용하며 `reliability = "MEDIUM"`으로 표시한다.

커뮤니티 문서까지 포함하려면 `official_only=False` 또는 CLI 옵션 `--include-community`를 사용한다.
이 경우에도 전체 웹을 모두 허용하지 않고, 공식 도메인과 커뮤니티 허용 도메인만 검색한다.

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
WebSearchRAG.retrieve()
  ↓
검색 근거 contexts 반환
  ↓
Final Answer Agent
```

Final Answer Agent는 `contexts`의 `title`, `url`, `content`, `reliability`를 함께 사용하여 답변과 출처를 구성한다.

## 11. 1차 구현 한계

현재 구현은 1차 POC 수준이므로 다음 한계가 있다.

- Tavily API 키가 필요하다.
- Tavily 응답 품질은 검색 API 결과와 허용 도메인 설정에 영향을 받는다.
- DuckDuckGo fallback 사용 시 검색 엔진 HTML 구조 변경에 영향을 받을 수 있다.
- 관련도 점수는 임베딩 기반이 아니라 단순 토큰 겹침 기반이다.
- 공식 문서의 동적 렌더링 영역은 완전히 추출되지 않을 수 있다.
- 중복 문서 제거와 날짜 기반 최신성 판단은 최소 수준이다.
- 수집 결과를 PGVector나 PostgreSQL에 저장하지 않고 메모리에서만 반환한다.

## 12. 다음 개선 방향

향후 개선 시 다음 항목을 추가할 수 있다.

- 문서 날짜 추출 및 최신성 가중치 반영
- PGVector 기반 문서 임베딩 검색 연동
- 공식 문서와 커뮤니티 문서 신뢰도 분리 강화
- 검색 결과 캐싱
- RAGAS 기반 Web RAG 검색 품질 평가
- Final Answer Agent용 출처 포맷 표준화
