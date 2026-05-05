# 머신 러닝 모델 디자인: 보스 클리어 예측기

---

## 1. 목표

캐릭터의 현재 스펙(스탯, 장비, 유니온 등)을 기반으로 특정 보스 클리어 가능 여부를 예측하는 이진 분류(Binary Classification) 머신러닝 모델을 학습한다.

- **입력**: 캐릭터 스펙 데이터 (스탯창 수치, 장비 옵션, 유니온 정보 등)
- **출력**: 특정 보스 클리어 성공 확률 (0.0 ~ 1.0) 및 클리어 가능 여부 (True / False)
- **서비스 연계**: `POST /analysis/boss` API의 `boss_clear_prediction` 필드에 모델 추론 결과를 제공

---

## 2. 데이터 수집 및 파이프라인

### 2-1. 데이터 수집 경로 (OpenAPI 기반)

| API 엔드포인트 | 수집 데이터 | 대응 도메인 모델 |
|---|---|---|
| `GET /maplestory/v1/character/stat` | 스탯창 수치 전체 | `CharacterStatDetail` |
| `GET /maplestory/v1/character/item-equipment` | 장비별 상세 옵션, 강화수치, 잠재등급 | `EquipmentDetail`, `StatPackage` |
| `GET /maplestory/v1/character/set-effect` | 세트효과 적용 여부 | `EquipmentDetail.set_name` |
| `GET /maplestory/v1/character/vmatrix` | V코어 레벨 | `ProcessedCharacter.v_matrix` |

### 2-2. 레이블(Label) 정의

- `POST /analysis/boss` 요청 시 실제 클리어 성공/실패 기록을 수집하거나, 커뮤니티/공식 데이터를 기반으로 보스별 권장 스펙 임계값을 레이블로 활용한다.
- 레이블: `boss_clear_success: 0 (실패) / 1 (성공)`
- 보스별로 별도 모델 또는 멀티 레이블 분류(Multi-label)로 확장 가능

### 2-3. 전처리

- `CharacterStatDetail`의 `None` 필드는 0으로 대체
- `EquipmentDetail`의 `potential_grade`는 순서형 인코딩 (노멀=0, 레어=1, 에픽=2, 유니크=3, 레전더리=4)
- `starforce`는 수치형 그대로 사용, 누락 시 0 처리
- 잠재 등급, 세트 이름 등 범주형 변수는 Label Encoding 또는 One-Hot Encoding 적용
- 전체 피처 스케일링: XGBoost는 스케일 불변이므로 선택적으로 적용 (해석 목적 시에만)

---

## 3. 피처 엔지니어링

### 3-1. CharacterStatDetail 기반 피처 (스탯창 결과값)

> `domain.py`의 `CharacterStatDetail` 클래스 및 OpenAPI `Stats` 스키마 대응

| 피처명 | 설명 | 타입 |
|---|---|---|
| `combat_power` | 전투력 | int |
| `boss_damage` | 보스 데미지 (%) | float |
| `final_damage` | 최종 데미지 (%) | float |
| `ignore_def` | 방어율 무시 (%) | float |
| `crit_rate` | 크리티컬 확률 (%) | float |
| `crit_damage` | 크리티컬 데미지 (%) | float |
| `attack_power` | 공격력 | int |
| `damage` | 데미지 (%) | float |
| `arcane_force` | 아케인포스 합계 | int |
| `authentic_force` | 어센틱포스 합계 | int |

### 3-2. StatPackage 기반 피처 (장비 옵션 합산)

> `domain.py`의 `StatPackage` 클래스 및 OpenAPI `StatPackage` 스키마 대응

장비 전체의 `total_stats`, `bonus_stats`, `scroll_stats`를 부위별/전체 합산하여 피처로 구성

| 피처명 | 설명 | 타입 |
|---|---|---|
| `total_attack_power_sum` | 전 장비 공격력 합산 | int |
| `total_boss_damage_sum` | 전 장비 보스 데미지 합산 (%) | float |
| `total_ignore_def_sum` | 전 장비 방어율 무시 합산 (%) | float |
| `total_final_damage_sum` | 전 장비 최종 데미지 합산 (%) | float |
| `total_crit_damage_sum` | 전 장비 크리티컬 데미지 합산 (%) | float |
| `bonus_attack_power_sum` | 추가옵션 공격력 합산 | int |
| `bonus_boss_damage_sum` | 추가옵션 보스 데미지 합산 (%) | float |
| `scroll_attack_power_sum` | 주문서 공격력 합산 | int |

### 3-3. EquipmentDetail 기반 피처 (장비 개별 메타)

> `domain.py`의 `EquipmentDetail` 클래스 및 OpenAPI `Equipment` 스키마 대응

| 피처명 | 설명 | 타입 |
|---|---|---|
| `weapon_starforce` | 무기 스타포스 수치 | int |
| `avg_starforce` | 전 장비 평균 스타포스 | float |
| `legendary_potential_count` | 레전더리 잠재 장비 수 | int |
| `unique_potential_count` | 유니크 잠재 장비 수 | int |
| `set_effect_count` | 적용 중인 세트 효과 종류 수 | int |
| `weapon_potential_grade_enc` | 무기 잠재 등급 (순서형 인코딩) | int |
| `sub_weapon_potential_grade_enc` | 보조무기 잠재 등급 (순서형 인코딩) | int |
| `emblem_potential_grade_enc` | 엠블렘 잠재 등급 (순서형 인코딩) | int |

### 3-4. 파생 피처 (Feature Engineering)

보스 클리어 판단에 복합적으로 영향을 미치는 계산 피처

| 피처명 | 계산식 | 설명 |
|---|---|---|
| `effective_damage_index` | `(1 + boss_damage/100) × (1 + final_damage/100) × attack_power` | 실질 보스 딜 지표 |
| `ignore_def_composite` | `1 - Π(1 - ignore_def_i/100)` | 복합 방무 실효값 |
| `crit_contribution` | `crit_rate × crit_damage / 100` | 크리티컬 기대 기여값 |
| `potential_tier_score` | 잠재 등급 가중 합산 | 전체 잠재 수준 점수 |
| `starforce_tier_score` | 부위별 스타포스 가중 합산 | 전체 강화 수준 점수 |

---

## 4. 모델링

### 4-1. 알고리즘: XGBoost (Gradient Boosting)

- **선택 이유**:
  - 수치형/범주형 혼합 피처에 강건
  - 피처 중요도(Feature Importance) 제공 → 병목 분석(`/analysis/bottleneck`)과 시너지
  - 스케일 불변 → 전처리 부담 최소화
  - 소/중규모 데이터셋에서 높은 성능

### 4-2. 학습 설정

```python
import xgboost as xgb

model = xgb.XGBClassifier(
    objective='binary:logistic',   # 이진 분류
    eval_metric='auc',             # AUC 기반 평가
    n_estimators=300,
    max_depth=6,
    learning_rate=0.05,
    subsample=0.8,
    colsample_bytree=0.8,
    use_label_encoder=False,
    random_state=42
)
```

### 4-3. 다중 보스 지원 전략

- **방법 1 (권장)**: 보스별 독립 이진 분류 모델 학습
  - 예: `model_normal_cygnus`, `model_chaos_vellum`, `model_chaos_black_mage` 등
  - `boss_clear_prediction: Dict[str, bool]` (`GrowthEfficiencyReport` 필드)에 각 모델 추론 결과 매핑
- **방법 2**: 단일 모델 + 보스 난이도 레벨을 피처로 추가 (빠른 프로토타이핑용)

---

## 5. 모델 학습 과정

```
[데이터 수집]
  ↓ OpenAPI (캐릭터 스탯, 장비, V매트릭스)
[전처리]
  ↓ 결측치 처리 / 범주형 인코딩 / 파생 피처 생성
[학습/검증 분할]
  ↓ Stratified K-Fold (k=5), 보스별 클리어 비율 유지
[XGBoost 학습]
  ↓ Early Stopping (validation AUC 기준)
[Threshold 튜닝]
  ↓ Precision-Recall 곡선 기반 최적 임계값 선택
[모델 저장]
  ↓ joblib 직렬화 → 보스별 모델 파일 저장
[서빙]
  ↓ /analysis/boss API → boss_clear_prediction 응답 필드 채움
```

---

## 6. 모델 평가

| 지표 | 설명 | 목표값 |
|---|---|---|
| AUC-ROC | 클리어/실패 분류 능력 | ≥ 0.85 |
| Precision | 클리어 예측 정밀도 (오탐 방지) | ≥ 0.80 |
| Recall | 실제 클리어 가능 케이스 탐지율 | ≥ 0.80 |
| F1-Score | Precision × Recall 조화평균 | ≥ 0.80 |
| Log Loss | 확률 출력 품질 | ≤ 0.35 |

- **교차검증**: Stratified 5-Fold CV로 과적합 방지
- **피처 중요도 분석**: 상위 피처를 `/analysis/bottleneck` 병목 분석 로직에 피드백
- **모델 갱신 주기**: 넥슨 데이터 갱신 정책(30일)에 맞춰 정기 재학습

---

## 7. 결과물 및 서비스 연동

### 7-1. 모델 출력

```python
# 단일 캐릭터, 단일 보스 추론 예시
prob = model.predict_proba(feature_vector)[0][1]  # 클리어 확률
result = prob >= threshold  # True / False

# GrowthEfficiencyReport.boss_clear_prediction 예시
{
  "카오스 벨룸": True,
  "하드 윌": False,
  "카오스 블랙 마지": False
}
```

### 7-2. API 연동 포인트

| API | 연동 방식 |
|---|---|
| `POST /analysis/boss` → `boss_clear_prediction` | 캐릭터 스펙 피처 추출 후 모델 추론, 확률 및 T/F 반환 |
| `POST /analysis/bottleneck` → `recommended_actions` | 피처 중요도 기반으로 우선 개선 부위(`ActionPlan`) 도출 |
| `POST /prediction/growth` → `recommendations` | 현재 스펙 대비 목표 보스 달성에 필요한 스펙 델타 계산 |

### 7-3. 신뢰도 표기

- 모델 예측 확률을 `ApiResponseBase.confidence` 필드에 반영
- `GrowthEfficiencyReport.data_reliability`에 모델 버전 및 학습 데이터 출처 명시
