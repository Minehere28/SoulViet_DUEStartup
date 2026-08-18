import argparse
import json
import sys
import unicodedata
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from uuid import uuid4

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from utils.place_matching import place_categories, place_types


DEFAULT_CASES = PROJECT_ROOT / "benchmarks" / "agent_quality_cases.json"


def normalize_text(value):
    value = str(value or "").replace("đ", "d").replace("Đ", "D")
    value = unicodedata.normalize("NFKD", value)
    value = "".join(
        character for character in value
        if not unicodedata.combining(character)
    )
    return " ".join(value.casefold().split())


def attraction_items(itinerary):
    return [
        item
        for day in itinerary or []
        for item in day.get("places", [])
        if item.get("item_type", "attraction") != "meal"
    ]


def item_at_position(itinerary, day, position, item_type="attraction"):
    if day < 1 or day > len(itinerary or []):
        return None
    items = itinerary[day - 1].get("places", [])
    if item_type != "any":
        items = [
            item for item in items
            if item.get("item_type", "attraction") == item_type
        ]
    if position < 1 or position > len(items):
        return None
    return items[position - 1]


def post_json(base_url, path, payload, timeout):
    request = Request(
        f"{base_url.rstrip('/')}{path}",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8")
    except HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {error.code} from {path}: {body[:500]}") from error
    except URLError as error:
        raise RuntimeError(f"Cannot reach {base_url}: {error.reason}") from error
    try:
        return json.loads(body)
    except json.JSONDecodeError as error:
        raise RuntimeError(f"Non-JSON response from {path}: {body[:500]}") from error


def _record(failures, condition, message):
    if not condition:
        failures.append(message)


def evaluate_case(case, initial_request, initial_itinerary, response):
    expected = case["expect"]
    failures = []
    itinerary = response.get("itinerary") or []
    request_data = response.get("request") or {}
    agent = response.get("agent") or {}
    report = response.get("validation_report") or {}
    answer = normalize_text(response.get("answer"))

    if "provider" in expected:
        _record(
            failures,
            response.get("provider") == expected["provider"],
            f"provider={response.get('provider')!r}, expected {expected['provider']!r}",
        )
        if response.get("provider") != expected["provider"]:
            provider_error = (response.get("agent") or {}).get("error")
            if provider_error:
                failures.append(
                    "provider error: "
                    f"{provider_error.get('type')}: {provider_error.get('message')}"
                )
            elif response.get("fallback_reason"):
                failures.append(
                    f"provider fallback: {response.get('fallback_reason')}"
                )
    if "committed" in expected:
        _record(
            failures,
            bool(agent.get("committed")) is expected["committed"],
            f"committed={agent.get('committed')!r}",
        )
    if "requires_input" in expected:
        _record(
            failures,
            bool(response.get("requires_input")) is expected["requires_input"],
            f"requires_input={response.get('requires_input')!r}",
        )
    if "validation_status" in expected:
        _record(
            failures,
            report.get("status") == expected["validation_status"],
            f"validation status={report.get('status')!r}",
        )
    if "validation_acceptable" in expected:
        _record(
            failures,
            bool(report.get("acceptable")) is expected["validation_acceptable"],
            f"validation acceptable={report.get('acceptable')!r}",
        )
    for field in ("duration", "region"):
        if field in expected:
            _record(
                failures,
                request_data.get(field) == expected[field],
                f"request.{field}={request_data.get(field)!r}, expected {expected[field]!r}",
            )

    for forbidden in expected.get("forbidden_answer_substrings", []):
        _record(
            failures,
            normalize_text(forbidden) not in answer,
            f"answer contains forbidden text {forbidden!r}",
        )

    attractions = attraction_items(itinerary)
    attraction_ids = [item.get("id") for item in attractions if item.get("id")]
    if expected.get("no_duplicate_places"):
        _record(
            failures,
            len(attraction_ids) == len(set(attraction_ids)),
            "itinerary contains duplicate attraction IDs",
        )

    for day_number, day in enumerate(itinerary, start=1):
        count = sum(
            item.get("item_type", "attraction") != "meal"
            for item in day.get("places", [])
        )
        if "min_attractions_per_day" in expected:
            _record(
                failures,
                count >= expected["min_attractions_per_day"],
                f"day {day_number} has only {count} attractions",
            )
        if "max_attractions_per_day" in expected:
            _record(
                failures,
                count <= expected["max_attractions_per_day"],
                f"day {day_number} has {count} attractions",
            )
        if "max_daily_distance_km" in expected:
            distance = float(day.get("total_distance_km") or 0)
            _record(
                failures,
                distance <= expected["max_daily_distance_km"] + 0.01,
                f"day {day_number} distance={distance} km",
            )
        if "max_daily_travel_minutes" in expected:
            travel = int(day.get("total_travel_time_minutes") or 0)
            _record(
                failures,
                travel <= expected["max_daily_travel_minutes"],
                f"day {day_number} travel={travel} minutes",
            )

    locality_terms = [
        normalize_text(term) for term in expected.get("locality_terms", [])
    ]
    if locality_terms:
        matched = 0
        for item in attractions:
            searchable = normalize_text(" ".join((
                str(item.get("name", "")),
                str(item.get("address", "")),
                str(item.get("description", "")),
            )))
            matched += any(term in searchable for term in locality_terms)
        ratio = matched / len(attractions) if attractions else 0
        _record(
            failures,
            ratio >= expected.get("min_locality_ratio", 1.0),
            f"locality ratio={ratio:.3f} ({matched}/{len(attractions)})",
        )

    excluded_types = {
        normalize_text(value) for value in expected.get("excluded_types", [])
    }
    excluded_categories = {
        normalize_text(value)
        for value in expected.get("excluded_categories", [])
    }
    for item in attractions:
        current_types = {normalize_text(value) for value in place_types(item)}
        current_categories = {
            normalize_text(value) for value in place_categories(item)
        }
        _record(
            failures,
            not excluded_types.intersection(current_types),
            f"excluded type present at {item.get('name')!r}",
        )
        _record(
            failures,
            not excluded_categories.intersection(current_categories),
            f"excluded category present at {item.get('name')!r}",
        )

    for category, minimum in expected.get("min_category_counts", {}).items():
        count = sum(
            normalize_text(category) in {
                normalize_text(value) for value in place_categories(item)
            }
            for item in attractions
        )
        _record(
            failures,
            count >= minimum,
            f"category {category!r} count={count}, expected >= {minimum}",
        )

    for required in expected.get("required_places", []):
        query = normalize_text(required["query"])
        days = itinerary
        if required.get("day"):
            day = int(required["day"])
            days = itinerary[day - 1:day] if day <= len(itinerary) else []
        found = any(
            query in normalize_text(item.get("name"))
            for day in days
            for item in day.get("places", [])
            if item.get("item_type", "attraction") != "meal"
        )
        _record(
            failures,
            found,
            f"required place {required['query']!r} is missing from day {required.get('day', 'any')}",
        )

    for required in expected.get("required_meals", []):
        day = int(required["day"])
        items = itinerary[day - 1].get("places", []) if day <= len(itinerary) else []
        found = any(
            item.get("item_type") == "meal"
            and item.get("meal_slot") == required["meal_slot"]
            for item in items
        )
        _record(
            failures,
            found,
            f"required meal {required['meal_slot']!r} is missing from day {day}",
        )

    for removed in expected.get("removed_initial_positions", []):
        original = item_at_position(
            initial_itinerary,
            int(removed["day"]),
            int(removed["position"]),
            removed.get("item_type", "attraction"),
        )
        _record(failures, original is not None, "initial position does not exist")
        if original:
            _record(
                failures,
                original.get("id") not in attraction_ids,
                f"initial place {original.get('name')!r} was not removed",
            )

    if expected.get("preserve_initial_attractions"):
        initial_ids = {
            item.get("id") for item in attraction_items(initial_itinerary)
            if item.get("id")
        }
        _record(
            failures,
            set(attraction_ids) == initial_ids,
            "final attraction set differs from initial attraction set",
        )

    if "max_total_distance_ratio_vs_initial" in expected:
        initial_distance = sum(
            float(day.get("total_distance_km") or 0)
            for day in initial_itinerary
        )
        final_distance = sum(
            float(day.get("total_distance_km") or 0) for day in itinerary
        )
        limit = initial_distance * expected["max_total_distance_ratio_vs_initial"]
        _record(
            failures,
            final_distance <= limit + 0.01,
            f"total distance grew from {initial_distance:.2f} to {final_distance:.2f} km",
        )

    for day_text, maximum_delta in expected.get(
        "day_attraction_delta_max", {}
    ).items():
        day = int(day_text)
        initial_count = sum(
            item.get("item_type", "attraction") != "meal"
            for item in initial_itinerary[day - 1].get("places", [])
        ) if day <= len(initial_itinerary) else 0
        final_count = sum(
            item.get("item_type", "attraction") != "meal"
            for item in itinerary[day - 1].get("places", [])
        ) if day <= len(itinerary) else 0
        _record(
            failures,
            final_count - initial_count <= maximum_delta,
            f"day {day} attraction delta={final_count - initial_count}, expected <= {maximum_delta}",
        )

    for day_text, maximum_ratio in expected.get(
        "max_day_distance_ratio_vs_initial", {}
    ).items():
        day = int(day_text)
        initial_distance = float(
            initial_itinerary[day - 1].get("total_distance_km") or 0
        ) if day <= len(initial_itinerary) else 0
        final_distance = float(
            itinerary[day - 1].get("total_distance_km") or 0
        ) if day <= len(itinerary) else 0
        _record(
            failures,
            final_distance <= initial_distance * maximum_ratio + 0.01,
            f"day {day} distance grew from {initial_distance:.2f} to {final_distance:.2f} km",
        )

    return failures


def load_manifest(path=DEFAULT_CASES):
    with Path(path).open(encoding="utf-8") as handle:
        manifest = json.load(handle)
    if manifest.get("version") != 1:
        raise ValueError("Unsupported benchmark manifest version")
    identifiers = [case["id"] for case in manifest.get("cases", [])]
    if not identifiers or len(identifiers) != len(set(identifiers)):
        raise ValueError("Benchmark case IDs must be non-empty and unique")
    return manifest


def run_case(base_url, manifest, case, timeout):
    request_data = {
        **manifest["base_request"],
        **case.get("request_overrides", {}),
    }
    planned = post_json(base_url, "/plan", request_data, timeout)
    initial_itinerary = planned.get("itinerary") or []
    response = post_json(base_url, "/assistant/chat", {
        "message": case["prompt"],
        "user_id": f"benchmark-{uuid4()}",
        "thread_id": f"benchmark-{uuid4()}",
        "current_request": request_data,
        "current_itinerary": initial_itinerary,
    }, timeout)
    failures = evaluate_case(
        case,
        request_data,
        initial_itinerary,
        response,
    )
    return {
        "id": case["id"],
        "passed": not failures,
        "failures": failures,
        "provider": response.get("provider"),
        "answer": response.get("answer"),
        "agent": response.get("agent"),
        "validation_report": response.get("validation_report"),
    }


def parse_args():
    parser = argparse.ArgumentParser(
        description="Run end-to-end SoulViet agent quality benchmark"
    )
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--case", action="append", dest="case_ids")
    parser.add_argument("--timeout", type=float, default=180)
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace")
    args = parse_args()
    manifest = load_manifest(args.cases)
    cases = manifest["cases"]
    if args.case_ids:
        selected = set(args.case_ids)
        cases = [case for case in cases if case["id"] in selected]
        missing = selected - {case["id"] for case in cases}
        if missing:
            raise SystemExit(f"Unknown case IDs: {', '.join(sorted(missing))}")
    if args.list:
        for case in cases:
            print(f"{case['id']}: {case['description']}")
        return 0

    results = []
    for case in cases:
        print(f"RUN  {case['id']}", flush=True)
        try:
            result = run_case(args.base_url, manifest, case, args.timeout)
        except Exception as error:
            result = {
                "id": case["id"],
                "passed": False,
                "failures": [f"{error.__class__.__name__}: {error}"],
            }
        results.append(result)
        status = "PASS" if result["passed"] else "FAIL"
        print(f"{status} {case['id']}")
        for failure in result.get("failures", []):
            print(f"     - {failure}")
        if not result["passed"] and result.get("agent"):
            print(
                "     agent="
                + json.dumps(result["agent"], ensure_ascii=False)
            )
        if not result["passed"] and result.get("answer"):
            print(f"     answer={result['answer']}")

    summary = {
        "passed": sum(result["passed"] for result in results),
        "total": len(results),
        "results": results,
    }
    print(json.dumps(
        {"passed": summary["passed"], "total": summary["total"]},
        ensure_ascii=False,
    ))
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    return int(summary["passed"] != summary["total"])


if __name__ == "__main__":
    sys.exit(main())
