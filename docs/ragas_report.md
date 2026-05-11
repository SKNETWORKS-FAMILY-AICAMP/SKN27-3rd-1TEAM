# RAGAS 평가 리포트

2026-05-11 기준 로컬 프로젝트 데이터로 생성한 RAGAS 평가 결과입니다.

## 팀 공유 요약

RAGAS 평가 업무를 완료했습니다.

1. 평가셋
   - 실제 프로젝트 데이터 기준으로 RAGAS 평가셋 20문항을 작성했습니다.
   - 평가 대상 RAG는 `pgvector`, `graph`, `web`입니다.

2. 평가 실행
   - `pgvector`, `graph`, `web` 각각 실제 검색을 실행해 context를 수집했습니다.
   - 수집된 context 기반으로 LLM 답변을 생성했습니다.
   - rule-based 평가와 RAGAS 평가를 모두 실행했습니다.
   - RAGAS metric은 `faithfulness`, `answer_relevancy`, `context_precision`, `context_recall`입니다.

3. 결과 요약
   - `pgvector`: 20/20 context 반환, 현재 가장 안정적인 baseline입니다.
   - `graph`: 20/20 context 반환, 관계형 질문에는 유용하지만 답변 관련성과 정밀도 개선이 필요합니다.
   - `web`: Tavily API 적용 후 12/20 context 반환, 최신 정보 보완용 보조 RAG로 사용하는 것이 적절합니다.

4. 하이브리드 RAG 관점
   - 최종 구조가 하이브리드 RAG라면 `web`이 전체 질문을 단독으로 커버할 필요는 없습니다.
   - `pgvector`와 `graph`를 기본 검색원으로 두고, `web`은 최신 공지나 외부 정보 질문에서 보조 검색원으로 쓰는 방향이 적절합니다.
   - 단, `web` 단독 coverage는 60%이므로 query rewrite, Tavily 옵션, 공식 사이트 우선순위, 필터링 개선이 필요합니다.

5. 산출물
   - RAGAS 평가셋: `src/evaluation/evaluation_ragas.csv`
   - 샘플 평가셋: `src/evaluation/sample_ragas_eval.csv`
   - 최종 리포트: `docs/ragas_report.md`
   - 결과 CSV는 `src/evaluation/results/`에 생성되지만 Git에는 올리지 않도록 `.gitignore` 처리했습니다.

6. 재현 시 주의사항
   - 팀 공용 실행은 `common/get_model.py`의 `ChatGroq` 설정 기준입니다.
   - `GROQ_API_KEY`가 필요합니다.
   - Web RAG 재현에는 `TAVILY_API_KEY`가 필요합니다.

## 평가 설계

이 평가 산출물은 DB Search RAG, PGVector, GraphDB, Web RAG의 검색 결과와 답변 품질을 RAGAS로 비교하기 위한 것입니다. 평가 범위는 `src/evaluation/`이며, 공용 계약인 `common/`과 실제 RAG 구현인 `src/rag/`는 수정하지 않았습니다.

평가 데이터는 강의자료의 RAGAS 흐름을 프로젝트 구조에 맞춘 형태입니다.

1. `evaluation_ragas.csv`에 평가 질문, 기준 정답, 기준 근거 문맥을 준비합니다.
2. `pgvector`, `graph`, `web` RAG를 각각 실행해 검색 문맥을 수집합니다.
3. 수집된 문맥만을 근거로 LLM 답변을 생성합니다.
4. rule-based 평가로 기본 품질을 먼저 확인합니다.
5. RAGAS로 `faithfulness`, `answer_relevancy`, `context_precision`, `context_recall`을 산출합니다.
6. RAG별 평균 점수와 약점을 정리합니다.

## RAGAS 스키마

RAGAS 0.4.x 실행 시 필요한 컬럼은 다음과 같습니다.

| 컬럼 | 의미 |
| --- | --- |
| `user_input` | 평가 질문 |
| `response` | RAG 문맥을 기반으로 생성한 답변 |
| `retrieved_contexts` | RAG가 검색한 문맥 목록 |
| `reference` | 기준 정답 |

강의자료의 중간 산출물 컬럼인 `question`, `contexts`, `answer`, `ground_truth`도 내부 유틸에서 읽을 수 있도록 맞춰두었습니다.

## 재현 실행 기준

팀 공용 재현 실행에서는 `common/get_model.py`의 `ChatGroq` 설정을 사용합니다. 실행 전 `GROQ_API_KEY`가 환경 변수 또는 `.env`에 설정되어 있어야 합니다.

```powershell
uv run python -m src.evaluation.ragas_eval make-contexts src\evaluation\evaluation_ragas.csv src\evaluation\results\evaluation_ragas_contexts.csv --rag-types pgvector graph web --top-k 3
uv run python -m src.evaluation.ragas_eval answer src\evaluation\results\evaluation_ragas_contexts.csv src\evaluation\results\evaluation_ragas_with_answer.csv --mode llm --overwrite
uv run python -m src.evaluation.answer_eval evaluate src\evaluation\results\evaluation_ragas_with_answer.csv --output-csv src\evaluation\results\answer_eval_scores.csv
uv run python -c "import pandas as pd; from src.evaluation.ragas_eval import parse_contexts; df = pd.read_csv('src/evaluation/results/evaluation_ragas_with_answer.csv'); df[df['contexts'].apply(lambda v: len(parse_contexts(v)) > 0)].to_csv('src/evaluation/results/evaluation_ragas_ragas_input.csv', index=False)"
uv run python -m src.evaluation.ragas_eval evaluate src\evaluation\results\evaluation_ragas_ragas_input.csv --output-csv src\evaluation\results\ragas_scores.csv --use-common-models
uv run python -m src.evaluation.ragas_eval summary src\evaluation\results\ragas_scores.csv --output-csv src\evaluation\results\ragas_summary.csv
```

이번 로컬 실행 환경에는 `GROQ_API_KEY`가 없어, 코드 수정 없이 명령 안에서만 `gpt-4o-mini`와 `text-embedding-3-small`을 주입해 20문항 결과를 재생성했습니다. 팀 제출 또는 공동 재현 시에는 위 명령처럼 ChatGroq 기반 공용 설정으로 다시 실행하는 것이 기준입니다.

## Web RAG 실행 조건

Web RAG의 기본 검색 경로는 Tavily입니다. 처음에는 `TAVILY_API_KEY`가 없어 `duckduckgo` 경로로 우회 실행했으며, 이때 Web RAG coverage는 0/20이었습니다.

이후 `TAVILY_API_KEY`를 설정한 뒤 Tavily 경로로 재실행했고, Web RAG coverage가 12/20으로 개선되었습니다. 다만 여전히 전체 질문을 모두 커버하지 못했고, RAGAS 점수도 `pgvector`, `graph`보다 낮게 나왔습니다.

## 평가 범위

- 평가셋: `src/evaluation/evaluation_ragas.csv`
- 평가 대상 RAG: `pgvector`, `graph`, `web`
- 질문 수: 20개
- 생성 행 수: 60개
- RAGAS 점수 산출 행 수: 52개
- RAGAS 점수 산출 대상: `pgvector` 20개, `graph` 20개, `web` 12개
- Web RAG 점수 제외 행: 8개 - context coverage 미달
- 평가 metric: `faithfulness`, `answer_relevancy`, `context_precision`, `context_recall`

## 검색 커버리지

| rag_type | context 보유 행 | 전체 행 | coverage |
| --- | ---: | ---: | ---: |
| pgvector | 20 | 20 | 1.000 |
| graph | 20 | 20 | 1.000 |
| web | 12 | 20 | 0.600 |

`pgvector`와 `graph`는 모든 평가 질문에서 context를 반환했습니다. `web`은 Tavily 키 적용 후 12개 질문에서 context를 반환했습니다.

## Rule-Based 평가

| rag_type | has_context | context_overlap | rule_passed |
| --- | ---: | ---: | ---: |
| pgvector | 1.000 | 0.513 | 1.000 |
| graph | 1.000 | 0.204 | 0.900 |
| web | 0.600 | 0.137 | 0.550 |

`pgvector`는 전체 질문에서 문맥과 답변 형식 검증을 통과했습니다. `graph`는 일부 답변에서 citation 또는 문맥 overlap 문제가 있었고, `web`은 coverage 부족과 일부 citation 문제로 통과율이 낮았습니다.

## RAGAS 요약

| rag_type | scored_rows | faithfulness | answer_relevancy | context_precision | context_recall |
| --- | ---: | ---: | ---: | ---: | ---: |
| pgvector | 20 | 0.928 | 0.352 | 0.725 | 0.500 |
| graph | 20 | 0.713 | 0.082 | 0.471 | 0.500 |
| web | 12 | 1.000 | 0.131 | 0.292 | 0.250 |

Web RAG는 context가 있는 12개 행만 RAGAS 점수에 포함되었습니다. 따라서 Web RAG 점수는 전체 20문항 coverage를 함께 고려해야 합니다.

## 하이브리드 RAG 관점

최종 서비스가 하이브리드 RAG 구조라면 Web RAG가 전체 20문항을 단독으로 모두 처리할 필요는 없습니다. 현재 평가셋에는 DB 내부 데이터, 캐릭터 스펙, 장비, 코어, 보스, 이벤트/공지성 질문이 함께 포함되어 있으므로, `pgvector`와 `graph`는 기본 검색원으로 사용하고 `web`은 최신 공지나 외부 정보가 필요한 질문에서 보조 검색원으로 사용하는 것이 적합합니다.

따라서 Web RAG 단독 coverage가 12/20이라는 결과는 하이브리드 최종 답변이 곧바로 실패한다는 의미는 아닙니다. 다만 Web RAG만 따로 평가하면 coverage가 60%에 머물기 때문에, 최신성 질문을 맡는 보조 RAG로서 query rewrite, Tavily 검색 옵션, 공식 사이트 도메인 우선순위, 검색 결과 필터링 개선이 필요합니다.

보고 시에는 `pgvector`와 `graph`는 안정적인 내부 지식 검색원이고, `web`은 Tavily 적용 후 개선되었지만 현재는 최신 정보 보완용 보조 검색원이라는 점을 함께 전달하는 것이 안전합니다.

## 해석

1. `pgvector`가 현재 가장 안정적인 baseline입니다.
   - 20개 질문 모두에서 문맥을 검색했습니다.
   - `faithfulness`, `answer_relevancy`, `context_precision`에서 가장 높았습니다.
   - 다만 `context_recall`은 0.500으로, 기준 정답을 충분히 포괄하지 못한 질문이 남아 있습니다.

2. `graph`는 관계형 질문에 유용하지만 답변 관련성과 문맥 정밀도가 낮았습니다.
   - 20개 질문 모두에서 문맥을 검색했습니다.
   - 보스, 직업, 스탯처럼 구조화된 엔티티 관계를 찾는 데 활용 가치가 있습니다.
   - 이벤트 문서나 서술형 규칙 질문에서는 불필요한 관계 문맥이 섞여 `answer_relevancy`와 `context_precision`이 낮게 나왔습니다.

3. `web`은 Tavily 적용 후 coverage가 개선되었지만 아직 보조 RAG 수준입니다.
   - coverage는 0/20에서 12/20으로 개선되었습니다.
   - scored row 기준 `faithfulness`는 높지만, `answer_relevancy`, `context_precision`, `context_recall`은 낮았습니다.
   - 최신 이벤트/공지 검색에는 필요하지만, 검색 결과 필터링과 문맥 정밀도 개선이 필요합니다.

## 개선 권장 사항

1. `pgvector`를 기본 DB RAG baseline으로 유지합니다.
2. `graph`는 보스, 직업, 스탯, 장비 관계형 질문의 보조 retriever로 사용하는 것이 적합합니다.
3. Graph RAG는 이벤트/문서형 질문에서 관계 문맥이 과도하게 섞이지 않도록 query routing 또는 필터링이 필요합니다.
4. Web RAG는 Tavily 기반 검색 coverage를 더 높이고, 공식 사이트 결과 중 질문과 직접 관련된 문맥만 남기도록 필터링이 필요합니다.
5. Web RAG 개선 후 같은 20문항으로 RAGAS를 다시 실행해 coverage와 `context_precision` 변화를 확인하는 것이 좋습니다.

## 현재 남긴 산출물

Git에 남길 파일:

- `src/evaluation/evaluation_ragas.csv`
- `src/evaluation/sample_ragas_eval.csv`
- `docs/ragas_report.md`

로컬 결과 CSV:

- `src/evaluation/results/evaluation_ragas_with_answer.csv`
- `src/evaluation/results/answer_eval_summary.csv`
- `src/evaluation/results/ragas_scores.csv`
- `src/evaluation/results/ragas_summary.csv`

`src/evaluation/results/*.csv`는 Git을 깔끔하게 유지하기 위해 `.gitignore` 처리되어 있습니다.
