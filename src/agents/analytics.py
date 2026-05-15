from __future__ import annotations

import ast
import re
from datetime import datetime
from typing import Any

from common.state import AgentState, RetrievedDocument
from common.validator import validate_agent_inputs, validate_agent_outputs


STATUS_LABELS = {
    "recommended": "권장",
    "challengeable": "도전 가능",
    "risky": "위험",
    "growth_target": "보완 후 도전",
    "difficult": "어려움",
    "unknown": "판단 보류",
}

STAT_LABELS = {
    "level": "레벨",
    "combat_power": "전투력",
    "main_stat": "주스탯",
    "stat_attack": "주스탯/공마",
    "attack_or_magic": "공격력/마력",
    "boss_damage": "보스 데미지",
    "ignore_def": "방어율 무시",
    "crit_rate": "크리티컬 확률",
    "crit_damage": "크리티컬 데미지",
    "crit": "크리 기대값",
    "final_damage": "최종 데미지",
    "arcane_force": "아케인포스",
    "authentic_force": "어센틱포스",
    "force": "포스",
    "starforce": "스타포스",
    "union_level": "유니온",
}

TARGET_BOSS_HINTS = (
    "루시드",
    "윌",
    "스우",
    "데미안",
    "더스크",
    "듄켈",
    "진힐라",
    "진 힐라",
    "검은 마법사",
    "검마",
    "세렌",
    "칼로스",
    "카링",
    "림보",
    "발드릭스",
    "자쿰",
    "혼테일",
    "핑크빈",
    "반 레온",
    "아카이럼",
    "매그너스",
    "파풀라투스",
    "벨룸",
    "피에르",
    "반반",
    "블러디 퀸",
    "가디언 엔젤 슬라임",
    "가엔슬",
)

DIFFICULTY_HINTS = {
    "이지": "EASY",
    "노말": "NORMAL",
    "하드": "HARD",
    "카오스": "CHAOS",
    "익스트림": "EXTREME",
    "easy": "EASY",
    "normal": "NORMAL",
    "hard": "HARD",
    "chaos": "CHAOS",
    "extreme": "EXTREME",
}

STAT_WEIGHTS = {
    "combat_power": 0.38,
    "main_stat": 0.12,
    "attack_or_magic": 0.08,
    "boss_damage": 0.09,
    "ignore_def": 0.10,
    "crit_rate": 0.03,
    "crit_damage": 0.04,
    "final_damage": 0.06,
    "force": 0.06,
    "level": 0.03,
    "starforce": 0.01,
    "union_level": 0.01,
}

ALL_BOSS_TIER_QUERY_KEYWORDS = (
    "모든 보스",
    "전체 보스",
    "보스 전체",
    "전 보스",
    "모든보스",
    "전체보스",
    "보스 티어표",
    "티어표",
    "도전 가능성 표",
    "가능성 표",
    "가능 티어",
    "보스별 가능",
    "보스별 도전",
    "보스 도전",
)

DIFFICULTY_LABELS_KO = {
    "EASY": "이지",
    "NORMAL": "노멀",
    "HARD": "하드",
    "CHAOS": "카오스",
    "EXTREME": "익스트림",
}


def _plain(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_plain(item) for item in value]
    if hasattr(value, "__dict__"):
        return {key: _plain(item) for key, item in vars(value).items()}
    return value


def _value(source: Any, key: str, default: Any = None) -> Any:
    source = _plain(source)
    if isinstance(source, dict):
        return source.get(key, default)
    return default


def _parse_number(value: Any, default: float = 0.0) -> float:
    if value is None or value == "":
        return default
    if isinstance(value, bool):
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


def _first_number(sources: list[Any], keys: tuple[str, ...], default: float = 0.0) -> float:
    for source in sources:
        for key in keys:
            value = _value(source, key, None)
            if value not in (None, ""):
                parsed = _parse_number(value, default)
                if parsed != default or str(value).strip() in {"0", "0.0"}:
                    return parsed
    return default


def _first_text(sources: list[Any], keys: tuple[str, ...], default: str = "") -> str:
    for source in sources:
        for key in keys:
            value = _value(source, key, None)
            if value not in (None, ""):
                return str(value)
    return default


def _state_stat_sources(state: AgentState) -> list[Any]:
    profile = _plain(state.get("character_profile", {}))
    return [
        state.get("stat_summary", {}),
        _value(profile, "final_stats", {}),
        state.get("character_stats", {}),
        profile,
    ]


def _state_union_sources(state: AgentState) -> list[Any]:
    profile = _plain(state.get("character_profile", {}))
    return [
        state.get("stat_summary", {}),
        _value(profile, "union_info", {}),
        state.get("union_status", {}),
    ]


def _sum_equipment_starforce(state: AgentState) -> int:
    equipment_summary = state.get("equipment_summary") or {}
    total = _parse_number(_value(equipment_summary, "total_starforce"), -1)
    if total >= 0:
        return int(total)

    equipment_items = state.get("equipment_items") or _value(state.get("character_profile", {}), "equipment_list", []) or []
    return sum(int(_parse_number(_value(item, "starforce"), 0)) for item in equipment_items)


def _character_input(state: AgentState) -> dict[str, Any]:
    profile = _plain(state.get("character_profile", {}))
    stat_sources = _state_stat_sources(state)
    union_sources = _state_union_sources(state)
    attack_power = int(_first_number(stat_sources, ("attack_power", "attack"), 0))
    magic_power = int(_first_number(stat_sources, ("magic_power", "magic"), 0))
    main_stat = _first_number(stat_sources, ("main_stat", "primary_stat"), 0)
    if main_stat <= 0:
        main_stat = max(
            _first_number(stat_sources, ("str_val", "str", "STR"), 0),
            _first_number(stat_sources, ("dex", "dex_val", "DEX"), 0),
            _first_number(stat_sources, ("int_val", "int", "INT"), 0),
            _first_number(stat_sources, ("luk", "luk_val", "LUK"), 0),
        )

    return {
        "character_name": _first_text([state, profile], ("character_name",), ""),
        "job_name": _first_text([profile, state], ("job_name", "class_name"), ""),
        "world_name": _first_text([state, profile], ("world_name",), ""),
        "level": int(_first_number([profile, *stat_sources], ("level", "character_level"), 0)),
        "combat_power": int(_first_number(stat_sources, ("combat_power",), 0)),
        "main_stat": int(main_stat),
        "attack_power": attack_power,
        "magic_power": magic_power,
        "attack_or_magic": max(attack_power, magic_power),
        "boss_damage": _first_number(stat_sources, ("boss_damage", "boss_damage_percent"), 0),
        "ignore_def": _first_number(stat_sources, ("ignore_def", "ignore_def_percent"), 0),
        "crit_rate": _first_number(stat_sources, ("crit_rate",), 0),
        "crit_damage": _first_number(stat_sources, ("crit_damage",), 0),
        "final_damage": _first_number(stat_sources, ("final_damage", "final_damage_percent"), 0),
        "damage": _first_number(stat_sources, ("damage", "damage_percent"), 0),
        "arcane_force": int(_first_number(stat_sources, ("arcane_force",), 0)),
        "authentic_force": int(_first_number(stat_sources, ("authentic_force",), 0)),
        "starforce": _sum_equipment_starforce(state),
        "union_level": int(_first_number(union_sources, ("union_level",), 0)),
    }


def _parse_context_fields(content: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for line in str(content or "").splitlines():
        if ": " not in line:
            continue
        key, value = line.split(": ", 1)
        key = key.strip()
        value = value.strip()
        if value:
            fields[key] = value
    return fields


def _parse_props(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    text = str(value or "").strip()
    if not text:
        return {}
    try:
        parsed = ast.literal_eval(text)
    except (ValueError, SyntaxError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _requirement_from_document(document: RetrievedDocument) -> dict[str, Any] | None:
    metadata = document.get("metadata", {}) or {}
    method = str(metadata.get("retrieval_method") or "")
    content = str(document.get("page_content") or "")
    if "graph_requirement" not in method and "Graph boss requirement fact" not in content:
        return None

    fields = _parse_context_fields(content)
    requirement_props = _parse_props(fields.get("requirement_properties"))
    boss_props = _parse_props(fields.get("boss_properties"))
    boss_name = fields.get("Boss") or boss_props.get("name") or metadata.get("title") or "unknown"
    if isinstance(boss_name, str) and " - " in boss_name:
        boss_name = boss_name.split(" - ", 1)[0]

    requirement = {
        "boss_name": str(boss_name),
        "difficulty": fields.get("difficulty") or boss_props.get("difficulty") or requirement_props.get("difficulty"),
        "source": document.get("source") or metadata.get("source_url") or metadata.get("title") or "",
        "score": document.get("score", 0.0),
        "raw_fields": fields,
    }
    aliases = {
        "required_level": ("level", "required_level"),
        "required_combat_power": ("combat_power", "required_combat_power"),
        "required_main_stat": ("main_stat", "required_main_stat"),
        "required_attack_power": ("attack_power", "required_attack_power"),
        "required_magic_power": ("magic_power", "required_magic_power"),
        "required_boss_damage": ("boss_damage", "required_boss_damage"),
        "required_ignore_def": ("ignore_def", "required_ignore_def"),
        "required_crit_rate": ("crit_rate", "required_crit_rate"),
        "required_crit_damage": ("crit_damage", "required_crit_damage"),
        "required_final_damage": ("final_damage", "required_final_damage"),
        "required_arcane_force": ("arcane_force", "required_arcane_force"),
        "required_authentic_force": ("authentic_force", "required_authentic_force"),
        "required_starforce": ("starforce", "required_starforce"),
        "required_union_level": ("union_level", "required_union_level"),
        "boss_level": ("boss_level", "monster_level", "target_level"),
        "boss_defense_rate": ("boss_defense_rate", "defense_rate", "pdr", "boss_pdr"),
    }
    for output_key, input_keys in aliases.items():
        value = 0.0
        for input_key in input_keys:
            value = _parse_number(requirement_props.get(input_key), 0)
            if value:
                break
            value = _parse_number(fields.get(input_key), 0)
            if value:
                break
        requirement[output_key] = value

    return requirement


def _research_requirements(state: AgentState) -> list[dict[str, Any]]:
    wants_all_boss_tier_table = _wants_all_boss_tier_table(state)
    docs = list(state.get("retrieved_docs") or []) if wants_all_boss_tier_table else list(
        state.get("selected_evidence") or state.get("retrieved_docs") or []
    )
    requirements = []
    seen = set()
    for doc in docs:
        requirement = _requirement_from_document(doc)
        if not requirement:
            continue
        key = (
            _normalize_text(requirement.get("boss_name")),
            str(requirement.get("difficulty") or "").upper(),
        )
        if key not in seen:
            seen.add(key)
            requirements.append(requirement)
    return requirements


def _normalize_text(value: Any) -> str:
    return re.sub(r"\s+", "", str(value or "")).lower()


def _has_hangul(value: Any) -> bool:
    return bool(re.search(r"[가-힣]", str(value or "")))


KOREAN_BOSS_NAME_MAP = {
    "zakum": "자쿰",
    "hilla": "힐라",
    "pinkbean": "핑크빈",
    "cygnus": "시그너스",
    "papulatus": "파풀라투스",
    "vonleon": "반 레온",
    "magnus": "매그너스",
    "vonbon": "반반",
    "pierre": "피에르",
    "crimsonqueen": "블러디 퀸",
    "vellum": "벨룸",
    "akechimitsuhide": "아케치 미츠히데",
    "lotus": "스우",
    "damien": "데미안",
    "lucid": "루시드",
    "will": "윌",
    "gloom": "더스크",
    "guardcaptaindarknell": "듄켈",
    "verushilla": "진 힐라",
    "blackmage": "검은 마법사",
    "seren": "세렌",
    "kalos": "칼로스",
    "kaling": "카링",
    "limbo": "림보",
}


def _korean_boss_name(value: Any) -> str:
    name = str(value or "unknown").strip()
    if not name or name == "unknown" or _has_hangul(name):
        return name
    return KOREAN_BOSS_NAME_MAP.get(_normalize_text(name), name)


def _korean_difficulty(value: Any) -> str:
    difficulty = str(value or "").strip()
    if not difficulty:
        return ""
    return DIFFICULTY_LABELS_KO.get(difficulty.upper(), difficulty)


def _display_boss_name(boss_name: Any, difficulty: Any = "") -> str:
    name = _korean_boss_name(boss_name)
    difficulty_label = _korean_difficulty(difficulty)
    if not difficulty_label:
        return name
    compact = _normalize_text(name)
    if difficulty_label and _normalize_text(difficulty_label) in compact:
        return name
    return f"{difficulty_label} {name}"


def _boss_realism_profile(requirement: dict[str, Any]) -> dict[str, Any]:
    return {
        "progression_rank": int(
            _requirement_number(
                requirement,
                ("progression_rank", "difficulty_rank", "boss_rank", "clear_order", "order"),
                999,
            )
        ),
        "pattern_penalty": _requirement_number(
            requirement,
            ("pattern_penalty", "mechanic_penalty", "difficulty_penalty"),
            0.0,
        ),
        "note": _requirement_text(
            requirement,
            ("profile_note", "pattern_note", "difficulty_note", "note"),
            "research 요구치 기준",
        ),
    }


def _requirement_number(requirement: dict[str, Any], keys: tuple[str, ...], default: float) -> float:
    raw_fields = requirement.get("raw_fields") if isinstance(requirement.get("raw_fields"), dict) else {}
    for source in (requirement, raw_fields):
        for key in keys:
            value = source.get(key) if isinstance(source, dict) else None
            if value not in (None, ""):
                return _parse_number(value, default)
    return default


def _requirement_text(requirement: dict[str, Any], keys: tuple[str, ...], default: str) -> str:
    raw_fields = requirement.get("raw_fields") if isinstance(requirement.get("raw_fields"), dict) else {}
    for source in (requirement, raw_fields):
        for key in keys:
            value = source.get(key) if isinstance(source, dict) else None
            if value not in (None, ""):
                return str(value)
    return default


def _calibrated_score(raw_score: float, profile: dict[str, Any], ratios: dict[str, float]) -> float:
    score = raw_score - float(profile.get("pattern_penalty") or 0.0)
    rank = int(profile.get("progression_rank") or 999)
    if rank != 999 and rank >= 100 and ratios.get("main_stat", 1.0) < 0.35:
        score -= 0.05
    if rank != 999 and rank >= 180 and ratios.get("force", 1.0) < 0.75:
        score -= 0.08
    return round(max(0.0, min(score, 1.15)), 4)


def _calibrated_status(
    raw_status: str,
    calibrated_score: float,
    lacking_stats: list[dict[str, Any]],
    profile: dict[str, Any],
    severe_components: list[dict[str, Any]] | None = None,
) -> str:
    status = _status(calibrated_score, lacking_stats, severe_components)
    if raw_status == "unknown":
        return "unknown"
    rank = int(profile.get("progression_rank") or 999)
    if rank != 999 and rank >= 140 and status == "recommended":
        return "challengeable"
    if rank != 999 and rank >= 240 and status in {"recommended", "challengeable"} and lacking_stats:
        return "risky"
    return status


def _boss_progression_rank(analysis: dict[str, Any]) -> int:
    profile = analysis.get("realism_profile") or {}
    return int(profile.get("progression_rank") or 999)


def _tier_sort_key(analysis: dict[str, Any]) -> tuple[int, float, str]:
    return (
        _boss_progression_rank(analysis),
        -float(analysis.get("challenge_fit_score") or 0),
        _boss_display_name(analysis),
    )


def _wants_all_boss_tier_table(state: AgentState) -> bool:
    query = str(state.get("contextualized_query") or state.get("user_query") or "")
    normalized = query.lower().replace(" ", "")
    if not normalized:
        return False
    has_scope = any(keyword.lower().replace(" ", "") in normalized for keyword in ALL_BOSS_TIER_QUERY_KEYWORDS)
    if "보스" in normalized and "티어" in normalized:
        has_scope = True
    has_intent = any(
        keyword in normalized
        for keyword in (
            "도전가능",
            "가능성",
            "가능여부",
            "갈수",
            "깰수",
            "클리어",
            "티어",
            "표",
            "스펙비교",
        )
    )
    return has_scope and has_intent


def _query_difficulty(query: str) -> str:
    normalized = query.lower()
    for label, difficulty in DIFFICULTY_HINTS.items():
        if label in normalized:
            return difficulty
    return ""


def _difficulty_match_score(query_difficulty: str, requirement: dict[str, Any]) -> float:
    if not query_difficulty:
        return 0.0
    difficulty = str(requirement.get("difficulty") or "").upper()
    return 0.8 if query_difficulty and query_difficulty in difficulty else 0.0


def _target_hint_score(query: str, requirement: dict[str, Any]) -> float:
    normalized_query = _normalize_text(query)
    boss_name = _normalize_text(requirement.get("boss_name"))
    score = 0.0
    if boss_name and boss_name in normalized_query:
        score += 2.0
    for hint in TARGET_BOSS_HINTS:
        normalized_hint = _normalize_text(hint)
        if normalized_hint and normalized_hint in normalized_query and normalized_hint in boss_name:
            score += 1.5
    score += _difficulty_match_score(_query_difficulty(query), requirement)
    try:
        score += float(requirement.get("score") or 0) * 0.01
    except (TypeError, ValueError):
        pass
    return score


def _select_target_requirement(state: AgentState, requirements: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not requirements:
        return None
    query = str(state.get("contextualized_query") or state.get("user_query") or "")
    return max(requirements, key=lambda item: _target_hint_score(query, item))


def _ratio(actual: float, required: float) -> float | None:
    if required <= 0:
        return None
    return max(0.0, min(actual / required, 1.25))


def _bounded_ratio(actual: float, required: float, *, cap: float = 1.35) -> float | None:
    if required <= 0:
        return None
    return max(0.0, min(actual / required, cap))


def _percent_factor(value: Any) -> float:
    return 1.0 + max(0.0, _parse_number(value, 0)) / 100.0


def _crit_expected_factor(rate: Any, damage: Any) -> float:
    crit_rate = max(0.0, min(_parse_number(rate, 0), 100.0)) / 100.0
    crit_damage = max(0.0, _parse_number(damage, 0)) / 100.0
    return 1.0 + crit_rate * crit_damage


def _boss_defense_from_requirement(requirement: dict[str, Any]) -> float:
    direct = _parse_number(requirement.get("boss_defense_rate"), 0)
    if direct:
        return direct
    required_ied = _parse_number(requirement.get("required_ignore_def"), 0)
    if required_ied >= 90:
        return 300.0
    if required_ied >= 80:
        return 200.0
    if required_ied >= 60:
        return 100.0
    if required_ied > 0:
        return 50.0
    return 0.0


def _defense_damage_factor(ignore_def: Any, boss_defense_rate: float) -> float:
    if boss_defense_rate <= 0:
        return 1.0
    ied = max(0.0, min(_parse_number(ignore_def, 0), 100.0)) / 100.0
    defense = max(0.0, boss_defense_rate) / 100.0
    return max(0.05, 1.0 - defense * (1.0 - ied))


def _level_damage_factor(character_level: Any, requirement: dict[str, Any]) -> float | None:
    target_level = _parse_number(requirement.get("boss_level"), 0) or _parse_number(requirement.get("required_level"), 0)
    if target_level <= 0:
        return None
    diff = _parse_number(character_level, 0) - target_level
    if diff >= 0:
        return min(1.20, 1.10 + min(diff, 5.0) * 0.02)
    near_penalty = {-1: 1.0584, -2: 1.007, -3: 0.9672, -4: 0.918}
    if int(diff) in near_penalty:
        return near_penalty[int(diff)]
    return max(0.0, 1.0 - int(abs(diff) * 2.5) / 100.0)


def _arcane_force_damage_factor(current: float, required: float) -> float | None:
    if required <= 0:
        return None
    met_percent = int((current / required) * 100)
    if met_percent < 10:
        return 0.10
    if met_percent < 30:
        return 0.30
    if met_percent < 50:
        return 0.60
    if met_percent < 70:
        return 0.70
    if met_percent < 100:
        return 0.80
    if met_percent < 110:
        return 1.00
    if met_percent < 130:
        return 1.10
    if met_percent < 150:
        return 1.30
    return 1.50


def _authentic_force_damage_factor(current: float, required: float) -> float | None:
    if required <= 0:
        return None
    diff = current - required
    if diff < 0:
        return max(0.05, 1.0 + diff / 100.0)
    return min(1.25, 1.0 + int(diff // 2) / 100.0)


def _geometric_mean(values: list[float]) -> float:
    usable = [max(0.01, value) for value in values if value > 0]
    if not usable:
        return 0.0
    product = 1.0
    for value in usable:
        product *= value
    return product ** (1.0 / len(usable))


def _bossing_fit_model(
    character: dict[str, Any],
    requirement: dict[str, Any],
    ratios: dict[str, float],
) -> dict[str, Any]:
    components: dict[str, float] = {}
    weights: dict[str, float] = {}

    combat_power_ratio = _bounded_ratio(
        _parse_number(character.get("combat_power"), 0),
        _parse_number(requirement.get("required_combat_power"), 0),
        cap=1.45,
    )
    if combat_power_ratio is not None:
        components["combat_power"] = combat_power_ratio
        weights["combat_power"] = 0.36

    stat_components = []
    main_stat_ratio = _bounded_ratio(
        _parse_number(character.get("main_stat"), 0),
        _parse_number(requirement.get("required_main_stat"), 0),
        cap=1.45,
    )
    if main_stat_ratio is not None:
        stat_components.append(main_stat_ratio)
    attack_ratio = _bounded_ratio(
        _parse_number(character.get("attack_or_magic"), 0),
        max(_parse_number(requirement.get("required_attack_power"), 0), _parse_number(requirement.get("required_magic_power"), 0)),
        cap=1.45,
    )
    if attack_ratio is not None:
        stat_components.append(attack_ratio)
    if stat_components:
        components["stat_attack"] = _geometric_mean(stat_components)
        weights["stat_attack"] = 0.18 if combat_power_ratio is None else 0.12

    required_boss_damage = _parse_number(requirement.get("required_boss_damage"), 0)
    if required_boss_damage > 0:
        actual_damage_factor = 1.0 + (
            max(0.0, _parse_number(character.get("damage"), 0))
            + max(0.0, _parse_number(character.get("boss_damage"), 0))
        ) / 100.0
        required_damage_factor = 1.0 + required_boss_damage / 100.0
        components["boss_damage"] = max(0.0, min(actual_damage_factor / required_damage_factor, 1.45))
        weights["boss_damage"] = 0.11

    required_final_damage = _parse_number(requirement.get("required_final_damage"), 0)
    if required_final_damage > 0:
        components["final_damage"] = max(
            0.0,
            min(_percent_factor(character.get("final_damage")) / _percent_factor(required_final_damage), 1.45),
        )
        weights["final_damage"] = 0.08

    boss_defense_rate = _boss_defense_from_requirement(requirement)
    required_ignore_def = _parse_number(requirement.get("required_ignore_def"), 0)
    if boss_defense_rate > 0 and required_ignore_def > 0:
        actual_def_factor = _defense_damage_factor(character.get("ignore_def"), boss_defense_rate)
        required_def_factor = _defense_damage_factor(required_ignore_def, boss_defense_rate)
        components["ignore_def"] = max(0.0, min(actual_def_factor / required_def_factor, 1.35))
        weights["ignore_def"] = 0.15

    if _parse_number(requirement.get("required_crit_rate"), 0) > 0 or _parse_number(requirement.get("required_crit_damage"), 0) > 0:
        required_crit_factor = _crit_expected_factor(
            requirement.get("required_crit_rate"),
            requirement.get("required_crit_damage"),
        )
        components["crit"] = max(
            0.0,
            min(_crit_expected_factor(character.get("crit_rate"), character.get("crit_damage")) / required_crit_factor, 1.25),
        )
        weights["crit"] = 0.04

    level_factor = _level_damage_factor(character.get("level"), requirement)
    if level_factor is not None:
        components["level"] = level_factor
        weights["level"] = 0.08

    arcane_factor = _arcane_force_damage_factor(
        _parse_number(character.get("arcane_force"), 0),
        _parse_number(requirement.get("required_arcane_force"), 0),
    )
    authentic_factor = _authentic_force_damage_factor(
        _parse_number(character.get("authentic_force"), 0),
        _parse_number(requirement.get("required_authentic_force"), 0),
    )
    force_factors = [factor for factor in (arcane_factor, authentic_factor) if factor is not None]
    if force_factors:
        components["force"] = min(force_factors)
        weights["force"] = 0.14

    starforce_ratio = _bounded_ratio(
        _parse_number(character.get("starforce"), 0),
        _parse_number(requirement.get("required_starforce"), 0),
        cap=1.25,
    )
    if starforce_ratio is not None:
        components["starforce"] = starforce_ratio
        weights["starforce"] = 0.03

    union_ratio = _bounded_ratio(
        _parse_number(character.get("union_level"), 0),
        _parse_number(requirement.get("required_union_level"), 0),
        cap=1.25,
    )
    if union_ratio is not None:
        components["union_level"] = union_ratio
        weights["union_level"] = 0.02

    active_weight = sum(weights.values())
    score = sum(min(components[key], 1.45) * weight for key, weight in weights.items()) / active_weight if active_weight else 0.0
    severe_components = [
        {"stat": key, "label": STAT_LABELS.get(key, key), "ratio": round(value, 4)}
        for key, value in components.items()
        if key in {"combat_power", "stat_attack", "ignore_def", "force", "level"} and value < 0.75
    ]
    return {
        "score": round(score, 4),
        "components": {key: round(value, 4) for key, value in components.items()},
        "weights": weights,
        "severe_components": severe_components,
        "boss_defense_rate": boss_defense_rate,
        "formula": "effective_boss_damage_fit_with_level_force_ied_multipliers",
    }


def _status(
    score: float,
    lacking_stats: list[dict[str, Any]],
    severe_components: list[dict[str, Any]] | None = None,
) -> str:
    severe_stats = {"combat_power", "main_stat", "ignore_def", "force"}
    severe_lacking = [
        item
        for item in lacking_stats
        if item["ratio"] < 0.75 and item["stat"] in severe_stats
    ]
    severe_lacking.extend(severe_components or [])
    if score >= 1.08 and not severe_lacking:
        return "recommended"
    if score >= 0.95 and not severe_lacking:
        return "challengeable"
    if score >= 0.80:
        return "risky"
    if score >= 0.65:
        return "growth_target"
    return "difficult"


def _stat_actual_required(character: dict[str, Any], requirement: dict[str, Any]) -> dict[str, tuple[float, float]]:
    required_force = _parse_number(requirement.get("required_arcane_force"), 0) + _parse_number(
        requirement.get("required_authentic_force"),
        0,
    )
    current_force = _parse_number(character.get("arcane_force"), 0) + _parse_number(character.get("authentic_force"), 0)
    return {
        "level": (character["level"], requirement.get("required_level", 0)),
        "combat_power": (character["combat_power"], requirement.get("required_combat_power", 0)),
        "main_stat": (character["main_stat"], requirement.get("required_main_stat", 0)),
        "attack_or_magic": (
            character["attack_or_magic"],
            max(requirement.get("required_attack_power", 0), requirement.get("required_magic_power", 0)),
        ),
        "boss_damage": (character["boss_damage"], requirement.get("required_boss_damage", 0)),
        "ignore_def": (character["ignore_def"], requirement.get("required_ignore_def", 0)),
        "crit_rate": (min(character["crit_rate"], 100), requirement.get("required_crit_rate", 0)),
        "crit_damage": (character["crit_damage"], requirement.get("required_crit_damage", 0)),
        "final_damage": (character["final_damage"], requirement.get("required_final_damage", 0)),
        "force": (current_force, required_force),
        "starforce": (character["starforce"], requirement.get("required_starforce", 0)),
        "union_level": (character["union_level"], requirement.get("required_union_level", 0)),
    }


def _analyze_requirement(character: dict[str, Any], requirement: dict[str, Any]) -> dict[str, Any]:
    ratios: dict[str, float] = {}
    lacking_stats = []
    active_weight = 0.0
    weighted_score = 0.0

    for stat, (actual, required) in _stat_actual_required(character, requirement).items():
        ratio = _ratio(_parse_number(actual), _parse_number(required))
        if ratio is None:
            continue
        ratios[stat] = round(ratio, 4)
        weight = STAT_WEIGHTS.get(stat, 0.03)
        active_weight += weight
        weighted_score += min(ratio, 1.15) * weight
        if ratio < 1.0:
            lacking_stats.append(
                {
                    "stat": stat,
                    "label": STAT_LABELS.get(stat, stat),
                    "actual": round(_parse_number(actual), 2),
                    "required": round(_parse_number(required), 2),
                    "ratio": round(ratio, 4),
                }
            )

    legacy_score = round(weighted_score / active_weight, 4) if active_weight else 0.0
    lacking_stats.sort(key=lambda item: (item["ratio"], item["stat"]))
    bossing_fit_model = _bossing_fit_model(character, requirement, ratios)
    model_has_components = bool(bossing_fit_model.get("components"))
    raw_score = float(bossing_fit_model.get("score") or 0.0) if model_has_components else legacy_score
    severe_components = list(bossing_fit_model.get("severe_components") or [])
    raw_status = _status(raw_score, lacking_stats, severe_components) if active_weight or model_has_components else "unknown"
    realism_profile = _boss_realism_profile(requirement)
    score = _calibrated_score(raw_score, realism_profile, ratios) if active_weight or model_has_components else 0.0
    clear_status = _calibrated_status(
        raw_status,
        score,
        lacking_stats,
        realism_profile,
        severe_components,
    ) if active_weight or model_has_components else "unknown"
    boss_name = str(requirement.get("boss_name") or "unknown")
    display_name = _display_boss_name(boss_name, requirement.get("difficulty"))
    near_miss_stats = [
        item
        for item in lacking_stats
        if float(item.get("ratio") or 0) >= 0.75
    ]
    return {
        "target_boss": boss_name,
        "boss_name": boss_name,
        "display_boss_name": display_name,
        "difficulty": requirement.get("difficulty"),
        "difficulty_label": _korean_difficulty(requirement.get("difficulty")),
        "clear_status": clear_status,
        "status_label": STATUS_LABELS.get(clear_status, clear_status),
        "challenge_fit_score": score,
        "raw_challenge_fit_score": raw_score,
        "legacy_weighted_fit_score": legacy_score,
        "challengeable": clear_status in {"recommended", "challengeable"},
        "boss_clear_prediction": {display_name: clear_status in {"recommended", "challengeable"}},
        "stat_ratios": ratios,
        "bossing_fit_model": bossing_fit_model,
        "lacking_stats": lacking_stats,
        "near_miss_stats": near_miss_stats,
        "realism_profile": realism_profile,
        "boss_requirements": requirement,
        "decision_basis": {
            "formula": bossing_fit_model.get("formula") or "state_research_requirement_weighted_fit",
            "data_flow": "research -> evidence_formatter -> calculator -> analystic",
            "uses_direct_graph_lookup": False,
            "uses_direct_api_lookup": False,
            "weights": bossing_fit_model.get("weights") or STAT_WEIGHTS,
            "component_scores": bossing_fit_model.get("components") or {},
            "legacy_weights": STAT_WEIGHTS,
            "calibration": {
                "pattern_penalty": realism_profile.get("pattern_penalty"),
                "progression_rank": realism_profile.get("progression_rank"),
                "profile_note": realism_profile.get("note"),
            },
        },
        "data_reliability": "research_context_and_calculator_state",
    }


def _available_bosses_result(
    character: dict[str, Any],
    requirements: list[dict[str, Any]],
    *,
    include_all: bool = False,
) -> dict[str, Any]:
    analyses = _dedupe_boss_analyses(
        [_analyze_requirement(character, item) for item in requirements]
    )
    groups = {"recommended": [], "challengeable": [], "risky": [], "growth_target": [], "difficult": []}
    for item in analyses:
        status = item.get("clear_status")
        if status in groups:
            groups[status].append(item)
    for status, items in groups.items():
        items.sort(key=_tier_sort_key)
        groups[status] = items if include_all else items[:8]

    available = [*groups["recommended"], *groups["challengeable"], *groups["risky"], *groups["growth_target"]]
    actions = [
        _action_for_status(item)
        for item in [
            *groups["recommended"][:2],
            *groups["challengeable"][:2],
            *groups["risky"][:1],
            *groups["growth_target"][:1],
        ]
    ]
    return {
        "available_bosses": available if include_all else available[:10],
        "boss_groups": groups,
        "all_boss_tier_table": include_all,
        "recommended_actions": actions[:5],
        "challenge_fit_score": max((float(item.get("challenge_fit_score") or 0) for item in available), default=0.0),
        "summary": {
            "recommended_count": len(groups["recommended"]),
            "challengeable_count": len(groups["challengeable"]),
            "risky_count": len(groups["risky"]),
            "growth_target_count": len(groups["growth_target"]),
            "difficult_count": len(groups["difficult"]),
            "total_bosses_checked": len(analyses),
            "calibration_basis": "research 제공 보스 요구치/보정값 + analytics 점수화 로직",
            "evidence_scope": "research_provided_requirements_only",
        },
        "data_reliability": "research_context_and_calculator_state",
    }


def _dedupe_boss_analyses(analyses: list[dict[str, Any]]) -> list[dict[str, Any]]:
    best_by_boss: dict[tuple[str, str], dict[str, Any]] = {}
    for analysis in analyses:
        key = (
            _normalize_text(analysis.get("boss_name") or analysis.get("target_boss")),
            str(analysis.get("difficulty") or "").upper(),
        )
        current = best_by_boss.get(key)
        if current is None or _analysis_rank(analysis) > _analysis_rank(current):
            best_by_boss[key] = analysis
    return sorted(
        best_by_boss.values(),
        key=lambda item: (
            -_status_rank(str(item.get("clear_status") or "")),
            _boss_progression_rank(item),
            -float(item.get("challenge_fit_score") or 0),
            _boss_display_name(item),
        ),
    )


def _analysis_rank(analysis: dict[str, Any]) -> tuple[int, float, int, int]:
    return (
        _status_rank(str(analysis.get("clear_status") or "")),
        float(analysis.get("challenge_fit_score") or 0),
        -len(analysis.get("lacking_stats") or []),
        -_boss_progression_rank(analysis),
    )


def _status_rank(status: str) -> int:
    return {
        "recommended": 5,
        "challengeable": 4,
        "risky": 3,
        "growth_target": 2,
        "difficult": 1,
        "unknown": 0,
    }.get(status, 0)


def _empty_result(message: str) -> dict[str, Any]:
    return {
        "available_bosses": [],
        "boss_groups": {"recommended": [], "challengeable": [], "risky": [], "growth_target": [], "difficult": []},
        "recommended_actions": [],
        "challenge_fit_score": 0.0,
        "summary": {"message": message, "total_bosses_checked": 0},
        "data_reliability": "analysis_failed_or_missing_state",
        "error": message,
    }


def _growth_report(
    state: AgentState,
    character: dict[str, Any],
    result: dict[str, Any],
    actions: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "character_id": str(state.get("ocid") or character.get("character_name") or ""),
        "current_combat_power": int(character.get("combat_power") or 0),
        "attack": int(character.get("attack_or_magic") or 0),
        "boss_damage": float(character.get("boss_damage") or 0),
        "ignore_def": float(character.get("ignore_def") or 0),
        "crit_rate": float(character.get("crit_rate") or 0),
        "crit_damage": float(character.get("crit_damage") or 0),
        "damage": float(character.get("damage") or 0),
        "bottleneck_analysis": state.get("bottleneck_analysis") or _bottleneck_from_result(result),
        "recommended_actions": actions,
        "boss_clear_prediction": result.get("boss_clear_prediction") or _prediction_from_groups(result),
        "data_reliability": result.get("data_reliability", "research_context_and_calculator_state"),
        "timestamp": datetime.now().isoformat(timespec="seconds"),
    }


def _bottleneck_from_result(result: dict[str, Any]) -> dict[str, float]:
    return {
        str(item.get("stat")): round(max(0.0, 1.0 - float(item.get("ratio") or 0)), 4)
        for item in result.get("lacking_stats", []) or []
        if item.get("stat")
    }


def _prediction_from_groups(result: dict[str, Any]) -> dict[str, bool]:
    prediction = {}
    groups = result.get("boss_groups") or {}
    for status in ("recommended", "challengeable"):
        for item in groups.get(status, []) or []:
            boss = item.get("display_boss_name") or _display_boss_name(
                item.get("boss_name") or item.get("target_boss"),
                item.get("difficulty"),
            )
            if boss:
                prediction[str(boss)] = True
    for status in ("risky", "growth_target", "difficult"):
        for item in groups.get(status, []) or []:
            boss = item.get("display_boss_name") or _display_boss_name(
                item.get("boss_name") or item.get("target_boss"),
                item.get("difficulty"),
            )
            if boss and boss not in prediction:
                prediction[str(boss)] = False
    return prediction


def _boss_display_name(item: dict[str, Any]) -> str:
    return str(
        item.get("display_boss_name")
        or _display_boss_name(item.get("boss_name") or item.get("target_boss"), item.get("difficulty"))
        or "unknown"
    )


def _top_lacking_labels(item: dict[str, Any], limit: int = 2) -> str:
    lacking = item.get("lacking_stats") or []
    if not lacking:
        return "주요 부족 없음"
    return ", ".join(str(row.get("label") or row.get("stat")) for row in lacking[:limit])


def _format_component_score(key: str, value: Any) -> str:
    return f"{STAT_LABELS.get(key, key)} {_parse_number(value, 0):.2f}"


def _component_basis_summary(analysis: dict[str, Any], limit: int = 3) -> str:
    model = analysis.get("bossing_fit_model") or {}
    components = model.get("components") or {}
    weights = model.get("weights") or {}
    if not isinstance(components, dict) or not components:
        return "research 요구치 대비 충족률 가중 평균"

    ranked = sorted(
        components.items(),
        key=lambda item: (
            _parse_number(item[1], 0),
            -_parse_number(weights.get(item[0]), 0),
            item[0],
        ),
    )
    return ", ".join(_format_component_score(str(key), value) for key, value in ranked[:limit])


def _bossing_basis_lines(analysis: dict[str, Any], limit: int = 4) -> list[str]:
    model = analysis.get("bossing_fit_model") or {}
    components = model.get("components") or {}
    if not isinstance(components, dict) or not components:
        return [
            "- research가 제공한 요구 스탯과 현재 스탯의 충족률을 가중 평균해 적합도를 계산했습니다.",
            "- research가 보스 방어율, 포스, 레벨 같은 세부 근거를 주지 않으면 해당 요소는 임의로 보충하지 않습니다.",
        ]

    lines = [
        "- 산정 공식은 전투력/주스탯 같은 기본 화력에 보공+데미지, 최종뎀, 크리 기대값, 방무-보스방어율, 레벨 차이, 아케인/어센틱 포스를 유효 보스딜 계수로 환산한 것입니다.",
    ]
    weights = model.get("weights") or {}
    ranked = sorted(
        components.items(),
        key=lambda item: (
            _parse_number(item[1], 0),
            -_parse_number(weights.get(item[0]), 0),
            item[0],
        ),
    )
    component_text = ", ".join(_format_component_score(str(key), value) for key, value in ranked[:limit])
    lines.append(f"- 주요 판정 요소는 {component_text} 순서로 봤습니다. 1.00 미만이면 요구치보다 부족한 쪽입니다.")
    boss_defense_rate = _parse_number(model.get("boss_defense_rate"), 0)
    if boss_defense_rate:
        lines.append(f"- 방무는 단순 요구치 비교가 아니라 보스 방어율 {boss_defense_rate:g}%에서 실제로 들어가는 피해율로 환산했습니다.")
    if "force" in components:
        lines.append("- 포스는 부족하면 실제 최종 피해가 크게 줄어드는 관문 요소라 별도 배율로 반영했습니다.")
    if "level" in components:
        lines.append("- 레벨 차이는 보스와의 레벨 차이에 따른 피해 보정/패널티를 반영했습니다.")
    return lines


def _tier_table_context(result: dict[str, Any]) -> str:
    if not result.get("all_boss_tier_table"):
        return ""

    groups = result.get("boss_groups") or {}
    lines = ["Analytics research-provided boss readiness tier table:"]
    lines.append(
        "Basis: readiness uses research-provided boss requirements only, then estimates effective boss damage with CP/stat, boss+damage, final damage, crit expectation, IED vs defense, level, and force components."
    )
    for status in ("recommended", "challengeable", "risky", "growth_target", "difficult"):
        items = groups.get(status) or []
        label = STATUS_LABELS.get(status, status)
        lines.append(f"## {label} ({len(items)})")
        if not items:
            lines.append("- 없음")
            continue
        for item in items:
            profile = item.get("realism_profile") or {}
            raw_score = item.get("raw_challenge_fit_score")
            raw_text = f", raw={raw_score}" if raw_score not in (None, "") else ""
            lines.append(
                "- "
                f"{_boss_display_name(item)} | "
                f"score={item.get('challenge_fit_score')}{raw_text} | "
                f"진행순서={profile.get('progression_rank', 'n/a')} | "
                f"보정={profile.get('note', 'DB 요구치 기준')} | "
                f"근거={_component_basis_summary(item)} | "
                f"부족={_top_lacking_labels(item)}"
            )
    return "\n".join(lines)


def _analysis_context(result: dict[str, Any]) -> str:
    if result.get("error"):
        return f"Analytics: {result['error']}"
    tier_context = _tier_table_context(result)
    if tier_context:
        return tier_context
    if result.get("boss_name") or result.get("target_boss"):
        lacking = result.get("lacking_stats") or []
        profile = result.get("realism_profile") or {}
        lacking_text = ", ".join(
            f"{item.get('label')}: {item.get('actual')}/{item.get('required')}"
            for item in lacking[:4]
        ) or "큰 부족 스탯 없음"
        return (
            "Analytics boss readiness: "
            f"{result.get('display_boss_name') or _display_boss_name(result.get('boss_name') or result.get('target_boss'), result.get('difficulty'))} "
            f"status={result.get('status_label')} "
            f"score={result.get('challenge_fit_score')} "
            f"raw_score={result.get('raw_challenge_fit_score')} "
            f"progression_rank={profile.get('progression_rank', 'n/a')} "
            f"calibration={profile.get('note', 'DB 요구치 기준')} "
            f"basis={_component_basis_summary(result, limit=5)} "
            f"lacking={lacking_text}"
        )
    summary = result.get("summary") or {}
    return (
        "Analytics available bosses: "
        f"recommended={summary.get('recommended_count', 0)}, "
        f"challengeable={summary.get('challengeable_count', 0)}, "
        f"risky={summary.get('risky_count', 0)}, "
        f"growth_target={summary.get('growth_target_count', 0)}, "
        f"checked={summary.get('total_bosses_checked', 0)}"
    )


def _append_analysis_to_context(context: str, result: dict[str, Any]) -> str:
    addition = _analysis_context(result)
    if not context:
        return addition
    if addition in context:
        return context
    return f"{context.rstrip()}\n\n{addition}"


def _format_answer_number(value: Any, suffix: str = "") -> str:
    number = _parse_number(value, 0)
    if number == int(number):
        text = f"{int(number):,}"
    else:
        text = f"{number:,.2f}".rstrip("0").rstrip(".")
    return f"{text}{suffix}"


def _format_answer_gap(actual: Any, required: Any) -> str:
    gap = max(0.0, _parse_number(required, 0) - _parse_number(actual, 0))
    return _format_answer_number(gap)


def _subject_particle(text: Any) -> str:
    label = str(text or "")
    if not label:
        return "이"
    code = ord(label[-1])
    if 0xAC00 <= code <= 0xD7A3:
        return "이" if (code - 0xAC00) % 28 else "가"
    return "이"


def _topic_particle(text: Any) -> str:
    label = str(text or "")
    if not label:
        return "은"
    code = ord(label[-1])
    if 0xAC00 <= code <= 0xD7A3:
        return "은" if (code - 0xAC00) % 28 else "는"
    return "는"


def _action_for_status(analysis: dict[str, Any]) -> dict[str, Any]:
    boss_name = str(
        analysis.get("display_boss_name")
        or _display_boss_name(analysis.get("boss_name") or analysis.get("target_boss"), analysis.get("difficulty"))
        or "대상 보스"
    )
    status = str(analysis.get("clear_status") or "unknown")
    score = float(analysis.get("challenge_fit_score") or 0)
    topic = _topic_particle(boss_name)
    if status == "recommended":
        description = f"{boss_name}{topic} 현재 분석 기준으로 권장 도전권입니다. 보스 패턴 숙련, 버프, 도핑을 준비하고 도전하세요."
        priority = 1
    elif status == "challengeable":
        description = f"{boss_name}{topic} 도전 가능권입니다. 적합도 {score:.2f} 기준으로 큰 결격은 없지만 버프와 패턴 숙련을 챙기는 편이 안전합니다."
        priority = 1
    elif status == "risky":
        description = f"{boss_name}{topic} 도전 자체는 가능할 수 있지만 위험권입니다. 부족 스탯을 보완한 뒤 재평가하는 것을 권장합니다."
        priority = 1
    elif status == "growth_target":
        description = f"{boss_name}{topic} 당장 안정권은 아니지만 다음 성장 목표로 적합합니다. 부족 스탯을 우선 보완한 뒤 다시 도전권을 확인하세요."
        priority = 1
    else:
        description = f"{boss_name}{topic} 현재 수치만으로는 어렵습니다. 아래 부족 스탯과 성장 우선순위를 먼저 보완하세요."
        priority = 1
    return {
        "category": "BOSS_CHALLENGE",
        "target": boss_name,
        "priority": priority,
        "expected_cp_gain": 0,
        "description": description,
    }


def _stat_action_description(item: dict[str, Any]) -> str:
    stat = str(item.get("stat") or "")
    label = str(item.get("label") or stat or "스탯")
    actual = item.get("actual")
    required = item.get("required")
    base = (
        f"{label}{_subject_particle(label)} 요구치보다 낮습니다. "
        f"현재 {_format_answer_number(actual)}, 기준 {_format_answer_number(required)}, "
        f"부족 {_format_answer_gap(actual, required)}입니다."
    )
    if stat == "level":
        return f"{base} 먼저 레벨을 기준까지 올린 뒤 보스 적합도를 다시 확인하세요."
    if stat == "force":
        return f"{base} 아케인/어센틱 심볼을 장착하고 일일 퀘스트, 이벤트 보상, 심볼 강화를 통해 포스를 확보하세요."
    if stat == "main_stat":
        return f"{base} 장비 스타포스, 잠재능력, 심볼 성장, 세트 효과를 우선 점검하세요."
    if stat == "boss_damage":
        return f"{base} 무기/보조무기/엠블렘 잠재, 링크 스킬, 유니온, 보스 도핑으로 보스 데미지를 보강하세요."
    if stat == "ignore_def":
        return f"{base} 방어율 무시는 무기/보조무기/엠블렘 잠재와 링크/유니온에서 우선 확보하세요."
    if stat == "combat_power":
        return f"{base} 장비 강화와 잠재 개선으로 기본 전투력을 먼저 끌어올리는 것이 좋습니다."
    return f"{base} 이 항목을 올릴 수 있는 장비 강화, 잠재, 유니온, 링크 구성을 우선 확인하세요."


def _actions_for_lacking_stats(analysis: dict[str, Any]) -> list[dict[str, Any]]:
    actions = []
    for index, item in enumerate((analysis.get("lacking_stats") or [])[:4], start=1):
        label = item.get("label") or item.get("stat")
        actions.append(
            {
                "category": "STAT_IMPROVEMENT",
                "target": str(label),
                "priority": index + 1,
                "expected_cp_gain": 0,
                "description": _stat_action_description(item),
            }
        )
    return actions


def _growth_forecast_actions(state: AgentState, start_priority: int = 6) -> list[dict[str, Any]]:
    forecasts = _value(state.get("equipment_summary") or {}, "growth_forecast", []) or []
    if not isinstance(forecasts, list):
        return []

    actions = []
    for index, forecast in enumerate(forecasts[:3], start=0):
        target = str(_value(forecast, "target", "") or "성장 항목")
        action = str(_value(forecast, "action", "") or "성장 진행")
        category = str(_value(forecast, "category", "") or "GROWTH")
        cp_gain = int(_parse_number(_value(forecast, "expected_cp_gain"), 0))
        damage_gain = _parse_number(_value(forecast, "expected_damage_gain_percent"), 0)
        cost = int(_parse_number(_value(forecast, "estimated_cost_meso"), 0))
        days = int(_parse_number(_value(forecast, "estimated_days"), 0))
        details = [f"{target}: {action}"]
        if cp_gain:
            details.append(f"예상 전투력 +{cp_gain:,}")
        if damage_gain:
            details.append(f"예상 데미지 +{_format_answer_number(damage_gain, '%')}")
        if cost:
            details.append(f"예상 비용 {_format_answer_number(cost)} 메소")
        if days:
            details.append(f"예상 기간 {days}일")
        actions.append(
            {
                "category": category,
                "target": target,
                "priority": start_priority + index,
                "expected_cp_gain": cp_gain,
                "description": ". ".join(details) + ".",
            }
        )
    return actions


def _recommended_actions(analysis: dict[str, Any], state: AgentState | None = None) -> list[dict[str, Any]]:
    actions = [_action_for_status(analysis), *_actions_for_lacking_stats(analysis)]
    if state is not None:
        actions.extend(_growth_forecast_actions(state, start_priority=len(actions) + 1))
    return actions[:8]


def _answer_guidance(
    character: dict[str, Any],
    result: dict[str, Any],
    actions: list[dict[str, Any]],
    state: AgentState | None = None,
) -> str:
    lines = [
        "Analytics final answer guide:",
        "답변 기준: research가 state에 전달한 보스 요구치와 calculator 결과만 입력 데이터로 사용했습니다.",
        "analytics는 직접 DB/API/로컬 파일을 조회하지 않습니다. research가 전달하지 않은 보스는 티어표에 임의로 보충하지 않습니다.",
        "가능성 산정: 전투력/주스탯 단순 평균이 아니라 보공+데미지, 최종뎀, 크리 기대값, 방무-보스방어율, 레벨 보정, 아케인/어센틱 포스를 곱셈형 유효 보스딜에 가깝게 환산한 적합도를 사용합니다.",
        (
            "캐릭터: "
            f"{character.get('character_name') or 'unknown'}"
            f"({character.get('world_name') or '월드 미상'}, {character.get('job_name') or '직업 미상'})"
        ),
    ]
    final_detail_block = _final_answer_detail_block(character, result, actions, state)
    if final_detail_block:
        lines.append(final_detail_block)
        lines.append("주의: analytics는 이미 state에 있는 research/calculator 결과만 입력 데이터로 사용하며, 직접 DB/API/로컬 파일을 조회하지 않습니다.")
        return "\n".join(lines)

    if result.get("error"):
        lines.append(f"판정: {result['error']} 보스 가능 여부는 단정하지 말고, 계산된 성장 우선순위만 안내하세요.")
    elif result.get("boss_name") or result.get("target_boss"):
        boss_name = result.get("display_boss_name") or _display_boss_name(
            result.get("boss_name") or result.get("target_boss"),
            result.get("difficulty"),
        )
        profile = result.get("realism_profile") or {}
        lines.append(
            f"판정: {boss_name} - {result.get('status_label')} "
            f"(보정 적합도 {result.get('challenge_fit_score')}, "
            f"기초 적합도 {result.get('raw_challenge_fit_score')}, "
            f"진행순서 {profile.get('progression_rank', 'n/a')}, "
            f"도전 가능={result.get('challengeable')})"
        )
        lines.append("산정 근거:")
        lines.extend(_bossing_basis_lines(result))
        lacking_stats = result.get("lacking_stats") or []
        if lacking_stats:
            lines.append("부족 스탯:")
            for item in lacking_stats[:5]:
                lines.append(
                    "- "
                    f"{item.get('label') or item.get('stat')}: "
                    f"현재 {_format_answer_number(item.get('actual'))}, "
                    f"기준 {_format_answer_number(item.get('required'))}, "
                    f"충족률 {_format_answer_number(float(item.get('ratio') or 0) * 100, '%')}"
                )
        else:
            lines.append("부족 스탯: 주요 요구치를 충족했습니다.")
    else:
        summary = result.get("summary") or {}
        if result.get("all_boss_tier_table"):
            lines.append(
                "판정: research가 전달한 보스 요구 스탯 기준으로 보스 도전 가능성 티어표를 만들었습니다. "
                f"권장 {summary.get('recommended_count', 0)}개, "
                f"도전 가능 {summary.get('challengeable_count', 0)}개, "
                f"위험 {summary.get('risky_count', 0)}개, "
                f"보완 후 도전 {summary.get('growth_target_count', 0)}개, "
                f"어려움 {summary.get('difficult_count', 0)}개입니다."
            )
            lines.append(
                "최종 답변은 권장/도전 가능/위험/보완 후 도전/어려움 티어로 나누되, research가 준 근거 범위 밖의 보스는 전체 목록처럼 단정하지 마세요."
            )
        else:
            lines.append(
                "판정: 추천 가능 보스 목록 "
                f"권장 {summary.get('recommended_count', 0)}개, "
                f"도전 가능 {summary.get('challengeable_count', 0)}개, "
                f"위험 {summary.get('risky_count', 0)}개, "
                f"보완 후 도전 {summary.get('growth_target_count', 0)}개"
            )

    if actions:
        lines.append("다음 추천 행동:")
        for action in sorted(actions, key=lambda item: int(item.get("priority") or 999))[:8]:
            cp_gain = int(_parse_number(action.get("expected_cp_gain"), 0))
            description = str(action.get("description") or "")
            cp_text = f" 예상 전투력 +{cp_gain:,}." if cp_gain and "예상 전투력" not in description else ""
            lines.append(
                "- "
                f"[{action.get('priority')}] {action.get('category')} / {action.get('target')}: "
                f"{description}{cp_text}"
            )

    calculator_context = _calculator_detail_context(state, result) if state is not None else ""
    if calculator_context:
        lines.append("calculator 세부 근거:")
        lines.append(calculator_context)

    lines.append("주의: analytics는 이미 state에 있는 research/calculator 결과만 입력 데이터로 사용하며, 직접 DB/API/로컬 파일을 조회하지 않습니다.")
    return "\n".join(lines)


def _append_answer_guidance_to_context(context: str, guidance: str) -> str:
    guidance = str(guidance or "").strip()
    if not guidance:
        return context
    if not context:
        return guidance
    if guidance in context:
        return context
    return f"{guidance}\n\n{context.rstrip()}"


def _calculator_interpretation(state: AgentState) -> dict[str, Any]:
    tool_results = state.get("tool_results") or {}
    if not isinstance(tool_results, dict):
        return {}
    calculator = tool_results.get("calculator") or {}
    if not isinstance(calculator, dict):
        return {}
    interpretation = calculator.get("llm_interpretation") or {}
    return interpretation if isinstance(interpretation, dict) else {}


def _format_calculator_growth_action(action: dict[str, Any]) -> str:
    target = str(action.get("target") or "성장 항목")
    step = str(action.get("action") or "성장 진행")
    details = []
    cp_gain = int(_parse_number(action.get("expected_cp_gain"), 0))
    damage_gain = _parse_number(action.get("expected_damage_gain_percent"), 0)
    cost_text = str(action.get("estimated_cost_text") or "")
    days = int(_parse_number(action.get("estimated_days"), 0))
    efficiency = _parse_number(action.get("efficiency_score"), 0)
    if cp_gain:
        details.append(f"전투력 +{cp_gain:,}")
    if damage_gain:
        details.append(f"데미지 +{_format_answer_number(damage_gain, '%')}")
    if cost_text:
        details.append(f"비용 {cost_text}")
    if days:
        details.append(f"기간 {days}일")
    if efficiency:
        details.append(f"효율 {_format_answer_number(efficiency)}")
    reason = str(action.get("reason") or "")
    if reason and not details:
        details.append(reason)
    suffix = f" ({', '.join(details)})" if details else ""
    return f"{target}: {step}{suffix}"


def _calculator_detail_context(state: AgentState | None, result: dict[str, Any] | None = None) -> str:
    if state is None:
        return ""
    interpretation = _calculator_interpretation(state)
    if not interpretation:
        return ""

    lines = ["Calculator detail for final_answer:"]
    handoff_context = str(interpretation.get("analytics_handoff_context") or "").strip()
    if handoff_context:
        lines.append(handoff_context)

    formula_lines = interpretation.get("damage_formula_summary") or []
    if isinstance(formula_lines, list) and formula_lines:
        lines.append("계산식 구성:")
        for line in formula_lines[:5]:
            lines.append(f"- {line}")

    bottlenecks = interpretation.get("top_bottlenecks") or []
    if isinstance(bottlenecks, list) and bottlenecks:
        requirement = (result or {}).get("boss_requirements") or {}
        direct_requirement_keys = set()
        requirement_key_map = {
            "combat_power": "required_combat_power",
            "main_stat": "required_main_stat",
            "primary_attack": ("required_attack_power", "required_magic_power"),
            "boss_damage": "required_boss_damage",
            "ignore_def": "required_ignore_def",
            "arcane_force": "required_arcane_force",
            "authentic_force": "required_authentic_force",
            "starforce": "required_starforce",
            "union_level": "required_union_level",
        }
        for key, requirement_key in requirement_key_map.items():
            if isinstance(requirement_key, tuple):
                required = max(_parse_number(requirement.get(item), 0) for item in requirement_key)
            else:
                required = _parse_number(requirement.get(requirement_key), 0)
            if required > 0:
                direct_requirement_keys.add(key)

        lines.append("병목 해석:")
        for item in bottlenecks[:5]:
            if not isinstance(item, dict):
                continue
            key = str(item.get("key") or "")
            label = item.get("label") or item.get("key") or "병목"
            score = _parse_number(item.get("urgency_score"), 0)
            reason = str(item.get("reason") or "")
            scope = "보스 요구치 직접 관련" if key in direct_requirement_keys else "일반 성장 기준"
            detail = f"{label} {_format_answer_number(score)} ({scope})"
            if reason:
                detail += f" - {reason}"
            lines.append(f"- {detail}")

    growth_actions = interpretation.get("top_growth_actions") or []
    if isinstance(growth_actions, list) and growth_actions:
        lines.append("계산된 성장 후보:")
        for action in growth_actions[:5]:
            if isinstance(action, dict):
                lines.append(f"- {_format_calculator_growth_action(action)}")

    caveats = interpretation.get("caveats") or []
    if isinstance(caveats, list) and caveats:
        lines.append("계산 한계:")
        for caveat in caveats[:2]:
            lines.append(f"- {caveat}")

    return "\n".join(lines)


def _query_difficulty_label(state: AgentState | None) -> str:
    if state is None:
        return ""
    query = str(state.get("contextualized_query") or state.get("user_query") or "")
    return _korean_difficulty(_query_difficulty(query))


def _comparison_row(label: str, actual: Any, required: Any, suffix: str = "") -> str:
    actual_number = _parse_number(actual, 0)
    required_number = _parse_number(required, 0)
    ratio_text = "기준 없음"
    gap_text = "-"
    if required_number > 0:
        ratio_text = _format_answer_number((actual_number / required_number) * 100, "%")
        gap_text = _format_answer_gap(actual_number, required_number)
    return (
        f"| {label} | {_format_answer_number(actual_number, suffix)} | "
        f"{_format_answer_number(required_number, suffix)} | {gap_text}{suffix} | {ratio_text} |"
    )


def _requirement_comparison_table(character: dict[str, Any], result: dict[str, Any]) -> list[str]:
    requirement = result.get("boss_requirements") or {}
    rows = []
    specs = [
        ("레벨", character.get("level"), requirement.get("required_level"), ""),
        ("전투력", character.get("combat_power"), requirement.get("required_combat_power"), ""),
        ("주스탯", character.get("main_stat"), requirement.get("required_main_stat"), ""),
        (
            "공격력/마력",
            character.get("attack_or_magic"),
            max(
                _parse_number(requirement.get("required_attack_power"), 0),
                _parse_number(requirement.get("required_magic_power"), 0),
            ),
            "",
        ),
        ("보스 데미지", character.get("boss_damage"), requirement.get("required_boss_damage"), "%"),
        ("방어율 무시", character.get("ignore_def"), requirement.get("required_ignore_def"), "%"),
        ("크리티컬 확률", character.get("crit_rate"), requirement.get("required_crit_rate"), "%"),
        ("크리티컬 데미지", character.get("crit_damage"), requirement.get("required_crit_damage"), "%"),
        ("최종 데미지", character.get("final_damage"), requirement.get("required_final_damage"), "%"),
        ("아케인포스", character.get("arcane_force"), requirement.get("required_arcane_force"), ""),
        ("어센틱포스", character.get("authentic_force"), requirement.get("required_authentic_force"), ""),
        ("스타포스", character.get("starforce"), requirement.get("required_starforce"), ""),
        ("유니온", character.get("union_level"), requirement.get("required_union_level"), ""),
    ]
    for label, actual, required, suffix in specs:
        if _parse_number(required, 0) <= 0:
            continue
        rows.append(_comparison_row(label, actual, required, suffix))
    return rows


def _component_table(result: dict[str, Any]) -> list[str]:
    model = result.get("bossing_fit_model") or {}
    components = model.get("components") or {}
    weights = model.get("weights") or {}
    if not isinstance(components, dict) or not components:
        return []
    rows = []
    for key, value in sorted(
        components.items(),
        key=lambda item: (
            _parse_number(item[1], 0),
            -_parse_number(weights.get(item[0]), 0),
            item[0],
        ),
    ):
        rows.append(
            "| "
            f"{STAT_LABELS.get(str(key), str(key))} | "
            f"{_format_answer_number(value)} | "
            f"{_format_answer_number(weights.get(key, 0))} |"
        )
    return rows


def _action_table(actions: list[dict[str, Any]]) -> list[str]:
    rows = []
    for action in sorted(actions, key=lambda item: int(_parse_number(item.get("priority"), 999)))[:8]:
        cp_gain = int(_parse_number(action.get("expected_cp_gain"), 0))
        cp_text = f"+{cp_gain:,}" if cp_gain else "-"
        rows.append(
            "| "
            f"{int(_parse_number(action.get('priority'), 999))} | "
            f"{action.get('category') or ''} | "
            f"{action.get('target') or ''} | "
            f"{cp_text} | "
            f"{str(action.get('description') or '').replace('|', '/')}"
            " |"
        )
    return rows


def _final_answer_detail_block(
    character: dict[str, Any],
    result: dict[str, Any],
    actions: list[dict[str, Any]],
    state: AgentState | None = None,
) -> str:
    if result.get("error"):
        return ""
    if not (result.get("boss_name") or result.get("target_boss")):
        return ""

    boss_name = result.get("display_boss_name") or _display_boss_name(
        result.get("boss_name") or result.get("target_boss"),
        result.get("difficulty"),
    )
    requirement = result.get("boss_requirements") or {}
    requested_difficulty = _query_difficulty_label(state)
    used_difficulty = result.get("difficulty_label") or _korean_difficulty(result.get("difficulty"))
    confidence = (
        requirement.get("raw_fields", {}).get("confidence")
        if isinstance(requirement.get("raw_fields"), dict)
        else ""
    )
    lines = [
        "권장 최종 답변 초안 (동적 AgentState 값 기반):",
        "아래 숫자와 표는 research/nexon_api/calculator/analytics 결과에서 생성한 값입니다. final_answer는 이 값을 우선 근거로 사용하세요.",
        "## 결론",
        f"- 대상: {boss_name}",
        f"- 판정: {result.get('status_label')} / clear_status={result.get('clear_status')} / 도전 가능={result.get('challengeable')}",
        f"- 적합도: 보정 {result.get('challenge_fit_score')}, 기초 {result.get('raw_challenge_fit_score')}",
    ]
    if requested_difficulty or used_difficulty:
        lines.append(f"- 질문 난이도: {requested_difficulty or '명시 없음'}, research 적용 난이도: {used_difficulty or '미상'}")
    if requested_difficulty and used_difficulty and requested_difficulty != used_difficulty:
        lines.append("- 난이도 주의: 질문 난이도와 research 적용 난이도가 다르므로 가능 여부를 단정하지 말고 이 차이를 명시하세요.")
    if confidence:
        lines.append(f"- 요구치 신뢰도/상태: {confidence}")

    comparison_rows = _requirement_comparison_table(character, result)
    if comparison_rows:
        lines.extend(
            [
                "## 보스 요구치 vs 현재 캐릭터",
                "| 항목 | 현재 | 기준 | 부족분 | 충족률 |",
                "| --- | ---: | ---: | ---: | ---: |",
                *comparison_rows,
            ]
        )

    lacking_stats = result.get("lacking_stats") or []
    if lacking_stats:
        lines.append("## 부족 스탯 요약")
        for item in lacking_stats[:6]:
            lines.append(
                "- "
                f"{item.get('label') or item.get('stat')}: "
                f"현재 {_format_answer_number(item.get('actual'))}, "
                f"기준 {_format_answer_number(item.get('required'))}, "
                f"충족률 {_format_answer_number(float(item.get('ratio') or 0) * 100, '%')}"
            )

    component_rows = _component_table(result)
    if component_rows:
        lines.extend(
            [
                "## analytics 판정 구성요소",
                "| 요소 | 점수 | 가중치 |",
                "| --- | ---: | ---: |",
                *component_rows,
            ]
        )

    calculator_context = _calculator_detail_context(state, result)
    if calculator_context:
        lines.append("## calculator 계산 근거")
        lines.append(calculator_context)

    action_rows = _action_table(actions)
    if action_rows:
        lines.extend(
            [
                "## 추천 성장 우선순위",
                "| 우선 | 분류 | 대상 | 예상 전투력 | 설명 |",
                "| ---: | --- | --- | ---: | --- |",
                *action_rows,
            ]
        )

    lines.extend(
        [
            "## 답변 한계",
            "- 위 수치는 research가 전달한 보스 요구치, Nexon API 캐릭터 상태, calculator 계산 결과만 사용했습니다.",
            "- analytics/final_answer는 직접 DB/API/로컬 파일을 다시 조회하지 않습니다.",
            "- 실제 클리어 가능성은 패턴 숙련도, 도핑, 링크/유니온 배치, 직업 운용, 파티 여부에 따라 달라질 수 있습니다.",
        ]
    )
    return "\n".join(lines)


def run_analystic(state: AgentState, **_: Any) -> AgentState:
    """Interpret research and calculator outputs without doing new DB/API/tool calls."""

    validate_agent_inputs("analystic", state)
    character = _character_input(state)
    requirements = _research_requirements(state)
    wants_all_boss_tier_table = _wants_all_boss_tier_table(state)

    if not requirements:
        result = _empty_result("research 결과에서 보스 요구 스탯 근거를 찾지 못했습니다.")
        actions: list[dict[str, Any]] = _growth_forecast_actions(state, start_priority=1)
    else:
        target_requirement = _select_target_requirement(state, requirements)
        effective_query = str(state.get("contextualized_query") or state.get("user_query") or "")
        wants_available_list = any(
            keyword in effective_query
            for keyword in ("어디까지", "가능한 보스", "추천 보스", "갈 수 있는", "가능해?")
        ) and len(requirements) > 1 and not _target_hint_score(effective_query, target_requirement or {})

        if wants_all_boss_tier_table or wants_available_list:
            result = _available_bosses_result(
                character,
                requirements,
                include_all=wants_all_boss_tier_table,
            )
            actions = result.get("recommended_actions", []) or []
        elif target_requirement:
            result = _analyze_requirement(character, target_requirement)
            actions = _recommended_actions(result, state)
        else:
            result = _empty_result("분석할 대상 보스를 선택하지 못했습니다.")
            actions = []
    deterministic_actions = actions
    deterministic_guidance = _answer_guidance(character, result, deterministic_actions, state)
    actions = deterministic_actions
    answer_guidance = deterministic_guidance
    tool_results = dict(state.get("tool_results") or {})
    tool_results["analystic"] = {
        **result,
        "character_input": character,
        "research_requirement_count": len(requirements),
        "answer_guidance": answer_guidance,
        "deterministic_answer_guidance": deterministic_guidance,
        "deterministic_recommended_actions": deterministic_actions,
        "llm_handoff_source": "deterministic_fallback",
    }

    next_state: AgentState = {
        **state,
        "tool_results": tool_results,
        "growth_report": _growth_report(state, character, result, actions),
        "recommended_actions": actions,
        "confidence_score": float(result.get("challenge_fit_score") or state.get("confidence_score") or 0.0),
        "context": _append_answer_guidance_to_context(
            _append_analysis_to_context(str(state.get("context") or ""), result),
            answer_guidance,
        ),
    }
    if result.get("lacking_stats"):
        next_state["bottleneck_analysis"] = {
            **(state.get("bottleneck_analysis") or {}),
            **_bottleneck_from_result(result),
        }
    validate_agent_outputs("analystic", next_state)
    return next_state


def analytics_agent(*, state: AgentState, **kwargs: Any) -> AgentState:
    """LangGraph analystic node entrypoint."""

    user_query = state.get("user_query", "")
    next_state = run_analystic(state, **kwargs)
    return {
        **next_state,
        "user_query": user_query,
    }
