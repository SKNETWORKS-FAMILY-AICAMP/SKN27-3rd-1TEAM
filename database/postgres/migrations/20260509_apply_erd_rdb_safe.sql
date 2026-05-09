-- Apply the updated ERD to the existing RDB without deleting loaded RAG/PGVector data.
-- Notes:
-- - Keep document_embeddings.embedding as vector(768) for google/embeddinggemma-300m.
-- - Keep trust_level as varchar(80) because the loaded dataset contains project review labels.
-- - Do not drop extra columns from existing populated tables.

CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS vector;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'char_stat' AND column_name = 'str_value'
    ) AND NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'char_stat' AND column_name = 'str_val'
    ) THEN
        ALTER TABLE char_stat RENAME COLUMN str_value TO str_val;
    END IF;

    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'char_stat' AND column_name = 'dex_value'
    ) AND NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'char_stat' AND column_name = 'dex'
    ) THEN
        ALTER TABLE char_stat RENAME COLUMN dex_value TO dex;
    END IF;

    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'char_stat' AND column_name = 'int_value'
    ) AND NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'char_stat' AND column_name = 'int_val'
    ) THEN
        ALTER TABLE char_stat RENAME COLUMN int_value TO int_val;
    END IF;

    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'char_stat' AND column_name = 'luk_value'
    ) AND NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'char_stat' AND column_name = 'luk'
    ) THEN
        ALTER TABLE char_stat RENAME COLUMN luk_value TO luk;
    END IF;

    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'char_stat' AND column_name = 'damage_percent'
    ) AND NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'char_stat' AND column_name = 'damage'
    ) THEN
        ALTER TABLE char_stat RENAME COLUMN damage_percent TO damage;
    END IF;

    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'char_stat' AND column_name = 'boss_damage_percent'
    ) AND NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'char_stat' AND column_name = 'boss_damage'
    ) THEN
        ALTER TABLE char_stat RENAME COLUMN boss_damage_percent TO boss_damage;
    END IF;

    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'char_stat' AND column_name = 'final_damage_percent'
    ) AND NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'char_stat' AND column_name = 'final_damage'
    ) THEN
        ALTER TABLE char_stat RENAME COLUMN final_damage_percent TO final_damage;
    END IF;

    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'char_stat' AND column_name = 'ignore_def_percent'
    ) AND NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'char_stat' AND column_name = 'ignore_def'
    ) THEN
        ALTER TABLE char_stat RENAME COLUMN ignore_def_percent TO ignore_def;
    END IF;

    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'char_stat' AND column_name = 'crit_rate_percent'
    ) AND NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'char_stat' AND column_name = 'crit_rate'
    ) THEN
        ALTER TABLE char_stat RENAME COLUMN crit_rate_percent TO crit_rate;
    END IF;

    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'char_stat' AND column_name = 'crit_damage_percent'
    ) AND NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'char_stat' AND column_name = 'crit_damage'
    ) THEN
        ALTER TABLE char_stat RENAME COLUMN crit_damage_percent TO crit_damage;
    END IF;

    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'char_equipment' AND column_name = 'item_equipment_part'
    ) AND NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'char_equipment' AND column_name = 'part'
    ) THEN
        ALTER TABLE char_equipment RENAME COLUMN item_equipment_part TO part;
    END IF;

    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'char_equipment' AND column_name = 'item_equipment_slot'
    ) AND NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'char_equipment' AND column_name = 'slot'
    ) THEN
        ALTER TABLE char_equipment RENAME COLUMN item_equipment_slot TO slot;
    END IF;

    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'char_equipment' AND column_name = 'potential_option_grade'
    ) AND NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'char_equipment' AND column_name = 'potential_grade'
    ) THEN
        ALTER TABLE char_equipment RENAME COLUMN potential_option_grade TO potential_grade;
    END IF;

    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'char_equipment' AND column_name = 'additional_potential_option_grade'
    ) AND NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'char_equipment' AND column_name = 'additional_potential_grade'
    ) THEN
        ALTER TABLE char_equipment RENAME COLUMN additional_potential_option_grade TO additional_potential_grade;
    END IF;

    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'char_equipment' AND column_name = 'total_options'
    ) AND NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'char_equipment' AND column_name = 'total_stats'
    ) THEN
        ALTER TABLE char_equipment RENAME COLUMN total_options TO total_stats;
    END IF;

    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'char_equipment' AND column_name = 'add_options'
    ) AND NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'char_equipment' AND column_name = 'bonus_stats'
    ) THEN
        ALTER TABLE char_equipment RENAME COLUMN add_options TO bonus_stats;
    END IF;

    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'char_equipment' AND column_name = 'etc_options'
    ) AND NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'char_equipment' AND column_name = 'scroll_stats'
    ) THEN
        ALTER TABLE char_equipment RENAME COLUMN etc_options TO scroll_stats;
    END IF;

    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'analysis_reports' AND column_name = 'report_timestamp'
    ) AND NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'analysis_reports' AND column_name = 'timestamp'
    ) THEN
        ALTER TABLE analysis_reports RENAME COLUMN report_timestamp TO timestamp;
    END IF;

    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'analysis_reports' AND column_name = 'attack_power'
    ) AND NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'analysis_reports' AND column_name = 'attack'
    ) THEN
        ALTER TABLE analysis_reports RENAME COLUMN attack_power TO attack;
    END IF;

    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'analysis_reports' AND column_name = 'damage_percent'
    ) AND NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'analysis_reports' AND column_name = 'damage'
    ) THEN
        ALTER TABLE analysis_reports RENAME COLUMN damage_percent TO damage;
    END IF;

    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'analysis_reports' AND column_name = 'boss_damage_percent'
    ) AND NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'analysis_reports' AND column_name = 'boss_damage'
    ) THEN
        ALTER TABLE analysis_reports RENAME COLUMN boss_damage_percent TO boss_damage;
    END IF;

    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'analysis_reports' AND column_name = 'ignore_def_percent'
    ) AND NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'analysis_reports' AND column_name = 'ignore_def'
    ) THEN
        ALTER TABLE analysis_reports RENAME COLUMN ignore_def_percent TO ignore_def;
    END IF;

    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'analysis_reports' AND column_name = 'crit_rate_percent'
    ) AND NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'analysis_reports' AND column_name = 'crit_rate'
    ) THEN
        ALTER TABLE analysis_reports RENAME COLUMN crit_rate_percent TO crit_rate;
    END IF;

    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'analysis_reports' AND column_name = 'crit_damage_percent'
    ) AND NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'analysis_reports' AND column_name = 'crit_damage'
    ) THEN
        ALTER TABLE analysis_reports RENAME COLUMN crit_damage_percent TO crit_damage;
    END IF;
END $$;

ALTER TABLE users ALTER COLUMN username TYPE varchar(50);
ALTER TABLE characters ALTER COLUMN ocid TYPE varchar(64);
ALTER TABLE characters ALTER COLUMN character_name TYPE varchar(50);
ALTER TABLE characters ALTER COLUMN world_name TYPE varchar(30);
ALTER TABLE characters ALTER COLUMN character_gender TYPE varchar(10);
ALTER TABLE characters ALTER COLUMN character_class TYPE varchar(50);
ALTER TABLE characters ALTER COLUMN character_class_level TYPE varchar(10);
ALTER TABLE characters ALTER COLUMN character_exp_rate TYPE numeric(8, 3);
ALTER TABLE characters ALTER COLUMN character_guild_name TYPE varchar(50);
ALTER TABLE char_stat ALTER COLUMN damage TYPE numeric(8, 2);
ALTER TABLE char_stat ALTER COLUMN boss_damage TYPE numeric(8, 2);
ALTER TABLE char_stat ALTER COLUMN final_damage TYPE numeric(8, 2);
ALTER TABLE char_stat ALTER COLUMN ignore_def TYPE numeric(8, 2);
ALTER TABLE char_stat ALTER COLUMN crit_rate TYPE numeric(8, 2);
ALTER TABLE char_stat ALTER COLUMN crit_damage TYPE numeric(8, 2);
ALTER TABLE char_equipment ALTER COLUMN part TYPE varchar(50);
ALTER TABLE char_equipment ALTER COLUMN slot TYPE varchar(50);
ALTER TABLE char_equipment ALTER COLUMN item_name TYPE varchar(120);
ALTER TABLE char_equipment ALTER COLUMN item_gender TYPE varchar(10);
ALTER TABLE char_equipment ALTER COLUMN potential_grade TYPE varchar(30);
ALTER TABLE char_equipment ALTER COLUMN additional_potential_grade TYPE varchar(30);
ALTER TABLE char_equipment ALTER COLUMN set_name TYPE varchar(120);
ALTER TABLE char_symbols ALTER COLUMN symbol_name TYPE varchar(100);
ALTER TABLE char_symbols ALTER COLUMN symbol_force TYPE varchar(30);
ALTER TABLE char_union ALTER COLUMN union_grade TYPE varchar(50);
ALTER TABLE char_skill_options ALTER COLUMN option_type TYPE varchar(30);
ALTER TABLE char_skill_options ALTER COLUMN option_name TYPE varchar(120);
ALTER TABLE char_skill_options ALTER COLUMN option_grade TYPE varchar(30);
ALTER TABLE char_cores ALTER COLUMN core_group TYPE varchar(30);
ALTER TABLE char_cores ALTER COLUMN core_type TYPE varchar(50);
ALTER TABLE char_cores ALTER COLUMN main_stat_name TYPE varchar(80);
ALTER TABLE char_set_effects ALTER COLUMN set_name TYPE varchar(120);
ALTER TABLE analysis_reports ALTER COLUMN report_type TYPE varchar(30);
ALTER TABLE analysis_reports ALTER COLUMN damage TYPE numeric(8, 2);
ALTER TABLE analysis_reports ALTER COLUMN boss_damage TYPE numeric(8, 2);
ALTER TABLE analysis_reports ALTER COLUMN ignore_def TYPE numeric(8, 2);
ALTER TABLE analysis_reports ALTER COLUMN crit_rate TYPE numeric(8, 2);
ALTER TABLE analysis_reports ALTER COLUMN crit_damage TYPE numeric(8, 2);
ALTER TABLE analysis_reports ALTER COLUMN data_reliability TYPE varchar(30);
ALTER TABLE action_plans ALTER COLUMN category TYPE varchar(50);
ALTER TABLE action_plans ALTER COLUMN target TYPE varchar(120);
ALTER TABLE source_catalog ALTER COLUMN source_id TYPE varchar(50);
ALTER TABLE source_catalog ALTER COLUMN source_name TYPE varchar(100);
-- Keep these wider than the DBML labels because the loaded dataset uses long project source labels.
ALTER TABLE source_catalog ALTER COLUMN source_type TYPE varchar(50);
ALTER TABLE source_catalog ALTER COLUMN category TYPE varchar(80);
ALTER TABLE source_catalog ALTER COLUMN collection_method TYPE varchar(80);
ALTER TABLE documents ALTER COLUMN doc_id TYPE varchar(100);
ALTER TABLE documents ALTER COLUMN source_id TYPE varchar(50);
ALTER TABLE documents ALTER COLUMN unified_id TYPE varchar(255);
ALTER TABLE documents ALTER COLUMN chatbot_purpose TYPE varchar(100);
ALTER TABLE documents ALTER COLUMN source_type TYPE varchar(50);
ALTER TABLE documents ALTER COLUMN language TYPE varchar(20);
ALTER TABLE wiki_entities ALTER COLUMN entity_type TYPE varchar(30);
ALTER TABLE tags ALTER COLUMN tag_name TYPE varchar(100);
ALTER TABLE tags ALTER COLUMN normalized_name TYPE varchar(100);
ALTER TABLE document_chunks ALTER COLUMN chunk_id TYPE varchar(100);
ALTER TABLE document_embeddings ALTER COLUMN embedding_model TYPE varchar(100);

ALTER TABLE documents ALTER COLUMN source_id SET NOT NULL;
ALTER TABLE documents ALTER COLUMN content SET NOT NULL;

ALTER TABLE characters ALTER COLUMN synced_at SET DEFAULT now();
ALTER TABLE char_stat ALTER COLUMN synced_at SET DEFAULT now();
ALTER TABLE char_equipment ALTER COLUMN synced_at SET DEFAULT now();
ALTER TABLE char_symbols ALTER COLUMN synced_at SET DEFAULT now();
ALTER TABLE char_union ALTER COLUMN synced_at SET DEFAULT now();
ALTER TABLE char_skill_options ALTER COLUMN synced_at SET DEFAULT now();
ALTER TABLE char_cores ALTER COLUMN synced_at SET DEFAULT now();
ALTER TABLE char_set_effects ALTER COLUMN synced_at SET DEFAULT now();

CREATE UNIQUE INDEX IF NOT EXISTS idx_documents_unified_id_unique
    ON documents(unified_id)
    WHERE unified_id IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS idx_document_chunks_document_chunk_index
    ON document_chunks(document_id, chunk_index);
