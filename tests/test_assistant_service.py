import unittest
from datetime import date
from typing import get_args

from models.assistant_request import AssistantRequest
from models.user_request import RegionName, UserRequest, VibeName
from services.assistant_service import AssistantService


class FakeLLM:
    def chat(self, message, itinerary, request_data, applied_changes):
        return {
            "answer": "local test",
            "provider": "test",
            "model": None,
            "fallback_reason": None,
            "usage": None,
        }


class AssistantServiceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.service = AssistantService(llm=FakeLLM())
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
