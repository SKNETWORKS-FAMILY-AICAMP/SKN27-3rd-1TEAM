from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from langchain_core.messages import HumanMessage

os.environ["LANGCHAIN_TRACING"] = "false"
os.environ["LANGCHAIN_TRACING_V2"] = "false"
os.environ["LANGSMITH_TRACING"] = "false"

import src.graph as graph_module
from common.nexon_state import (
    has_external_research_evidence,
    make_nexon_document,
    nexon_api_attempted,
)
from src.agents.supervisor import (
    _fallback_supervisor_response,
    character_lookup_guard,
    is_character_data_lookup_query,
    requires_personal_character_judgement_query,
    requires_character_lookup_query,
    supervisor,
)
from src.agents.research_agent import classify_research_route, derive_intent_tags, web_fallback_reason
from src.collectors import character_lookup_node
from src.collectors import nexon_api_tasks
from src.collectors.nexon_api import extract_character_lookup_from_query
from src.collectors.nexon_api_tasks import (
    API_TASK_CHARACTER_LOOKUP,
    API_TASK_RANKING_OVERALL,
)


def base_state(query: str) -> dict:
    return {
        "user_query": query,
        "contextualized_query": query,
        "messages": [HumanMessage(content=query)],
        "completed_agents": [],
        "retry_count": 0,
        "errors": [],
        "is_complete": False,
    }


class GraphRoutingTests(unittest.TestCase):
    def test_ranking_question_routes_through_nexon_api_task(self) -> None:
        query = "엘리시움 서버 랭킹 1위 누구야?"

        routed = supervisor(base_state(query))

        self.assertTrue(routed["requires_api"])
        self.assertEqual(API_TASK_RANKING_OVERALL, routed["api_task_type"])
        self.assertEqual("엘리시움", routed["api_params"]["world_name"])
        self.assertEqual(1, routed["api_params"]["target_rank"])
        self.assertEqual("nexon_api", graph_module.route_from_supervisor(routed))

        fake_result = {
            "result_kind": "ranking_list",
            "answer": "엘리시움 랭킹 1위는 테스트캐릭터입니다.",
            "raw": [
                {
                    "ranking": 1,
                    "character_name": "테스트캐릭터",
                    "world_name": "엘리시움",
                }
            ],
            "source_url": nexon_api_tasks.RANKING_SOURCE_URL,
        }
        with patch.object(nexon_api_tasks, "run_ranking_task", return_value=fake_result):
            api_state = graph_module.nexon_api_node(routed)

        self.assertFalse(api_state["requires_api"])
        self.assertTrue(nexon_api_attempted(api_state))
        self.assertIn("테스트캐릭터", api_state["context"])
        self.assertEqual("final_answer", graph_module.route_from_nexon_api(api_state))

    def test_boss_comparison_keeps_character_and_boss_entities_separate(self) -> None:
        query = "엘리시움 서버의 캐릭터 '버터'로 하드 오스카 보스를 잡을 수 있을까?"

        character_name, lookup_blocked = character_lookup_guard(query)
        routed = _fallback_supervisor_response(base_state(query))

        self.assertEqual("버터", character_name)
        self.assertFalse(lookup_blocked)
        self.assertTrue(routed["requires_character_lookup"])
        self.assertEqual(API_TASK_CHARACTER_LOOKUP, routed["api_task_type"])
        self.assertEqual("boss_strategy", routed["task_type"])
        self.assertEqual(
            ["research", "calculator", "analystic", "final_answer"],
            routed["plan"],
        )
        self.assertEqual("nexon_api", graph_module.route_from_supervisor(routed))

    def test_possessive_world_character_info_query_routes_to_character_lookup(self) -> None:
        query = "엘리시움 서버의 버터 조회해줘"

        lookup = extract_character_lookup_from_query(query)
        routed = supervisor(base_state(query))

        self.assertEqual({"character_name": "버터", "world_name": "엘리시움"}, lookup)
        self.assertTrue(requires_character_lookup_query(query))
        self.assertTrue(is_character_data_lookup_query(query))
        self.assertTrue(routed["requires_character_lookup"])
        self.assertEqual(API_TASK_CHARACTER_LOOKUP, routed["api_task_type"])
        self.assertEqual("버터", routed["character_name"])
        self.assertEqual("엘리시움", routed["world_name"])
        self.assertEqual(["final_answer"], routed["plan"])
        self.assertEqual("nexon_api", graph_module.route_from_supervisor(routed))

    def test_character_lookup_query_runs_api_then_final_answer_without_research(self) -> None:
        query = "엘리시움 서버의 버터 조회해줘"
        calls: list[str] = []

        def fake_character_lookup_node(state: dict) -> dict:
            calls.append("nexon_api")
            return {
                **state,
                "character_name": "버터",
                "world_name": "엘리시움",
                "ocid": "fake-ocid",
                "character_profile": {
                    "character_name": "버터",
                    "world_name": "엘리시움",
                    "job_name": "도적",
                    "level": 300,
                },
                "character_stats": {"combat_power": 123456},
                "tool_results": {
                    "nexon_api": {
                        "api_task_type": API_TASK_CHARACTER_LOOKUP,
                        "character_name": "버터",
                        "world_name": "엘리시움",
                        "data_reliability": "nexon_open_api",
                    }
                },
            }

        def fail_research(state: dict) -> dict:
            raise AssertionError("simple character lookup should not route to research")

        def fake_final_answer(state: dict) -> dict:
            calls.append("final_answer")
            return {
                **state,
                "draft_answer": "버터 캐릭터 조회 결과입니다.",
                "final_answer": "버터 캐릭터 조회 결과입니다.",
            }

        def fake_evaluation(state: dict) -> dict:
            calls.append("evaluation")
            return {
                **state,
                "validation_passed": True,
                "is_complete": True,
                "next_agent": "FINISH",
            }

        with (
            patch("src.collectors.nexon_api.character_lookup_node", side_effect=fake_character_lookup_node),
            patch.object(graph_module, "research", side_effect=fail_research),
            patch.object(graph_module, "final_answer", side_effect=fake_final_answer),
            patch.object(graph_module, "evaluation", side_effect=fake_evaluation),
        ):
            result = graph_module.maple_chat_graph().invoke(base_state(query))

        self.assertEqual(["nexon_api", "final_answer", "evaluation"], calls)
        self.assertEqual("FINISH", result["next_agent"])
        self.assertEqual("fake-ocid", result["ocid"])
        self.assertIn("Nexon Open API 캐릭터 조회 결과", result["context"])

    def test_followup_boss_feasibility_uses_cached_character_and_fetches_boss_criteria(self) -> None:
        query = "이 캐릭터로 힐라 잡을 수 있을까?"
        nexon_document = make_nexon_document(
            content=(
                "Nexon Open API 캐릭터 조회 결과\n"
                "- 캐릭터: 버터\n"
                "- 월드: 엘리시움\n"
                "- 레벨: 300\n"
                "- 전투력: 24277650"
            ),
            metadata={"character_name": "버터", "world_name": "엘리시움"},
        )
        state = {
            **base_state(query),
            "character_name": "버터",
            "world_name": "엘리시움",
            "ocid": "fake-ocid",
            "character_profile": {
                "character_name": "버터",
                "world_name": "엘리시움",
                "job_name": "도적",
                "level": 300,
            },
            "character_stats": {
                "combat_power": 24277650,
                "boss_damage": 190.0,
                "ignore_def": 61.22,
                "arcane_force": 1350,
                "authentic_force": 770,
            },
            "context": nexon_document["page_content"],
            "retrieved_docs": [nexon_document],
            "tool_results": {
                "nexon_api": {
                    "lookup_attempted": True,
                    "api_task_type": API_TASK_CHARACTER_LOOKUP,
                }
            },
        }

        routed = _fallback_supervisor_response(state)

        self.assertFalse(has_external_research_evidence(state))
        self.assertFalse(routed["requires_character_lookup"])
        self.assertEqual("boss_strategy", routed["task_type"])
        self.assertEqual(
            ["research", "calculator", "analystic", "final_answer"],
            routed["plan"],
        )
        self.assertEqual("research", graph_module.route_from_supervisor(routed))

    def test_first_person_growth_followup_reuses_last_character_state(self) -> None:
        from app.maple_chat import should_reuse_last_character_state

        self.assertTrue(
            should_reuse_last_character_state(
                "그럼 지금 내가 더 성장하려면 어떤 콘텐츠를 시작해야할까"
            )
        )
        self.assertTrue(should_reuse_last_character_state("제가 다음 보스 가능할까요?"))
        self.assertTrue(should_reuse_last_character_state("지금 노멀 스우 공략 가능해?"))
        self.assertTrue(should_reuse_last_character_state("노멀 스우 공략 가능해?"))
        self.assertFalse(should_reuse_last_character_state("내가 아까 뭐 물어봤지?"))
        self.assertFalse(should_reuse_last_character_state("오늘 이벤트 알려줘"))
        self.assertFalse(should_reuse_last_character_state("노멀 스우 공략법 알려줘"))

    def test_personal_growth_followup_uses_cached_character_for_recommendation_plan(self) -> None:
        query = "그럼 지금 내가 더 성장하려면 어떤 콘텐츠를 시작해야할까"
        nexon_document = make_nexon_document(
            content=(
                "Nexon Open API 캐릭터 조회 결과\n"
                "- 캐릭터: 버터\n"
                "- 월드: 엘리시움\n"
                "- 레벨: 300\n"
                "- 전투력: 24277650"
            ),
            metadata={"character_name": "버터", "world_name": "엘리시움"},
        )
        state = {
            **base_state(query),
            "character_name": "버터",
            "world_name": "엘리시움",
            "character_profile": {
                "character_name": "버터",
                "world_name": "엘리시움",
                "job_name": "도적",
                "level": 300,
            },
            "character_stats": {
                "combat_power": 24277650,
                "boss_damage": 190.0,
                "ignore_def": 61.22,
            },
            "context": nexon_document["page_content"],
            "retrieved_docs": [nexon_document],
            "tool_results": {"nexon_api": {"lookup_attempted": True}},
        }

        routed = _fallback_supervisor_response(state)

        self.assertTrue(requires_personal_character_judgement_query(query))
        self.assertEqual(
            ["research", "calculator", "analystic", "final_answer"],
            routed["plan"],
        )
        self.assertEqual("research", graph_module.route_from_supervisor(routed))

    def test_boss_feasibility_research_route_uses_requirement_graph_intent(self) -> None:
        query = "\uc774 \uce90\ub9ad\ud130\ub85c \ub178\uba40 \uc2a4\uc6b0 \uac00\ub2a5\ud574?"

        intent_tags = derive_intent_tags(query)
        routed = classify_research_route(query, task_type="boss_strategy")

        self.assertIn("boss_strategy", intent_tags)
        self.assertIn("boss_requirement", intent_tags)
        self.assertTrue(routed["use_graph"])
        self.assertIn("boss_requirement", routed["intent_tags"])

    def test_boss_requirement_graph_evidence_skips_web_fallback(self) -> None:
        query = "\uc774 \uce90\ub9ad\ud130\ub85c \ub178\uba40 \uc2a4\uc6b0 \uac00\ub2a5\ud574?"
        routed = classify_research_route(query, task_type="boss_strategy")
        document = {
            "page_content": (
                "Graph boss requirement fact\n"
                "Boss: Lotus\n"
                "aliases: Lotus, \uc2a4\uc6b0\n"
                "difficulty: Normal\n"
                "relationship: HAS_REQUIREMENT\n"
                "main_stat: 34000\n"
                "boss_damage: 200\n"
                "ignore_def: 88"
            ),
            "metadata": {
                "title": "Lotus - HAS_REQUIREMENT",
                "retrieval_method": "graph_requirement",
                "entity_type": "Boss->StatRequirement",
            },
            "source": "graph::requirement::lotus::normal",
            "score": 1.0,
        }

        self.assertEqual("", web_fallback_reason(routed, [document], {}))

    def test_plain_boss_question_does_not_trigger_character_lookup(self) -> None:
        query = "하드 오스카 정보 조회해줘"

        character_name, lookup_blocked = character_lookup_guard(query)
        routed = _fallback_supervisor_response(base_state(query))

        self.assertEqual("", character_name)
        self.assertTrue(lookup_blocked)
        self.assertFalse(routed["requires_character_lookup"])
        self.assertNotEqual(API_TASK_CHARACTER_LOOKUP, routed.get("api_task_type"))
        self.assertEqual("research", graph_module.route_from_supervisor(routed))

    def test_blue_mushroom_research_path_finishes_without_retry_loop(self) -> None:
        query = "파란버섯에 대해 알려줘"
        calls: list[str] = []

        def fake_supervisor(state: dict) -> dict:
            calls.append("supervisor")
            if "research" not in state.get("completed_agents", []):
                return {
                    **state,
                    "intent": "파란버섯 정보 요청",
                    "task_type": "story_explanation",
                    "requires_api": False,
                    "api_task_type": "",
                    "api_params": {},
                    "requires_character_lookup": False,
                    "plan": ["research", "final_answer"],
                    "next_agent": "research",
                }
            return {
                **state,
                "intent": "파란버섯 정보 요청",
                "task_type": "story_explanation",
                "requires_api": False,
                "api_task_type": "",
                "api_params": {},
                "requires_character_lookup": False,
                "plan": ["final_answer"],
                "next_agent": "final_answer",
            }

        def fake_research(state: dict) -> dict:
            calls.append("research")
            document = {
                "page_content": "파란버섯은 메이플스토리의 버섯형 몬스터입니다.",
                "source": "test_fixture",
                "score": 1.0,
                "metadata": {"source": "test_fixture", "reliability": "HIGH"},
            }
            return {
                **state,
                "completed_agents": [*state.get("completed_agents", []), "research"],
                "retrieved_docs": [document],
                "selected_evidence": [document],
                "context": document["page_content"],
            }

        def fake_evidence_formatter(state: dict) -> dict:
            calls.append("evidence_formatter")
            return state

        def fake_final_answer(state: dict) -> dict:
            calls.append("final_answer")
            return {
                **state,
                "draft_answer": "파란버섯은 메이플스토리의 버섯형 몬스터입니다.",
                "final_answer": "파란버섯은 메이플스토리의 버섯형 몬스터입니다.",
            }

        def fake_evaluation(state: dict) -> dict:
            calls.append("evaluation")
            return {
                **state,
                "validation_passed": True,
                "is_complete": True,
                "next_agent": "FINISH",
            }

        with (
            patch.object(graph_module, "supervisor", side_effect=fake_supervisor),
            patch.object(graph_module, "research", side_effect=fake_research),
            patch.object(graph_module, "evidence_formatter", side_effect=fake_evidence_formatter),
            patch.object(graph_module, "final_answer", side_effect=fake_final_answer),
            patch.object(graph_module, "evaluation", side_effect=fake_evaluation),
        ):
            result = graph_module.maple_chat_graph().invoke(base_state(query))

        self.assertTrue(result["validation_passed"])
        self.assertEqual("FINISH", result["next_agent"])
        self.assertLessEqual(calls.count("supervisor"), 2)
        self.assertEqual(
            ["supervisor", "research", "evidence_formatter", "supervisor", "final_answer", "evaluation"],
            calls,
        )

    def test_character_lookup_node_export_is_renamed_collector_entrypoint(self) -> None:
        self.assertTrue(callable(character_lookup_node))


if __name__ == "__main__":
    unittest.main()
