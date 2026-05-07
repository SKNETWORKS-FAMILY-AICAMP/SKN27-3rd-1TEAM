from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class Stats:
    # 최종 계산 스탯
    attack: int
    crit_rate: float
    crit_damage: float
    boss_damage: float
    ignore_def: float
    damage: float
    attack_speed: int


@dataclass
class Equipment:
    # 기본 장비 정보
    name: str
    slot: str
    starforce: int

    # 계산 기여 스탯


@dataclass
class StatPackage:
    """장비, 세트 효과, 유니온 등이 가지는 스탯 묶음."""

    str_val: int = 0
    dex_val: int = 0
    int_val: int = 0
    luk_val: int = 0
    attack_power: int = 0
    magic_power: int = 0
    hp: int = 0

    # 퍼센트 단위 옵션
    boss_damage_percent: float = 0.0
    ignore_def_percent: float = 0.0
    final_damage_percent: float = 0.0
    damage_percent: Optional[float] = 0.0
    crit_damage: Optional[float] = 0.0
    all_stat_percent: float = 0.0


@dataclass
class EquipmentDetail:
    """개별 장비의 상세 정보."""

    item_name: str
    part: str
    item_gender: Optional[str] = None
    starforce: Optional[int] = None
    potential_grade: Optional[str] = None
    additional_potential_grade: Optional[str] = None

    # 옵션 원천별 스탯
    total_stats: Optional[StatPackage] = None  # 최종 합산 옵션
    bonus_stats: Optional[StatPackage] = None  # 추가 옵션
    scroll_stats: Optional[StatPackage] = None  # 주문서/업그레이드 수치

    # 세트 효과 이름
    set_name: Optional[str] = None


@dataclass
class CharacterStatDetail:
    """게임 내 스탯창 기준 상세 스탯 정보."""

    combat_power: int = 0
    min_stat_damage: float = 0
    max_stat_damage: float = 0
    str_val: int = 0
    dex: int = 0
    int_val: int = 0
    luk: int = 0
    hp: int = 0
    mp: int = 0
    damage: float = 0.0
    boss_damage: float = 0.0
    final_damage: float = 0.0
    ignore_def: float = 0.0
    crit_rate: float = 0.0
    crit_damage: float = 0.0
    attack_power: int = 0
    magic_power: int = 0
    attack_speed: int = 0
    buff_duration: int = 0
    arcane_force: int = 0
    authentic_force: int = 0


@dataclass
class UnionStatus:
    """유니온 및 아티팩트 정보."""

    union_level: int = 0
    union_grade: str = ""
    artifact_level: Optional[int] = None
    artifact_exp: int = 0

    # 유니온 공격대원 효과로 얻는 합산 스탯
    union_raider_stats: Optional[StatPackage] = None


@dataclass
class ActionPlan:
    """성장 추천 액션 아이템."""

    category: str  # 예: 장비 강화, 심볼, 유니온
    target: str  # 예: 장갑, 아케인심볼
    priority: int  # 1이 가장 높고 5가 가장 낮음
    expected_cp_gain: int  # 예상 전투력 상승치
    description: str


@dataclass
class ProcessedCharacter:
    """통합 캐릭터 모델."""

    # 기본 프로필
    character_name: str
    job_name: str
    world_name: str
    level: int
    gender: Optional[str] = None

    # 스탯창 정보
    final_stats: Optional[CharacterStatDetail] = None

    # 성장 데이터
    equipment_list: List[EquipmentDetail] = field(default_factory=list)
    union_info: Optional[UnionStatus] = None
    v_matrix: Optional[Dict[str, int]] = None  # 코어 이름: 레벨
    hexa_core: Optional[Dict[str, int]] = None  # 코어 이름: 레벨
    ability_info: Optional[List[str]] = None  # 어빌리티 옵션 목록
    hyper_stats: Optional[Dict[str, int]] = None

    # 임시/버프 데이터
    active_buffs: List[str] = field(default_factory=list)


@dataclass
class GrowthEfficiencyReport:
    """최종 분석 및 리포트 모델."""

    character_id: str
    current_combat_power: int
    attack: int
    boss_damage: float
    ignore_def: float
    crit_rate: float
    crit_damage: float
    damage: float

    # 부위별 성장 여력 분석
    # 예: {"무기": 0.85, "보조무기": 0.4}
    bottleneck_analysis: Dict[str, float] = field(default_factory=dict)

    # 추천 가이드
    recommended_actions: List[ActionPlan] = field(default_factory=list)

    # 보스 클리어 가능 여부
    boss_clear_prediction: Optional[Dict[str, bool]] = None

    # 출처 및 신뢰도 정보
    data_reliability: str = ""
    timestamp: str = ""


@dataclass
class CharacterAbility:
    union_level: int
    arcane_force: int
    authentic_force: int


@dataclass
class Character:
    ocid: str
    level: int
    char_class: str

    stats: Stats
    equipment: List[Equipment]
    ability: CharacterAbility
