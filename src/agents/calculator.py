from __future__ import annotations

import os
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(current_dir, "../../"))
sys.path.append(project_root)

import requests
from dotenv import load_dotenv
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

_NEXON_API_BASE_URL = "https://open.api.nexon.com/maplestory/v1"
_NEXON_API_TIMEOUT_SECONDS = 10


class NexonCharacterLookupInput(BaseModel):
    """Input for fetching MapleStory character data from Nexon Open API."""

    character_name: str = Field(..., description="MapleStory character name.")
    date: Optional[str] = Field(None, description="KST query date in YYYY-MM-DD. Defaults to yesterday.")


class DamageSimulationInput(BaseModel):
    """Normalized stat input for relative damage simulation."""

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
    union_level: int = Field(0, ge=0)


class EquipmentContributionInput(BaseModel):
    """Input for summarizing equipment contribution."""

    equipment_items: List[Dict[str, Any]] = Field(default_factory=list)
    main_stat: int = Field(0, ge=0)
    attack_power: int = Field(0, ge=0)
    magic_power: int = Field(0, ge=0)


class GrowthEstimateInput(BaseModel):
    """Input for estimating growth cost, duration, and value."""

    stat_summary: Dict[str, Any] = Field(default_factory=dict)
    equipment_summary: Dict[str, Any] = Field(default_factory=dict)
    daily_meso_budget: int = Field(150_000_000, ge=1)


class BottleneckAnalysisInput(BaseModel):
    """Input for scoring current growth bottlenecks."""

    stat_summary: Dict[str, Any] = Field(default_factory=dict)
    equipment_summary: Dict[str, Any] = Field(default_factory=dict)
    growth_options: List[Dict[str, Any]] = Field(default_factory=list)


_NEXON_FINAL_STAT_KEYS = {
    "전투력": "combat_power",
    "최소 스탯공격력": "min_stat_damage",
    "최소 스탯 공격력": "min_stat_damage",
    "최대 스탯공격력": "max_stat_damage",
    "최대 스탯 공격력": "max_stat_damage",
    "STR": "str_val",
    "DEX": "dex",
    "INT": "int_val",
    "LUK": "luk",
    "HP": "hp",
    "MP": "mp",
    "데미지": "damage",
    "보스 몬스터 데미지": "boss_damage",
    "보스 데미지": "boss_damage",
    "최종 데미지": "final_damage",
    "방어율 무시": "ignore_def",
    "몬스터 방어율 무시": "ignore_def",
    "크리티컬 확률": "crit_rate",
    "크리티컬 데미지": "crit_damage",
    "공격력": "attack_power",
    "마력": "magic_power",
    "공격 속도": "attack_speed",
    "버프 지속시간": "buff_duration",
    "아케인포스": "arcane_force",
    "어센틱포스": "authentic_force",
    "스타포스": "starforce",
}

_NEXON_INT_STAT_KEYS = {
    "combat_power",
    "str_val",
    "dex",
    "int_val",
    "luk",
    "hp",
    "mp",
    "attack_power",
    "magic_power",
    "attack_speed",
    "arcane_force",
    "authentic_force",
    "starforce",
}

_NEXON_OPTION_KEYS = {
    "str": "str_val",
    "dex": "dex_val",
    "int": "int_val",
    "luk": "luk_val",
    "max_hp": "hp",
    "attack_power": "attack_power",
    "magic_power": "magic_power",
    "boss_damage": "boss_damage_percent",
    "ignore_monster_armor": "ignore_def_percent",
    "ignore_def": "ignore_def_percent",
    "damage": "damage_percent",
    "all_stat": "all_stat_percent",
}

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


def _load_project_env() -> None:
    root = Path(__file__).resolve().parents[2]
    for env_path in (root / ".env", root / "database" / ".env", Path(__file__).resolve().parent / ".env"):
        if not env_path.exists():
            continue
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _value(source: Any, key: str, default: Any = None) -> Any:
    if source is None:
        return default
    if isinstance(source, dict):
        return source.get(key, default)
    return getattr(source, key, default)


def _number(source: Any, key: str, default: float = 0.0) -> float:
    value = _value(source, key, default)
    return _parse_number(value, default=default)


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


def _ratio(value: float, target: float) -> float:
    if target <= 0:
        return 1.0
    return max(0.0, min(value / target, 1.0))


def _safe_round(value: float, digits: int = 4) -> float:
    if value == float("inf") or value != value:
        return 0.0
    return round(value, digits)


def _nexon_api_date(date: Optional[str] = None) -> str:
    if date:
        return date
    _load_project_env()
    env_date = os.environ.get("NEXON_API_DATE")
    if env_date:
        return env_date
    return (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")


def _nexon_headers() -> Dict[str, str]:
    _load_project_env()
    api_key = os.environ.get("NEXON_API_KEY")
    if not api_key:
        raise RuntimeError("NEXON_API_KEY is required to fetch character data from Nexon Open API.")
    return {"x-nxopen-api-key": api_key, "Accept": "application/json"}


def _nexon_error_message(response: requests.Response) -> str:
    try:
        data = response.json()
    except ValueError:
        return response.text[:500]
    if isinstance(data, dict):
        return str(data.get("message") or data.get("error") or data)[:500]
    return str(data)[:500]


def _nexon_get(path: str, params: Dict[str, Any]) -> Dict[str, Any]:
    try:
        response = requests.get(
            f"{_NEXON_API_BASE_URL}{path}",
            headers=_nexon_headers(),
            params=params,
            timeout=_NEXON_API_TIMEOUT_SECONDS,
        )
    except requests.RequestException as exc:
        raise RuntimeError(f"Nexon Open API request failed for {path}: {exc}") from exc

    if response.status_code != 200:
        raise RuntimeError(
            f"Nexon Open API request failed for {path} "
            f"({response.status_code}): {_nexon_error_message(response)}"
        )

    try:
        data = response.json()
    except ValueError as exc:
        raise RuntimeError(f"Nexon Open API returned non-JSON response for {path}.") from exc
    return data if isinstance(data, dict) else {}


def _normalize_nexon_final_stats(stat_response: Dict[str, Any]) -> Dict[str, Any]:
    stat_summary: Dict[str, Any] = {}
    for item in stat_response.get("final_stat") or []:
        if not isinstance(item, dict):
            continue
        target_key = _NEXON_FINAL_STAT_KEYS.get(str(item.get("stat_name", "")).strip())
        if not target_key:
            continue
        value = _parse_number(item.get("stat_value"))
        stat_summary[target_key] = int(value) if target_key in _NEXON_INT_STAT_KEYS else value

    stat_summary["main_stat"] = int(
        max(
            _number(stat_summary, "str_val"),
            _number(stat_summary, "dex"),
            _number(stat_summary, "int_val"),
            _number(stat_summary, "luk"),
        )
    )
    return stat_summary


def _normalize_nexon_option(option: Any) -> Dict[str, Any]:
    if not isinstance(option, dict):
        return {}
    normalized: Dict[str, Any] = {}
    for source_key, target_key in _NEXON_OPTION_KEYS.items():
        value = _parse_number(option.get(source_key))
        if value == 0:
            continue
        if target_key.endswith("_val") or target_key in {"attack_power", "magic_power", "hp"}:
            normalized[target_key] = int(value)
        else:
            normalized[target_key] = value
    return normalized


def _normalize_nexon_equipment(equipment_response: Dict[str, Any]) -> List[Dict[str, Any]]:
    equipment_items: List[Dict[str, Any]] = []
    for item in equipment_response.get("item_equipment") or []:
        if not isinstance(item, dict):
            continue
        equipment_items.append(
            {
                "item_name": item.get("item_name", ""),
                "part": item.get("item_equipment_part") or item.get("item_equipment_slot", ""),
                "item_gender": item.get("item_gender"),
                "starforce": int(_parse_number(item.get("starforce"))),
                "potential_grade": item.get("potential_option_grade"),
                "additional_potential_grade": item.get("additional_potential_option_grade"),
                "total_stats": _normalize_nexon_option(item.get("item_total_option")),
                "bonus_stats": _normalize_nexon_option(item.get("item_add_option")),
                "scroll_stats": _normalize_nexon_option(item.get("item_etc_option")),
                "set_name": item.get("set_item_name"),
            }
        )
    return equipment_items


def _normalize_nexon_union(union_response: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "union_level": int(_parse_number(union_response.get("union_level"))),
        "union_grade": str(union_response.get("union_grade") or ""),
        "artifact_level": None,
        "artifact_exp": 0,
    }


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


def _estimated_days(cost_meso: int, daily_meso_budget: int) -> int:
    return max(1, int((cost_meso + daily_meso_budget - 1) // daily_meso_budget))


def _extract_character_name_from_query(query: str) -> str:
    tokens = re.findall(r"[0-9A-Za-z가-힣_]+", query or "")
    stopwords = {
        "내",
        "캐릭터",
        "캐릭",
        "전투력",
        "딜",
        "계산",
        "성장",
        "비용",
        "기간",
        "예측",
        "해줘",
        "알려줘",
    }
    for token in tokens:
        if token not in stopwords and len(token) >= 2:
            return token
    return ""


def _extract_stat_summary(state: AgentState) -> Dict[str, Any]:
    stats = state.get("character_stats") or _value(state.get("character_profile"), "final_stats", {}) or {}
    union = state.get("union_status") or _value(state.get("character_profile"), "union_info", {}) or {}
    main_stat = int(
        max(
            _number(stats, "main_stat"),
            _number(stats, "str_val"),
            _number(stats, "dex"),
            _number(stats, "int_val"),
            _number(stats, "luk"),
        )
    )
    return {
        "combat_power": int(_number(stats, "combat_power")),
        "main_stat": main_stat,
        "str_val": int(_number(stats, "str_val")),
        "dex": int(_number(stats, "dex")),
        "int_val": int(_number(stats, "int_val")),
        "luk": int(_number(stats, "luk")),
        "attack_power": int(_number(stats, "attack_power")),
        "magic_power": int(_number(stats, "magic_power")),
        "damage": _number(stats, "damage"),
        "boss_damage": _number(stats, "boss_damage"),
        "final_damage": _number(stats, "final_damage"),
        "ignore_def": _number(stats, "ignore_def"),
        "crit_rate": _number(stats, "crit_rate"),
        "crit_damage": _number(stats, "crit_damage"),
        "arcane_force": int(_number(stats, "arcane_force")),
        "authentic_force": int(_number(stats, "authentic_force")),
        "starforce": int(_number(stats, "starforce", _sum_equipment_starforce(state.get("equipment_items") or []))),
        "union_level": int(_number(union, "union_level")),
    }


@tool(args_schema=NexonCharacterLookupInput)
def fetch_nexon_character_state(character_name: str, date: Optional[str] = None) -> Dict[str, Any]:
    """Fetch MapleStory character stats, equipment, and union data from Nexon Open API."""

    api_date = _nexon_api_date(date)
    id_response = _nexon_get("/id", {"character_name": character_name})
    ocid = id_response.get("ocid")
    if not ocid:
        raise RuntimeError(f"Nexon Open API did not return ocid for character: {character_name}")

    params = {"ocid": ocid, "date": api_date}
    basic_response = _nexon_get("/character/basic", params)
    stat_response = _nexon_get("/character/stat", params)
    equipment_response = _nexon_get("/character/item-equipment", params)
    try:
        union_response = _nexon_get("/user/union", params)
    except RuntimeError as exc:
        union_response = {"error": str(exc)}

    character_stats = _normalize_nexon_final_stats(stat_response)
    equipment_items = _normalize_nexon_equipment(equipment_response)
    union_status = _normalize_nexon_union(union_response)
    if union_status.get("union_level"):
        character_stats["union_level"] = union_status["union_level"]

    character_profile = {
        "character_name": basic_response.get("character_name") or character_name,
        "job_name": basic_response.get("character_class") or stat_response.get("character_class", ""),
        "world_name": basic_response.get("world_name", ""),
        "level": int(_parse_number(basic_response.get("character_level"))),
        "gender": basic_response.get("character_gender"),
        "final_stats": character_stats,
        "equipment_list": equipment_items,
        "union_info": union_status,
    }

    return {
        "ocid": ocid,
        "character_name": character_profile["character_name"],
        "world_name": character_profile["world_name"],
        "character_profile": character_profile,
        "character_stats": character_stats,
        "equipment_items": equipment_items,
        "union_status": union_status,
        "raw_api_results": {
            "nexon": {
                "date": api_date,
                "id": id_response,
                "basic": basic_response,
                "stat": stat_response,
                "item_equipment": equipment_response,
                "union": union_response,
            }
        },
    }


@tool(args_schema=DamageSimulationInput)
def simulate_damage_score(
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
    union_level: int = 0,
) -> Dict[str, Any]:
    """Calculate a deterministic relative damage score for growth comparison."""

    attack_stat = max(attack_power, magic_power)
    stat_factor = max(main_stat, 1) / 10_000
    attack_factor = max(attack_stat, 1) / 1_000
    damage_factor = 1 + max(damage, 0) / 100
    boss_factor = 1 + max(boss_damage, 0) / 100
    final_damage_factor = 1 + max(final_damage, 0) / 100
    crit_factor = 1 + min(max(crit_rate, 0), 100) / 100 * max(crit_damage, 0) / 100
    ignore_def_factor = 1 / max(0.3, 1 - min(max(ignore_def, 0), 100) / 100 * 0.3)
    force_factor = 1 + min(arcane_force / 1_320, 1) * 0.05 + min(authentic_force / 730, 1) * 0.05
    union_factor = 1 + min(union_level / 8_500, 1) * 0.04
    relative_damage_score = (
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
        "combat_power": combat_power,
        "main_stat": main_stat,
        "attack_power": attack_power,
        "magic_power": magic_power,
        "primary_attack": attack_stat,
        "damage": damage,
        "boss_damage": boss_damage,
        "final_damage": final_damage,
        "ignore_def": ignore_def,
        "crit_rate": crit_rate,
        "crit_damage": crit_damage,
        "arcane_force": arcane_force,
        "authentic_force": authentic_force,
        "union_level": union_level,
        "damage_score": _safe_round(relative_damage_score, 6),
        "formula": "relative_growth_comparison_score",
        "assumption": "실제 DPM이 아니라 성장 전후 비교를 위한 상대 딜 점수입니다.",
    }


@tool(args_schema=EquipmentContributionInput)
def summarize_equipment_contribution(
    equipment_items: List[Dict[str, Any]],
    main_stat: int = 0,
    attack_power: int = 0,
    magic_power: int = 0,
) -> Dict[str, Any]:
    """Summarize equipment contribution, starforce status, and weak upgrade slots."""

    by_slot: Dict[str, Any] = {}
    total_score = 0.0
    total_starforce = 0
    weak_slots: List[Dict[str, Any]] = []

    for item in equipment_items:
        slot = str(_value(item, "part", "") or "unknown")
        score = _equipment_contribution_score(item)
        total_score += score
        starforce = int(_number(item, "starforce"))
        total_starforce += starforce
        potential_grade = _value(item, "potential_grade")
        additional_grade = _value(item, "additional_potential_grade")

        upgrade_flags: List[str] = []
        if starforce < 17:
            upgrade_flags.append("starforce_under_17")
        if _potential_rank(potential_grade) < 3:
            upgrade_flags.append("potential_under_unique")
        if _potential_rank(additional_grade) < 2:
            upgrade_flags.append("additional_potential_under_epic")

        slot_summary = {
            "item_name": _value(item, "item_name", ""),
            "part": slot,
            "starforce": starforce,
            "potential_grade": potential_grade,
            "additional_potential_grade": additional_grade,
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
        "equipment_contribution_score": _safe_round(total_score, 2),
        "average_contribution_score": _safe_round(total_score / max(len(equipment_items), 1), 2),
        "main_stat_reference": main_stat,
        "attack_reference": max(attack_power, magic_power),
        "by_slot": by_slot,
        "weak_slots": weak_slots[:8],
    }


@tool(args_schema=GrowthEstimateInput)
def estimate_growth_options(
    stat_summary: Dict[str, Any],
    equipment_summary: Dict[str, Any],
    daily_meso_budget: int = 150_000_000,
) -> List[Dict[str, Any]]:
    """Estimate growth action cost, duration, and relative damage gain."""

    options: List[Dict[str, Any]] = []
    base_score = max(_number(stat_summary, "damage_score"), 0.000001)
    weak_slots = equipment_summary.get("weak_slots") or []

    for slot in weak_slots[:5]:
        current_starforce = int(_number(slot, "starforce"))
        if current_starforce < 17:
            cost = _estimate_starforce_cost(current_starforce)
            gain_percent = max(2.0, min((17 - current_starforce) * 1.4, 12.0))
            options.append(
                {
                    "category": "장비 강화",
                    "target": slot.get("part") or slot.get("item_name"),
                    "action": "스타포스 17성 우선 달성",
                    "expected_damage_gain_percent": _safe_round(gain_percent, 2),
                    "expected_score_after": _safe_round(base_score * (1 + gain_percent / 100), 6),
                    "expected_cp_gain": int(_number(stat_summary, "combat_power") * gain_percent / 100),
                    "estimated_cost_meso": cost,
                    "estimated_days": _estimated_days(cost, daily_meso_budget),
                    "efficiency_score": _safe_round(gain_percent / max(cost / 1_000_000_000, 0.1), 3),
                }
            )

        if "potential_under_unique" in (slot.get("upgrade_flags") or []):
            cost = 700_000_000
            gain_percent = 3.5
            options.append(
                {
                    "category": "잠재능력",
                    "target": slot.get("part") or slot.get("item_name"),
                    "action": "주요 장비 유니크 이상 목표",
                    "expected_damage_gain_percent": gain_percent,
                    "expected_score_after": _safe_round(base_score * 1.035, 6),
                    "expected_cp_gain": int(_number(stat_summary, "combat_power") * 0.035),
                    "estimated_cost_meso": cost,
                    "estimated_days": _estimated_days(cost, daily_meso_budget),
                    "efficiency_score": _safe_round(gain_percent / (cost / 1_000_000_000), 3),
                }
            )

    if _number(stat_summary, "arcane_force") < 1_320:
        cost = 250_000_000
        gain_percent = 2.5
        options.append(
            {
                "category": "심볼",
                "target": "아케인포스",
                "action": "아케인 심볼 레벨업",
                "expected_damage_gain_percent": gain_percent,
                "expected_score_after": _safe_round(base_score * 1.025, 6),
                "expected_cp_gain": int(_number(stat_summary, "combat_power") * 0.025),
                "estimated_cost_meso": cost,
                "estimated_days": _estimated_days(cost, daily_meso_budget),
                "efficiency_score": _safe_round(gain_percent / (cost / 1_000_000_000), 3),
            }
        )

    if _number(stat_summary, "union_level") < 8_000:
        cost = 0
        gain_percent = 1.8
        options.append(
            {
                "category": "유니온",
                "target": "유니온 레벨",
                "action": "유니온 8000 구간까지 육성",
                "expected_damage_gain_percent": gain_percent,
                "expected_score_after": _safe_round(base_score * 1.018, 6),
                "expected_cp_gain": int(_number(stat_summary, "combat_power") * 0.018),
                "estimated_cost_meso": cost,
                "estimated_days": max(7, int((8_000 - _number(stat_summary, "union_level")) / 120)),
                "efficiency_score": 1.8,
            }
        )

    options.sort(key=lambda item: (item["efficiency_score"], item["expected_damage_gain_percent"]), reverse=True)
    return options[:10]


@tool(args_schema=BottleneckAnalysisInput)
def calculate_bottleneck_scores(
    stat_summary: Dict[str, Any],
    equipment_summary: Dict[str, Any],
    growth_options: List[Dict[str, Any]],
) -> Dict[str, float]:
    """Calculate 0 to 1 bottleneck scores. Higher means more urgent."""

    scores = {
        "combat_power": 1 - _ratio(_number(stat_summary, "combat_power"), 50_000_000),
        "main_stat": 1 - _ratio(_number(stat_summary, "main_stat"), 50_000),
        "primary_attack": 1 - _ratio(_number(stat_summary, "primary_attack"), 4_000),
        "boss_damage": 1 - _ratio(_number(stat_summary, "boss_damage"), 300),
        "ignore_def": 1 - _ratio(_number(stat_summary, "ignore_def"), 95),
        "crit_rate": 1 - _ratio(_number(stat_summary, "crit_rate"), 100),
        "crit_damage": 1 - _ratio(_number(stat_summary, "crit_damage"), 80),
        "arcane_force": 1 - _ratio(_number(stat_summary, "arcane_force"), 1_320),
        "authentic_force": 1 - _ratio(_number(stat_summary, "authentic_force"), 730),
        "union_level": 1 - _ratio(_number(stat_summary, "union_level"), 8_000),
        "starforce": 1 - _ratio(_number(equipment_summary, "total_starforce"), 280),
    }

    if growth_options:
        best = growth_options[0]
        key = str(best.get("category") or "growth_efficiency")
        scores[f"growth_option:{key}"] = min(float(best.get("efficiency_score", 0)) / 10, 1.0)

    return {key: _safe_round(value, 4) for key, value in scores.items() if value > 0.05}


def _hydrate_state_from_nexon_if_needed(state: AgentState, date: Optional[str] = None) -> AgentState:
    if state.get("character_stats") and state.get("equipment_items") and state.get("union_status"):
        return state

    character_name = state.get("character_name") or _extract_character_name_from_query(state.get("user_query", ""))
    if not character_name:
        return state

    fetched = fetch_nexon_character_state.invoke({"character_name": character_name, "date": date})
    return {
        **state,
        **fetched,
        "raw_api_results": {
            **state.get("raw_api_results", {}),
            **fetched.get("raw_api_results", {}),
        },
    }


def _append_state_error(state: AgentState, message: str) -> AgentState:
    new_state = dict(state)
    new_state["errors"] = [*new_state.get("errors", []), message]
    return new_state


def run_calculator(
    state: AgentState,
    *,
    date: Optional[str] = None,
    daily_meso_budget: int = 150_000_000,
) -> AgentState:
    """Run the AgentState-compatible calculator step with deterministic tool outputs."""

    try:
        hydrated_state = _hydrate_state_from_nexon_if_needed(state, date=date)
        validate_agent_inputs("calculator", hydrated_state)

        stat_input = _extract_stat_summary(hydrated_state)
        damage_summary = simulate_damage_score.invoke(stat_input)
        equipment_summary = summarize_equipment_contribution.invoke(
            {
                "equipment_items": hydrated_state.get("equipment_items", []),
                "main_stat": damage_summary["main_stat"],
                "attack_power": damage_summary["attack_power"],
                "magic_power": damage_summary["magic_power"],
            }
        )
        growth_options = estimate_growth_options.invoke(
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
                "growth_options": growth_options,
            }
        )
    except Exception as exc:
        message = f"calculator failed: {exc}"
        new_state = _append_state_error(state, message)
        new_state["stat_summary"] = {}
        new_state["equipment_summary"] = {"growth_options": []}
        new_state["bottleneck_analysis"] = {}
        return new_state

    new_state = dict(hydrated_state)
    new_state["stat_summary"] = damage_summary
    new_state["equipment_summary"] = {
        **equipment_summary,
        "growth_options": growth_options,
        "daily_meso_budget": daily_meso_budget,
    }
    new_state["bottleneck_analysis"] = bottleneck_analysis
    new_state["tool_results"] = {
        **new_state.get("tool_results", {}),
        "calculator": {
            "stat_summary": damage_summary,
            "equipment_summary": new_state["equipment_summary"],
            "bottleneck_analysis": bottleneck_analysis,
        },
    }

    validate_agent_outputs("calculator", new_state)
    return new_state


CALCULATOR_TOOLS = [
    fetch_nexon_character_state,
    simulate_damage_score,
    summarize_equipment_contribution,
    estimate_growth_options,
    calculate_bottleneck_scores,
]

CALCULATOR_SYSTEM_PROMPT = f"""
{master_prompt}

You are the MapleStory calculator agent.
Use the provided tools for all numeric calculations.
Fetch character data with fetch_nexon_character_state when AgentState does not already contain normalized stats.
Do not invent character stats, equipment, cost, or period values outside tool outputs.
Your required AgentState outputs are stat_summary, equipment_summary, and bottleneck_analysis.
Damage score is a deterministic relative growth comparison score, not official DPM.
Answer in Korean when a textual explanation is needed.
""".strip()


def calculator_agent(
    model: str | BaseChatModel | None = None,
    *,
    state: AgentState,
    date: Optional[str] = None,
    daily_meso_budget: int = 150_000_000,
) -> AgentState:
    """Create a LangChain calculator agent and return state updated by deterministic tool outputs."""

    if model is None:
        model = get_llm()

    agent = create_agent(
        model=model,
        tools=CALCULATOR_TOOLS,
        system_prompt=CALCULATOR_SYSTEM_PROMPT,
    )
    agent.invoke(
        {
            "messages": [
                HumanMessage(
                    content=(
                        "다음 AgentState를 기반으로 계산 도구를 사용해 수치 계산 과정을 점검하라.\n"
                        "최종 state 갱신은 run_calculator의 tool output으로 수행된다.\n\n"
                        f"user_query: {state.get('user_query', '')}\n"
                        f"character_name: {state.get('character_name', '')}\n"
                        f"character_stats: {state.get('character_stats', {})}\n"
                        f"equipment_items_count: {len(state.get('equipment_items', []) or [])}\n"
                        f"union_status: {state.get('union_status', {})}"
                    )
                )
            ]
        }
    )

    return run_calculator(state, date=date, daily_meso_budget=daily_meso_budget)

