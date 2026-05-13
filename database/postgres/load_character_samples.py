from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from collections import Counter, defaultdict
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import psycopg2
from dotenv import load_dotenv
from psycopg2.extras import Json, RealDictCursor


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


DEFAULT_DATASET = (
    PROJECT_ROOT
    / "database"
    / "mapleqa_full_handoff_with_raw_2026-05-06"
    / "handoff_simplified"
    / "maple_chatbot_final_dataset.csv"
)

CORE_CATEGORIES = {
    "character_basic",
    "character_stat",
    "character_item_equipment",
    "character_symbol_equipment",
    "user_union",
    "user_union_raider",
    "character_set_effect",
    "character_vmatrix",
    "character_hexamatrix",
    "character_hexamatrix_stat",
    "character_ability",
    "character_hyper_stat",
    "character_link_skill",
}

STAT_NAME_TO_COLUMN = {
    "전투력": "combat_power",
    "최소 스탯공격력": "min_stat_damage",
    "최대 스탯공격력": "max_stat_damage",
    "STR": "str_val",
    "DEX": "dex",
    "INT": "int_val",
    "LUK": "luk",
    "HP": "hp",
    "MP": "mp",
    "데미지": "damage",
    "보스 몬스터 데미지": "boss_damage",
    "최종 데미지": "final_damage",
    "방어율 무시": "ignore_def",
    "크리티컬 확률": "crit_rate",
    "크리티컬 데미지": "crit_damage",
    "공격력": "attack_power",
    "마력": "magic_power",
    "공격 속도": "attack_speed",
    "버프 지속시간": "buff_duration",
    "아케인포스": "arcane_force",
    "어센틱포스": "authentic_force",
}

INT_STAT_COLUMNS = {
    "combat_power",
    "min_stat_damage",
    "max_stat_damage",
    "str_val",
    "dex",
    "int_val",
    "luk",
    "hp",
    "mp",
    "attack_power",
    "magic_power",
    "attack_speed",
    "buff_duration",
    "arcane_force",
    "authentic_force",
    "remain_ap",
}


def database_url() -> str:
    load_dotenv()
    return os.getenv("POSTGRES_URI") or os.getenv("DATABASE_URL") or (
        "postgresql://"
        f"{os.getenv('POSTGRES_USER', 'admin')}:"
        f"{os.getenv('POSTGRES_PASSWORD', 'admin123')}@"
        f"{os.getenv('POSTGRES_HOST', 'localhost')}:"
        f"{os.getenv('POSTGRES_PORT', '5432')}/"
        f"{os.getenv('POSTGRES_DB', 'mapledb')}"
    )


def raise_csv_field_limit() -> None:
    limit = sys.maxsize
    while True:
        try:
            csv.field_size_limit(limit)
            return
        except OverflowError:
            limit = int(limit / 10)


def clean_text(value: Any, limit: int | None = None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if text == "":
        return None
    if limit is not None:
        return text[:limit]
    return text


def to_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    text = str(value).replace(",", "").replace("%", "").strip()
    if text == "":
        return None
    try:
        return int(Decimal(text))
    except (InvalidOperation, ValueError):
        return None


def to_decimal(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    text = str(value).replace(",", "").replace("%", "").strip()
    if text == "":
        return None
    try:
        return Decimal(text)
    except InvalidOperation:
        return None


def to_bool(value: Any) -> bool | None:
    if value is None or value == "":
        return None
    return str(value).strip().lower() in {"1", "true", "t", "yes", "y"}


def parse_payload(row: dict[str, str]) -> dict[str, Any] | None:
    raw = row.get("rag_text") or row.get("text_preview") or "{}"
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    return payload


def read_character_rows(dataset_path: Path) -> dict[str, list[dict[str, Any]]]:
    raise_csv_field_limit()
    rows_by_category: dict[str, list[dict[str, Any]]] = defaultdict(list)
    with dataset_path.open("r", encoding="utf-8-sig", newline="") as file:
        for row in csv.DictReader(file):
            category = row.get("category") or ""
            if category not in CORE_CATEGORIES:
                continue
            payload = parse_payload(row)
            if payload is None or not payload.get("ocid"):
                continue
            rows_by_category[category].append(payload)
    return rows_by_category


def ensure_sample_user(cur, username: str) -> str:
    cur.execute(
        """
        INSERT INTO users (username)
        VALUES (%s)
        ON CONFLICT (username) DO UPDATE SET updated_at = now()
        RETURNING id
        """,
        (username,),
    )
    return cur.fetchone()["id"]


def clear_sample_characters(cur, user_id: str) -> int:
    cur.execute(
        """
        DELETE FROM characters
        WHERE user_id = %s
        RETURNING id
        """,
        (user_id,),
    )
    return len(cur.fetchall())


def insert_characters(cur, user_id: str, rows: list[dict[str, Any]]) -> dict[str, str]:
    ocid_to_character_id: dict[str, str] = {}
    for payload in rows:
        cur.execute(
            """
            INSERT INTO characters (
                user_id, ocid, character_name, world_name, character_gender,
                character_class, character_class_level, character_level,
                character_exp, character_exp_rate, character_guild_name,
                character_image, character_date_create, access_flag,
                liberation_quest_clear, synced_at
            )
            VALUES (
                %s, %s, %s, %s, %s,
                %s, %s, %s,
                %s, %s, %s,
                %s, %s, %s,
                %s, now()
            )
            ON CONFLICT (ocid) DO UPDATE SET
                character_name = EXCLUDED.character_name,
                world_name = EXCLUDED.world_name,
                character_gender = EXCLUDED.character_gender,
                character_class = EXCLUDED.character_class,
                character_class_level = EXCLUDED.character_class_level,
                character_level = EXCLUDED.character_level,
                character_exp = EXCLUDED.character_exp,
                character_exp_rate = EXCLUDED.character_exp_rate,
                character_guild_name = EXCLUDED.character_guild_name,
                character_image = EXCLUDED.character_image,
                character_date_create = EXCLUDED.character_date_create,
                access_flag = EXCLUDED.access_flag,
                liberation_quest_clear = EXCLUDED.liberation_quest_clear,
                synced_at = now(),
                updated_at = now()
            RETURNING id
            """,
            (
                user_id,
                clean_text(payload.get("ocid"), 64),
                clean_text(payload.get("character_name"), 50) or "unknown",
                clean_text(payload.get("world_name"), 30),
                clean_text(payload.get("character_gender"), 10),
                clean_text(payload.get("character_class"), 50),
                clean_text(payload.get("character_class_level"), 10),
                to_int(payload.get("character_level")),
                to_int(payload.get("character_exp")),
                to_decimal(payload.get("character_exp_rate")),
                clean_text(payload.get("character_guild_name"), 50),
                clean_text(payload.get("character_image")),
                clean_text(payload.get("character_date_create")),
                to_bool(payload.get("access_flag")),
                to_bool(payload.get("liberation_quest_clear")),
            ),
        )
        ocid_to_character_id[str(payload["ocid"])] = cur.fetchone()["id"]
    return ocid_to_character_id


def insert_stats(cur, rows: list[dict[str, Any]], character_ids: dict[str, str]) -> int:
    count = 0
    for payload in rows:
        character_id = character_ids.get(str(payload.get("ocid")))
        if character_id is None:
            continue
        values: dict[str, Any] = {column: None for column in STAT_NAME_TO_COLUMN.values()}
        for stat in payload.get("final_stat") or []:
            column = STAT_NAME_TO_COLUMN.get(stat.get("stat_name"))
            if column is None:
                continue
            raw_value = stat.get("stat_value")
            values[column] = to_int(raw_value) if column in INT_STAT_COLUMNS else to_decimal(raw_value)
        values["remain_ap"] = to_int(payload.get("remain_ap"))
        cur.execute(
            """
            INSERT INTO char_stat (
                character_id, combat_power, min_stat_damage, max_stat_damage,
                str_val, dex, int_val, luk, hp, mp, damage, boss_damage,
                final_damage, ignore_def, crit_rate, crit_damage,
                attack_power, magic_power, attack_speed, buff_duration,
                arcane_force, authentic_force, remain_ap, raw_final_stat
            )
            VALUES (
                %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s, %s, %s
            )
            """,
            (
                character_id,
                values["combat_power"],
                values["min_stat_damage"],
                values["max_stat_damage"],
                values["str_val"],
                values["dex"],
                values["int_val"],
                values["luk"],
                values["hp"],
                values["mp"],
                values["damage"],
                values["boss_damage"],
                values["final_damage"],
                values["ignore_def"],
                values["crit_rate"],
                values["crit_damage"],
                values["attack_power"],
                values["magic_power"],
                values["attack_speed"],
                values["buff_duration"],
                values["arcane_force"],
                values["authentic_force"],
                values["remain_ap"],
                Json(payload.get("final_stat") or []),
            ),
        )
        count += 1
    return count


def equipment_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    preset_no = to_int(payload.get("preset_no"))
    for key in ("item_equipment", "dragon_equipment", "mechanic_equipment"):
        for item in payload.get(key) or []:
            if isinstance(item, dict):
                item = dict(item)
                item["_preset_no"] = preset_no
                rows.append(item)
    return rows


def insert_equipment(cur, rows: list[dict[str, Any]], character_ids: dict[str, str]) -> int:
    count = 0
    for payload in rows:
        character_id = character_ids.get(str(payload.get("ocid")))
        if character_id is None:
            continue
        for item in equipment_rows(payload):
            cur.execute(
                """
                INSERT INTO char_equipment (
                    character_id, preset_no, part, slot, item_name, item_gender,
                    starforce, potential_grade, additional_potential_grade,
                    set_name, total_stats, bonus_stats, scroll_stats
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    character_id,
                    item.get("_preset_no"),
                    clean_text(item.get("item_equipment_part"), 50),
                    clean_text(item.get("item_equipment_slot"), 50),
                    clean_text(item.get("item_name"), 120),
                    clean_text(item.get("item_gender"), 10),
                    to_int(item.get("starforce")),
                    clean_text(item.get("potential_option_grade"), 30),
                    clean_text(item.get("additional_potential_option_grade"), 30),
                    clean_text(item.get("set_name"), 120),
                    Json(item.get("item_total_option") or {}),
                    Json(item.get("item_add_option") or {}),
                    Json(item.get("item_etc_option") or {}),
                ),
            )
            count += 1
    return count


def insert_symbols(cur, rows: list[dict[str, Any]], character_ids: dict[str, str]) -> int:
    count = 0
    for payload in rows:
        character_id = character_ids.get(str(payload.get("ocid")))
        if character_id is None:
            continue
        for symbol in payload.get("symbol") or []:
            cur.execute(
                """
                INSERT INTO char_symbols (
                    character_id, symbol_name, symbol_force, symbol_level,
                    symbol_str, symbol_dex, symbol_int, symbol_luk, symbol_hp,
                    symbol_growth_count, symbol_require_growth_count, raw_payload
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    character_id,
                    clean_text(symbol.get("symbol_name"), 100) or "unknown",
                    clean_text(symbol.get("symbol_force"), 30),
                    to_int(symbol.get("symbol_level")),
                    to_int(symbol.get("symbol_str")),
                    to_int(symbol.get("symbol_dex")),
                    to_int(symbol.get("symbol_int")),
                    to_int(symbol.get("symbol_luk")),
                    to_int(symbol.get("symbol_hp")),
                    to_int(symbol.get("symbol_growth_count")),
                    to_int(symbol.get("symbol_require_growth_count")),
                    Json(symbol),
                ),
            )
            count += 1
    return count


def upsert_union_basic(cur, rows: list[dict[str, Any]], character_ids: dict[str, str]) -> int:
    count = 0
    for payload in rows:
        character_id = character_ids.get(str(payload.get("ocid")))
        if character_id is None:
            continue
        cur.execute(
            """
            INSERT INTO char_union (
                character_id, union_level, union_grade, union_artifact_level,
                union_artifact_exp, union_artifact_point, artifact_payload
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (character_id) DO UPDATE SET
                union_level = EXCLUDED.union_level,
                union_grade = EXCLUDED.union_grade,
                union_artifact_level = EXCLUDED.union_artifact_level,
                union_artifact_exp = EXCLUDED.union_artifact_exp,
                union_artifact_point = EXCLUDED.union_artifact_point,
                artifact_payload = EXCLUDED.artifact_payload,
                updated_at = now()
            """,
            (
                character_id,
                to_int(payload.get("union_level")),
                clean_text(payload.get("union_grade"), 50),
                to_int(payload.get("union_artifact_level")),
                to_int(payload.get("union_artifact_exp")),
                to_int(payload.get("union_artifact_point")),
                Json(payload),
            ),
        )
        count += 1
    return count


def upsert_union_raider(cur, rows: list[dict[str, Any]], character_ids: dict[str, str]) -> int:
    count = 0
    for payload in rows:
        character_id = character_ids.get(str(payload.get("ocid")))
        if character_id is None:
            continue
        cur.execute(
            """
            INSERT INTO char_union (character_id, raider_payload)
            VALUES (%s, %s)
            ON CONFLICT (character_id) DO UPDATE SET
                raider_payload = EXCLUDED.raider_payload,
                updated_at = now()
            """,
            (character_id, Json(payload)),
        )
        count += 1
    return count


def insert_set_effects(cur, rows: list[dict[str, Any]], character_ids: dict[str, str]) -> int:
    count = 0
    for payload in rows:
        character_id = character_ids.get(str(payload.get("ocid")))
        if character_id is None:
            continue
        for set_effect in payload.get("set_effect") or []:
            info_rows = set_effect.get("set_effect_info") or [None]
            for info in info_rows:
                cur.execute(
                    """
                    INSERT INTO char_set_effects (
                        character_id, set_name, total_set_count, set_count,
                        set_option, set_option_full, raw_payload
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        character_id,
                        clean_text(set_effect.get("set_name"), 120) or "unknown",
                        to_int(set_effect.get("total_set_count")),
                        to_int(info.get("set_count") if isinstance(info, dict) else None),
                        clean_text(info.get("set_option") if isinstance(info, dict) else None),
                        clean_text(set_effect.get("set_option_full")),
                        Json(set_effect),
                    ),
                )
                count += 1
    return count


def insert_vmatrix(cur, rows: list[dict[str, Any]], character_ids: dict[str, str]) -> int:
    count = 0
    for payload in rows:
        character_id = character_ids.get(str(payload.get("ocid")))
        if character_id is None:
            continue
        for core in payload.get("character_v_core_equipment") or []:
            cur.execute(
                """
                INSERT INTO char_cores (
                    character_id, core_group, slot_id, slot_level,
                    core_name, core_type, core_level, skill_payload
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    character_id,
                    "v_matrix",
                    to_int(core.get("slot_id")),
                    to_int(core.get("slot_level")),
                    clean_text(core.get("v_core_name"), 150),
                    clean_text(core.get("v_core_type"), 50),
                    to_int(core.get("v_core_level")),
                    Json(core),
                ),
            )
            count += 1
    return count


def insert_hexamatrix(cur, rows: list[dict[str, Any]], character_ids: dict[str, str]) -> int:
    count = 0
    for payload in rows:
        character_id = character_ids.get(str(payload.get("ocid")))
        if character_id is None:
            continue
        for core in payload.get("character_hexa_core_equipment") or []:
            cur.execute(
                """
                INSERT INTO char_cores (
                    character_id, core_group, core_name, core_type,
                    core_level, skill_payload
                )
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (
                    character_id,
                    "hexa_matrix",
                    clean_text(core.get("hexa_core_name"), 150),
                    clean_text(core.get("hexa_core_type"), 50),
                    to_int(core.get("hexa_core_level")),
                    Json(core),
                ),
            )
            count += 1
    return count


def insert_hexa_stats(cur, rows: list[dict[str, Any]], character_ids: dict[str, str]) -> int:
    count = 0
    list_keys = (
        "character_hexa_stat_core",
        "character_hexa_stat_core_2",
        "character_hexa_stat_core_3",
        "preset_hexa_stat_core",
        "preset_hexa_stat_core_2",
        "preset_hexa_stat_core_3",
    )
    for payload in rows:
        character_id = character_ids.get(str(payload.get("ocid")))
        if character_id is None:
            continue
        for key in list_keys:
            for stat_core in payload.get(key) or []:
                cur.execute(
                    """
                    INSERT INTO char_cores (
                        character_id, core_group, slot_id, main_stat_name,
                        main_stat_level, stat_payload
                    )
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    (
                        character_id,
                        key,
                        to_int(stat_core.get("slot_id")),
                        clean_text(stat_core.get("main_stat_name"), 80),
                        to_int(stat_core.get("main_stat_level")),
                        Json(stat_core),
                    ),
                )
                count += 1
    return count


def insert_ability_options(cur, rows: list[dict[str, Any]], character_ids: dict[str, str]) -> int:
    count = 0
    for payload in rows:
        character_id = character_ids.get(str(payload.get("ocid")))
        if character_id is None:
            continue
        preset_no = to_int(payload.get("preset_no"))
        for option in payload.get("ability_info") or []:
            cur.execute(
                """
                INSERT INTO char_skill_options (
                    character_id, option_type, preset_no, slot_no,
                    option_grade, option_value, raw_payload
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    character_id,
                    "ability",
                    preset_no,
                    to_int(option.get("ability_no")),
                    clean_text(option.get("ability_grade"), 30),
                    clean_text(option.get("ability_value")),
                    Json(option),
                ),
            )
            count += 1
    return count


def insert_hyper_stat_options(cur, rows: list[dict[str, Any]], character_ids: dict[str, str]) -> int:
    count = 0
    for payload in rows:
        character_id = character_ids.get(str(payload.get("ocid")))
        if character_id is None:
            continue
        for preset_no in (1, 2, 3):
            key = f"hyper_stat_preset_{preset_no}"
            for index, option in enumerate(payload.get(key) or [], start=1):
                cur.execute(
                    """
                    INSERT INTO char_skill_options (
                        character_id, option_type, preset_no, slot_no,
                        option_name, option_level, option_value, raw_payload
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        character_id,
                        "hyper_stat",
                        preset_no,
                        index,
                        clean_text(option.get("stat_type"), 120),
                        to_int(option.get("stat_level")),
                        clean_text(option.get("stat_increase")),
                        Json(option),
                    ),
                )
                count += 1
    return count


def insert_link_skill_options(cur, rows: list[dict[str, Any]], character_ids: dict[str, str]) -> int:
    count = 0
    for payload in rows:
        character_id = character_ids.get(str(payload.get("ocid")))
        if character_id is None:
            continue
        for index, skill in enumerate(payload.get("character_link_skill") or [], start=1):
            cur.execute(
                """
                INSERT INTO char_skill_options (
                    character_id, option_type, slot_no, option_name,
                    option_level, option_value, option_effect, raw_payload
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    character_id,
                    "link_skill",
                    index,
                    clean_text(skill.get("skill_name"), 120),
                    to_int(skill.get("skill_level")),
                    clean_text(skill.get("skill_effect")),
                    clean_text(skill.get("skill_description")),
                    Json(skill),
                ),
            )
            count += 1
    return count


def expected_counts(rows_by_category: dict[str, list[dict[str, Any]]]) -> Counter[str]:
    counts: Counter[str] = Counter()
    counts["characters"] = len(rows_by_category.get("character_basic", []))
    counts["char_stat"] = len(rows_by_category.get("character_stat", []))
    counts["char_equipment"] = sum(
        len(equipment_rows(payload)) for payload in rows_by_category.get("character_item_equipment", [])
    )
    counts["char_symbols"] = sum(
        len(payload.get("symbol") or []) for payload in rows_by_category.get("character_symbol_equipment", [])
    )
    counts["char_union_basic_payloads"] = len(rows_by_category.get("user_union", []))
    counts["char_union_raider_payloads"] = len(rows_by_category.get("user_union_raider", []))
    counts["char_set_effects"] = sum(
        sum(len(item.get("set_effect_info") or [None]) for item in payload.get("set_effect") or [])
        for payload in rows_by_category.get("character_set_effect", [])
    )
    counts["char_cores"] = sum(
        len(payload.get("character_v_core_equipment") or []) for payload in rows_by_category.get("character_vmatrix", [])
    )
    counts["char_cores"] += sum(
        len(payload.get("character_hexa_core_equipment") or [])
        for payload in rows_by_category.get("character_hexamatrix", [])
    )
    for payload in rows_by_category.get("character_hexamatrix_stat", []):
        for key in (
            "character_hexa_stat_core",
            "character_hexa_stat_core_2",
            "character_hexa_stat_core_3",
            "preset_hexa_stat_core",
            "preset_hexa_stat_core_2",
            "preset_hexa_stat_core_3",
        ):
            counts["char_cores"] += len(payload.get(key) or [])
    counts["char_skill_options"] = sum(
        len(payload.get("ability_info") or []) for payload in rows_by_category.get("character_ability", [])
    )
    counts["char_skill_options"] += sum(
        sum(len(payload.get(f"hyper_stat_preset_{preset_no}") or []) for preset_no in (1, 2, 3))
        for payload in rows_by_category.get("character_hyper_stat", [])
    )
    counts["char_skill_options"] += sum(
        len(payload.get("character_link_skill") or []) for payload in rows_by_category.get("character_link_skill", [])
    )
    return counts


def load_character_samples(dataset_path: Path, dsn: str, username: str, dry_run: bool = False) -> Counter[str]:
    rows_by_category = read_character_rows(dataset_path)
    counts = expected_counts(rows_by_category)
    if dry_run:
        return counts

    with psycopg2.connect(dsn, cursor_factory=RealDictCursor) as conn:
        with conn.cursor() as cur:
            user_id = ensure_sample_user(cur, username)
            clear_sample_characters(cur, user_id)
            character_ids = insert_characters(cur, user_id, rows_by_category.get("character_basic", []))
            counts["characters"] = len(character_ids)
            counts["char_stat"] = insert_stats(cur, rows_by_category.get("character_stat", []), character_ids)
            counts["char_equipment"] = insert_equipment(
                cur, rows_by_category.get("character_item_equipment", []), character_ids
            )
            counts["char_symbols"] = insert_symbols(
                cur, rows_by_category.get("character_symbol_equipment", []), character_ids
            )
            counts["char_union_basic_payloads"] = upsert_union_basic(
                cur, rows_by_category.get("user_union", []), character_ids
            )
            counts["char_union_raider_payloads"] = upsert_union_raider(
                cur, rows_by_category.get("user_union_raider", []), character_ids
            )
            counts["char_set_effects"] = insert_set_effects(
                cur, rows_by_category.get("character_set_effect", []), character_ids
            )
            core_count = insert_vmatrix(cur, rows_by_category.get("character_vmatrix", []), character_ids)
            core_count += insert_hexamatrix(cur, rows_by_category.get("character_hexamatrix", []), character_ids)
            core_count += insert_hexa_stats(cur, rows_by_category.get("character_hexamatrix_stat", []), character_ids)
            counts["char_cores"] = core_count
            skill_count = insert_ability_options(cur, rows_by_category.get("character_ability", []), character_ids)
            skill_count += insert_hyper_stat_options(
                cur, rows_by_category.get("character_hyper_stat", []), character_ids
            )
            skill_count += insert_link_skill_options(
                cur, rows_by_category.get("character_link_skill", []), character_ids
            )
            counts["char_skill_options"] = skill_count
        conn.commit()
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description="Load Maple character API samples from handoff CSV.")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--dsn", default=database_url())
    parser.add_argument("--username", default="sample_user")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    counts = load_character_samples(
        dataset_path=args.dataset,
        dsn=args.dsn,
        username=args.username,
        dry_run=args.dry_run,
    )
    for key in sorted(counts):
        print(f"{key}: {counts[key]}")


if __name__ == "__main__":
    main()
