from utils.opening_hours import time_to_minutes
from utils.place_matching import matches_category, place_categories, place_types
from services.locality_service import ResolvedLocality


class ItineraryValidator:
    """Check postconditions independently from the route optimizer."""

    @staticmethod
    def validate(itinerary, user, graph=None):
        hard_violations = []
        soft_warnings = []
        seen = set()
        attraction_count = 0
        locality_direct_count = 0
        locality_in_boundary_count = 0
        preference_matched_count = 0
        meal_count = 0
        supporting_count = 0
        seen_brands = set()
        duplicate_brands = set()
        matched_preference_groups = set()
        category_counts = {
            rule.category: 0 for rule in user.category_constraints
        }
        excluded_types = {
            value.strip().casefold()
            for value in user.excluded_place_types if value.strip()
        }
        excluded_categories = {
            value.strip().casefold()
            for value in user.excluded_activity_categories if value.strip()
        }
        requested_preference_groups = {
            value.strip().casefold()
            for value in user.preferred_activities
            if value.strip()
        }
        locality = None
        if user.location_focus and graph is not None:
            locality = ResolvedLocality.resolve(
                (
                    place for place in graph.get_all_places()
                    if place.get("region") == user.region
                ),
                user.location_focus,
                user.location_mode,
                user.location_radius_km,
                neighbor_lookup=graph.get_neighbors,
            )

        day_start = time_to_minutes(user.day_start_time.strftime("%H:%M"))
        day_end = time_to_minutes(user.day_end_time.strftime("%H:%M"))
        idle_gap_minutes_by_day = []
        tail_gap_minutes_by_day = []
        all_idle_gaps = []

        for day_index, day in enumerate(itinerary, start=1):
            if day["total_distance_km"] > user.max_daily_distance_km + 0.01:
                hard_violations.append(f"day_{day_index}:distance_limit")

            previous_departure = day_start
            day_attractions = 0
            day_idle_gaps = []
            for place in day["places"]:
                place_id = place["id"]
                if place_id in seen:
                    hard_violations.append(f"duplicate_place:{place_id}")
                seen.add(place_id)

                arrival = time_to_minutes(place["arrival_time"])
                departure = time_to_minutes(place["departure_time"])
                travel_minutes = max(
                    0, int(place.get("travel_time_minutes", 0) or 0)
                )
                idle_minutes = max(
                    0, arrival - previous_departure - travel_minutes
                )
                day_idle_gaps.append(idle_minutes)
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
                    if locality is not None:
                        locality_direct_count += int(locality.is_direct(place))
                        locality_in_boundary_count += int(locality.contains(place))
                    day_attractions += 1
                    brand_key = place.get("brand_key")
                    if brand_key:
                        if brand_key in seen_brands:
                            duplicate_brands.add(brand_key)
                        seen_brands.add(brand_key)
                    if place.get("primary_role") == "supporting":
                        supporting_count += 1
                    place_groups = place_categories(place)
                    current_place_types = place_types(place)
                    if excluded_types & current_place_types:
                        hard_violations.append(
                            f"excluded_type_present:{place_id}"
                        )
                    if excluded_categories & place_groups:
                        hard_violations.append(
                            f"excluded_category_present:{place_id}"
                        )
                    for rule in user.category_constraints:
                        if matches_category(place, rule.category):
                            category_counts[rule.category] += 1
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
            tail_gap = max(0, day_end - previous_departure)
            idle_gap_minutes_by_day.append(sum(day_idle_gaps))
            tail_gap_minutes_by_day.append(tail_gap)
            all_idle_gaps.extend(day_idle_gaps)
            if any(gap >= 90 for gap in day_idle_gaps):
                soft_warnings.append(f"day_{day_index}:large_idle_gap")

        valid = not hard_violations
        quality_violations = []
        locality_outside_count = attraction_count - locality_in_boundary_count
        if locality is not None and not locality.found:
            hard_violations.append("locality_not_found")
        elif locality is not None and locality_outside_count:
            hard_violations.append("locality_focus_violated")
        valid = not hard_violations
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
        missing_required_ids = sorted(
            set(user.required_place_ids) - seen
        )
        if missing_required_ids:
            quality_violations.append("missing_required_places")
        category_violations = []
        for rule in user.category_constraints:
            count = category_counts[rule.category]
            if rule.mode == "hard" and count < rule.min_count:
                category_violations.append(
                    f"category_min_unmet:{rule.category}"
                )
            if (
                rule.mode == "hard"
                and rule.max_count is not None
                and count > rule.max_count
            ):
                category_violations.append(
                    f"category_max_exceeded:{rule.category}"
                )
        if category_violations:
            quality_violations.append("category_constraints_unmet")

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
                "missing_required_place_ids": missing_required_ids,
                "category_counts": category_counts,
                "category_constraint_violations": category_violations,
                "idle_gap_minutes_by_day": idle_gap_minutes_by_day,
                "tail_gap_minutes_by_day": tail_gap_minutes_by_day,
                "max_idle_gap_minutes": max(all_idle_gaps, default=0),
                "total_idle_minutes": sum(all_idle_gaps),
                "large_idle_gap_count": sum(
                    gap >= 90 for gap in all_idle_gaps
                ),
                "duplicate_place_count": len(
                    [item for item in hard_violations if item.startswith("duplicate_place:")]
                ),
                "total_distance_km": round(
                    sum(day["total_distance_km"] for day in itinerary), 2
                ),
                "location_focus": user.location_focus,
                "locality_direct_ratio": round(
                    locality_direct_count / attraction_count, 3
                ) if attraction_count and locality is not None else (
                    1.0 if locality is None else 0.0
                ),
                "locality_in_boundary_ratio": round(
                    locality_in_boundary_count / attraction_count, 3
                ) if attraction_count and locality is not None else (
                    1.0 if locality is None else 0.0
                ),
            },
        }
