from types import MappingProxyType
from uuid import UUID

import pytest
from soulviet_contracts import (
    GeoPoint,
    Money,
    MoneyRange,
    OpeningDay,
    OpeningSchedule,
    OpeningWindow,
    PlaceIR,
    PlaceType,
    SourceProvenance,
)

SOURCE_ID = UUID("52bb0cd5-d8cb-59a3-a844-e385104ce979")


def test_coordinate_and_opening_window_invariants() -> None:
    assert GeoPoint(158_772_080, 1_083_281_008).crs == "EPSG:4326"
    assert OpeningWindow(0, 1440).ends_next_day is False
    assert OpeningWindow(1080, 0, True).ends_next_day is True
    with pytest.raises(ValueError):
        GeoPoint(900_000_001, 0)
    with pytest.raises(ValueError):
        OpeningWindow(1440, 1440)
    with pytest.raises(ValueError):
        OpeningWindow(1080, 0, False)


def test_money_range_distinguishes_free_unknown_and_open_ended() -> None:
    zero = Money(0)
    assert MoneyRange("free", zero, zero).kind == "free"
    assert MoneyRange("unknown").lower is None
    assert MoneyRange("open_ended", Money(500_000)).upper is None
    with pytest.raises(ValueError):
        MoneyRange("unknown", Money(0))


def test_schedule_requires_seven_ordered_days() -> None:
    days = tuple(OpeningDay(day, "unknown") for day in range(1, 8))
    assert len(OpeningSchedule(days).days) == 7
    with pytest.raises(ValueError):
        OpeningSchedule(days[:-1])


def test_place_ir_collections_and_provenance_are_immutable() -> None:
    raw = {"Id": str(SOURCE_ID)}
    provenance = SourceProvenance(
        source_name="fixture",
        source_path="fixture.csv",
        source_sha256="0" * 64,
        row_number=2,
        source_record_id=SOURCE_ID,
        raw_row=raw,
    )
    raw["Id"] = "changed"
    place = PlaceIR(
        id=SOURCE_ID,
        name="Place",
        location=GeoPoint(0, 0),
        place_types=(PlaceType("source:place", "place"),),
        opening_schedule=OpeningSchedule(tuple(OpeningDay(day, "unknown") for day in range(1, 8))),
        reference_price=MoneyRange("unknown"),
        provenance=provenance,
    )
    assert provenance.raw_row["Id"] == str(SOURCE_ID)
    assert isinstance(provenance.raw_row, MappingProxyType)
    assert isinstance(place.extensions, MappingProxyType)


def test_place_identity_must_match_provenance() -> None:
    provenance = SourceProvenance(
        source_name="fixture",
        source_path="fixture.csv",
        source_sha256="0" * 64,
        row_number=2,
        source_record_id=SOURCE_ID,
        raw_row={},
    )
    with pytest.raises(ValueError):
        PlaceIR(
            id=UUID("841cb6cf-93f8-556e-b02b-b5762154204a"),
            name="Place",
            location=GeoPoint(0, 0),
            place_types=(PlaceType("source:place", "place"),),
            opening_schedule=OpeningSchedule(
                tuple(OpeningDay(day, "unknown") for day in range(1, 8))
            ),
            reference_price=MoneyRange("unknown"),
            provenance=provenance,
        )
