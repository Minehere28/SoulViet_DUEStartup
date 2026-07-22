from decimal import Decimal

import pytest
from soulviet_compiler.parsers import (
    parse_ewkb_point,
    parse_json_string_array,
    parse_media_info,
    parse_money_range,
    parse_opening_schedule,
    parse_rating_e2,
    parse_review_count,
    parse_timestamp,
    source_taxonomy,
)


def _week(value: str) -> str:
    names = ("Thứ Hai", "Thứ Ba", "Thứ Tư", "Thứ Năm", "Thứ Sáu", "Thứ Bảy", "Chủ Nhật")
    return " | ".join(f"{name}: {value}" for name in names)


def test_ewkb_decodes_longitude_then_latitude_to_e7() -> None:
    point = parse_ewkb_point("0101000020E6100000A7727F9AFF145B4042942F6821C12F40")
    assert point.longitude_e7 == 1_083_281_008
    assert point.latitude_e7 == 158_772_080
    with pytest.raises(ValueError):
        parse_ewkb_point("not-hex")
    with pytest.raises(ValueError):
        parse_ewkb_point("010100000000000000000000000000000000000000")


@pytest.mark.parametrize(
    ("source", "kind", "lower", "upper"),
    [
        ("0đ", "free", 0, 0),
        ("30.000đ - 70.000đ", "range", 30_000, 70_000),
        ("30.000đ - 100.000đ", "range", 30_000, 100_000),
        ("100.000đ - 300.000đ", "range", 100_000, 300_000),
        ("Từ 500.000đ", "open_ended", 500_000, None),
        ("Chưa phân loại", "unknown", None, None),
    ],
)
def test_all_reviewed_money_forms(
    source: str, kind: str, lower: int | None, upper: int | None
) -> None:
    parsed = parse_money_range(source)
    assert parsed.kind == kind
    assert (None if parsed.lower is None else parsed.lower.amount_minor) == lower
    assert (None if parsed.upper is None else parsed.upper.amount_minor) == upper


def test_taxonomy_json_numeric_and_timestamp_parsers() -> None:
    assert source_taxonomy("  Café   Bar ") == ("source:café bar", "Café   Bar")
    parsed = parse_json_string_array('["one", "two", 3, ""]')
    assert parsed.values == ((0, "one"), (1, "two"))
    assert parsed.invalid_ordinals == (2, 3)
    assert parse_rating_e2("4.25") == 425
    assert parse_review_count("12") == 12
    assert parse_timestamp("2026-07-02 17:01:21.694162+00") is not None
    with pytest.raises(ValueError):
        parse_rating_e2(str(Decimal("5.01")))


def test_opening_hours_cover_unknown_closed_all_day_normal_split_and_overnight() -> None:
    unknown, warnings = parse_opening_schedule("Đang cập nhật")
    assert all(day.status == "unknown" for day in unknown.days)
    assert warnings
    closed, _ = parse_opening_schedule(_week("Đóng cửa"))
    assert all(day.status == "closed" for day in closed.days)
    all_day, _ = parse_opening_schedule(_week("Mở cửa cả ngày"))
    assert all_day.days[0].windows[0].end_minute == 1440
    normal, _ = parse_opening_schedule(_week("08:00–17:00"))
    assert normal.days[0].windows == (normal.days[0].windows[0],)
    split, _ = parse_opening_schedule(_week("08:00–11:30, 14:00–17:30"))
    assert len(split.days[0].windows) == 2
    overnight, _ = parse_opening_schedule(_week("18:00–00:00"))
    assert overnight.days[0].windows[0].start_minute == 1080
    assert overnight.days[0].windows[0].end_minute == 0
    assert overnight.days[0].windows[0].ends_next_day is True


def test_media_parser_retains_valid_urls_and_reports_invalid_entries() -> None:
    parsed = parse_media_info(
        '{"VideoUrl":"", "MainImage":"https://example.com/main.jpg", '
        '"LandImages":["http://example.com/one.jpg", "ftp://invalid"]}'
    )
    assert [entry.kind for entry in parsed.entries] == ["main_image", "land_image"]
    assert parsed.invalid_fields == ("LandImages[1]",)
