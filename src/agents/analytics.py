from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from langchain.agents import create_agent
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.tools import tool
from pydantic import BaseModel, Field

try:
    from neo4j import GraphDatabase
except Exception:  # pragma: no cover - neo4j is installed in the project env.
    GraphDatabase = None

try:
    from common.get_model import get_llm
except Exception:  # pragma: no cover - depends on local env variables.
    get_llm = None

try:
    from common.prompt import master_prompt
except Exception:  # pragma: no cover - prompt file is optional at runtime.
    master_prompt = ""

try:
    from common.validator import validate_agent_inputs, validate_agent_outputs
except Exception:  # common.domain is currently allowed to be in merge-conflict state.
    validate_agent_inputs = None
    validate_agent_outputs = None

if TYPE_CHECKING:
    from common.state import AgentState


_BOSS_GRAPH_CONNECTION: Any = None
_BOSS_GRAPH_DATABASE: Optional[str] = None


class BossStatAnalysisInput(BaseModel):
    """Input schema matching OpenAPI BossAnalysisRequest plus normalized stats."""

    character_name: str = Field(..., description="Character name.")
    job_name: str = Field(..., description="Character job or class name.")
    level: int = Field(..., ge=1, description="Character level.")
    target_boss: str = Field(..., description="Target boss name.")
    combat_power: int = Field(..., ge=0, description="Current combat power.")
    main_stat: int = Field(..., ge=0, description="Primary stat value.")
    attack_power: int = Field(0, ge=0, description="Current attack power.")
    magic_power: int = Field(0, ge=0, description="Current magic power.")
    boss_damage: float = Field(0.0, ge=0, description="Boss damage percentage.")
    ignore_def: float = Field(0.0, ge=0, description="Ignore enemy defense percentage.")
    crit_rate: float = Field(0.0, ge=0, description="Critical rate percentage.")
    crit_damage: float = Field(0.0, ge=0, description="Critical damage percentage.")
    final_damage: float = Field(0.0, ge=0, description="Final damage percentage.")
    arcane_force: int = Field(0, ge=0, description="Arcane force.")
    authentic_force: int = Field(0, ge=0, description="Authentic force.")
    starforce: int = Field(0, ge=0, description="Total starforce.")
    union_level: int = Field(0, ge=0, description="Union level.")


class AvailableBossesInput(BaseModel):
    """Input schema for finding all bosses suitable for the current character."""

    character_name: str = Field(..., description="Character name.")
    job_name: str = Field(..., description="Character job or class name.")
    level: int = Field(..., ge=1, description="Character level.")
    combat_power: int = Field(..., ge=0, description="Current combat power.")
    main_stat: int = Field(..., ge=0, description="Primary stat value.")
    attack_power: int = Field(0, ge=0, description="Current attack power.")
    magic_power: int = Field(0, ge=0, description="Current magic power.")
    boss_damage: float = Field(0.0, ge=0, description="Boss damage percentage.")
    ignore_def: float = Field(0.0, ge=0, description="Ignore enemy defense percentage.")
    crit_rate: float = Field(0.0, ge=0, description="Critical rate percentage.")
    crit_damage: float = Field(0.0, ge=0, description="Critical damage percentage.")
    final_damage: float = Field(0.0, ge=0, description="Final damage percentage.")
    arcane_force: int = Field(0, ge=0, description="Arcane force.")
    authentic_force: int = Field(0, ge=0, description="Authentic force.")
    starforce: int = Field(0, ge=0, description="Total starforce.")
    union_level: int = Field(0, ge=0, description="Union level.")
    include_risky: bool = Field(True, description="Whether to include risky bosses in the returned list.")
    max_results: int = Field(20, ge=1, le=100, description="Maximum number of bosses to return per group.")


def _load_project_env() -> None:
    project_root = Path(__file__).resolve().parents[2]
    for env_path in (project_root / ".env", project_root / "database" / ".env"):
        if not env_path.exists():
            continue
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def set_boss_neo4j_connection(connection: Any, database: Optional[str] = None) -> None:
    """Register the Neo4j driver/session/graph object used by the analytics tool."""

    global _BOSS_GRAPH_CONNECTION, _BOSS_GRAPH_DATABASE
    _BOSS_GRAPH_CONNECTION = connection
    if database is not None:
        _BOSS_GRAPH_DATABASE = database


def set_boss_db_connection(connection: Any, database: Optional[str] = None) -> None:
    """Backward-compatible alias for registering the Neo4j boss graph connection."""

    set_boss_neo4j_connection(connection, database=database)


def _get_boss_neo4j_connection() -> Any:
    global _BOSS_GRAPH_CONNECTION, _BOSS_GRAPH_DATABASE

    if _BOSS_GRAPH_CONNECTION is not None:
        return _BOSS_GRAPH_CONNECTION

    if GraphDatabase is None:
        raise RuntimeError("neo4j package is not available.")

    _load_project_env()
    uri = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
    user = os.environ.get("NEO4J_USER", "neo4j")
    password = os.environ.get("NEO4J_PASSWORD")
    if not password:
        raise RuntimeError("NEO4J_PASSWORD is required to connect to the boss graph.")

    _BOSS_GRAPH_DATABASE = os.environ.get("NEO4J_DATABASE", _BOSS_GRAPH_DATABASE)
    _BOSS_GRAPH_CONNECTION = GraphDatabase.driver(uri, auth=(user, password))
    return _BOSS_GRAPH_CONNECTION


def _value(source: Any, key: str, default: Any = None) -> Any:
    if source is None:
        return default
    if isinstance(source, dict):
        return source.get(key, default)
    return getattr(source, key, default)


def _number(source: Any, key: str, default: float = 0.0) -> float:
    value = _value(source, key, default)
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _record_to_dict(record: Any) -> Dict[str, Any]:
    if record is None:
        return {}
    if isinstance(record, dict):
        return dict(record)
    if hasattr(record, "data"):
        return dict(record.data())
    if hasattr(record, "_mapping"):
        return dict(record._mapping)
    try:
        return dict(record)
    except (TypeError, ValueError):
        return {}


def _result_to_rows(result: Any) -> List[Dict[str, Any]]:
    if result is None:
        return []
    if isinstance(result, tuple):
        result = result[0]
    if hasattr(result, "records"):
        return [_record_to_dict(record) for record in result.records]
    if isinstance(result, list):
        return [_record_to_dict(record) for record in result]
    return [_record_to_dict(record) for record in result]


def _run_neo4j_query(query: str, params: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    if _BOSS_GRAPH_CONNECTION is None:
        raise RuntimeError("Neo4j boss graph connection is not configured.")

    params = params or {}
    connection = _BOSS_GRAPH_CONNECTION

    if hasattr(connection, "query"):
        try:
            return _result_to_rows(connection.query(query, params=params))
        except TypeError:
            return _result_to_rows(connection.query(query, params))

    if hasattr(connection, "execute_query"):
        try:
            return _result_to_rows(connection.execute_query(query, parameters_=params))
        except TypeError:
            return _result_to_rows(connection.execute_query(query, params))

    if hasattr(connection, "session"):
        with connection.session() as session:
            return _result_to_rows(session.run(query, params))

    if hasattr(connection, "run"):
        return _result_to_rows(connection.run(query, params))

    raise TypeError("Neo4j connection must provide query, execute_query, session, or run.")


def _parse_boss_target(target_boss: str) -> Dict[str, Optional[str]]:
    normalized = " ".join(str(target_boss).split())
    difficulty_aliases = {
        "이지": "EASY",
        "easy": "EASY",
        "노멀": "NORMAL",
        "normal": "NORMAL",
        "하드": "HARD",
        "hard": "HARD",
        "카오스": "CHAOS",
        "chaos": "CHAOS",
        "익스트림": "EXTREME",
        "extreme": "EXTREME",
    }
    difficulty_ko = {
        "EASY": "이지",
        "NORMAL": "노멀",
        "HARD": "하드",
        "CHAOS": "카오스",
        "EXTREME": "익스트림",
    }

    lowered = normalized.lower()
    difficulty = None
    base_boss = normalized
    for prefix, value in difficulty_aliases.items():
        if lowered.startswith(f"{prefix} "):
            difficulty = value
            base_boss = normalized[len(prefix) :].strip()
            break

    return {
        "target_boss": normalized,
        "base_boss": base_boss,
        "difficulty": difficulty,
        "difficulty_ko": difficulty_ko.get(difficulty) if difficulty else None,
    }


def _clean_boss_requirement_row(row: Dict[str, Any]) -> Dict[str, Any]:
    boss_name = _value(row, "boss_name") or _value(row, "name")
    if not boss_name:
        return {}

    cleaned = {
        "boss_name": boss_name,
        "difficulty": _value(row, "difficulty"),
        "required_level": _value(row, "required_level"),
        "required_combat_power": _value(row, "required_combat_power"),
        "required_main_stat": _value(row, "required_main_stat"),
        "required_attack_power": _value(row, "required_attack_power"),
        "required_magic_power": _value(row, "required_magic_power"),
        "required_boss_damage": _value(row, "required_boss_damage"),
        "required_ignore_def": _value(row, "required_ignore_def"),
        "required_crit_rate": _value(row, "required_crit_rate"),
        "required_crit_damage": _value(row, "required_crit_damage"),
        "required_final_damage": _value(row, "required_final_damage"),
        "required_arcane_force": _value(row, "required_arcane_force"),
        "required_authentic_force": _value(row, "required_authentic_force"),
        "required_starforce": _value(row, "required_starforce"),
        "required_union_level": _value(row, "required_union_level"),
        "source_name": _value(row, "source_name"),
        "source_url": _value(row, "source_url"),
        "reliability": _value(row, "reliability"),
    }
    return {key: value for key, value in cleaned.items() if value is not None}


BOSS_REQUIREMENT_RETURN = """
RETURN
    coalesce(row_boss_name, "") AS boss_name,
    row_difficulty AS difficulty,
    coalesce(n.required_level, n.level, n.monster_level, n.entry_level) AS required_level,
    coalesce(n.required_combat_power, n.combat_power_cut, n.min_combat_power) AS required_combat_power,
    coalesce(n.required_main_stat, n.main_stat_cut, n.min_main_stat) AS required_main_stat,
    coalesce(n.required_attack_power, n.attack_power_cut, n.min_attack_power) AS required_attack_power,
    coalesce(n.required_magic_power, n.magic_power_cut, n.min_magic_power) AS required_magic_power,
    coalesce(n.required_boss_damage, n.boss_damage_cut, n.min_boss_damage) AS required_boss_damage,
    coalesce(n.required_ignore_def, n.ignore_def_cut, n.ied_cut, n.min_ignore_def) AS required_ignore_def,
    coalesce(n.required_crit_rate, n.crit_rate_cut, n.min_crit_rate) AS required_crit_rate,
    coalesce(n.required_crit_damage, n.crit_damage_cut, n.min_crit_damage) AS required_crit_damage,
    coalesce(n.required_final_damage, n.final_damage_cut, n.min_final_damage) AS required_final_damage,
    coalesce(n.required_arcane_force, n.arcane_force_cut, n.arcane_force) AS required_arcane_force,
    coalesce(n.required_authentic_force, n.authentic_force_cut, n.authentic_force) AS required_authentic_force,
    coalesce(n.required_starforce, n.starforce_cut, n.starforce) AS required_starforce,
    coalesce(n.required_union_level, n.union_level_cut, n.union_level) AS required_union_level,
    coalesce(n.source_name, n.source) AS source_name,
    n.source_url AS source_url,
    n.reliability AS reliability
"""


def _fetch_boss_requirements(target_boss: str) -> Dict[str, Any]:
    target = _parse_boss_target(target_boss)
    params = {
        "target_boss": target["target_boss"],
        "base_boss": target["base_boss"],
        "difficulty": target["difficulty"],
        "difficulty_ko": target["difficulty_ko"],
    }

    queries = (
        f"""
        MATCH (n)
        WHERE any(label IN labels(n) WHERE label IN ["BossRequirement", "Boss", "BossCut"])
        WITH
            n,
            coalesce(n.boss_name, n.name, n.korean_name, n.display_name) AS row_boss_name,
            coalesce(n.difficulty, n.difficulty_name, n.difficultyName) AS row_difficulty
        WHERE
            toLower(toString(row_boss_name)) = toLower($target_boss)
            OR toLower(toString(row_boss_name)) = toLower($base_boss)
            OR toLower(toString(coalesce(n.full_name, ""))) = toLower($target_boss)
        WITH n, row_boss_name, row_difficulty
        WHERE
            $difficulty IS NULL
            OR toLower(toString(row_boss_name)) = toLower($target_boss)
            OR toUpper(toString(row_difficulty)) = $difficulty
            OR row_difficulty = $difficulty_ko
        {BOSS_REQUIREMENT_RETURN}
        ORDER BY
            CASE WHEN toLower(toString(boss_name)) = toLower($target_boss) THEN 0 ELSE 1 END,
            coalesce(required_combat_power, 0) DESC
        LIMIT 1
        """,
        f"""
        MATCH (b)-[]->(n)
        WHERE any(label IN labels(b) WHERE label IN ["Boss"])
          AND any(label IN labels(n) WHERE label IN ["BossRequirement", "Requirement", "BossCut"])
        WITH
            n,
            coalesce(n.boss_name, b.boss_name, b.name, b.korean_name, b.display_name) AS row_boss_name,
            coalesce(n.difficulty, b.difficulty, n.difficulty_name, b.difficulty_name) AS row_difficulty
        WHERE
            toLower(toString(row_boss_name)) = toLower($target_boss)
            OR toLower(toString(row_boss_name)) = toLower($base_boss)
        WITH n, row_boss_name, row_difficulty
        WHERE
            $difficulty IS NULL
            OR toLower(toString(row_boss_name)) = toLower($target_boss)
            OR toUpper(toString(row_difficulty)) = $difficulty
            OR row_difficulty = $difficulty_ko
        {BOSS_REQUIREMENT_RETURN}
        ORDER BY
            CASE WHEN toLower(toString(boss_name)) = toLower($target_boss) THEN 0 ELSE 1 END,
            coalesce(required_combat_power, 0) DESC
        LIMIT 1
        """,
    )

    last_error: Optional[Exception] = None
    for query in queries:
        try:
            rows = _run_neo4j_query(query, params)
            for row in rows:
                cleaned = _clean_boss_requirement_row(row)
                if cleaned:
                    return cleaned
        except Exception as exc:  # pragma: no cover - depends on team Neo4j schema.
            last_error = exc

    if last_error:
        raise RuntimeError(f"Neo4j boss requirement query failed: {last_error}") from last_error
    raise LookupError(f"Boss requirement not found in Neo4j: {target_boss}")


def _fetch_all_boss_requirements() -> List[Dict[str, Any]]:
    queries = (
        f"""
        MATCH (n)
        WHERE any(label IN labels(n) WHERE label IN ["BossRequirement", "Boss", "BossCut"])
        WITH
            n,
            coalesce(n.boss_name, n.name, n.korean_name, n.display_name) AS row_boss_name,
            coalesce(n.difficulty, n.difficulty_name, n.difficultyName) AS row_difficulty
        {BOSS_REQUIREMENT_RETURN}
        ORDER BY coalesce(required_combat_power, 0) ASC, coalesce(required_level, 0) ASC
        """,
        f"""
        MATCH (b)-[]->(n)
        WHERE any(label IN labels(b) WHERE label IN ["Boss"])
          AND any(label IN labels(n) WHERE label IN ["BossRequirement", "Requirement", "BossCut"])
        WITH
            n,
            coalesce(n.boss_name, b.boss_name, b.name, b.korean_name, b.display_name) AS row_boss_name,
            coalesce(n.difficulty, b.difficulty, n.difficulty_name, b.difficulty_name) AS row_difficulty
        {BOSS_REQUIREMENT_RETURN}
        ORDER BY coalesce(required_combat_power, 0) ASC, coalesce(required_level, 0) ASC
        """,
    )

    last_error: Optional[Exception] = None
    for query in queries:
        try:
            rows = [_clean_boss_requirement_row(row) for row in _run_neo4j_query(query)]
            rows = [row for row in rows if row]
            if rows:
                return rows
        except Exception as exc:  # pragma: no cover - depends on team Neo4j schema.
            last_error = exc

    if last_error:
        raise RuntimeError(f"Neo4j boss requirement list query failed: {last_error}") from last_error
    return []


def _ratio(actual: float, required: float) -> float:
    if required <= 0:
        return 1.0
    return round(actual / required, 4)


def _priority(ratio: float) -> int:
    if ratio < 0.75:
        return 1
    if ratio < 0.90:
        return 2
    if ratio < 1.0:
        return 3
    return 4


def _bottleneck(stat_name: str, actual: float, required: float, description: str) -> Dict[str, Any]:
    ratio = _ratio(actual, required)
    return {
        "category": "BOSS_READINESS",
        "target": stat_name,
        "stat": stat_name,
        "actual": actual,
        "required": required,
        "gap": round(max(0.0, required - actual), 2),
        "ratio": ratio,
        "priority": _priority(ratio),
        "expected_cp_gain": int(max(0.0, required - actual)),
        "description": description,
    }


def _boss_clear_score(ratios: Dict[str, float]) -> float:
    weights = {
        "combat_power": 0.35,
        "main_stat": 0.15,
        "attack_or_magic": 0.10,
        "boss_damage": 0.10,
        "ignore_def": 0.10,
        "crit_rate": 0.05,
        "crit_damage": 0.05,
        "final_damage": 0.05,
        "force": 0.03,
        "union_level": 0.02,
    }
    score = sum(min(1.2, ratios.get(key, 1.0)) * weight for key, weight in weights.items())
    return round(score, 4)


def _status(score: float, bottlenecks: List[Dict[str, Any]]) -> str:
    if any(item["priority"] <= 2 for item in bottlenecks):
        return "difficult"
    if score >= 1.05:
        return "recommended"
    if score >= 0.95:
        return "challengeable"
    return "risky"


def _sum_equipment_starforce(equipment_items: Any) -> int:
    if not equipment_items:
        return 0
    total = 0
    for item in equipment_items:
        total += int(_number(item, "starforce", 0))
    return total


def _target_boss_from_state(state: "AgentState", target_boss: Optional[str]) -> str:
    if target_boss:
        return target_boss
    direct_value = _value(state, "target_boss")
    if direct_value:
        return str(direct_value)

    raw_api_results = _value(state, "raw_api_results", {})
    raw_value = _value(raw_api_results, "target_boss")
    if raw_value:
        return str(raw_value)

    tool_results = _value(state, "tool_results", {})
    tool_value = _value(tool_results, "target_boss")
    if tool_value:
        return str(tool_value)

    raise ValueError("target_boss is required for analystic boss readiness analysis.")


def _has_target_boss(state: "AgentState", target_boss: Optional[str]) -> bool:
    if target_boss or _value(state, "target_boss"):
        return True
    if _value(_value(state, "raw_api_results", {}), "target_boss"):
        return True
    if _value(_value(state, "tool_results", {}), "target_boss"):
        return True
    return False


def _analyze_boss_row(
    boss: Dict[str, Any],
    *,
    character_name: str,
    job_name: str,
    level: int,
    target_boss: str,
    combat_power: int,
    main_stat: int,
    attack_power: int,
    magic_power: int,
    boss_damage: float,
    ignore_def: float,
    crit_rate: float,
    crit_damage: float,
    final_damage: float,
    arcane_force: int,
    authentic_force: int,
    starforce: int,
    union_level: int,
) -> Dict[str, Any]:
    current_attack_or_magic = max(attack_power, magic_power)
    required_attack_or_magic = max(
        _number(boss, "required_attack_power"),
        _number(boss, "required_magic_power"),
    )
    current_force = arcane_force + authentic_force
    required_force = _number(boss, "required_arcane_force") + _number(
        boss, "required_authentic_force"
    )

    checks = {
        "level": _ratio(level, _number(boss, "required_level")),
        "combat_power": _ratio(combat_power, _number(boss, "required_combat_power")),
        "main_stat": _ratio(main_stat, _number(boss, "required_main_stat")),
        "attack_or_magic": _ratio(current_attack_or_magic, required_attack_or_magic),
        "boss_damage": _ratio(boss_damage, _number(boss, "required_boss_damage")),
        "ignore_def": _ratio(ignore_def, _number(boss, "required_ignore_def")),
        "crit_rate": _ratio(min(crit_rate, 100), _number(boss, "required_crit_rate")),
        "crit_damage": _ratio(crit_damage, _number(boss, "required_crit_damage")),
        "final_damage": _ratio(final_damage, _number(boss, "required_final_damage")),
        "force": _ratio(current_force, required_force),
        "starforce": _ratio(starforce, _number(boss, "required_starforce")),
        "union_level": _ratio(union_level, _number(boss, "required_union_level")),
    }

    stat_pairs = {
        "level": (level, _number(boss, "required_level"), "Character level is below the boss baseline."),
        "combat_power": (
            combat_power,
            _number(boss, "required_combat_power"),
            "Combat power is below the boss requirement.",
        ),
        "main_stat": (main_stat, _number(boss, "required_main_stat"), "Primary stat is insufficient."),
        "attack_or_magic": (
            current_attack_or_magic,
            required_attack_or_magic,
            "Attack or magic power is below the boss baseline.",
        ),
        "boss_damage": (boss_damage, _number(boss, "required_boss_damage"), "Boss damage is insufficient."),
        "ignore_def": (ignore_def, _number(boss, "required_ignore_def"), "Ignore defense is insufficient."),
        "crit_rate": (min(crit_rate, 100), _number(boss, "required_crit_rate"), "Critical rate is insufficient."),
        "crit_damage": (crit_damage, _number(boss, "required_crit_damage"), "Critical damage is insufficient."),
        "final_damage": (final_damage, _number(boss, "required_final_damage"), "Final damage is insufficient."),
        "force": (current_force, required_force, "Arcane or authentic force is insufficient."),
        "starforce": (starforce, _number(boss, "required_starforce"), "Starforce is below the baseline."),
        "union_level": (union_level, _number(boss, "required_union_level"), "Union level is below the baseline."),
    }

    bottlenecks = [
        _bottleneck(stat_name, actual, required, description)
        for stat_name, (actual, required, description) in stat_pairs.items()
        if checks[stat_name] < 1.0
    ]
    bottlenecks.sort(key=lambda item: (item["priority"], item["ratio"]))

    score = _boss_clear_score(checks)
    status = _status(score, bottlenecks)
    boss_name = boss.get("boss_name", target_boss)

    return {
        "character_name": character_name,
        "job_name": job_name,
        "target_boss": boss_name,
        "difficulty": boss.get("difficulty"),
        "clear_status": status,
        "challenge_fit_score": score,
        "challengeable": status in {"recommended", "challengeable"},
        "boss_clear_prediction": {str(boss_name): status in {"recommended", "challengeable"}},
        "boss_challenge_prediction": {str(boss_name): status in {"recommended", "challengeable"}},
        "stat_ratios": checks,
        "bottleneck_analysis": {
            item["stat"]: round(max(0.0, 1 - item["ratio"]), 4) for item in bottlenecks
        },
        "lacking_stats": [item["stat"] for item in bottlenecks],
        "recommended_actions": bottlenecks[:5],
        "boss_requirements": boss,
        "data_reliability": "boss_requirements_from_neo4j",
    }


@tool(args_schema=BossStatAnalysisInput)
def analyze_boss_readiness(
    character_name: str,
    job_name: str,
    level: int,
    target_boss: str,
    combat_power: int,
    main_stat: int,
    attack_power: int = 0,
    magic_power: int = 0,
    boss_damage: float = 0.0,
    ignore_def: float = 0.0,
    crit_rate: float = 0.0,
    crit_damage: float = 0.0,
    final_damage: float = 0.0,
    arcane_force: int = 0,
    authentic_force: int = 0,
    starforce: int = 0,
    union_level: int = 0,
) -> Dict[str, Any]:
    """Compare character stats with one DB-backed boss requirement row."""

    boss = _fetch_boss_requirements(target_boss)
    return _analyze_boss_row(
        boss,
        character_name=character_name,
        job_name=job_name,
        level=level,
        target_boss=target_boss,
        combat_power=combat_power,
        main_stat=main_stat,
        attack_power=attack_power,
        magic_power=magic_power,
        boss_damage=boss_damage,
        ignore_def=ignore_def,
        crit_rate=crit_rate,
        crit_damage=crit_damage,
        final_damage=final_damage,
        arcane_force=arcane_force,
        authentic_force=authentic_force,
        starforce=starforce,
        union_level=union_level,
    )


@tool(args_schema=AvailableBossesInput)
def find_available_bosses(
    character_name: str,
    job_name: str,
    level: int,
    combat_power: int,
    main_stat: int,
    attack_power: int = 0,
    magic_power: int = 0,
    boss_damage: float = 0.0,
    ignore_def: float = 0.0,
    crit_rate: float = 0.0,
    crit_damage: float = 0.0,
    final_damage: float = 0.0,
    arcane_force: int = 0,
    authentic_force: int = 0,
    starforce: int = 0,
    union_level: int = 0,
    include_risky: bool = True,
    max_results: int = 20,
) -> Dict[str, Any]:
    """Find all bosses whose DB requirements fit the current character specs."""

    bosses = _fetch_all_boss_requirements()
    analyses = [
        _analyze_boss_row(
            boss,
            character_name=character_name,
            job_name=job_name,
            level=level,
            target_boss=str(boss.get("boss_name", "")),
            combat_power=combat_power,
            main_stat=main_stat,
            attack_power=attack_power,
            magic_power=magic_power,
            boss_damage=boss_damage,
            ignore_def=ignore_def,
            crit_rate=crit_rate,
            crit_damage=crit_damage,
            final_damage=final_damage,
            arcane_force=arcane_force,
            authentic_force=authentic_force,
            starforce=starforce,
            union_level=union_level,
        )
        for boss in bosses
    ]

    grouped: Dict[str, List[Dict[str, Any]]] = {
        "recommended": [],
        "challengeable": [],
        "risky": [],
        "difficult": [],
    }
    for analysis in analyses:
        grouped[analysis["clear_status"]].append(
            {
                "boss_name": analysis["target_boss"],
                "difficulty": analysis["difficulty"],
                "challenge_fit_score": analysis["challenge_fit_score"],
                "lacking_stats": analysis["lacking_stats"],
                "top_bottlenecks": analysis["recommended_actions"][:3],
            }
        )

    for status, items in grouped.items():
        reverse = status in {"recommended", "challengeable"}
        items.sort(key=lambda item: item["challenge_fit_score"], reverse=reverse)
        grouped[status] = items[:max_results]

    available = grouped["recommended"] + grouped["challengeable"]
    if include_risky:
        available += grouped["risky"]

    recommended_actions = [
        {
            "category": "BOSS_CHALLENGE",
            "target": item["boss_name"],
            "priority": 1 if item in grouped["recommended"] else 2,
            "expected_cp_gain": 0,
            "description": (
                f"{item['boss_name']} is classified as a "
                f"{'recommended' if item in grouped['recommended'] else 'challengeable'} boss target."
            ),
        }
        for item in (grouped["recommended"] + grouped["challengeable"])[:max_results]
    ]
    best_score = 0.0
    if available:
        best_score = max(item["challenge_fit_score"] for item in available)

    return {
        "character_name": character_name,
        "job_name": job_name,
        "available_bosses": available[:max_results],
        "boss_groups": grouped,
        "recommended_actions": recommended_actions,
        "challenge_fit_score": best_score,
        "summary": {
            "recommended_count": len(grouped["recommended"]),
            "challengeable_count": len(grouped["challengeable"]),
            "risky_count": len(grouped["risky"]),
            "difficult_count": len(grouped["difficult"]),
            "total_bosses_checked": len(analyses),
        },
        "data_reliability": "boss_requirements_from_neo4j",
    }


def _extract_agent_input(state: "AgentState", target_boss: Optional[str]) -> Dict[str, Any]:
    profile = _value(state, "character_profile", {})
    stats = _value(profile, "final_stats") or _value(state, "character_stats", {})
    union_status = _value(state, "union_status") or _value(profile, "union_info", {})
    equipment_items = _value(state, "equipment_items", _value(profile, "equipment_list", []))

    return {
        "character_name": _value(profile, "character_name", _value(state, "character_name", "")),
        "job_name": _value(profile, "job_name", ""),
        "level": int(_number(profile, "level", 0)),
        "target_boss": _target_boss_from_state(state, target_boss),
        "combat_power": int(_number(stats, "combat_power", 0)),
        "main_stat": int(
            max(
                _number(stats, "str_val"),
                _number(stats, "dex"),
                _number(stats, "int_val"),
                _number(stats, "luk"),
            )
        ),
        "attack_power": int(_number(stats, "attack_power", 0)),
        "magic_power": int(_number(stats, "magic_power", 0)),
        "boss_damage": _number(stats, "boss_damage", 0),
        "ignore_def": _number(stats, "ignore_def", 0),
        "crit_rate": _number(stats, "crit_rate", 0),
        "crit_damage": _number(stats, "crit_damage", 0),
        "final_damage": _number(stats, "final_damage", 0),
        "arcane_force": int(_number(stats, "arcane_force", 0)),
        "authentic_force": int(_number(stats, "authentic_force", 0)),
        "starforce": int(_number(stats, "starforce", _sum_equipment_starforce(equipment_items))),
        "union_level": int(_number(union_status, "union_level", 0)),
    }


def _extract_available_bosses_input(
    state: "AgentState",
    *,
    include_risky: bool = True,
    max_results: int = 20,
) -> Dict[str, Any]:
    tool_input = _extract_character_input(state)
    tool_input["include_risky"] = include_risky
    tool_input["max_results"] = max_results
    return tool_input


def _extract_character_input(state: "AgentState") -> Dict[str, Any]:
    profile = _value(state, "character_profile", {})
    stats = _value(profile, "final_stats") or _value(state, "character_stats", {})
    union_status = _value(state, "union_status") or _value(profile, "union_info", {})
    equipment_items = _value(state, "equipment_items", _value(profile, "equipment_list", []))

    return {
        "character_name": _value(profile, "character_name", _value(state, "character_name", "")),
        "job_name": _value(profile, "job_name", ""),
        "level": int(_number(profile, "level", 0)),
        "combat_power": int(_number(stats, "combat_power", 0)),
        "main_stat": int(
            max(
                _number(stats, "str_val"),
                _number(stats, "dex"),
                _number(stats, "int_val"),
                _number(stats, "luk"),
            )
        ),
        "attack_power": int(_number(stats, "attack_power", 0)),
        "magic_power": int(_number(stats, "magic_power", 0)),
        "boss_damage": _number(stats, "boss_damage", 0),
        "ignore_def": _number(stats, "ignore_def", 0),
        "crit_rate": _number(stats, "crit_rate", 0),
        "crit_damage": _number(stats, "crit_damage", 0),
        "final_damage": _number(stats, "final_damage", 0),
        "arcane_force": int(_number(stats, "arcane_force", 0)),
        "authentic_force": int(_number(stats, "authentic_force", 0)),
        "starforce": int(_number(stats, "starforce", _sum_equipment_starforce(equipment_items))),
        "union_level": int(_number(union_status, "union_level", 0)),
    }


def run_analystic(
    state: "AgentState",
    *,
    boss_graph_connection: Any = None,
    boss_db_connection: Any = None,
    target_boss: Optional[str] = None,
) -> "AgentState":
    """Run the common.state-compatible analystic step.

    This function intentionally reads raw character fields only. It does not consume
    calculator-owned stat_summary or equipment_summary values.
    """

    if boss_graph_connection is not None:
        set_boss_neo4j_connection(boss_graph_connection)
    elif boss_db_connection is not None:
        set_boss_db_connection(boss_db_connection)

    if _has_target_boss(state, target_boss):
        tool_input = _extract_agent_input(state, target_boss)
        result = analyze_boss_readiness.invoke(tool_input)
    else:
        tool_input = _extract_available_bosses_input(state)
        result = find_available_bosses.invoke(tool_input)

    growth_report = {
        "character_id": _value(state, "ocid", tool_input["character_name"]),
        "current_combat_power": tool_input["combat_power"],
        "attack": max(tool_input["attack_power"], tool_input["magic_power"]),
        "boss_damage": tool_input["boss_damage"],
        "ignore_def": tool_input["ignore_def"],
        "crit_rate": tool_input["crit_rate"],
        "crit_damage": tool_input["crit_damage"],
        "damage": _number(_value(_value(state, "character_profile", {}), "final_stats", {}), "damage", 0),
        "bottleneck_analysis": result.get("bottleneck_analysis", {}),
        "recommended_actions": result.get("recommended_actions", result.get("available_bosses", [])),
        "boss_clear_prediction": result.get("boss_clear_prediction", {}),
        "data_reliability": result["data_reliability"],
        "timestamp": "",
    }

    new_state = dict(state)
    new_state["tool_results"] = {**new_state.get("tool_results", {}), "analystic": result}
    new_state["bottleneck_analysis"] = result.get("bottleneck_analysis", {})
    new_state["growth_report"] = growth_report
    new_state["recommended_actions"] = growth_report["recommended_actions"]
    new_state["confidence_score"] = result.get("challenge_fit_score", 0.0)

    if validate_agent_outputs is not None:
        validate_agent_outputs("analystic", new_state)
    return new_state


ANALYTICS_TOOLS = [analyze_boss_readiness, find_available_bosses]

ANALYTICS_SYSTEM_PROMPT = f"""
{master_prompt}

You are the MapleStory analystic agent for boss readiness.
Use analyze_boss_readiness when the user asks about one target boss.
Use find_available_bosses when the user asks which bosses are possible.
Explain the result in Korean.

Rules:
- Use boss requirement data from the configured Neo4j graph connection.
- Produce growth_report and recommended_actions without depending on calculator output.
- State whether the character is difficult, risky, challengeable, or recommended.
- Explain the strongest bottlenecks first.
- Do not invent boss requirements when the Neo4j connection or boss row is missing.
""".strip()


def create_analytics_agent(
    model: str | BaseChatModel | None = None,
    *,
    boss_graph_connection: Any = None,
    boss_db_connection: Any = None,
    name: str = "analystic_agent",
    state: AgentState) -> Any:
    """Create the analystic agent with common.get_model and Neo4j-backed tools."""
    question=state['user_query']   
    if boss_graph_connection is not None:
        set_boss_neo4j_connection(boss_graph_connection)
    elif boss_db_connection is not None:
        set_boss_db_connection(boss_db_connection)
    if model is None:
        model = get_llm() if get_llm is not None else "openai:gpt-4o-mini"

    analytics_agent=create_agent(
        model=model,
        tools=ANALYTICS_TOOLS,
        system_prompt=ANALYTICS_SYSTEM_PROMPT,
        name=name,
    )
    result = analytics_agent.invoke(
    {"messages": HumanMessage(content=question)}
        )
    analysis=result['messages'][-1].content

    return  {
        "question": question,
        "analysis": analysis
    }


__all__ = [
    "ANALYTICS_SYSTEM_PROMPT",
    "ANALYTICS_TOOLS",
    "AvailableBossesInput",
    "BossStatAnalysisInput",
    "analyze_boss_readiness",
    "create_analytic_agent",
    "create_analytics_agent",
    "create_analystic_agent",
    "find_available_bosses",
    "run_analystic",
    "set_boss_db_connection",
    "set_boss_neo4j_connection",
]
