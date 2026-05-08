# GraphDB 스키마 정의서

## 1. 설계 기준

본 GraphDB는 유저의 실시간 캐릭터 상태를 저장하는 DB가 아니라, 메이플스토리의 게임 지식 관계를 저장하는 GraphDB이다.

실시간으로 바뀌는 캐릭터 레벨, 장비, 스탯, 유니온, 어빌리티 정보는 NEXON Open API를 통해 조회하고, `common/domain.py`의 `ProcessedCharacter`, `CharacterStatDetail`, `EquipmentDetail`, `StatPackage`, `UnionStatus` 모델로 변환하여 `common/state.py` 기준 `analystic`/Calculator Agent에서 사용한다.

GraphDB는 `common/domain.py`의 분석 모델이 필요로 하는 판단 근거를 제공하기 위해 다음 고정성/관계성 데이터를 저장한다.

- 직업
- 보스
- 장비 카탈로그
- 세트 효과
- 스탯 요구조건
- 이벤트
- 보상
- 콘텐츠
- 문서 출처 관계

추가 데이터셋을 적재할 때도 GraphDB 담당 범위인 직업, 보스, 아이템, 이벤트 간 관계 정의와 쿼리 지원에 필요한 데이터만 선별한다.

## 2. 노드 정의

| 노드 | 설명 | 주요 속성 |
|---|---|---|
| `Job` | 메이플스토리 직업 | `job_id`, `name`, `job_group`, `main_stat`, `description` |
| `Boss` | 보스 몬스터 | `boss_id`, `name`, `difficulty`, `boss_type`, `required_level`, `description` |
| `EquipmentCatalog` | 장비 카탈로그 | `equipment_id`, `name`, `part`, `slot`, `item_type`, `level_limit`, `set_name` |
| `SetEffect` | 장비 세트 효과 | `set_effect_id`, `name`, `set_type`, `description` |
| `StatRequirement` | 보스/콘텐츠 요구 스펙 | `requirement_id`, `boss_name`, `level`, `main_stat`, `boss_damage`, `ignore_def`, `arcane_force`, `authentic_force`, `confidence` |
| `Event` | 이벤트 정보 | `event_id`, `name`, `event_type`, `start_date`, `end_date`, `target_user`, `description` |
| `Reward` | 보상 정보 | `reward_id`, `name`, `reward_type`, `value_type`, `description` |
| `Content` | 일일/주간/성장 콘텐츠 | `content_id`, `name`, `content_type`, `reset_cycle`, `description` |
| `Source` | RAG/문서 출처 | `source_id`, `title`, `category`, `source_type`, `relative_path`, `url`, `trust_level`, `collected_at`, `text_preview`, `reliability` (`HIGH`, `MEDIUM`, `LOW`) |
| `StatType` | 공통 스탯 종류 | `stat_type_id`, `code`, `domain_field`, `description` |

## 3. 관계 정의

| 관계 | 시작 노드 | 끝 노드 | 의미 |
|---|---|---|---|
| `USES_MAIN_STAT` | `Job` | `StatType` | 직업이 주스탯으로 사용하는 스탯 |
| `RECOMMENDED_FOR_JOB` | `EquipmentCatalog` | `Job` | 특정 장비가 직업군/직업에게 추천됨 |
| `PART_OF_SET` | `EquipmentCatalog` | `SetEffect` | 장비가 특정 세트 효과에 포함됨 |
| `HAS_REQUIREMENT` | `Boss` | `StatRequirement` | 보스가 요구 스펙을 가짐 |
| `DROPS_REWARD` | `Boss` | `Reward` | 보스가 보상을 드롭함 |
| `PROVIDES_REWARD` | `Event` | `Reward` | 이벤트가 보상을 제공함 |
| `RELATED_CONTENT` | `Event` | `Content` | 이벤트와 관련된 콘텐츠 |
| `HELPS_GROWTH` | `Event` | `Content` | 이벤트가 성장 콘텐츠 수행에 도움 |
| `REQUIRES_STAT` | `StatRequirement` | `StatType` | 요구 조건이 어떤 domain.py 스탯 필드를 기준으로 하는지 표시 |
| `MENTIONED_IN` | `StatType/Job/Boss/EquipmentCatalog/Event/Content/Reward` | `Source` | 문서 출처에서 엔티티가 언급됨 |

## 4. 추가 데이터 선별 기준

`maple_chatbot_final_dataset.csv`를 추가 적재할 때는 다음 기준으로 중복과 역할 범위를 제한한다.

| 기준 | 처리 방식 |
|---|---|
| 중복 제거 | `dedup_group_key`, `dedup_rank=1`, `dedup_action=keep*` 기준으로 1차 제거 |
| 최종 사용 여부 | `is_final_keep=True`, `rag_ready=True` 데이터만 사용 |
| 포함 데이터 | `official_event`, `official_notice`, `official_update`, `testworld_update`, `boss_recommendation_rule`, `equipment_growth_rule`, `reward_priority_rule`, `class_5th_core_priority`, `class_6th_hexa_priority` |
| 제외 데이터 | `character_*`, `user_union*`, `ranking_*` 등 유저 실시간 상태 또는 샘플 API 데이터 |
| 적재 방향 | 새 복잡한 도메인 노드를 늘리기보다 `Job`, `Boss`, `EquipmentCatalog`, `Event`, `Reward`, `Source`에 연결 |

추가 데이터의 주요 활용 관계는 다음과 같다.

```text
(Boss)-[:HAS_REQUIREMENT]->(StatRequirement)
(Boss)-[:DROPS_REWARD]->(Reward)
(Job)-[:MENTIONED_IN]->(Source)
(EquipmentCatalog)-[:MENTIONED_IN]->(Source)
(Event)-[:MENTIONED_IN]->(Source)
```

## 5. domain.py와의 연결

GraphDB는 `common/domain.py` 객체를 직접 저장하는 것이 아니라, domain 모델이 분석할 때 필요한 기준 지식을 제공한다.

예시:

1. `analystic` Agent가 NEXON API로 `ProcessedCharacter`를 생성한다.
2. 캐릭터의 `job_name`, `level`, `final_stats`, `equipment_list`를 확인한다.
3. GraphDB에서 해당 직업의 주스탯, 추천 장비, 도전 가능한 보스 요구조건, 성장 콘텐츠를 조회한다.
4. Calculator Agent가 `StatPackage`와 `CharacterStatDetail`을 기반으로 계산한다.
5. Final Answer Agent가 GraphDB 근거와 API 실시간 상태를 종합한다.

## 6. 예시 조회

```cypher
MATCH (j:Job {name: "아델"})-[:USES_MAIN_STAT]->(s:StatType)
RETURN j.name, s.code, s.domain_field;
```

```cypher
MATCH (b:Boss {name: "노멀 스우"})-[:HAS_REQUIREMENT]->(r:StatRequirement)
RETURN b.name, r.level, r.main_stat, r.boss_damage, r.ignore_def;
```

```cypher
MATCH (e:Event)-[:PROVIDES_REWARD]->(r:Reward)
RETURN e.name, r.name, r.reward_type;
```

```cypher
MATCH (b:Boss)-[:HAS_REQUIREMENT]->(r:StatRequirement)
MATCH (b)-[:MENTIONED_IN]->(s:Source)
WHERE r.confidence <> "draft"
RETURN b.name, b.difficulty, r.level, r.main_stat, s.title
LIMIT 10;
```

```cypher
MATCH (e:Event {event_type: "official_event"})-[:MENTIONED_IN]->(s:Source)
RETURN e.name, s.url, s.trust_level
ORDER BY e.name;
```

## 7. 1차 구축 한계

현재 seed 데이터는 1차 설계 및 Agent 연동용 기준 데이터이다. 보스 요구 스펙, 이벤트, 보상, 추천 장비 관계는 팀 검증 후 수치와 관계를 보완해야 한다.

공식 문서나 Web RAG가 수집한 문서는 `Source` 노드로 저장하고, 추후 엔티티 추출을 통해 `MENTIONED_IN` 관계를 확장한다.



