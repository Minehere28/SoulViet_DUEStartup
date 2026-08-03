import unittest
from datetime import date, time
from typing import get_args

from models.user_request import UserRequest
from services.itinerary_validator import ItineraryValidator


class ItineraryValidatorTests(unittest.TestCase):
    def request(self):
        return UserRequest(
            duration=1,
            vibe=get_args(UserRequest.model_fields["vibe"].annotation)[0],
            region=get_args(UserRequest.model_fields["region"].annotation)[1],
            start_date=date(2026, 8, 3),
            day_start_time=time(8),
            day_end_time=time(21),
            max_places_per_day=2,
            max_daily_distance_km=10,
        )

    @staticmethod
    def item(place_id, arrival, departure, item_type="attraction"):
        return {
            "id": place_id,
            "arrival_time": arrival,
            "departure_time": departure,
            "item_type": item_type,
            "opening_status_for_day": "open",
        }

    def test_accepts_a_valid_timeline(self):
        itinerary = [{
            "total_distance_km": 5,
            "places": [
                self.item("a", "08:00", "09:00"),
                self.item("meal", "11:30", "13:00", "meal"),
                self.item("b", "13:10", "14:00"),
            ],
        }]

        report = ItineraryValidator.validate(itinerary, self.request())

        self.assertTrue(report["valid"])
        self.assertEqual(report["metrics"]["attraction_count"], 2)
        self.assertEqual(report["metrics"]["meal_count"], 1)

    def test_rejects_duplicates_distance_and_timeline_conflicts(self):
        itinerary = [{
            "total_distance_km": 12,
            "places": [
                self.item("a", "09:00", "10:00"),
                self.item("a", "09:30", "10:30"),
            ],
        }]

        report = ItineraryValidator.validate(itinerary, self.request())

        self.assertFalse(report["valid"])
        self.assertIn("day_1:distance_limit", report["hard_violations"])
        self.assertIn("day_1:timeline_order", report["hard_violations"])
        self.assertIn("duplicate_place:a", report["hard_violations"])


if __name__ == "__main__":
    unittest.main()
