from scripts.benchmark_agent_quality import evaluate_case, load_manifest


def itinerary():
    return [{
        "day": 1,
        "total_distance_km": 5,
        "total_travel_time_minutes": 20,
        "places": [{
            "id": "hoi-an-1",
            "name": "Phố cổ Hội An",
            "address": "Hội An, Quảng Nam",
            "item_type": "attraction",
            "type": "historical_place",
            "all_types": ["historical_place", "outdoor"],
            "activity_categories": ["outdoor"],
        }],
    }]


def test_manifest_has_unique_runnable_quality_cases():
    manifest = load_manifest()

    assert len(manifest["cases"]) >= 10
    assert all(case.get("prompt") for case in manifest["cases"])
    assert all(case.get("expect") for case in manifest["cases"])


def test_evaluator_accepts_a_committed_local_itinerary():
    case = {
        "expect": {
            "provider": "gemini_langgraph",
            "committed": True,
            "requires_input": False,
            "validation_acceptable": True,
            "locality_terms": ["hoi an"],
            "min_locality_ratio": 1.0,
            "no_duplicate_places": True,
            "max_daily_distance_km": 10,
        }
    }
    response = {
        "provider": "gemini_langgraph",
        "requires_input": False,
        "agent": {"committed": True},
        "validation_report": {"acceptable": True, "status": "success"},
        "request": {"duration": 1, "region": "Quảng Nam"},
        "itinerary": itinerary(),
        "answer": "Đã cập nhật hành trình.",
    }

    assert evaluate_case(case, response["request"], itinerary(), response) == []


def test_evaluator_reports_partial_clarification_and_wrong_locality():
    case = {
        "expect": {
            "committed": True,
            "requires_input": False,
            "validation_acceptable": True,
            "locality_terms": ["hoi an"],
            "min_locality_ratio": 1.0,
            "forbidden_answer_substrings": ["partial"],
        }
    }
    bad_itinerary = itinerary()
    bad_itinerary[0]["places"][0].update({
        "name": "Bà Nà Hills",
        "address": "Đà Nẵng",
    })
    response = {
        "provider": "gemini_langgraph",
        "requires_input": True,
        "agent": {"committed": False},
        "validation_report": {"acceptable": False, "status": "partial"},
        "request": {"duration": 1, "region": "Quảng Nam"},
        "itinerary": bad_itinerary,
        "answer": "Bản nháp đang partial.",
    }

    failures = evaluate_case(
        case, response["request"], itinerary(), response
    )

    assert any("committed" in failure for failure in failures)
    assert any("requires_input" in failure for failure in failures)
    assert any("locality ratio" in failure for failure in failures)
    assert any("forbidden text" in failure for failure in failures)
