import unittest
from datetime import date
from typing import get_args

from models.assistant_request import AssistantRequest
from models.user_request import RegionName, UserRequest, VibeName
from services.assistant_service import AssistantService
from services.itinerary_service import ItineraryService


class FakeLLM:
    def chat(self, message, itinerary, request_data, applied_changes):
        return {
            "answer": "local test",
            "provider": "test",
            "model": None,
            "fallback_reason": None,
            "usage": None,
        }


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
        self.assertEqual(self.optimizer.candidate_counts[0], 12)

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


if __name__ == "__main__":
    unittest.main()
