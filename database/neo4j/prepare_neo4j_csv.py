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
HANDOFF_DATASET_PATH = Path(
    r"C:\Users\Playdata\Downloads\mapleqa_full_handoff_with_raw_2026-05-06\handoff_simplified\maple_chatbot_final_dataset.csv"
)

HANDOFF_SOURCE_CATEGORIES = {
    "official_event",
    "official_notice",
    "official_update",
    "testworld_update",
    "boss_recommendation_rule",
    "equipment_growth_rule",
    "reward_priority_rule",
    "class_5th_core_priority",
    "class_6th_hexa_priority",
    "api_feature_requirements",
}
OFFICIAL_DOCUMENT_CATEGORIES = {
    "official_event",
    "official_notice",
    "official_update",
    "testworld_update",
}
RULE_CATEGORIES = {
    "boss_recommendation_rule",
    "equipment_growth_rule",
    "reward_priority_rule",
    "class_5th_core_priority",
    "class_6th_hexa_priority",
}


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

TRUST_TO_RELIABILITY = {
    "S": "high",
    "A": "high",
    "B": "medium",
    "C": "low",
}


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


def truthy(value):
    return str(value or "").strip().lower() in {"true", "1", "yes", "y"}


def clean_handoff_id(value):
    text = str(value or "").strip()
    return "".join(ch if ch.isalnum() or ch in "_-" else "_" for ch in text)


def trust_to_reliability(value):
    text = str(value or "").strip()
    if text in TRUST_TO_RELIABILITY:
        return TRUST_TO_RELIABILITY[text]
    if "official" in text.lower() or "review" in text.lower():
        return "medium"
    return "medium"


def text_preview(value, limit=1000):
    text = " ".join(str(value or "").split())
    if len(text) > limit:
        return text[:limit].rstrip() + "..."
    return text


def read_handoff_dataset(path=HANDOFF_DATASET_PATH):
    if not path.exists():
        return []
    rows = []
    seen = set()
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            category = row.get("category", "").strip()
            if category not in HANDOFF_SOURCE_CATEGORIES:
                continue
            if not truthy(row.get("is_final_keep")) or not truthy(row.get("rag_ready")):
                continue
            action = row.get("dedup_action", "").strip()
            if not action.startswith("keep"):
                continue
            if str(row.get("dedup_rank", "")).strip() not in {"", "1"}:
                continue
            key = (
                row.get("dedup_group_key")
                or row.get("normalized_url")
                or row.get("source_url")
                or row.get("unified_id")
                or row.get("title")
            )
            key = f"{category}|{key}".strip()
            if key in seen:
                continue
            seen.add(key)
            rows.append(row)
    return rows


def parse_rule_fields(text):
    text = " ".join(str(text or "").split())
    labels = [
        "rule_file",
        "dataset_type",
        "boss",
        "difficulty",
        "minimum level",
        "recommended level",
        "required force",
        "combat power",
        "main stat",
        "damage stats",
        "party",
        "mode",
        "pattern difficulty",
        "practice priority",
        "reward summary",
        "notes",
        "stage",
        "level range",
        "job group",
        "slot",
        "current tier",
        "recommended tier",
        "starforce",
        "potential grade",
        "priority",
        "additional potential",
        "flame score",
        "upgrade priority",
        "condition",
        "reason",
        "reward_source",
        "content_type",
        "item_or_reward",
        "reward_category",
        "progression_stage",
        "value_tier",
        "why_it_matters",
        "class_name",
        "priority_1",
        "priority_2",
        "priority_3",
        "priority_4",
        "implementation_note",
        "review_status",
        "source_url",
    ]
    result = {}
    for index, label in enumerate(labels):
        pattern = label + ":"
        start = text.find(pattern)
        if start == -1:
            continue
        start += len(pattern)
        end_candidates = []
        for next_label in labels:
            next_pattern = " " + next_label + ":"
            next_pos = text.find(next_pattern, start)
            if next_pos != -1:
                end_candidates.append(next_pos)
        end = min(end_candidates) if end_candidates else len(text)
        result[label] = text[start:end].strip(" ,")
    return result


def extract_number(text, default=""):
    import re

    match = re.search(r"-?\d+(?:\.\d+)?", str(text or ""))
    return match.group(0) if match else default


def extract_named_number(text, name, default=""):
    import re

    pattern = rf"{name}\s+(-?\d+(?:\.\d+)?)"
    match = re.search(pattern, str(text or ""), flags=re.IGNORECASE)
    return match.group(1) if match else default


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
                "url": row.get("url", row.get("relative_path", "")),
                "trust_level": "medium",
                "collected_at": "",
                "text_preview": "",
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
            "url": "",
            "trust_level": "high",
            "collected_at": "",
            "text_preview": "",
            "reliability": "high",
        },
        {
            "source_id": "source_domain",
            "title": "common/domain.py",
            "category": "project_docs",
            "source_type": "python",
            "relative_path": "common/domain.py",
            "url": "",
            "trust_level": "high",
            "collected_at": "",
            "text_preview": "",
            "reliability": "high",
        },
    ]
    for source in project_sources:
        if source["source_id"] not in seen:
            rows.append(source)
    return rows


def build_handoff_sources(handoff_rows):
    rows = []
    seen = set()
    for row in handoff_rows:
        source_id = "source_" + clean_handoff_id(row.get("unified_id") or row.get("doc_id"))
        if source_id in seen:
            continue
        seen.add(source_id)
        url = row.get("normalized_url") or row.get("source_url") or ""
        rows.append(
            {
                "source_id": source_id,
                "title": row.get("title") or row.get("primary_name") or source_id,
                "category": row.get("category", ""),
                "source_type": row.get("source_type", ""),
                "relative_path": url,
                "url": url,
                "trust_level": row.get("trust_level", ""),
                "collected_at": row.get("collected_at", ""),
                "text_preview": text_preview(row.get("rag_text") or row.get("text_preview"), 1000),
                "reliability": trust_to_reliability(row.get("trust_level")),
            }
        )
    return rows


def append_unique_by_id(rows, new_rows, id_key):
    seen = {row[id_key] for row in rows if row.get(id_key)}
    for row in new_rows:
        if row.get(id_key) and row[id_key] not in seen:
            rows.append(row)
            seen.add(row[id_key])


def unique_rows(rows, keys):
    unique = []
    seen = set()
    for row in rows:
        key = tuple(row.get(item, "") for item in keys)
        if key in seen:
            continue
        seen.add(key)
        unique.append(row)
    return unique


def build_handoff_graph_rows(handoff_rows):
    events = []
    bosses = []
    requirements = []
    equipment = []
    rewards = []
    jobs = []
    boss_requirements = []
    boss_rewards = []
    source_mentions = []

    seen_events = set()
    seen_bosses = set()
    seen_requirements = set()
    seen_equipment = set()
    seen_rewards = set()
    seen_jobs = set()
    seen_mentions = set()
    seen_boss_requirements = set()
    seen_boss_rewards = set()

    def add_mention(source_id, label, entity_id):
        key = (source_id, label, entity_id)
        if source_id and entity_id and key not in seen_mentions:
            source_mentions.append({"source_id": source_id, "entity_label": label, "entity_id": entity_id})
            seen_mentions.add(key)

    for row in handoff_rows:
        category = row.get("category", "")
        source_id = "source_" + clean_handoff_id(row.get("unified_id") or row.get("doc_id"))
        title = row.get("title") or row.get("primary_name") or ""
        primary_name = (row.get("primary_name") or title).strip()
        fields = parse_rule_fields(row.get("rag_text") or "")

        if category == "official_event" and primary_name:
            event_id = "event_" + stable_id(primary_name)
            if event_id not in seen_events:
                events.append(
                    {
                        "event_id": event_id,
                        "name": primary_name,
                        "event_type": "official_event",
                        "target_user": "all",
                        "description": text_preview(row.get("rag_text") or title, 300),
                        "start_date": "",
                        "end_date": "",
                    }
                )
                seen_events.add(event_id)
            add_mention(source_id, "Event", event_id)

        if category in {"official_notice", "official_update", "testworld_update"}:
            # 공식 문서는 Source로 보관하고, 제목/본문에서 핵심 엔티티를 탐지해 MENTIONED_IN으로 연결한다.
            continue

        if category == "boss_recommendation_rule":
            boss_name = fields.get("boss") or primary_name
            difficulty = fields.get("difficulty") or ""
            if boss_name:
                boss_id = "boss_" + stable_id(boss_name, difficulty)
                if boss_id not in seen_bosses:
                    bosses.append(
                        {
                            "boss_id": boss_id,
                            "name": boss_name,
                            "difficulty": difficulty,
                            "required_level": extract_number(fields.get("recommended level") or fields.get("minimum level")),
                            "boss_type": "boss",
                            "description": text_preview(row.get("rag_text"), 300),
                        }
                    )
                    seen_bosses.add(boss_id)
                requirement_id = "requirement_" + clean_handoff_id(row.get("unified_id") or title)
                if requirement_id not in seen_requirements:
                    requirements.append(
                        {
                            "requirement_id": requirement_id,
                            "boss_name": boss_name,
                            "level": extract_number(fields.get("recommended level") or fields.get("minimum level")),
                            "main_stat": extract_named_number(fields.get("main stat"), "recommended")
                            or extract_number(fields.get("main stat")),
                            "arcane_force": extract_named_number(fields.get("required force"), "arcane"),
                            "boss_damage": extract_named_number(fields.get("damage stats"), "boss damage"),
                            "ignore_def": extract_named_number(fields.get("damage stats"), "ignore defense"),
                            "authentic_force": extract_named_number(fields.get("required force"), "sacred"),
                            "confidence": row.get("trust_level", ""),
                        }
                    )
                    seen_requirements.add(requirement_id)
                rel_key = (boss_id, requirement_id)
                if rel_key not in seen_boss_requirements:
                    boss_requirements.append({"boss_id": boss_id, "requirement_id": requirement_id})
                    seen_boss_requirements.add(rel_key)
                add_mention(source_id, "Boss", boss_id)

        if category == "equipment_growth_rule":
            slot = fields.get("slot") or primary_name
            tier = fields.get("recommended tier") or fields.get("current tier") or title
            equipment_name = f"{tier} {slot}".strip()
            if equipment_name:
                equipment_id = "equipment_" + stable_id(equipment_name, slot, category)
                if equipment_id not in seen_equipment:
                    equipment.append(
                        {
                            "equipment_id": equipment_id,
                            "name": equipment_name,
                            "part": slot,
                            "slot": slot,
                            "item_type": "equipment_growth_rule",
                            "level_limit": extract_number(fields.get("level range")),
                            "set_name": "",
                        }
                    )
                    seen_equipment.add(equipment_id)
                add_mention(source_id, "EquipmentCatalog", equipment_id)

        if category == "reward_priority_rule":
            boss_name = fields.get("reward_source") or primary_name
            reward_name = fields.get("item_or_reward") or title
            if boss_name:
                boss_id = "boss_" + stable_id(boss_name, "")
                if boss_id not in seen_bosses:
                    bosses.append(
                        {
                            "boss_id": boss_id,
                            "name": boss_name,
                            "difficulty": "",
                            "required_level": "",
                            "boss_type": "boss",
                            "description": text_preview(row.get("rag_text"), 300),
                        }
                    )
                    seen_bosses.add(boss_id)
                add_mention(source_id, "Boss", boss_id)
            if reward_name:
                reward_id = "reward_" + stable_id(reward_name)
                if reward_id not in seen_rewards:
                    rewards.append(
                        {
                            "reward_id": reward_id,
                            "name": reward_name,
                            "reward_type": fields.get("reward_category") or "reward",
                            "value_type": fields.get("value_tier") or "",
                            "description": fields.get("why_it_matters") or text_preview(row.get("rag_text"), 300),
                        }
                    )
                    seen_rewards.add(reward_id)
                add_mention(source_id, "Reward", reward_id)
                if boss_name:
                    rel_key = (boss_id, reward_id)
                    if rel_key not in seen_boss_rewards:
                        boss_rewards.append({"boss_id": boss_id, "reward_id": reward_id})
                        seen_boss_rewards.add(rel_key)

        if category in {"class_5th_core_priority", "class_6th_hexa_priority"}:
            job_name = fields.get("class_name") or primary_name
            if job_name:
                job_id = "job_" + stable_id(job_name)
                if job_id not in seen_jobs:
                    jobs.append(
                        {
                            "job_id": job_id,
                            "name": job_name,
                            "job_group": fields.get("job_group") or fields.get("job group") or "",
                            "main_stat": "",
                            "description": text_preview(row.get("rag_text"), 300),
                        }
                    )
                    seen_jobs.add(job_id)
                add_mention(source_id, "Job", job_id)

    return {
        "events": events,
        "bosses": bosses,
        "requirements": requirements,
        "equipment": equipment,
        "rewards": rewards,
        "jobs": jobs,
        "boss_requirements": boss_requirements,
        "boss_rewards": boss_rewards,
        "source_mentions": source_mentions,
    }


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
    handoff_rows = read_handoff_dataset()

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
    handoff_graph = build_handoff_graph_rows(handoff_rows)
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
    append_unique_by_id(sources, build_handoff_sources(handoff_rows), "source_id")
    append_unique_by_id(jobs, handoff_graph["jobs"], "job_id")
    append_unique_by_id(bosses, handoff_graph["bosses"], "boss_id")
    append_unique_by_id(requirements, handoff_graph["requirements"], "requirement_id")
    append_unique_by_id(equipment, handoff_graph["equipment"], "equipment_id")
    append_unique_by_id(events, handoff_graph["events"], "event_id")
    append_unique_by_id(rewards, handoff_graph["rewards"], "reward_id")

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
    write_csv(
        "sources.csv",
        sources,
        ["source_id", "title", "category", "source_type", "relative_path", "url", "trust_level", "collected_at", "text_preview", "reliability"],
    )

    job_main_stats = [
        {"job_id": job["job_id"], "stat_type_id": stat_by_code[job["main_stat"]]["stat_type_id"]}
        for job in jobs
        if job["main_stat"] in stat_by_code
    ]
    boss_requirements = [
        {"boss_id": boss_by_name[row["boss_name"]]["boss_id"], "requirement_id": row["requirement_id"]}
        for row in requirements
        if row["boss_name"] in boss_by_name and row.get("confidence") == "draft"
    ]
    boss_requirements.extend(handoff_graph["boss_requirements"])
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
    boss_rewards.extend(handoff_graph["boss_rewards"])

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
    source_mentions.extend(handoff_graph["source_mentions"])
    seen_mentions = {(row["source_id"], row["entity_label"], row["entity_id"]) for row in source_mentions}
    for source_id in ["source_domain", "source_openapi"]:
        for stat_type in stat_types:
            key = (source_id, "StatType", stat_type["stat_type_id"])
            if key not in seen_mentions:
                source_mentions.append({"source_id": source_id, "entity_label": "StatType", "entity_id": stat_type["stat_type_id"]})
                seen_mentions.add(key)

    write_csv("rel_job_main_stats.csv", unique_rows(job_main_stats, ["job_id", "stat_type_id"]), ["job_id", "stat_type_id"])
    write_csv("rel_boss_requirements.csv", unique_rows(boss_requirements, ["boss_id", "requirement_id"]), ["boss_id", "requirement_id"])
    write_csv("rel_requirement_stats.csv", unique_rows(requirement_stats, ["requirement_id", "stat_type_id"]), ["requirement_id", "stat_type_id", "value"])
    write_csv("rel_equipment_set_effects.csv", unique_rows(equipment_set_effects, ["equipment_id", "set_effect_id"]), ["equipment_id", "set_effect_id"])
    write_csv("rel_boss_rewards.csv", unique_rows(boss_rewards, ["boss_id", "reward_id"]), ["boss_id", "reward_id"])
    write_csv("rel_event_rewards.csv", unique_rows(event_rewards, ["event_id", "reward_id"]), ["event_id", "reward_id"])
    write_csv("rel_event_contents.csv", unique_rows(event_contents, ["event_id", "content_id"]), ["event_id", "content_id"])
    write_csv("rel_source_mentions.csv", unique_rows(source_mentions, ["source_id", "entity_label", "entity_id"]), ["source_id", "entity_label", "entity_id"])

    manifest = [
        {"file_name": path.name, "row_count": sum(1 for _ in path.open("r", encoding="utf-8-sig")) - 1}
        for path in sorted(OUT_DIR.glob("*.csv"))
    ]
    write_csv("manifest.csv", manifest, ["file_name", "row_count"])
    for row in manifest:
        print(f"{row['file_name']}: {row['row_count']}")


if __name__ == "__main__":
    main()
