from utils.opening_hours import time_to_minutes


class ItineraryValidator:
    """Check postconditions independently from the route optimizer."""

    @staticmethod
    def validate(itinerary, user):
        hard_violations = []
        soft_warnings = []
        seen = set()
        attraction_count = 0
        preference_matched_count = 0
        meal_count = 0

        day_start = time_to_minutes(user.day_start_time.strftime("%H:%M"))
        day_end = time_to_minutes(user.day_end_time.strftime("%H:%M"))

        for day_index, day in enumerate(itinerary, start=1):
            if day["total_distance_km"] > user.max_daily_distance_km + 0.01:
                hard_violations.append(f"day_{day_index}:distance_limit")

            previous_departure = day_start
            day_attractions = 0
            for place in day["places"]:
                place_id = place["id"]
                if place_id in seen:
                    hard_violations.append(f"duplicate_place:{place_id}")
                seen.add(place_id)

                arrival = time_to_minutes(place["arrival_time"])
                departure = time_to_minutes(place["departure_time"])
                if arrival < previous_departure or departure < arrival:
                    hard_violations.append(f"day_{day_index}:timeline_order")
                if arrival < day_start or departure > day_end:
                    hard_violations.append(f"day_{day_index}:day_window")
                if place.get("opening_status_for_day") == "closed":
                    hard_violations.append(f"closed_place:{place_id}")
                previous_departure = departure

                if place.get("item_type") == "meal":
                    meal_count += 1
                else:
                    attraction_count += 1
                    day_attractions += 1
                    if place.get("query_priority", 0) >= 20:
                        preference_matched_count += 1

            if day_attractions > user.max_places_per_day:
                hard_violations.append(f"day_{day_index}:place_limit")
            if not day["places"]:
                soft_warnings.append(f"day_{day_index}:empty")
            elif day_attractions < min(3, user.max_places_per_day):
                soft_warnings.append(f"day_{day_index}:few_attractions")

        return {
            "valid": not hard_violations,
            "hard_violations": sorted(set(hard_violations)),
            "soft_warnings": sorted(set(soft_warnings)),
            "metrics": {
                "day_count": len(itinerary),
                "attraction_count": attraction_count,
                "meal_count": meal_count,
                "preference_match_ratio": (
                    round(preference_matched_count / attraction_count, 3)
                    if attraction_count
                    else 0
                ),
                "duplicate_place_count": len(
                    [item for item in hard_violations if item.startswith("duplicate_place:")]
                ),
                "total_distance_km": round(
                    sum(day["total_distance_km"] for day in itinerary), 2
                ),
            },
        }
