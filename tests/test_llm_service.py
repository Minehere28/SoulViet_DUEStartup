import json
import unittest

from services.llm_service import LLMService


class LLMServiceTests(unittest.TestCase):
    def setUp(self):
        self.service = LLMService()
        self.service.api_key = "test-key"

    def test_parses_a_structured_intent(self):
        response = {
            "request_updates": {
                "max_daily_distance_km": 12,
            },
            "graph_query": {
                "keywords": ["biển"],
                "expand_near": True,
                "near_hops": 1,
            },
        }
        self.service._request_completion = lambda *_args, **_kwargs: (
            {"tool_calls": [{"function": {
                "name": "replan_itinerary",
                "arguments": json.dumps(response, ensure_ascii=False),
            }}]},
            {},
        )

        intent = self.service.parse_intent("test", {}, [])

        self.assertEqual(intent.intent, "modify_itinerary")
        self.assertEqual(
            intent.request_updates.max_daily_distance_km, 12
        )
        self.assertEqual(intent.graph_query.near_hops, 1)

    def test_rejects_unknown_fields_from_the_model(self):
        self.service._request_completion = lambda *_args, **_kwargs: (
            {"tool_calls": [{"function": {
                "name": "replan_itinerary",
                "arguments": json.dumps({
                    "unsafe_query": "MATCH (n) DELETE n",
                }),
            }}]},
            {},
        )

        intent = self.service.parse_intent("test", {}, [])

        self.assertIsNone(intent)

    def test_selects_question_tool_without_replanning(self):
        self.service._request_completion = lambda *_args, **_kwargs: (
            {"tool_calls": [{"function": {
                "name": "answer_itinerary_question",
                "arguments": "{}",
            }}]},
            {},
        )

        intent = self.service.parse_intent("test", {}, [])

        self.assertEqual(intent.intent, "question")

    def test_selects_clarification_tool(self):
        self.service._request_completion = lambda *_args, **_kwargs: (
            {"tool_calls": [{"function": {
                "name": "ask_for_clarification",
                "arguments": json.dumps({"question": "Bạn muốn đi ngày nào?"}),
            }}]},
            {},
        )

        intent = self.service.parse_intent("test", {}, [])

        self.assertTrue(intent.needs_clarification)
        self.assertEqual(intent.clarification_question, "Bạn muốn đi ngày nào?")

    def test_semantic_classifier_keeps_only_known_confident_ids(self):
        response = {
            "matched_place_ids": ["beach-by-name", "low", "invented"],
            "confidence_by_id": {
                "beach-by-name": 0.91,
                "low": 0.4,
                "invented": 0.99,
            },
            "reason_by_id": {
                "beach-by-name": "Tên và mô tả thể hiện đây là bãi biển",
            },
        }
        self.service._complete = lambda *_args, **_kwargs: (
            json.dumps(response, ensure_ascii=False),
            {},
        )

        result = self.service.classify_place_matches("muốn đi biển", [
            {"id": "beach-by-name", "name": "Bãi X"},
            {"id": "low", "name": "Điểm Y"},
        ])

        self.assertEqual(result["matched_place_ids"], ["beach-by-name"])
        self.assertEqual(result["confidence_by_id"], {"beach-by-name": 0.91})


if __name__ == "__main__":
    unittest.main()
