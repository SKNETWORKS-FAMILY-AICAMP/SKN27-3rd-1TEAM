from dataclasses import dataclass
from typing import List
from dataclasses import field


@dataclass
class Stats:
    # 최종 합산 스탯 (계산 입력)
    attack: int
    crit_rate: float
    crit_damage: float
    boss_damage: float
    ignore_def: float
    damage: float
    attack_speed: int


@dataclass
class Equipment:
    # 기본 정보
    name: str
    slot: str
    starforce: int

    # 계산 기여 스탯 (핵심만 유지)from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any

@dataclass
class StatPackage:
    """아이템이나 스킬 하나가 가진 스탯 묶음"""
    str_val: int = 0
    dex_val: int = 0
    int_val: int = 0
    luk_val: int = 0
    attack_power: int = 0
    magic_power: int = 0
    hp: int = 0
    
    # % 단위 옵션
    boss_damage_percent: float = 0.0
    ignore_def_percent: float = 0.0
    final_damage_percent: float = 0.0
    damage_percent: Optional[float] = 0.0
    crit_damage: Optional[float] = 0.0
    all_stat_percent: float = 0.0

@dataclass
class EquipmentDetail:
    """개별 장비의 상세 정보"""
    item_name: str
    part: str
    item_gender: Optional[str] = None
    starforce: Optional[int] = None
    potential_grade: Optional[str] = None
    additional_potential_grade: Optional[str] = None
    
    # 옵션 세분화 (성장 효율 분석의 핵심)
    total_stats: Optional[StatPackage] = None  # 최종 합산 옵션
    bonus_stats: Optional[StatPackage] = None  # 추가옵션 (추옵)
    scroll_stats: Optional[StatPackage] = None # 주문서/업그레이드 수치
    
    # 세트 효과 명칭
    set_name: Optional[str] = None

@dataclass
class CharacterStatDetail:
    """게임 내 스탯창(결과 데이터) 상세 정보"""
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
    """유니온 및 아티팩트 정보"""
    union_level: int = 0
    union_grade: str = ""
    artifact_level: Optional[int] = None
    artifact_exp: int = 0
    # 유니온 공격대원으로 얻는 합산 스탯
    union_raider_stats: Optional[StatPackage] = None

@dataclass
class ActionPlan:
    """성장 추천 액션 아이템"""
    category: str  # 예: "장비강화", "내실", "큐브"
    target: str    # 예: "앱솔랩스 숄더"
    priority: int  # 1 (매우 높음) ~ 5 (낮음)
    expected_cp_gain: int  # 예상 전투력 상승치
    description: str

@dataclass
class ProcessedCharacter:
    """통합 캐릭터 모델 (모든 분석의 기준점)"""
    # 기본 프로필
    character_name: str
    job_name: str
    world_name: str
    level: int
    gender: Optional[str] = None
    
    # 스탯창 정보 (결과)
    final_stats: Optional[CharacterStatDetail] = None
    
    # 성장 데이터 (원인)
    equipment_list: List[EquipmentDetail] = field(default_factory=list)
    union_info: Optional[UnionStatus] = None
    v_matrix: Optional[Dict[str, int]] = None  # 코어 이름 : 레벨
    hexa_core: Optional[Dict[str, int]] = None # 코어 이름 : 레벨
    ability_info: Optional[List[str]] = None   # 어빌리티 옵션 목록
    hyper_stats: Optional[Dict[str, int]] = None
    
    # 임시/시뮬레이션 데이터
    active_buffs: List[str] = field(default_factory=list)

@dataclass
class GrowthEfficiencyReport:
    """최종 분석 및 리포트 모델"""
    character_id: str
    current_combat_power: int
    
    # 부위별 성장 여력 분석 (Bottleneck)
    # 예: {"무기": 0.85, "보조무기": 0.4} (숫자가 낮을수록 성장 필요도 높음)
    bottleneck_analysis: Dict[str, float] = field(default_factory=dict)
    
    # 추천 가이드
    recommended_actions: List[ActionPlan] = field(default_factory=list)
    
    # 보스 도전 가능 여부
    boss_clear_prediction: Optional[Dict[str, bool]] = None
    
    # 출처 및 신뢰도 정보
    data_reliability: str = ""
    timestamp: str = ""
    attack: int
    boss_damage: float
    ignore_def: float
    crit_rate: float
    crit_damage: float
    damage: float


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