from datetime import date
from typing import get_args

import pytest
from pydantic import ValidationError

from agent.memory import AgentMemory
from agent.tools import ApplyTripChangesInput, SoulVietToolExecutor
from models.user_request import RegionName, UserRequest, VibeName
from services.itinerary_service import ItineraryService
from utils.place_matching import normalize_text, place_types


class StableRouting:
    def build_matrix(self, places):
        metrics = {}
        for source in places:
            for destination in places:
                same = source["id"] == destination["id"]
                metrics[(source["id"], destination["id"])] = {
                    "distance_km": 0 if same else 0.5,
                    "duration_minutes": 0 if same else 2,
                    "source": "test_matrix",
                }
        return {
            "metrics": metrics,
            "source": "test_matrix",
            "fallback_reason": None,
        }


def request_data(**overrides):
    values = {
        "duration": 2,
        "vibe": get_args(VibeName)[0],
        "region": get_args(RegionName)[1],
        "start_date": date(2026, 8, 1),
    }
    values.update(overrides)
    return UserRequest(**values).model_dump(mode="json")


def test_update_tool_only_changes_working_request(tmp_path):
    executor = SoulVietToolExecutor(memory=AgentMemory(tmp_path))
    state = {
        "current_request": request_data(),
        "current_itinerary": [],
    }

    observation, updates = executor.execute(
        "update_trip_settings",
        {"duration": 3, "max_daily_distance_km": 12},
        state,
    )

    assert observation["ok"]
    assert state["current_request"]["duration"] == 2
    assert updates["working_request"]["duration"] == 3
    assert updates["dirty"] is True


def test_location_focus_switches_stale_region_automatically(tmp_path):
    executor = SoulVietToolExecutor(memory=AgentMemory(tmp_path))
    state = {
        "current_request": request_data(region="Đà Nẵng"),
        "current_itinerary": [],
    }

    observation, updates = executor.execute(
        "update_trip_settings",
        {
            "duration": 2,
            "location_focus": "Hội An",
            "location_mode": "strict",
        },
        state,
    )

    assert observation["data"]["locality_resolution"]["region"] == "Quảng Nam"
    assert updates["working_request"]["region"] == "Quảng Nam"
    assert updates["working_request"]["location_focus"] == "Hội An"


def test_resolve_location_scope_reads_region_and_capacity_from_graph(tmp_path):
    executor = SoulVietToolExecutor(memory=AgentMemory(tmp_path))

    observation, updates = executor.execute(
        "resolve_location_scope",
        {"query": "Hội An"},
        {"current_request": request_data(region="Đà Nẵng")},
    )

    assert updates == {}
    assert observation["data"]["region"] == "Quảng Nam"
    assert observation["data"]["attraction_candidates"] >= 2
    assert "meal_candidates" not in observation["data"]


def test_hoi_an_preflight_has_enough_candidates_for_two_days(tmp_path):
    itinerary = ItineraryService(routing=StableRouting())
    executor = SoulVietToolExecutor(
        itinerary=itinerary,
        memory=AgentMemory(tmp_path),
    )
    state = {
        "current_request": request_data(region="Đà Nẵng"),
        "current_itinerary": [],
    }
    _, changed = executor.execute("apply_trip_changes", {
        "trip_settings": {
            "duration": 2,
            "location_focus": "Hội An",
            "location_mode": "strict",
        },
    }, state)
    state.update(changed)

    _, replanned = executor.execute("replan_itinerary", {}, state)

    report = replanned["validation_report"]
    assert replanned["working_request"]["region"] == "Quảng Nam"
    assert report["metrics"]["preflight_attraction_candidates"] >= 2
    assert "empty_days" not in report["quality_violations"]
    assert all(day["places"] for day in replanned["working_itinerary"])


def test_focused_beach_query_drives_real_graph_candidates_and_itinerary(tmp_path):
    itinerary = ItineraryService(routing=StableRouting())
    executor = SoulVietToolExecutor(
        itinerary=itinerary,
        memory=AgentMemory(tmp_path),
    )
    state = {
        "current_request": request_data(
            region="Đà Nẵng", duration=2, max_places_per_day=3
        ),
        "current_itinerary": [],
    }
    payload = {
        "place_query": {
            "keywords": ["biển", "bãi biển", "tắm biển"],
            "types": ["beach"],
            "activity_categories": ["beach"],
            "match_mode": "focused",
            "candidate_limit": 30,
        }
    }

    _, changed = executor.execute("apply_trip_changes", payload, state)
    state.update(changed)
    allowed_ids = state["working_constraints"]["allowed_place_ids"]
    assert len(allowed_ids) >= 2
    assert all(
        "place_of_worship" not in place_types(executor.graph.get_place(place_id))
        for place_id in allowed_ids
    )

    _, replanned = executor.execute("replan_itinerary", {}, state)
    assert all(day["places"] for day in replanned["working_itinerary"])
    assert all(
        "place_of_worship" not in place_types(place)
        for day in replanned["working_itinerary"]
        for place in day["places"]
    )


def test_place_query_respects_explicit_worship_exclusion(tmp_path):
    executor = SoulVietToolExecutor(memory=AgentMemory(tmp_path))
    state = {
        "current_request": request_data(region="Đà Nẵng"),
        "current_itinerary": [],
    }

    _, changed = executor.execute("apply_trip_changes", {
        "excluded_place_types": ["place_of_worship"],
        "place_query": {
            "keywords": ["nổi tiếng"],
            "match_mode": "balanced",
            "candidate_limit": 30,
        },
    }, state)

    allowed_ids = changed["working_constraints"]["allowed_place_ids"]
    assert allowed_ids
    assert all(
        "place_of_worship" not in place_types(executor.graph.get_place(place_id))
        for place_id in allowed_ids
    )


def test_remove_mutation_preserves_every_unaffected_place_and_day(tmp_path):
    itinerary_service = ItineraryService(routing=StableRouting())
    executor = SoulVietToolExecutor(
        itinerary=itinerary_service, memory=AgentMemory(tmp_path)
    )
    request = request_data(duration=2, max_places_per_day=3)
    current = itinerary_service.build(UserRequest.model_validate(request))
    removed_id = current[0]["places"][0]["id"]
    original_days = {
        item["id"]: day_number
        for day_number, day in enumerate(current, start=1)
        for item in day["places"]
    }
    state = {"current_request": request, "current_itinerary": current}

    _, changed = executor.execute("apply_trip_changes", {
        "remove_places": [{"day": 1, "position": 1}],
    }, state)
    state.update(changed)
    _, replanned = executor.execute("replan_itinerary", {}, state)

    result_days = {
        item["id"]: day_number
        for day_number, day in enumerate(
            replanned["working_itinerary"], start=1
        )
        for item in day["places"]
    }
    assert set(result_days) == set(original_days) - {removed_id}
    assert all(
        result_days[place_id] == original_days[place_id]
        for place_id in result_days
    )
    assert replanned["validation_report"]["acceptable"] is True


def test_add_mutation_keeps_current_set_and_places_new_entity_on_target_day(tmp_path):
    itinerary_service = ItineraryService(routing=StableRouting())
    executor = SoulVietToolExecutor(
        itinerary=itinerary_service, memory=AgentMemory(tmp_path)
    )
    small_request = UserRequest.model_validate(
        request_data(duration=2, max_places_per_day=2)
    )
    current = itinerary_service.build(small_request)
    request = request_data(duration=2, max_places_per_day=3)
    state = {"current_request": request, "current_itinerary": current}
    baseline_ids = {
        item["id"] for day in current for item in day["places"]
    }

    _, changed = executor.execute("apply_trip_changes", {
        "add_places": [{"query": "Bà Nà Hills", "day": 2}],
    }, state)
    state.update(changed)
    _, replanned = executor.execute("replan_itinerary", {}, state)

    target_id = next(
        place_id
        for place_id in replanned["working_request"]["required_place_ids"]
        if place_id not in baseline_ids
    )
    result_ids = {
        item["id"]
        for day in replanned["working_itinerary"]
        for item in day["places"]
    }
    assert result_ids == baseline_ids | {target_id}
    assert any(
        item["id"] == target_id
        for item in replanned["working_itinerary"][1]["places"]
    )
    assert replanned["validation_report"]["acceptable"] is True


def test_public_add_mutation_rejects_model_selected_place_id():
    with pytest.raises(ValidationError):
        ApplyTripChangesInput.model_validate({
            "add_places": [{
                "place_id": "1ddbcea2-c38d-594b-9ced-5208ee38e11f",
                "day": 2,
            }]
        })


def test_move_mutation_preserves_set_and_only_changes_requested_day(tmp_path):
    itinerary_service = ItineraryService(routing=StableRouting())
    executor = SoulVietToolExecutor(
        itinerary=itinerary_service, memory=AgentMemory(tmp_path)
    )
    request = request_data(duration=2, max_places_per_day=3)
    current = itinerary_service.build(UserRequest.model_validate(request))
    target = current[0]["places"][0]
    baseline_ids = {
        item["id"] for day in current for item in day["places"]
    }
    state = {"current_request": request, "current_itinerary": current}

    _, changed = executor.execute("apply_trip_changes", {
        "move_places": [{"query": target["name"], "target_day": 2}],
    }, state)
    state.update(changed)
    _, replanned = executor.execute("replan_itinerary", {}, state)

    result_ids = {
        item["id"]
        for day in replanned["working_itinerary"]
        for item in day["places"]
    }
    assert result_ids == baseline_ids
    assert any(
        item["id"] == target["id"]
        for item in replanned["working_itinerary"][1]["places"]
    )
    assert replanned["validation_report"]["acceptable"] is True


def test_reorder_only_keeps_exact_current_place_set(tmp_path):
    itinerary_service = ItineraryService(routing=StableRouting())
    executor = SoulVietToolExecutor(
        itinerary=itinerary_service, memory=AgentMemory(tmp_path)
    )
    request = request_data(duration=2, max_places_per_day=3)
    current = itinerary_service.build(UserRequest.model_validate(request))
    baseline_ids = {
        item["id"] for day in current for item in day["places"]
    }
    state = {"current_request": request, "current_itinerary": current}

    _, changed = executor.execute("apply_trip_changes", {
        "optimization_policy": {
            "preserve_existing_places": True,
            "reorder_only": True,
            "minimize_travel": True,
            "fill_idle_gaps": False,
        },
    }, state)
    state.update(changed)
    _, replanned = executor.execute("replan_itinerary", {}, state)

    result_ids = {
        item["id"]
        for day in replanned["working_itinerary"]
        for item in day["places"]
    }
    assert result_ids == baseline_ids
    assert "reorder_only_changed_places" not in replanned[
        "validation_report"
    ]["quality_violations"]


def test_explicit_named_place_can_override_broad_exclusion_only_for_itself(tmp_path):
    itinerary_service = ItineraryService(routing=StableRouting())
    executor = SoulVietToolExecutor(
        itinerary=itinerary_service, memory=AgentMemory(tmp_path)
    )
    small_request = UserRequest.model_validate(request_data(
        duration=2,
        max_places_per_day=2,
        excluded_place_types=["place_of_worship"],
    ))
    current = itinerary_service.build(small_request)
    request = request_data(
        duration=2,
        max_places_per_day=3,
        excluded_place_types=["place_of_worship"],
    )
    state = {"current_request": request, "current_itinerary": current}

    _, changed = executor.execute("apply_trip_changes", {
        "add_places": [{"query": "Chùa Linh Ứng", "day": 2}],
        "scoped_exclusions": [{
            "day": 2,
            "place_types": ["place_of_worship"],
            "except_queries": ["Chùa Linh Ứng"],
        }],
    }, state)
    state.update(changed)
    _, replanned = executor.execute("replan_itinerary", {}, state)

    exceptions = set(
        replanned["working_request"]["exclusion_exception_place_ids"]
    )
    worship_ids = {
        item["id"]
        for day in replanned["working_itinerary"]
        for item in day["places"]
        if "place_of_worship" in place_types(item)
    }
    assert len(exceptions) == 1
    assert worship_ids == exceptions
    assert replanned["validation_report"]["acceptable"] is True


def test_planner_does_not_add_default_lunch_or_dinner(tmp_path):
    itinerary = ItineraryService(routing=StableRouting())

    result = itinerary.build(UserRequest.model_validate(request_data()))

    meals = [
        item
        for day in result
        for item in day.get("places", [])
        if item.get("item_type") == "meal"
    ]
    assert meals == []


def test_commit_requires_valid_working_itinerary(tmp_path):
    executor = SoulVietToolExecutor(memory=AgentMemory(tmp_path))
    state = {
        "current_request": request_data(),
        "current_itinerary": [],
        "working_request": request_data(duration=3),
        "working_itinerary": [],
        "validation_report": {"valid": False, "acceptable": False},
    }

    with pytest.raises(ValueError, match="cannot be committed"):
        executor.execute("commit_itinerary", {}, state)


def test_commit_promotes_valid_working_state(tmp_path):
    executor = SoulVietToolExecutor(memory=AgentMemory(tmp_path))
    draft = [{"day": 1, "places": [], "total_distance_km": 0}]
    state = {
        "current_request": request_data(),
        "current_itinerary": [],
        "working_request": request_data(duration=1),
        "working_itinerary": draft,
        "validation_report": {"valid": True, "acceptable": True},
    }

    _, updates = executor.execute("commit_itinerary", {}, state)

    assert updates["current_request"]["duration"] == 1
    assert updates["current_itinerary"] == draft
    assert updates["dirty"] is False
    assert updates["committed"] is True


def test_place_constraint_rejects_invented_id(tmp_path):
    executor = SoulVietToolExecutor(memory=AgentMemory(tmp_path))
    state = {"current_request": request_data(), "current_itinerary": []}

    with pytest.raises(ValueError, match="Unknown place ID"):
        executor.execute("require_place", {"place_id": "invented"}, state)


def test_replace_place_excludes_old_requires_new_and_keeps_day(tmp_path):
    executor = SoulVietToolExecutor(memory=AgentMemory(tmp_path))
    places = [
        place for place in executor.graph.get_all_places()
        if place["region"] == get_args(RegionName)[1]
        and "attraction" in place.get("roles", [])
    ][:2]
    state = {
        "current_request": request_data(),
        "current_itinerary": [{"places": [{"id": places[0]["id"]}]}],
    }

    _, updates = executor.execute("replace_itinerary_item", {
        "old_place_id": places[0]["id"],
        "new_place_id": places[1]["id"],
        "keep_same_day": True,
    }, state)

    assert places[0]["id"] in updates["working_request"]["excluded_place_ids"]
    assert places[1]["id"] in updates["working_request"]["required_place_ids"]
    assert updates["working_constraints"]["required_place_days"][places[1]["id"]] == 1


def test_move_place_creates_a_day_anchor(tmp_path):
    executor = SoulVietToolExecutor(memory=AgentMemory(tmp_path))
    place = next(
        place for place in executor.graph.get_all_places()
        if place["region"] == get_args(RegionName)[1]
    )
    state = {"current_request": request_data(), "current_itinerary": []}

    _, updates = executor.execute("move_itinerary_item", {
        "place_id": place["id"], "target_day": 2,
    }, state)

    assert updates["working_constraints"]["required_place_days"][place["id"]] == 2
    assert place["id"] in updates["working_request"]["required_place_ids"]


def test_named_place_is_resolved_fuzzily_and_can_be_anchored(tmp_path):
    executor = SoulVietToolExecutor(memory=AgentMemory(tmp_path))
    target = next(
        place for place in executor.graph.get_all_places()
        if place["region"] == get_args(RegionName)[1]
        and normalize_text(place["name"]) == "bai bien son tra"
    )
    state = {"current_request": request_data(), "current_itinerary": []}

    observation, updates = executor.execute(
        "require_place", {"query": "biển Sơn Trà", "day": 2}, state
    )

    assert observation["data"]["id"] == target["id"]
    assert target["id"] in updates["working_request"]["required_place_ids"]
    assert updates["working_constraints"]["required_place_days"][target["id"]] == 2


def test_named_place_can_be_removed_without_a_prior_search_call(tmp_path):
    executor = SoulVietToolExecutor(memory=AgentMemory(tmp_path))
    target = next(
        place for place in executor.graph.get_all_places()
        if place["region"] == get_args(RegionName)[1]
        and normalize_text(place["name"]) == "bai bien son tra"
    )
    state = {"current_request": request_data(), "current_itinerary": []}

    _, updates = executor.execute(
        "remove_itinerary_item", {"query": "biển Sơn Trà"}, state
    )

    assert target["id"] in updates["working_request"]["excluded_place_ids"]


def test_replacement_accepts_a_new_place_name(tmp_path):
    executor = SoulVietToolExecutor(memory=AgentMemory(tmp_path))
    places = [
        place for place in executor.graph.get_all_places()
        if place["region"] == get_args(RegionName)[1]
        and "attraction" in place.get("roles", [])
    ]
    old_place = places[0]
    new_place = next(place for place in places if place["id"] != old_place["id"])
    state = {
        "current_request": request_data(),
        "current_itinerary": [{"places": [{"id": old_place["id"]}]}],
    }

    _, updates = executor.execute("replace_itinerary_item", {
        "old_place_id": old_place["id"],
        "new_query": new_place["name"],
        "keep_same_day": True,
    }, state)

    assert old_place["id"] in updates["working_request"]["excluded_place_ids"]
    assert new_place["id"] in updates["working_request"]["required_place_ids"]
    assert updates["working_constraints"]["required_place_days"][new_place["id"]] == 1


def test_exclusion_tool_covers_place_types_and_activity_categories(tmp_path):
    executor = SoulVietToolExecutor(memory=AgentMemory(tmp_path))
    state = {"current_request": request_data(), "current_itinerary": []}

    _, updates = executor.execute("set_exclusion_filters", {
        "place_types": ["place_of_worship"],
        "activity_categories": ["Tâm linh & Tín ngưỡng"],
        "mode": "add",
    }, state)

    request = updates["working_request"]
    assert request["excluded_place_types"] == ["place_of_worship"]
    assert request["excluded_activity_categories"] == [
        "Tâm linh & Tín ngưỡng"
    ]


def test_preference_constraint_meal_and_quality_tools_cover_benchmark_cases(tmp_path):
    executor = SoulVietToolExecutor(memory=AgentMemory(tmp_path))
    state = {"current_request": request_data(), "current_itinerary": []}

    _, activity = executor.execute("set_activity_preferences", {
        "activities": ["Biển & Hoạt động dưới nước"], "mode": "add",
    }, state)
    state.update(activity)
    _, category = executor.execute("set_category_constraint", {
        "category": "Biển & Hoạt động dưới nước",
        "min_count": 2,
        "max_count": 2,
        "target_count": 2,
        "mode": "hard",
    }, state)
    state.update(category)
    _, meal = executor.execute("set_meal_preferences", {
        "preferences": ["lunch", "dinner", "cafe"], "mode": "add",
    }, state)
    state.update(meal)
    _, quality = executor.execute("apply_quality_policies", {
        "exclude_shop_only_attractions": True,
        "deduplicate_brands": True,
    }, state)

    assert "Biển & Hoạt động dưới nước" in state["working_request"][
        "preferred_activities"
    ]
    assert state["working_request"]["category_constraints"][0]["max_count"] == 2
    assert state["working_constraints"]["meal_preferences"] == [
        "lunch", "dinner", "cafe"
    ]
    assert quality["working_constraints"]["quality_policies"] == {
        "exclude_shop_only_attractions": True,
        "deduplicate_brands": True,
    }


def test_apply_trip_changes_rejects_unknown_fields():
    with pytest.raises(ValidationError, match="extra_forbidden"):
        ApplyTripChangesInput.model_validate({
            "meal_preferences": {
                "preferences": ["local_food"],
                "day": 2,
            },
        })


def test_category_constraint_requires_explicit_user_requirement_to_stay_hard(tmp_path):
    executor = SoulVietToolExecutor(memory=AgentMemory(tmp_path))
    state = {"current_request": request_data(), "current_itinerary": []}

    _, inferred = executor.execute("set_category_constraint", {
        "category": "văn hóa",
        "min_count": 2,
        "mode": "hard",
        "explicitly_required": False,
    }, state)
    assert inferred["working_request"]["category_constraints"][0]["mode"] == "soft"

    _, explicit = executor.execute("set_category_constraint", {
        "category": "văn hóa",
        "min_count": 2,
        "mode": "hard",
        "explicitly_required": True,
    }, state)
    assert explicit["working_request"]["category_constraints"][0]["mode"] == "hard"


def test_legacy_meal_request_is_ignored_by_attractions_only_mvp(tmp_path):
    itinerary = ItineraryService(routing=StableRouting())
    executor = SoulVietToolExecutor(
        itinerary=itinerary, memory=AgentMemory(tmp_path)
    )
    state = {
        "current_request": request_data(duration=2, max_places_per_day=3),
        "current_itinerary": [],
    }
    _, updates = executor.execute("apply_trip_changes", {
        "meal_requests": [{
            "day": 2,
            "meal_slot": "dinner",
            "preferences": ["local_food"],
            "required": True,
            "near_route": True,
        }],
    }, state)
    state.update(updates)
    _, replanned = executor.execute("replan_itinerary", {}, state)

    meals = [
        item
        for day in replanned["working_itinerary"]
        for item in day["places"]
        if item.get("item_type") == "meal"
    ]
    assert meals == []
    assert "meal_requests" not in replanned["working_constraints"]


def test_day_scoped_spiritual_filter_keeps_explicit_exception(tmp_path):
    itinerary = ItineraryService(routing=StableRouting())
    executor = SoulVietToolExecutor(
        itinerary=itinerary, memory=AgentMemory(tmp_path)
    )
    state = {
        "current_request": request_data(duration=2, max_places_per_day=3),
        "current_itinerary": [],
        "current_constraints": {
            "scoped_exclusions": [{
                "day": 2,
                "place_types": ["place_of_worship"],
                "activity_categories": [],
                "except_place_ids": [],
            }],
        },
    }
    _, updates = executor.execute("apply_trip_changes", {
        "add_places": [{"query": "Chùa Linh Ứng", "day": 2}],
        "scoped_exclusions": [{
            "day": 2,
            "place_types": ["place_of_worship"],
            "except_queries": ["Chùa Linh Ứng"],
        }],
    }, state)
    state.update(updates)
    _, replanned = executor.execute("replan_itinerary", {}, state)

    exception_id = replanned["working_constraints"]["scoped_exclusions"][0][
        "except_place_ids"
    ][0]
    assert len(replanned["working_constraints"]["scoped_exclusions"]) == 1
    worship_ids = {
        item["id"]
        for item in replanned["working_itinerary"][1]["places"]
        if "place_of_worship" in {
            item.get("type"), *item.get("types", []), *item.get("all_types", [])
        }
    }
    assert exception_id in worship_ids
    assert worship_ids == {exception_id}
    assert replanned["validation_report"]["metrics"][
        "scoped_exclusion_violations"
    ] == []


def test_day_policy_removes_least_important_current_place(tmp_path):
    executor = SoulVietToolExecutor(memory=AgentMemory(tmp_path))
    places = [
        place for place in executor.graph.get_all_places()
        if place["region"] == get_args(RegionName)[1]
        and "attraction" in place.get("roles", [])
    ][:3]
    state = {
        "current_request": request_data(),
        "current_itinerary": [{"places": places}],
    }
    _, updates = executor.execute("apply_trip_changes", {
        "day_policies": [{
            "day": 1,
            "remove_count": 1,
            "remove_strategy": "least_important",
            "max_places": 2,
        }],
    }, state)

    assert len(updates["working_request"]["excluded_place_ids"]) == 1
    assert updates["working_constraints"]["day_policies"][0][
        "max_places"
    ] == 2


def test_commit_rejects_valid_but_partial_draft(tmp_path):
    executor = SoulVietToolExecutor(memory=AgentMemory(tmp_path))
    state = {
        "current_request": request_data(),
        "current_itinerary": [],
        "working_request": request_data(),
        "working_itinerary": [{"places": [], "total_distance_km": 0}],
        "validation_report": {
            "valid": True,
            "acceptable": False,
            "status": "partial",
        },
    }

    with pytest.raises(ValueError, match="not acceptable"):
        executor.execute("commit_itinerary", {}, state)
