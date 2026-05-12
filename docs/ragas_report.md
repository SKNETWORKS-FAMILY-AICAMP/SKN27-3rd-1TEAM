# RAGAS 평가 리포트

2026-05-11 기준 로컬 프로젝트 데이터와 실제 RAG 실행 결과로 작성한 RAGAS 평가 리포트입니다.

## 팀 공유 요약

이번 평가는 기존처럼 하나의 공통 20문항을 `pgvector`, `graph`, `web`에 모두 넣어 비교하는 방식이 아니라, 각 RAG가 실제로 담당해야 하는 범위에 맞는 질문을 20개씩 따로 구성해 평가했습니다.

이렇게 분리한 이유는 RAG별 역할이 다르기 때문입니다. 예를 들어 Web RAG는 최신 공식 공지나 외부 웹 문서를 찾는 역할인데, 보스 요구 스펙이나 직업 주스탯처럼 GraphDB에 있는 질문까지 Web RAG에 넣으면 Web RAG의 실제 담당 범위를 벗어난 평가가 됩니다. 따라서 이번 리포트는 각 RAG의 고유 역할을 기준으로 평가셋을 다시 나누었습니다.

평가 결과는 다음과 같습니다.

| RAG | 담당 범위 질문 수 | context 생성 | RAGAS 산출 행 |
| --- | ---: | ---: | ---: |
| `pgvector` | 20 | 20 | 20 |
| `graph` | 20 | 20 | 20 |
| `web` | 20 | 20 | 20 |

최종적으로 총 60개 행에 대해 RAGAS 점수를 산출했고, context 미달로 제외된 행은 없습니다.

## 평가 목적

이번 평가의 목적은 세 RAG를 같은 질문으로 무리하게 경쟁시키는 것이 아니라, 프로젝트 안에서 각 RAG가 맡는 역할을 제대로 수행하는지 확인하는 것입니다.

| RAG | 평가 목적 |
| --- | --- |
| `pgvector` | PostgreSQL/PGVector에 적재된 공식 문서, 위키형 보조 문서, 정제 룰 문서를 잘 검색하는지 확인 |
| `graph` | Neo4j에 적재된 직업, 주스탯, 보스 요구 스펙 같은 구조화 관계 정보를 잘 검색하는지 확인 |
| `web` | 메이플스토리 공식 웹 사이트의 최신 공지, 이벤트, 업데이트 문서를 잘 검색하는지 확인 |

따라서 이번 결과는 "전체 최종 답변 품질" 평가가 아니라, RAG별 검색원 품질과 답변 근거 품질을 분리해서 본 1차 평가입니다. 최종 MultiAgent 답변 품질 평가는 supervisor, research, final answer agent가 연결된 뒤 별도 end-to-end 평가로 진행하는 것이 맞습니다.

## 평가셋

이번에 새로 만든 범위별 평가셋은 다음과 같습니다.

| 파일 | 대상 RAG | 질문 수 | 질문 범위 |
| --- | --- | ---: | --- |
| `src/evaluation/evaluation_ragas_pgvector_scoped.csv` | `pgvector` | 20 | 공식 이벤트, 공식 업데이트, 테스트월드, 위키형 보조 문서, 코어/HEXA/룰 문서 |
| `src/evaluation/evaluation_ragas_graph_scoped.csv` | `graph` | 20 | 직업군, 주스탯, 보스별 요구 스펙 |
| `src/evaluation/evaluation_ragas_web_scoped.csv` | `web` | 20 | 공식 웹 사이트의 공지, 이벤트, 업데이트, 테스트월드 문서 |

기존 `src/evaluation/evaluation_ragas.csv`는 20문항 안에 `pgvector`, `graph`, `web` 범위가 섞여 있었습니다. 이 방식에서는 Web RAG가 DB/Graph 전용 질문까지 받게 되어 context coverage가 낮아졌습니다. 이번 scoped 평가셋은 그 문제를 줄이기 위해 RAG별 담당 범위에 맞게 질문을 다시 나눈 것입니다.

## 평가 방법

평가 흐름은 다음과 같습니다.

1. RAG별 담당 범위에 맞는 평가 질문 20개를 작성합니다.
2. 각 RAG를 실제로 실행해 context를 수집합니다.
3. 수집된 context 기반으로 extractive 답변을 생성합니다.
4. rule-based 평가로 기본 형식과 context 보유 여부를 확인합니다.
5. RAGAS로 `faithfulness`, `answer_relevancy`, `context_precision`, `context_recall`을 산출합니다.

답변 생성은 `extractive` 모드로 수행했습니다. 이는 RAGAS 점수를 검색 context 품질 중심으로 보기 위해서입니다. LLM 답변 생성까지 포함하면 답변 모델의 생성 성향이 점수에 섞일 수 있으므로, 이번 1차 평가는 context에서 직접 추출한 답변을 기준으로 했습니다.

RAGAS 평가 모델은 프로젝트 공통 규칙에 맞춰 `common.get_model`의 설정을 사용했습니다.

| 항목 | 사용 설정 |
| --- | --- |
| LLM | `common.get_model.get_llm()` |
| Embedding | `common.get_model.get_embedding_model()` |
| 필요 환경변수 | `GROQ_API_KEY`, `OPENAI_API_KEY` |
| Web RAG 필요 환경변수 | `TAVILY_API_KEY` |

## 산출 파일

이번 평가 결과는 다음 위치에 생성되었습니다.

| 파일 | 설명 |
| --- | --- |
| `src/evaluation/results/scoped_ragas/pgvector_contexts.csv` | PGVector RAG context 생성 결과 |
| `src/evaluation/results/scoped_ragas/graph_contexts.csv` | Graph RAG context 생성 결과 |
| `src/evaluation/results/scoped_ragas/web_contexts.csv` | Web RAG context 생성 결과 |
| `src/evaluation/results/scoped_ragas/scoped_ragas_with_answer.csv` | 세 RAG 결과를 합친 RAGAS 입력 파일 |
| `src/evaluation/results/scoped_ragas/answer_eval_summary.csv` | rule-based 평가 요약 |
| `src/evaluation/results/scoped_ragas/ragas_scores.csv` | RAGAS 문항별 점수 |
| `src/evaluation/results/scoped_ragas/ragas_summary.csv` | RAGAS RAG별 평균 점수 |

`src/evaluation/results/` 하위 CSV는 실행 결과물이므로 Git 공유 대상이 아니라 로컬 산출물로 관리하는 것이 적절합니다. 팀 공유 시에는 리포트와 평가셋 CSV를 공유하고, 결과 CSV는 필요할 때 재생성하는 방식을 권장합니다.

## 검색 Coverage

| rag_type | context 보유 행 | 전체 행 | coverage |
| --- | ---: | ---: | ---: |
| `pgvector` | 20 | 20 | 1.000 |
| `graph` | 20 | 20 | 1.000 |
| `web` | 20 | 20 | 1.000 |

이전 혼합형 평가에서는 Web RAG가 20개 중 12개만 RAGAS 산출 대상이었습니다. 이번에는 Web RAG가 담당해야 하는 공식 웹 문서 질문만 따로 구성했기 때문에 20개 모두 context를 반환했습니다.

따라서 기존 결과의 "Web RAG 12/20"은 Web RAG 자체가 항상 40% 실패한다는 의미가 아니라, 기존 평가셋 안에 Web RAG 담당 범위를 벗어난 질문이 섞여 있었다는 신호로 해석하는 것이 맞습니다.

## Rule-Based 평가

| rag_type | has_answer | has_context | has_source_citation | context_overlap | rule_passed |
| --- | ---: | ---: | ---: | ---: | ---: |
| `graph` | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |
| `pgvector` | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |
| `web` | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |

Rule-based 평가는 답변이 존재하는지, context가 있는지, citation 형식이 있는지, 답변과 context가 기본적으로 겹치는지를 확인하는 사전 검증입니다. 세 RAG 모두 20문항에서 기본 형식 검증을 통과했습니다.

## RAGAS 요약

| rag_type | faithfulness | answer_relevancy | context_precision | context_recall |
| --- | ---: | ---: | ---: | ---: |
| `graph` | 0.9632 | 0.3095 | 0.7580 | 0.8500 |
| `pgvector` | 0.8947 | 0.1737 | 0.9182 | 0.8500 |
| `web` | 0.7117 | 0.1693 | 0.4186 | 0.4000 |

RAGAS 입력 파일은 총 60행이며, 각 RAG별로 20행씩 산출되었습니다. 네 metric 모두 결측값 없이 계산되었습니다.

## 결과 해석

### PGVector RAG

`pgvector`는 `context_precision`이 0.9182로 가장 높습니다. 이는 공식 문서, 위키형 보조 문서, 코어/HEXA 우선순위, 정제 룰 문서처럼 문서 단위 검색이 필요한 질문에서 관련 context를 비교적 잘 가져온다는 의미입니다.

`faithfulness`도 0.8947로 높아, 생성된 답변이 검색된 context에 근거하는 정도가 안정적입니다. `context_recall`은 0.8500으로 양호하지만, 일부 질문에서는 기준 정답의 모든 세부 요소를 검색 context가 완전히 포괄하지 못했습니다.

`answer_relevancy`가 0.1737로 낮은 것은 현재 답변 생성이 extractive 방식이라 원문 context를 길게 끌고 오는 경향이 있고, RAGAS의 answer relevancy가 질문에 딱 맞는 자연어 답변을 선호하기 때문입니다. 따라서 이 값은 검색 실패만 의미하지 않고, 답변 생성 방식의 영향도 함께 받은 결과입니다.

### Graph RAG

`graph`는 `faithfulness`가 0.9632로 가장 높고, `context_recall`도 0.8500입니다. 직업군, 주스탯, 보스 요구 스펙처럼 구조화된 엔티티와 관계를 묻는 질문에서는 GraphDB가 강점을 보였습니다.

`context_precision`은 0.7580으로 준수하지만, 일부 보스 요구 스펙 질문에서는 관련 graph fact와 함께 덜 필요한 관계 문맥이 섞이면서 정밀도가 낮아졌습니다. 그래도 이번 scoped 평가에서는 Graph RAG가 맡아야 할 범위에서는 충분히 유효한 검색원으로 확인되었습니다.

`answer_relevancy`는 0.3095로 세 RAG 중 가장 높지만, 절대값은 높지 않습니다. 이 역시 extractive 답변이 원문 형식을 그대로 가져오는 영향이 있습니다. 향후 final answer agent가 graph context를 자연어로 재구성하면 개선될 가능성이 큽니다.

### Web RAG

`web`은 이번 scoped 평가에서 20/20 context를 반환했습니다. 이전 혼합형 평가에서 12/20에 그쳤던 것과 비교하면, Web RAG도 담당 범위 질문으로 평가하면 coverage는 확보할 수 있습니다.

다만 RAGAS 점수는 `faithfulness` 0.7117, `context_precision` 0.4186, `context_recall` 0.4000으로 낮습니다. 이유는 공식 사이트 검색 결과가 상세 공지 본문만 가져오는 것이 아니라 목록 페이지, 주변 공지, 이벤트 링크 모음, 일부 스니펫을 함께 가져오는 경우가 있기 때문입니다.

즉 Web RAG는 "공식 웹에서 무언가를 찾는 능력"은 있지만, "질문과 직접 맞는 상세 페이지 본문만 정밀하게 가져오는 능력"은 아직 개선이 필요합니다.

## 기존 혼합형 평가와의 차이

기존 평가 결과는 다음과 같았습니다.

| 항목 | 기존 혼합형 평가 |
| --- | ---: |
| 평가 질문 수 | 20 |
| 생성 행 수 | 60 |
| RAGAS 산출 행 수 | 52 |
| `pgvector` 산출 | 20 |
| `graph` 산출 | 20 |
| `web` 산출 | 12 |
| Web 제외 행 | 8 |

이 결과만 보면 Web RAG가 불안정해 보이지만, 실제로는 20개 질문이 각 RAG의 담당 범위에 맞게 분리되어 있지 않았습니다. 보스 스펙, 직업 주스탯, 정제 룰 문서 같은 질문은 Web RAG보다 Graph RAG 또는 PGVector RAG의 담당 범위입니다.

이번 scoped 평가에서는 이 문제를 보정했습니다.

| 항목 | scoped 평가 |
| --- | ---: |
| `pgvector` 전용 질문 | 20 |
| `graph` 전용 질문 | 20 |
| `web` 전용 질문 | 20 |
| 전체 생성 행 | 60 |
| RAGAS 산출 행 | 60 |
| context 미달 제외 행 | 0 |

따라서 앞으로 보고할 때는 기존 혼합형 결과를 "초기 통합 비교"로 두고, 실제 RAG별 성능 판단은 이번 scoped 결과를 기준으로 삼는 것이 적절합니다.

## 하이브리드 RAG 관점

프로젝트의 최종 구조는 단일 RAG가 아니라 하이브리드 RAG입니다. 따라서 `pgvector`, `graph`, `web`은 서로 경쟁하는 검색원이 아니라 역할이 다른 검색원입니다.

권장 라우팅 방향은 다음과 같습니다.

| 질문 유형 | 우선 RAG | 보조 RAG |
| --- | --- | --- |
| 공식 공지, 이벤트, 업데이트, 테스트월드 문서 | `pgvector` | `web` |
| 최신 공지, 현재 진행 이벤트, 웹에서 다시 확인해야 하는 정보 | `web` | `pgvector` |
| 직업군, 주스탯, 보스 요구 스펙, 엔티티 관계 | `graph` | `pgvector` |
| 코어 강화, HEXA 우선순위, 보조 룰 문서 | `pgvector` | `graph` |

이 구조에서 `web`은 모든 질문을 처리하는 기본 검색원이 아니라 최신성 검증과 공식 웹 재확인을 위한 보조 검색원으로 쓰는 것이 맞습니다. `pgvector`는 문서 기반 기본 검색원, `graph`는 구조화 관계 검색원으로 구분하는 것이 평가 결과와도 잘 맞습니다.

## 개선 권장 사항

1. Web RAG는 공식 상세 URL 우선순위를 강화해야 합니다.
   - 현재는 공식 사이트 목록 페이지나 주변 링크가 context에 섞이는 경우가 있습니다.
   - `/News/Event/`, `/News/Notice/`, `/News/Update/`, `/testworld/news/` 상세 페이지를 우선하는 rerank가 필요합니다.

2. Web RAG는 query rewrite가 필요합니다.
   - 이벤트 제목, 날짜, "메이플스토리 공식", "공지", "업데이트" 같은 키워드를 명시적으로 붙이면 상세 페이지 검색률이 올라갈 수 있습니다.

3. Graph RAG는 질문 유형 라우팅을 적용하는 것이 좋습니다.
   - graph는 구조화 관계 질문에는 강하지만, 서술형 공식 문서 질문에는 불필요한 관계 context가 섞일 수 있습니다.
   - supervisor나 retriever router에서 보스/직업/스탯 질문일 때 graph를 우선 호출하는 방식이 적절합니다.

4. PGVector RAG는 현재 DB RAG baseline으로 유지할 수 있습니다.
   - 문서 검색 정밀도가 가장 높으므로 공식 문서, 위키, 룰 문서 검색의 기본 검색원으로 두는 것이 좋습니다.

5. 최종 답변 품질 평가는 별도로 해야 합니다.
   - 이번 평가는 RAG별 검색 context 품질 평가입니다.
   - MultiAgent가 연결된 뒤에는 supervisor routing, final answer 생성, citation 품질까지 포함한 end-to-end 평가셋이 필요합니다.

## 재현 시 주의사항

로컬에서 재실행하려면 다음 환경이 필요합니다.

| 항목 | 필요 조건 |
| --- | --- |
| PostgreSQL | `maplestory-postgres` 컨테이너 실행 |
| Neo4j | `maplestory-neo4j` 컨테이너 실행 |
| Python | 프로젝트 `.venv` 사용 |
| RAGAS LLM | `.env`에 `GROQ_API_KEY` 필요 |
| RAGAS Embedding | `.env`에 `OPENAI_API_KEY` 필요 |
| Web RAG | `.env`에 `TAVILY_API_KEY` 필요 |

PowerShell 기준 주요 실행 명령 예시는 다음과 같습니다.

```powershell
.\.venv\Scripts\python.exe -m src.evaluation.ragas_eval make-contexts src\evaluation\evaluation_ragas_pgvector_scoped.csv src\evaluation\results\scoped_ragas\pgvector_contexts.csv --rag-types pgvector --top-k 5
.\.venv\Scripts\python.exe -m src.evaluation.ragas_eval make-contexts src\evaluation\evaluation_ragas_graph_scoped.csv src\evaluation\results\scoped_ragas\graph_contexts.csv --rag-types graph --top-k 5
.\.venv\Scripts\python.exe -m src.evaluation.ragas_eval make-contexts src\evaluation\evaluation_ragas_web_scoped.csv src\evaluation\results\scoped_ragas\web_contexts.csv --rag-types web --top-k 5
.\.venv\Scripts\python.exe -m src.evaluation.ragas_eval answer src\evaluation\results\scoped_ragas\pgvector_contexts.csv src\evaluation\results\scoped_ragas\pgvector_with_answer.csv --mode extractive --overwrite
.\.venv\Scripts\python.exe -m src.evaluation.ragas_eval answer src\evaluation\results\scoped_ragas\graph_contexts.csv src\evaluation\results\scoped_ragas\graph_with_answer.csv --mode extractive --overwrite
.\.venv\Scripts\python.exe -m src.evaluation.ragas_eval answer src\evaluation\results\scoped_ragas\web_contexts.csv src\evaluation\results\scoped_ragas\web_with_answer.csv --mode extractive --overwrite
.\.venv\Scripts\python.exe -c "import pandas as pd, pathlib; outdir=pathlib.Path('src/evaluation/results/scoped_ragas'); files=[outdir/'pgvector_with_answer.csv', outdir/'graph_with_answer.csv', outdir/'web_with_answer.csv']; pd.concat([pd.read_csv(f) for f in files], ignore_index=True).to_csv(outdir/'scoped_ragas_with_answer.csv', index=False)"
.\.venv\Scripts\python.exe -m src.evaluation.ragas_eval evaluate src\evaluation\results\scoped_ragas\scoped_ragas_with_answer.csv --output-csv src\evaluation\results\scoped_ragas\ragas_scores.csv --use-common-models
.\.venv\Scripts\python.exe -m src.evaluation.ragas_eval summary src\evaluation\results\scoped_ragas\ragas_scores.csv --output-csv src\evaluation\results\scoped_ragas\ragas_summary.csv
```

실제 실행 시에는 세 RAG의 answered CSV를 하나로 합친 `scoped_ragas_with_answer.csv`를 만든 뒤 RAGAS를 실행해야 합니다.

## 최종 판단

이번 scoped 평가 기준으로는 `pgvector`와 `graph`가 각각 문서 검색과 구조화 관계 검색에서 안정적으로 동작합니다. `web`도 담당 범위 질문에서는 context를 모두 반환했지만, 검색 정밀도와 기준 정답 포괄성은 아직 낮습니다.

따라서 현재 단계의 결론은 다음과 같습니다.

1. DB Search RAG의 기본 검색원은 `pgvector`로 두는 것이 적절합니다.
2. 보스, 직업, 스탯, 요구 스펙 질문은 `graph`를 함께 사용하는 것이 좋습니다.
3. 최신 공식 공지 확인이 필요한 질문에는 `web`을 보조 검색원으로 사용합니다.
4. RAGAS 결과만 보면 Web RAG는 coverage보다 precision 개선이 우선입니다.
5. 최종 프로젝트 평가에서는 RAG별 단독 평가와 MultiAgent end-to-end 평가를 분리해야 합니다.
