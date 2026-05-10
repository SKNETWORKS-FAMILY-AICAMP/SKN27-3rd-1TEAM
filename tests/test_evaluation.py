from __future__ import annotations

import unittest

from src.agents.evaluation import evaluate_answer, evaluation_agent


class EvaluationAgentTest(unittest.TestCase):
    def test_evaluation_passes_grounded_answer(self) -> None:
        state = {
            "user_query": "하드 스우 요구 스펙 알려줘",
            "context": (
                "하드 스우 요구 스펙은 전투력, 보스 데미지, 방어율 무시, "
                "생존 유틸, 패턴 숙련도, 기준 정보를 함께 확인한다. "
                "근거는 제공된 context 기준이다."
            ),
            "final_answer": (
                "하드 스우 요구 스펙은 전투력, 보스 데미지, 방어율 무시, "
                "생존 유틸, 패턴 숙련도, 기준 정보를 함께 확인하는 것이 좋습니다. "
                "근거: 제공된 context 기준입니다."
            ),
            "retry_count": 0,
            "completed_agents": ["research", "final_answer"],
        }

        result = evaluation_agent(state)

        self.assertTrue(result["validation_passed"])
        self.assertEqual(result["retry_target"], "FINISH")
        self.assertEqual(result["next_agent"], "FINISH")
        self.assertTrue(result["is_complete"])
        self.assertIn("evaluation", result["completed_agents"])
        self.assertGreaterEqual(result["confidence_score"], 0.72)

    def test_empty_answer_retries_final_answer(self) -> None:
        decision = evaluate_answer(
            {
                "user_query": "보스 추천해줘",
                "context": "캐릭터 스펙과 보스 요구 스펙을 비교한다.",
                "final_answer": "",
            }
        )

        self.assertFalse(decision.passed)
        self.assertEqual(decision.retry_target, "final_answer")
        self.assertEqual(decision.scores.confidence, 0.1)

    def test_missing_context_retries_research(self) -> None:
        result = evaluation_agent(
            {
                "user_query": "하드 스우 요구 스펙 알려줘",
                "final_answer": "하드 스우 요구 스펙은 전투력과 보스 데미지를 기준으로 판단합니다.",
                "retry_count": 0,
            }
        )

        self.assertFalse(result["validation_passed"])
        self.assertEqual(result["retry_target"], "research")
        self.assertEqual(result["next_agent"], "research")
        self.assertEqual(result["retry_count"], 1)

    def test_error_routes_to_related_agent(self) -> None:
        result = evaluation_agent(
            {
                "user_query": "최신 이벤트 알려줘",
                "context": "최신 이벤트 검색 결과",
                "final_answer": "최신 이벤트 검색 결과를 기준으로 답변합니다.",
                "errors": ["research db_search_rag failed: connection refused"],
                "retry_count": 0,
            }
        )

        self.assertFalse(result["validation_passed"])
        self.assertEqual(result["retry_target"], "research")
        self.assertEqual(result["next_agent"], "research")

    def test_max_retry_finishes_with_failure_state(self) -> None:
        result = evaluation_agent(
            {
                "user_query": "보스 추천해줘",
                "final_answer": "",
                "retry_count": 2,
            }
        )

        self.assertFalse(result["validation_passed"])
        self.assertEqual(result["retry_target"], "final_answer")
        self.assertEqual(result["next_agent"], "FINISH")
        self.assertTrue(result["is_complete"])
        self.assertEqual(result["retry_count"], 2)


if __name__ == "__main__":
    unittest.main()
