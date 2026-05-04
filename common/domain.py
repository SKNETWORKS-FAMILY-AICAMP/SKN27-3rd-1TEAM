from dataclasses import dataclass
from typing import List


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

    # 계산 기여 스탯 (핵심만 유지)
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