import unittest
from datetime import date
from typing import get_args

from models.assistant_request import AssistantRequest
from models.user_request import RegionName, UserRequest, VibeName
from services.assistant_service import AssistantService
from services.itinerary_service import ItineraryService
from models.assistant_intent import AssistantIntent, PlaceOperation


class FakeLLM:
    def chat(self, message, itinerary, request_data, applied_changes):
        return {
            "answer": "local test",
            "provider": "test",
            "model": None,
            "fallback_reason": None,
            "usage": None,
        }


class StructuredIntentLLM(FakeLLM):
    def parse_intent(self, _message, _request, _itinerary):
        return AssistantIntent(
            intent="modify_itinerary",
            operations=[PlaceOperation(action="remove", day=1, position=1)],
        )


class FakeRouting:
    def build_matrix(self, places):
        metrics = {}
        for source in places:
            for destination in places:
                metrics[(source["id"], destination["id"])] = {
                    "distance_km": 0 if source is destination else 0.5,
                    "duration_minutes": 0 if source is destination else 2,
                    "source": "test_matrix",
                }
        return {
            "metrics": metrics,
            "source": "test_matrix",
            "fallback_reason": None,
        }


class FakeOptimizer:
    def __init__(self):
        self.candidate_counts = []
        self.attraction_counts = []

    def optimize(
        self,
        places,
        _day_schedules,
        _route_matrix,
        max_places,
        _max_distance_km,
        _day_start_minutes,
        _day_end_minutes,
        _start_place=None,
    ):
        self.candidate_counts.append(len(places))
        self.attraction_counts.append(sum(
            place.get("item_type") != "meal" for place in places
        ))
        return places[:max_places]


class AssistantServiceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.optimizer = FakeOptimizer()
        itinerary = ItineraryService(
            routing=FakeRouting(),
            optimizer=cls.optimizer,
        )
        cls.service = AssistantService(itinerary=itinerary, llm=FakeLLM())
        cls.region = get_args(RegionName)[1]
        cls.vibes = get_args(VibeName)

    def request(self, **overrides):
        values = {
            "duration": 2,
            "vibe": self.vibes[1],
            "region": self.region,
            "start_date": date(2026, 8, 1),
        }
        values.update(overrides)
        return UserRequest(**values)

    def customize(self, message, **overrides):
        payload = AssistantRequest(
            message=message,
            current_request=self.request(**overrides),
        )
        return self.service.customize(payload)

    def test_changes_duration(self):
        result = self.customize("Đổi thành 3 ngày")
        self.assertEqual(result["request"]["duration"], 3)

    def test_changes_budget(self):
        result = self.customize("Chuyển sang mức tiết kiệm")
        self.assertEqual(result["request"]["budget_level"], "economy")

    def test_changes_max_places(self):
        result = self.customize("Chỉ đi 3 địa điểm mỗi ngày")
        self.assertEqual(result["request"]["max_places_per_day"], 3)

    def test_changes_max_places_to_eight(self):
        result = self.customize("Chỉ đi 8 địa điểm mỗi ngày")
        self.assertEqual(result["request"]["max_places_per_day"], 8)

    def test_uses_real_start_location_and_limits_daily_candidates(self):
        self.optimizer.candidate_counts.clear()
        itinerary = self.service.itinerary.build(
            self.request(
                duration=1,
                start_lat=16.0544,
                start_lng=108.2022,
                start_name="Khách sạn",
            )
        )

        self.assertEqual(
            itinerary[0]["start_location"]["name"],
            "Khách sạn",
        )
        self.assertEqual(
            itinerary[0]["places"][0]["travel_time_minutes"],
            2,
        )
        self.assertEqual(self.optimizer.attraction_counts[0], 12)
        self.assertLessEqual(self.optimizer.candidate_counts[0], 24)

    def test_changes_distance(self):
        result = self.customize("Không đi quá 8,5 km")
        self.assertEqual(result["request"]["max_daily_distance_km"], 8.5)

    def test_changes_vibe(self):
        target_vibe = self.vibes[0]
        result = self.customize(f"Đổi sang vibe {target_vibe}")
        self.assertEqual(result["request"]["vibe"], target_vibe)

    def test_removes_named_place(self):
        initial = self.service.itinerary.build(self.request())
        place = initial[0]["places"][0]
        result = self.customize(f"Bỏ {place['name']} khỏi lịch trình")
        self.assertIn(
            place["id"],
            result["request"]["excluded_place_ids"],
        )
        returned_ids = {
            item["id"]
            for day in result["itinerary"]
            for item in day["places"]
        }
        self.assertNotIn(place["id"], returned_ids)

    def test_question_does_not_rebuild_itinerary(self):
        self.optimizer.candidate_counts.clear()
        current_itinerary = [{
            "date": "2026-08-01",
            "total_distance_km": 5,
            "places": [],
        }]
        payload = AssistantRequest(
            message="Tại sao lịch này lại hợp lý?",
            current_request=self.request(),
            current_itinerary=current_itinerary,
        )

        result = self.service.customize(payload)

        self.assertEqual(result["intent"], "question")
        self.assertEqual(result["itinerary"], current_itinerary)
        self.assertEqual(self.optimizer.candidate_counts, [])

    def test_natural_preference_uses_graph_query(self):
        result = self.customize(
            "Ưu tiên biển và ít di chuyển"
        )

        self.assertEqual(result["intent"], "modify_itinerary")
        self.assertIsNotNone(result["query_metadata"])
        self.assertEqual(result["query_metadata"]["near_hops"], 1)
        self.assertLessEqual(result["query_metadata"]["candidate_count"], 24)
        self.assertIn(
            "Biển & Hoạt động dưới nước",
            result["request"]["preferred_activities"],
        )

    def test_structured_intent_resolves_a_place_position(self):
        initial = self.service.itinerary.build(self.request(duration=1))
        removed_id = initial[0]["places"][0]["id"]
        service = AssistantService(
            itinerary=self.service.itinerary,
            llm=StructuredIntentLLM(),
        )
        payload = AssistantRequest(
            message="Bỏ điểm đầu tiên",
            current_request=self.request(duration=1),
            current_itinerary=initial,
        )

        result = service.customize(payload)

        self.assertIn(removed_id, result["request"]["excluded_place_ids"])
        returned_ids = {
            item["id"]
            for day in result["itinerary"]
            for item in day["places"]
        }
        self.assertNotIn(removed_id, returned_ids)


if __name__ == "__main__":
    unittest.main()
