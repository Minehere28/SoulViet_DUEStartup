from pathlib import Path

import pytest
from soulviet_compiler.place_compiler import PlaceIRCompiler
from soulviet_compiler.source_rows import REQUIRED_HEADERS, RawPlaceRow, RawSourceContext


def _week(value: str) -> str:
    names = ("Thứ Hai", "Thứ Ba", "Thứ Tư", "Thứ Năm", "Thứ Sáu", "Thứ Bảy", "Chủ Nhật")
    return " | ".join(f"{name}: {value}" for name in names)


def _values() -> dict[str, str]:
    values = dict.fromkeys(REQUIRED_HEADERS, "NULL")
    values.update(
        {
            "Id": "52bb0cd5-d8cb-59a3-a844-e385104ce979",
            "CategoryId": "b8160b87-2804-5067-a596-b76a5ffe7b79",
            "PlaceId": " external-value ",
            "Address": "Address",
            "ProvinceId": "5cb8d34b-5bc6-46ff-b2ee-4f50e64461fe",
            "Name": "Place",
            "Type": "cafe",
            "Description": "Description",
            "OperationHours": _week("08:00–17:00"),
            "Location": "0101000020E6100000A7727F9AFF145B4042942F6821C12F40",
            "RatingScore": "4.25",
            "ReviewCount": "12",
            "ReferencePrice": "30.000đ - 70.000đ",
            "AllTypes": '["cafe", "food"]',
            "Activities": '["Drink coffee"]',
            "TopReviews": '["Useful review"]',
            "VibeTag": "4",
            "BudgetTag": "Bình dân",
            "AiContext": "Generated context",
            "CreatedAt": "2026-07-02 17:01:21.694162+00",
            "MediaInfo": (
                '{"VideoUrl":"", "MainImage":"https://example.com/main.jpg", "LandImages":[]}'
            ),
        }
    )
    return values


def _row(values: dict[str, str] | None = None) -> RawPlaceRow:
    raw = _values() if values is None else values
    context = RawSourceContext("fixture", "fixture.csv", "0" * 64, 2, raw)
    return RawPlaceRow(2, raw, context)


def test_compiler_creates_provenance_only_after_valid_id() -> None:
    values = _values()
    values["Id"] = "invalid"
    result = PlaceIRCompiler().compile(_row(values))
    assert result.place is None
    assert result.issues[0].code == "INVALID_ID"
    assert result.issues[0].severity == "error"


@pytest.mark.parametrize("external", ["", "NULL"])
def test_blank_or_null_external_id_is_absent(external: str) -> None:
    values = _values()
    values["PlaceId"] = external
    result = PlaceIRCompiler().compile(_row(values))
    assert result.place is not None
    assert result.place.external_place_id is None


def test_arbitrary_trimmed_external_id_is_preserved_without_verification() -> None:
    result = PlaceIRCompiler().compile(_row())
    assert result.place is not None
    assert result.place.external_place_id is not None
    assert result.place.external_place_id.value == "external-value"


def test_required_fields_are_fatal_and_optional_fields_are_recoverable() -> None:
    values = _values()
    values["Type"] = ""
    values["RatingScore"] = "9"
    values["Activities"] = "not-json"
    result = PlaceIRCompiler().compile(_row(values))
    assert result.place is None
    assert [issue.field for issue in result.issues][:3] == ["Type", "RatingScore", "Activities"]
    assert any(issue.severity == "error" for issue in result.issues)
    assert any(issue.severity == "warning" for issue in result.issues)


def test_evidence_is_deterministic_and_ai_context_is_not_evidence() -> None:
    first = PlaceIRCompiler().compile(_row())
    second = PlaceIRCompiler().compile(_row())
    assert first == second
    assert first.place is not None
    assert all(reference.field != "AiContext" for reference in first.place.evidence)
    assert {"Description", "TopReviews", "MediaInfo"}.issubset(
        {reference.field for reference in first.place.evidence}
    )
    assert first.place.provenance.raw_row["AiContext"] == "Generated context"


def test_fixture_rows_compile_without_fatal_errors() -> None:
    from soulviet_compiler.source_rows import CsvPlaceRowAdapter

    rows = CsvPlaceRowAdapter().read(
        Path("tests/fixtures/tourist_attraction_v2_compiler_fixture.csv"),
        source_name="fixture",
    )
    results = tuple(PlaceIRCompiler().compile(row) for row in rows)
    assert all(result.place is not None for result in results)
