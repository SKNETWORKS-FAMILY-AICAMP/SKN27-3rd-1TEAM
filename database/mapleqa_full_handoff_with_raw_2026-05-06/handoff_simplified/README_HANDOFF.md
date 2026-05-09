# MapleStory Chatbot Dataset Handoff

## 전달본 구성

이 폴더는 메이플스토리 챗봇 개발자에게 전달하기 위한 간단 패키지입니다.
현재 폴더 안에서 실제로 사용해야 하는 파일은 아래 4개입니다.

| 파일 | 설명 |
|---|---|
| `maple_chatbot_final_dataset.csv` | 최종 챗봇용 통합 데이터셋 |
| `mapleqa_eda_for_chatbot.ipynb` | 현재 데이터셋 기준 EDA/인수인계 노트북 |
| `dataset_summary.csv` | 최종 데이터셋 요약 |
| `README_HANDOFF.md` | 이 설명 파일 |

원본 raw 데이터는 상위 폴더의 `data/raw/`에 보존되어 있습니다.

## 최종 데이터셋

챗봇 개발자는 우선 아래 파일 하나를 사용하면 됩니다.

`maple_chatbot_final_dataset.csv`

현재 기준:

- 3,567행
- 25컬럼
- 약 69.91MB
- 전체 행의 `rag_ready` 값은 `True`
- UTF-8 CSV

이 파일에는 다음 데이터가 하나의 스키마로 통합되어 있습니다.

| 범위 | 행 수 |
|---|---:|
| NEXON API 정적 샘플 | 1,824 |
| 추가 수집 wiki 문서 | 1,338 |
| 공식 문서 | 67 |
| 보스/장비 추천 룰 | 197 |
| 추천 검수/가드레일 보강 데이터 | 27 |
| 한국어 스토리 요약 seed | 12 |
| 직업별 5차 코어 우선순위 seed | 47 |
| 직업별 6차 HEXA 우선순위 seed | 47 |
| 시세/이벤트 강화 타이밍 seed | 8 |

## 주요 컬럼

| 컬럼 | 설명 |
|---|---|
| `unified_id` | 통합 문서 ID |
| `category` | 데이터 카테고리 |
| `chatbot_purpose` | 챗봇에서의 사용 목적 |
| `collection_scope` | 수집/생성 범위 |
| `title` | 제목 |
| `source_type` | 출처 유형 |
| `trust_level` | 신뢰도/검수 상태 |
| `source_url` | 원문 또는 로컬 규칙 출처 |
| `tags` | 검색/필터용 태그 |
| `rag_ready` | RAG 인덱싱 가능 여부 |
| `handoff_warning` | 인수인계 주의사항 |
| `rag_text` | 임베딩/검색에 사용할 본문 |

## 추천 기능 사용 기준

보스 추천과 장비 성장 추천 관련 데이터도 `maple_chatbot_final_dataset.csv` 안에 포함되어 있습니다.
별도 CSV로 나뉘어 있던 추천 룰, 검수 큐, API 요구사항, 답변 가드레일과 추가 보강 seed 데이터는 최종 데이터셋에 `collection_scope`로 구분되어 들어가 있습니다.

추천 기능을 구현할 때는 다음 값을 필터링해서 사용하면 됩니다.

| `collection_scope` | 용도 |
|---|---|
| `supplemental_recommendation_rules` | 보스/장비 추천 룰 |
| `supplemental_recommendation_review_support` | API 요구사항, 답변 가드레일, 추가 보강 백로그 |
| `supplemental_korean_story_summary` | 아케인리버/테네브리스 지역별 한국어 스토리 요약 seed |
| `supplemental_class_5th_core_priority` | 직업별 5차 코어 강화 우선순위 seed |
| `supplemental_class_6th_hexa_priority` | 직업별 6차 HEXA 강화 우선순위 seed |
| `supplemental_market_event_upgrade_timing` | 시세/이벤트 기반 강화 타이밍 판단 seed |

주의: 보스 컷, 장비 성장 수치, 보상 가치는 프로젝트용 1차 기준입니다.
정답형 답변을 만들 수는 있지만, API 실시간 연동 전에는 사용자가 직접 입력한 스펙을 기준으로 계산하는 방식이 적합합니다.

## 권장 개발 흐름

1. `maple_chatbot_final_dataset.csv`를 로드합니다.
2. `rag_ready == True` 행의 `rag_text`를 임베딩합니다.
3. `category`, `collection_scope`, `trust_level`, `source_url`을 메타데이터로 유지합니다.
4. 일반 Q&A는 wiki/official 문서를 검색합니다.
5. 보스/장비 추천은 `supplemental_recommendation_rules` 행을 기준 룰로 사용합니다.
6. 추천 답변 문구는 `supplemental_recommendation_review_support` 행의 가드레일을 참고합니다.
7. 나중에 NEXON Open API를 붙이면 캐릭터명 기반 개인화 추천으로 확장합니다.

## 현재 한계

- 이벤트 이미지 OCR 데이터는 제외되어 있습니다.
- 캐릭터 분석은 최종적으로 NEXON Open API 실시간 연동이 필요합니다.
- 한국어 공식 스토리는 대사 전문 복제가 아니라 지역별 요약 seed로 보강했습니다.
- 직업별 5차 코어/6차 HEXA 강화 우선순위는 seed 데이터로 보강했으며, 정확한 스킬명/효율 순서는 팀 검수가 필요합니다.
- 서버별 시세와 스타포스/큐브 이벤트 기반 강화 타이밍은 일반 판단 seed로 보강했으며, 실시간 시세/현재 이벤트 일정은 별도 수집 또는 수동 입력이 필요합니다.
- 보스 컷/장비 성장 기준은 정답형 답변에 쓰기 전 팀 검수를 권장합니다.

## 압축 파일

상위 폴더의 `mapleqa_chatbot_handoff_simplified_2026-05-06.zip`은 이 폴더의 4개 파일을 그대로 압축한 전달용 파일입니다.
