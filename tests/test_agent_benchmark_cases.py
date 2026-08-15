"""Schema-level regression coverage for the 35 itinerary-edit benchmarks.

These payloads represent the structured calls the LLM is expected to make.
Semantic executor/planner behavior is covered in test_agent_tools.py.
"""

import pytest

from agent.tools import ApplyTripChangesInput
from models.user_request import RegionName


DA_NANG = "Đà Nẵng"
QUANG_NAM = "Quảng Nam"


BENCHMARK_TOOL_CALLS = [
    {"activity_preferences": {"activities": ["outdoor", "beach"], "mode": "add"}, "trip_settings": {"max_daily_distance_km": 12}, "remove_places": [{"day": 1, "position": 1}]},
    {"add_places": [{"query": "Chua Linh Ung", "day": 2}]},
    {"add_places": [{"query": "Ba Na Hills", "day_strategy": "most_free"}]},
    {"category_constraints": [{"category": "beach", "min_count": 1, "mode": "hard"}]},
    {"meal_requests": [{"day": 2, "meal_slot": "dinner", "preferences": ["local_food"], "required": True}]},
    {"remove_places": [{"day": 1, "position": 1}]},
    {"remove_places": [{"day": 2, "position": 2}]},
    {"remove_places": [{"day": 3, "relative_position": "last", "item_type": "attraction"}]},
    {"remove_places": [{"query": "Ba Na Hills"}]},
    {"remove_places": [{"query": "Chua Linh Ung"}]},
    {"excluded_place_types": ["place_of_worship"]},
    {"excluded_activity_categories": ["indoor"], "activity_preferences": {"activities": ["outdoor"], "mode": "add"}},
    {"excluded_place_types": ["shopping_mall", "store", "gift_shop"]},
    {"excluded_place_types": ["place_of_worship"], "activity_preferences": {"activities": ["culture", "history"], "mode": "add"}},
    {"activity_preferences": {"activities": ["nature", "outdoor"], "mode": "add"}, "trip_settings": {"max_daily_distance_km": 10}},
    {"activity_preferences": {"activities": ["interactive"], "mode": "add"}},
    {"meal_preferences": {"preferences": ["local_food"], "mode": "add"}},
    {"add_places": [{"query": "Chua Linh Ung", "day": 2}], "scoped_exclusions": [{"day": 2, "place_types": ["place_of_worship"], "except_queries": ["Chua Linh Ung"]}]},
    {"replacements": [{"old_query": "Ba Na Hills", "new_query": "dia diem thien nhien", "keep_same_day": True}]},
    {"day_policies": [{"day": 1, "remove_count": 1, "remove_strategy": "least_important", "max_places": 3}]},
    {"optimization_policy": {"reorder_only": True, "minimize_travel": True}},
    {"trip_settings": {"duration": 3, "region": QUANG_NAM}},
    {"trip_settings": {"duration": 5}, "quality_policies": {"deduplicate_brands": True}},
    {"trip_settings": {"region": DA_NANG}, "activity_preferences": {"activities": ["beach", "local_food"], "mode": "replace"}},
    {"trip_settings": {"duration": 2, "region": QUANG_NAM}, "excluded_place_types": ["place_of_worship"]},
    {"remove_places": [{"day": 1, "position": 1}]},
    {"excluded_place_types": ["place_of_worship"], "activity_preferences": {"activities": ["outdoor", "culture"], "mode": "add"}},
    {"meal_requests": [{"day_strategy": "most_free", "meal_slot": "dinner", "preferences": ["local_food"], "near_route": True}]},
    {"optimization_policy": {"reorder_only": True, "minimize_travel": True}},
    {"trip_settings": {"duration": 4, "region": QUANG_NAM}, "activity_preferences": {"activities": ["nature", "beach", "interactive"], "mode": "replace"}, "excluded_place_types": ["place_of_worship"], "optimization_policy": {"fill_idle_gaps": True, "minimize_travel": True}},
    {"remove_places": [{"day": 1, "position": 1}], "add_places": [{"query": "Ba Na Hills", "day": 2}], "excluded_place_types": ["place_of_worship"], "optimization_policy": {"minimize_travel": True}},
    {"trip_settings": {"duration": 3}, "activity_preferences": {"activities": ["beach", "nature", "local_food"], "mode": "replace"}, "excluded_place_types": ["place_of_worship"], "optimization_policy": {"minimize_travel": True, "fill_idle_gaps": True}},
    {"trip_settings": {"duration": 3, "region": DA_NANG, "max_places_per_day": 3}, "activity_preferences": {"activities": ["beach", "culture", "local_food"], "mode": "replace"}, "excluded_place_types": ["place_of_worship"], "day_policies": [{"day": 1, "max_places": 3}, {"day": 2, "max_places": 3}, {"day": 3, "max_places": 2}]},
    {"day_policies": [{"day": 1, "remove_count": 1, "remove_strategy": "least_important", "fill_if_idle": True}], "optimization_policy": {"minimize_travel": True, "fill_idle_gaps": True}},
    {"excluded_place_types": ["place_of_worship"], "quality_policies": {"deduplicate_brands": True, "exclude_shop_only_attractions": True}, "optimization_policy": {"minimize_travel": True, "fill_idle_gaps": True}},
]


def test_benchmark_fixture_covers_all_35_cases():
    assert len(BENCHMARK_TOOL_CALLS) == 35


@pytest.mark.parametrize("payload", BENCHMARK_TOOL_CALLS)
def test_benchmark_change_payload_is_supported(payload):
    parsed = ApplyTripChangesInput.model_validate(payload)
    assert parsed.model_dump(exclude_defaults=True, exclude_none=True)


def test_benchmark_regions_use_canonical_request_values():
    assert DA_NANG in RegionName.__args__
    assert QUANG_NAM in RegionName.__args__
