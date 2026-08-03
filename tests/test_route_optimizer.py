import unittest

from services.route_optimizer import RouteOptimizer


def open_day(start="08:00", end="18:00"):
    return {
        "status": "open",
        "intervals": [
            {
                "open": start,
                "close": end,
                "closes_next_day": False,
            }
        ],
    }


PLACES = [
    {"id": "a", "visit_duration_minutes": 30},
    {"id": "b", "visit_duration_minutes": 30},
    {"id": "c", "visit_duration_minutes": 30},
]


def matrix(
    distances=None,
    durations=None,
    places=PLACES,
    travel_minutes=10,
):
    distances = distances or {}
    durations = durations or {}
    metrics = {}
    for source in places:
        for destination in places:
            distance = distances.get(
                (source["id"], destination["id"]),
                0.0 if source is destination else 9.0,
            )
            metrics[(source["id"], destination["id"])] = {
                "distance_km": distance,
                "duration_minutes": (
                    durations.get(
                        (source["id"], destination["id"]),
                        0 if source is destination else travel_minutes,
                    )
                ),
                "source": "test_matrix",
            }
    return {"metrics": metrics}


class RouteOptimizerTests(unittest.TestCase):
    def setUp(self):
        self.optimizer = RouteOptimizer(time_limit_milliseconds=100)

    def optimize(self, route_matrix, schedules=None, **overrides):
        values = {
            "places": PLACES,
            "day_schedules": schedules
            or {place["id"]: open_day() for place in PLACES},
            "route_matrix": route_matrix,
            "max_places": 3,
            "max_distance_km": 20,
            "day_start_minutes": 8 * 60,
            "day_end_minutes": 18 * 60,
        }
        values.update(overrides)
        return self.optimizer.optimize(**values)

    def test_minimizes_travel_time_instead_of_distance(self):
        route_matrix = matrix(
            distances={
                ("a", "b"): 1,
                ("b", "a"): 1,
                ("b", "c"): 1,
                ("c", "b"): 1,
            },
            durations={
                ("a", "b"): 9,
                ("b", "a"): 9,
                ("a", "c"): 1,
                ("c", "a"): 1,
                ("b", "c"): 1,
                ("c", "b"): 1,
            },
        )

        result = self.optimize(route_matrix)
        ids = [place["id"] for place in result]
        travel_minutes = sum(
            route_matrix["metrics"][(source, destination)][
                "duration_minutes"
            ]
            for source, destination in zip(ids, ids[1:])
        )

        self.assertEqual(len(ids), 3)
        self.assertEqual(len(set(ids)), 3)
        self.assertEqual(travel_minutes, 2)

    def test_uses_real_start_place_for_first_leg(self):
        start = {"id": "hotel", "visit_duration_minutes": 0}
        places = [start, *PLACES]
        route_matrix = matrix(
            durations={
                ("hotel", "a"): 1,
                ("hotel", "b"): 50,
                ("hotel", "c"): 50,
                ("a", "b"): 1,
                ("a", "c"): 1,
                ("b", "c"): 1,
                ("c", "b"): 1,
            },
            places=places,
        )

        result = self.optimize(route_matrix, start_place=start)

        self.assertEqual(result[0]["id"], "a")

    def test_depot_leg_counts_toward_distance_limit(self):
        start = {"id": "hotel", "visit_duration_minutes": 0}
        places = [start, *PLACES]
        route_matrix = matrix(
            distances={
                ("hotel", "a"): 5,
                ("hotel", "b"): 5,
                ("hotel", "c"): 5,
            },
            places=places,
        )

        result = self.optimize(
            route_matrix,
            start_place=start,
            max_distance_km=4,
        )

        self.assertEqual(result, [])

    def test_respects_time_windows_and_excludes_closed_places(self):
        schedules = {
            "a": open_day("08:00", "09:00"),
            "b": open_day("10:00", "12:00"),
            "c": {"status": "closed", "intervals": []},
        }

        result = self.optimize(matrix(), schedules=schedules)

        self.assertEqual([place["id"] for place in result], ["a", "b"])

    def test_respects_place_and_distance_limits(self):
        route_matrix = matrix(
            {
                ("a", "b"): 1,
                ("b", "a"): 1,
            }
        )

        result = self.optimize(
            route_matrix,
            max_places=2,
            max_distance_km=1.5,
        )
        ids = [place["id"] for place in result]

        self.assertEqual(len(ids), 2)
        self.assertEqual(set(ids), {"a", "b"})

    def test_visit_durations_limit_number_of_places(self):
        places = [
            {"id": place["id"], "visit_duration_minutes": 50}
            for place in PLACES
        ]
        route_matrix = matrix(places=places, travel_minutes=0)
        schedules = {
            place["id"]: {"status": "unknown", "intervals": []}
            for place in places
        }

        result = self.optimizer.optimize(
            places,
            schedules,
            route_matrix,
            3,
            20,
            8 * 60,
            10 * 60,
        )

        self.assertEqual(len(result), 2)

    def test_never_exceeds_eight_places(self):
        places = [
            {"id": str(index), "visit_duration_minutes": 10}
            for index in range(10)
        ]
        route_matrix = matrix(places=places, travel_minutes=1)
        schedules = {
            place["id"]: {"status": "unknown", "intervals": []}
            for place in places
        }

        result = self.optimizer.optimize(
            places,
            schedules,
            route_matrix,
            8,
            100,
            8 * 60,
            18 * 60,
        )
        ids = [place["id"] for place in result]

        self.assertEqual(len(ids), 8)
        self.assertEqual(len(ids), len(set(ids)))

    def test_meals_have_fixed_windows_and_do_not_consume_place_quota(self):
        attractions = [
            {"id": "a", "visit_duration_minutes": 60},
            {"id": "b", "visit_duration_minutes": 60},
        ]
        physical_restaurants = [
            {"id": "r1", "visit_duration_minutes": 90},
            {"id": "r2", "visit_duration_minutes": 90},
        ]
        meals = [
            {
                **physical_restaurants[0], "id": "lunch-r1", "routing_id": "r1",
                "item_type": "meal", "meal_slot": "lunch",
                "fixed_start_minutes": 11 * 60 + 30,
            },
            {
                **physical_restaurants[1], "id": "dinner-r2", "routing_id": "r2",
                "item_type": "meal", "meal_slot": "dinner",
                "fixed_start_minutes": 18 * 60,
            },
        ]
        places = [*attractions, *meals]
        route_matrix = matrix(
            places=[*attractions, *physical_restaurants],
            travel_minutes=5,
        )
        schedules = {
            place["id"]: {"status": "unknown", "intervals": []}
            for place in places
        }

        result = self.optimizer.optimize(
            places, schedules, route_matrix, 2, 100,
            8 * 60, 21 * 60,
        )

        self.assertEqual(
            len([place for place in result if place.get("item_type") != "meal"]),
            2,
        )
        self.assertEqual(
            {place.get("meal_slot") for place in result if place.get("item_type") == "meal"},
            {"lunch", "dinner"},
        )

    def test_prefers_graph_query_matches_before_shorter_unrelated_places(self):
        places = [
            {"id": "a", "visit_duration_minutes": 30, "query_priority": 50},
            {"id": "b", "visit_duration_minutes": 30, "query_priority": 20},
            {"id": "c", "visit_duration_minutes": 30, "query_priority": 0},
        ]
        route_matrix = matrix(places=places, travel_minutes=5)
        schedules = {
            place["id"]: {"status": "unknown", "intervals": []}
            for place in places
        }

        result = self.optimizer.optimize(
            places, schedules, route_matrix, 2, 100,
            8 * 60, 18 * 60,
        )

        self.assertEqual({place["id"] for place in result}, {"a", "b"})


if __name__ == "__main__":
    unittest.main()
