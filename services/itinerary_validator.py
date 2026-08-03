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
        supporting_count = 0
        seen_brands = set()
        duplicate_brands = set()
        matched_preference_groups = set()
        requested_preference_groups = {
            value.strip().casefold()
            for value in user.preferred_activities
            if value.strip()
        }

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
                    brand_key = place.get("brand_key")
                    if brand_key:
                        if brand_key in seen_brands:
                            duplicate_brands.add(brand_key)
                        seen_brands.add(brand_key)
                    if place.get("primary_role") == "supporting":
                        supporting_count += 1
                    place_groups = {
                        value.strip().casefold()
                        for value in place.get("activity_categories", [])
                        if value
                    }
                    matched_preference_groups.update(
                        requested_preference_groups & place_groups
                    )
                    if place.get("query_priority", 0) >= 20:
                        preference_matched_count += 1

            if day_attractions > user.max_places_per_day:
                hard_violations.append(f"day_{day_index}:place_limit")
            if not day["places"]:
                soft_warnings.append(f"day_{day_index}:empty")
            elif day_attractions < min(3, user.max_places_per_day):
                soft_warnings.append(f"day_{day_index}:few_attractions")

        valid = not hard_violations
        quality_violations = []
        if attraction_count == 0:
            quality_violations.append("no_attractions")
        if duplicate_brands:
            quality_violations.append("duplicate_brands")
        supporting_ratio = (
            supporting_count / attraction_count if attraction_count else 0
        )
        if supporting_ratio > 0.4:
            quality_violations.append("too_many_supporting_places")
        if any(warning.endswith(":empty") for warning in soft_warnings):
            quality_violations.append("empty_days")

        acceptable = valid and not quality_violations
        if not valid:
            status = "invalid"
        elif attraction_count == 0:
            status = "infeasible"
        elif quality_violations:
            status = "partial"
        else:
            status = "success"

        preference_match_ratio = (
            round(preference_matched_count / attraction_count, 3)
            if attraction_count
            else 0
        )
        group_coverage_ratio = (
            round(
                len(matched_preference_groups)
                / len(requested_preference_groups),
                3,
            )
            if requested_preference_groups
            else 1.0
        )

        return {
            "valid": valid,
            "acceptable": acceptable,
            "status": status,
            "hard_violations": sorted(set(hard_violations)),
            "soft_warnings": sorted(set(soft_warnings)),
            "quality_violations": sorted(set(quality_violations)),
            "metrics": {
                "day_count": len(itinerary),
                "attraction_count": attraction_count,
                "meal_count": meal_count,
                "preference_match_ratio": preference_match_ratio,
                "place_preference_match_ratio": preference_match_ratio,
                "preference_group_coverage_ratio": group_coverage_ratio,
                "duplicate_brand_count": len(duplicate_brands),
                "supporting_ratio": round(supporting_ratio, 3),
                "duplicate_place_count": len(
                    [item for item in hard_violations if item.startswith("duplicate_place:")]
                ),
                "total_distance_km": round(
                    sum(day["total_distance_km"] for day in itinerary), 2
                ),
            },
        }
