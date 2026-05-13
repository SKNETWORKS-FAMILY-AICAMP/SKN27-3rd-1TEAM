// 보스 요구 스펙 조회
MATCH (b:Boss {name: "노멀 스우"})-[:HAS_REQUIREMENT]->(r:StatRequirement)
RETURN b.name AS boss,
       b.difficulty AS difficulty,
       r.level AS level,
       r.main_stat AS main_stat,
       r.arcane_force AS arcane_force,
       r.boss_damage AS boss_damage,
       r.ignore_def AS ignore_def;

// 보스 요구 스탯을 domain.py 필드 기준으로 조회
MATCH (b:Boss {name: "노멀 스우"})-[:HAS_REQUIREMENT]->(r:StatRequirement)-[rel:REQUIRES_STAT]->(s:StatType)
RETURN b.name AS boss,
       s.code AS stat_code,
       s.domain_field AS domain_field,
       rel.value AS required_value
ORDER BY s.code;

// 직업의 주스탯 조회
MATCH (j:Job)-[:USES_MAIN_STAT]->(s:StatType)
RETURN j.name AS job,
       j.job_group AS job_group,
       s.code AS main_stat,
       s.domain_field AS domain_field
ORDER BY j.job_group, j.name;

// 장비 세트 조회
MATCH (e:EquipmentCatalog)-[:PART_OF_SET]->(s:SetEffect)
RETURN s.name AS set_name,
       collect(DISTINCT e.name)[0..20] AS equipment_examples,
       count(e) AS equipment_count
ORDER BY equipment_count DESC;

// 이벤트 보상과 관련 콘텐츠 조회
MATCH (e:Event {name: "하이퍼 버닝"})
OPTIONAL MATCH (e)-[:PROVIDES_REWARD]->(r:Reward)
OPTIONAL MATCH (e)-[:RELATED_CONTENT]->(c:Content)
RETURN e.name AS event,
       collect(DISTINCT r.name) AS rewards,
       collect(DISTINCT c.name) AS contents;

// 보스별 보상 조회
MATCH (b:Boss)-[:DROPS_REWARD]->(r:Reward)
RETURN b.name AS boss,
       b.difficulty AS difficulty,
       collect(DISTINCT r.name) AS rewards
ORDER BY b.required_level, b.name;

// 문서 출처 조회
MATCH (s:Source)
RETURN s.title AS source,
       s.category AS category,
       s.url AS source_url,
       s.trust_level AS trust_level
LIMIT 50;

// 추가 데이터셋에서 선별한 보스 추천 요구 스펙 조회
MATCH (b:Boss)-[:HAS_REQUIREMENT]->(r:StatRequirement)
WHERE r.confidence <> "draft"
RETURN b.name AS boss,
       b.difficulty AS difficulty,
       r.level AS recommended_level,
       r.main_stat AS recommended_main_stat,
       r.boss_damage AS boss_damage,
       r.ignore_def AS ignore_def
ORDER BY b.name, b.difficulty
LIMIT 20;

// 공식 이벤트 조회
MATCH (e:Event {event_type: "official_event"})
RETURN e.name AS event,
       e.target_user AS target_user,
       e.start_date AS start_date,
       e.end_date AS end_date
ORDER BY e.name
LIMIT 20;

// 5차/6차 강화 우선순위 출처 조회
MATCH (s:Source)
WHERE s.category IN ["class_5th_core_priority", "class_6th_hexa_priority"]
RETURN s.category AS category,
       s.title AS source_title,
       s.text_preview AS summary
ORDER BY s.category, s.title
LIMIT 20;
