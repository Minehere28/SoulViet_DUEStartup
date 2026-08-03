"""Deterministic regression benchmark for SoulViet recommendation behavior."""

import argparse
from datetime import date
from typing import get_args

from models.assistant_intent import AssistantIntent, GraphQueryPlan
from models.assistant_request import AssistantRequest
from models.user_request import RegionName, UserRequest, VibeName
from services.assistant_service import AssistantService
from services.graph_query_service import GraphQueryService
from services.itinerary_service import ItineraryService
from services.itinerary_validator import ItineraryValidator
from utils.place_matching import normalize_text, place_types


BEACH_CATEGORY = "Biển & Hoạt động dưới nước"


class StableRouting:
    """Keep benchmark results independent from public OSRM availability."""

    def build_matrix(self, places):
        metrics = {}
        for source in places:
            for destination in places:
                same = source["id"] == destination["id"]
                metrics[(source["id"], destination["id"])] = {
                    "distance_km": 0 if same else 0.5,
                    "duration_minutes": 0 if same else 2,
                    "source": "benchmark_matrix",
                }
        return {
            "metrics": metrics,
            "source": "benchmark_matrix",
            "fallback_reason": None,
        }


class LocalBenchmarkLLM:
    def chat(self, *_args, **_kwargs):
        return {
            "answer": "benchmark",
            "provider": "benchmark",
            "model": None,
            "fallback_reason": None,
            "usage": None,
        }


class SemanticFallbackBenchmarkLLM(LocalBenchmarkLLM):
    def __init__(self):
        self.calls = 0

    def parse_intent(self, *_args):
        return AssistantIntent(
            intent="modify_itinerary",
            graph_query=GraphQueryPlan(keywords=["nhãn-không-tồn-tại"]),
        )

    def classify_place_matches(self, _message, candidates):
        self.calls += 1
        place_id = candidates[0]["id"]
        return {
            "matched_place_ids": [place_id],
            "confidence_by_id": {place_id: 0.9},
            "reason_by_id": {place_id: "khớp theo tên/mô tả"},
        }


def base_request(duration=2):
    return UserRequest(
        duration=duration,
        vibe=get_args(VibeName)[1],
        region=get_args(RegionName)[1],
        start_date=date(2026, 8, 4),
        max_places_per_day=5,
        max_daily_distance_km=20,
    )


def attraction_places(itinerary):
    return [
        place
        for day in itinerary
        for place in day.get("places", [])
        if place.get("item_type") != "meal"
    ]


def add_result(results, name, passed, detail):
    results.append({
        "name": name,
        "passed": bool(passed),
        "detail": detail,
    })


def run(days=10):
    itinerary_service = ItineraryService(routing=StableRouting())
    assistant = AssistantService(
        itinerary=itinerary_service,
        llm=LocalBenchmarkLLM(),
    )
    results = []

    request = base_request(days)
    itinerary = itinerary_service.build(request)
    report = ItineraryValidator.validate(itinerary, request)
    counts = [
        sum(place.get("item_type") != "meal" for place in day["places"])
        for day in itinerary
    ]
    add_result(
        results,
        "multi_day_no_empty_attraction",
        len(itinerary) == days and all(count > 0 for count in counts),
        f"attractions/day={counts}",
    )
    attraction_ids = [place["id"] for place in attraction_places(itinerary)]
    add_result(
        results,
        "multi_day_no_duplicate_attraction",
        len(attraction_ids) == len(set(attraction_ids)),
        f"total={len(attraction_ids)}, unique={len(set(attraction_ids))}",
    )
    continuity_ok = all(
        (current.get("start_location") or {}).get("source_place_id")
        == previous["places"][-1].get(
            "routing_id", previous["places"][-1]["id"]
        )
        for previous, current in zip(itinerary, itinerary[1:])
        if previous["places"]
    )
    add_result(
        results,
        "cross_day_location_continuity",
        continuity_ok,
        "day N start source equals day N-1 final physical location",
    )
    evening_days = sum(
        any(
            place.get("item_type") != "meal"
            and place["arrival_time"] >= "19:00"
            for place in day["places"]
        )
        for day in itinerary
    )
    add_result(
        results,
        "evening_window_is_used",
        evening_days >= max(1, days // 2),
        f"evening activity days={evening_days}/{days}",
    )
    add_result(
        results,
        "no_large_internal_timeline_gap",
        report["metrics"]["max_idle_gap_minutes"] < 90,
        f"max internal idle={report['metrics']['max_idle_gap_minutes']} min",
    )
    filled_count = sum(
        day.get("gap_filler_added_count", 0) for day in itinerary
    )
    add_result(
        results,
        "gap_filler_is_exercised",
        filled_count > 0,
        f"places inserted into large gaps={filled_count}",
    )

    def ask(message, duration=1):
        return assistant.customize(AssistantRequest(
            message=message,
            current_request=base_request(duration),
        ))

    exact_one = ask("Đi đúng 1 bãi biển")
    exact_one_places = attraction_places(exact_one["itinerary"])
    exact_one_count = sum(
        BEACH_CATEGORY in place.get("activity_categories", [])
        for place in exact_one_places
    )
    add_result(
        results,
        "exactly_one_beach",
        exact_one_count == 1,
        f"beach count={exact_one_count}",
    )

    natural = ask("Tôi muốn đi biển")
    natural_places = attraction_places(natural["itinerary"])
    natural_beaches = sum(
        BEACH_CATEGORY in place.get("activity_categories", [])
        for place in natural_places
    )
    add_result(
        results,
        "natural_beach_request_is_balanced",
        1 <= natural_beaches < len(natural_places),
        f"beaches={natural_beaches}/{len(natural_places)}",
    )

    target = next(
        place
        for place in itinerary_service.graph.get_all_places()
        if normalize_text(place["name"]) == "bai bien son tra"
        and place["region"] == base_request().region
    )
    for key, message in (
        ("add_named_place", "Thêm bãi biển Sơn Trà"),
        (
            "need_named_place",
            "Tôi cần có bãi biển Sơn Trà trong chuyến đi",
        ),
        ("fuzzy_named_place", "Thêm biển Sơn Trà vào lịch"),
    ):
        result = ask(message, duration=2)
        returned_ids = {
            place["id"] for place in attraction_places(result["itinerary"])
        }
        query = result["query_metadata"]["query"]
        passed = (
            target["id"] in result["request"]["required_place_ids"]
            and target["id"] in returned_ids
            and target["id"] in query["seed_place_ids"]
            and query["expand_near"]
        )
        add_result(
            results,
            key,
            passed,
            f"required/present/anchor={passed}",
        )

    anchored = ask("Thêm bãi biển Sơn Trà", duration=2)
    provenance = anchored["query_metadata"]["provenance"].values()
    around_count = sum(
        source.startswith(("near:", "similar:"))
        for source in provenance
    )
    add_result(
        results,
        "anchor_has_surrounding_candidates",
        around_count > 0,
        f"near/similar candidates={around_count}",
    )

    excluded = ask(
        "Tôi k muốn đi chùa và bỏ Bãi biển Sơn Trà",
        duration=2,
    )
    excluded_places = attraction_places(excluded["itinerary"])
    worship_returned = [
        place["name"] for place in excluded_places
        if "place_of_worship" in place_types(place)
    ]
    add_result(
        results,
        "exclude_type_and_named_place_together",
        (
            "place_of_worship" in excluded["request"]["excluded_place_types"]
            and target["id"] in excluded["request"]["excluded_place_ids"]
            and target["id"] not in {
                place["id"] for place in excluded_places
            }
            and not worship_returned
        ),
        f"worship returned={worship_returned}",
    )

    query_score = GraphQueryService._query_score
    add_result(
        results,
        "semantic_match_name",
        query_score(
            {"name": "Bãi biển ẩn", "description": "", "types": [],
             "all_types": [], "activities": [],
             "activity_categories": [], "vibes": []},
            GraphQueryPlan(keywords=["bãi biển ẩn"]),
        ) > 0,
        "keyword matched from place name without category tag",
    )
    add_result(
        results,
        "semantic_match_activity_and_vibe",
        query_score(
            {"name": "Điểm X", "description": "", "types": [],
             "all_types": [], "activities": [],
             "activity_categories": [BEACH_CATEGORY],
             "vibes": ["Chữa lành & Yên bình"]},
            GraphQueryPlan(
                activity_categories=[BEACH_CATEGORY],
                vibes=["Chữa lành & Yên bình"],
            ),
        ) >= 4,
        "activity category and vibe are both scored",
    )

    semantic_llm = SemanticFallbackBenchmarkLLM()
    semantic_assistant = AssistantService(
        itinerary=itinerary_service,
        llm=semantic_llm,
    )
    semantic = semantic_assistant.customize(AssistantRequest(
        message="Tìm điểm phù hợp dù dữ liệu thiếu nhãn",
        current_request=base_request(1),
    ))
    semantic_ids = {
        place["id"] for place in attraction_places(semantic["itinerary"])
    }
    matched_ids = set(
        semantic["query_metadata"]["semantic_refinement"][
            "matched_place_ids"
        ]
    )
    add_result(
        results,
        "bounded_llm_semantic_fallback",
        (
            semantic_llm.calls == 1
            and matched_ids <= semantic_ids
            and semantic["query_metadata"]["semantic_classifier_used"]
        ),
        f"LLM calls={semantic_llm.calls}, matched scheduled={matched_ids <= semantic_ids}",
    )

    return results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=10, choices=range(3, 15))
    args = parser.parse_args()
    results = run(args.days)
    width = max(len(result["name"]) for result in results)
    for result in results:
        status = "PASS" if result["passed"] else "FAIL"
        print(f"[{status}] {result['name']:<{width}}  {result['detail']}")
    passed = sum(result["passed"] for result in results)
    print(f"\nSummary: {passed}/{len(results)} passed")
    raise SystemExit(0 if passed == len(results) else 1)


if __name__ == "__main__":
    main()
