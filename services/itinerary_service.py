from datetime import timedelta

from services.graph_service import GraphService
from services.gap_filler_service import GapFillerService
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
from utils.place_matching import matches_category, normalize_text


class ItineraryService:
    MAX_OSRM_COORDINATES = 100
    MAX_CANDIDATES_PER_DAY = 12
    START_PLACE_ID = "__route_start__"
    MEAL_ALTERNATIVES_PER_SLOT = 6
    MEAL_SLOTS = (
        {"key": "lunch", "label": "Ăn trưa", "start": 690, "end": 780},
        {
            "key": "dinner",
            "label": "Ăn tối",
            "start": 1080,
            "end": 1140,
            "duration": 60,
        },
    )
    RESTAURANT_TYPES = {
        "restaurant", "vietnamese_restaurant", "seafood_restaurant",
        "fast_food_restaurant", "vegetarian_restaurant", "asian_restaurant",
        "breakfast_restaurant", "brunch_restaurant", "food_court",
    }
    FOOD_FALLBACK_TYPES = {"cafe", "coffee_shop", "bakery", "tea_house"}
    CAFE_TYPES = {"cafe", "coffee_shop", "tea_house"}
    EVENING_TYPES = {
        "amusement_center", "bar", "beer_garden", "lounge_bar",
        "market", "night_club", "performing_arts_theater",
    }
    EVENING_KEYWORDS = {
        "bar", "cau", "cho dem", "club", "lounge", "night",
        "pho di bo", "show", "walking street",
    }

    def __init__(
        self,
        graph=None,
        routing=None,
        optimizer=None,
        gap_filler=None,
    ):
        self.graph = graph or GraphService()
        self.routing = routing or RoutingService()
        self.optimizer = optimizer or RouteOptimizer()
        self.gap_filler = gap_filler or GapFillerService()

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

    @classmethod
    def _food_priority(cls, place):
        types = {
            str(value).strip().casefold()
            for value in (
                place.get("type", ""),
                *place.get("all_types", []),
                *place.get("types", []),
            )
            if value
        }
        if types & cls.RESTAURANT_TYPES or any(
            "restaurant" in value for value in types
        ):
            return 0
        if types & cls.FOOD_FALLBACK_TYPES:
            return 1
        if place.get("primary_role") == "meal":
            return 2
        return None

    @classmethod
    def _is_food_place(cls, place):
        return (
            place.get("primary_role") == "meal"
            or cls._food_priority(place) is not None
        )

    @staticmethod
    def _is_attraction(place):
        roles = place.get("roles")
        return not roles or "attraction" in roles

    @staticmethod
    def _types(place):
        return {
            str(value).strip().casefold()
            for value in (
                place.get("type", ""),
                *place.get("all_types", []),
                *place.get("types", []),
            )
            if value
        }

    @staticmethod
    def _matches_category(place, category):
        return matches_category(place, category)

    @classmethod
    def _apply_category_limits(cls, places, constraints, required_ids):
        hard_maxima = {
            rule.category: rule.max_count
            for rule in constraints
            if rule.mode == "hard" and rule.max_count is not None
        }
        selected = []
        counts = {category: 0 for category in hard_maxima}
        for place in places:
            matched = [
                category for category in hard_maxima
                if cls._matches_category(place, category)
            ]
            if place["id"] not in required_ids and any(
                counts[category] >= hard_maxima[category]
                for category in matched
            ):
                continue
            selected.append(place)
            for category in matched:
                counts[category] += 1
        return selected

    def _assign_required_days(
        self, candidates, user, day_start_minutes, day_end_minutes,
        additional_required_ids=None,
    ):
        assignments = {index: set() for index in range(user.duration)}
        required_ids = set(user.required_place_ids)
        required_ids.update(additional_required_ids or [])
        required = [
            place for place in candidates if place["id"] in required_ids
        ]
        for place in required:
            feasible_days = []
            for day_index in range(user.duration):
                trip_date = user.start_date + timedelta(days=day_index)
                schedule = self._day_schedule(place, weekday_key(trip_date))
                if visit_start_windows(
                    schedule,
                    place.get("visit_duration_minutes", 90),
                    day_start_minutes,
                    day_end_minutes,
                ):
                    feasible_days.append(day_index)
            if feasible_days:
                selected_day = min(
                    feasible_days, key=lambda index: len(assignments[index])
                )
                assignments[selected_day].add(place["id"])
        return assignments

    def _feasible_day_count(
        self, place, user, day_start_minutes, day_end_minutes
    ):
        count = 0
        for day_index in range(user.duration):
            trip_date = user.start_date + timedelta(days=day_index)
            schedule = self._day_schedule(place, weekday_key(trip_date))
            if visit_start_windows(
                schedule,
                place.get("visit_duration_minutes", 90),
                day_start_minutes,
                day_end_minutes,
            ):
                count += 1
        return count

    def _fits_segment(self, place, weekday, start_minutes, end_minutes):
        if end_minutes <= start_minutes:
            return False
        return bool(visit_start_windows(
            self._day_schedule(place, weekday),
            place.get("visit_duration_minutes", 90),
            start_minutes,
            end_minutes,
        ))

    @classmethod
    def _is_evening_suitable(cls, place):
        if cls._types(place) & cls.EVENING_TYPES:
            return True
        searchable = normalize_text(" ".join((
            place.get("name", ""),
            *place.get("activity_categories", []),
            *place.get("activities", []),
        )))
        return any(keyword in searchable for keyword in cls.EVENING_KEYWORDS)

    def _day_attraction_candidates(
        self,
        remaining,
        weekday,
        day_start_minutes,
        day_end_minutes,
        required_place_ids=None,
    ):
        required_place_ids = set(required_place_ids or [])
        feasible = [
            place for place in remaining
            if self._fits_segment(
                place, weekday, day_start_minutes, day_end_minutes
            )
        ]
        lunch = next(
            (slot for slot in self.MEAL_SLOTS if slot["key"] == "lunch"),
            None,
        )
        dinner = next(
            (slot for slot in self.MEAL_SLOTS if slot["key"] == "dinner"),
            None,
        )
        segments = []
        if lunch:
            segments.append((day_start_minutes, min(lunch["start"], day_end_minutes)))
        if lunch and dinner:
            segments.append((
                max(day_start_minutes, lunch["end"]),
                min(dinner["start"], day_end_minutes),
            ))
        evening_start = (
            max(day_start_minutes, dinner["end"])
            if dinner else day_end_minutes
        )
        evening = [
            place for place in feasible
            if self._is_evening_suitable(place)
            and self._fits_segment(
                place, weekday, evening_start, day_end_minutes
            )
        ]

        selected = []
        selected_ids = set()

        def add(place):
            if (
                place["id"] in selected_ids
                or len(selected) >= self.MAX_CANDIDATES_PER_DAY
            ):
                return
            selected.append(place)
            selected_ids.add(place["id"])

        for place in feasible:
            if place["id"] in required_place_ids:
                add(place)
        for start, end in segments:
            segment_places = [
                place for place in feasible
                if self._fits_segment(place, weekday, start, end)
            ]
            for place in segment_places[:2]:
                add(place)
        for place in evening[:2]:
            add(place)
        for place in feasible:
            add(place)

        preferred_evening_id = evening[0]["id"] if evening else None
        return [
            {
                **place,
                **(
                    {"preferred_start_minutes": evening_start}
                    if place["id"] == preferred_evening_id
                    else {}
                ),
            }
            for place in selected
        ]

    @staticmethod
    def _remove_remaining_place(remaining, place):
        place_id = place.get("routing_id", place.get("id"))
        for index, candidate in enumerate(remaining):
            if candidate.get("id") == place_id:
                remaining.pop(index)
                return

    @classmethod
    def _meal_preference_score(cls, place, preferences):
        types = cls._types(place)
        searchable = " ".join((
            place.get("name", ""),
            place.get("description", ""),
            *types,
            *place.get("activities", []),
            *place.get("activity_categories", []),
        )).casefold()
        score = 0
        for preference in preferences:
            if preference == "cafe" and types & cls.CAFE_TYPES:
                score += 4
            elif preference == "seafood" and (
                "seafood_restaurant" in types or "hải sản" in searchable
            ):
                score += 4
            elif preference == "local_food" and (
                "vietnamese_restaurant" in types
                or "địa phương" in searchable
                or "đặc sản" in searchable
                or "local" in searchable
            ):
                score += 3
        return score

    @staticmethod
    def _deduplicate_brands(places):
        selected = []
        seen = set()
        for place in places:
            brand = place.get("brand_key") or place["id"]
            if brand in seen:
                continue
            selected.append(place)
            seen.add(brand)
        return selected

    @staticmethod
    def _routing_id(place):
        return place.get("routing_id", place["id"])

    def _meal_candidates(
        self, restaurants, attractions, route_matrix, weekday,
        day_start_minutes, day_end_minutes, meal_preferences=None,
    ):
        result = []
        meal_preferences = meal_preferences or []
        meal_slots = list(self.MEAL_SLOTS)
        if "cafe" in meal_preferences:
            meal_slots.append({
                "key": "cafe_break",
                "label": "Nghỉ cà phê",
                "start": 930,
                "end": 975,
                "duration": 45,
            })
        for meal in meal_slots:
            if not (
                day_start_minutes <= meal["start"]
                and meal["end"] <= day_end_minutes
            ):
                continue
            eligible = []
            for restaurant in restaurants:
                types = self._types(restaurant)
                if meal["key"] == "cafe_break" and not types & self.CAFE_TYPES:
                    continue
                if meal["key"] in {"lunch", "dinner"} and (
                    types & self.CAFE_TYPES
                    and not types & self.RESTAURANT_TYPES
                ):
                    continue
                visit_duration = meal.get("duration", 90)
                schedule = self._day_schedule(restaurant, weekday)
                windows = visit_start_windows(
                    schedule, visit_duration, meal["start"], meal["end"]
                )
                if not any(start <= meal["start"] <= end for start, end in windows):
                    continue
                nearby_minutes = min(
                    (
                        route_matrix["metrics"][(place["id"], restaurant["id"])][
                            "duration_minutes"
                        ]
                        for place in attractions
                    ),
                    default=0,
                )
                eligible.append((
                    -self._meal_preference_score(
                        restaurant, meal_preferences
                    ),
                    self._food_priority(restaurant),
                    nearby_minutes,
                    -restaurant.get("rating", 0),
                    restaurant,
                ))
            eligible.sort(key=lambda item: item[:3])
            for _, _, _, _, restaurant in eligible[: self.MEAL_ALTERNATIVES_PER_SLOT]:
                result.append({
                    **restaurant,
                    "id": f"__meal__{meal['key']}__{restaurant['id']}",
                    "routing_id": restaurant["id"],
                    "item_type": "meal",
                    "meal_slot": meal["key"],
                    "meal_label": meal["label"],
                    "fixed_start_minutes": meal["start"],
                    "visit_duration_minutes": meal.get("duration", 90),
                })
        return result

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
                (self._routing_id(previous), self._routing_id(candidate))
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
        fixed_start = candidate.get("fixed_start_minutes")
        if fixed_start is not None:
            valid_windows = visit_start_windows(
                day_schedule, visit_minutes, fixed_start,
                fixed_start + visit_minutes,
            )
            slot = (
                (fixed_start, fixed_start + visit_minutes)
                if earliest <= fixed_start and valid_windows
                else None
            )
        else:
            optimized_start = candidate.get("_optimized_arrival_minutes")
            optimized_windows = (
                visit_start_windows(
                    day_schedule,
                    visit_minutes,
                    earliest,
                    day_end_minutes,
                )
                if optimized_start is not None
                else []
            )
            slot = (
                (optimized_start, optimized_start + visit_minutes)
                if optimized_start is not None
                and optimized_start >= earliest
                and any(
                    start <= optimized_start <= end
                    for start, end in optimized_windows
                )
                else find_visit_slot(
                    day_schedule, earliest, visit_minutes, day_end_minutes
                )
            )
        if slot is None:
            return None

        warnings = []
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
        required_place_ids=None,
    ):
        required_place_ids = set(required_place_ids or [])
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
                    candidate["id"] not in required_place_ids,
                    evaluation["travel_minutes"],
                    bool(day_places)
                    and candidate["id"] not in connected_ids,
                    evaluation["distance"],
                    -scores.get(
                        candidate["id"],
                        scores.get(self._routing_id(candidate), 0),
                    ),
                    evaluation,
                )
            )

        if not eligible:
            return None
        eligible.sort(key=lambda item: item[:5])
        return eligible[0][5]

    @staticmethod
    def _timeline_item(evaluation):
        place = evaluation["place"]
        day_schedule = evaluation["day_schedule"]
        return {
            **{
                key: value for key, value in place.items()
                if not key.startswith("_optimized_")
            },
            "id": place.get("routing_id", place["id"]),
            "item_type": place.get("item_type", "attraction"),
            "meal_slot": place.get("meal_slot"),
            "meal_label": place.get("meal_label"),
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

    def _recover_nonempty_route(
        self,
        optimized_places,
        attraction_candidates,
        optimization_candidates,
        day_schedules,
        route_matrix,
        max_places,
        max_daily_distance,
        day_start_minutes,
        day_end_minutes,
        start_place,
        required_place_ids,
    ):
        """Retry only an attraction-less result with one mandatory anchor."""
        if optimized_places and any(
            place.get("item_type") != "meal"
            for place in optimized_places
        ):
            return optimized_places, False
        if not attraction_candidates:
            return optimized_places, False

        required_place_ids = set(required_place_ids or [])
        recovery_anchors = sorted(
            attraction_candidates,
            key=lambda place: (
                place["id"] not in required_place_ids,
                -place.get("query_priority", 0),
                -place.get("recommendation_score", 0),
            ),
        )[:3]
        candidate_sets = [
            (optimization_candidates, day_schedules),
            (
                attraction_candidates,
                {
                    place["id"]: day_schedules[place["id"]]
                    for place in attraction_candidates
                },
            ),
        ]
        for anchor in recovery_anchors:
            forced_ids = {*required_place_ids, anchor["id"]}
            for candidates, schedules in candidate_sets:
                recovered = self.optimizer.optimize(
                    candidates,
                    schedules,
                    route_matrix,
                    max_places,
                    max_daily_distance,
                    day_start_minutes,
                    day_end_minutes,
                    start_place,
                    required_place_ids=forced_ids,
                )
                if recovered and any(
                    place.get("item_type") != "meal"
                    for place in recovered
                ):
                    return recovered, True
        return optimized_places, False

    def _simulate_day_route(
        self,
        route,
        weekday,
        day_start_minutes,
        day_end_minutes,
        max_daily_distance,
        route_matrix,
        start_place,
    ):
        day_places = []
        timeline = []
        distance_used = 0.0
        travel_minutes_used = 0
        current_minutes = day_start_minutes
        idle_gaps = []
        for raw_place in route:
            place = {
                key: value for key, value in raw_place.items()
                if not key.startswith("_optimized_")
            }
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
                return None
            idle_gaps.append(max(
                0,
                selection["arrival_minutes"]
                - current_minutes
                - selection["travel_minutes"],
            ))
            day_places.append(place)
            timeline.append(self._timeline_item(selection))
            distance_used += selection["distance"]
            travel_minutes_used += selection["travel_minutes"]
            current_minutes = selection["departure_minutes"]
        tail_gap = max(0, day_end_minutes - current_minutes)
        idle_gaps.append(tail_gap)
        return {
            "day_places": day_places,
            "timeline": timeline,
            "total_distance_km": distance_used,
            "total_travel_time_minutes": travel_minutes_used,
            "idle_gaps": idle_gaps,
            "max_idle_gap_minutes": max(idle_gaps, default=0),
            "total_idle_minutes": sum(idle_gaps),
        }

    def _build_day(
        self,
        remaining,
        restaurants,
        scores,
        max_places,
        max_daily_distance,
        trip_date,
        day_start_minutes,
        day_end_minutes,
        route_matrix,
        start_place=None,
        meal_preferences=None,
        required_place_ids=None,
        reserved_place_ids=None,
    ):
        weekday = weekday_key(trip_date)
        day_places = []
        timeline = []
        distance_used = 0.0
        travel_minutes_used = 0
        current_minutes = day_start_minutes

        reserved_place_ids = set(reserved_place_ids or [])
        required_place_ids = set(required_place_ids or [])
        eligible_remaining = [
            place for place in remaining
            if place["id"] not in reserved_place_ids
            or place["id"] in required_place_ids
        ]
        attraction_candidates = self._day_attraction_candidates(
            eligible_remaining,
            weekday,
            day_start_minutes,
            day_end_minutes,
            required_place_ids,
        )
        all_day_schedules = {
            place["id"]: self._day_schedule(place, weekday)
            for place in attraction_candidates
        }
        meal_candidates = self._meal_candidates(
            restaurants, attraction_candidates, route_matrix, weekday,
            day_start_minutes, day_end_minutes, meal_preferences,
        )
        optimization_candidates = [*attraction_candidates, *meal_candidates]
        all_day_schedules.update({
            place["id"]: self._day_schedule(place, weekday)
            for place in meal_candidates
        })
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
            required_place_ids=required_place_ids,
        )
        optimized_places, recovered_nonempty = self._recover_nonempty_route(
            optimized_places,
            attraction_candidates,
            optimization_candidates,
            day_schedules,
            route_matrix,
            max_places,
            max_daily_distance,
            day_start_minutes,
            day_end_minutes,
            start_place,
            required_place_ids,
        )
        optimization_source = (
            "ortools_nonempty_recovery"
            if recovered_nonempty
            else "ortools"
        )

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
                if place.get("item_type") != "meal":
                    self._remove_remaining_place(remaining, place)
                distance_used += selection["distance"]
                travel_minutes_used += selection["travel_minutes"]
                current_minutes = selection["departure_minutes"]

        while (
            optimized_places is None
            and optimization_candidates
            and sum(
                place.get("item_type") != "meal" for place in day_places
            ) < max_places
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
                required_place_ids,
            )
            if selection is None:
                break

            place = selection["place"]
            day_places.append(place)
            timeline.append(self._timeline_item(selection))
            if place.get("item_type") != "meal":
                self._remove_remaining_place(remaining, place)
            optimization_candidates.remove(place)
            distance_used += selection["distance"]
            travel_minutes_used += selection["travel_minutes"]
            current_minutes = selection["departure_minutes"]

        (
            gap_route,
            gap_simulation,
            gap_added_ids,
            gap_removed_places,
        ) = self.gap_filler.fill(
            day_places,
            remaining,
            lambda route: self._simulate_day_route(
                route,
                weekday,
                day_start_minutes,
                day_end_minutes,
                max_daily_distance,
                route_matrix,
                start_place,
            ),
            max_places,
            reserved_place_ids,
            required_place_ids,
        )
        if gap_added_ids and gap_simulation is not None:
            day_places = gap_simulation["day_places"]
            timeline = gap_simulation["timeline"]
            distance_used = gap_simulation["total_distance_km"]
            travel_minutes_used = gap_simulation[
                "total_travel_time_minutes"
            ]
            for place_id in gap_added_ids:
                self._remove_remaining_place(
                    remaining,
                    {"id": place_id},
                )
            remaining.extend(gap_removed_places)
            optimization_source = f"{optimization_source}_gap_fill"

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
            "gap_filler_added_count": len(gap_added_ids),
            "gap_filler_replaced_count": len(gap_removed_places),
            "start_location": (
                {
                    "id": start_place["id"],
                    "source_place_id": start_place.get("source_place_id"),
                    "name": start_place["name"],
                    "lat": start_place["lat"],
                    "lng": start_place["lng"],
                }
                if start_place
                else None
            ),
            "_used_restaurant_ids": [
                self._routing_id(place)
                for place in day_places
                if place.get("item_type") == "meal"
            ],
            "_end_place": day_places[-1] if day_places else None,
        }

    def build(
        self,
        user,
        candidate_ids=None,
        candidate_priorities=None,
        meal_preferences=None,
        candidate_semantic_categories=None,
    ):
        day_start_minutes = time_to_minutes(
            user.day_start_time.strftime("%H:%M")
        )
        day_end_minutes = time_to_minutes(
            user.day_end_time.strftime("%H:%M")
        )
        filtered = self.graph.filter_places(user)
        selected_candidate_ids = (
            set(candidate_ids) if candidate_ids is not None else None
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
        all_candidates = [
            {
                **place,
                **BudgetService.estimate_place(place, user.budget_level),
                "semantic_categories": list(
                    (candidate_semantic_categories or {}).get(
                        place["id"], []
                    )
                ),
                "recommendation_score": score["total"],
                "score_breakdown": score,
            }
            for place, score in scored
        ]
        requested_places = user.duration * user.max_places_per_day
        desired_candidates = (requested_places * 5 + 1) // 2
        meal_reserve = min(30, max(12, user.duration * 2 + 2))
        attraction_limit = min(
            user.duration * self.MAX_CANDIDATES_PER_DAY,
            desired_candidates,
            max(1, available_osrm_slots - meal_reserve),
        )
        candidate_priorities = candidate_priorities or {}
        required_ids = set(user.required_place_ids)

        def constraint_priority(place):
            return max((
                200
                for rule in user.category_constraints
                if (rule.min_count or rule.target_count)
                and self._matches_category(place, rule.category)
            ), default=0)

        raw_candidates = [
            {
                **place,
                "query_priority": max(
                    candidate_priorities.get(place["id"], 0),
                    constraint_priority(place),
                    1000 if place["id"] in required_ids else 0,
                ),
            }
            for place in all_candidates
            if not self._is_food_place(place)
            and self._is_attraction(place)
            and (
                selected_candidate_ids is None
                or place["id"] in selected_candidate_ids
            )
        ]
        raw_candidates.sort(key=lambda place: (
            place["id"] not in required_ids,
            -place.get("query_priority", 0),
            -self._feasible_day_count(
                place, user, day_start_minutes, day_end_minutes
            ),
            -place.get("recommendation_score", 0),
        ))
        candidates = self._deduplicate_brands(raw_candidates)
        candidates = self._apply_category_limits(
            candidates, user.category_constraints, required_ids
        )[:attraction_limit]
        quota_required_ids = set()
        for rule in user.category_constraints:
            if rule.mode != "hard" or rule.min_count <= 0:
                continue
            matching_ids = [
                place["id"]
                for place in candidates
                if self._matches_category(place, rule.category)
            ]
            quota_required_ids.update(matching_ids[:rule.min_count])
        restaurant_limit = max(
            0, available_osrm_slots - len(candidates)
        )
        restaurants = self._deduplicate_brands([
            place for place in all_candidates if self._is_food_place(place)
        ])
        restaurants.sort(key=lambda place: (
            -self._meal_preference_score(place, meal_preferences or []),
            self._food_priority(place),
            -place.get("rating", 0),
        ))
        restaurants = restaurants[:restaurant_limit]
        scores = {
            place["id"]: score["total"]
            for place, score in scored
        }
        routing_places = (
            [start_place, *candidates, *restaurants]
            if start_place
            else [*candidates, *restaurants]
        )
        route_matrix = self.routing.build_matrix(routing_places)

        required_by_day = self._assign_required_days(
            candidates,
            user,
            day_start_minutes,
            day_end_minutes,
            quota_required_ids,
        )
        days = []
        current_start = start_place
        for day_index in range(user.duration):
            trip_date = user.start_date + timedelta(days=day_index)
            days.append(
                self._build_day(
                    candidates,
                    restaurants,
                    scores,
                    user.max_places_per_day,
                    user.max_daily_distance_km,
                    trip_date,
                    day_start_minutes,
                    day_end_minutes,
                    route_matrix,
                    current_start,
                    meal_preferences,
                    required_by_day[day_index],
                    set().union(*(
                        required_by_day[index]
                        for index in range(day_index + 1, user.duration)
                    )),
                )
            )
            used_restaurants = set(days[-1].pop("_used_restaurant_ids"))
            end_place = days[-1].pop("_end_place")
            restaurants[:] = [
                place for place in restaurants
                if place["id"] not in used_restaurants
            ]
            if end_place:
                source_place_id = self._routing_id(end_place)
                current_start = {
                    "id": f"__day_start__{day_index + 2}",
                    "routing_id": source_place_id,
                    "source_place_id": source_place_id,
                    "name": end_place["name"],
                    "lat": end_place["lat"],
                    "lng": end_place["lng"],
                    "visit_duration_minutes": 0,
                }
        for day in days:
            day["estimated_spend_min"] = sum(
                place["spend_min"] for place in day["places"]
            )
            day["estimated_spend_max"] = sum(
                place["spend_max"] for place in day["places"]
            )
        return days
