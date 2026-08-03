import unittest
from datetime import date
from typing import get_args

from models.assistant_request import AssistantRequest
from models.user_request import (
    CategoryConstraint,
    RegionName,
    UserRequest,
    VibeName,
)
from services.assistant_service import AssistantService
from services.itinerary_service import ItineraryService
from models.assistant_intent import (
    AssistantIntent,
    GraphQueryPlan,
    PlaceOperation,
)


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


class SemanticFallbackLLM(FakeLLM):
    def __init__(self):
        self.classifier_calls = 0

    def parse_intent(self, _message, _request, _itinerary):
        return AssistantIntent(
            intent="modify_itinerary",
            graph_query=GraphQueryPlan(
                keywords=["nhãn bị thiếu"],
                category_constraints=[CategoryConstraint(
                    category="Biển & Hoạt động dưới nước",
                    min_count=1,
                    target_count=1,
                )],
            ),
        )

    def classify_place_matches(self, _message, candidates):
        self.classifier_calls += 1
        return {
            "matched_place_ids": [candidates[0]["id"]],
            "confidence_by_id": {candidates[0]["id"]: 0.9},
            "reason_by_id": {candidates[0]["id"]: "khớp theo ngữ nghĩa"},
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
        required_place_ids=None,
    ):
        self.candidate_counts.append(len(places))
        self.attraction_counts.append(sum(
            place.get("item_type") != "meal" for place in places
        ))
        return places[:max_places]


class EmptyThenRecoverOptimizer(FakeOptimizer):
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
        required_place_ids=None,
    ):
        self.candidate_counts.append(len(places))
        required_place_ids = set(required_place_ids or [])
        if not required_place_ids:
            return []
        return [
            place for place in places
            if place["id"] in required_place_ids
            and place.get("item_type") != "meal"
        ][:max_places]


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
        self.assertEqual(result["request"]["day_start_time"], "08:00:00")

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

    def test_applies_a_relative_daily_time_window(self):
        result = self.customize("Đi 8 điểm trong 2 tiếng và không quá 1 km")
        self.assertEqual(result["request"]["day_start_time"], "08:00:00")
        self.assertEqual(result["request"]["day_end_time"], "10:00:00")
        self.assertIn(
            result["validation_report"]["status"],
            {"partial", "infeasible"},
        )

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

    def test_budget_and_distance_questions_do_not_rebuild(self):
        current_itinerary = [{
            "date": "2026-08-01",
            "total_distance_km": 5,
            "estimated_spend_min": 100000,
            "estimated_spend_max": 200000,
            "places": [],
        }]
        for message in (
            "Tổng budget khoảng bao nhiêu?",
            "Ngày nào di chuyển xa nhất?",
        ):
            with self.subTest(message=message):
                self.optimizer.candidate_counts.clear()
                result = self.service.customize(AssistantRequest(
                    message=message,
                    current_request=self.request(),
                    current_itinerary=current_itinerary,
                ))
                self.assertEqual(result["intent"], "question")
                self.assertEqual(result["itinerary"], current_itinerary)
                self.assertEqual(self.optimizer.candidate_counts, [])

    def test_local_position_reference_removes_first_attraction(self):
        initial = self.service.itinerary.build(self.request(duration=1))
        attractions = [
            place for place in initial[0]["places"]
            if place.get("item_type") != "meal"
        ]
        removed_id = attractions[0]["id"]
        result = self.service.customize(AssistantRequest(
            message="Bỏ điểm đầu tiên ngày 1",
            current_request=self.request(duration=1),
            current_itinerary=initial,
        ))
        self.assertIn(removed_id, result["request"]["excluded_place_ids"])

    def test_natural_preference_uses_graph_query(self):
        result = self.customize(
            "Ưu tiên biển và ít di chuyển"
        )

        self.assertEqual(result["intent"], "modify_itinerary")
        self.assertIsNotNone(result["query_metadata"])
        self.assertEqual(result["query_metadata"]["near_hops"], 1)
        self.assertLessEqual(result["query_metadata"]["candidate_count"], 90)
        self.assertIn(
            "Biển & Hoạt động dưới nước",
            result["request"]["preferred_activities"],
        )

    def test_natural_beach_request_is_a_target_not_an_all_beach_rule(self):
        result = self.customize("Tôi muốn đi biển", duration=1)

        constraints = result["request"]["category_constraints"]
        beach_rule = next(
            rule for rule in constraints
            if rule["category"] == "Biển & Hoạt động dưới nước"
        )
        self.assertEqual(beach_rule["min_count"], 1)
        self.assertEqual(beach_rule["target_count"], 1)
        attractions = [
            place
            for day in result["itinerary"]
            for place in day["places"]
            if place.get("item_type") != "meal"
        ]
        beach_count = sum(
            "Biển & Hoạt động dưới nước" in place.get(
                "activity_categories", []
            )
            for place in attractions
        )
        self.assertGreaterEqual(beach_count, 1)
        self.assertLess(beach_count, len(attractions))

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

    def test_semantic_fallback_runs_once_and_keeps_the_matched_seed(self):
        llm = SemanticFallbackLLM()
        service = AssistantService(
            itinerary=self.service.itinerary,
            llm=llm,
        )

        result = service.customize(AssistantRequest(
            message="Tìm trải nghiệm có nhãn bị thiếu",
            current_request=self.request(duration=1),
        ))

        refinement = result["query_metadata"]["semantic_refinement"]
        matched_id = refinement["matched_place_ids"][0]
        self.assertEqual(llm.classifier_calls, 1)
        self.assertTrue(
            result["query_metadata"]["semantic_classifier_used"]
        )
        self.assertIn(
            matched_id,
            result["query_metadata"]["query"]["seed_place_ids"],
        )
        matched_place = next(
            place
            for day in result["itinerary"]
            for place in day["places"]
            if place["id"] == matched_id
        )
        self.assertIn(
            "Biển & Hoạt động dưới nước",
            matched_place["semantic_categories"],
        )
        self.assertGreaterEqual(
            result["validation_report"]["metrics"]["category_counts"][
                "Biển & Hoạt động dưới nước"
            ],
            1,
        )

    def test_an_trua_triggers_meal_preferences(self):
        result = self.customize("Thêm ăn trưa và ăn tối vào giúp mình")
        self.assertEqual(result["intent"], "modify_itinerary")
        self.assertIn("đổi ưu tiên ăn uống", result["applied_changes"])

    def test_cafe_accent_triggers_meal_preferences(self):
        result = self.customize("Thêm café vào buổi chiều")
        self.assertEqual(result["intent"], "modify_itinerary")
        self.assertIn("đổi ưu tiên ăn uống", result["applied_changes"])

    def test_policy_no_shops_triggers_rebuild(self):
        result = self.customize(
            "Đừng chọn toàn cửa hàng làm điểm tham quan"
        )
        self.assertEqual(result["intent"], "modify_itinerary")
        self.assertIn("lọc điểm tham quan chính", result["applied_changes"])

    def test_policy_no_brand_dupes_triggers_rebuild(self):
        result = self.customize(
            "Đừng lặp nhiều chi nhánh cùng một thương hiệu"
        )
        self.assertEqual(result["intent"], "modify_itinerary")
        self.assertIn("loại trùng thương hiệu", result["applied_changes"])

    def test_question_about_duplicates_does_not_rebuild(self):
        current_itinerary = [{
            "date": "2026-08-01",
            "total_distance_km": 5,
            "places": [],
        }]
        for message in (
            "Có địa điểm nào bị trùng không?",
            "Có ngày nào bị trống không?",
            "Tổng quãng đường khoảng bao nhiêu km?",
        ):
            with self.subTest(message=message):
                result = self.service.customize(AssistantRequest(
                    message=message,
                    current_request=self.request(duration=1),
                    current_itinerary=current_itinerary,
                ))
                self.assertEqual(result["intent"], "question")

    def test_exact_two_beaches_becomes_a_general_category_constraint(self):
        result = self.customize("Đi đúng 2 bãi biển")

        constraints = result["request"]["category_constraints"]
        self.assertEqual(len(constraints), 1)
        self.assertEqual(constraints[0]["min_count"], 2)
        self.assertEqual(constraints[0]["max_count"], 2)
        beach_count = sum(
            "Biển & Hoạt động dưới nước" in place.get(
                "activity_categories", []
            )
            for day in result["itinerary"]
            for place in day["places"]
            if place.get("item_type") != "meal"
        )
        self.assertLessEqual(beach_count, 2)

    def test_excludes_a_place_type_and_a_named_place_together(self):
        place = next(
            item for item in self.service.itinerary.graph.get_all_places()
            if item["region"] == self.region
            and item.get("type") != "place_of_worship"
            and len(item["name"]) >= 5
        )
        result = self.customize(
            f"Không muốn đi chùa và bỏ {place['name']}"
        )

        self.assertIn(
            "place_of_worship", result["request"]["excluded_place_types"]
        )
        self.assertIn(place["id"], result["request"]["excluded_place_ids"])
        returned = [
            item
            for day in result["itinerary"]
            for item in day["places"]
            if item.get("item_type") != "meal"
        ]
        self.assertNotIn(place["id"], {item["id"] for item in returned})
        self.assertTrue(all(
            "place_of_worship" not in {
                item.get("type"), *item.get("all_types", [])
            }
            for item in returned
        ))

    def test_adds_a_named_place_as_required(self):
        place = next(
            item for item in self.service.itinerary.graph.get_all_places()
            if item["region"] == self.region
            and self.service.itinerary._is_attraction(item)
            and not self.service.itinerary._is_food_place(item)
            and len(item["name"]) >= 5
        )
        result = self.customize(f"Nhất định thêm {place['name']}")

        self.assertIn(place["id"], result["request"]["required_place_ids"])
        returned_ids = {
            item["id"]
            for day in result["itinerary"]
            for item in day["places"]
        }
        self.assertIn(place["id"], returned_ids)

    def test_need_or_want_to_have_named_place_is_mandatory_anchor(self):
        target_id = "8d9e0314-917c-5164-868a-42da9b5e65a4"
        for message in (
            "Thêm bãi biển Sơn Trà",
            "Tôi cần có bãi biển Sơn Trà trong chuyến đi",
            "Tôi muốn có bãi biển Sơn Trà trong chuyến đi",
            "Thêm biển Sơn Trà vào lịch",
            "Không quá 10 km, tôi muốn có bãi biển Sơn Trà",
        ):
            with self.subTest(message=message):
                result = self.customize(message, duration=1)
                returned_ids = {
                    place["id"]
                    for day in result["itinerary"]
                    for place in day["places"]
                }
                self.assertIn(target_id, result["request"]["required_place_ids"])
                self.assertIn(target_id, returned_ids)
                self.assertIn(
                    target_id,
                    result["query_metadata"]["query"]["seed_place_ids"],
                )
                self.assertTrue(
                    result["query_metadata"]["query"]["expand_near"]
                )
                self.assertEqual(result["query_metadata"]["near_hops"], 1)

    def test_generic_beach_preference_does_not_require_a_random_beach(self):
        result = self.customize("Tôi muốn đi biển", duration=1)

        self.assertEqual(result["request"]["required_place_ids"], [])

    def test_empty_solver_result_uses_nonempty_recovery(self):
        optimizer = EmptyThenRecoverOptimizer()
        itinerary_service = ItineraryService(
            routing=FakeRouting(),
            optimizer=optimizer,
        )

        itinerary = itinerary_service.build(self.request(duration=1))
        attractions = [
            place
            for place in itinerary[0]["places"]
            if place.get("item_type") != "meal"
        ]

        self.assertTrue(attractions)
        self.assertTrue(
            itinerary[0]["route_optimization_source"].startswith(
                "ortools_nonempty_recovery"
            ),
        )

    def test_infeasible_constraint_uses_all_five_query_attempts(self):
        result = self.customize(
            "Đi đúng 8 bãi biển",
            duration=1,
            max_places_per_day=3,
        )

        self.assertEqual(result["query_metadata"]["attempts"], 5)
        self.assertEqual(len(result["query_metadata"]["attempt_history"]), 5)
        self.assertEqual(result["validation_report"]["status"], "partial")

    def test_five_day_plan_keeps_candidate_supply_for_every_day(self):
        itinerary = self.service.itinerary.build(self.request(
            duration=5,
            max_places_per_day=5,
        ))

        self.assertEqual(len(itinerary), 5)
        self.assertTrue(all(day["places"] for day in itinerary))

    def test_next_day_uses_previous_end_only_as_a_synthetic_start(self):
        itinerary = self.service.itinerary.build(self.request(
            duration=3,
            max_places_per_day=3,
        ))

        for previous_day, current_day in zip(itinerary, itinerary[1:]):
            previous_end = previous_day["places"][-1]
            start = current_day["start_location"]
            self.assertTrue(start["id"].startswith("__day_start__"))
            self.assertEqual(
                start["source_place_id"],
                previous_end.get("routing_id", previous_end["id"]),
            )
            self.assertNotIn(
                start["id"],
                {place["id"] for place in current_day["places"]},
            )

        attraction_ids = [
            place["id"]
            for day in itinerary
            for place in day["places"]
            if place.get("item_type") != "meal"
        ]
        self.assertEqual(len(attraction_ids), len(set(attraction_ids)))


if __name__ == "__main__":
    unittest.main()
