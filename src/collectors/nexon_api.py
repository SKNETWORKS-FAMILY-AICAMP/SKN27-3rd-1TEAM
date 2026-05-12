from __future__ import annotations

import json
import os
import re
import sys

current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(current_dir, "../../"))
sys.path.append(project_root)

from dataclasses import asdict, is_dataclass
from datetime import date
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

from common.domain import (
    CharacterStatDetail,
    EquipmentDetail,
    ProcessedCharacter,
    StatPackage,
    UnionStatus,
)

from common.state import AgentState


if load_dotenv is not None:
    load_dotenv()

DEFAULT_BASE_URL = "https://open.api.nexon.com/maplestory/v1"
DEFAULT_TIMEOUT_SECONDS = 10
API_KEY_ENV_NAMES = (
    "NEXON_OPEN_API_KEY",
    "NEXON_API_KEY",
    "NXOPEN_API_KEY",
)


class NexonAPIError(RuntimeError):
    """Raised when Nexon Open API cannot return usable character data."""


class NexonOpenAPIClient:
    """Small Nexon Open API client that returns raw JSON dictionaries.

    The collector intentionally has no dependency on Streamlit, LangGraph, or
    agent code. Other nodes can import it and then pass the normalized
    AgentState to calculator, analystic, research, or final_answer.
    """

    def __init__(
        self,
        api_key: str | None = None,
        *,
        base_url: str = DEFAULT_BASE_URL,
        timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        self.api_key = api_key or load_api_key()
        if not self.api_key:
            raise NexonAPIError(
                "Nexon API key is required. Set one of: "
                + ", ".join(API_KEY_ENV_NAMES)
            )
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    def request(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        query = urlencode(
            {
                key: value
                for key, value in (params or {}).items()
                if value not in (None, "")
            }
        )
        url = f"{self.base_url}/{path.lstrip('/')}"
        if query:
            url = f"{url}?{query}"

        request = Request(url, headers={"x-nxopen-api-key": self.api_key})
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                body = response.read().decode("utf-8")
        except HTTPError as exc:
            detail = _read_error_body(exc)
            raise NexonAPIError(f"Nexon API HTTP {exc.code} for {path}: {detail}") from exc
        except URLError as exc:
            raise NexonAPIError(f"Nexon API request failed for {path}: {exc}") from exc

        try:
            parsed = json.loads(body)
        except json.JSONDecodeError as exc:
            raise NexonAPIError(f"Nexon API returned invalid JSON for {path}") from exc
        return parsed if isinstance(parsed, dict) else {"data": parsed}

    def get_ocid(self, character_name: str) -> str:
        payload = self.request("id", {"character_name": character_name})
        ocid = str(payload.get("ocid") or "").strip()
        if not ocid:
            raise NexonAPIError(f"Could not resolve ocid for character: {character_name}")
        return ocid

    def get_character_basic(self, ocid: str, api_date: str | None = None) -> dict[str, Any]:
        return self.request("character/basic", {"ocid": ocid, "date": api_date})

    def get_character_stat(self, ocid: str, api_date: str | None = None) -> dict[str, Any]:
        return self.request("character/stat", {"ocid": ocid, "date": api_date})

    def get_item_equipment(self, ocid: str, api_date: str | None = None) -> dict[str, Any]:
        return self.request("character/item-equipment", {"ocid": ocid, "date": api_date})

    def get_union(self, ocid: str, api_date: str | None = None) -> dict[str, Any]:
        return self.request("user/union", {"ocid": ocid, "date": api_date})

    def get_union_raider(self, ocid: str, api_date: str | None = None) -> dict[str, Any]:
        return self.request("user/union-raider", {"ocid": ocid, "date": api_date})

    def get_union_artifact(self, ocid: str, api_date: str | None = None) -> dict[str, Any]:
        return self.request("user/union-artifact", {"ocid": ocid, "date": api_date})

    def get_vmatrix(self, ocid: str, api_date: str | None = None) -> dict[str, Any]:
        return self.request("character/vmatrix", {"ocid": ocid, "date": api_date})

    def get_hexamatrix(self, ocid: str, api_date: str | None = None) -> dict[str, Any]:
        return self.request("character/hexamatrix", {"ocid": ocid, "date": api_date})

    def get_ability(self, ocid: str, api_date: str | None = None) -> dict[str, Any]:
        return self.request("character/ability", {"ocid": ocid, "date": api_date})

    def get_hyper_stat(self, ocid: str, api_date: str | None = None) -> dict[str, Any]:
        return self.request("character/hyper-stat", {"ocid": ocid, "date": api_date})

    def fetch_raw_character_bundle(
        self,
        *,
        character_name: str | None = None,
        ocid: str | None = None,
        api_date: str | date | None = None,
        include_optional: bool = True,
    ) -> dict[str, Any]:
        resolved_date = normalise_api_date(api_date)
        resolved_ocid = ocid or self.get_ocid(require_character_name(character_name))

        raw: dict[str, Any] = {"ocid": resolved_ocid, "date": resolved_date}
        raw["basic"] = self.get_character_basic(resolved_ocid, resolved_date)
        raw["stat"] = self.get_character_stat(resolved_ocid, resolved_date)
        raw["item_equipment"] = self.get_item_equipment(resolved_ocid, resolved_date)
        raw["union"] = self.get_union(resolved_ocid, resolved_date)

        if include_optional:
            raw["union_raider"] = self._optional(self.get_union_raider, resolved_ocid, resolved_date)
            raw["union_artifact"] = self._optional(self.get_union_artifact, resolved_ocid, resolved_date)
            raw["vmatrix"] = self._optional(self.get_vmatrix, resolved_ocid, resolved_date)
            raw["hexamatrix"] = self._optional(self.get_hexamatrix, resolved_ocid, resolved_date)
            raw["ability"] = self._optional(self.get_ability, resolved_ocid, resolved_date)
            raw["hyper_stat"] = self._optional(self.get_hyper_stat, resolved_ocid, resolved_date)

        return raw

    def _optional(self, func: Any, ocid: str, api_date: str | None) -> dict[str, Any]:
        try:
            return func(ocid, api_date)
        except NexonAPIError as exc:
            return {"error": str(exc)}


def load_api_key() -> str:
    for name in API_KEY_ENV_NAMES:
        value = os.environ.get(name, "").strip()
        if value:
            return value
    return ""


def normalise_api_date(value: str | date | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, date):
        return value.isoformat()
    text = str(value).strip()
    return text or None


def require_character_name(character_name: str | None) -> str:
    text = str(character_name or "").strip()
    if not text:
        raise NexonAPIError("character_name is required when ocid is not provided.")
    return text


def fetch_character_state(
    character_name: str | None = None,
    *,
    ocid: str | None = None,
    world_name: str | None = None,
    user_query: str | None = None,
    api_date: str | date | None = None,
    api_key: str | None = None,
    client: NexonOpenAPIClient | None = None,
    include_optional: bool = True,
) -> AgentState:
    """Fetch Nexon Open API data and return an AgentState fragment.

    This is the easiest import point for app, service, or LangGraph nodes:

    ``state.update(fetch_character_state(character_name="음표"))``
    """

    api = client or NexonOpenAPIClient(api_key=api_key)
    raw = api.fetch_raw_character_bundle(
        character_name=character_name,
        ocid=ocid,
        api_date=api_date,
        include_optional=include_optional,
    )
    return normalise_raw_character_bundle(
        raw,
        character_name=character_name,
        world_name=world_name,
        user_query=user_query,
    )


def nexon_api_node(
    state: AgentState,
    *,
    api_date: str | date | None = None,
    api_key: str | None = None,
    client: NexonOpenAPIClient | None = None,
    include_optional: bool = True,
) -> AgentState:
    """LangGraph-friendly node that enriches AgentState with Nexon data."""

    character_name = state.get("character_name") or extract_character_name_from_query(
        state.get("user_query", "")
    )
    fetched = fetch_character_state(
        character_name=character_name,
        ocid=state.get("ocid"),
        world_name=state.get("world_name"),
        user_query=state.get("user_query"),
        api_date=api_date,
        api_key=api_key,
        client=client,
        include_optional=include_optional,
    )
    return {
        **state,
        **fetched,
        "raw_api_results": {
            **(state.get("raw_api_results") or {}),
            **(fetched.get("raw_api_results") or {}),
        },
        "tool_results": {
            **(state.get("tool_results") or {}),
            "nexon_api": {
                "character_name": fetched.get("character_name", ""),
                "world_name": fetched.get("world_name", ""),
                "ocid": fetched.get("ocid", ""),
                "data_reliability": "nexon_open_api",
            },
        },
    }


def normalise_raw_character_bundle(
    raw: dict[str, Any],
    *,
    character_name: str | None = None,
    world_name: str | None = None,
    user_query: str | None = None,
) -> AgentState:
    basic = raw.get("basic") or {}
    stat_payload = raw.get("stat") or {}
    equipment_payload = raw.get("item_equipment") or {}
    union_payload = raw.get("union") or {}

    stats = normalise_character_stats(stat_payload)
    equipment_items = normalise_equipment_items(equipment_payload)
    union_status = normalise_union_status(union_payload, raw.get("union_artifact"))
    profile = ProcessedCharacter(
        character_name=str(
            basic.get("character_name")
            or character_name
            or ""
        ),
        job_name=str(
            basic.get("character_class")
            or equipment_payload.get("character_class")
            or ""
        ),
        world_name=str(
            basic.get("world_name")
            or world_name
            or ""
        ),
        level=int(parse_number(basic.get("character_level"), 0)),
        gender=basic.get("character_gender") or equipment_payload.get("character_gender"),
        final_stats=stats,
        equipment_list=equipment_items,
        union_info=union_status,
        v_matrix=normalise_vmatrix(raw.get("vmatrix")),
        hexa_core=normalise_hexamatrix(raw.get("hexamatrix")),
        ability_info=normalise_ability(raw.get("ability")),
        hyper_stats=normalise_hyper_stats(raw.get("hyper_stat")),
    )

    state: AgentState = {
        "character_name": profile.character_name,
        "world_name": profile.world_name,
        "ocid": str(raw.get("ocid") or ""),
        "raw_api_results": {"nexon": make_json_safe(raw)},
        "character_profile": profile,
        "character_stats": stats,
        "equipment_items": equipment_items,
        "union_status": union_status,
    }
    if user_query is not None:
        state["user_query"] = user_query
    return state


def normalise_character_stats(payload: dict[str, Any]) -> CharacterStatDetail:
    final_stats = payload.get("final_stat") or []
    stat_map = {
        normalise_stat_name(row.get("stat_name")): row.get("stat_value")
        for row in final_stats
        if isinstance(row, dict)
    }

    return CharacterStatDetail(
        combat_power=int(stat_value(stat_map, "combat_power")),
        min_stat_damage=stat_value(stat_map, "min_stat_damage"),
        max_stat_damage=stat_value(stat_map, "max_stat_damage"),
        str_val=int(stat_value(stat_map, "str_val")),
        dex=int(stat_value(stat_map, "dex")),
        int_val=int(stat_value(stat_map, "int_val")),
        luk=int(stat_value(stat_map, "luk")),
        hp=int(stat_value(stat_map, "hp")),
        mp=int(stat_value(stat_map, "mp")),
        damage=stat_value(stat_map, "damage"),
        boss_damage=stat_value(stat_map, "boss_damage"),
        final_damage=stat_value(stat_map, "final_damage"),
        ignore_def=stat_value(stat_map, "ignore_def"),
        crit_rate=stat_value(stat_map, "crit_rate"),
        crit_damage=stat_value(stat_map, "crit_damage"),
        attack_power=int(stat_value(stat_map, "attack_power")),
        magic_power=int(stat_value(stat_map, "magic_power")),
        attack_speed=int(stat_value(stat_map, "attack_speed")),
        buff_duration=int(stat_value(stat_map, "buff_duration")),
        arcane_force=int(stat_value(stat_map, "arcane_force")),
        authentic_force=int(stat_value(stat_map, "authentic_force")),
    )


def normalise_equipment_items(payload: dict[str, Any]) -> list[EquipmentDetail]:
    items = payload.get("item_equipment") or []
    normalised: list[EquipmentDetail] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        item_name = str(item.get("item_name") or "")
        normalised.append(
            EquipmentDetail(
                item_name=item_name,
                part=str(item.get("item_equipment_part") or item.get("item_equipment_slot") or ""),
                item_gender=item.get("item_gender"),
                starforce=int(parse_number(item.get("starforce"), 0)) if item.get("starforce") is not None else None,
                potential_grade=item.get("potential_option_grade"),
                additional_potential_grade=item.get("additional_potential_option_grade"),
                total_stats=normalise_stat_package(item.get("item_total_option")),
                bonus_stats=normalise_stat_package(item.get("item_add_option")),
                scroll_stats=normalise_stat_package(item.get("item_etc_option")),
                set_name=item.get("set_item_name"),
            )
        )
    return normalised


def normalise_union_status(
    union_payload: dict[str, Any],
    artifact_payload: dict[str, Any] | None = None,
) -> UnionStatus:
    artifact = artifact_payload if isinstance(artifact_payload, dict) else {}
    return UnionStatus(
        union_level=int(parse_number(union_payload.get("union_level"), 0)),
        union_grade=str(union_payload.get("union_grade") or ""),
        artifact_level=optional_int(
            union_payload.get("union_artifact_level")
            or artifact.get("union_artifact_level")
        ),
        artifact_exp=int(
            parse_number(
                union_payload.get("union_artifact_exp")
                or artifact.get("union_artifact_exp"),
                0,
            )
        ),
    )


def normalise_stat_package(payload: Any) -> StatPackage | None:
    if not isinstance(payload, dict):
        return None
    return StatPackage(
        str_val=int(parse_number(payload.get("str"), 0)),
        dex_val=int(parse_number(payload.get("dex"), 0)),
        int_val=int(parse_number(payload.get("int"), 0)),
        luk_val=int(parse_number(payload.get("luk"), 0)),
        attack_power=int(parse_number(payload.get("attack_power"), 0)),
        magic_power=int(parse_number(payload.get("magic_power"), 0)),
        hp=int(parse_number(payload.get("max_hp") or payload.get("hp"), 0)),
        boss_damage_percent=parse_number(payload.get("boss_damage"), 0),
        ignore_def_percent=parse_number(payload.get("ignore_monster_armor"), 0),
        final_damage_percent=parse_number(payload.get("final_damage"), 0),
        damage_percent=parse_number(payload.get("damage"), 0),
        crit_damage=parse_number(payload.get("critical_damage"), 0),
        all_stat_percent=parse_number(payload.get("all_stat"), 0),
    )


def normalise_vmatrix(payload: Any) -> dict[str, int] | None:
    if not isinstance(payload, dict) or payload.get("error"):
        return None
    cores = payload.get("character_v_core_equipment") or payload.get("v_core_equipment") or []
    result = {}
    for core in cores:
        if not isinstance(core, dict):
            continue
        name = core.get("v_core_name") or core.get("core_name")
        level = core.get("v_core_level") or core.get("core_level")
        if name:
            result[str(name)] = int(parse_number(level, 0))
    return result or None


def normalise_hexamatrix(payload: Any) -> dict[str, int] | None:
    if not isinstance(payload, dict) or payload.get("error"):
        return None
    cores = payload.get("character_hexa_core_equipment") or payload.get("hexa_core_equipment") or []
    result = {}
    for core in cores:
        if not isinstance(core, dict):
            continue
        name = core.get("hexa_core_name") or core.get("core_name")
        level = core.get("hexa_core_level") or core.get("core_level")
        if name:
            result[str(name)] = int(parse_number(level, 0))
    return result or None


def normalise_ability(payload: Any) -> list[str] | None:
    if not isinstance(payload, dict) or payload.get("error"):
        return None
    rows = payload.get("ability_info") or []
    values = [
        str(row.get("ability_value"))
        for row in rows
        if isinstance(row, dict) and row.get("ability_value")
    ]
    return values or None


def normalise_hyper_stats(payload: Any) -> dict[str, int] | None:
    if not isinstance(payload, dict) or payload.get("error"):
        return None
    rows = payload.get("hyper_stat_preset_1") or payload.get("hyper_stat_preset") or []
    result = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        name = row.get("stat_type")
        level = row.get("stat_level")
        if name:
            result[str(name)] = int(parse_number(level, 0))
    return result or None


def normalise_stat_name(value: Any) -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"\s+", "", text)
    aliases = {
        "전투력": "combat_power",
        "최소스탯공격력": "min_stat_damage",
        "최대스탯공격력": "max_stat_damage",
        "str": "str_val",
        "dex": "dex",
        "int": "int_val",
        "luk": "luk",
        "hp": "hp",
        "mp": "mp",
        "데미지": "damage",
        "보스몬스터데미지": "boss_damage",
        "최종데미지": "final_damage",
        "방어율무시": "ignore_def",
        "크리티컬확률": "crit_rate",
        "크리티컬데미지": "crit_damage",
        "공격력": "attack_power",
        "마력": "magic_power",
        "공격속도": "attack_speed",
        "버프지속시간": "buff_duration",
        "아케인포스": "arcane_force",
        "어센틱포스": "authentic_force",
    }
    return aliases.get(text, text)


def stat_value(stat_map: dict[str, Any], key: str, default: float = 0.0) -> float:
    return parse_number(stat_map.get(key), default)


def parse_number(value: Any, default: float = 0.0) -> float:
    if value in (None, ""):
        return default
    if isinstance(value, int | float):
        return float(value)
    text = str(value)
    match = re.search(r"-?\d+(?:\.\d+)?", text.replace(",", ""))
    if not match:
        return default
    try:
        return float(match.group(0))
    except ValueError:
        return default


def optional_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    return int(parse_number(value, 0))


def extract_character_name_from_query(query: str) -> str:
    text = str(query or "").strip()
    patterns = (
        r"(?:내\s*)?캐릭터(?:는|가|명은|명)?\s*([가-힣A-Za-z0-9_]+?)(?:인데요|인데|이고|으로|로|은|는|이|가|\s|$)",
        r"나는\s*([가-힣A-Za-z0-9_]+?)(?:인데요|인데|이고|으로|로|은|는|이|가|\s|$)",
        r"나\s*([가-힣A-Za-z0-9_]+?)(?:인데요|인데|이고|으로|로|은|는|이|가|\s|$)",
        r"닉네임(?:은|이)?\s*([가-힣A-Za-z0-9_]+?)(?:인데요|인데|이고|으로|로|은|는|이|가|\s|$)",
        r"이름(?:은|이)?\s*([가-힣A-Za-z0-9_]+?)(?:인데요|인데|이고|으로|로|은|는|이|가|\s|$)",
    )
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return clean_character_name(match.group(1))
    return ""


def clean_character_name(value: Any) -> str:
    text = str(value or "").strip()
    return re.sub(r"(인데요|인데|입니다|이고|이라는|라는|은|는|이|가)$", "", text).strip()


def make_json_safe(value: Any) -> Any:
    if is_dataclass(value):
        return make_json_safe(asdict(value))
    if isinstance(value, dict):
        return {str(key): make_json_safe(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [make_json_safe(item) for item in value]
    if isinstance(value, date):
        return value.isoformat()
    return value


def _read_error_body(exc: HTTPError) -> str:
    try:
        body = exc.read().decode("utf-8")
    except Exception:
        return str(exc)
    return body or str(exc)


__all__ = [
    "NexonAPIError",
    "NexonOpenAPIClient",
    "fetch_character_state",
    "nexon_api_node",
    "normalise_raw_character_bundle",
    "normalise_character_stats",
    "normalise_equipment_items",
    "normalise_union_status",
]


def _print_manual_test_summary(state: AgentState) -> None:
    profile = state["character_profile"]
    stats = state["character_stats"]
    union = state["union_status"]
    equipment_items = state["equipment_items"]

    print("=== Character ===")
    print(f"name: {profile.character_name}")
    print(f"world: {profile.world_name}")
    print(f"job: {profile.job_name}")
    print(f"level: {profile.level}")
    print(f"ocid: {state['ocid']}")

    print("\n=== Stats ===")
    print(f"combat_power: {stats.combat_power}")
    print(f"STR/DEX/INT/LUK: {stats.str_val}/{stats.dex}/{stats.int_val}/{stats.luk}")
    print(f"boss_damage: {stats.boss_damage}")
    print(f"ignore_def: {stats.ignore_def}")
    print(f"crit_rate: {stats.crit_rate}")
    print(f"crit_damage: {stats.crit_damage}")
    print(f"arcane_force: {stats.arcane_force}")
    print(f"authentic_force: {stats.authentic_force}")

    print("\n=== Equipment / Union ===")
    print(f"equipment_count: {len(equipment_items)}")
    print(f"union_level: {union.union_level}")
    print(f"union_grade: {union.union_grade}")

    print("\n=== AgentState keys ===")
    print(", ".join(sorted(state.keys())))


if __name__ == "__main__":
    import argparse

    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:
        pass

    parser = argparse.ArgumentParser(description="Fetch Nexon Open API data into AgentState.")
    parser.add_argument("character_name", nargs="?", help="MapleStory character name")
    parser.add_argument("--date", help="Nexon Open API date in YYYY-MM-DD format")
    parser.add_argument("--no-optional", action="store_true", help="Skip optional V/HEXA/ability calls")
    args = parser.parse_args()

    character_name = args.character_name or input("character_name: ").strip()
    try:
        result_state = fetch_character_state(
            character_name=character_name,
            api_date=args.date,
            include_optional=not args.no_optional,
        )
    except NexonAPIError as exc:
        print(f"[NexonAPIError] {exc}")
        raise SystemExit(1) from exc

    _print_manual_test_summary(result_state)

