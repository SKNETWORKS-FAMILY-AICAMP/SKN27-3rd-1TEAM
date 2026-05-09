CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS users (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    username varchar(50) NOT NULL UNIQUE,
    nexon_api_key text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS characters (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    ocid varchar(64) NOT NULL UNIQUE,
    character_name varchar(50) NOT NULL,
    world_name varchar(30),
    character_gender varchar(10),
    character_class varchar(50),
    character_class_level varchar(10),
    character_level int,
    character_exp bigint,
    character_exp_rate numeric(8, 3),
    character_guild_name varchar(50),
    character_image text,
    character_date_create timestamptz,
    access_flag boolean,
    liberation_quest_clear boolean,
    synced_at timestamptz NOT NULL DEFAULT now(),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS char_stat (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    character_id uuid NOT NULL REFERENCES characters(id) ON DELETE CASCADE,
    combat_power bigint,
    min_stat_damage bigint,
    max_stat_damage bigint,
    str_val int,
    dex int,
    int_val int,
    luk int,
    hp int,
    mp int,
    damage numeric(8, 2),
    boss_damage numeric(8, 2),
    final_damage numeric(8, 2),
    ignore_def numeric(8, 2),
    crit_rate numeric(8, 2),
    crit_damage numeric(8, 2),
    attack_power int,
    magic_power int,
    attack_speed int,
    buff_duration int,
    arcane_force int,
    authentic_force int,
    remain_ap int,
    raw_final_stat jsonb,
    synced_at timestamptz NOT NULL DEFAULT now(),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS char_equipment (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    character_id uuid NOT NULL REFERENCES characters(id) ON DELETE CASCADE,
    preset_no int,
    part varchar(50),
    slot varchar(50),
    item_name varchar(120),
    item_gender varchar(10),
    starforce int,
    potential_grade varchar(30),
    additional_potential_grade varchar(30),
    set_name varchar(120),
    total_stats jsonb,
    bonus_stats jsonb,
    scroll_stats jsonb,
    synced_at timestamptz NOT NULL DEFAULT now(),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS char_symbols (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    character_id uuid NOT NULL REFERENCES characters(id) ON DELETE CASCADE,
    symbol_name varchar(100) NOT NULL,
    symbol_force varchar(30),
    symbol_level int,
    symbol_str int,
    symbol_dex int,
    symbol_int int,
    symbol_luk int,
    symbol_hp int,
    symbol_growth_count int,
    symbol_require_growth_count int,
    raw_payload jsonb,
    synced_at timestamptz NOT NULL DEFAULT now(),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS char_union (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    character_id uuid NOT NULL UNIQUE REFERENCES characters(id) ON DELETE CASCADE,
    union_level int,
    union_grade varchar(50),
    union_artifact_level int,
    union_artifact_exp bigint,
    union_artifact_point int,
    raider_payload jsonb,
    artifact_payload jsonb,
    synced_at timestamptz NOT NULL DEFAULT now(),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS char_skill_options (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    character_id uuid NOT NULL REFERENCES characters(id) ON DELETE CASCADE,
    option_type varchar(30) NOT NULL,
    preset_no int,
    slot_no int,
    option_name varchar(120),
    option_grade varchar(30),
    option_level int,
    option_value text,
    option_effect text,
    raw_payload jsonb,
    synced_at timestamptz NOT NULL DEFAULT now(),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS char_cores (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    character_id uuid NOT NULL REFERENCES characters(id) ON DELETE CASCADE,
    core_group varchar(30) NOT NULL,
    slot_id int,
    slot_level int,
    core_name varchar(150),
    core_type varchar(50),
    core_level int,
    main_stat_name varchar(80),
    main_stat_level int,
    skill_payload jsonb,
    stat_payload jsonb,
    synced_at timestamptz NOT NULL DEFAULT now(),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS char_set_effects (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    character_id uuid NOT NULL REFERENCES characters(id) ON DELETE CASCADE,
    set_name varchar(120) NOT NULL,
    total_set_count int,
    set_count int,
    set_option text,
    set_option_full text,
    raw_payload jsonb,
    synced_at timestamptz NOT NULL DEFAULT now(),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS analysis_reports (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    character_id uuid NOT NULL REFERENCES characters(id) ON DELETE CASCADE,
    report_type varchar(30) NOT NULL,
    current_combat_power bigint,
    timestamp timestamptz,
    attack int,
    damage numeric(8, 2),
    boss_damage numeric(8, 2),
    ignore_def numeric(8, 2),
    crit_rate numeric(8, 2),
    crit_damage numeric(8, 2),
    bottleneck_analysis jsonb,
    boss_clear_prediction jsonb,
    data_reliability varchar(30),
    result_payload jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS action_plans (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    analysis_report_id uuid NOT NULL REFERENCES analysis_reports(id) ON DELETE CASCADE,
    category varchar(50) NOT NULL,
    target varchar(120) NOT NULL,
    priority int NOT NULL CHECK (priority BETWEEN 1 AND 5),
    expected_cp_gain int,
    description text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS source_catalog (
    source_id varchar(50) PRIMARY KEY,
    source_name varchar(100) NOT NULL,
    source_type varchar(50) NOT NULL,
    category varchar(80),
    url text,
    trust_level varchar(80),
    collection_method varchar(80),
    notes text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS documents (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    doc_id varchar(100) NOT NULL UNIQUE,
    source_id varchar(50) NOT NULL REFERENCES source_catalog(source_id),
    unified_id varchar(255) UNIQUE,
    title text NOT NULL,
    category varchar(80),
    chatbot_purpose varchar(100),
    collection_scope varchar(120),
    source_type varchar(50),
    source_url text,
    normalized_url text,
    trust_level varchar(80),
    language varchar(20) DEFAULT 'ko',
    content_format varchar(50),
    text_length int,
    text_preview text,
    content text NOT NULL,
    rag_ready boolean NOT NULL DEFAULT true,
    is_final_keep boolean NOT NULL DEFAULT true,
    published_at date,
    collected_at date,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS wiki_entities (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id uuid NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    entity_type varchar(30) NOT NULL,
    entity_name varchar(150) NOT NULL,
    normalized_name varchar(150),
    category varchar(80),
    level int,
    description text,
    metadata jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS tags (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tag_name varchar(100) NOT NULL UNIQUE,
    normalized_name varchar(100) NOT NULL UNIQUE,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS document_tags (
    document_id uuid NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    tag_id uuid NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (document_id, tag_id)
);

CREATE TABLE IF NOT EXISTS document_chunks (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id uuid NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    chunk_id varchar(100) NOT NULL UNIQUE,
    chunk_index int NOT NULL,
    content text NOT NULL,
    token_count int,
    char_start int,
    char_end int,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS document_embeddings (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    chunk_id uuid NOT NULL UNIQUE REFERENCES document_chunks(id) ON DELETE CASCADE,
    embedding vector(768) NOT NULL,
    embedding_model varchar(100) NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_characters_user_id ON characters(user_id);
CREATE INDEX IF NOT EXISTS idx_char_stat_character_id ON char_stat(character_id);
CREATE INDEX IF NOT EXISTS idx_char_equipment_character_id ON char_equipment(character_id);
CREATE INDEX IF NOT EXISTS idx_documents_source_id ON documents(source_id);
CREATE INDEX IF NOT EXISTS idx_documents_rag_ready ON documents(rag_ready);
CREATE INDEX IF NOT EXISTS idx_documents_trust_level ON documents(trust_level);
CREATE INDEX IF NOT EXISTS idx_document_chunks_document_id ON document_chunks(document_id);
CREATE INDEX IF NOT EXISTS idx_wiki_entities_lookup ON wiki_entities(entity_type, normalized_name);
CREATE INDEX IF NOT EXISTS idx_document_chunks_fts
    ON document_chunks USING gin (to_tsvector('simple', content));
CREATE INDEX IF NOT EXISTS idx_documents_fts
    ON documents USING gin (to_tsvector('simple', coalesce(title, '') || ' ' || coalesce(content, '')));
CREATE INDEX IF NOT EXISTS idx_document_embeddings_vector
    ON document_embeddings USING hnsw (embedding vector_cosine_ops);
