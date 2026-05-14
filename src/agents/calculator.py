from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import asdict, is_dataclass
from typing import Any, Dict, List
from dotenv import load_dotenv

current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(current_dir, "../../"))
sys.path.append(project_root)



from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.tools import tool
from pydantic import BaseModel, Field

from common.get_model import get_llm
from common.prompt import master_prompt
from common.state import AgentState
from common.validator import validate_agent_inputs, validate_agent_outputs

load_dotenv()
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
            "formula": "relative_growth_comparison_score",
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


def _parse_json_object(content: str) -> Dict[str, Any]:
    text = content.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{[\s\S]*\}", text)
        if not match:
            return {}
        try:
            parsed = json.loads(match.group(0))
        except json.JSONDecodeError:
            return {}
    return parsed if isinstance(parsed, dict) else {}


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
    """Calculate a deterministic relative damage score for growth comparison."""

    primary_attack = max(attack_power, magic_power)
    stat_factor = max(main_stat, 1) / 10_000
    attack_factor = max(primary_attack, 1) / 1_000
    damage_factor = 1 + max(damage, 0) / 100
    boss_factor = 1 + max(boss_damage, 0) / 100
    final_damage_factor = 1 + max(final_damage, 0) / 100
    crit_factor = 1 + min(max(crit_rate, 0), 100) / 100 * max(crit_damage, 0) / 100
    ignore_def_factor = 1 / max(0.3, 1 - min(max(ignore_def, 0), 100) / 100 * 0.3)
    force_factor = 1 + min(arcane_force / 1_320, 1) * 0.05 + min(authentic_force / 730, 1) * 0.05
    union_factor = 1 + min(union_level / 8_500, 1) * 0.04
    damage_score = (
        stat_factor
        * attack_factor
        * damage_factor
        * boss_factor
        * final_damage_factor
        * crit_factor
        * ignore_def_factor
        * force_factor
        * union_factor
    )

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
        "damage_score": _safe_round(damage_score, 6),
        "formula": "relative_growth_comparison_score",
        "assumption": "실제 DPM이 아니라 성장 전후 비교를 위한 상대 딜 점수입니다.",
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
                    "expected_score_after": _safe_round(base_score * 1.035, 6),
                    "expected_cp_gain": int(combat_power * 0.035),
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

    scores = {
        "combat_power": 1 - _ratio(_number(stat_summary, "combat_power"), _STAT_TARGETS["combat_power"]),
        "main_stat": 1 - _ratio(_number(stat_summary, "main_stat"), _STAT_TARGETS["main_stat"]),
        "primary_attack": 1 - _ratio(_number(stat_summary, "primary_attack"), _STAT_TARGETS["primary_attack"]),
        "boss_damage": 1 - _ratio(_number(stat_summary, "boss_damage"), _STAT_TARGETS["boss_damage"]),
        "ignore_def": 1 - _ratio(_number(stat_summary, "ignore_def"), _STAT_TARGETS["ignore_def"]),
        "crit_rate": 1 - _ratio(_number(stat_summary, "crit_rate"), _STAT_TARGETS["crit_rate"]),
        "crit_damage": 1 - _ratio(_number(stat_summary, "crit_damage"), _STAT_TARGETS["crit_damage"]),
        "arcane_force": 1 - _ratio(_number(stat_summary, "arcane_force"), _STAT_TARGETS["arcane_force"]),
        "authentic_force": 1 - _ratio(_number(stat_summary, "authentic_force"), _STAT_TARGETS["authentic_force"]),
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
            "combat_power": _value(stat_summary, "combat_power", 0),
            "main_stat": _value(stat_summary, "main_stat", 0),
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


CALCULATOR_TOOLS = [
    simulate_damage_score,
    summarize_equipment_contribution,
    estimate_growth_cost_period,
    calculate_bottleneck_scores,
]

CALCULATOR_STATE_SYSTEM_PROMPT = f"""
{master_prompt}

너는 메이플스토리 계산 에이전트이다.
다음의 룰은 꼭 지켜야 한다.
- 툴과 AgentState에 이미 기록된 계산 결과만 사용한다.
- 절대로 사용자에게 보여줄 최종 답변 문장을 만들지 않는다.
- 절대로 캐릭터 스탯, 장비 수치, 비용, 기간을 임의로 새로 만들지 않는다.
- 너는 딜 시뮬레이션 및 성장 비용/기간 예측 수치 계산 결과를 정해진 state에 넣는 절차의 일부이다.
- Return only a JSON object for AgentState update.
- Allowed top-level keys: stat_summary, equipment_summary, bottleneck_analysis, llm_interpretation.
- stat_summary/equipment_summary/bottleneck_analysis는 기존 계산 결과를 보존하고, 필요한 설명용 메타데이터만 보강한다.
""".strip()


def _format_meso(value: Any) -> str:
    amount = int(_parse_number(value, 0))
    if amount >= 100_000_000:
        return f"{amount / 100_000_000:g}억 메소"
    if amount >= 10_000:
        return f"{amount / 10_000:g}만 메소"
    return f"{amount:,} 메소"


def _fallback_calculator_interpretation(state: AgentState) -> Dict[str, Any]:
    payload = _calculator_state_payload(state)
    forecast = payload["equipment_summary"].get("growth_forecast", []) or []
    top_items = []
    for item in forecast[:3]:
        target = item.get("target") or "성장 항목"
        action = item.get("action") or "성장 진행"
        cp_gain = int(_parse_number(item.get("expected_cp_gain"), 0))
        cost = _format_meso(item.get("estimated_cost_meso"))
        days = int(_parse_number(item.get("estimated_days"), 0))
        top_items.append(
            {
                "target": target,
                "action": action,
                "reason": f"예상 전투력 +{cp_gain:,}, 예상 비용 {cost}, 예상 기간 {days}일",
                "expected_cp_gain": cp_gain,
            }
        )

    if top_items:
        summary = "전투력 상승 효율은 " + ", ".join(str(item["target"]) for item in top_items) + " 순서가 높습니다."
    else:
        summary = "계산 가능한 성장 후보가 충분하지 않습니다."

    return {
        "query_intent": "장비/성장 후보별 전투력 상승량 비교",
        "calculation_scope": "현재 캐릭터 스탯, 장비 약점, 성장 예측값 요약",
        "priority_summary": summary,
        "top_growth_actions": top_items,
        "caveats": [
            "전투력 상승량은 프로젝트의 상대 성장 공식 기반 추정입니다.",
            "실제 상승량은 잠재 옵션, 세트 효과, 버프, 이벤트, 강화 운에 따라 달라질 수 있습니다.",
        ],
        "analytics_handoff_context": summary,
        "source": "deterministic_fallback",
    }


def _calculator_interpretation_prompt(state: AgentState) -> str:
    payload = _calculator_state_payload(state)
    return "\n".join(
        [
            master_prompt.strip(),
            "",
            "You are the calculator interpretation layer.",
            "The numeric calculation is already finished by deterministic code.",
            "Do not call tools. Do not invent new stats, costs, combat power gains, boss requirements, or item names.",
            "Your job is only to classify the calculation request and write a short handoff summary for analytics.",
            "Return only a JSON object with these keys:",
            "- query_intent: short Korean phrase",
            "- calculation_scope: short Korean phrase",
            "- priority_summary: one Korean sentence",
            "- top_growth_actions: array of at most 3 objects from the provided growth_forecast, each with target, action, reason, expected_cp_gain",
            "- caveats: array of 1-2 short Korean caveats",
            "- analytics_handoff_context: 2-4 Korean sentences analytics can reuse",
            "",
            f"Input JSON: {json.dumps(payload, ensure_ascii=False, default=str)}",
        ]
    )


def _normalize_llm_interpretation(parsed: Dict[str, Any], state: AgentState) -> Dict[str, Any]:
    fallback = _fallback_calculator_interpretation(state)
    if not parsed:
        return fallback

    result = {
        "query_intent": str(parsed.get("query_intent") or fallback["query_intent"]),
        "calculation_scope": str(parsed.get("calculation_scope") or fallback["calculation_scope"]),
        "priority_summary": str(parsed.get("priority_summary") or fallback["priority_summary"]),
        "analytics_handoff_context": str(
            parsed.get("analytics_handoff_context") or fallback["analytics_handoff_context"]
        ),
        "source": "llm_summary",
    }

    caveats = parsed.get("caveats")
    result["caveats"] = [str(item) for item in caveats[:2]] if isinstance(caveats, list) else fallback["caveats"]

    allowed_forecasts = {}
    for item in ((_value(state.get("equipment_summary") or {}, "growth_forecast", []) or [])[:10]):
        if not isinstance(item, dict):
            continue
        target = str(item.get("target") or "")
        if target and target not in allowed_forecasts:
            allowed_forecasts[target] = item
    top_actions = []
    for item in parsed.get("top_growth_actions", []) if isinstance(parsed.get("top_growth_actions"), list) else []:
        if not isinstance(item, dict):
            continue
        target = str(item.get("target") or "")
        source = allowed_forecasts.get(target)
        if not source:
            continue
        cp_gain = int(_parse_number(source.get("expected_cp_gain"), 0))
        top_actions.append(
            {
                "target": target,
                "action": str(item.get("action") or source.get("action") or ""),
                "reason": str(item.get("reason") or f"예상 전투력 +{cp_gain:,}"),
                "expected_cp_gain": cp_gain,
            }
        )
    result["top_growth_actions"] = top_actions[:3] or fallback["top_growth_actions"]
    return result


def _generate_agent_state_update(
    state: AgentState,
    model: str | BaseChatModel | None,
) -> Dict[str, Any]:
    if model is None or isinstance(model, str) or not hasattr(model, "invoke"):
        model = get_llm()

    response = model.invoke(_calculator_interpretation_prompt(state))
    content = getattr(response, "content", response)
    if isinstance(content, list):
        content = "\n".join(str(item) for item in content)
    interpretation = _normalize_llm_interpretation(_parse_json_object(str(content)), state)
    return {"llm_interpretation": interpretation}


def _merge_calculator_state_update(state: AgentState, agent_update: Dict[str, Any]) -> AgentState:
    if not agent_update:
        return state

    new_state = dict(state)
    if isinstance(agent_update.get("stat_summary"), dict):
        new_state["stat_summary"] = {
            **agent_update["stat_summary"],
            **(_value(new_state, "stat_summary", {}) or {}),
        }
    if isinstance(agent_update.get("equipment_summary"), dict):
        new_state["equipment_summary"] = {
            **agent_update["equipment_summary"],
            **(_value(new_state, "equipment_summary", {}) or {}),
        }
    if isinstance(agent_update.get("bottleneck_analysis"), dict):
        new_state["bottleneck_analysis"] = {
            **(_value(new_state, "bottleneck_analysis", {}) or {}),
            **{
                str(key): float(value)
                for key, value in agent_update["bottleneck_analysis"].items()
                if isinstance(value, (int, float))
            },
        }

    llm_interpretation = agent_update.get("llm_interpretation") or {}
    if llm_interpretation:
        tool_results = dict(_value(new_state, "tool_results", {}) or {})
        calculator_result = dict(_value(tool_results, "calculator", {}) or {})
        calculator_result["llm_interpretation"] = llm_interpretation
        if agent_update.get("llm_interpretation_error"):
            calculator_result["llm_interpretation_error"] = str(agent_update["llm_interpretation_error"])
        tool_results["calculator"] = calculator_result
        new_state["tool_results"] = tool_results
    return new_state


def calculator_agent(
    model: str | BaseChatModel | None = None,
    *,
    state: AgentState,
    daily_meso_budget: int = 150_000_000,
) -> AgentState:
    """Run calculator node with create_agent tools and return AgentState-compatible fields."""

    user_query = state["user_query"]

    state = run_calculator(state, daily_meso_budget=daily_meso_budget)
    if _calculator_has_usable_result(state):
        try:
            if model is None:
                model = get_llm()
            agent_update = _generate_agent_state_update(state, model)
        except Exception as exc:
            agent_update = {
                "llm_interpretation": _fallback_calculator_interpretation(state),
                "llm_interpretation_error": exc,
            }
    else:
        agent_update = {}

    state = _merge_calculator_state_update(state, agent_update)
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
