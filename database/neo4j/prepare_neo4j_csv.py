import csv
import hashlib
import sys
from pathlib import Path


csv.field_size_limit(min(sys.maxsize, 2**31 - 1))

PROJECT_ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = PROJECT_ROOT / "database" / "data" / "neo4j_import"
CONTENT_SPLIT_DIR = PROJECT_ROOT / "database" / "data" / "content_split_csv"
DOWNLOAD_CONTENT_SPLIT_DIR = Path(
    r"C:\Users\Playdata\Downloads\raw_files_csv_2026-05-04\data\processed\content_split_csv"
)


STAT_TYPES = [
    ("STR", "str_val", "CharacterStatDetail.str_val / StatPackage.str_val"),
    ("DEX", "dex", "CharacterStatDetail.dex / StatPackage.dex_val"),
    ("INT", "int_val", "CharacterStatDetail.int_val / StatPackage.int_val"),
    ("LUK", "luk", "CharacterStatDetail.luk / StatPackage.luk_val"),
    ("ATTACK_POWER", "attack_power", "CharacterStatDetail.attack_power / StatPackage.attack_power"),
    ("MAGIC_POWER", "magic_power", "CharacterStatDetail.magic_power / StatPackage.magic_power"),
    ("BOSS_DAMAGE", "boss_damage", "CharacterStatDetail.boss_damage / StatPackage.boss_damage_percent"),
    ("IGNORE_DEF", "ignore_def", "CharacterStatDetail.ignore_def / StatPackage.ignore_def_percent"),
    ("DAMAGE", "damage", "CharacterStatDetail.damage / StatPackage.damage_percent"),
    ("CRIT_RATE", "crit_rate", "CharacterStatDetail.crit_rate"),
    ("CRIT_DAMAGE", "crit_damage", "CharacterStatDetail.crit_damage / StatPackage.crit_damage"),
    ("ARCANE_FORCE", "arcane_force", "CharacterStatDetail.arcane_force"),
    ("AUTHENTIC_FORCE", "authentic_force", "CharacterStatDetail.authentic_force"),
    ("COMBAT_POWER", "combat_power", "CharacterStatDetail.combat_power"),
]

JOBS = [
    ("아델", "전사", "STR", "레프 계열 전사"),
    ("히어로", "전사", "STR", "모험가 전사"),
    ("팔라딘", "전사", "STR", "모험가 전사"),
    ("다크나이트", "전사", "STR", "모험가 전사"),
    ("섀도어", "도적", "LUK", "모험가 도적"),
    ("나이트로드", "도적", "LUK", "모험가 도적"),
    ("듀얼블레이드", "도적", "LUK", "모험가 도적"),
    ("카데나", "도적", "LUK", "노바 계열 도적"),
    ("메르세데스", "궁수", "DEX", "영웅 계열 궁수"),
    ("보우마스터", "궁수", "DEX", "모험가 궁수"),
    ("패스파인더", "궁수", "DEX", "모험가 궁수"),
    ("메카닉", "해적", "DEX", "레지스탕스 해적"),
    ("캡틴", "해적", "DEX", "모험가 해적"),
    ("키네시스", "마법사", "INT", "프렌즈 월드 마법사"),
    ("비숍", "마법사", "INT", "모험가 마법사"),
    ("아크메이지(불,독)", "마법사", "INT", "모험가 마법사"),
    ("은월", "해적", "STR", "영웅 계열 해적"),
]

BOSSES = [
    ("자쿰", "Normal", 50, "daily", "초반 성장 구간 보스"),
    ("카오스 자쿰", "Chaos", 90, "daily", "초중반 장비 파밍 보스"),
    ("노멀 스우", "Normal", 190, "weekly", "블랙헤븐 관련 주간 보스"),
    ("노멀 데미안", "Normal", 190, "weekly", "히어로즈 오브 메이플 관련 주간 보스"),
    ("노멀 루시드", "Normal", 220, "weekly", "아케인 리버 보스"),
    ("노멀 윌", "Normal", 235, "weekly", "아케인 리버 보스"),
    ("하드 루시드", "Hard", 220, "weekly", "상위 아케인 리버 보스"),
    ("하드 윌", "Hard", 235, "weekly", "상위 아케인 리버 보스"),
    ("진 힐라", "Normal", 250, "weekly", "고난도 주간 보스"),
    ("검은 마법사", "Hard", 255, "monthly", "최종장 보스"),
]

STAT_REQUIREMENTS = [
    ("자쿰", 90, 0, 0, 0, 0, 0),
    ("카오스 자쿰", 150, 3000, 0, 50, 0, 0),
    ("노멀 스우", 220, 15000, 0, 150, 85, 0),
    ("노멀 데미안", 220, 15000, 0, 150, 85, 0),
    ("노멀 루시드", 235, 25000, 360, 200, 90, 0),
    ("노멀 윌", 235, 28000, 760, 220, 90, 0),
    ("하드 루시드", 250, 50000, 360, 300, 93, 0),
    ("하드 윌", 250, 55000, 760, 320, 93, 0),
    ("진 힐라", 250, 65000, 900, 350, 94, 0),
    ("검은 마법사", 255, 90000, 1320, 400, 95, 0),
]

SET_EFFECTS = [
    ("루타비스 세트", "boss_equipment", "카오스 루타비스 장비 세트"),
    ("앱솔랩스 세트", "boss_equipment", "스우/데미안 이후 장비 성장 세트"),
    ("아케인셰이드 세트", "boss_equipment", "아케인 리버 상위 장비 세트"),
    ("에테르넬 세트", "boss_equipment", "상위 보스 장비 세트"),
]

EVENTS = [
    ("하이퍼 버닝", "growth", "new_returning", "성장 지원 이벤트"),
    ("코인샵 이벤트", "reward", "all", "이벤트 재화 기반 보상 교환"),
    ("썬데이 메이플", "boost", "all", "주간 강화/성장 보너스 이벤트"),
]

REWARDS = [
    ("강렬한 힘의 결정", "meso", "boss_crystal", "보스 처치 후 판매 가능한 재화성 보상"),
    ("앱솔랩스 장비", "equipment", "gear", "중후반 장비 성장 보상"),
    ("아케인셰이드 장비", "equipment", "gear", "상위 장비 성장 보상"),
    ("경험치 쿠폰", "growth", "exp", "레벨업 속도를 높이는 보상"),
    ("선택 심볼 교환권", "growth", "symbol", "아케인/어센틱 심볼 성장 보상"),
    ("코어 젬스톤", "growth", "v_matrix", "V 매트릭스 성장 보상"),
]

CONTENTS = [
    ("일일 퀘스트", "daily", "daily", "성장 재화와 경험치를 반복 획득하는 콘텐츠"),
    ("주간 보스", "boss", "weekly", "장비와 재화를 획득하는 핵심 보스 콘텐츠"),
    ("몬스터파크", "daily", "daily", "경험치 중심의 성장 콘텐츠"),
    ("유니온", "account_growth", "always", "계정 단위 성장 콘텐츠"),
    ("아케인 리버 일일 콘텐츠", "daily", "daily", "아케인 심볼 성장 콘텐츠"),
    ("어센틱 심볼 일일 콘텐츠", "daily", "daily", "어센틱 심볼 성장 콘텐츠"),
]


def stable_id(*parts):
    text = "|".join("" if p is None else str(p) for p in parts)
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:20]


def read_existing_csv(file_name):
    path = OUT_DIR / file_name
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def read_optional_csv(path):
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def write_csv(file_name, rows, headers):
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUT_DIR / file_name
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=headers, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def detect_set_name(item_name):
    if "앱솔랩스" in item_name:
        return "앱솔랩스 세트"
    if "아케인셰이드" in item_name:
        return "아케인셰이드 세트"
    if "에테르넬" in item_name:
        return "에테르넬 세트"
    if any(token in item_name for token in ("하이네스", "카오스", "파프니르", "루타비스")):
        return "루타비스 세트"
    return ""


def build_equipment_catalog(existing_equipment):
    by_key = {}
    for row in existing_equipment:
        name = (row.get("item_name") or row.get("name") or "").strip()
        if not name:
            continue
        part = (row.get("part") or row.get("item_equipment_part") or "").strip()
        slot = (row.get("slot") or row.get("item_equipment_slot") or part).strip()
        set_name = (row.get("set_name") or detect_set_name(name)).strip()
        key = (name, part, slot)
        if key not in by_key:
            by_key[key] = {
                "equipment_id": "equipment_" + stable_id(name, part, slot),
                "name": name,
                "part": part,
                "slot": slot,
                "item_type": "equipment",
                "level_limit": row.get("base_equipment_level")
                or row.get("item_base_option.base_equipment_level")
                or row.get("level_limit")
                or "",
                "set_name": set_name,
            }

    fallback = [
        ("앱솔랩스 무기", "무기", "무기", "앱솔랩스 세트", 160),
        ("앱솔랩스 견장", "어깨장식", "어깨장식", "앱솔랩스 세트", 160),
        ("아케인셰이드 무기", "무기", "무기", "아케인셰이드 세트", 200),
        ("아케인셰이드 방어구", "방어구", "방어구", "아케인셰이드 세트", 200),
        ("에테르넬 방어구", "방어구", "방어구", "에테르넬 세트", 250),
    ]
    for name, part, slot, set_name, level in fallback:
        key = (name, part, slot)
        by_key.setdefault(
            key,
            {
                "equipment_id": "equipment_" + stable_id(name, part, slot),
                "name": name,
                "part": part,
                "slot": slot,
                "item_type": "equipment",
                "level_limit": level,
                "set_name": set_name,
            },
        )
    return list(by_key.values())


def build_sources(existing_sources):
    rows = []
    seen = set()
    for row in existing_sources:
        source_id = (row.get("source_id") or "").strip()
        title = (row.get("title") or row.get("file_name") or "").strip()
        if not source_id or not title:
            continue
        seen.add(source_id)
        rows.append(
            {
                "source_id": source_id,
                "title": title,
                "category": row.get("category", ""),
                "source_type": row.get("source_type", row.get("extension", "")),
                "relative_path": row.get("relative_path", ""),
                "reliability": "high" if row.get("category") == "nexon_api" else "medium",
            }
        )
    project_sources = [
        {
            "source_id": "source_openapi",
            "title": "docs/openapi.yaml",
            "category": "project_docs",
            "source_type": "yaml",
            "relative_path": "docs/openapi.yaml",
            "reliability": "high",
        },
        {
            "source_id": "source_domain",
            "title": "common/domain.py",
            "category": "project_docs",
            "source_type": "python",
            "relative_path": "common/domain.py",
            "reliability": "high",
        },
    ]
    for source in project_sources:
        if source["source_id"] not in seen:
            rows.append(source)
    return rows


def build_source_mentions(sources, entity_rows):
    mentions = []
    seen = set()
    for source in sources:
        text = f"{source.get('title', '')} {source.get('relative_path', '')}"
        for label, rows, id_key, name_key in entity_rows:
            for entity in rows:
                name = str(entity.get(name_key, "")).strip()
                if not name or name not in text:
                    continue
                key = (source["source_id"], label, entity[id_key])
                if key in seen:
                    continue
                seen.add(key)
                mentions.append(
                    {
                        "source_id": source["source_id"],
                        "entity_label": label,
                        "entity_id": entity[id_key],
                    }
                )
    return mentions


def main():
    existing_equipment = read_existing_csv("equipment_details_catalog.csv")
    for source_dir in [CONTENT_SPLIT_DIR, DOWNLOAD_CONTENT_SPLIT_DIR]:
        existing_equipment.extend(read_optional_csv(source_dir / "json_list__character_item_equipment__item_equipment.csv"))
        existing_equipment.extend(read_optional_csv(source_dir / "json_list__character_item_equipment__dragon_equipment.csv"))
        existing_equipment.extend(read_optional_csv(source_dir / "json_list__character_item_equipment__mechanic_equipment.csv"))
    existing_sources = read_existing_csv("sources.csv")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for path in OUT_DIR.glob("*.csv"):
        path.unlink()

    stat_types = [
        {"stat_type_id": f"stat_{code}", "code": code, "domain_field": field, "description": description}
        for code, field, description in STAT_TYPES
    ]
    jobs = [
        {
            "job_id": "job_" + stable_id(name),
            "name": name,
            "job_group": job_group,
            "main_stat": main_stat,
            "description": description,
        }
        for name, job_group, main_stat, description in JOBS
    ]
    bosses = [
        {
            "boss_id": "boss_" + stable_id(name, difficulty),
            "name": name,
            "difficulty": difficulty,
            "required_level": required_level,
            "boss_type": boss_type,
            "description": description,
        }
        for name, difficulty, required_level, boss_type, description in BOSSES
    ]
    requirements = [
        {
            "requirement_id": "requirement_" + stable_id(name),
            "boss_name": name,
            "level": level,
            "main_stat": main_stat,
            "arcane_force": arcane_force,
            "boss_damage": boss_damage,
            "ignore_def": ignore_def,
            "authentic_force": authentic_force,
            "confidence": "draft",
        }
        for name, level, main_stat, arcane_force, boss_damage, ignore_def, authentic_force in STAT_REQUIREMENTS
    ]
    set_effects = [
        {
            "set_effect_id": "set_" + stable_id(name),
            "name": name,
            "set_type": set_type,
            "description": description,
        }
        for name, set_type, description in SET_EFFECTS
    ]
    equipment = build_equipment_catalog(existing_equipment)
    events = [
        {
            "event_id": "event_" + stable_id(name),
            "name": name,
            "event_type": event_type,
            "target_user": target_user,
            "description": description,
            "start_date": "",
            "end_date": "",
        }
        for name, event_type, target_user, description in EVENTS
    ]
    rewards = [
        {
            "reward_id": "reward_" + stable_id(name),
            "name": name,
            "reward_type": reward_type,
            "value_type": value_type,
            "description": description,
        }
        for name, reward_type, value_type, description in REWARDS
    ]
    contents = [
        {
            "content_id": "content_" + stable_id(name),
            "name": name,
            "content_type": content_type,
            "reset_cycle": reset_cycle,
            "description": description,
        }
        for name, content_type, reset_cycle, description in CONTENTS
    ]
    sources = build_sources(existing_sources)

    boss_by_name = {row["name"]: row for row in bosses}
    reward_by_name = {row["name"]: row for row in rewards}
    content_by_name = {row["name"]: row for row in contents}
    set_by_name = {row["name"]: row for row in set_effects}
    stat_by_code = {row["code"]: row for row in stat_types}

    write_csv("stat_types.csv", stat_types, ["stat_type_id", "code", "domain_field", "description"])
    write_csv("jobs.csv", jobs, ["job_id", "name", "job_group", "main_stat", "description"])
    write_csv("bosses.csv", bosses, ["boss_id", "name", "difficulty", "required_level", "boss_type", "description"])
    write_csv(
        "stat_requirements.csv",
        requirements,
        ["requirement_id", "boss_name", "level", "main_stat", "arcane_force", "boss_damage", "ignore_def", "authentic_force", "confidence"],
    )
    write_csv("equipment_catalog.csv", equipment, ["equipment_id", "name", "part", "slot", "item_type", "level_limit", "set_name"])
    write_csv("set_effects.csv", set_effects, ["set_effect_id", "name", "set_type", "description"])
    write_csv("events.csv", events, ["event_id", "name", "event_type", "target_user", "description", "start_date", "end_date"])
    write_csv("rewards.csv", rewards, ["reward_id", "name", "reward_type", "value_type", "description"])
    write_csv("contents.csv", contents, ["content_id", "name", "content_type", "reset_cycle", "description"])
    write_csv("sources.csv", sources, ["source_id", "title", "category", "source_type", "relative_path", "reliability"])

    job_main_stats = [
        {"job_id": job["job_id"], "stat_type_id": stat_by_code[job["main_stat"]]["stat_type_id"]}
        for job in jobs
        if job["main_stat"] in stat_by_code
    ]
    boss_requirements = [
        {"boss_id": boss_by_name[row["boss_name"]]["boss_id"], "requirement_id": row["requirement_id"]}
        for row in requirements
        if row["boss_name"] in boss_by_name
    ]
    requirement_stats = []
    for row in requirements:
        for code, prop in [
            ("COMBAT_POWER", "main_stat"),
            ("ARCANE_FORCE", "arcane_force"),
            ("BOSS_DAMAGE", "boss_damage"),
            ("IGNORE_DEF", "ignore_def"),
            ("AUTHENTIC_FORCE", "authentic_force"),
        ]:
            if code in stat_by_code and str(row.get(prop, "")).strip() not in ("", "0"):
                requirement_stats.append(
                    {
                        "requirement_id": row["requirement_id"],
                        "stat_type_id": stat_by_code[code]["stat_type_id"],
                        "value": row[prop],
                    }
                )
    equipment_set_effects = [
        {"equipment_id": row["equipment_id"], "set_effect_id": set_by_name[row["set_name"]]["set_effect_id"]}
        for row in equipment
        if row.get("set_name") in set_by_name
    ]
    boss_rewards = []
    for boss in bosses:
        for reward_name in ["강렬한 힘의 결정"]:
            boss_rewards.append({"boss_id": boss["boss_id"], "reward_id": reward_by_name[reward_name]["reward_id"]})
    for boss_name, reward_name in [
        ("노멀 스우", "앱솔랩스 장비"),
        ("노멀 데미안", "앱솔랩스 장비"),
        ("노멀 루시드", "아케인셰이드 장비"),
        ("노멀 윌", "아케인셰이드 장비"),
        ("하드 루시드", "아케인셰이드 장비"),
        ("하드 윌", "아케인셰이드 장비"),
    ]:
        if boss_name in boss_by_name and reward_name in reward_by_name:
            boss_rewards.append({"boss_id": boss_by_name[boss_name]["boss_id"], "reward_id": reward_by_name[reward_name]["reward_id"]})

    event_rewards = []
    for event_name, reward_names in {
        "하이퍼 버닝": ["경험치 쿠폰", "선택 심볼 교환권", "코어 젬스톤"],
        "코인샵 이벤트": ["선택 심볼 교환권", "코어 젬스톤"],
        "썬데이 메이플": ["경험치 쿠폰"],
    }.items():
        event = next(row for row in events if row["name"] == event_name)
        for reward_name in reward_names:
            event_rewards.append({"event_id": event["event_id"], "reward_id": reward_by_name[reward_name]["reward_id"]})

    event_contents = []
    for event_name, content_names in {
        "하이퍼 버닝": ["일일 퀘스트", "몬스터파크"],
        "코인샵 이벤트": ["일일 퀘스트", "주간 보스"],
        "썬데이 메이플": ["주간 보스", "몬스터파크"],
    }.items():
        event = next(row for row in events if row["name"] == event_name)
        for content_name in content_names:
            event_contents.append({"event_id": event["event_id"], "content_id": content_by_name[content_name]["content_id"]})

    source_mentions = build_source_mentions(
        sources,
        [
            ("StatType", stat_types, "stat_type_id", "code"),
            ("Job", jobs, "job_id", "name"),
            ("Boss", bosses, "boss_id", "name"),
            ("EquipmentCatalog", equipment, "equipment_id", "name"),
            ("SetEffect", set_effects, "set_effect_id", "name"),
            ("Event", events, "event_id", "name"),
            ("Reward", rewards, "reward_id", "name"),
            ("Content", contents, "content_id", "name"),
        ],
    )
    seen_mentions = {(row["source_id"], row["entity_label"], row["entity_id"]) for row in source_mentions}
    for source_id in ["source_domain", "source_openapi"]:
        for stat_type in stat_types:
            key = (source_id, "StatType", stat_type["stat_type_id"])
            if key not in seen_mentions:
                source_mentions.append({"source_id": source_id, "entity_label": "StatType", "entity_id": stat_type["stat_type_id"]})
                seen_mentions.add(key)

    write_csv("rel_job_main_stats.csv", job_main_stats, ["job_id", "stat_type_id"])
    write_csv("rel_boss_requirements.csv", boss_requirements, ["boss_id", "requirement_id"])
    write_csv("rel_requirement_stats.csv", requirement_stats, ["requirement_id", "stat_type_id", "value"])
    write_csv("rel_equipment_set_effects.csv", equipment_set_effects, ["equipment_id", "set_effect_id"])
    write_csv("rel_boss_rewards.csv", boss_rewards, ["boss_id", "reward_id"])
    write_csv("rel_event_rewards.csv", event_rewards, ["event_id", "reward_id"])
    write_csv("rel_event_contents.csv", event_contents, ["event_id", "content_id"])
    write_csv("rel_source_mentions.csv", source_mentions, ["source_id", "entity_label", "entity_id"])

    manifest = [
        {"file_name": path.name, "row_count": sum(1 for _ in path.open("r", encoding="utf-8-sig")) - 1}
        for path in sorted(OUT_DIR.glob("*.csv"))
    ]
    write_csv("manifest.csv", manifest, ["file_name", "row_count"])
    for row in manifest:
        print(f"{row['file_name']}: {row['row_count']}")


if __name__ == "__main__":
    main()
