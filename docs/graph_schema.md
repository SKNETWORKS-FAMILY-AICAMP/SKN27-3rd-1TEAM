# 메이플스토리 Neo4j GraphDB 스키마 정의 문서

## 1. 기준 파일

본 GraphDB 스키마는 팀 프로젝트의 기준 데이터 구조 파일인 `common/domain.py`를 중심으로 정의한다.

추가로 `docs/openapi.yaml`은 외부 API 입력/출력에서 어떤 값이 들어오고 나가는지 확인하는 보조 기준으로 사용한다.

```text
기준 모델: common/domain.py
API 명세: docs/openapi.yaml
```

## 2. 설계 원칙

모든 분석 로직은 `domain.py`의 domain 모델을 기준으로 작성되어야 한다. 따라서 GraphDB도 API 응답 원본 구조가 아니라, 내부 분석 모델에 맞춰 노드와 관계를 구성한다.

핵심 중심 노드는 `ProcessedCharacter`이다.

```text
ProcessedCharacter
 ├─ CharacterStatDetail
 ├─ EquipmentDetail
 │   ├─ total_stats: StatPackage
 │   ├─ bonus_stats: StatPackage
 │   └─ scroll_stats: StatPackage
 ├─ UnionStatus
 │   └─ union_raider_stats: StatPackage
 ├─ AbilityInfo
 └─ GrowthEfficiencyReport
```

## 3. 노드 정의

| 노드 | domain.py 기준 | 설명 | 주요 속성 |
|---|---|---|---|
| `ProcessedCharacter` | `ProcessedCharacter` | 모든 분석의 기준이 되는 통합 캐릭터 모델 | `character_name`, `job_name`, `world_name`, `level`, `gender` |
| `CharacterStatDetail` | `CharacterStatDetail` | 게임 내 스탯창 결과 데이터 | `combat_power`, `min_stat_damage`, `max_stat_damage`, `str_val`, `dex`, `int_val`, `luk`, `damage`, `boss_damage`, `ignore_def`, `crit_rate`, `crit_damage`, `arcane_force`, `authentic_force` |
| `EquipmentDetail` | `EquipmentDetail` | 개별 장비 상세 정보 | `item_name`, `part`, `item_gender`, `starforce`, `potential_grade`, `additional_potential_grade`, `set_name` |
| `StatPackage` | `StatPackage` | 장비/스킬/유니온 등이 가진 스탯 묶음 | `str_val`, `dex_val`, `int_val`, `luk_val`, `attack_power`, `magic_power`, `hp`, `boss_damage_percent`, `ignore_def_percent`, `final_damage_percent`, `damage_percent`, `crit_damage`, `all_stat_percent` |
| `UnionStatus` | `UnionStatus` | 유니온 및 아티팩트 정보 | `union_level`, `union_grade`, `artifact_level`, `artifact_exp` |
| `AbilityInfo` | `ProcessedCharacter.ability_info` | 어빌리티 옵션 목록 | `ability_id`, `preset_no`, `ability_grade`, `ability_value` |
| `ActionPlan` | `ActionPlan` | 성장 추천 액션 | `category`, `target`, `priority`, `expected_cp_gain`, `description` |
| `GrowthEfficiencyReport` | `GrowthEfficiencyReport` | 최종 분석 및 리포트 | `character_id`, `current_combat_power`, `data_reliability`, `timestamp`, `attack`, `boss_damage`, `ignore_def`, `crit_rate`, `crit_damage`, `damage` |
| `RankingRecord` | API/전처리 보조 데이터 | 랭킹 기록 | `ranking_type`, `date`, `ranking`, `character_name`, `world_name`, `class_name`, `character_level`, `union_level`, `union_power` |
| `Source` | OpenAPI `Source` 참고 | RAG/분석 답변 출처 | `title`, `url`, `reliability`, `document_type`, `text_preview_1000` |
| `World` | 보조 노드 | 월드 | `world_name` |
| `Job` | 보조 노드 | 직업 | `job_name` |
| `Guild` | 보조 노드 | 길드 | `guild_name` |

## 4. 관계 정의

| 관계 | 시작 노드 | 끝 노드 | 의미 |
|---|---|---|---|
| `BELONGS_TO_WORLD` | `ProcessedCharacter` | `World` | 캐릭터가 특정 월드에 속함 |
| `HAS_JOB` | `ProcessedCharacter` | `Job` | 캐릭터의 직업 |
| `MEMBER_OF_GUILD` | `ProcessedCharacter` | `Guild` | 캐릭터의 길드 |
| `HAS_FINAL_STATS` | `ProcessedCharacter` | `CharacterStatDetail` | 캐릭터의 최종 스탯 상세 |
| `HAS_EQUIPMENT` | `ProcessedCharacter` | `EquipmentDetail` | 캐릭터가 보유/착용한 장비 |
| `HAS_TOTAL_STATS` | `EquipmentDetail` | `StatPackage` | 장비 최종 합산 옵션 |
| `HAS_BONUS_STATS` | `EquipmentDetail` | `StatPackage` | 장비 추가 옵션 |
| `HAS_SCROLL_STATS` | `EquipmentDetail` | `StatPackage` | 주문서/업그레이드 옵션 |
| `HAS_UNION` | `ProcessedCharacter` | `UnionStatus` | 캐릭터의 유니온 정보 |
| `HAS_RAIDER_STATS` | `UnionStatus` | `StatPackage` | 유니온 공격대원 합산 스탯 |
| `HAS_ABILITY_INFO` | `ProcessedCharacter` | `AbilityInfo` | 캐릭터의 어빌리티 옵션 |
| `HAS_REPORT` | `ProcessedCharacter` | `GrowthEfficiencyReport` | 캐릭터 분석 리포트 |
| `RECOMMENDS` | `GrowthEfficiencyReport` | `ActionPlan` | 리포트가 추천 액션을 포함함 |
| `USES_SOURCE` | `GrowthEfficiencyReport` | `Source` | 분석 결과가 사용한 출처 |
| `RECORDED_IN_RANKING` | `ProcessedCharacter` 또는 `CharacterName` | `RankingRecord` | 랭킹 기록 |

## 5. 현재 1차 구축 데이터 매핑

현재 1차 구축은 이미 생성된 `content_split_csv`만 사용한다.

| CSV | domain 모델 매핑 | 처리 방식 |
|---|---|---|
| `json_main__character_basic.csv` | `ProcessedCharacter` | 캐릭터 기본 프로필 생성 |
| `json_main__character_ability.csv` | `AbilityInfo` | `ProcessedCharacter`와 연결 |
| `json_main__user_union.csv` | `UnionStatus` | `ProcessedCharacter`와 연결 |
| `json_list__character_item_equipment__*.csv` | `EquipmentDetail`, `StatPackage` | 부모 캐릭터 식별자가 없어 장비 카탈로그로 생성 |
| `json_list__character_stat__final_stat.csv` | `CharacterStatDetail` | 부모 캐릭터 식별자가 없어 스탯 카탈로그로 생성 |
| `json_list__ranking_*__ranking.csv` | `RankingRecord` | 캐릭터명 기준으로 연결 |
| `html_content_summary.csv` | `Source` | RAG 출처 후보로 생성 |

## 6. 현재 1차 구축 한계

전처리된 리스트형 CSV에서 `ocid`, `character_name`, `file_name` 등 부모 식별자가 제거되어 있으므로 다음 관계는 현재 1차 구축 단계에서 완전하게 만들 수 없다.

```text
(ProcessedCharacter)-[:HAS_EQUIPMENT]->(EquipmentDetail)
(ProcessedCharacter)-[:HAS_FINAL_STATS]->(CharacterStatDetail)
```

실제 서비스용 전처리에서는 장비, 스탯, 심볼, 유니온 블록 리스트에도 최소한 아래 값을 유지해야 한다.

```text
ocid
character_name
```

## 7. Agent 연동 방식

GraphDB 조회 결과는 Final Answer Agent가 사용할 수 있는 domain 모델 형태의 JSON으로 반환한다.

예시:

```json
{
  "character": {
    "character_name": "Baddy",
    "job_name": "카데나",
    "world_name": "크로아",
    "level": 300
  },
  "union_info": {
    "union_level": 9000,
    "union_grade": "그랜드 마스터"
  },
  "equipment_candidates": [
    {
      "item_name": "하이네스 원더러햇",
      "part": "모자",
      "total_stats": {
        "str_val": 173,
        "dex_val": 341,
        "attack_power": 0
      }
    }
  ],
  "sources": [
    {
      "title": "문서 제목",
      "reliability": "MEDIUM"
    }
  ]
}
```

이 구조는 `Analystic Agent`, `Calculator Agent`, `Final Answer Agent`가 공통 domain 모델 기준으로 데이터를 해석할 수 있게 한다.
