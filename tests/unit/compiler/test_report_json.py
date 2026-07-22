import json
from pathlib import Path

from soulviet_compiler import CsvPlaceRowAdapter, PlaceIRCompiler, build_report, render_report_json


def _report():  # type: ignore[no-untyped-def]
    rows = CsvPlaceRowAdapter().read(
        Path("tests/fixtures/tourist_attraction_v2_compiler_fixture.csv"),
        source_name="fixture",
    )
    results = tuple(PlaceIRCompiler().compile(row) for row in rows)
    return build_report(rows, results)


def test_report_json_is_stable_and_includes_summary_and_source_hash() -> None:
    report = _report()
    first = render_report_json(report, pretty=False)
    second = render_report_json(report, pretty=False)
    assert first == second
    payload = json.loads(first)
    assert payload["source"]["sha256"] == report.source_sha256
    assert payload["summary"]["input_rows"] == 6
    assert payload["summary"]["fatal_rows"] == 0
    assert [result["row_number"] for result in payload["results"]] == [2, 3, 4, 5, 6, 7]


def test_pretty_and_compact_json_have_equal_semantics() -> None:
    report = _report()
    assert json.loads(render_report_json(report, pretty=True)) == json.loads(
        render_report_json(report, pretty=False)
    )
