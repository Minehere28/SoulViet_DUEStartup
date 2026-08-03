import unittest

from services.gap_filler_service import GapFillerService


class GapFillerServiceTests(unittest.TestCase):
    def test_inserts_candidate_that_reduces_a_large_gap(self):
        service = GapFillerService(minimum_gap_minutes=90)
        route = [{"id": "a"}, {"id": "meal", "item_type": "meal"}]
        candidates = [{"id": "near", "recommendation_score": 5}]

        def simulate(trial):
            filled = any(place["id"] == "near" for place in trial)
            return {
                "max_idle_gap_minutes": 60 if filled else 300,
                "total_idle_minutes": 60 if filled else 300,
                "total_distance_km": 4 if filled else 3,
            }

        filled_route, result, added_ids, removed = service.fill(
            route, candidates, simulate, max_places=3
        )

        self.assertEqual(added_ids, ["near"])
        self.assertEqual(result["max_idle_gap_minutes"], 60)
        self.assertIn("near", {place["id"] for place in filled_route})
        self.assertEqual(removed, [])

    def test_does_not_take_a_place_reserved_for_another_day(self):
        service = GapFillerService(minimum_gap_minutes=90)
        route = [{"id": "a"}]
        candidates = [{"id": "reserved"}]

        def simulate(_trial):
            return {
                "max_idle_gap_minutes": 300,
                "total_idle_minutes": 300,
                "total_distance_km": 1,
            }

        _, _, added_ids, _ = service.fill(
            route,
            candidates,
            simulate,
            max_places=3,
            reserved_place_ids={"reserved"},
        )

        self.assertEqual(added_ids, [])

    def test_swaps_only_an_unprotected_place_when_insertion_is_impossible(self):
        service = GapFillerService(minimum_gap_minutes=90)
        route = [{"id": "required"}, {"id": "far"}]
        candidates = [{"id": "evening", "query_priority": 5}]

        def simulate(trial):
            ids = {place["id"] for place in trial}
            if len(trial) > 2:
                return None
            filled = "evening" in ids and "far" not in ids
            return {
                "max_idle_gap_minutes": 60 if filled else 120,
                "total_idle_minutes": 60 if filled else 120,
                "total_distance_km": 10 if filled else 19,
            }

        filled_route, result, added_ids, removed = service.fill(
            route,
            candidates,
            simulate,
            max_places=3,
            protected_place_ids={"required"},
        )

        self.assertEqual(added_ids, ["evening"])
        self.assertEqual([place["id"] for place in removed], ["far"])
        self.assertIn("required", {place["id"] for place in filled_route})
        self.assertEqual(result["max_idle_gap_minutes"], 60)

    def test_can_replace_one_far_place_with_two_gap_fillers(self):
        service = GapFillerService(minimum_gap_minutes=90)
        route = [
            {"id": "required"},
            {"id": "far"},
            {"id": "meal", "item_type": "meal"},
        ]
        candidates = [{"id": "midday"}, {"id": "evening"}]

        def simulate(trial):
            ids = {place["id"] for place in trial}
            if "far" in ids and ids & {"midday", "evening"}:
                return None
            complete = {"midday", "evening"} <= ids and "far" not in ids
            return {
                "max_idle_gap_minutes": 60 if complete else 180,
                "total_idle_minutes": 90 if complete else 300,
                "total_distance_km": 15 if complete else 19,
            }

        filled_route, result, added_ids, removed = service.fill(
            route,
            candidates,
            simulate,
            max_places=4,
            protected_place_ids={"required"},
        )

        self.assertEqual(set(added_ids), {"midday", "evening"})
        self.assertEqual([place["id"] for place in removed], ["far"])
        self.assertIn("required", {place["id"] for place in filled_route})
        self.assertEqual(result["max_idle_gap_minutes"], 60)


if __name__ == "__main__":
    unittest.main()
