from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional


@dataclass
class Stats:
    """Final character stats used by calculation agents."""

    attack: int = 0
    crit_rate: float = 0.0
    crit_damage: float = 0.0
    boss_damage: float = 0.0
    ignore_def: float = 0.0
    damage: float = 0.0
    attack_speed: int = 0


@dataclass
class StatPackage:
    """A bundle of additive and percentage stat values."""

    str_val: int = 0
    dex_val: int = 0
    int_val: int = 0
    luk_val: int = 0
    attack_power: int = 0
    magic_power: int = 0
    hp: int = 0
    boss_damage_percent: float = 0.0
    ignore_def_percent: float = 0.0
    final_damage_percent: float = 0.0
    damage_percent: float = 0.0
    crit_damage: float = 0.0
    all_stat_percent: float = 0.0


@dataclass
class Equipment:
    name: str
    slot: str
    starforce: int = 0
    stats: StatPackage = field(default_factory=StatPackage)


@dataclass
class EquipmentDetail:
    """Detailed equipment information from the Open API."""

    item_name: str
    part: str
    item_gender: Optional[str] = None
    starforce: Optional[int] = None
    potential_grade: Optional[str] = None
    additional_potential_grade: Optional[str] = None
    total_stats: Optional[StatPackage] = None
    bonus_stats: Optional[StatPackage] = None
    scroll_stats: Optional[StatPackage] = None
    set_name: Optional[str] = None


@dataclass
class CharacterStatDetail:
    """Current stat window values for a processed character."""

    combat_power: int = 0
    min_stat_damage: float = 0.0
    max_stat_damage: float = 0.0
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
    starforce: int = 0


@dataclass
class UnionStatus:
    union_level: int = 0
    union_grade: str = ""
    artifact_level: Optional[int] = None
    artifact_exp: int = 0
    union_raider_stats: Optional[StatPackage] = None


@dataclass
class CharacterAbility:
    union_level: int = 0
    arcane_force: int = 0
    authentic_force: int = 0


@dataclass
class Character:
    ocid: str
    level: int
    char_class: str
    stats: Stats = field(default_factory=Stats)
    equipment: List[Equipment] = field(default_factory=list)
    ability: CharacterAbility = field(default_factory=CharacterAbility)


@dataclass
class ProcessedCharacter:
    """Integrated character model used by all analysis agents."""

    character_name: str
    job_name: str
    world_name: str
    level: int
    gender: Optional[str] = None
    final_stats: Optional[CharacterStatDetail] = None
    equipment_list: List[EquipmentDetail] = field(default_factory=list)
    union_info: Optional[UnionStatus] = None
    v_matrix: Optional[Dict[str, int]] = None
    hexa_core: Optional[Dict[str, int]] = None
    ability_info: Optional[List[str]] = None
    hyper_stats: Optional[Dict[str, int]] = None
    active_buffs: List[str] = field(default_factory=list)


