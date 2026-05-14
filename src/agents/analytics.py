from __future__ import annotations

import ast
import json
import re
from datetime import datetime
from typing import Any

from common.get_model import get_llm
from common.state import AgentState, RetrievedDocument
from common.validator import validate_agent_inputs, validate_agent_outputs


STATUS_LABELS = {
    "recommended": "권장",
    "challengeable": "도전 가능",
    "risky": "위험",
    "difficult": "어려움",
    "unknown": "판단 보류",
}

STAT_LABELS = {
    "level": "레벨",
    "combat_power": "전투력",
    "main_stat": "주스탯",
    "attack_or_magic": "공격력/마력",
    "boss_damage": "보스 데미지",
    "ignore_def": "방어율 무시",
    "crit_rate": "크리티컬 확률",
    "crit_damage": "크리티컬 데미지",
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
    docs = list(state.get("selected_evidence") or state.get("retrieved_docs") or [])
    requirements = []
    for doc in docs:
        requirement = _requirement_from_document(doc)
        if requirement:
            requirements.append(requirement)
    return requirements


def _normalize_text(value: Any) -> str:
    return re.sub(r"\s+", "", str(value or "")).lower()


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


def _status(score: float, lacking_stats: list[dict[str, Any]]) -> str:
    severe = any(item["ratio"] < 0.75 and item["stat"] in {"combat_power", "main_stat", "ignore_def", "force"} for item in lacking_stats)
    if score >= 1.03 and not lacking_stats:
        return "recommended"
    if score >= 0.93 and not severe:
        return "challengeable"
    if score >= 0.80:
        return "risky"
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

    score = round(weighted_score / active_weight, 4) if active_weight else 0.0
    lacking_stats.sort(key=lambda item: (item["ratio"], item["stat"]))
    clear_status = _status(score, lacking_stats) if active_weight else "unknown"
    boss_name = str(requirement.get("boss_name") or "unknown")
    return {
        "target_boss": boss_name,
        "boss_name": boss_name,
        "difficulty": requirement.get("difficulty"),
        "clear_status": clear_status,
        "status_label": STATUS_LABELS.get(clear_status, clear_status),
        "challenge_fit_score": score,
        "challengeable": clear_status in {"recommended", "challengeable"},
        "boss_clear_prediction": {boss_name: clear_status in {"recommended", "challengeable"}},
        "stat_ratios": ratios,
        "lacking_stats": lacking_stats,
        "boss_requirements": requirement,
        "decision_basis": {
            "formula": "state_research_requirement_weighted_fit",
            "data_flow": "research -> evidence_formatter -> calculator -> analystic",
            "uses_direct_graph_lookup": False,
            "uses_direct_api_lookup": False,
            "weights": STAT_WEIGHTS,
        },
        "data_reliability": "research_context_and_calculator_state",
    }


def _action_for_status(analysis: dict[str, Any]) -> dict[str, Any]:
    boss_name = str(analysis.get("boss_name") or analysis.get("target_boss") or "대상 보스")
    status = str(analysis.get("clear_status") or "unknown")
    score = float(analysis.get("challenge_fit_score") or 0)
    if status == "recommended":
        description = f"{boss_name}는 현재 계산 기준으로 권장 도전권입니다. 패턴 숙련도와 버프 준비를 확인하고 도전하세요."
        priority = 1
    elif status == "challengeable":
        description = f"{boss_name}는 도전 가능권입니다. 점수 {score:.2f} 기준으로 주요 요구치가 크게 벗어나지 않습니다."
        priority = 1
    elif status == "risky":
        description = f"{boss_name}는 가능성이 있지만 위험합니다. 부족 스탯을 보완하고 연습 모드나 파티 보조를 권장합니다."
        priority = 2
    else:
        description = f"{boss_name}는 현재 수치만으로는 어렵습니다. 아래 부족 스탯을 먼저 보완하는 편이 안전합니다."
        priority = 2
    return {
        "category": "BOSS_CHALLENGE",
        "target": boss_name,
        "priority": priority,
        "expected_cp_gain": 0,
        "description": description,
    }


def _actions_for_lacking_stats(analysis: dict[str, Any]) -> list[dict[str, Any]]:
    actions = []
    for index, item in enumerate((analysis.get("lacking_stats") or [])[:4], start=1):
        label = item.get("label") or item.get("stat")
        actual = item.get("actual")
        required = item.get("required")
        actions.append(
            {
                "category": "STAT_IMPROVEMENT",
                "target": str(label),
                "priority": index + 1,
                "expected_cp_gain": 0,
                "description": f"{label}이 요구치보다 낮습니다. 현재 {actual}, 기준 {required}입니다.",
            }
        )
    return actions


def _recommended_actions(analysis: dict[str, Any]) -> list[dict[str, Any]]:
    return [_action_for_status(analysis), *_actions_for_lacking_stats(analysis)][:5]


def _available_bosses_result(character: dict[str, Any], requirements: list[dict[str, Any]]) -> dict[str, Any]:
    analyses = [_analyze_requirement(character, item) for item in requirements]
    groups = {"recommended": [], "challengeable": [], "risky": [], "difficult": []}
    for item in analyses:
        status = item.get("clear_status")
        if status in groups:
            groups[status].append(item)
    for status, items in groups.items():
        items.sort(key=lambda row: float(row.get("challenge_fit_score") or 0), reverse=status != "difficult")
        groups[status] = items[:8]

    available = [*groups["recommended"], *groups["challengeable"], *groups["risky"]]
    actions = [
        _action_for_status(item)
        for item in [*groups["recommended"][:3], *groups["challengeable"][:3]]
    ]
    return {
        "available_bosses": available[:10],
        "boss_groups": groups,
        "recommended_actions": actions[:5],
        "challenge_fit_score": max((float(item.get("challenge_fit_score") or 0) for item in available), default=0.0),
        "summary": {
            "recommended_count": len(groups["recommended"]),
            "challengeable_count": len(groups["challengeable"]),
            "risky_count": len(groups["risky"]),
            "difficult_count": len(groups["difficult"]),
            "total_bosses_checked": len(analyses),
        },
        "data_reliability": "research_context_and_calculator_state",
    }


def _empty_result(message: str) -> dict[str, Any]:
    return {
        "available_bosses": [],
        "boss_groups": {"recommended": [], "challengeable": [], "risky": [], "difficult": []},
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
            boss = item.get("boss_name") or item.get("target_boss")
            if boss:
                prediction[str(boss)] = True
    for status in ("risky", "difficult"):
        for item in groups.get(status, []) or []:
            boss = item.get("boss_name") or item.get("target_boss")
            if boss and boss not in prediction:
                prediction[str(boss)] = False
    return prediction


def _analysis_context(result: dict[str, Any]) -> str:
    if result.get("error"):
        return f"Analytics: {result['error']}"
    if result.get("boss_name") or result.get("target_boss"):
        lacking = result.get("lacking_stats") or []
        lacking_text = ", ".join(
            f"{item.get('label')}: {item.get('actual')}/{item.get('required')}"
            for item in lacking[:4]
        ) or "큰 부족 스탯 없음"
        return (
            "Analytics boss readiness: "
            f"{result.get('boss_name') or result.get('target_boss')} "
            f"status={result.get('status_label')} "
            f"score={result.get('challenge_fit_score')} "
            f"lacking={lacking_text}"
        )
    summary = result.get("summary") or {}
    return (
        "Analytics available bosses: "
        f"recommended={summary.get('recommended_count', 0)}, "
        f"challengeable={summary.get('challengeable_count', 0)}, "
        f"risky={summary.get('risky_count', 0)}, "
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


def _action_for_status(analysis: dict[str, Any]) -> dict[str, Any]:
    boss_name = str(analysis.get("boss_name") or analysis.get("target_boss") or "대상 보스")
    status = str(analysis.get("clear_status") or "unknown")
    score = float(analysis.get("challenge_fit_score") or 0)
    if status == "recommended":
        description = f"{boss_name}는 현재 분석 기준으로 권장 도전권입니다. 보스 패턴 숙련, 버프, 도핑을 준비하고 도전하세요."
        priority = 1
    elif status == "challengeable":
        description = f"{boss_name}는 도전 가능권입니다. 적합도 {score:.2f} 기준으로 큰 결격은 없지만 버프와 패턴 숙련을 챙기는 편이 안전합니다."
        priority = 1
    elif status == "risky":
        description = f"{boss_name}는 도전 자체는 가능할 수 있지만 위험권입니다. 부족 스탯을 보완한 뒤 재평가하는 것을 권장합니다."
        priority = 1
    else:
        description = f"{boss_name}는 현재 수치만으로는 어렵습니다. 아래 부족 스탯과 성장 우선순위를 먼저 보완하세요."
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
) -> str:
    lines = [
        "Analytics final answer guide:",
        "답변 기준: research와 calculator 결과만 사용했습니다. 근거에 없는 권장 스펙, 커뮤니티 기준, 공식 기준, 보스 패턴 설명은 제외합니다.",
        "보스 요구 스탯 근거가 없으면 가능/불가능을 단정하지 않고 계산된 성장 우선순위만 안내합니다.",
        (
            "캐릭터: "
            f"{character.get('character_name') or 'unknown'}"
            f"({character.get('world_name') or '월드 미상'}, {character.get('job_name') or '직업 미상'})"
        ),
    ]

    if result.get("error"):
        lines.append(f"판정: {result['error']} 보스 가능 여부는 단정하지 말고, 계산된 성장 우선순위만 안내하세요.")
    elif result.get("boss_name") or result.get("target_boss"):
        boss_name = result.get("boss_name") or result.get("target_boss")
        difficulty = result.get("difficulty") or "난이도 미상"
        lines.append(
            f"판정: {boss_name} {difficulty} - {result.get('status_label')} "
            f"(적합도 {result.get('challenge_fit_score')}, 도전 가능={result.get('challengeable')})"
        )
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
        lines.append(
            "판정: 추천 가능 보스 목록 "
            f"권장 {summary.get('recommended_count', 0)}개, "
            f"도전 가능 {summary.get('challengeable_count', 0)}개, "
            f"위험 {summary.get('risky_count', 0)}개"
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

    lines.append("주의: analytics는 이미 state에 있는 research/calculator 결과만 사용하며, 직접 DB/API를 다시 조회하지 않습니다.")
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


def _parse_json_object(content: str) -> dict[str, Any]:
    text = str(content or "").strip()
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


def _calculator_interpretation(state: AgentState) -> dict[str, Any]:
    tool_results = state.get("tool_results") or {}
    if not isinstance(tool_results, dict):
        return {}
    calculator = tool_results.get("calculator") or {}
    if not isinstance(calculator, dict):
        return {}
    interpretation = calculator.get("llm_interpretation") or {}
    return interpretation if isinstance(interpretation, dict) else {}


def _action_identity(action: dict[str, Any]) -> str:
    return f"{action.get('category', '')}|{action.get('target', '')}"


def _normalize_llm_actions(
    parsed_actions: Any,
    fallback_actions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if not isinstance(parsed_actions, list):
        return fallback_actions

    by_identity = {
        _action_identity(action): action
        for action in fallback_actions
        if isinstance(action, dict)
    }
    by_target = {
        str(action.get("target") or ""): action
        for action in fallback_actions
        if isinstance(action, dict)
    }
    normalized = []
    used = set()
    for item in parsed_actions:
        if not isinstance(item, dict):
            continue
        source = by_identity.get(_action_identity(item)) or by_target.get(str(item.get("target") or ""))
        if not source:
            continue
        identity = _action_identity(source)
        if identity in used:
            continue
        used.add(identity)
        normalized.append(
            {
                **source,
                "priority": int(_parse_number(item.get("priority"), source.get("priority", len(normalized) + 1))),
                "description": str(item.get("description") or source.get("description") or ""),
            }
        )
    normalized.sort(key=lambda action: int(action.get("priority") or 999))
    return normalized[:5] or fallback_actions


def _analytics_llm_prompt(
    state: AgentState,
    character: dict[str, Any],
    result: dict[str, Any],
    actions: list[dict[str, Any]],
    deterministic_guidance: str,
) -> str:
    payload = {
        "user_query": state.get("contextualized_query") or state.get("user_query", ""),
        "character": {
            "character_name": character.get("character_name"),
            "world_name": character.get("world_name"),
            "job_name": character.get("job_name"),
            "level": character.get("level"),
            "combat_power": character.get("combat_power"),
        },
        "analysis": {
            "target_boss": result.get("target_boss") or result.get("boss_name"),
            "difficulty": result.get("difficulty"),
            "clear_status": result.get("clear_status"),
            "status_label": result.get("status_label"),
            "challenge_fit_score": result.get("challenge_fit_score"),
            "challengeable": result.get("challengeable"),
            "lacking_stats": (result.get("lacking_stats") or [])[:5],
            "error": result.get("error"),
        },
        "calculator_interpretation": _calculator_interpretation(state),
        "candidate_actions": actions[:8],
        "deterministic_guidance": deterministic_guidance,
    }
    return "\n".join(
        [
            "You are the analytics recommendation writer.",
            "The analysis and calculations are already finished by code.",
            "Use only the provided analysis, calculator_interpretation, and candidate_actions.",
            "Do not invent new stats, combat power gains, costs, boss requirements, item names, official/community standards, or boss patterns.",
            "If analysis.error exists, do not decide boss challenge success/failure. Recommend only the calculated growth actions.",
            "Write concise Korean for a MapleStory newbie.",
            "Return only a JSON object with:",
            "- answer_guidance: 4-8 short Korean lines final_answer can reuse",
            "- recommended_actions: at most 5 actions selected from candidate_actions, preserving category and target",
            "Each recommended action must include category, target, priority, description.",
            "",
            f"Input JSON: {json.dumps(payload, ensure_ascii=False, default=str)}",
        ]
    )


def _llm_analytics_handoff(
    state: AgentState,
    character: dict[str, Any],
    result: dict[str, Any],
    actions: list[dict[str, Any]],
    deterministic_guidance: str,
) -> dict[str, Any]:
    fallback = {
        "answer_guidance": deterministic_guidance,
        "recommended_actions": actions,
        "source": "deterministic_fallback",
    }
    try:
        response = get_llm().invoke(
            _analytics_llm_prompt(state, character, result, actions, deterministic_guidance)
        )
    except Exception as exc:
        return {**fallback, "llm_error": str(exc)}

    content = getattr(response, "content", response)
    if isinstance(content, list):
        content = "\n".join(str(item) for item in content)
    parsed = _parse_json_object(str(content))
    answer_guidance = str(parsed.get("answer_guidance") or deterministic_guidance).strip()
    return {
        "answer_guidance": answer_guidance or deterministic_guidance,
        "recommended_actions": _normalize_llm_actions(parsed.get("recommended_actions"), actions),
        "source": "llm_summary" if parsed else "deterministic_fallback",
    }


def run_analystic(state: AgentState, **_: Any) -> AgentState:
    """Interpret research and calculator outputs without doing new DB/API/tool calls."""

    validate_agent_inputs("analystic", state)
    character = _character_input(state)
    requirements = _research_requirements(state)

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

        if wants_available_list:
            result = _available_bosses_result(character, requirements)
            actions = result.get("recommended_actions", []) or []
        elif target_requirement:
            result = _analyze_requirement(character, target_requirement)
            actions = _recommended_actions(result, state)
        else:
            result = _empty_result("분석할 대상 보스를 선택하지 못했습니다.")
            actions = []

    deterministic_actions = actions
    deterministic_guidance = _answer_guidance(character, result, deterministic_actions)
    handoff = _llm_analytics_handoff(
        state,
        character,
        result,
        deterministic_actions,
        deterministic_guidance,
    )
    actions = handoff["recommended_actions"]
    answer_guidance = handoff["answer_guidance"]
    tool_results = dict(state.get("tool_results") or {})
    tool_results["analystic"] = {
        **result,
        "character_input": character,
        "research_requirement_count": len(requirements),
        "answer_guidance": answer_guidance,
        "deterministic_answer_guidance": deterministic_guidance,
        "deterministic_recommended_actions": deterministic_actions,
        "llm_handoff_source": handoff.get("source"),
    }
    if handoff.get("llm_error"):
        tool_results["analystic"]["llm_handoff_error"] = handoff["llm_error"]

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
