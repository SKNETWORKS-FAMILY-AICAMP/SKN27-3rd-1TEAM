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



from langchain.agents import create_agent
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage
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

_STAT_SCORE_WEIGHTS = {
    "str_val": 1,
    "dex_val": 1,
    "int_val": 1,
    "luk_val": 1,
    "all_stat_percent": 9,
    "attack_power": 4,
    "magic_power": 4,
    "boss_damage_percent": 6,
    "ignore_def_percent": 5,
    "damage_percent": 4,
    "crit_damage": 8,
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


def _safe_round(value: float, digits: int = 4) -> float:
    if value == float("inf") or value != value:
        return 0.0
    return round(value, digits)


def _format_number(value: Any, digits: int = 2) -> str:
    if value in (None, ""):
        return "0"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    if number.is_integer():
        return f"{int(number):,}"
    return f"{number:,.{digits}f}".rstrip("0").rstrip(".")


def _upsert_context_section(context: Any, section_id: str, body: str) -> str:
    start = f"[{section_id}:start]"
    end = f"[{section_id}:end]"
    block = f"{start}\n{body.strip()}\n{end}"
    text = str(context or "").strip()
    pattern = rf"{re.escape(start)}[\s\S]*?{re.escape(end)}"
    if re.search(pattern, text):
        return re.sub(pattern, block, text).strip()
    return "\n\n".join(part for part in (text, block) if part).strip()


def _build_calculator_answer_context(state: AgentState) -> str:
    profile = _value(state, "character_profile", {})
    stat_summary = _value(state, "stat_summary", {}) or {}
    equipment_summary = _value(state, "equipment_summary", {}) or {}
    bottlenecks = _value(state, "bottleneck_analysis", {}) or {}
    forecast = _value(equipment_summary, "growth_forecast", []) or []

    top_bottlenecks = sorted(
        ((str(key), float(value)) for key, value in bottlenecks.items() if isinstance(value, (int, float))),
        key=lambda item: item[1],
        reverse=True,
    )[:5]
    bottleneck_text = ", ".join(f"{key}={_format_number(value, 3)}" for key, value in top_bottlenecks) or "none"

    growth_text = "; ".join(
        (
            f"{_value(item, 'category', 'growth')} "
            f"target={_value(item, 'target', _value(item, 'slot', 'unknown'))} "
            f"expected_score_after={_format_number(_value(item, 'expected_score_after', 0), 4)} "
            f"gain={_format_number(_value(item, 'expected_damage_gain_percent', 0))}%"
        )
        for item in forecast[:3]
    ) or "none"

    return "\n".join(
        [
            "Calculator result for final answer.",
            f"- Character: {_value(profile, 'character_name', _value(state, 'character_name', ''))} / job={_value(profile, 'job_name', '')} / level={_format_number(_value(profile, 'level', 0))}.",
            (
                "- Current stats: "
                f"combat_power={_format_number(_value(stat_summary, 'combat_power', 0))}, "
                f"main_stat={_format_number(_value(stat_summary, 'main_stat', 0))}, "
                f"boss_damage={_format_number(_value(stat_summary, 'boss_damage', 0))}, "
                f"ignore_def={_format_number(_value(stat_summary, 'ignore_def', 0))}, "
                f"crit_rate={_format_number(_value(stat_summary, 'crit_rate', 0))}, "
                f"crit_damage={_format_number(_value(stat_summary, 'crit_damage', 0))}, "
                f"arcane_force={_format_number(_value(stat_summary, 'arcane_force', 0))}, "
                f"authentic_force={_format_number(_value(stat_summary, 'authentic_force', 0))}, "
                f"damage_score={_format_number(_value(stat_summary, 'damage_score', 0), 4)}."
            ),
            (
                "- Equipment summary: "
                f"equipment_count={_format_number(_value(equipment_summary, 'equipment_count', 0))}, "
                f"total_starforce={_format_number(_value(equipment_summary, 'total_starforce', 0))}."
            ),
            f"- Calculator bottlenecks: {bottleneck_text}.",
            f"- Top growth options: {growth_text}.",
        ]
    )


def _stat_package_score(stats: Any) -> float:
    return sum(_number(stats, key) * weight for key, weight in _STAT_SCORE_WEIGHTS.items())


def _potential_rank(grade: Any) -> int:
    if grade is None:
        return 0
    return _POTENTIAL_GRADE_RANK.get(str(grade).strip(), 0)


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


def _state_equipment_items(state: AgentState) -> List[Dict[str, Any]]:
    profile = _value(state, "character_profile", {})
    items = _value(state, "equipment_items", None)
    if items is None:
        items = _value(profile, "equipment_list", [])
    return [item for item in _plain(items or []) if isinstance(item, dict)]


def _extract_character_input(state: AgentState) -> Dict[str, Any]:
    profile = _value(state, "character_profile", {})
    stat_sources = [_value(state, "character_stats", {}), _value(profile, "final_stats", {})]
    union_sources = [_value(state, "union_status", {}), _value(profile, "union_info", {})]
    equipment_items = _state_equipment_items(state)
    main_stat = _first_number(stat_sources, ["main_stat", "primary_stat", "mainStat"], 0)
    if main_stat <= 0:
        main_stat = max(
            _first_number(stat_sources, ["str_val", "str", "STR"], 0),
            _first_number(stat_sources, ["dex", "dex_val", "DEX"], 0),
            _first_number(stat_sources, ["int_val", "int", "INT"], 0),
            _first_number(stat_sources, ["luk", "luk_val", "LUK"], 0),
        )
    return {
        "character_level": int(_first_number([profile, *stat_sources, state], ["level", "character_level"], 0)),
        "combat_power": int(_first_number(stat_sources, ["combat_power", "current_combat_power"], 0)),
        "main_stat": int(main_stat),
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
        "starforce": int(
            _first_number(
                stat_sources,
                ["starforce", "total_starforce"],
                sum(int(_number(item, "starforce", 0)) for item in equipment_items),
            )
        ),
        "union_level": int(_first_number(union_sources, ["union_level"], 0)),
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
        score = (
            _stat_package_score(_value(item, "total_stats", {}))
            + _stat_package_score(_value(item, "bonus_stats", {})) * 0.4
            + _stat_package_score(_value(item, "scroll_stats", {})) * 0.3
            + starforce * 18
        )
        total_starforce += starforce
        total_score += score

        target_potential = _POTENTIAL_GRADE_RANK[
            "레전드리" if character_level >= 270 else "유니크" if character_level >= 220 else "에픽"
        ]
        target_additional = _POTENTIAL_GRADE_RANK["유니크" if character_level >= 270 else "에픽"]
        upgrade_flags = []
        if starforce_target["recommended"] and starforce < starforce_target["recommended"]:
            upgrade_flags.append(f"starforce_under_{starforce_target['recommended']}")
        if _potential_rank(_value(item, "potential_grade")) < target_potential:
            upgrade_flags.append("potential_under_target")
        if _potential_rank(_value(item, "additional_potential_grade")) < target_additional:
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


def _growth_item(
    *,
    category: str,
    target: str,
    action: str,
    gain_percent: float,
    base_score: float,
    combat_power: float,
    cost: int,
    daily_meso_budget: int,
    days: int | None = None,
    basis: str | None = None,
    score_gain_percent: float | None = None,
    cp_gain_percent: float | None = None,
    efficiency_score: float | None = None,
) -> Dict[str, Any]:
    score_gain_percent = gain_percent if score_gain_percent is None else score_gain_percent
    cp_gain_percent = gain_percent if cp_gain_percent is None else cp_gain_percent
    item = {
        "category": category,
        "target": target,
        "action": action,
        "expected_damage_gain_percent": _safe_round(gain_percent, 2),
        "expected_score_after": _safe_round(base_score * (1 + score_gain_percent / 100), 6),
        "expected_cp_gain": int(combat_power * cp_gain_percent / 100),
        "estimated_cost_meso": cost,
        "estimated_days": days or max(1, int((cost + daily_meso_budget - 1) // daily_meso_budget)),
        "efficiency_score": (
            _safe_round(gain_percent / max(cost / 1_000_000_000, 0.1), 3)
            if efficiency_score is None
            else efficiency_score
        ),
    }
    if basis:
        item["basis"] = basis
    return item


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
            cost = 6_000_000_000
            for limit, candidate in ((10, 80_000_000), (15, 350_000_000), (17, 900_000_000), (20, 2_500_000_000)):
                if current_starforce < limit:
                    cost = candidate
                    break
            star_gap = recommended_starforce - current_starforce
            gain_percent = max(2.0, min(star_gap * 1.15, 14.0))
            forecast.append(
                _growth_item(
                    category="장비 강화",
                    target=target,
                    action=f"스타포스 {recommended_starforce}성 권장선 달성",
                    gain_percent=gain_percent,
                    base_score=base_score,
                    combat_power=combat_power,
                    cost=cost,
                    daily_meso_budget=daily_meso_budget,
                    basis="neo4j_equipment_growth_rule",
                )
            )

        if "potential_under_target" in (slot.get("upgrade_flags") or []):
            cost = 700_000_000
            gain_percent = 4.5 if _number(stat_summary, "character_level") >= 270 else 3.5
            forecast.append(
                _growth_item(
                    category="잠재능력",
                    target=target,
                    action="주요 장비 잠재 목표 등급 달성",
                    gain_percent=gain_percent,
                    base_score=base_score,
                    combat_power=combat_power,
                    cost=cost,
                    daily_meso_budget=daily_meso_budget,
                    score_gain_percent=3.5,
                    cp_gain_percent=3.5,
                )
            )

    if _number(stat_summary, "arcane_force") < _STAT_TARGETS["arcane_force"]:
        cost = 250_000_000
        gain_percent = 2.5
        forecast.append(
            _growth_item(
                category="심볼",
                target="아케인포스",
                action="아케인 심볼 레벨업",
                gain_percent=gain_percent,
                base_score=base_score,
                combat_power=combat_power,
                cost=cost,
                daily_meso_budget=daily_meso_budget,
            )
        )

    if _number(stat_summary, "union_level") < _STAT_TARGETS["union_level"]:
        remaining = _STAT_TARGETS["union_level"] - _number(stat_summary, "union_level")
        forecast.append(
            _growth_item(
                category="유니온",
                target="유니온 레벨",
                action="유니온 8000 구간까지 육성",
                gain_percent=1.8,
                base_score=base_score,
                combat_power=combat_power,
                cost=0,
                daily_meso_budget=daily_meso_budget,
                days=max(7, int(remaining / 120)),
                efficiency_score=1.8,
            )
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
        key: 1 - max(0.0, min(_number(stat_summary, key) / target, 1.0))
        for key, target in _STAT_TARGETS.items()
        if key != "starforce" and target > 0
    }
    starforce_target = max(_number(equipment_summary, "total_recommended_starforce"), _STAT_TARGETS["starforce"])
    scores["starforce"] = 1 - max(0.0, min(_number(equipment_summary, "total_starforce") / starforce_target, 1.0))

    if growth_forecast:
        best = growth_forecast[0]
        category = str(best.get("category") or "growth_efficiency")
        scores[f"growth_option:{category}"] = min(float(best.get("efficiency_score", 0)) / 10, 1.0)

    return {key: _safe_round(value, 4) for key, value in scores.items() if value > 0.05}


def _calculator_state_payload(state: AgentState) -> Dict[str, Any]:
    stat_summary = _value(state, "stat_summary", {}) or {}
    equipment_summary = _value(state, "equipment_summary", {}) or {}
    return {
        "user_query": _value(state, "user_query", ""),
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
        missing = [
            key
            for key in ("character_stats", "equipment_items", "union_status")
            if key not in state or state[key] is None
        ]
        if missing:
            raise ValueError(f"calculator input state missing fields: {missing}")
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
        new_state = dict(state)
        new_state["errors"] = [*new_state.get("errors", []), message]
        empty_result = {
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
        new_state.update(empty_result)
        new_state["tool_results"] = {
            **new_state.get("tool_results", {}),
            "calculator": empty_result,
        }
        new_state["context"] = _upsert_context_section(
            new_state.get("context", ""),
            "calculator_context",
            f"Calculator result for final answer.\n- Calculator failed: {message}",
        )
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
    new_state["context"] = _upsert_context_section(
        new_state.get("context", ""),
        "calculator_context",
        _build_calculator_answer_context(new_state),
    )

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


def _generate_agent_state_update(
    state: AgentState,
    model: str | BaseChatModel | None,
) -> Dict[str, Any]:
    if model is None:
        model = get_llm()

    calculator = create_agent(
        model=model,
        tools=CALCULATOR_TOOLS,
        system_prompt=CALCULATOR_STATE_SYSTEM_PROMPT,
    )
    result = calculator.invoke(
        {
            "messages": [
                HumanMessage(
                    content=(
                        "Return only a JSON object for AgentState update. "
                        f"Input: {json.dumps(_calculator_state_payload(state), ensure_ascii=False)}"
                    )
                )
            ]
        }
    )
    parsed = _parse_json_object(result["messages"][-1].content)
    allowed = {"stat_summary", "equipment_summary", "bottleneck_analysis", "llm_interpretation"}
    parsed = {key: value for key, value in parsed.items() if key in allowed}
    for key in ("stat_summary", "equipment_summary", "bottleneck_analysis", "llm_interpretation"):
        if key in parsed and not isinstance(parsed[key], dict):
            parsed.pop(key, None)
    return parsed


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
    if model is None:
        model = get_llm()

    state = run_calculator(state, daily_meso_budget=daily_meso_budget)
    calculator_result = _value(_value(state, "tool_results", {}), "calculator", {}) or {}
    stat_summary = _value(state, "stat_summary", {}) or {}
    equipment_summary = _value(state, "equipment_summary", {}) or {}
    has_usable_result = (
        not _value(calculator_result, "error")
        and _value(stat_summary, "data_reliability") != "calculation_failed_or_missing_data"
        and bool(_value(stat_summary, "damage_score") or _value(equipment_summary, "equipment_count"))
    )
    if has_usable_result:
        try:
            agent_update = _generate_agent_state_update(state, model)
        except Exception as exc:
            state = dict(state)
            state["errors"] = [
                *state.get("errors", []),
                f"calculator create_agent state generation failed: {exc}",
            ]
            agent_update = {}
    else:
        agent_update = {}

    state = _merge_calculator_state_update(state, agent_update)
    validate_agent_outputs("calculator", state)
    return {
        **state,
        "user_query": user_query,
    }
