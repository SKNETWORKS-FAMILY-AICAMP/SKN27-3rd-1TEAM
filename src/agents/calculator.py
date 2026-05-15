from __future__ import annotations

import re
from dataclasses import asdict, is_dataclass
from typing import Any, Dict, List


from langchain_core.tools import tool
from pydantic import BaseModel, Field

from common.state import AgentState
from common.validator import validate_agent_inputs, validate_agent_outputs


class DamageSimulationInput(BaseModel):
    """Input schema for relative damage simulation."""

    character_level: int = Field(0, ge=0)
    combat_power: int = Field(0, ge=0)
    main_stat: int = Field(0, ge=0)
    attack_power: int = Field(0, ge=0)
    magic_power: int = Field(0, ge=0)
    damage: float = Field(0.0, ge=0)
    boss_damage: float = Field(0.0, ge=0)
    final_damage: float = Field(0.0, ge=0)
    ignore_def: float = Field(0.0, ge=0)
    crit_rate: float = Field(0.0, ge=0)
    crit_damage: float = Field(0.0, ge=0)
    arcane_force: int = Field(0, ge=0)
    authentic_force: int = Field(0, ge=0)
    starforce: int = Field(0, ge=0)
    union_level: int = Field(0, ge=0)


class EquipmentSummaryInput(BaseModel):
    """Input schema for summarizing equipment contribution."""

    equipment_items: List[Dict[str, Any]] = Field(default_factory=list)
    character_level: int = Field(0, ge=0)
    main_stat: int = Field(0, ge=0)
    attack_power: int = Field(0, ge=0)
    magic_power: int = Field(0, ge=0)


class GrowthForecastInput(BaseModel):
    """Input schema for estimating growth cost and period."""

    stat_summary: Dict[str, Any] = Field(default_factory=dict)
    equipment_summary: Dict[str, Any] = Field(default_factory=dict)
    daily_meso_budget: int = Field(150_000_000, ge=1)


class BottleneckScoreInput(BaseModel):
    """Input schema for scoring growth bottlenecks."""

    stat_summary: Dict[str, Any] = Field(default_factory=dict)
    equipment_summary: Dict[str, Any] = Field(default_factory=dict)
    growth_forecast: List[Dict[str, Any]] = Field(default_factory=list)


_POTENTIAL_GRADE_RANK = {
    "레어": 1,
    "에픽": 2,
    "유니크": 3,
    "레전드리": 4,
    "Rare": 1,
    "Epic": 2,
    "Unique": 3,
    "Legendary": 4,
}

_STAT_TARGETS = {
    # Derived from Neo4j StatRequirement distribution on 2026-05-10.
    # main_stat p90 ~= 102,000, boss_damage p90 = 350, ignore_def p90 ~= 95.6.
    "combat_power": 100_000_000,
    "main_stat": 102_000,
    "primary_attack": 7_000,
    "boss_damage": 350,
    "ignore_def": 95.6,
    "crit_rate": 100,
    "crit_damage": 90,
    "arcane_force": 1_320,
    "authentic_force": 230,
    "union_level": 8_000,
    "starforce": 22,
}

DEFAULT_BOSS_DEFENSE_RATE = 300.0
TARGET_BOSS_IED = 95.0
TARGET_CRIT_DAMAGE = 100.0
DAMAGE_SCORE_SCALE = 1_000_000

BOTTLENECK_LABELS = {
    "combat_power": "전투력",
    "main_stat": "주스탯",
    "primary_attack": "공격력/마력",
    "boss_damage": "보공+데미지 배율",
    "ignore_def": "방무 실효딜",
    "crit_expected": "크리 기대값",
    "arcane_force": "아케인포스",
    "authentic_force": "어센틱포스",
    "union_level": "유니온",
    "starforce": "스타포스",
}

_STARFORCE_TARGET_RULES = [
    # Mirrored from Neo4j EquipmentCatalog item_type=equipment_growth_rule.
    {"min_level": 200, "max_level": 219, "category": "all", "minimum": 10, "recommended": 12},
    {"min_level": 200, "max_level": 219, "category": "weapon_or_armor", "minimum": 12, "recommended": 15},
    {"min_level": 220, "max_level": 249, "category": "armor", "minimum": 15, "recommended": 17},
    {"min_level": 220, "max_level": 249, "category": "weapon_or_armor", "minimum": 15, "recommended": 17},
    {"min_level": 220, "max_level": 249, "category": "accessory", "minimum": 10, "recommended": 17},
    {"min_level": 250, "max_level": 269, "category": "weapon_or_armor", "minimum": 17, "recommended": 18},
    {"min_level": 270, "max_level": 300, "category": "weapon_or_armor", "minimum": 17, "recommended": 22},
    {"min_level": 270, "max_level": 300, "category": "armor", "minimum": 17, "recommended": 22},
    {"min_level": 270, "max_level": 300, "category": "accessory", "minimum": 17, "recommended": 22},
]

_WEAPON_PARTS = {"무기", "스태프", "완드", "샤이닝로드", "ESP 리미터", "체스피스", "매직 건틀렛"}
_ARMOR_PARTS = {"모자", "상의", "하의", "한벌옷", "신발", "장갑", "망토", "어깨장식"}
_ACCESSORY_PARTS = {"얼굴장식", "눈장식", "귀고리", "반지", "펜던트", "벨트", "기계 심장"}
_NO_STARFORCE_PARTS = {"엠블렘", "뱃지", "훈장", "포켓 아이템", "보조무기", "보석"}


def _plain(value: Any) -> Any:
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, dict):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_plain(item) for item in value]
    return value


def _value(source: Any, key: str, default: Any = None) -> Any:
    source = _plain(source)
    if source is None:
        return default
    if isinstance(source, dict):
        return source.get(key, default)
    return getattr(source, key, default)


def _parse_number(value: Any, default: float = 0.0) -> float:
    if value is None or value == "":
        return default
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).replace(",", "").replace("%", "").strip()
    match = re.search(r"[-+]?\d+(?:\.\d+)?", text)
    if not match:
        return default
    try:
        return float(match.group(0))
    except ValueError:
        return default


def _number(source: Any, key: str, default: float = 0.0) -> float:
    return _parse_number(_value(source, key, default), default=default)


def _first_number(sources: List[Any], keys: List[str], default: float = 0.0) -> float:
    for source in sources:
        for key in keys:
            value = _value(source, key, None)
            if value is not None and value != "":
                return _parse_number(value, default)
    return default


def _ratio(value: float, target: float) -> float:
    if target <= 0:
        return 1.0
    return max(0.0, min(value / target, 1.0))


def _percent_multiplier(value: float) -> float:
    return 1.0 + max(value, 0.0) / 100.0


def _critical_expected_multiplier(crit_rate: float, crit_damage: float) -> float:
    crit_chance = max(0.0, min(crit_rate, 100.0)) / 100.0
    # MapleStory critical damage has a built-in variable base range. Use 35% as the midpoint.
    crit_damage_multiplier = 0.35 + max(crit_damage, 0.0) / 100.0
    return 1.0 + crit_chance * crit_damage_multiplier


def _defense_damage_multiplier(ignore_def: float, boss_defense_rate: float = DEFAULT_BOSS_DEFENSE_RATE) -> float:
    ied = max(0.0, min(ignore_def, 100.0)) / 100.0
    defense = max(0.0, boss_defense_rate) / 100.0
    return max(0.05, 1.0 - defense * (1.0 - ied))


def _stat_attack_proxy(main_stat: int, primary_attack: int) -> float:
    if main_stat <= 0 or primary_attack <= 0:
        return 0.0
    # Real range uses weapon constants and secondary stat. The state only has consolidated main stat,
    # so this keeps the core 4*main_stat*attack structure and omits unavailable class constants.
    return (4.0 * main_stat * primary_attack) / 100.0


def _force_readiness(current: float, target: float) -> float:
    if target <= 0:
        return 1.0
    return max(0.0, min(current / target, 1.5))


def _safe_round(value: float, digits: int = 4) -> float:
    if value == float("inf") or value != value:
        return 0.0
    return round(value, digits)


def _sum_equipment_starforce(equipment_items: List[Any]) -> int:
    return sum(int(_number(item, "starforce", 0)) for item in equipment_items)


def _stat_package_score(stats: Any) -> float:
    return (
        _number(stats, "str_val")
        + _number(stats, "dex_val")
        + _number(stats, "int_val")
        + _number(stats, "luk_val")
        + _number(stats, "all_stat_percent") * 9
        + (_number(stats, "attack_power") + _number(stats, "magic_power")) * 4
        + _number(stats, "boss_damage_percent") * 6
        + _number(stats, "ignore_def_percent") * 5
        + _number(stats, "damage_percent") * 4
        + _number(stats, "crit_damage") * 8
    )


def _equipment_contribution_score(item: Any) -> float:
    return (
        _stat_package_score(_value(item, "total_stats", {}))
        + _stat_package_score(_value(item, "bonus_stats", {})) * 0.4
        + _stat_package_score(_value(item, "scroll_stats", {})) * 0.3
        + _number(item, "starforce") * 18
    )


def _potential_rank(grade: Any) -> int:
    if grade is None:
        return 0
    return _POTENTIAL_GRADE_RANK.get(str(grade).strip(), 0)


def _estimate_starforce_cost(current_starforce: int) -> int:
    if current_starforce < 10:
        return 80_000_000
    if current_starforce < 15:
        return 350_000_000
    if current_starforce < 17:
        return 900_000_000
    if current_starforce < 20:
        return 2_500_000_000
    return 6_000_000_000


def _equipment_category(part: Any) -> str:
    text = str(part or "")
    if text in _NO_STARFORCE_PARTS:
        return "no_starforce"
    if text in _WEAPON_PARTS or "무기" in text:
        return "weapon_or_armor"
    if text in _ARMOR_PARTS:
        return "armor"
    if text in _ACCESSORY_PARTS:
        return "accessory"
    return "all"


def _starforce_target_for_item(character_level: int, part: Any) -> Dict[str, Any]:
    category = _equipment_category(part)
    if category == "no_starforce":
        return {"minimum": 0, "recommended": 0, "category": category, "source": "non_starforce_slot"}

    matched = [
        rule
        for rule in _STARFORCE_TARGET_RULES
        if rule["min_level"] <= character_level <= rule["max_level"]
        and rule["category"] in {category, "all", "weapon_or_armor"}
        and not (rule["category"] == "weapon_or_armor" and category not in {"weapon_or_armor", "armor"})
    ]
    if not matched:
        matched = [rule for rule in _STARFORCE_TARGET_RULES if rule["category"] == "all"]
    if not matched:
        return {"minimum": 10, "recommended": 12, "category": category, "source": "fallback"}

    best = max(matched, key=lambda rule: (rule["recommended"], rule["minimum"]))
    return {
        "minimum": best["minimum"],
        "recommended": best["recommended"],
        "category": category,
        "source": "neo4j_equipment_growth_rule",
    }


def _potential_target_rank(character_level: int) -> int:
    if character_level >= 270:
        return _POTENTIAL_GRADE_RANK["레전드리"]
    if character_level >= 220:
        return _POTENTIAL_GRADE_RANK["유니크"]
    return _POTENTIAL_GRADE_RANK["에픽"]


def _additional_potential_target_rank(character_level: int) -> int:
    if character_level >= 270:
        return _POTENTIAL_GRADE_RANK["유니크"]
    return _POTENTIAL_GRADE_RANK["에픽"]


def _estimated_days(cost_meso: int, daily_meso_budget: int) -> int:
    return max(1, int((cost_meso + daily_meso_budget - 1) // daily_meso_budget))


def _state_stat_sources(state: AgentState) -> List[Any]:
    profile = _value(state, "character_profile", {})
    return [
        _value(state, "character_stats", {}),
        _value(profile, "final_stats", {}),
    ]


def _state_union_sources(state: AgentState) -> List[Any]:
    profile = _value(state, "character_profile", {})
    return [
        _value(state, "union_status", {}),
        _value(profile, "union_info", {}),
    ]


def _state_equipment_items(state: AgentState) -> List[Dict[str, Any]]:
    profile = _value(state, "character_profile", {})
    items = _value(state, "equipment_items", None)
    if items is None:
        items = _value(profile, "equipment_list", [])
    return [item for item in _plain(items or []) if isinstance(item, dict)]


def _state_character_level(state: AgentState) -> int:
    profile = _value(state, "character_profile", {})
    stat_sources = _state_stat_sources(state)
    return int(_first_number([profile, *stat_sources, state], ["level", "character_level"], 0))


def _main_stat_from_sources(sources: List[Any]) -> int:
    direct = _first_number(sources, ["main_stat", "primary_stat", "mainStat"], 0)
    if direct > 0:
        return int(direct)
    return int(
        max(
            _first_number(sources, ["str_val", "str", "STR"], 0),
            _first_number(sources, ["dex", "dex_val", "DEX"], 0),
            _first_number(sources, ["int_val", "int", "INT"], 0),
            _first_number(sources, ["luk", "luk_val", "LUK"], 0),
        )
    )


def _extract_character_input(state: AgentState) -> Dict[str, Any]:
    stat_sources = _state_stat_sources(state)
    union_sources = _state_union_sources(state)
    equipment_items = _state_equipment_items(state)
    return {
        "character_level": _state_character_level(state),
        "combat_power": int(_first_number(stat_sources, ["combat_power", "current_combat_power"], 0)),
        "main_stat": _main_stat_from_sources(stat_sources),
        "attack_power": int(_first_number(stat_sources, ["attack_power", "attack"], 0)),
        "magic_power": int(_first_number(stat_sources, ["magic_power"], 0)),
        "damage": _first_number(stat_sources, ["damage"], 0),
        "boss_damage": _first_number(stat_sources, ["boss_damage"], 0),
        "final_damage": _first_number(stat_sources, ["final_damage"], 0),
        "ignore_def": _first_number(stat_sources, ["ignore_def", "ignore_defense", "ied"], 0),
        "crit_rate": _first_number(stat_sources, ["crit_rate", "critical_rate"], 0),
        "crit_damage": _first_number(stat_sources, ["crit_damage", "critical_damage"], 0),
        "arcane_force": int(_first_number(stat_sources, ["arcane_force"], 0)),
        "authentic_force": int(_first_number(stat_sources, ["authentic_force", "sacred_force"], 0)),
        "starforce": int(_first_number(stat_sources, ["starforce", "total_starforce"], _sum_equipment_starforce(equipment_items))),
        "union_level": int(_first_number(union_sources, ["union_level"], 0)),
    }


def _validate_calculator_state_inputs(state: AgentState) -> None:
    missing = [
        key
        for key in ("character_stats", "equipment_items", "union_status")
        if key not in state or state[key] is None
    ]
    if missing:
        raise ValueError(f"calculator input state missing fields: {missing}")


def _append_state_error(state: AgentState, message: str) -> AgentState:
    new_state = dict(state)
    new_state["errors"] = [*new_state.get("errors", []), message]
    return new_state


def _empty_calculator_result(message: str) -> Dict[str, Any]:
    return {
        "stat_summary": {
            "damage_score": 0.0,
            "formula": "maplestory_boss_effective_damage_proxy",
            "data_reliability": "calculation_failed_or_missing_data",
            "error": message,
        },
        "equipment_summary": {
            "equipment_count": 0,
            "total_starforce": 0,
            "growth_forecast": [],
            "data_reliability": "calculation_failed_or_missing_data",
            "error": message,
        },
        "bottleneck_analysis": {},
    }


@tool(args_schema=DamageSimulationInput)
def simulate_damage_score(
    character_level: int = 0,
    combat_power: int = 0,
    main_stat: int = 0,
    attack_power: int = 0,
    magic_power: int = 0,
    damage: float = 0.0,
    boss_damage: float = 0.0,
    final_damage: float = 0.0,
    ignore_def: float = 0.0,
    crit_rate: float = 0.0,
    crit_damage: float = 0.0,
    arcane_force: int = 0,
    authentic_force: int = 0,
    starforce: int = 0,
    union_level: int = 0,
) -> Dict[str, Any]:
    """Calculate a deterministic boss-effective damage score for growth comparison."""

    primary_attack = max(attack_power, magic_power)
    stat_attack_proxy = _stat_attack_proxy(main_stat, primary_attack)
    normal_damage_multiplier = _percent_multiplier(damage)
    boss_damage_multiplier = 1.0 + (max(damage, 0.0) + max(boss_damage, 0.0)) / 100.0
    final_damage_multiplier = _percent_multiplier(final_damage)
    crit_multiplier = _critical_expected_multiplier(crit_rate, crit_damage)
    boss_defense_multiplier = _defense_damage_multiplier(ignore_def)

    normal_effective_damage = (
        stat_attack_proxy
        * normal_damage_multiplier
        * final_damage_multiplier
        * crit_multiplier
    )
    boss_effective_damage = (
        stat_attack_proxy
        * boss_damage_multiplier
        * final_damage_multiplier
        * crit_multiplier
        * boss_defense_multiplier
    )
    damage_score = boss_effective_damage / DAMAGE_SCORE_SCALE
    normal_damage_score = normal_effective_damage / DAMAGE_SCORE_SCALE
    arcane_force_readiness = _force_readiness(arcane_force, _STAT_TARGETS["arcane_force"])
    authentic_force_readiness = _force_readiness(authentic_force, _STAT_TARGETS["authentic_force"])
    union_readiness = _ratio(union_level, _STAT_TARGETS["union_level"])

    return {
        "character_level": character_level,
        "combat_power": combat_power,
        "main_stat": main_stat,
        "attack_power": attack_power,
        "magic_power": magic_power,
        "primary_attack": primary_attack,
        "damage": damage,
        "boss_damage": boss_damage,
        "final_damage": final_damage,
        "ignore_def": ignore_def,
        "crit_rate": crit_rate,
        "crit_damage": crit_damage,
        "arcane_force": arcane_force,
        "authentic_force": authentic_force,
        "starforce": starforce,
        "union_level": union_level,
        "stat_attack_proxy": _safe_round(stat_attack_proxy, 2),
        "normal_damage_score": _safe_round(normal_damage_score, 6),
        "boss_effective_damage_score": _safe_round(damage_score, 6),
        "damage_score": _safe_round(damage_score, 6),
        "formula": "maplestory_boss_effective_damage_proxy",
        "formula_components": {
            "stat_attack_proxy": _safe_round(stat_attack_proxy, 2),
            "normal_damage_multiplier": _safe_round(normal_damage_multiplier, 4),
            "boss_damage_multiplier": _safe_round(boss_damage_multiplier, 4),
            "final_damage_multiplier": _safe_round(final_damage_multiplier, 4),
            "critical_expected_multiplier": _safe_round(crit_multiplier, 4),
            "boss_defense_rate_assumption": DEFAULT_BOSS_DEFENSE_RATE,
            "boss_defense_damage_multiplier": _safe_round(boss_defense_multiplier, 4),
            "arcane_force_readiness": _safe_round(arcane_force_readiness, 4),
            "authentic_force_readiness": _safe_round(authentic_force_readiness, 4),
            "union_readiness": _safe_round(union_readiness, 4),
        },
        "assumption": (
            "실제 DPM이 아니라 보스전 성장 비교용 근사값입니다. "
            "스탯공격력은 4*주스탯*공마 구조를 쓰고, 직업별 무기상수/보조스탯/스킬 퍼뎀/공속/쿨타임은 state에 없어 제외합니다."
        ),
        "data_reliability": "state_input_relative_formula",
    }


@tool(args_schema=EquipmentSummaryInput)
def summarize_equipment_contribution(
    equipment_items: List[Dict[str, Any]],
    character_level: int = 0,
    main_stat: int = 0,
    attack_power: int = 0,
    magic_power: int = 0,
) -> Dict[str, Any]:
    """Summarize equipment contribution, starforce status, and weak upgrade slots."""

    by_slot: Dict[str, Any] = {}
    weak_slots: List[Dict[str, Any]] = []
    total_score = 0.0
    total_starforce = 0

    for item in equipment_items:
        slot = str(_value(item, "part", "") or "unknown")
        starforce = int(_number(item, "starforce"))
        starforce_target = _starforce_target_for_item(character_level, slot)
        score = _equipment_contribution_score(item)
        total_starforce += starforce
        total_score += score

        upgrade_flags: List[str] = []
        if starforce_target["recommended"] and starforce < starforce_target["recommended"]:
            upgrade_flags.append(f"starforce_under_{starforce_target['recommended']}")
        if _potential_rank(_value(item, "potential_grade")) < _potential_target_rank(character_level):
            upgrade_flags.append("potential_under_target")
        if _potential_rank(_value(item, "additional_potential_grade")) < _additional_potential_target_rank(character_level):
            upgrade_flags.append("additional_potential_under_target")

        slot_summary = {
            "item_name": _value(item, "item_name", ""),
            "part": slot,
            "starforce": starforce,
            "potential_grade": _value(item, "potential_grade"),
            "additional_potential_grade": _value(item, "additional_potential_grade"),
            "equipment_category": starforce_target["category"],
            "minimum_starforce": starforce_target["minimum"],
            "recommended_starforce": starforce_target["recommended"],
            "contribution_score": _safe_round(score, 2),
            "upgrade_flags": upgrade_flags,
        }
        by_slot[slot] = slot_summary
        if upgrade_flags:
            weak_slots.append(slot_summary)

    weak_slots.sort(key=lambda entry: (entry["starforce"], entry["contribution_score"]))
    return {
        "equipment_count": len(equipment_items),
        "total_starforce": total_starforce,
        "total_recommended_starforce": sum(
            int(_value(slot, "recommended_starforce", 0))
            for slot in by_slot.values()
            if int(_value(slot, "recommended_starforce", 0)) > 0
        ),
        "equipment_contribution_score": _safe_round(total_score, 2),
        "average_contribution_score": _safe_round(total_score / max(len(equipment_items), 1), 2),
        "main_stat_reference": main_stat,
        "attack_reference": max(attack_power, magic_power),
        "by_slot": by_slot,
        "weak_slots": weak_slots[:8],
        "data_reliability": "state_input_with_neo4j_equipment_growth_rules",
    }


@tool(args_schema=GrowthForecastInput)
def estimate_growth_cost_period(
    stat_summary: Dict[str, Any],
    equipment_summary: Dict[str, Any],
    daily_meso_budget: int = 150_000_000,
) -> List[Dict[str, Any]]:
    """Estimate growth action cost, period, expected CP gain, and relative damage gain."""

    forecast: List[Dict[str, Any]] = []
    base_score = max(_number(stat_summary, "damage_score"), 0.000001)
    combat_power = _number(stat_summary, "combat_power")

    for slot in (equipment_summary.get("weak_slots") or [])[:5]:
        current_starforce = int(_number(slot, "starforce"))
        recommended_starforce = int(_number(slot, "recommended_starforce"))
        target = slot.get("part") or slot.get("item_name") or "unknown"
        if recommended_starforce and current_starforce < recommended_starforce:
            cost = _estimate_starforce_cost(current_starforce)
            star_gap = recommended_starforce - current_starforce
            gain_percent = max(2.0, min(star_gap * 1.15, 14.0))
            forecast.append(
                {
                    "category": "장비 강화",
                    "target": target,
                    "action": f"스타포스 {recommended_starforce}성 권장선 달성",
                    "expected_damage_gain_percent": _safe_round(gain_percent, 2),
                    "expected_score_after": _safe_round(base_score * (1 + gain_percent / 100), 6),
                    "expected_cp_gain": int(combat_power * gain_percent / 100),
                    "estimated_cost_meso": cost,
                    "estimated_days": _estimated_days(cost, daily_meso_budget),
                    "efficiency_score": _safe_round(gain_percent / max(cost / 1_000_000_000, 0.1), 3),
                    "basis": "neo4j_equipment_growth_rule",
                }
            )

        if "potential_under_target" in (slot.get("upgrade_flags") or []):
            cost = 700_000_000
            gain_percent = 4.5 if _number(stat_summary, "character_level") >= 270 else 3.5
            forecast.append(
                {
                    "category": "잠재능력",
                    "target": target,
                    "action": "주요 장비 잠재 목표 등급 달성",
                    "expected_damage_gain_percent": gain_percent,
                    "expected_score_after": _safe_round(base_score * (1 + gain_percent / 100), 6),
                    "expected_cp_gain": int(combat_power * gain_percent / 100),
                    "estimated_cost_meso": cost,
                    "estimated_days": _estimated_days(cost, daily_meso_budget),
                    "efficiency_score": _safe_round(gain_percent / (cost / 1_000_000_000), 3),
                }
            )

    if _number(stat_summary, "arcane_force") < _STAT_TARGETS["arcane_force"]:
        cost = 250_000_000
        gain_percent = 2.5
        forecast.append(
            {
                "category": "심볼",
                "target": "아케인포스",
                "action": "아케인 심볼 레벨업",
                "expected_damage_gain_percent": gain_percent,
                "expected_score_after": _safe_round(base_score * 1.025, 6),
                "expected_cp_gain": int(combat_power * 0.025),
                "estimated_cost_meso": cost,
                "estimated_days": _estimated_days(cost, daily_meso_budget),
                "efficiency_score": _safe_round(gain_percent / (cost / 1_000_000_000), 3),
            }
        )

    if _number(stat_summary, "union_level") < _STAT_TARGETS["union_level"]:
        remaining = _STAT_TARGETS["union_level"] - _number(stat_summary, "union_level")
        forecast.append(
            {
                "category": "유니온",
                "target": "유니온 레벨",
                "action": "유니온 8000 구간까지 육성",
                "expected_damage_gain_percent": 1.8,
                "expected_score_after": _safe_round(base_score * 1.018, 6),
                "expected_cp_gain": int(combat_power * 0.018),
                "estimated_cost_meso": 0,
                "estimated_days": max(7, int(remaining / 120)),
                "efficiency_score": 1.8,
            }
        )

    forecast.sort(key=lambda item: (item["efficiency_score"], item["expected_damage_gain_percent"]), reverse=True)
    return forecast[:10]


@tool(args_schema=BottleneckScoreInput)
def calculate_bottleneck_scores(
    stat_summary: Dict[str, Any],
    equipment_summary: Dict[str, Any],
    growth_forecast: List[Dict[str, Any]],
) -> Dict[str, float]:
    """Calculate 0 to 1 growth bottleneck scores. Higher means more urgent."""

    components = _value(stat_summary, "formula_components", {}) or {}
    current_crit = _critical_expected_multiplier(
        _number(stat_summary, "crit_rate"),
        _number(stat_summary, "crit_damage"),
    )
    target_crit = _critical_expected_multiplier(100, TARGET_CRIT_DAMAGE)
    current_defense_factor = _number(
        components,
        "boss_defense_damage_multiplier",
        _defense_damage_multiplier(_number(stat_summary, "ignore_def")),
    )
    target_defense_factor = _defense_damage_multiplier(TARGET_BOSS_IED)
    current_boss_multiplier = 1.0 + (
        max(_number(stat_summary, "damage"), 0.0)
        + max(_number(stat_summary, "boss_damage"), 0.0)
    ) / 100.0
    target_boss_multiplier = 1.0 + (
        max(_number(stat_summary, "damage"), 0.0)
        + _STAT_TARGETS["boss_damage"]
    ) / 100.0

    scores = {
        "combat_power": 1 - _ratio(_number(stat_summary, "combat_power"), _STAT_TARGETS["combat_power"]),
        "main_stat": 1 - _ratio(_number(stat_summary, "main_stat"), _STAT_TARGETS["main_stat"]),
        "primary_attack": 1 - _ratio(_number(stat_summary, "primary_attack"), _STAT_TARGETS["primary_attack"]),
        "boss_damage": 1 - _ratio(current_boss_multiplier, target_boss_multiplier),
        "ignore_def": 1 - _ratio(current_defense_factor, target_defense_factor),
        "crit_expected": 1 - _ratio(current_crit, target_crit),
        "arcane_force": 1 - _ratio(_number(components, "arcane_force_readiness", 0), 1.0),
        "authentic_force": 1 - _ratio(_number(components, "authentic_force_readiness", 0), 1.0),
        "union_level": 1 - _ratio(_number(stat_summary, "union_level"), _STAT_TARGETS["union_level"]),
        "starforce": 1
        - _ratio(
            _number(equipment_summary, "total_starforce"),
            max(_number(equipment_summary, "total_recommended_starforce"), _STAT_TARGETS["starforce"]),
        ),
    }

    if growth_forecast:
        best = growth_forecast[0]
        category = str(best.get("category") or "growth_efficiency")
        scores[f"growth_option:{category}"] = min(float(best.get("efficiency_score", 0)) / 10, 1.0)

    return {key: _safe_round(value, 4) for key, value in scores.items() if value > 0.05}


def _calculator_has_usable_result(state: AgentState) -> bool:
    result = _value(_value(state, "tool_results", {}), "calculator", {}) or {}
    if _value(result, "error"):
        return False
    stat_summary = _value(state, "stat_summary", {}) or {}
    equipment_summary = _value(state, "equipment_summary", {}) or {}
    if _value(stat_summary, "data_reliability") == "calculation_failed_or_missing_data":
        return False
    return bool(_value(stat_summary, "damage_score") or _value(equipment_summary, "equipment_count"))


def _calculator_state_payload(state: AgentState) -> Dict[str, Any]:
    stat_summary = _value(state, "stat_summary", {}) or {}
    equipment_summary = _value(state, "equipment_summary", {}) or {}
    return {
        "user_query": _value(state, "contextualized_query", "") or _value(state, "user_query", ""),
        "character": {
            "character_name": _value(state, "character_name", ""),
            "world_name": _value(state, "world_name", ""),
            "level": _value(stat_summary, "character_level", 0),
            "combat_power": _value(stat_summary, "combat_power", 0),
            "main_stat": _value(stat_summary, "main_stat", 0),
            "primary_attack": _value(stat_summary, "primary_attack", 0),
            "boss_damage": _value(stat_summary, "boss_damage", 0),
            "ignore_def": _value(stat_summary, "ignore_def", 0),
            "crit_rate": _value(stat_summary, "crit_rate", 0),
            "crit_damage": _value(stat_summary, "crit_damage", 0),
            "damage_score": _value(stat_summary, "damage_score", 0),
        },
        "stat_summary": stat_summary,
        "equipment_summary": {
            "equipment_count": _value(equipment_summary, "equipment_count", 0),
            "total_starforce": _value(equipment_summary, "total_starforce", 0),
            "weak_slots": (_value(equipment_summary, "weak_slots", []) or [])[:8],
            "growth_forecast": (_value(equipment_summary, "growth_forecast", []) or [])[:10],
        },
        "bottleneck_analysis": _value(state, "bottleneck_analysis", {}),
    }


def run_calculator(
    state: AgentState,
    *,
    daily_meso_budget: int = 150_000_000,
) -> AgentState:
    """Run the common.state-compatible calculator step using only AgentState inputs."""

    try:
        _validate_calculator_state_inputs(state)
        validate_agent_inputs("calculator", state)

        character_input = _extract_character_input(state)
        damage_summary = simulate_damage_score.invoke(character_input)
        equipment_summary = summarize_equipment_contribution.invoke(
            {
                "equipment_items": _state_equipment_items(state),
                "character_level": damage_summary["character_level"],
                "main_stat": damage_summary["main_stat"],
                "attack_power": damage_summary["attack_power"],
                "magic_power": damage_summary["magic_power"],
            }
        )
        growth_forecast = estimate_growth_cost_period.invoke(
            {
                "stat_summary": damage_summary,
                "equipment_summary": equipment_summary,
                "daily_meso_budget": daily_meso_budget,
            }
        )
        bottleneck_analysis = calculate_bottleneck_scores.invoke(
            {
                "stat_summary": damage_summary,
                "equipment_summary": equipment_summary,
                "growth_forecast": growth_forecast,
            }
        )
    except Exception as exc:
        message = f"calculator failed: {exc}"
        new_state = _append_state_error(state, message)
        empty_result = _empty_calculator_result(message)
        new_state.update(empty_result)
        new_state["tool_results"] = {
            **new_state.get("tool_results", {}),
            "calculator": empty_result,
        }
        return new_state

    new_state = dict(state)
    new_state["stat_summary"] = damage_summary
    new_state["equipment_summary"] = {
        **equipment_summary,
        "growth_forecast": growth_forecast,
        "daily_meso_budget": daily_meso_budget,
    }
    new_state["bottleneck_analysis"] = bottleneck_analysis
    new_state["tool_results"] = {
        **new_state.get("tool_results", {}),
        "calculator": {
            "stat_summary": new_state["stat_summary"],
            "equipment_summary": new_state["equipment_summary"],
            "bottleneck_analysis": new_state["bottleneck_analysis"],
        },
    }

    validate_agent_outputs("calculator", new_state)
    return new_state


def _format_meso(value: Any) -> str:
    amount = int(_parse_number(value, 0))
    if amount >= 100_000_000:
        return f"{amount / 100_000_000:g}억 메소"
    if amount >= 10_000:
        return f"{amount / 10_000:g}만 메소"
    return f"{amount:,} 메소"


def _format_percent(value: Any) -> str:
    number = _parse_number(value, 0)
    if number == int(number):
        return f"{int(number)}%"
    return f"{number:.2f}".rstrip("0").rstrip(".") + "%"


def _format_score(value: Any, digits: int = 4) -> str:
    number = _parse_number(value, 0)
    if digits <= 0:
        return f"{int(round(number)):,}"
    return f"{number:.{digits}f}".rstrip("0").rstrip(".")


def _growth_action_detail(item: Dict[str, Any]) -> Dict[str, Any]:
    cp_gain = int(_parse_number(item.get("expected_cp_gain"), 0))
    damage_gain = _parse_number(item.get("expected_damage_gain_percent"), 0)
    cost = int(_parse_number(item.get("estimated_cost_meso"), 0))
    days = int(_parse_number(item.get("estimated_days"), 0))
    efficiency = _parse_number(item.get("efficiency_score"), 0)
    details = []
    if cp_gain:
        details.append(f"예상 전투력 +{cp_gain:,}")
    if damage_gain:
        details.append(f"예상 데미지 +{_format_percent(damage_gain)}")
    if cost:
        details.append(f"예상 비용 {_format_meso(cost)}")
    if days:
        details.append(f"예상 기간 {days}일")
    if efficiency:
        details.append(f"효율 점수 {_format_score(efficiency)}")

    return {
        "target": item.get("target") or "성장 항목",
        "action": item.get("action") or "성장 진행",
        "reason": ", ".join(details) if details else "계산된 성장 후보입니다.",
        "expected_cp_gain": cp_gain,
        "expected_damage_gain_percent": _safe_round(damage_gain, 2),
        "estimated_cost_meso": cost,
        "estimated_cost_text": _format_meso(cost) if cost else "",
        "estimated_days": days,
        "efficiency_score": _safe_round(efficiency, 3),
        "expected_score_after": item.get("expected_score_after"),
        "basis": item.get("basis"),
    }


def _ranked_bottleneck_details(state: AgentState, limit: int = 5) -> List[Dict[str, Any]]:
    bottlenecks = _value(state, "bottleneck_analysis", {}) or {}
    if not isinstance(bottlenecks, dict):
        return []
    ranked = sorted(
        (
            (str(key), _parse_number(value, 0))
            for key, value in bottlenecks.items()
            if isinstance(value, (int, float))
            and not str(key).startswith("growth_option:")
            and _parse_number(value, 0) > 0.05
        ),
        key=lambda item: item[1],
        reverse=True,
    )
    details = []
    for key, score in ranked[:limit]:
        label = BOTTLENECK_LABELS.get(key, key)
        details.append(
            {
                "key": key,
                "label": label,
                "urgency_score": _safe_round(score, 4),
                "reason": f"{label} 병목 점수 {_format_score(score)}. 1에 가까울수록 현재 목표 대비 보완 우선도가 높습니다.",
            }
        )
    return details


def _damage_formula_details(stat_summary: Dict[str, Any]) -> List[str]:
    components = _value(stat_summary, "formula_components", {}) or {}
    if not isinstance(components, dict) or not components:
        return []

    return [
        (
            "보스 유효딜 점수 = "
            "스탯공격력 프록시 * 보스 공격 배율 * 최종 데미지 배율 * "
            "크리 기대 배율 * 방무 실효딜 계수 / 1,000,000 구조로 계산했습니다."
        ),
        (
            "스탯공격력 프록시 "
            f"{_format_score(_value(components, 'stat_attack_proxy'), 2)} "
            "= 4 * 주스탯 * 주공격력 / 100 구조로 계산했습니다."
        ),
        (
            "보스 공격 배율 "
            f"{_format_score(_value(components, 'boss_damage_multiplier'))} "
            "= 1 + (데미지 + 보스 데미지) / 100 입니다."
        ),
        f"최종 데미지 배율은 {_format_score(_value(components, 'final_damage_multiplier'))} 입니다.",
        f"크리 기대 배율은 {_format_score(_value(components, 'critical_expected_multiplier'))} 입니다.",
        (
            "방무 실효딜 계수는 "
            f"{_format_score(_value(components, 'boss_defense_damage_multiplier'))} "
            f"(보스 방어율 {_format_score(_value(components, 'boss_defense_rate_assumption'), 0)}% 가정)입니다."
        ),
    ]


def _calculator_handoff_context(
    payload: Dict[str, Any],
    top_items: List[Dict[str, Any]],
    bottlenecks: List[Dict[str, Any]],
    formula_lines: List[str],
) -> str:
    stat_summary = payload.get("stat_summary") or {}
    character = payload.get("character") or {}
    lines = [
        "Calculator detailed handoff:",
        (
            f"캐릭터 계산 스냅샷: {character.get('character_name') or 'unknown'}, "
            f"전투력 {_format_score(_value(stat_summary, 'combat_power'), 0)}, "
            f"주스탯 {_format_score(_value(stat_summary, 'main_stat'), 0)}, "
            f"보스 데미지 {_format_percent(_value(stat_summary, 'boss_damage'))}, "
            f"방무 {_format_percent(_value(stat_summary, 'ignore_def'))}, "
            f"보스 유효딜 점수 {_format_score(_value(stat_summary, 'damage_score'), 6)}."
        ),
    ]
    if formula_lines:
        lines.append("계산 구성: " + " / ".join(formula_lines[:6]))
    if bottlenecks:
        lines.append(
            "성장 병목 우선순위: "
            + ", ".join(
                f"{item['label']}({item['urgency_score']})"
                for item in bottlenecks[:4]
            )
            + "."
        )
    if top_items:
        lines.append(
            "계산된 성장 후보: "
            + "; ".join(
                f"{item['target']} - {item['action']} ({item['reason']})"
                for item in top_items[:3]
            )
            + "."
        )
    lines.append(
        "계산 한계: 실제 DPM이 아니라 state에 있는 스탯/장비/성장 후보 기반의 보스전 상대 지표이며, 직업별 무기상수와 스킬 운용은 제외했습니다."
    )
    return "\n".join(lines)


def _calculator_final_answer_context(interpretation: Dict[str, Any]) -> str:
    character = interpretation.get("character_snapshot") or {}
    top_actions = interpretation.get("top_growth_actions") or []
    bottlenecks = interpretation.get("top_bottlenecks") or []
    formula_lines = interpretation.get("damage_formula_summary") or []
    caveats = interpretation.get("caveats") or []

    lines = [
        "Calculator final answer guide:",
        "아래 값은 calculator가 AgentState의 캐릭터 스탯/장비/유니온 입력만 사용해 만든 계산 결과입니다. calculator-only 질문에서는 이 값을 우선 근거로 답변하세요.",
        "성장 후보가 존재하면 장비 계산이 수행된 상태이므로, 장비 정보가 없다고 단정하지 말고 아래 후보를 기준으로 추천하세요.",
        "## 계산 스냅샷",
        (
            f"- 캐릭터: {character.get('character_name') or 'unknown'}"
            f" / 레벨 {_format_score(character.get('level'), 0)}"
            f" / 전투력 {_format_score(character.get('combat_power'), 0)}"
            f" / 주스탯 {_format_score(character.get('main_stat'), 0)}"
            f" / 보스 데미지 {_format_percent(character.get('boss_damage'))}"
            f" / 방무 {_format_percent(character.get('ignore_def'))}"
            f" / 보스 유효딜 점수 {_format_score(character.get('damage_score'), 6)}"
        ),
    ]

    if top_actions:
        lines.extend(
            [
                "## calculator 추천 성장 후보",
                "| 우선 | 대상 | 액션 | 예상 전투력 | 예상 데미지 | 비용 | 기간 | 효율 |",
                "| ---: | --- | --- | ---: | ---: | ---: | ---: | ---: |",
            ]
        )
        for index, action in enumerate(top_actions[:5], start=1):
            cp_gain = int(_parse_number(action.get("expected_cp_gain"), 0))
            damage_gain = _parse_number(action.get("expected_damage_gain_percent"), 0)
            cost = int(_parse_number(action.get("estimated_cost_meso"), 0))
            days = int(_parse_number(action.get("estimated_days"), 0))
            efficiency = _parse_number(action.get("efficiency_score"), 0)
            lines.append(
                "| "
                f"{index} | {action.get('target') or ''} | {action.get('action') or ''} | "
                f"+{cp_gain:,} | {_format_percent(damage_gain)} | {_format_meso(cost)} | "
                f"{days}일 | {_format_score(efficiency)} |"
            )

    if bottlenecks:
        lines.extend(
            [
                "## 계산상 병목 우선순위",
                "| 우선 | 항목 | 병목 점수 | 의미 |",
                "| ---: | --- | ---: | --- |",
            ]
        )
        for index, item in enumerate(bottlenecks[:5], start=1):
            lines.append(
                "| "
                f"{index} | {item.get('label') or item.get('key') or ''} | "
                f"{_format_score(item.get('urgency_score'))} | "
                "1에 가까울수록 목표 대비 보완 우선도가 높음 |"
            )

    if formula_lines:
        lines.append("## 계산식 근거")
        for line in formula_lines[:6]:
            lines.append(f"- {line}")

    if caveats:
        lines.append("## 계산 한계")
        for caveat in caveats[:2]:
            lines.append(f"- {caveat}")

    return "\n".join(lines)


def _calculator_recommended_actions(interpretation: Dict[str, Any]) -> List[Dict[str, Any]]:
    actions = []
    for index, item in enumerate(interpretation.get("top_growth_actions") or [], start=1):
        if not isinstance(item, dict):
            continue
        reason = str(item.get("reason") or "").strip()
        action = str(item.get("action") or "성장 진행").strip()
        description = f"{action}. {reason}" if reason else action
        actions.append(
            {
                "category": "CALCULATOR_GROWTH",
                "target": str(item.get("target") or "성장 항목"),
                "priority": index,
                "expected_cp_gain": int(_parse_number(item.get("expected_cp_gain"), 0)),
                "description": description,
            }
        )
    return actions[:5]


def _should_expose_calculator_context(state: AgentState) -> bool:
    plan = _value(state, "plan", []) or []
    if isinstance(plan, list) and "analystic" in plan:
        return False
    return True


def _append_calculator_answer_context(state: AgentState, interpretation: Dict[str, Any]) -> AgentState:
    if not _should_expose_calculator_context(state):
        return state

    context_block = _calculator_final_answer_context(interpretation)
    marker = "Calculator final answer guide:"
    new_state = dict(state)
    existing_context = str(_value(new_state, "context", "") or "").strip()
    if marker not in existing_context:
        new_state["context"] = (
            f"{existing_context}\n\n{context_block}"
            if existing_context
            else context_block
        )

    existing_actions = [
        action
        for action in list(_value(new_state, "recommended_actions", []) or [])
        if isinstance(action, dict)
    ]
    seen = {
        (str(action.get("category") or ""), str(action.get("target") or ""))
        for action in existing_actions
    }
    for action in _calculator_recommended_actions(interpretation):
        identity = (str(action.get("category") or ""), str(action.get("target") or ""))
        if identity in seen:
            continue
        seen.add(identity)
        existing_actions.append(action)
    if existing_actions:
        new_state["recommended_actions"] = sorted(
            existing_actions,
            key=lambda action: int(_parse_number(action.get("priority"), 999)),
        )
    return new_state


def _fallback_calculator_interpretation(state: AgentState) -> Dict[str, Any]:
    payload = _calculator_state_payload(state)
    forecast = payload["equipment_summary"].get("growth_forecast", []) or []
    top_items = [_growth_action_detail(item) for item in forecast[:3] if isinstance(item, dict)]
    top_bottlenecks = _ranked_bottleneck_details(state)
    formula_lines = _damage_formula_details(payload.get("stat_summary") or {})

    if top_items:
        summary = "전투력 상승 효율은 " + ", ".join(str(item["target"]) for item in top_items) + " 순서가 높습니다."
    else:
        summary = "계산 가능한 성장 후보가 충분하지 않습니다."
    if top_bottlenecks:
        summary += " 현재 계산상 가장 큰 병목은 " + ", ".join(item["label"] for item in top_bottlenecks[:3]) + "입니다."

    return {
        "query_intent": "장비/성장 후보별 전투력 상승량 비교",
        "calculation_scope": "현재 캐릭터 스탯, 장비 약점, 성장 예측값 요약",
        "priority_summary": summary,
        "character_snapshot": payload.get("character") or {},
        "damage_formula_summary": formula_lines,
        "top_bottlenecks": top_bottlenecks,
        "top_growth_actions": top_items,
        "caveats": [
            "전투력 상승량은 프로젝트의 상대 성장 공식 기반 추정입니다.",
            "실제 상승량은 잠재 옵션, 세트 효과, 버프, 이벤트, 강화 운에 따라 달라질 수 있습니다.",
        ],
        "analytics_handoff_context": _calculator_handoff_context(payload, top_items, top_bottlenecks, formula_lines),
        "source": "deterministic_fallback",
    }


def _attach_calculator_interpretation(state: AgentState, interpretation: Dict[str, Any]) -> AgentState:
    if not interpretation:
        return state

    new_state = dict(state)
    tool_results = dict(_value(new_state, "tool_results", {}) or {})
    calculator_result = dict(_value(tool_results, "calculator", {}) or {})
    calculator_result["llm_interpretation"] = interpretation
    tool_results["calculator"] = calculator_result
    new_state["tool_results"] = tool_results
    return _append_calculator_answer_context(new_state, interpretation)


def calculator_agent(
    model: Any | None = None,
    *,
    state: AgentState,
    daily_meso_budget: int = 150_000_000,
) -> AgentState:
    """Run calculator node and attach a deterministic analytics handoff."""

    _ = model  # Kept for call compatibility; calculator output is deterministic.
    user_query = state["user_query"]

    state = run_calculator(state, daily_meso_budget=daily_meso_budget)
    if _calculator_has_usable_result(state):
        state = _attach_calculator_interpretation(
            state,
            _fallback_calculator_interpretation(state),
        )

    validate_agent_outputs("calculator", state)
    return {
        **state,
        "user_query": user_query,
    }


# if __name__ == "__main__":
#     input_state = {
#     "user_query": "음표 캐릭터 딜 시뮬레이션과 성장 비용/기간 계산해줘",
#     "character_name": "음표",
#     "world_name": "스카니아",
#     "ocid": "816a7a2b984c1a3031fbc144d913a189",
#     "character_profile": {
#         "character_name": "음표",
#         "job_name": "플레임위자드",
#         "world_name": "스카니아",
#         "level": 294,
#         "gender": "여",
#     },
#     "character_stats": {
#         "min_stat_damage": 78086560,
#         "max_stat_damage": 82196377,
#         "damage": 73.0,
#         "boss_damage": 320.0,
#         "final_damage": 122.75,
#         "ignore_def": 89.89,
#         "crit_rate": 90.0,
#         "crit_damage": 91.55,
#         "starforce": 279,
#         "arcane_force": 1375,
#         "authentic_force": 800,
#         "str_val": 3870,
#         "dex": 3494,
#         "int_val": 60976,
#         "luk": 6306,
#         "hp": 46901,
#         "mp": 80133,
#         "buff_duration": 50,
#         "attack_speed": 8,
#         "attack_power": 2268,
#         "magic_power": 7104,
#         "combat_power": 144744108,
#         "main_stat": 60976,
#     },
#     "equipment_items": [
#         {"item_name": "하이네스 던위치햇", "part": "모자", "starforce": 22, "potential_grade": "레전드리", "additional_potential_grade": "에픽", "total_stats": {"str_val": 20, "int_val": 301, "luk_val": 157, "attack_power": 85, "magic_power": 88, "hp": 2055, "ignore_def_percent": 10, "all_stat_percent": 5}, "bonus_stats": {"str_val": 20, "int_val": 60, "all_stat_percent": 5}, "scroll_stats": {"int_val": 84, "magic_power": 1, "hp": 1440}},
#         {"item_name": "레드 매지션 마이스터 심볼", "part": "얼굴장식", "starforce": 8, "potential_grade": "레전드리", "additional_potential_grade": "레어", "total_stats": {"int_val": 21, "luk_val": 20, "magic_power": 8, "hp": 1200}, "bonus_stats": {"hp": 1200}, "scroll_stats": {"magic_power": 8}},
#         {"item_name": "미카엘라의 새 안경", "part": "눈장식", "starforce": 5, "potential_grade": "레전드리", "additional_potential_grade": "레어", "total_stats": {"str_val": 12, "dex_val": 12, "int_val": 12, "luk_val": 12, "attack_power": 2, "magic_power": 27, "all_stat_percent": 3}, "bonus_stats": {"all_stat_percent": 3}, "scroll_stats": {"magic_power": 25}},
#         {"item_name": "하프 이어링", "part": "귀고리", "starforce": 5, "potential_grade": "레전드리", "additional_potential_grade": "레어", "total_stats": {"str_val": 10, "dex_val": 18, "int_val": 36, "luk_val": 24, "hp": 420}, "bonus_stats": {"dex_val": 8, "int_val": 6, "luk_val": 14, "hp": 420}, "scroll_stats": {"int_val": 20}},
#         {"item_name": "이글아이 던위치로브", "part": "상의", "starforce": 22, "potential_grade": "레전드리", "additional_potential_grade": "유니크", "total_stats": {"str_val": 20, "int_val": 263, "luk_val": 147, "attack_power": 85, "magic_power": 88, "hp": 1215, "ignore_def_percent": 5, "all_stat_percent": 6}, "bonus_stats": {"str_val": 20, "int_val": 60, "all_stat_percent": 6}, "scroll_stats": {"int_val": 56, "magic_power": 1, "hp": 960}},
#         {"item_name": "트릭스터 던위치팬츠", "part": "하의", "starforce": 22, "potential_grade": "레전드리", "additional_potential_grade": "유니크", "total_stats": {"str_val": 106, "int_val": 268, "luk_val": 149, "attack_power": 85, "magic_power": 95, "hp": 975, "ignore_def_percent": 5, "all_stat_percent": 6}, "bonus_stats": {"str_val": 28, "int_val": 76, "all_stat_percent": 6}, "scroll_stats": {"str_val": 1, "int_val": 45, "luk_val": 2, "magic_power": 8, "hp": 720}},
#         {"item_name": "아케인셰이드 메이지슈즈", "part": "신발", "starforce": 22, "potential_grade": "레전드리", "additional_potential_grade": "유니크", "total_stats": {"str_val": 142, "int_val": 358, "luk_val": 185, "attack_power": 106, "magic_power": 122, "hp": 1190, "all_stat_percent": 5}, "bonus_stats": {"str_val": 36, "int_val": 102, "all_stat_percent": 5}, "scroll_stats": {"str_val": 1, "int_val": 71, "magic_power": 7, "hp": 1190}},
#         {"item_name": "아케인셰이드 메이지글러브", "part": "장갑", "starforce": 22, "potential_grade": "레전드리", "additional_potential_grade": "레전드리", "total_stats": {"dex_val": 30, "int_val": 283, "luk_val": 186, "attack_power": 106, "magic_power": 160, "all_stat_percent": 5}, "bonus_stats": {"dex_val": 30, "int_val": 96, "magic_power": 4, "all_stat_percent": 5}, "scroll_stats": {"int_val": 2, "luk_val": 1, "magic_power": 34}},
#         {"item_name": "아케인셰이드 메이지케이프", "part": "망토", "starforce": 22, "potential_grade": "레전드리", "additional_potential_grade": "레전드리", "total_stats": {"str_val": 178, "dex_val": 179, "int_val": 378, "luk_val": 181, "attack_power": 113, "magic_power": 119, "hp": 1445, "all_stat_percent": 4}, "bonus_stats": {"str_val": 36, "dex_val": 36, "int_val": 127, "all_stat_percent": 4}, "scroll_stats": {"str_val": 2, "dex_val": 3, "int_val": 71, "luk_val": 1, "attack_power": 1, "magic_power": 7, "hp": 1190}},
#         {"item_name": "제네시스 스태프", "part": "스태프", "starforce": 22, "potential_grade": "레전드리", "additional_potential_grade": "레전드리", "total_stats": {"int_val": 351, "luk_val": 319, "attack_power": 541, "magic_power": 1004, "hp": 255, "boss_damage_percent": 30, "ignore_def_percent": 20, "damage_percent": 4}, "bonus_stats": {"int_val": 24, "luk_val": 24, "attack_power": 92, "magic_power": 250, "damage_percent": 4}, "scroll_stats": {"int_val": 32, "magic_power": 72}},
#     ],
#     "union_status": {
#         "union_level": 8935,
#         "union_grade": "그랜드 마스터 유니온 2",
#         "artifact_level": None,
#         "artifact_exp": 0,
#     },
#     "raw_api_results": {
#         "nexon": {
#             "date": "2026-05-09"
#         }
#     },
# }

#     result_state = calculator_agent(state=input_state)
#     print(result_state["equipment_summary"])
