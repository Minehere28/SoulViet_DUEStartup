import unittest
from datetime import date, time
from typing import get_args

from models.user_request import CategoryConstraint, UserRequest
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
        self.assertEqual(report["metrics"]["max_idle_gap_minutes"], 150)
        self.assertEqual(report["metrics"]["total_idle_minutes"], 160)
        self.assertEqual(report["metrics"]["tail_gap_minutes_by_day"], [420])
        self.assertIn("day_1:large_idle_gap", report["soft_warnings"])

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

    def test_marks_a_meal_only_result_as_infeasible(self):
        itinerary = [{
            "total_distance_km": 1,
            "places": [self.item("meal", "11:30", "13:00", "meal")],
        }]

        report = ItineraryValidator.validate(itinerary, self.request())

        self.assertTrue(report["valid"])
        self.assertFalse(report["acceptable"])
        self.assertEqual(report["status"], "infeasible")
        self.assertIn("no_attractions", report["quality_violations"])

    def test_reports_duplicate_brands_as_partial(self):
        first = self.item("a", "08:00", "09:00")
        second = self.item("b", "09:10", "10:00")
        first["brand_key"] = second["brand_key"] = "same_brand"
        itinerary = [{"total_distance_km": 1, "places": [first, second]}]

        report = ItineraryValidator.validate(itinerary, self.request())

        self.assertEqual(report["status"], "partial")
        self.assertEqual(report["metrics"]["duplicate_brand_count"], 1)

    def test_reports_missing_required_place_and_category_minimum(self):
        request = self.request().model_copy(update={
            "required_place_ids": ["required"],
            "category_constraints": [CategoryConstraint(
                category="beach", min_count=1, max_count=1
            )],
        })
        itinerary = [{
            "total_distance_km": 1,
            "places": [self.item("other", "08:00", "09:00")],
        }]

        report = ItineraryValidator.validate(itinerary, request)

        self.assertEqual(report["status"], "partial")
        self.assertIn("missing_required_places", report["quality_violations"])
        self.assertIn(
            "category_constraints_unmet", report["quality_violations"]
        )


if __name__ == "__main__":
    unittest.main()
