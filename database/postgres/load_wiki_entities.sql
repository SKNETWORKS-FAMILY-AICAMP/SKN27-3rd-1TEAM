BEGIN;

DELETE FROM wiki_entities
WHERE document_id IN (
    SELECT id
    FROM documents
    WHERE source_type = 'wiki'
       OR collection_scope = 'wiki_additional_collection'
);

WITH wiki_docs AS (
    SELECT
        d.id AS document_id,
        d.doc_id,
        d.title,
        d.category,
        d.source_type,
        d.collection_scope,
        d.source_url,
        d.trust_level,
        d.text_preview,
        d.content,
        COALESCE(
            jsonb_agg(t.tag_name) FILTER (WHERE t.tag_name IS NOT NULL),
            '[]'::jsonb
        ) AS tags
    FROM documents d
    LEFT JOIN document_tags dt ON dt.document_id = d.id
    LEFT JOIN tags t ON t.id = dt.tag_id
    WHERE d.source_type = 'wiki'
       OR d.collection_scope = 'wiki_additional_collection'
    GROUP BY d.id
),
classified AS (
    SELECT
        *,
        CASE
            WHEN lower(title) LIKE '%/monster%'
             AND substring(content FROM 1 FOR 5000) ~* '\(Boss\)|Entry Level|Death Count|Clear Limit'
                THEN 'boss'
            WHEN lower(title) LIKE '%/monster%'
                THEN 'monster'
            WHEN lower(title) LIKE '%/skill%'
                THEN 'skill'
            WHEN lower(title) LIKE '%/quest%'
                THEN 'quest'
            WHEN lower(title) LIKE '%/map%'
                THEN 'map'
            WHEN substring(content FROM 1 FOR 5000) ~* 'Entry Level|Potion Cooldown|Death Count|Clear Limit'
                THEN 'boss'
            WHEN substring(content FROM 1 FOR 5000) ~* '\(Boss\)|Boss\)'
                THEN 'boss'
            WHEN substring(content FROM 1 FOR 5000) ~* 'Map Properties|Return Map|Continent|Monsters|NPCs'
                THEN 'map'
            WHEN substring(content FROM 1 FOR 5000) ~* 'Pre-requisite|Procedure|Rewards'
             AND substring(content FROM 1 FOR 5000) ~* 'Quest'
                THEN 'quest'
            WHEN substring(content FROM 1 FOR 5000) ~* 'Skill Description|Master Level|MP Cost|Cooldown'
                THEN 'skill'
            WHEN substring(content FROM 1 FOR 5000) ~* 'Tradable|Max per slot|Equipment Drops|Usable Drops|Set-up Drops|Required Level|Primary weapon|Secondary weapon|Accessories are|Provides Potential'
                THEN 'item'
            WHEN substring(content FROM 1 FOR 5000) ~* 'Defense Rate|PDR:|MDR:|Elements|EXP|HP'
                THEN 'monster'
            ELSE NULL
        END AS entity_type,
        CASE
            WHEN lower(title) LIKE '%/monster%'
             AND substring(content FROM 1 FOR 5000) ~* '\(Boss\)|Entry Level|Death Count|Clear Limit'
                THEN 'title /Monster with boss markers'
            WHEN lower(title) LIKE '%/monster%'
                THEN 'title contains /Monster'
            WHEN lower(title) LIKE '%/skill%'
                THEN 'title contains /Skill'
            WHEN lower(title) LIKE '%/quest%'
                THEN 'title contains /Quest'
            WHEN lower(title) LIKE '%/map%'
                THEN 'title contains /Map'
            WHEN substring(content FROM 1 FOR 5000) ~* 'Entry Level|Potion Cooldown|Death Count|Clear Limit'
                THEN 'boss battle markers'
            WHEN substring(content FROM 1 FOR 5000) ~* '\(Boss\)|Boss\)'
                THEN 'content contains boss marker'
            WHEN substring(content FROM 1 FOR 5000) ~* 'Map Properties|Return Map|Continent|Monsters|NPCs'
                THEN 'map metadata markers'
            WHEN substring(content FROM 1 FOR 5000) ~* 'Pre-requisite|Procedure|Rewards'
             AND substring(content FROM 1 FOR 5000) ~* 'Quest'
                THEN 'quest metadata markers'
            WHEN substring(content FROM 1 FOR 5000) ~* 'Skill Description|Master Level|MP Cost|Cooldown'
                THEN 'skill metadata markers'
            WHEN substring(content FROM 1 FOR 5000) ~* 'Tradable|Max per slot|Equipment Drops|Usable Drops|Set-up Drops|Required Level|Primary weapon|Secondary weapon|Accessories are|Provides Potential'
                THEN 'item/equipment markers'
            WHEN substring(content FROM 1 FOR 5000) ~* 'Defense Rate|PDR:|MDR:|Elements|EXP|HP'
                THEN 'monster stat markers'
            ELSE NULL
        END AS inferred_reason
    FROM wiki_docs
),
prepared AS (
    SELECT
        document_id,
        entity_type,
        left(
            CASE
                WHEN entity_type IN ('monster', 'skill', 'quest', 'map')
                 AND position('/' IN title) > 0
                    THEN split_part(title, '/', 1)
                ELSE title
            END,
            150
        ) AS entity_name,
        category,
        CASE
            WHEN content ~* '(Level|Entry Level|Required Level)\s+[0-9]{1,4}'
                THEN substring(content FROM '(?i)(?:Level|Entry Level|Required Level)\s+([0-9]{1,4})')::int
            ELSE NULL
        END AS level,
        text_preview AS description,
        jsonb_build_object(
            'doc_id', doc_id,
            'source_type', source_type,
            'collection_scope', collection_scope,
            'source_url', source_url,
            'trust_level', trust_level,
            'tags', tags,
            'inferred_reason', inferred_reason
        ) AS metadata
    FROM classified
    WHERE entity_type IS NOT NULL
)
INSERT INTO wiki_entities (
    document_id,
    entity_type,
    entity_name,
    normalized_name,
    category,
    level,
    description,
    metadata
)
SELECT
    document_id,
    entity_type,
    entity_name,
    lower(regexp_replace(trim(entity_name), '\s+', ' ', 'g')) AS normalized_name,
    category,
    level,
    description,
    metadata
FROM prepared;

COMMIT;
