from datetime import timedelta

from services.graph_service import GraphService
from services.budget_service import BudgetService
from services.routing_service import RoutingService
from services.route_optimizer import RouteOptimizer
from utils.opening_hours import (
    WEEKDAY_LABELS,
    find_visit_slot,
    minutes_to_time,
    time_to_minutes,
    visit_start_windows,
    weekday_key,
)


class ItineraryService:
    MAX_OSRM_COORDINATES = 100
    MAX_CANDIDATES_PER_DAY = 12
    START_PLACE_ID = "__route_start__"

    def __init__(self, graph=None, routing=None, optimizer=None):
        self.graph = graph or GraphService()
        self.routing = routing or RoutingService()
        self.optimizer = optimizer or RouteOptimizer()

    @staticmethod
    def _day_schedule(place, weekday):
        opening_hours = place.get("opening_hours") or {}
        return opening_hours.get("days", {}).get(
            weekday,
            {
                "status": "unknown",
                "intervals": [],
                "needs_review": False,
            },
        )

    def _evaluate_candidate(
        self,
        candidate,
        day_places,
        current_minutes,
        day_end_minutes,
        distance_used,
        max_daily_distance,
        weekday,
        route_matrix,
        start_place=None,
    ):
        previous = day_places[-1] if day_places else start_place
        metric = (
            route_matrix["metrics"].get(
                (previous["id"], candidate["id"])
            )
            if previous
            else {
                "distance_km": 0.0,
                "duration_minutes": 0,
                "source": route_matrix["source"],
            }
        )
        if metric is None:
            return None
        distance = metric["distance_km"]
        if distance_used + distance > max_daily_distance:
            return None

        travel_minutes = metric["duration_minutes"]
        earliest = current_minutes + travel_minutes
        visit_minutes = candidate.get("visit_duration_minutes", 90)
        day_schedule = self._day_schedule(candidate, weekday)
        slot = find_visit_slot(
            day_schedule,
            earliest,
            visit_minutes,
            day_end_minutes,
        )
        if slot is None:
            return None

        warnings = []
        if day_schedule.get("status") == "unknown":
            warnings.append("Giờ mở cửa chưa được xác minh")
        if day_schedule.get("needs_review") or candidate.get(
            "opening_hours_needs_review"
        ):
            warnings.append("Giờ mở cửa có dấu hiệu bất thường, cần kiểm tra")

        return {
            "place": candidate,
            "distance": distance,
            "travel_minutes": travel_minutes,
            "arrival_minutes": slot[0],
            "departure_minutes": slot[1],
            "day_schedule": day_schedule,
            "warnings": warnings,
            "travel_time_source": metric["source"],
        }

    def _select_next_place(
        self,
        day_places,
        remaining,
        scores,
        current_minutes,
        day_end_minutes,
        distance_used,
        max_daily_distance,
        weekday,
        route_matrix,
        start_place=None,
    ):
        connected_ids = {
            edge["to"]
            for place in day_places
            for edge in self.graph.get_neighbors(place["id"])
        }
        eligible = []
        for candidate in remaining:
            evaluation = self._evaluate_candidate(
                candidate,
                day_places,
                current_minutes,
                day_end_minutes,
                distance_used,
                max_daily_distance,
                weekday,
                route_matrix,
                start_place,
            )
            if evaluation is None:
                continue
            eligible.append(
                (
                    evaluation["travel_minutes"],
                    bool(day_places)
                    and candidate["id"] not in connected_ids,
                    evaluation["distance"],
                    -scores[candidate["id"]],
                    evaluation,
                )
            )

        if not eligible:
            return None
        eligible.sort(key=lambda item: item[:4])
        return eligible[0][4]

    @staticmethod
    def _timeline_item(evaluation):
        place = evaluation["place"]
        day_schedule = evaluation["day_schedule"]
        return {
            **place,
            "arrival_time": minutes_to_time(
                evaluation["arrival_minutes"]
            ),
            "departure_time": minutes_to_time(
                evaluation["departure_minutes"]
            ),
            "distance_from_previous_km": round(
                evaluation["distance"], 2
            ),
            "travel_time_minutes": evaluation["travel_minutes"],
            "travel_time_source": evaluation["travel_time_source"],
            "opening_status_for_day": day_schedule.get(
                "status", "unknown"
            ),
            "opening_intervals_for_day": day_schedule.get(
                "intervals", []
            ),
            "schedule_verified": False,
            "schedule_verification_status": place.get(
                "opening_hours_verification_status",
                "source_unverified",
            ),
            "schedule_warnings": evaluation["warnings"],
        }

    def _build_day(
        self,
        remaining,
        scores,
        max_places,
        max_daily_distance,
        trip_date,
        day_start_minutes,
        day_end_minutes,
        route_matrix,
        start_place=None,
    ):
        weekday = weekday_key(trip_date)
        day_places = []
        timeline = []
        distance_used = 0.0
        travel_minutes_used = 0
        current_minutes = day_start_minutes

        all_day_schedules = {
            place["id"]: self._day_schedule(place, weekday)
            for place in remaining
        }
        optimization_candidates = [
            place
            for place in remaining
            if visit_start_windows(
                all_day_schedules[place["id"]],
                place.get("visit_duration_minutes", 90),
                day_start_minutes,
                day_end_minutes,
            )
        ][: self.MAX_CANDIDATES_PER_DAY]
        day_schedules = {
            place["id"]: all_day_schedules[place["id"]]
            for place in optimization_candidates
        }
        optimized_places = self.optimizer.optimize(
            optimization_candidates,
            day_schedules,
            route_matrix,
            max_places,
            max_daily_distance,
            day_start_minutes,
            day_end_minutes,
            start_place,
        )
        optimization_source = "ortools"

        if optimized_places is not None:
            for place in optimized_places:
                selection = self._evaluate_candidate(
                    place,
                    day_places,
                    current_minutes,
                    day_end_minutes,
                    distance_used,
                    max_daily_distance,
                    weekday,
                    route_matrix,
                    start_place,
                )
                if selection is None:
                    break
                day_places.append(place)
                timeline.append(self._timeline_item(selection))
                remaining.remove(place)
                distance_used += selection["distance"]
                travel_minutes_used += selection["travel_minutes"]
                current_minutes = selection["departure_minutes"]

        while (
            optimized_places is None
            and optimization_candidates
            and len(day_places) < max_places
        ):
            optimization_source = "greedy_fallback"
            selection = self._select_next_place(
                day_places,
                optimization_candidates,
                scores,
                current_minutes,
                day_end_minutes,
                distance_used,
                max_daily_distance,
                weekday,
                route_matrix,
                start_place,
            )
            if selection is None:
                break

            place = selection["place"]
            day_places.append(place)
            timeline.append(self._timeline_item(selection))
            remaining.remove(place)
            optimization_candidates.remove(place)
            distance_used += selection["distance"]
            travel_minutes_used += selection["travel_minutes"]
            current_minutes = selection["departure_minutes"]

        return {
            "date": trip_date.isoformat(),
            "weekday": WEEKDAY_LABELS[weekday],
            "day_start_time": minutes_to_time(day_start_minutes),
            "day_end_time": minutes_to_time(day_end_minutes),
            "places": timeline,
            "total_distance_km": round(distance_used, 2),
            "total_travel_time_minutes": travel_minutes_used,
            "travel_time_source": route_matrix["source"],
            "routing_fallback_reason": route_matrix["fallback_reason"],
            "route_optimization_source": optimization_source,
            "route_optimization_objective": (
                "travel_time_plus_visit_duration"
            ),
            "start_location": (
                {
                    "name": start_place["name"],
                    "lat": start_place["lat"],
                    "lng": start_place["lng"],
                }
                if start_place
                else None
            ),
        }

    def build(self, user):
        filtered = self.graph.filter_places(user)
        budget_limit = BudgetService.trip_limit(
            user.budget_level, user.duration
        )
        scored = [
            (place, self.graph.score_place(place, user))
            for place in filtered
        ]
        scored.sort(
            key=lambda item: item[1]["total"],
            reverse=True,
        )

        start_place = (
            {
                "id": self.START_PLACE_ID,
                "name": user.start_name,
                "lat": user.start_lat,
                "lng": user.start_lng,
            }
            if user.start_lat is not None
            else None
        )
        available_osrm_slots = self.MAX_OSRM_COORDINATES - int(
            start_place is not None
        )
        candidate_limit = min(
            user.duration * self.MAX_CANDIDATES_PER_DAY,
            len(scored),
            available_osrm_slots,
        )
        candidates = [
            {
                **place,
                **BudgetService.estimate_place(place, user.budget_level),
                "recommendation_score": score["total"],
                "score_breakdown": score,
            }
            for place, score in scored[:candidate_limit]
        ]
        scores = {
            place["id"]: score["total"]
            for place, score in scored[:candidate_limit]
        }
        routing_places = (
            [start_place, *candidates]
            if start_place
            else candidates
        )
        route_matrix = self.routing.build_matrix(routing_places)

        day_start_minutes = time_to_minutes(
            user.day_start_time.strftime("%H:%M")
        )
        day_end_minutes = time_to_minutes(
            user.day_end_time.strftime("%H:%M")
        )
        days = []
        for day_index in range(user.duration):
            trip_date = user.start_date + timedelta(days=day_index)
            days.append(
                self._build_day(
                    candidates,
                    scores,
                    user.max_places_per_day,
                    user.max_daily_distance_km,
                    trip_date,
                    day_start_minutes,
                    day_end_minutes,
                    route_matrix,
                    start_place,
                )
            )
        running_spend = 0
        for day in days:
            accepted = []
            for place in day["places"]:
                expected = place["expected_spend"]
                if running_spend + expected > budget_limit:
                    continue
                accepted.append(place)
                running_spend += expected
            day["places"] = accepted
            day["estimated_spend_min"] = sum(
                place["spend_min"] for place in accepted
            )
            day["estimated_spend_max"] = sum(
                place["spend_max"] for place in accepted
            )
        return days
