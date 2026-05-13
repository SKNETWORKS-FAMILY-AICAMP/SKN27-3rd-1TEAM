from __future__ import annotations
import os
import json
import re
import sys
from datetime import datetime

current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(current_dir, "../../"))
sys.path.append(project_root)

from pathlib import Path
from typing import Any, Dict, List, Optional
from dotenv import load_dotenv


from langchain.agents import create_agent
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage
from langchain_core.tools import tool
from pydantic import BaseModel, Field
from neo4j import GraphDatabase
from common.get_model import get_llm
from common.prompt import master_prompt
from common.validator import validate_agent_inputs, validate_agent_outputs
from common.state import AgentState

load_dotenv()

_BOSS_GRAPH_CONNECTION: Any = None
_BOSS_GRAPH_DATABASE: Optional[str] = None

_BOSS_DIFFICULTY_KO = {
    "EASY": "이지",
    "NORMAL": "노멀",
    "HARD": "하드",
    "CHAOS": "카오스",
    "EXTREME": "익스트림",
    "이지": "이지",
    "노말": "노멀",
    "노멀": "노멀",
    "하드": "하드",
    "카오스": "카오스",
    "익스트림": "익스트림",
}

_CHARACTER_NUMBER_FIELDS = {
    "combat_power": (("combat_power", "current_combat_power"), int),
    "attack_power": (("attack_power", "attack"), int),
    "magic_power": (("magic_power",), int),
    "boss_damage": (("boss_damage",), float),
    "ignore_def": (("ignore_def", "ignore_defense", "ied"), float),
    "crit_rate": (("crit_rate", "critical_rate"), float),
    "crit_damage": (("crit_damage", "critical_damage"), float),
    "final_damage": (("final_damage",), float),
    "arcane_force": (("arcane_force",), int),
    "authentic_force": (("authentic_force", "sacred_force"), int),
}

_BOSS_STAT_RULES = (
    ("level", "required_level", "Character level is below the boss baseline."),
    ("combat_power", "required_combat_power", "Combat power is below the boss requirement."),
    ("main_stat", "required_main_stat", "Primary stat is insufficient."),
    ("attack_or_magic", None, "Attack or magic power is below the boss baseline."),
    ("boss_damage", "required_boss_damage", "Boss damage is insufficient."),
    ("ignore_def", "required_ignore_def", "Ignore defense is insufficient."),
    ("crit_rate", "required_crit_rate", "Critical rate is insufficient."),
    ("crit_damage", "required_crit_damage", "Critical damage is insufficient."),
    ("final_damage", "required_final_damage", "Final damage is insufficient."),
    ("force", None, "Arcane or authentic force is insufficient."),
    ("starforce", "required_starforce", "Starforce is below the baseline."),
    ("union_level", "required_union_level", "Union level is below the baseline."),
)

_BOSS_STATUSES = ("recommended", "challengeable", "risky", "difficult")


class CharacterStatsInput(BaseModel):
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


class BossStatAnalysisInput(CharacterStatsInput):
    target_boss: str = Field(..., description="Target boss name.")


class AvailableBossesInput(CharacterStatsInput):
    include_risky: bool = Field(True, description="Whether to include risky bosses in the returned list.")
    max_results: int = Field(20, ge=1, le=100, description="Maximum number of bosses to return per group.")


def _load_project_env() -> None:
    project_root = Path(__file__).resolve().parents[2]
    for env_path in (
        project_root / ".env",
        project_root / "database" / ".env",
        Path(__file__).resolve().parent / ".env",
    ):
        load_dotenv(env_path, override=False)


def set_boss_neo4j_connection(connection: Any, database: Optional[str] = None) -> None:
    global _BOSS_GRAPH_CONNECTION, _BOSS_GRAPH_DATABASE
    _BOSS_GRAPH_CONNECTION = connection
    if database is not None:
        _BOSS_GRAPH_DATABASE = database


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
    return [_record_to_dict(record) for record in result]


def _run_neo4j_query(query: str, params: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    params = params or {}
    connection = _get_boss_neo4j_connection()

    if hasattr(connection, "query"):
        try:
            return _result_to_rows(connection.query(query, params=params))
        except TypeError:
            return _result_to_rows(connection.query(query, params))

    if hasattr(connection, "execute_query"):
        try:
            kwargs = {"parameters_": params}
            if _BOSS_GRAPH_DATABASE:
                kwargs["database_"] = _BOSS_GRAPH_DATABASE
            return _result_to_rows(connection.execute_query(query, **kwargs))
        except TypeError:
            return _result_to_rows(connection.execute_query(query, params))

    if hasattr(connection, "session"):
        session_kwargs = {"database": _BOSS_GRAPH_DATABASE} if _BOSS_GRAPH_DATABASE else {}
        with connection.session(**session_kwargs) as session:
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
        "노말": "NORMAL",
        "normal": "NORMAL",
        "하드": "HARD",
        "hard": "HARD",
        "카오스": "CHAOS",
        "chaos": "CHAOS",
        "익스트림": "EXTREME",
        "extreme": "EXTREME",
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
        "difficulty_ko": _BOSS_DIFFICULTY_KO.get(difficulty) if difficulty else None,
    }


def _boss_difficulty_ko(value: Any) -> Optional[str]:
    text = str(value or "").strip()
    if not text:
        return None
    return _BOSS_DIFFICULTY_KO.get(text.upper()) or _BOSS_DIFFICULTY_KO.get(text)


def _normalize_boss_lookup_text(value: Any) -> str:
    text = str(value or "").lower()
    text = text.replace("노말", "노멀")
    text = re.sub(r"[^0-9a-z가-힣]+", "", text)
    return text.replace("의", "")


_BOSS_NAME_ALIASES = {
    "자쿰": "Zakum",
    "매그너스": "Magnus",
    "힐라": "Hilla",
    "카웅": "Kaung",
    "파풀라투스": "Papulatus",
    "파풀": "Papulatus",
    "반반": "Van von",
    "피에르": "Pierre",
    "블러디 퀸": "Bloody Queen",
    "블러디퀸": "Bloody Queen",
    "벨룸": "Vellum",
    "반 레온": "Von Leon",
    "반레온": "Von Leon",
    "혼테일": "Horntail",
    "아카이럼": "Akayrum",
    "핑크빈": "Pink Bean",
    "시그너스": "Cygnus",
    "스우": "Lotus",
    "데미안": "Damien",
    "가디언 엔젤 슬라임": "Guardian Angel Slime",
    "가엔슬": "Guardian Angel Slime",
    "루시드": "Lucid",
    "윌": "Will",
    "더스크": "Dusk",
    "진 힐라": "Verus Hilla",
    "진힐라": "Verus Hilla",
    "듄켈": "Dunkel",
    "검은 마법사": "Black Mage",
    "검마": "Black Mage",
    "선택받은 세렌": "Chosen Seren",
    "세렌": "Chosen Seren",
    "감시자 칼로스": "Kalos the Guardian",
    "칼로스": "Kalos the Guardian",
    "최초의 대적자": "First Adversary",
    "최초 대적자": "First Adversary",
    "대적자": "First Adversary",
    "카링": "Kaling",
    "찬란한 흉성": "Radiant Malefic",
    "흉성": "Radiant Malefic",
    "림보": "Limbo",
    "발드릭스": "Baldrix",
    "유피테르": "Jupiter",
}


def _alias_boss_target_to_neo4j_name(target_boss: str) -> str:
    target = _parse_boss_target(target_boss)
    lookup_values = {
        _normalize_boss_lookup_text(target["target_boss"]),
        _normalize_boss_lookup_text(target["base_boss"]),
    }

    matched_alias = ""
    matched_boss = ""
    for alias, neo4j_boss_name in _BOSS_NAME_ALIASES.items():
        alias_key = _normalize_boss_lookup_text(alias)
        if not alias_key:
            continue
        if any(alias_key == value or alias_key in value for value in lookup_values if value):
            if len(alias_key) > len(matched_alias):
                matched_alias = alias_key
                matched_boss = neo4j_boss_name

    if not matched_boss:
        return target_boss
    if target["difficulty_ko"]:
        return f"{target['difficulty_ko']} {matched_boss}"
    return matched_boss


def _boss_lookup_candidates(row: Dict[str, Any]) -> List[str]:
    boss_name = str(_value(row, "boss_name", "") or "")
    difficulty_ko = _boss_difficulty_ko(_value(row, "difficulty"))
    candidates = [boss_name]
    if difficulty_ko and boss_name:
        if not _normalize_boss_lookup_text(boss_name).startswith(_normalize_boss_lookup_text(difficulty_ko)):
            candidates.append(f"{difficulty_ko} {boss_name}")
    return [candidate for candidate in candidates if candidate]


def _boss_lookup_score(target_boss: str, row: Dict[str, Any]) -> float:
    target = _parse_boss_target(target_boss)
    requested_candidates = [target["target_boss"], target["base_boss"]]
    if target["difficulty_ko"] and target["base_boss"]:
        requested_candidates.append(f"{target['difficulty_ko']} {target['base_boss']}")

    requested_values = {
        _normalize_boss_lookup_text(candidate)
        for candidate in requested_candidates
        if candidate
    }
    candidate_values = {
        _normalize_boss_lookup_text(candidate)
        for candidate in _boss_lookup_candidates(row)
        if candidate
    }

    score = 0.0
    for requested in requested_values:
        for candidate in candidate_values:
            if not requested or not candidate:
                continue
            if requested == candidate:
                score = max(score, 100.0)
            elif requested in candidate or candidate in requested:
                score = max(score, 75.0 + min(len(requested), len(candidate)) / max(len(requested), len(candidate)) * 15)
            else:
                overlap = len(set(requested) & set(candidate))
                union = len(set(requested) | set(candidate))
                if union:
                    score = max(score, overlap / union * 60)

    target_difficulty = target["difficulty_ko"]
    row_difficulty = _boss_difficulty_ko(_value(row, "difficulty"))
    if target_difficulty and row_difficulty == target_difficulty:
        score += 10
    elif target_difficulty and row_difficulty and row_difficulty != target_difficulty:
        score -= 20
    return score


def _resolve_boss_target_from_neo4j(target_boss: str) -> str:
    try:
        rows = _query_all_boss_requirements()
    except Exception:
        return target_boss

    best_row: Dict[str, Any] = {}
    best_score = 0.0
    for row in rows:
        score = _boss_lookup_score(target_boss, row)
        if score > best_score:
            best_row = row
            best_score = score

    if not best_row or best_score < 75:
        return _alias_boss_target_to_neo4j_name(target_boss)

    target = _parse_boss_target(target_boss)
    boss_name = str(_value(best_row, "boss_name", "") or target_boss)
    difficulty_ko = target["difficulty_ko"] or _boss_difficulty_ko(_value(best_row, "difficulty"))
    if difficulty_ko and not _normalize_boss_lookup_text(boss_name).startswith(_normalize_boss_lookup_text(difficulty_ko)):
        return f"{difficulty_ko} {boss_name}"
    return boss_name


def _clean_boss_requirement_row(row: Dict[str, Any]) -> Dict[str, Any]:
    boss_name = _value(row, "boss_name") or _value(row, "name")
    if not boss_name:
        return {}

    requirement_keys = (
        "required_level",
        "required_combat_power",
        "required_main_stat",
        "required_attack_power",
        "required_magic_power",
        "required_boss_damage",
        "required_ignore_def",
        "required_crit_rate",
        "required_crit_damage",
        "required_final_damage",
        "required_arcane_force",
        "required_authentic_force",
        "required_starforce",
        "required_union_level",
    )
    if not any(_value(row, key) not in {None, ""} for key in requirement_keys):
        return {}

    cleaned = {"boss_name": boss_name, "difficulty": _value(row, "difficulty")}
    cleaned.update({key: _value(row, key) for key in requirement_keys})
    cleaned.update({key: _value(row, key) for key in ("source_name", "source_url", "reliability")})
    return {key: value for key, value in cleaned.items() if value is not None}


BOSS_REQUIREMENT_RETURN = """
RETURN
    coalesce(row_boss_name, "") AS boss_name,
    row_difficulty AS difficulty,
    coalesce(n.required_level, n.level, n.monster_level, n.entry_level) AS required_level,
    coalesce(n.required_combat_power, n.combat_power_cut, n.min_combat_power) AS required_combat_power,
    coalesce(n.required_main_stat, n.main_stat, n.main_stat_cut, n.min_main_stat) AS required_main_stat,
    coalesce(n.required_attack_power, n.attack_power_cut, n.min_attack_power) AS required_attack_power,
    coalesce(n.required_magic_power, n.magic_power_cut, n.min_magic_power) AS required_magic_power,
    coalesce(n.required_boss_damage, n.boss_damage, n.boss_damage_cut, n.min_boss_damage) AS required_boss_damage,
    coalesce(n.required_ignore_def, n.ignore_def, n.ignore_def_cut, n.ied_cut, n.min_ignore_def) AS required_ignore_def,
    coalesce(n.required_crit_rate, n.crit_rate_cut, n.min_crit_rate) AS required_crit_rate,
    coalesce(n.required_crit_damage, n.crit_damage_cut, n.min_crit_damage) AS required_crit_damage,
    coalesce(n.required_final_damage, n.final_damage_cut, n.min_final_damage) AS required_final_damage,
    coalesce(n.required_arcane_force, n.arcane_force, n.arcane_force_cut) AS required_arcane_force,
    coalesce(n.required_authentic_force, n.authentic_force, n.authentic_force_cut) AS required_authentic_force,
    coalesce(n.required_starforce, n.starforce_cut, n.starforce) AS required_starforce,
    coalesce(n.required_union_level, n.union_level_cut, n.union_level) AS required_union_level,
    coalesce(n.source_name, n.source, n.confidence) AS source_name,
    n.source_url AS source_url,
    coalesce(n.reliability, n.confidence) AS reliability
"""


STAT_REQUIREMENT_RETURN = """
WITH
    b,
    req,
    row_boss_name,
    row_difficulty,
    max(CASE WHEN stat.code = "COMBAT_POWER" OR stat.domain_field = "combat_power" THEN rel.value END) AS stat_combat_power,
    max(CASE WHEN stat.domain_field IN ["str_val", "dex", "int_val", "luk"] THEN rel.value END) AS stat_main_stat,
    max(CASE WHEN stat.code = "ATTACK_POWER" OR stat.domain_field = "attack_power" THEN rel.value END) AS stat_attack_power,
    max(CASE WHEN stat.code = "MAGIC_POWER" OR stat.domain_field = "magic_power" THEN rel.value END) AS stat_magic_power,
    max(CASE WHEN stat.code = "BOSS_DAMAGE" OR stat.domain_field = "boss_damage" THEN rel.value END) AS stat_boss_damage,
    max(CASE WHEN stat.code = "IGNORE_DEF" OR stat.domain_field = "ignore_def" THEN rel.value END) AS stat_ignore_def,
    max(CASE WHEN stat.code = "CRIT_RATE" OR stat.domain_field = "crit_rate" THEN rel.value END) AS stat_crit_rate,
    max(CASE WHEN stat.code = "CRIT_DAMAGE" OR stat.domain_field = "crit_damage" THEN rel.value END) AS stat_crit_damage,
    max(CASE WHEN stat.code = "FINAL_DAMAGE" OR stat.domain_field = "final_damage" THEN rel.value END) AS stat_final_damage,
    max(CASE WHEN stat.code = "ARCANE_FORCE" OR stat.domain_field = "arcane_force" THEN rel.value END) AS stat_arcane_force,
    max(CASE WHEN stat.code = "AUTHENTIC_FORCE" OR stat.domain_field = "authentic_force" THEN rel.value END) AS stat_authentic_force,
    max(CASE WHEN stat.code = "STARFORCE" OR stat.domain_field = "starforce" THEN rel.value END) AS stat_starforce,
    max(CASE WHEN stat.code = "UNION_LEVEL" OR stat.domain_field = "union_level" THEN rel.value END) AS stat_union_level
RETURN
    row_boss_name AS boss_name,
    row_difficulty AS difficulty,
    coalesce(req.level, b.required_level) AS required_level,
    stat_combat_power AS required_combat_power,
    coalesce(req.main_stat, stat_main_stat) AS required_main_stat,
    stat_attack_power AS required_attack_power,
    stat_magic_power AS required_magic_power,
    coalesce(req.boss_damage, stat_boss_damage) AS required_boss_damage,
    coalesce(req.ignore_def, stat_ignore_def) AS required_ignore_def,
    stat_crit_rate AS required_crit_rate,
    stat_crit_damage AS required_crit_damage,
    stat_final_damage AS required_final_damage,
    coalesce(req.arcane_force, stat_arcane_force) AS required_arcane_force,
    coalesce(req.authentic_force, stat_authentic_force) AS required_authentic_force,
    stat_starforce AS required_starforce,
    stat_union_level AS required_union_level,
    req.confidence AS reliability,
    "neo4j_stat_requirement" AS source_name,
    null AS source_url
"""


def _query_boss_requirements(target_boss: str) -> Dict[str, Any]:
    resolved_target_boss = _resolve_boss_target_from_neo4j(target_boss)
    target = _parse_boss_target(resolved_target_boss)
    params = {
        "target_boss": target["target_boss"],
        "base_boss": target["base_boss"],
        "difficulty": target["difficulty"],
        "difficulty_ko": target["difficulty_ko"],
    }

    queries = (
        f"""
        MATCH (b:Boss)-[:HAS_REQUIREMENT]->(req:StatRequirement)
        WITH
            b,
            req,
            coalesce(b.name, req.boss_name) AS row_boss_name,
            coalesce(b.difficulty, req.difficulty) AS row_difficulty
        WHERE
            toLower(toString(row_boss_name)) = toLower($target_boss)
            OR toLower(toString(row_boss_name)) = toLower($base_boss)
            OR toLower(toString(coalesce(req.boss_name, ""))) = toLower($target_boss)
            OR toLower(toString(coalesce(req.boss_name, ""))) = toLower($base_boss)
        WITH b, req, row_boss_name, row_difficulty
        WHERE
            $difficulty IS NULL
            OR toLower(toString(row_boss_name)) = toLower($target_boss)
            OR toUpper(toString(row_difficulty)) = $difficulty
            OR row_difficulty = $difficulty_ko
        OPTIONAL MATCH (req)-[rel:REQUIRES_STAT]->(stat:StatType)
        WITH b, req, row_boss_name, row_difficulty, rel, stat
        {STAT_REQUIREMENT_RETURN}
        ORDER BY
            CASE WHEN toLower(toString(boss_name)) = toLower($target_boss) THEN 0 ELSE 1 END,
            coalesce(required_combat_power, required_main_stat, 0) DESC
        LIMIT 1
        """,
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


def _query_all_boss_requirements() -> List[Dict[str, Any]]:
    queries = (
        f"""
        MATCH (b:Boss)-[:HAS_REQUIREMENT]->(req:StatRequirement)
        WITH
            b,
            req,
            coalesce(b.name, req.boss_name) AS row_boss_name,
            coalesce(b.difficulty, req.difficulty) AS row_difficulty
        OPTIONAL MATCH (req)-[rel:REQUIRES_STAT]->(stat:StatType)
        WITH b, req, row_boss_name, row_difficulty, rel, stat
        {STAT_REQUIREMENT_RETURN}
        ORDER BY coalesce(required_combat_power, required_main_stat, 0) ASC, coalesce(required_level, 0) ASC
        """,
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


_BOSS_PRIORITY_PROFILES = {
    "early": {
        "weights": {
            "combat_power": 0.42,
            "main_stat": 0.22,
            "attack_or_magic": 0.10,
            "boss_damage": 0.06,
            "ignore_def": 0.05,
            "crit_rate": 0.04,
            "crit_damage": 0.04,
            "final_damage": 0.02,
            "force": 0.01,
            "level": 0.04,
            "starforce": 0.01,
            "union_level": 0.00,
        },
        "thresholds": {"recommended": 1.08, "challengeable": 0.82, "risky": 0.62},
        "hard_gates": {"level": 0.88, "force": 0.55, "ignore_def": 0.55, "combat_power": 0.50},
        "critical_stats": ["level", "combat_power", "main_stat"],
    },
    "mid": {
        "weights": {
            "combat_power": 0.34,
            "main_stat": 0.20,
            "attack_or_magic": 0.08,
            "boss_damage": 0.10,
            "ignore_def": 0.10,
            "crit_rate": 0.03,
            "crit_damage": 0.05,
            "final_damage": 0.05,
            "force": 0.05,
            "level": 0.03,
            "starforce": 0.01,
            "union_level": 0.00,
        },
        "thresholds": {"recommended": 1.10, "challengeable": 0.85, "risky": 0.68},
        "hard_gates": {"level": 0.90, "force": 0.65, "ignore_def": 0.68, "combat_power": 0.58},
        "critical_stats": ["level", "combat_power", "main_stat", "force", "ignore_def"],
    },
    "late": {
        "weights": {
            "combat_power": 0.28,
            "main_stat": 0.16,
            "attack_or_magic": 0.07,
            "boss_damage": 0.13,
            "ignore_def": 0.14,
            "crit_rate": 0.02,
            "crit_damage": 0.06,
            "final_damage": 0.08,
            "force": 0.10,
            "level": 0.03,
            "starforce": 0.01,
            "union_level": 0.00,
        },
        "thresholds": {"recommended": 1.12, "challengeable": 0.88, "risky": 0.74},
        "hard_gates": {"level": 0.92, "force": 0.75, "ignore_def": 0.78, "combat_power": 0.62},
        "critical_stats": ["level", "combat_power", "main_stat", "force", "ignore_def", "boss_damage"],
    },
    "endgame": {
        "weights": {
            "combat_power": 0.24,
            "main_stat": 0.13,
            "attack_or_magic": 0.06,
            "boss_damage": 0.14,
            "ignore_def": 0.16,
            "crit_rate": 0.01,
            "crit_damage": 0.06,
            "final_damage": 0.09,
            "force": 0.15,
            "level": 0.04,
            "starforce": 0.01,
            "union_level": 0.00,
        },
        "thresholds": {"recommended": 1.15, "challengeable": 0.90, "risky": 0.80},
        "hard_gates": {"level": 0.94, "force": 0.82, "ignore_def": 0.84, "combat_power": 0.65},
        "critical_stats": ["level", "combat_power", "main_stat", "force", "ignore_def", "boss_damage", "final_damage"],
    },
}

_LATE_BOSS_KEYS = {
    _normalize_boss_lookup_text(name)
    for name in (
        "Lucid",
        "Will",
        "Verus Hilla",
        "Black Mage",
        "Chosen Seren",
        "Kalos the Guardian",
        "Dusk",
        "Dunkel",
    )
}

_ENDGAME_BOSS_KEYS = {
    _normalize_boss_lookup_text(name)
    for name in (
        "Black Mage",
        "Chosen Seren",
        "Kalos the Guardian",
        "First Adversary",
        "Kaling",
        "Radiant Malefic",
        "Limbo",
        "Baldrix",
        "Jupiter",
    )
}


_VERY_HIGH_MECHANIC_BOSS_KEYS = {
    _normalize_boss_lookup_text(name)
    for name in (
        "Lucid",
        "Will",
        "Verus Hilla",
        "Black Mage",
        "하드 루시드",
        "하드 윌",
        "진 힐라",
        "검은 마법사",
    )
}


def _boss_priority_tier(boss: Dict[str, Any], required_values: Dict[str, float]) -> str:
    boss_name_key = _normalize_boss_lookup_text(_value(boss, "boss_name", ""))
    required_level = _number(required_values, "level")
    required_force = _number(required_values, "force")
    required_ignore_def = _number(required_values, "ignore_def")
    required_main_stat = _number(required_values, "main_stat")
    required_authentic_force = _number(required_values, "authentic_force")

    if (
        any(key and key in boss_name_key for key in _ENDGAME_BOSS_KEYS)
        or required_level >= 275
        or required_main_stat >= 110000
        or required_authentic_force > 0
    ):
        return "endgame"
    if (
        any(key and key in boss_name_key for key in _LATE_BOSS_KEYS)
        or required_level >= 250
        or required_force >= 200
        or required_ignore_def >= 90
    ):
        return "late"
    if required_level >= 220 or required_force > 0:
        return "mid"
    return "early"


def _boss_priority_profile(boss: Dict[str, Any], required_values: Dict[str, float]) -> Dict[str, Any]:
    tier = _boss_priority_tier(boss, required_values)
    base_profile = _BOSS_PRIORITY_PROFILES[tier]
    weights = dict(base_profile["weights"])
    required_force = _number(required_values, "force")
    required_ignore_def = _number(required_values, "ignore_def")
    required_combat_power = _number(required_values, "combat_power")
    required_main_stat = _number(required_values, "main_stat")
    boss_name_key = _normalize_boss_lookup_text(_value(boss, "boss_name", ""))
    thresholds = dict(base_profile["thresholds"])
    hard_gates = dict(base_profile["hard_gates"])
    critical_stats = list(base_profile["critical_stats"])

    if required_combat_power <= 0:
        weights["combat_power"] = 0.0
        weights["main_stat"] += 0.12
        weights["attack_or_magic"] += 0.04
    if required_force > 0:
        weights["force"] += 0.04
        weights["combat_power"] = max(0.0, weights["combat_power"] - 0.02)
    if required_ignore_def >= 90:
        weights["ignore_def"] += 0.04
        weights["combat_power"] = max(0.0, weights["combat_power"] - 0.02)
    elif required_ignore_def > 0:
        weights["ignore_def"] += 0.02
    if required_main_stat >= 50000:
        weights["main_stat"] += 0.04
        weights["attack_or_magic"] = max(0.0, weights["attack_or_magic"] - 0.01)
    if any(key and key in boss_name_key for key in _VERY_HIGH_MECHANIC_BOSS_KEYS):
        thresholds["recommended"] += 0.03
        thresholds["challengeable"] += 0.02
        weights["boss_damage"] += 0.02
        weights["ignore_def"] += 0.02
        if "boss_damage" not in critical_stats:
            critical_stats.append("boss_damage")

    return {
        "tier": tier,
        "weights": {key: round(max(0.0, value), 4) for key, value in weights.items()},
        "thresholds": {key: round(value, 4) for key, value in thresholds.items()},
        "hard_gates": hard_gates,
        "critical_stats": critical_stats,
    }


def _boss_clear_score(
    ratios: Dict[str, float],
    required_values: Optional[Dict[str, float]] = None,
    priority_profile: Optional[Dict[str, Any]] = None,
) -> float:
    weights = priority_profile["weights"] if priority_profile else {
        "combat_power": 0.42,
        "main_stat": 0.12,
        "attack_or_magic": 0.08,
        "boss_damage": 0.08,
        "ignore_def": 0.06,
        "crit_rate": 0.03,
        "crit_damage": 0.04,
        "final_damage": 0.05,
        "force": 0.06,
        "level": 0.04,
        "starforce": 0.01,
        "union_level": 0.01,
    }
    active_weights = {
        key: weight
        for key, weight in weights.items()
        if required_values is None or _number(required_values, key) > 0
    }
    if not active_weights:
        active_weights = weights

    total_weight = sum(active_weights.values())
    score = sum(
        min(1.2, ratios.get(key, 1.0)) * weight
        for key, weight in active_weights.items()
    ) / total_weight
    return round(score, 4)


def _status(
    score: float,
    bottlenecks: List[Dict[str, Any]],
    checks: Dict[str, float],
    required_values: Dict[str, float],
    priority_profile: Dict[str, Any],
) -> str:
    hard_gates = priority_profile["hard_gates"]
    thresholds = priority_profile["thresholds"]
    critical_stats = set(priority_profile["critical_stats"])

    if _number(required_values, "level") > 0 and checks.get("level", 1.0) < hard_gates["level"]:
        return "difficult"
    if _number(required_values, "force") > 0 and checks.get("force", 1.0) < hard_gates["force"]:
        return "difficult"
    if _number(required_values, "combat_power") > 0 and checks.get("combat_power", 1.0) < hard_gates["combat_power"]:
        return "difficult"
    if _number(required_values, "ignore_def") > 0 and checks.get("ignore_def", 1.0) < hard_gates["ignore_def"]:
        return "difficult"

    severe_bottleneck = any(
        item["stat"] in critical_stats
        and item["stat"] != "level"
        and item["ratio"] < hard_gates.get(item["stat"], 0.60)
        for item in bottlenecks
    )

    combat_power_ready = checks.get("combat_power", 1.0) >= 1.0
    soft_level_gap = _number(required_values, "level") > 0 and checks.get("level", 1.0) < 1.0
    if score >= thresholds["recommended"] and not severe_bottleneck and not soft_level_gap:
        return "recommended"
    if severe_bottleneck and score >= thresholds["challengeable"]:
        return "risky"
    if score >= thresholds["challengeable"] or (
        combat_power_ready and score >= max(0.80, thresholds["challengeable"] - 0.08)
    ):
        return "risky" if soft_level_gap else "challengeable"
    if score >= thresholds["risky"]:
        return "risky"
    return "difficult"


def _first_number(sources: List[Any], keys: List[str], default: float = 0.0) -> float:
    for source in sources:
        for key in keys:
            value = _value(source, key, None)
            if value in {None, ""}:
                continue
            try:
                return float(value)
            except (TypeError, ValueError):
                continue
    return default


def _first_text(sources: List[Any], keys: List[str], default: str = "") -> str:
    for source in sources:
        for key in keys:
            value = _value(source, key, None)
            if value not in {None, ""}:
                return str(value)
    return default


def _query_tokens(query: str) -> List[str]:
    return [token.strip() for token in re.findall(r"[0-9A-Za-z가-힣_]+", query or "") if token.strip()]


def _strip_korean_particle(token: str) -> str:
    return re.sub(r"(인데요|인데|입니다|이고|이라는|라는|은|는|이|가)$", "", token).strip()


QUERY_PARSER_SYSTEM_PROMPT = """
You are a MapleStory Korean query parser for an analystic agent node.
Extract only boss-routing slots. Do not answer the user.
Return only one JSON object with these keys:
- intent: boss_readiness | available_boss_recommendation | character_analysis | unknown
- target_boss: string or null
- boss_difficulty: Easy | Normal | Hard | Chaos | Extreme | null
- needs_boss_recommendation: boolean
- confidence: number from 0 to 1

Rules:
- Ignore character/user names. Supervisor and API collection own that responsibility.
- Map boss abbreviations when obvious, e.g. 하스우 -> 하드 스우, 검마 -> 검은 마법사.
- If the query asks "가능한 보스", "추천 보스", or "어디까지 가능", set needs_boss_recommendation true.
- If no specific boss is asked, target_boss must be null.
""".strip()


def _parse_user_query_with_runnable(user_query: str, model: str | BaseChatModel | None = None) -> Dict[str, Any]:
    if model is None:
        if get_llm is None:
            raise RuntimeError("common.get_model.get_llm is required for LLM query parsing.")
        _load_project_env()
        model = get_llm()
    response = model.invoke(
        [
            HumanMessage(
                content=f"{QUERY_PARSER_SYSTEM_PROMPT}\n\nUser query: {user_query}\nJSON only:"
            )
        ]
    )
    parsed = _parse_json_object(str(getattr(response, "content", response)))
    intent = str(parsed.get("intent") or "unknown")
    if intent not in {"boss_readiness", "available_boss_recommendation", "character_analysis", "unknown"}:
        intent = "unknown"

    difficulty = parsed.get("boss_difficulty")
    if difficulty is not None:
        difficulty = str(difficulty).title()
        if difficulty not in {"Easy", "Normal", "Hard", "Chaos", "Extreme"}:
            difficulty = None

    try:
        confidence = float(parsed.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0

    target_boss = str(parsed["target_boss"]).strip() if parsed.get("target_boss") else None
    fallback_target = _extract_target_boss_from_query(user_query)
    if not target_boss and fallback_target:
        target_boss = fallback_target
        if intent == "unknown":
            intent = "boss_readiness"
        confidence = max(confidence, 0.55)

    parsed_target = _parse_boss_target(target_boss) if target_boss else {}
    if difficulty is None and parsed_target.get("difficulty"):
        difficulty = str(parsed_target["difficulty"]).title()

    return {
        "intent": intent,
        "target_boss": target_boss,
        "boss_difficulty": difficulty,
        "needs_boss_recommendation": bool(parsed.get("needs_boss_recommendation", False)),
        "confidence": max(0.0, min(1.0, confidence)),
    }


def _apply_parsed_query_to_state(state: AgentState, parsed: Dict[str, Any]) -> AgentState:
    if not parsed:
        return state

    new_state = dict(state)
    if parsed.get("intent") and parsed["intent"] != "unknown":
        new_state.setdefault("intent", parsed["intent"])

    target_boss = parsed.get("target_boss")
    difficulty = parsed.get("boss_difficulty")
    difficulty_label = _boss_difficulty_ko(difficulty) or difficulty
    difficulty_text = str(difficulty or "")
    target_has_difficulty = bool(_parse_boss_target(target_boss).get("difficulty")) if target_boss else False
    if target_boss and difficulty_label and not target_has_difficulty and difficulty_text.lower() not in target_boss.lower() and str(difficulty_label) not in target_boss:
        target_boss = f"{difficulty_label} {target_boss}"

    if target_boss:
        raw_api_results = dict(_value(new_state, "raw_api_results", {}) or {})
        raw_api_results["target_boss"] = target_boss
        new_state["raw_api_results"] = raw_api_results

    tool_results = dict(_value(new_state, "tool_results", {}) or {})
    tool_results["analystic_query_parse"] = parsed
    new_state["tool_results"] = tool_results
    return new_state


def _fallback_parse_query_to_state(state: AgentState) -> AgentState:
    user_query = str(_value(state, "user_query", ""))
    target_boss = _extract_target_boss_from_query(user_query)
    parsed = {
        "intent": "boss_readiness" if target_boss else "available_boss_recommendation",
        "target_boss": target_boss or None,
        "boss_difficulty": None,
        "needs_boss_recommendation": not bool(target_boss),
        "confidence": 0.35,
    }
    return _apply_parsed_query_to_state(state, parsed)


def _extract_target_boss_from_query(query: str) -> str:
    tokens = _query_tokens(query)
    difficulties = {"이지", "노멀", "노말", "하드", "카오스", "익스트림"}
    stopwords = {"가능", "가능해", "가능할까", "추천", "추천해", "보스", "뭐", "뭐가"}
    for index, token in enumerate(tokens):
        if token not in difficulties:
            continue
        boss_tokens = [item for item in tokens[index + 1 : index + 3] if item not in stopwords and item not in difficulties]
        if boss_tokens:
            return f"{token} {' '.join(boss_tokens)}"
    return ""


def _append_state_error(state: AgentState, message: str) -> AgentState:
    new_state = dict(state)
    errors = list(new_state.get("errors", []) or [])
    errors.append(message)
    new_state["errors"] = errors
    return new_state


def _empty_analytics_result(message: str) -> Dict[str, Any]:
    return {
        "available_bosses": [],
        "boss_groups": {status: [] for status in _BOSS_STATUSES},
        "recommended_actions": [],
        "challenge_fit_score": 0.0,
        "summary": {
            **{f"{status}_count": 0 for status in _BOSS_STATUSES},
            "total_bosses_checked": 0,
            "message": message,
        },
        "data_reliability": "analysis_failed_or_missing_data",
        "error": message,
    }


def _target_boss_from_state(state: AgentState, target_boss: Optional[str], *, required: bool = True) -> str:
    if target_boss:
        return target_boss
    for value in (
        _value(state, "target_boss"),
        _value(_value(state, "raw_api_results", {}), "target_boss"),
        _value(_value(state, "tool_results", {}), "target_boss"),
        _extract_target_boss_from_query(str(_value(state, "user_query", ""))),
    ):
        if value:
            return str(value)
    if required:
        raise ValueError("target_boss is required for analystic boss readiness analysis.")
    return ""


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

    current_values = {
        "level": level,
        "combat_power": combat_power,
        "main_stat": main_stat,
        "attack_or_magic": current_attack_or_magic,
        "boss_damage": boss_damage,
        "ignore_def": ignore_def,
        "crit_rate": min(crit_rate, 100),
        "crit_damage": crit_damage,
        "final_damage": final_damage,
        "force": current_force,
        "starforce": starforce,
        "union_level": union_level,
    }
    required_values = {
        stat: _number(boss, field)
        for stat, field, _ in _BOSS_STAT_RULES
        if field
    }
    required_values.update(
        {
            "attack_or_magic": required_attack_or_magic,
            "force": required_force,
        }
    )
    stat_pairs = [
        (
            stat,
            current_values[stat],
            required_values[stat],
            description,
        )
        for stat, _, description in _BOSS_STAT_RULES
    ]
    checks = {
        key: round(actual / required, 4) if required > 0 else 1.0
        for key, actual, required, _ in stat_pairs
    }

    bottlenecks = []
    for stat_name, actual, required, description in stat_pairs:
        ratio = checks[stat_name]
        if ratio >= 1.0:
            continue
        priority = 1 if ratio < 0.75 else 2 if ratio < 0.90 else 3
        bottlenecks.append(
            {
                "category": "BOSS_READINESS",
                "target": stat_name,
                "stat": stat_name,
                "actual": actual,
                "required": required,
                "gap": round(max(0.0, required - actual), 2),
                "ratio": ratio,
                "priority": priority,
                "expected_cp_gain": int(max(0.0, required - actual)),
                "description": description,
            }
        )
    bottlenecks.sort(key=lambda item: (item["priority"], item["ratio"]))

    priority_profile = _boss_priority_profile(boss, required_values)
    score = _boss_clear_score(checks, required_values, priority_profile)
    status = _status(score, bottlenecks, checks, required_values, priority_profile)
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
        "decision_basis": {
            "formula": "weighted_boss_attempt_fit",
            "stat_priority_profile": priority_profile["tier"],
            "primary_signal": "combat_power_when_available_otherwise_main_stat_and_damage_stats",
            "stat_weights": priority_profile["weights"],
            "status_thresholds": priority_profile["thresholds"],
            "hard_gates": priority_profile["hard_gates"],
            "critical_stats": priority_profile["critical_stats"],
            "bottlenecks_are_advisory": True,
            "calibration_basis": "neo4j_stat_requirements_and_postgres_boss_recommendation_guardrails",
        },
        "data_reliability": "neo4j_requirements_weighted_boss_fit",
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

    tool_input = locals()
    boss = _query_boss_requirements(tool_input.pop("target_boss"))
    return _analyze_boss_row(boss, target_boss=target_boss, **tool_input)


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

    bosses = _query_all_boss_requirements()
    if not bosses:
        return {
            **_empty_analytics_result("No boss requirement rows were found in Neo4j."),
            "character_name": character_name,
            "job_name": job_name,
        }

    character_stats = {
        key: value
        for key, value in locals().items()
        if key not in {"bosses", "include_risky", "max_results"}
    }
    analyses = [
        _analyze_boss_row(
            boss,
            target_boss=str(boss.get("boss_name", "")),
            **character_stats,
        )
        for boss in bosses
    ]

    grouped: Dict[str, List[Dict[str, Any]]] = {status: [] for status in _BOSS_STATUSES}
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
            **{f"{status}_count": len(grouped[status]) for status in _BOSS_STATUSES},
            "total_bosses_checked": len(analyses),
        },
        "data_reliability": "boss_requirements_from_neo4j",
    }


def _extract_character_input(state: AgentState) -> Dict[str, Any]:
    profile = _value(state, "character_profile", {})
    equipment_items = _value(state, "equipment_items", _value(profile, "equipment_list", []))
    stat_sources = [
        _value(state, "stat_summary", {}),
        _value(profile, "final_stats", {}),
        _value(state, "character_stats", {}),
        profile,
    ]
    equipment_sources = [_value(state, "equipment_summary", {}), _value(state, "stat_summary", {})]
    union_sources = [_value(state, "stat_summary", {}), _value(profile, "union_info", {}), _value(state, "union_status", {})]
    main_stat = _first_number(stat_sources, ["main_stat", "primary_stat", "mainStat"], 0)
    if main_stat <= 0:
        main_stat = max(
            _first_number(stat_sources, ["str_val", "str", "STR"], 0),
            _first_number(stat_sources, ["dex", "dex_val", "DEX"], 0),
            _first_number(stat_sources, ["int_val", "int", "INT"], 0),
            _first_number(stat_sources, ["luk", "luk_val", "LUK"], 0),
        )
    starforce_default = sum(int(_number(item, "starforce", 0)) for item in (equipment_items or []))

    character_input = {
        "character_name": _first_text([profile, state], ["character_name", "name"], ""),
        "job_name": _first_text([profile, state], ["job_name", "character_class", "class_name"], ""),
        "level": int(_first_number([profile, *stat_sources], ["level", "character_level"], 0)),
        "main_stat": int(main_stat),
        "starforce": int(
            _first_number(
                [*equipment_sources, *stat_sources],
                ["starforce", "total_starforce"],
                starforce_default,
            )
        ),
        "union_level": int(_first_number(union_sources, ["union_level"], 0)),
    }
    character_input.update(
        {
            field: caster(_first_number(stat_sources, list(keys), 0))
            for field, (keys, caster) in _CHARACTER_NUMBER_FIELDS.items()
        }
    )
    return character_input


def _normalise_action_plan(action: Any, *, fallback_category: str = "BOSS_READINESS") -> Dict[str, Any]:
    category = str(_value(action, "category", fallback_category) or fallback_category)
    target = _value(action, "target", None) or _value(action, "stat", None) or _value(action, "boss_name", None)
    target = str(target or "unknown")
    priority = int(_number(action, "priority", 3))
    priority = min(5, max(1, priority))
    expected_cp_gain = int(max(0, _number(action, "expected_cp_gain", _number(action, "gap", 0))))
    description = _value(action, "description", "")
    if not description:
        if category == "BOSS_CHALLENGE":
            description = f"{target} is a candidate boss target for the current character."
        else:
            description = f"{target} is a bottleneck for the current boss readiness analysis."

    return {
        "category": category,
        "target": target,
        "priority": priority,
        "expected_cp_gain": expected_cp_gain,
        "description": str(description),
    }


def _is_valid_recommendation_action(action: Dict[str, Any]) -> bool:
    description = str(action.get("description", ""))
    target = str(action.get("target", ""))
    if not target or target == "unknown" or not description:
        return False
    planning_phrases = (
        "api",
        "API",
        "넥슨",
        "이용해",
        "이용하여",
        "가져와",
        "가져와서",
        "가져오",
        "분석합니다",
        "분석하세요",
        "분석하",
        "조회합니다",
        "조회하세요",
        "조회하고",
        "조회하",
        "확인합니다",
        "확인하세요",
        "확인하",
        "계산합니다",
        "계산하세요",
        "계산하",
        "업데이트",
        "fetch",
        "analyze",
        "retrieve",
        "check",
    )
    return not any(phrase in description for phrase in planning_phrases)


def _normalise_action_plans(result: Dict[str, Any]) -> List[Dict[str, Any]]:
    raw_actions = result.get("recommended_actions") or []
    if raw_actions:
        return [_normalise_action_plan(action) for action in raw_actions]

    if "available_bosses" in result:
        return [
            _normalise_action_plan(
                {
                    "category": "BOSS_CHALLENGE",
                    "target": item.get("boss_name"),
                    "priority": 2,
                    "expected_cp_gain": 0,
                    "description": f"{item.get('boss_name', 'unknown')} is included in the available boss list.",
                },
                fallback_category="BOSS_CHALLENGE",
            )
            for item in (result.get("available_bosses") or [])[:5]
        ]

    return []


def _boss_prediction_from_result(result: Dict[str, Any]) -> Dict[str, bool]:
    prediction = result.get("boss_clear_prediction")
    if isinstance(prediction, dict):
        return {str(key): bool(value) for key, value in prediction.items()}

    boss_groups = result.get("boss_groups") or {}
    if not isinstance(boss_groups, dict):
        return {}

    derived: Dict[str, bool] = {}
    for status in ("recommended", "challengeable"):
        for item in boss_groups.get(status, []) or []:
            boss_name = _value(item, "boss_name")
            if boss_name:
                derived[str(boss_name)] = True
    for status in ("risky", "difficult"):
        for item in boss_groups.get(status, []) or []:
            boss_name = _value(item, "boss_name")
            if boss_name and boss_name not in derived:
                derived[str(boss_name)] = False
    return derived


def _build_growth_report(
    state: AgentState,
    tool_input: Dict[str, Any],
    result: Dict[str, Any],
    recommended_actions: List[Dict[str, Any]],
) -> Dict[str, Any]:
    profile = _value(state, "character_profile", {})
    stat_sources = [
        _value(state, "stat_summary", {}),
        _value(profile, "final_stats", {}),
        _value(state, "character_stats", {}),
        profile,
    ]
    return {
        "character_id": _value(state, "ocid", tool_input.get("character_name", "")),
        "current_combat_power": int(tool_input.get("combat_power", 0)),
        "attack": int(max(tool_input.get("attack_power", 0), tool_input.get("magic_power", 0))),
        "boss_damage": float(tool_input.get("boss_damage", 0.0)),
        "ignore_def": float(tool_input.get("ignore_def", 0.0)),
        "crit_rate": float(tool_input.get("crit_rate", 0.0)),
        "crit_damage": float(tool_input.get("crit_damage", 0.0)),
        "damage": _first_number(stat_sources, ["damage"], 0),
        "bottleneck_analysis": result.get("bottleneck_analysis", {}),
        "recommended_actions": recommended_actions,
        "boss_clear_prediction": _boss_prediction_from_result(result),
        "data_reliability": result.get("data_reliability", "unknown"),
        "timestamp": datetime.now().isoformat(timespec="seconds"),
    }


def _build_analytics_answer_context(tool_input: Dict[str, Any], result: Dict[str, Any]) -> str:
    if result.get("error"):
        return "\n".join(
            [
                "Analytics result for final answer.",
                f"- Analytics failed: {result.get('error')}",
                "- Final answer should say the boss verdict could not be calculated from the current analytics result.",
            ]
        )

    if "available_bosses" in result and not result.get("boss_requirements"):
        groups = result.get("boss_groups") or {}
        group_counts = ", ".join(
            f"{status}={len(groups.get(status, []) or [])}" for status in _BOSS_STATUSES
        )
        top_bosses = ", ".join(
            str(_value(item, "boss_name", "unknown"))
            for item in (result.get("available_bosses") or [])[:8]
        ) or "none"
        return "\n".join(
            [
                "Analytics result for final answer.",
                "- Verdict type: available boss recommendation.",
                f"- Boss group counts: {group_counts}.",
                f"- Top available bosses: {top_bosses}.",
                f"- Best challenge fit score: {_format_number(result.get('challenge_fit_score', 0), 4)}.",
                f"- Data reliability: {result.get('data_reliability', 'unknown')}.",
            ]
        )

    requirements = result.get("boss_requirements") or {}
    target_boss = result.get("target_boss") or tool_input.get("target_boss") or "unknown"
    status = str(result.get("clear_status") or "unknown")
    challengeable = result.get("challengeable")
    if challengeable is None:
        challengeable = status in {"recommended", "challengeable"}

    current_force = _number(tool_input, "arcane_force") + _number(tool_input, "authentic_force")
    required_force = _number(requirements, "required_arcane_force") + _number(requirements, "required_authentic_force")
    comparisons = [
        ("level", _value(tool_input, "level", 0), _value(requirements, "required_level", 0)),
        ("combat_power", _value(tool_input, "combat_power", 0), _value(requirements, "required_combat_power", 0)),
        ("main_stat", _value(tool_input, "main_stat", 0), _value(requirements, "required_main_stat", 0)),
        ("boss_damage", _value(tool_input, "boss_damage", 0), _value(requirements, "required_boss_damage", 0)),
        ("ignore_def", _value(tool_input, "ignore_def", 0), _value(requirements, "required_ignore_def", 0)),
        ("force", current_force, required_force),
        ("starforce", _value(tool_input, "starforce", 0), _value(requirements, "required_starforce", 0)),
        ("union_level", _value(tool_input, "union_level", 0), _value(requirements, "required_union_level", 0)),
    ]
    comparison_text = "; ".join(
        f"{name}: current={_format_number(current)} required={_format_number(required)}"
        for name, current, required in comparisons
        if current not in (None, "") or required not in (None, "")
    )
    lacking_stats = ", ".join(str(item) for item in (result.get("lacking_stats") or [])) or "none"
    action_text = "; ".join(
        (
            f"{_value(action, 'target', _value(action, 'stat', 'unknown'))}: "
            f"current={_format_number(_value(action, 'actual', 0))} "
            f"required={_format_number(_value(action, 'required', 0))} "
            f"gap={_format_number(_value(action, 'gap', 0))}"
        )
        for action in (result.get("recommended_actions") or [])[:5]
    ) or "none"

    return "\n".join(
        [
            "Analytics result for final answer.",
            (
                "- Verdict: "
                f"target_boss={target_boss}, status={status}, "
                f"challengeable={bool(challengeable)}, "
                f"challenge_fit_score={_format_number(result.get('challenge_fit_score', 0), 4)}."
            ),
            "- Verdict rule: recommended/challengeable means the character can attempt the boss; risky means possible but unstable; difficult means not ready.",
            f"- Current vs required stats: {comparison_text}.",
            f"- Lacking stats: {lacking_stats}.",
            f"- Recommended improvements: {action_text}.",
            f"- Requirement source: {requirements.get('source_name', 'unknown')} / reliability={requirements.get('reliability', result.get('data_reliability', 'unknown'))}.",
        ]
    )


def _with_analytics_result(state: AgentState, tool_input: Dict[str, Any], result: Dict[str, Any]) -> AgentState:
    recommended_actions = _normalise_action_plans(result)
    new_state = dict(state)
    new_state["tool_results"] = {**new_state.get("tool_results", {}), "analystic": result}
    new_state["bottleneck_analysis"] = result.get("bottleneck_analysis", {})
    new_state["growth_report"] = _build_growth_report(new_state, tool_input, result, recommended_actions)
    new_state["recommended_actions"] = recommended_actions
    new_state["confidence_score"] = result.get("challenge_fit_score", 0.0)
    new_state["context"] = _upsert_context_section(
        new_state.get("context", ""),
        "analytics_context",
        _build_analytics_answer_context(tool_input, result),
    )
    return new_state


def run_analystic(
    state: AgentState,
    *,
    boss_neo4j_connection: Any = None,
    target_boss: Optional[str] = None,
) -> "AgentState":
    """Run the common.state-compatible analystic step.

    This function uses common.state.AgentState fields directly. It reads
    character_profile, stat_summary, and equipment_summary from AgentState.
    Character data must already be present in state; this node does not fetch it.
    """

    try:
        missing = [
            key
            for key in ("character_profile", "stat_summary", "equipment_summary")
            if key not in state or state[key] is None
        ]
        if missing:
            raise ValueError(f"analystic input state missing fields: {missing}")
        if validate_agent_inputs is not None:
            validate_agent_inputs("analystic", state)

        if boss_neo4j_connection is not None:
            set_boss_neo4j_connection(boss_neo4j_connection)

        resolved_target_boss = _target_boss_from_state(state, target_boss, required=False)
        if resolved_target_boss:
            tool_input = _extract_character_input(state)
            tool_input["target_boss"] = resolved_target_boss
            result = analyze_boss_readiness.invoke(tool_input)
        else:
            tool_input = _extract_character_input(state)
            tool_input["include_risky"] = True
            tool_input["max_results"] = 20
            result = find_available_bosses.invoke(tool_input)
    except Exception as exc:
        message = f"analystic failed: {exc}"
        new_state = _append_state_error(state, message)
        result = _empty_analytics_result(message)
        tool_input = {
            "character_name": _value(new_state, "character_name", ""),
            "combat_power": 0,
            "attack_power": 0,
            "magic_power": 0,
            "boss_damage": 0.0,
            "ignore_def": 0.0,
            "crit_rate": 0.0,
            "crit_damage": 0.0,
        }
        new_state = _with_analytics_result(new_state, tool_input, result)
        if validate_agent_outputs is not None:
            validate_agent_outputs("analystic", new_state)
        return new_state

    new_state = _with_analytics_result(state, tool_input, result)
    if validate_agent_outputs is not None:
        validate_agent_outputs("analystic", new_state)
    return new_state


def _compact_boss_item(item: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "boss_name": item.get("boss_name"),
        "difficulty": item.get("difficulty"),
        "score": item.get("challenge_fit_score"),
        "lacking_stats": (item.get("lacking_stats") or [])[:3],
    }


def _compact_analytics_context(state: AgentState) -> Dict[str, Any]:
    tool_result = _value(_value(state, "tool_results", {}), "analystic", {}) or {}
    character_input = _extract_character_input(state)
    context: Dict[str, Any] = {
        "character": {
            "name": character_input["character_name"],
            "job": character_input["job_name"],
            "level": character_input["level"],
            "combat_power": character_input["combat_power"],
            "main_stat": character_input["main_stat"],
            "boss_damage": character_input["boss_damage"],
            "ignore_def": character_input["ignore_def"],
            "arcane_force": character_input["arcane_force"],
            "authentic_force": character_input["authentic_force"],
        },
        "summary": tool_result.get("summary", {}),
        "data_reliability": tool_result.get("data_reliability"),
    }

    if "available_bosses" in tool_result:
        boss_groups = tool_result.get("boss_groups", {}) or {}
        context["available_bosses"] = [_compact_boss_item(item) for item in tool_result.get("available_bosses", [])[:8]]
        context["boss_groups"] = {
            status: [_compact_boss_item(item) for item in (boss_groups.get(status, []) or [])[:5]]
            for status in _BOSS_STATUSES[:3]
        }
        return context

    context.update(
        {
            "target_boss": tool_result.get("target_boss"),
            "difficulty": tool_result.get("difficulty"),
            "clear_status": tool_result.get("clear_status"),
            "challenge_fit_score": tool_result.get("challenge_fit_score"),
            "lacking_stats": (tool_result.get("lacking_stats") or [])[:5],
            "recommended_actions": (tool_result.get("recommended_actions") or [])[:3],
            "decision_basis": {
                "profile": _value(tool_result.get("decision_basis", {}), "stat_priority_profile"),
                "critical_stats": _value(tool_result.get("decision_basis", {}), "critical_stats", []),
            },
        }
    )
    return context


def _compact_research_context(state: AgentState) -> Dict[str, Any]:
    docs = []
    for doc in (_value(state, "retrieved_docs", []) or [])[:4]:
        content = str(_value(doc, "page_content", ""))[:700]
        metadata = _value(doc, "metadata", {}) or {}
        docs.append(
            {
                "page_content": content,
                "source": _value(doc, "source", _value(metadata, "source", "")),
                "score": _value(doc, "score", None),
            }
        )

    return {
        "context": str(_value(state, "context", ""))[:2500],
        "retrieved_docs": docs,
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


def _merge_action_plans(base_actions: List[Dict[str, Any]], llm_actions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    merged: List[Dict[str, Any]] = []
    seen = set()
    for action in [*base_actions, *llm_actions]:
        normalised = _normalise_action_plan(action)
        if not _is_valid_recommendation_action(normalised):
            continue
        key = (normalised["category"], normalised["target"])
        if key in seen:
            continue
        seen.add(key)
        merged.append(normalised)
    return merged[:8]


ANALYTICS_TOOLS = [analyze_boss_readiness, find_available_bosses]


ANALYTICS_STATE_SYSTEM_PROMPT = f"""
{master_prompt}

너는 메이플스토리 분석 전문가이다.\
다음의 룰은 꼭지켜야한다.
- 툴을 사용하여 분석 결과를 제시하여야한다.
- 절대로 문장으로 답변을 제시하면 안된다.
- 절대로 너가 임의로 답변을 만들면 안된다. 
- 너는 어디까지나 state에 이미 들어온 유저 캐릭터의 스탯과 DB를 통해 가져온 보스 필요스탯을 비교하여 정의된 규칙에 따라서 적절성을 판단한후 그걸 정해진 state에 넣는것을 수행하는 절차의 일부이다.
- 유저 캐릭터 정보는 AgentState에서만 읽고, 이 노드에서 외부 API를 호출하지 않는다.


""".strip()

def _generate_agent_state_update(
    state: AgentState,
    model: str | BaseChatModel | None,
) -> Dict[str, Any]:
    if model is None:
        if get_llm is None:
            raise RuntimeError("common.get_model.get_llm is required for analystic agent state generation.")
        _load_project_env()
        model = get_llm()

    analytic_agent = create_agent(
        model=model,
        tools=ANALYTICS_TOOLS,
        system_prompt=ANALYTICS_STATE_SYSTEM_PROMPT,
    )
    result = analytic_agent.invoke(
        {
            "messages": [
                HumanMessage(
                    content=(
                        "Return only a JSON object for AgentState update. "
                        f"Input: {json.dumps({
                            'user_query': _value(state, 'user_query', ''),
                            'analytics': _compact_analytics_context(state),
                            'research_context': _compact_research_context(state),
                            'current_recommended_actions': _value(state, 'recommended_actions', []),
                        }, ensure_ascii=False)}"
                    )
                )
            ]
        }
    )
    parsed = _parse_json_object(result["messages"][-1].content)
    parsed["recommended_actions"] = [
        normalised
        for action in (parsed.get("recommended_actions") or [])[:5]
        if isinstance(action, dict)
        for normalised in [_normalise_action_plan(action)]
        if _is_valid_recommendation_action(normalised)
    ]
    interpretation = parsed.get("llm_interpretation")
    parsed["llm_interpretation"] = interpretation if isinstance(interpretation, dict) else {}
    return parsed





def analytics_agent(
    model: str | BaseChatModel | None = None,
    *,
    boss_neo4j_connection: Any = None,
    state: AgentState,
) -> AgentState:
    """Run analystic node with create_agent tools and return AgentState-compatible fields."""

    user_query = state["user_query"]
    try:
        parsed_query = _parse_user_query_with_runnable(user_query, model)
        state = _apply_parsed_query_to_state(state, parsed_query)
    except Exception as exc:
        state = _append_state_error(state, f"analystic query parser failed: {exc}")
        state = _fallback_parse_query_to_state(state)

    state = run_analystic(
        state,
        boss_neo4j_connection=boss_neo4j_connection,
    )
    analysis_result = _value(_value(state, "tool_results", {}), "analystic", {}) or {}
    has_usable_result = (
        not _value(analysis_result, "error")
        and _value(analysis_result, "data_reliability") != "analysis_failed_or_missing_data"
        and bool(
            _value(analysis_result, "boss_requirements")
            or _value(analysis_result, "available_bosses")
            or _value(analysis_result, "clear_status")
            or _value(analysis_result, "boss_clear_prediction")
            or _value(state, "recommended_actions", [])
        )
    )
    if has_usable_result:
        try:
            agent_update = _generate_agent_state_update(state, model)
        except Exception as exc:
            state = _append_state_error(state, f"analystic create_agent state generation failed: {exc}")
            agent_update = {}
    else:
        agent_update = {}

    llm_actions = agent_update.get("recommended_actions") or []
    llm_interpretation = agent_update.get("llm_interpretation") or {}
    if llm_actions or llm_interpretation:
        base_actions = [_normalise_action_plan(action) for action in (_value(state, "recommended_actions", []) or [])]
        recommended_actions = _merge_action_plans(base_actions, llm_actions)
        growth_report = dict(_value(state, "growth_report", {}) or {})
        growth_report["recommended_actions"] = recommended_actions
        if str(_value(state, "context", "")).strip() or (_value(state, "retrieved_docs", []) or []):
            growth_report["data_reliability"] = "boss_requirements_from_neo4j_with_research_context"

        tool_results = dict(_value(state, "tool_results", {}) or {})
        analystic_result = dict(_value(tool_results, "analystic", {}) or {})
        analystic_result["llm_interpretation"] = llm_interpretation
        analystic_result["agent_recommended_actions"] = llm_actions
        analystic_result["recommended_actions"] = recommended_actions
        analystic_result["data_reliability"] = growth_report.get(
            "data_reliability",
            analystic_result.get("data_reliability", "boss_requirements_from_neo4j"),
        )
        tool_results["analystic"] = analystic_result

        state = {
            **state,
            "tool_results": tool_results,
            "growth_report": growth_report,
            "recommended_actions": recommended_actions,
        }

    if validate_agent_outputs is not None:
        validate_agent_outputs("analystic", state)
    return {
        **state,
        "user_query": user_query,
    }
