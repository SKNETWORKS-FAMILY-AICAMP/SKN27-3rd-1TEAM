import csv
import os
from pathlib import Path

from neo4j import GraphDatabase


BASE_DIR = Path(__file__).resolve().parents[1]
IMPORT_DIR = BASE_DIR / "data" / "neo4j_import"
BATCH_SIZE = 1000


def load_dotenv():
    env_path = BASE_DIR / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def env(name, default):
    return os.environ.get(name, default)


def read_rows(file_name):
    path = IMPORT_DIR / file_name
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def clean_value(key, value):
    if value is None:
        return ""
    value = value.strip()
    if value == "":
        return ""
    if key.endswith("_id") or key in {"entity_id", "source_id"}:
        return value
    try:
        if "." in value:
            return float(value)
        return int(value)
    except ValueError:
        return value


def clean_row(row):
    return {key: clean_value(key, value) for key, value in row.items()}


def run_batch(session, query, rows):
    rows = [clean_row(row) for row in rows]
    for i in range(0, len(rows), BATCH_SIZE):
        session.run(query, rows=rows[i : i + BATCH_SIZE])


def clear_database(session):
    session.run("MATCH (n) DETACH DELETE n")


def create_constraints(session):
    constraints = [
        "CREATE CONSTRAINT job_id IF NOT EXISTS FOR (n:Job) REQUIRE n.job_id IS UNIQUE",
        "CREATE CONSTRAINT stat_type_id IF NOT EXISTS FOR (n:StatType) REQUIRE n.stat_type_id IS UNIQUE",
        "CREATE CONSTRAINT boss_id IF NOT EXISTS FOR (n:Boss) REQUIRE n.boss_id IS UNIQUE",
        "CREATE CONSTRAINT stat_requirement_id IF NOT EXISTS FOR (n:StatRequirement) REQUIRE n.requirement_id IS UNIQUE",
        "CREATE CONSTRAINT equipment_catalog_id IF NOT EXISTS FOR (n:EquipmentCatalog) REQUIRE n.equipment_id IS UNIQUE",
        "CREATE CONSTRAINT set_effect_id IF NOT EXISTS FOR (n:SetEffect) REQUIRE n.set_effect_id IS UNIQUE",
        "CREATE CONSTRAINT event_id IF NOT EXISTS FOR (n:Event) REQUIRE n.event_id IS UNIQUE",
        "CREATE CONSTRAINT reward_id IF NOT EXISTS FOR (n:Reward) REQUIRE n.reward_id IS UNIQUE",
        "CREATE CONSTRAINT content_id IF NOT EXISTS FOR (n:Content) REQUIRE n.content_id IS UNIQUE",
        "CREATE CONSTRAINT source_id IF NOT EXISTS FOR (n:Source) REQUIRE n.source_id IS UNIQUE",
    ]
    for query in constraints:
        session.run(query)


def load_nodes(session):
    node_loads = [
        (
            "stat_types.csv",
            """
            UNWIND $rows AS row
            MERGE (n:StatType {stat_type_id: row.stat_type_id})
            SET n.code = row.code,
                n.domain_field = row.domain_field,
                n.description = row.description
            """,
        ),
        (
            "jobs.csv",
            """
            UNWIND $rows AS row
            MERGE (n:Job {job_id: row.job_id})
            SET n.name = row.name,
                n.job_group = row.job_group,
                n.main_stat = row.main_stat,
                n.description = row.description
            """,
        ),
        (
            "bosses.csv",
            """
            UNWIND $rows AS row
            MERGE (n:Boss {boss_id: row.boss_id})
            SET n.name = row.name,
                n.difficulty = row.difficulty,
                n.required_level = row.required_level,
                n.boss_type = row.boss_type,
                n.description = row.description
            """,
        ),
        (
            "stat_requirements.csv",
            """
            UNWIND $rows AS row
            MERGE (n:StatRequirement {requirement_id: row.requirement_id})
            SET n.boss_name = row.boss_name,
                n.level = row.level,
                n.main_stat = row.main_stat,
                n.arcane_force = row.arcane_force,
                n.boss_damage = row.boss_damage,
                n.ignore_def = row.ignore_def,
                n.authentic_force = row.authentic_force,
                n.confidence = row.confidence
            """,
        ),
        (
            "equipment_catalog.csv",
            """
            UNWIND $rows AS row
            MERGE (n:EquipmentCatalog {equipment_id: row.equipment_id})
            SET n.name = row.name,
                n.part = row.part,
                n.slot = row.slot,
                n.item_type = row.item_type,
                n.level_limit = row.level_limit,
                n.set_name = row.set_name
            """,
        ),
        (
            "set_effects.csv",
            """
            UNWIND $rows AS row
            MERGE (n:SetEffect {set_effect_id: row.set_effect_id})
            SET n.name = row.name,
                n.set_type = row.set_type,
                n.description = row.description
            """,
        ),
        (
            "events.csv",
            """
            UNWIND $rows AS row
            MERGE (n:Event {event_id: row.event_id})
            SET n.name = row.name,
                n.event_type = row.event_type,
                n.target_user = row.target_user,
                n.description = row.description,
                n.start_date = row.start_date,
                n.end_date = row.end_date
            """,
        ),
        (
            "rewards.csv",
            """
            UNWIND $rows AS row
            MERGE (n:Reward {reward_id: row.reward_id})
            SET n.name = row.name,
                n.reward_type = row.reward_type,
                n.value_type = row.value_type,
                n.description = row.description
            """,
        ),
        (
            "contents.csv",
            """
            UNWIND $rows AS row
            MERGE (n:Content {content_id: row.content_id})
            SET n.name = row.name,
                n.content_type = row.content_type,
                n.reset_cycle = row.reset_cycle,
                n.description = row.description
            """,
        ),
        (
            "sources.csv",
            """
            UNWIND $rows AS row
            MERGE (n:Source {source_id: row.source_id})
            SET n.title = row.title,
                n.category = row.category,
                n.source_type = row.source_type,
                n.relative_path = row.relative_path,
                n.url = row.url,
                n.trust_level = row.trust_level,
                n.collected_at = row.collected_at,
                n.text_preview = row.text_preview,
                n.reliability = row.reliability
            """,
        ),
    ]
    for file_name, query in node_loads:
        rows = read_rows(file_name)
        run_batch(session, query, rows)
        print(f"loaded nodes: {file_name} ({len(rows)})")


def load_relationships(session):
    relationship_loads = [
        (
            "rel_job_main_stats.csv",
            """
            UNWIND $rows AS row
            MATCH (j:Job {job_id: row.job_id})
            MATCH (s:StatType {stat_type_id: row.stat_type_id})
            MERGE (j)-[:USES_MAIN_STAT]->(s)
            """,
        ),
        (
            "rel_boss_requirements.csv",
            """
            UNWIND $rows AS row
            MATCH (b:Boss {boss_id: row.boss_id})
            MATCH (r:StatRequirement {requirement_id: row.requirement_id})
            MERGE (b)-[:HAS_REQUIREMENT]->(r)
            """,
        ),
        (
            "rel_requirement_stats.csv",
            """
            UNWIND $rows AS row
            MATCH (r:StatRequirement {requirement_id: row.requirement_id})
            MATCH (s:StatType {stat_type_id: row.stat_type_id})
            MERGE (r)-[rel:REQUIRES_STAT]->(s)
            SET rel.value = row.value
            """,
        ),
        (
            "rel_equipment_set_effects.csv",
            """
            UNWIND $rows AS row
            MATCH (e:EquipmentCatalog {equipment_id: row.equipment_id})
            MATCH (s:SetEffect {set_effect_id: row.set_effect_id})
            MERGE (e)-[:PART_OF_SET]->(s)
            """,
        ),
        (
            "rel_boss_rewards.csv",
            """
            UNWIND $rows AS row
            MATCH (b:Boss {boss_id: row.boss_id})
            MATCH (r:Reward {reward_id: row.reward_id})
            MERGE (b)-[:DROPS_REWARD]->(r)
            """,
        ),
        (
            "rel_event_rewards.csv",
            """
            UNWIND $rows AS row
            MATCH (e:Event {event_id: row.event_id})
            MATCH (r:Reward {reward_id: row.reward_id})
            MERGE (e)-[:PROVIDES_REWARD]->(r)
            """,
        ),
        (
            "rel_event_contents.csv",
            """
            UNWIND $rows AS row
            MATCH (e:Event {event_id: row.event_id})
            MATCH (c:Content {content_id: row.content_id})
            MERGE (e)-[:RELATED_CONTENT]->(c)
            """,
        ),
    ]
    for file_name, query in relationship_loads:
        rows = read_rows(file_name)
        run_batch(session, query, rows)
        print(f"loaded relationships: {file_name} ({len(rows)})")
    load_source_mentions(session)


def load_source_mentions(session):
    rows = read_rows("rel_source_mentions.csv")
    queries = {
        "StatType": """
            UNWIND $rows AS row
            MATCH (s:Source {source_id: row.source_id})
            MATCH (n:StatType {stat_type_id: row.entity_id})
            MERGE (n)-[:MENTIONED_IN]->(s)
        """,
        "Job": """
            UNWIND $rows AS row
            MATCH (s:Source {source_id: row.source_id})
            MATCH (n:Job {job_id: row.entity_id})
            MERGE (n)-[:MENTIONED_IN]->(s)
        """,
        "Boss": """
            UNWIND $rows AS row
            MATCH (s:Source {source_id: row.source_id})
            MATCH (n:Boss {boss_id: row.entity_id})
            MERGE (n)-[:MENTIONED_IN]->(s)
        """,
        "EquipmentCatalog": """
            UNWIND $rows AS row
            MATCH (s:Source {source_id: row.source_id})
            MATCH (n:EquipmentCatalog {equipment_id: row.entity_id})
            MERGE (n)-[:MENTIONED_IN]->(s)
        """,
        "SetEffect": """
            UNWIND $rows AS row
            MATCH (s:Source {source_id: row.source_id})
            MATCH (n:SetEffect {set_effect_id: row.entity_id})
            MERGE (n)-[:MENTIONED_IN]->(s)
        """,
        "Event": """
            UNWIND $rows AS row
            MATCH (s:Source {source_id: row.source_id})
            MATCH (n:Event {event_id: row.entity_id})
            MERGE (n)-[:MENTIONED_IN]->(s)
        """,
        "Reward": """
            UNWIND $rows AS row
            MATCH (s:Source {source_id: row.source_id})
            MATCH (n:Reward {reward_id: row.entity_id})
            MERGE (n)-[:MENTIONED_IN]->(s)
        """,
        "Content": """
            UNWIND $rows AS row
            MATCH (s:Source {source_id: row.source_id})
            MATCH (n:Content {content_id: row.entity_id})
            MERGE (n)-[:MENTIONED_IN]->(s)
        """,
    }
    for label, query in queries.items():
        label_rows = [row for row in rows if row.get("entity_label") == label]
        if label_rows:
            run_batch(session, query, label_rows)
    print(f"loaded relationships: rel_source_mentions.csv ({len(rows)})")


def print_summary(session):
    print("node counts")
    for record in session.run(
        """
        MATCH (n)
        UNWIND labels(n) AS label
        RETURN label, count(*) AS count
        ORDER BY label
        """
    ):
        print(f"- {record['label']}: {record['count']}")

    print("relationship counts")
    for record in session.run(
        """
        MATCH ()-[r]->()
        RETURN type(r) AS type, count(*) AS count
        ORDER BY type
        """
    ):
        print(f"- {record['type']}: {record['count']}")


def main():
    load_dotenv()
    uri = env("NEO4J_URI", "bolt://localhost:7687")
    user = env("NEO4J_USER", "admin")
    password = env("NEO4J_PASSWORD", "admin123")
    database = env("NEO4J_DATABASE", "mapledb")

    driver = GraphDatabase.driver(uri, auth=(user, password))
    with driver.session(database=database) as session:
        clear_database(session)
        create_constraints(session)
        load_nodes(session)
        load_relationships(session)
        print_summary(session)
    driver.close()


if __name__ == "__main__":
    main()
