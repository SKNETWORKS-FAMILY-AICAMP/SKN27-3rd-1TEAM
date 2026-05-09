from __future__ import annotations
import sys
import os
import re
from datetime import datetime, timedelta

# 현재 파일(main.py)의 부모의 부모의 부모 폴더를 path에 추가 (project_root 경로)
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(current_dir, "../../"))
sys.path.append(project_root)

from pathlib import Path
from typing import Any, Dict, List, Optional, TYPE_CHECKING
from dotenv import load_dotenv


from langchain.agents import create_agent
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage
from langchain_core.tools import tool
from pydantic import BaseModel, Field
import requests
from neo4j import GraphDatabase
from common.get_model import get_llm
from common.prompt import master_prompt
from common.validator import validate_agent_inputs, validate_agent_outputs
from common.state import AgentState

load_dotenv()

_BOSS_GRAPH_CONNECTION: Any = None
_BOSS_GRAPH_DATABASE: Optional[str] = None
_NEXON_API_BASE_URL = "https://open.api.nexon.com/maplestory/v1"
_NEXON_API_TIMEOUT_SECONDS = 10


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


class NexonCharacterLookupInput(BaseModel):
    """Input schema for fetching MapleStory character data from Nexon Open API."""

    character_name: str = Field(..., description="MapleStory character name.")
    date: Optional[str] = Field(None, description="KST query date in YYYY-MM-DD. Defaults to yesterday.")


def _load_project_env() -> None:
    project_root = Path(__file__).resolve().parents[2]
    for env_path in (
        project_root / ".env",
        project_root / "database" / ".env",
        Path(__file__).resolve().parent / ".env",
    ):
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


def _boss_difficulty_ko(value: Any) -> Optional[str]:
    difficulty_map = {
        "EASY": "이지",
        "NORMAL": "노멀",
        "HARD": "하드",
        "CHAOS": "카오스",
        "EXTREME": "익스트림",
        "이지": "이지",
        "노멀": "노멀",
        "노말": "노멀",
        "하드": "하드",
        "카오스": "카오스",
        "익스트림": "익스트림",
    }
    text = str(value or "").strip()
    if not text:
        return None
    return difficulty_map.get(text.upper()) or difficulty_map.get(text)


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
        rows = _fetch_all_boss_requirements()
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


def _fetch_boss_requirements(target_boss: str) -> Dict[str, Any]:
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


def _fetch_all_boss_requirements() -> List[Dict[str, Any]]:
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


_BOSS_PRIORITY_PROFILES = {
    "early": {
        "weights": {
            "combat_power": 0.48,
            "main_stat": 0.18,
            "attack_or_magic": 0.10,
            "boss_damage": 0.05,
            "ignore_def": 0.03,
            "crit_rate": 0.04,
            "crit_damage": 0.04,
            "final_damage": 0.02,
            "force": 0.01,
            "level": 0.04,
            "starforce": 0.01,
            "union_level": 0.00,
        },
        "thresholds": {"recommended": 1.00, "challengeable": 0.84, "risky": 0.65},
        "hard_gates": {"level": 1.0, "force": 0.55, "ignore_def": 0.55, "combat_power": 0.50},
        "critical_stats": ["level", "combat_power"],
    },
    "mid": {
        "weights": {
            "combat_power": 0.40,
            "main_stat": 0.14,
            "attack_or_magic": 0.08,
            "boss_damage": 0.08,
            "ignore_def": 0.08,
            "crit_rate": 0.03,
            "crit_damage": 0.05,
            "final_damage": 0.05,
            "force": 0.05,
            "level": 0.03,
            "starforce": 0.01,
            "union_level": 0.00,
        },
        "thresholds": {"recommended": 1.03, "challengeable": 0.88, "risky": 0.70},
        "hard_gates": {"level": 1.0, "force": 0.65, "ignore_def": 0.65, "combat_power": 0.58},
        "critical_stats": ["level", "combat_power", "force", "ignore_def"],
    },
    "late": {
        "weights": {
            "combat_power": 0.34,
            "main_stat": 0.10,
            "attack_or_magic": 0.07,
            "boss_damage": 0.10,
            "ignore_def": 0.11,
            "crit_rate": 0.02,
            "crit_damage": 0.06,
            "final_damage": 0.08,
            "force": 0.08,
            "level": 0.03,
            "starforce": 0.01,
            "union_level": 0.00,
        },
        "thresholds": {"recommended": 1.05, "challengeable": 0.92, "risky": 0.76},
        "hard_gates": {"level": 1.0, "force": 0.75, "ignore_def": 0.75, "combat_power": 0.65},
        "critical_stats": ["level", "combat_power", "force", "ignore_def", "boss_damage"],
    },
    "endgame": {
        "weights": {
            "combat_power": 0.28,
            "main_stat": 0.08,
            "attack_or_magic": 0.06,
            "boss_damage": 0.10,
            "ignore_def": 0.13,
            "crit_rate": 0.01,
            "crit_damage": 0.06,
            "final_damage": 0.09,
            "force": 0.14,
            "level": 0.04,
            "starforce": 0.01,
            "union_level": 0.00,
        },
        "thresholds": {"recommended": 1.08, "challengeable": 0.96, "risky": 0.82},
        "hard_gates": {"level": 1.0, "force": 0.85, "ignore_def": 0.82, "combat_power": 0.72},
        "critical_stats": ["level", "combat_power", "force", "ignore_def", "boss_damage", "final_damage"],
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


def _boss_priority_tier(boss: Dict[str, Any], required_values: Dict[str, float]) -> str:
    boss_name_key = _normalize_boss_lookup_text(_value(boss, "boss_name", ""))
    required_level = _number(required_values, "level")
    required_force = _number(required_values, "force")
    required_ignore_def = _number(required_values, "ignore_def")

    if (
        any(key and key in boss_name_key for key in _ENDGAME_BOSS_KEYS)
        or required_level >= 275
        or required_force >= 300
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

    if required_combat_power <= 0:
        weights["combat_power"] = 0.0
        weights["main_stat"] += 0.08
        weights["attack_or_magic"] += 0.04
    if required_force > 0:
        weights["force"] += 0.04
        weights["combat_power"] = max(0.0, weights["combat_power"] - 0.02)
    if required_ignore_def >= 90:
        weights["ignore_def"] += 0.04
        weights["combat_power"] = max(0.0, weights["combat_power"] - 0.02)
    elif required_ignore_def > 0:
        weights["ignore_def"] += 0.02

    return {
        "tier": tier,
        "weights": {key: round(max(0.0, value), 4) for key, value in weights.items()},
        "thresholds": dict(base_profile["thresholds"]),
        "hard_gates": dict(base_profile["hard_gates"]),
        "critical_stats": list(base_profile["critical_stats"]),
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

    if _number(required_values, "level") > 0 and checks.get("level", 1.0) < 1.0:
        return "difficult"
    if _number(required_values, "force") > 0 and checks.get("force", 1.0) < hard_gates["force"]:
        return "difficult"
    if _number(required_values, "combat_power") > 0 and checks.get("combat_power", 1.0) < hard_gates["combat_power"]:
        return "difficult"

    severe_bottleneck = any(
        item["stat"] in critical_stats
        and item["stat"] != "level"
        and item["ratio"] < hard_gates.get(item["stat"], 0.60)
        for item in bottlenecks
    )

    combat_power_ready = checks.get("combat_power", 1.0) >= 1.0
    if score >= thresholds["recommended"] and not severe_bottleneck:
        return "recommended"
    if severe_bottleneck and score >= thresholds["challengeable"]:
        return "risky"
    if score >= thresholds["challengeable"] or (
        combat_power_ready and score >= max(0.80, thresholds["challengeable"] - 0.08)
    ):
        return "challengeable"
    if score >= thresholds["risky"]:
        return "risky"
    return "difficult"


def _sum_equipment_starforce(equipment_items: Any) -> int:
    if not equipment_items:
        return 0
    total = 0
    for item in equipment_items:
        total += int(_number(item, "starforce", 0))
    return total


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

_CHARACTER_QUERY_STOPWORDS = {
    "가능한",
    "보스",
    "추천",
    "추천하",
    "뭐",
    "뭐가",
    "무엇",
    "어떤",
    "하드",
    "노말",
    "노멀",
    "이지",
    "카오스",
    "익스트림",
    "가능해",
    "가능할까",
}

_BOSS_DIFFICULTY_WORDS = {"이지", "노멀", "노말", "하드", "카오스", "익스트림"}
_QUERY_END_WORD_PREFIXES = (
    "가능",
    "도전",
    "갈",
    "잡",
    "깰",
    "클리어",
    "어때",
    "될까",
    "추천",
    "알려",
    "뭐",
    "무엇",
    "어떤",
    "있",
)


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
    return {
        "x-nxopen-api-key": api_key,
        "Accept": "application/json",
    }


def _nexon_error_message(response: requests.Response) -> str:
    try:
        data = response.json()
    except ValueError:
        return response.text[:500]
    if isinstance(data, dict):
        return str(data.get("message") or data.get("error") or data)[:500]
    return str(data)[:500]


def _nexon_get(path: str, params: Dict[str, Any]) -> Dict[str, Any]:
    url = f"{_NEXON_API_BASE_URL}{path}"
    try:
        response = requests.get(
            url,
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


def _nexon_number(value: Any, default: float = 0.0) -> float:
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


def _normalize_nexon_final_stats(stat_response: Dict[str, Any]) -> Dict[str, Any]:
    stat_summary: Dict[str, Any] = {}
    for item in stat_response.get("final_stat") or []:
        if not isinstance(item, dict):
            continue
        stat_name = str(item.get("stat_name", "")).strip()
        target_key = _NEXON_FINAL_STAT_KEYS.get(stat_name)
        if not target_key:
            continue
        value = _nexon_number(item.get("stat_value"))
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
        value = _nexon_number(option.get(source_key))
        if value == 0:
            continue
        normalized[target_key] = int(value) if target_key.endswith("_val") or target_key in {
            "attack_power",
            "magic_power",
            "hp",
        } else value
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
                "starforce": int(_nexon_number(item.get("starforce"))),
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
    if not isinstance(union_response, dict):
        return {}
    return {
        "union_level": int(_nexon_number(union_response.get("union_level"))),
        "union_grade": str(union_response.get("union_grade") or ""),
        "artifact_level": None,
        "artifact_exp": 0,
    }


def _fetch_nexon_character_state(character_name: str, date: Optional[str] = None) -> Dict[str, Any]:
    api_date = _nexon_api_date(date)
    id_response = _nexon_get("/id", {"character_name": character_name})
    ocid = id_response.get("ocid")
    if not ocid:
        raise RuntimeError(f"Nexon Open API did not return ocid for character: {character_name}")

    dated_params = {"ocid": ocid, "date": api_date}
    basic_response = _nexon_get("/character/basic", dated_params)
    stat_response = _nexon_get("/character/stat", dated_params)
    equipment_response = _nexon_get("/character/item-equipment", dated_params)
    try:
        union_response = _nexon_get("/user/union", dated_params)
    except RuntimeError as exc:
        union_response = {"error": str(exc)}

    stat_summary = _normalize_nexon_final_stats(stat_response)
    equipment_items = _normalize_nexon_equipment(equipment_response)
    union_status = _normalize_nexon_union(union_response)
    if union_status.get("union_level"):
        stat_summary["union_level"] = union_status["union_level"]

    profile = {
        "character_name": basic_response.get("character_name") or character_name,
        "job_name": basic_response.get("character_class") or stat_response.get("character_class", ""),
        "world_name": basic_response.get("world_name", ""),
        "level": int(_nexon_number(basic_response.get("character_level"))),
        "gender": basic_response.get("character_gender"),
        "final_stats": stat_summary,
        "equipment_list": equipment_items,
        "union_info": union_status,
    }
    total_starforce = _sum_equipment_starforce(equipment_items)

    return {
        "ocid": ocid,
        "character_name": profile["character_name"],
        "world_name": profile["world_name"],
        "character_profile": profile,
        "character_stats": stat_summary,
        "equipment_items": equipment_items,
        "union_status": union_status,
        "stat_summary": stat_summary,
        "equipment_summary": {
            "equipment_count": len(equipment_items),
            "starforce": total_starforce,
            "total_starforce": total_starforce,
        },
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


def _clean_query_token(token: str) -> str:
    return re.sub(r"(인데요|인데|입니다|이고|님|은|는|이|가|으로|로|의)$", "", token).strip()


def _query_tokens(query: str) -> List[str]:
    return [_clean_query_token(token) for token in re.findall(r"[0-9A-Za-z가-힣_]+", query or "")]


def _is_query_end_word(token: str) -> bool:
    return any(token.startswith(prefix) for prefix in _QUERY_END_WORD_PREFIXES)


def _is_character_query_boundary(token: str) -> bool:
    return (
        token in _CHARACTER_QUERY_STOPWORDS
        or token in _BOSS_DIFFICULTY_WORDS
        or _is_query_end_word(token)
    )


def _extract_character_name_from_query(query: str) -> str:
    tokens = [token for token in _query_tokens(query) if token]
    if not tokens:
        return ""

    for marker in ("캐릭터", "닉네임", "이름"):
        if marker not in tokens:
            continue
        marker_index = tokens.index(marker) + 1
        candidate_tokens = []
        for token in tokens[marker_index:]:
            if _is_character_query_boundary(token):
                break
            candidate_tokens.append(token)
            if len(candidate_tokens) >= 2:
                break
        candidate = "".join(candidate_tokens)
        if candidate:
            return candidate

    candidate_tokens = []
    for token in tokens:
        if token in {"내", "제", "저", "나", "캐릭터", "닉네임", "이름"}:
            continue
        if _is_character_query_boundary(token):
            break
        candidate_tokens.append(token)
        if len(candidate_tokens) >= 2:
            break
    candidate = "".join(candidate_tokens)
    if candidate:
        return candidate
    return ""


def _extract_target_boss_from_query(query: str) -> str:
    tokens = [token for token in _query_tokens(query) if token]
    for index, token in enumerate(tokens):
        if token not in _BOSS_DIFFICULTY_WORDS:
            continue
        boss_tokens = []
        for boss_token in tokens[index + 1:]:
            if boss_token in _CHARACTER_QUERY_STOPWORDS or boss_token in _BOSS_DIFFICULTY_WORDS:
                break
            if _is_query_end_word(boss_token):
                break
            boss_tokens.append(boss_token)
            if len(boss_tokens) >= 2:
                break
        if boss_tokens:
            return f"{token} {' '.join(boss_tokens)}"
    return ""


def _state_needs_nexon_fetch(state: AgentState) -> bool:
    for key in ("character_profile", "stat_summary", "equipment_summary"):
        if key not in state or state[key] is None:
            return True
        if isinstance(state[key], dict) and not state[key]:
            return True
    return False


def _append_state_error(state: AgentState, message: str) -> AgentState:
    new_state = dict(state)
    errors = list(new_state.get("errors", []) or [])
    errors.append(message)
    new_state["errors"] = errors
    return new_state


def _empty_analytics_result(message: str) -> Dict[str, Any]:
    return {
        "available_bosses": [],
        "boss_groups": {
            "recommended": [],
            "challengeable": [],
            "risky": [],
            "difficult": [],
        },
        "recommended_actions": [],
        "challenge_fit_score": 0.0,
        "summary": {
            "recommended_count": 0,
            "challengeable_count": 0,
            "risky_count": 0,
            "difficult_count": 0,
            "total_bosses_checked": 0,
            "message": message,
        },
        "data_reliability": "analysis_failed_or_missing_data",
        "error": message,
    }


def _hydrate_state_from_nexon_if_needed(state: AgentState) -> AgentState:
    if not _state_needs_nexon_fetch(state):
        return state

    profile = _value(state, "character_profile", {})
    character_name = _first_text([state, profile], ["character_name", "name"], "")
    if not character_name:
        character_name = _extract_character_name_from_query(str(_value(state, "user_query", "")))
    if not character_name:
        raise ValueError("Could not extract character_name from user_query.")

    fetched_state = _fetch_nexon_character_state(character_name)
    raw_api_results = {
        **(_value(state, "raw_api_results", {}) or {}),
        **fetched_state.pop("raw_api_results", {}),
    }
    target_boss = _value(state, "target_boss") or _extract_target_boss_from_query(str(_value(state, "user_query", "")))

    hydrated_state = {
        **state,
        **fetched_state,
        "raw_api_results": raw_api_results,
    }
    if target_boss:
        hydrated_state["target_boss"] = str(target_boss)
    return hydrated_state


def _state_stat_sources(state: AgentState) -> List[Any]:
    profile = _value(state, "character_profile", {})
    return [
        _value(state, "stat_summary", {}),
        _value(profile, "final_stats", {}),
        _value(state, "character_stats", {}),
        profile,
    ]


def _state_equipment_sources(state: AgentState) -> List[Any]:
    return [
        _value(state, "equipment_summary", {}),
        _value(state, "stat_summary", {}),
    ]


def _state_union_sources(state: AgentState) -> List[Any]:
    profile = _value(state, "character_profile", {})
    return [
        _value(state, "stat_summary", {}),
        _value(profile, "union_info", {}),
        _value(state, "union_status", {}),
    ]


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


def _validate_analystic_state_inputs(state: AgentState) -> None:
    missing = [
        key
        for key in ("character_profile", "stat_summary", "equipment_summary")
        if key not in state or state[key] is None
    ]
    if missing:
        raise ValueError(f"analystic input state missing fields: {missing}")


def _target_boss_from_state(state: AgentState, target_boss: Optional[str]) -> str:
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

    query_value = _extract_target_boss_from_query(str(_value(state, "user_query", "")))
    if query_value:
        return query_value

    raise ValueError("target_boss is required for analystic boss readiness analysis.")


def _has_target_boss(state: AgentState, target_boss: Optional[str]) -> bool:
    if target_boss or _value(state, "target_boss"):
        return True
    if _value(_value(state, "raw_api_results", {}), "target_boss"):
        return True
    if _value(_value(state, "tool_results", {}), "target_boss"):
        return True
    if _extract_target_boss_from_query(str(_value(state, "user_query", ""))):
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
    required_values = {
        "level": _number(boss, "required_level"),
        "combat_power": _number(boss, "required_combat_power"),
        "main_stat": _number(boss, "required_main_stat"),
        "attack_or_magic": required_attack_or_magic,
        "boss_damage": _number(boss, "required_boss_damage"),
        "ignore_def": _number(boss, "required_ignore_def"),
        "crit_rate": _number(boss, "required_crit_rate"),
        "crit_damage": _number(boss, "required_crit_damage"),
        "final_damage": _number(boss, "required_final_damage"),
        "force": required_force,
        "starforce": _number(boss, "required_starforce"),
        "union_level": _number(boss, "required_union_level"),
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
            "primary_signal": "combat_power_when_available",
            "stat_weights": priority_profile["weights"],
            "hard_gates": priority_profile["hard_gates"],
            "critical_stats": priority_profile["critical_stats"],
            "bottlenecks_are_advisory": True,
        },
        "data_reliability": "neo4j_requirements_weighted_boss_fit",
    }


@tool(args_schema=NexonCharacterLookupInput)
def fetch_nexon_character_state(character_name: str, date: Optional[str] = None) -> Dict[str, Any]:
    """Fetch MapleStory character data from Nexon Open API and normalize it for AgentState."""

    return _fetch_nexon_character_state(character_name, date=date)


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
    if not bosses:
        return {
            **_empty_analytics_result("No boss requirement rows were found in Neo4j."),
            "character_name": character_name,
            "job_name": job_name,
        }

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


def _extract_agent_input(state: AgentState, target_boss: Optional[str]) -> Dict[str, Any]:
    tool_input = _extract_character_input(state)
    tool_input["target_boss"] = _target_boss_from_state(state, target_boss)
    return tool_input


def _extract_available_bosses_input(
    state: AgentState,
    *,
    include_risky: bool = True,
    max_results: int = 20,
) -> Dict[str, Any]:
    tool_input = _extract_character_input(state)
    tool_input["include_risky"] = include_risky
    tool_input["max_results"] = max_results
    return tool_input


def _extract_character_input(state: AgentState) -> Dict[str, Any]:
    profile = _value(state, "character_profile", {})
    equipment_items = _value(state, "equipment_items", _value(profile, "equipment_list", []))
    stat_sources = _state_stat_sources(state)
    equipment_sources = _state_equipment_sources(state)
    union_sources = _state_union_sources(state)
    starforce_default = _sum_equipment_starforce(equipment_items)

    return {
        "character_name": _first_text([profile, state], ["character_name", "name"], ""),
        "job_name": _first_text([profile, state], ["job_name", "character_class", "class_name"], ""),
        "level": int(_first_number([profile, *stat_sources], ["level", "character_level"], 0)),
        "combat_power": int(_first_number(stat_sources, ["combat_power", "current_combat_power"], 0)),
        "main_stat": _main_stat_from_sources(stat_sources),
        "attack_power": int(_first_number(stat_sources, ["attack_power", "attack"], 0)),
        "magic_power": int(_first_number(stat_sources, ["magic_power"], 0)),
        "boss_damage": _first_number(stat_sources, ["boss_damage"], 0),
        "ignore_def": _first_number(stat_sources, ["ignore_def", "ignore_defense", "ied"], 0),
        "crit_rate": _first_number(stat_sources, ["crit_rate", "critical_rate"], 0),
        "crit_damage": _first_number(stat_sources, ["crit_damage", "critical_damage"], 0),
        "final_damage": _first_number(stat_sources, ["final_damage"], 0),
        "arcane_force": int(_first_number(stat_sources, ["arcane_force"], 0)),
        "authentic_force": int(_first_number(stat_sources, ["authentic_force", "sacred_force"], 0)),
        "starforce": int(
            _first_number(
                [*equipment_sources, *stat_sources],
                ["starforce", "total_starforce"],
                starforce_default,
            )
        ),
        "union_level": int(_first_number(union_sources, ["union_level"], 0)),
    }


def run_analystic(
    state: AgentState,
    *,
    boss_graph_connection: Any = None,
    boss_db_connection: Any = None,
    target_boss: Optional[str] = None,
) -> "AgentState":
    """Run the common.state-compatible analystic step.

    This function uses common.state.AgentState fields directly. It reads
    character_profile, stat_summary, and equipment_summary first, then falls back to
    compatible raw character fields when older callers still provide them.
    """

    try:
        state = _hydrate_state_from_nexon_if_needed(state)
        _validate_analystic_state_inputs(state)
        if validate_agent_inputs is not None:
            validate_agent_inputs("analystic", state)

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
        new_state["tool_results"] = {**new_state.get("tool_results", {}), "analystic": result}
        new_state["bottleneck_analysis"] = {}
        new_state["growth_report"] = {
            "character_id": _value(new_state, "ocid", tool_input["character_name"]),
            "current_combat_power": 0,
            "attack": 0,
            "boss_damage": 0.0,
            "ignore_def": 0.0,
            "crit_rate": 0.0,
            "crit_damage": 0.0,
            "damage": 0.0,
            "bottleneck_analysis": {},
            "recommended_actions": [],
            "boss_clear_prediction": {},
            "data_reliability": result["data_reliability"],
            "timestamp": "",
        }
        new_state["recommended_actions"] = []
        new_state["confidence_score"] = 0.0
        return new_state

    growth_report = {
        "character_id": _value(state, "ocid", tool_input["character_name"]),
        "current_combat_power": tool_input["combat_power"],
        "attack": max(tool_input["attack_power"], tool_input["magic_power"]),
        "boss_damage": tool_input["boss_damage"],
        "ignore_def": tool_input["ignore_def"],
        "crit_rate": tool_input["crit_rate"],
        "crit_damage": tool_input["crit_damage"],
        "damage": _first_number(_state_stat_sources(state), ["damage"], 0),
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
            for status in ("recommended", "challengeable", "risky")
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


ANALYTICS_TOOLS = [fetch_nexon_character_state, analyze_boss_readiness, find_available_bosses]

ANALYTICS_SYSTEM_PROMPT = f"""
{master_prompt}

You are the MapleStory analystic agent for boss readiness.
Use analyze_boss_readiness when the user asks about one target boss.
Use find_available_bosses when the user asks which bosses are possible.
Explain the result in Korean.

Rules:
- Use boss requirement data from the configured Neo4j graph connection.
- Use character_profile, stat_summary, and equipment_summary from AgentState.
- Use fetch_nexon_character_state when the user gives only a character name and AgentState is not populated yet.
- Do not invoke the calculator agent; only consume values already present in AgentState.
- Produce growth_report and recommended_actions as the analystic output contract.
- Judge boss readiness with the weighted boss attempt fit score, not by one missing sub-stat alone.
- Apply different stat priority profiles by boss tier: early, mid, late, and endgame.
- Treat detailed lacking stats as bottlenecks and improvement advice unless level or force is a hard gate.
- State whether the character is difficult, risky, challengeable, or recommended.
- Explain the strongest bottlenecks first.
- Do not invent boss requirements when the Neo4j connection or boss row is missing.
- You may only use tools explicitly provided in the tools list.
- Never invent tools.
- Never call get_state.
""".strip()

ANALYTICS_ANSWER_SYSTEM_PROMPT = f"""
{master_prompt}

You are the MapleStory analystic final response writer.
Answer in Korean using only the provided compact analysis context.
Do not call tools. Do not request raw API data.
Keep the answer concise and mention the strongest boss recommendations first.
""".strip()


def analytics_agent(
    model: str | BaseChatModel | None = None,
    *,
    boss_graph_connection: Any = None,
    boss_db_connection: Any = None,
    state: AgentState,
) -> AgentState:
    """Create the analystic agent with common.get_model and Neo4j-backed tools."""

    user_query = state["user_query"]
    if boss_graph_connection is not None:
        set_boss_neo4j_connection(boss_graph_connection)
    elif boss_db_connection is not None:
        set_boss_db_connection(boss_db_connection)
    state = run_analystic(
        state,
        boss_graph_connection=boss_graph_connection,
        boss_db_connection=boss_db_connection,
    )
    if model is None:
        if get_llm is None:
            raise RuntimeError("common.get_model.get_llm is required for the analystic agent.")
        _load_project_env()
        model = get_llm()

    analytics_agent = create_agent(
        model=model,
        tools=[],
        system_prompt=ANALYTICS_ANSWER_SYSTEM_PROMPT
    )

    analysis_context = _compact_analytics_context(state)

    result = analytics_agent.invoke({"messages": [HumanMessage(content=f'''질문:{user_query}

    분석 요약:{analysis_context}
    
    위 분석 요약만 사용해서 답변하라''')]})
    analysis = result["messages"][-1].content

    return {
        **state,
        "user_query": user_query,
        "analysis": analysis,
    }


if __name__ == "__main__":
    state = analytics_agent(
        state={"user_query": "내 캐릭터는 음표인데 노멀 발드릭스 가능해?"}
    )
    print(state["analysis"])
