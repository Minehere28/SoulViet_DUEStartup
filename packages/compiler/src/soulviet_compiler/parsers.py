from __future__ import annotations

import json
import math
import re
import struct
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from decimal import ROUND_HALF_EVEN, Decimal, InvalidOperation
from typing import Literal
from urllib.parse import urlsplit
from uuid import UUID

from soulviet_contracts import (
    GeoPoint,
    Money,
    MoneyRange,
    OpeningDay,
    OpeningSchedule,
    OpeningWindow,
)

NULL_LITERAL = "NULL"
DAY_NAMES = {
    "Thứ Hai": 1,
    "Thứ Ba": 2,
    "Thứ Tư": 3,
    "Thứ Năm": 4,
    "Thứ Sáu": 5,
    "Thứ Bảy": 6,
    "Chủ Nhật": 7,
}
TIME_RANGE = re.compile(r"^(\d{2}):(\d{2})\s*[–-]\s*(\d{2}):(\d{2})$")
BOUNDED_PRICE = re.compile(r"^(\d[\d.]*)đ\s*-\s*(\d[\d.]*)đ$")
OPEN_PRICE = re.compile(r"^Từ\s+(\d[\d.]*)đ$")


@dataclass(frozen=True)
class ParsedStringArray:
    values: tuple[tuple[int, str], ...]
    invalid_ordinals: tuple[int, ...]


MediaKind = Literal["video", "main_image", "land_image"]


@dataclass(frozen=True)
class ParsedMediaEntry:
    kind: MediaKind
    url: str
    ordinal: int


@dataclass(frozen=True)
class ParsedMedia:
    entries: tuple[ParsedMediaEntry, ...]
    invalid_fields: tuple[str, ...]


def nullable_text(value: str) -> str | None:
    stripped = value.strip()
    if not stripped or stripped == NULL_LITERAL:
        return None
    return stripped


def normalized_text(value: str) -> str:
    return unicodedata.normalize("NFKC", value).strip()


def parse_uuid(value: str) -> UUID:
    text = nullable_text(value)
    if text is None:
        raise ValueError("UUID is absent")
    try:
        return UUID(text)
    except (ValueError, AttributeError) as exc:
        raise ValueError("UUID is malformed") from exc


def parse_optional_uuid(value: str) -> UUID | None:
    text = nullable_text(value)
    return None if text is None else parse_uuid(text)


def _to_e7(value: float) -> int:
    if not math.isfinite(value):
        raise ValueError("coordinate is not finite")
    decimal_value = Decimal(str(value)).quantize(Decimal("0.0000001"), rounding=ROUND_HALF_EVEN)
    return int(decimal_value * 10_000_000)


def parse_ewkb_point(value: str) -> GeoPoint:
    text = normalized_text(value)
    try:
        payload = bytes.fromhex(text)
    except ValueError as exc:
        raise ValueError("EWKB is not valid hexadecimal") from exc
    if len(payload) != 25 or payload[0] != 1:
        raise ValueError("EWKB must be a little-endian 2D point with SRID")
    geometry_type, srid = struct.unpack_from("<II", payload, 1)
    if geometry_type != 0x20000001 or srid != 4326:
        raise ValueError("EWKB geometry or SRID is unsupported")
    longitude, latitude = struct.unpack_from("<dd", payload, 9)
    point = GeoPoint(latitude_e7=_to_e7(latitude), longitude_e7=_to_e7(longitude))
    return point


def parse_rating_e2(value: str) -> int | None:
    text = nullable_text(value)
    if text is None:
        return None
    try:
        rating = Decimal(text)
    except InvalidOperation as exc:
        raise ValueError("rating is not decimal") from exc
    if not Decimal(0) <= rating <= Decimal(5):
        raise ValueError("rating is outside 0 to 5")
    return int((rating * 100).quantize(Decimal("1"), rounding=ROUND_HALF_EVEN))


def parse_review_count(value: str) -> int | None:
    text = nullable_text(value)
    if text is None:
        return None
    try:
        count = int(text)
    except ValueError as exc:
        raise ValueError("review count is not an integer") from exc
    if count < 0:
        raise ValueError("review count is negative")
    return count


def _vnd_amount(value: str) -> Money:
    digits = value.replace(".", "")
    if not digits.isdigit():
        raise ValueError("VND amount is malformed")
    return Money(int(digits))


def parse_money_range(value: str) -> MoneyRange:
    label = normalized_text(value)
    if not label or label in {NULL_LITERAL, "Chưa phân loại"}:
        return MoneyRange(kind="unknown", source_label=label or None)
    if label == "0đ":
        zero = Money(0)
        return MoneyRange(kind="free", lower=zero, upper=zero, source_label=label)
    bounded = BOUNDED_PRICE.fullmatch(label)
    if bounded:
        return MoneyRange(
            kind="range",
            lower=_vnd_amount(bounded.group(1)),
            upper=_vnd_amount(bounded.group(2)),
            source_label=label,
        )
    open_ended = OPEN_PRICE.fullmatch(label)
    if open_ended:
        return MoneyRange(
            kind="open_ended",
            lower=_vnd_amount(open_ended.group(1)),
            source_label=label,
        )
    raise ValueError("reference price is unsupported")


def source_taxonomy(value: str) -> tuple[str, str]:
    label = normalized_text(value)
    if not label:
        raise ValueError("taxonomy label is blank")
    token = " ".join(label.casefold().split())
    return f"source:{token}", label


def parse_json_string_array(value: str) -> ParsedStringArray:
    try:
        decoded = json.loads(value)
    except json.JSONDecodeError as exc:
        raise ValueError("value is not valid JSON") from exc
    if not isinstance(decoded, list):
        raise ValueError("JSON value is not an array")
    values: list[tuple[int, str]] = []
    invalid: list[int] = []
    for ordinal, item in enumerate(decoded):
        if not isinstance(item, str) or not item.strip():
            invalid.append(ordinal)
            continue
        values.append((ordinal, item))
    return ParsedStringArray(tuple(values), tuple(invalid))


def _minute(hour: int, minute: int, *, is_end: bool) -> int:
    if hour == 24 and minute == 0 and is_end:
        return 1440
    if not 0 <= hour <= 23 or not 0 <= minute <= 59:
        raise ValueError("opening time is outside clock bounds")
    return hour * 60 + minute


def _opening_window(text: str) -> OpeningWindow:
    match = TIME_RANGE.fullmatch(text.strip())
    if match is None:
        raise ValueError("opening interval is malformed")
    start = _minute(int(match.group(1)), int(match.group(2)), is_end=False)
    end = _minute(int(match.group(3)), int(match.group(4)), is_end=True)
    ends_next_day = end <= start
    return OpeningWindow(start_minute=start, end_minute=end, ends_next_day=ends_next_day)


def parse_opening_schedule(value: str) -> tuple[OpeningSchedule, tuple[str, ...]]:
    text = normalized_text(value)
    if not text or text in {NULL_LITERAL, "Đang cập nhật"}:
        days = tuple(OpeningDay(day, "unknown") for day in range(1, 8))
        return OpeningSchedule(days), ("opening hours are unavailable",)

    parsed: dict[int, OpeningDay] = {}
    warnings: list[str] = []
    for segment in text.split(" | "):
        if ": " not in segment:
            warnings.append("opening segment is malformed")
            continue
        day_label, day_value = segment.split(": ", 1)
        weekday = DAY_NAMES.get(day_label)
        if weekday is None:
            warnings.append(f"opening weekday is unsupported: {day_label}")
            continue
        if weekday in parsed:
            parsed[weekday] = OpeningDay(weekday, "unknown")
            warnings.append(f"opening weekday is duplicated: {day_label}")
            continue
        if day_value == "Đóng cửa":
            parsed[weekday] = OpeningDay(weekday, "closed")
            continue
        if day_value == "Mở cửa cả ngày":
            parsed[weekday] = OpeningDay(
                weekday,
                "open",
                (OpeningWindow(0, 1440, False),),
            )
            continue
        try:
            windows = tuple(_opening_window(part) for part in day_value.split(","))
            parsed[weekday] = OpeningDay(weekday, "open", windows)
        except ValueError:
            parsed[weekday] = OpeningDay(weekday, "unknown")
            warnings.append(f"opening value is malformed: {day_label}")

    for weekday in range(1, 8):
        if weekday not in parsed:
            parsed[weekday] = OpeningDay(weekday, "unknown")
            warnings.append(f"opening weekday is missing: {weekday}")
    return OpeningSchedule(tuple(parsed[day] for day in range(1, 8))), tuple(warnings)


def parse_timestamp(value: str) -> datetime | None:
    text = nullable_text(value)
    if text is None:
        return None
    normalized = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        timestamp = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ValueError("timestamp is not ISO-8601") from exc
    if timestamp.tzinfo is None:
        raise ValueError("timestamp must include a timezone")
    return timestamp


def _valid_http_url(value: str) -> bool:
    parsed = urlsplit(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def parse_media_info(value: str) -> ParsedMedia:
    try:
        decoded = json.loads(value)
    except json.JSONDecodeError as exc:
        raise ValueError("media value is not valid JSON") from exc
    if not isinstance(decoded, dict):
        raise ValueError("media value is not an object")
    entries: list[ParsedMediaEntry] = []
    invalid: list[str] = []
    scalar_keys: tuple[tuple[str, MediaKind], ...] = (
        ("VideoUrl", "video"),
        ("MainImage", "main_image"),
    )
    for key, kind in scalar_keys:
        candidate = decoded.get(key, "")
        if candidate in {"", None}:
            continue
        if not isinstance(candidate, str) or not _valid_http_url(candidate):
            invalid.append(key)
            continue
        entries.append(ParsedMediaEntry(kind, candidate, 0))
    land_images = decoded.get("LandImages", [])
    if not isinstance(land_images, list):
        invalid.append("LandImages")
    else:
        for ordinal, candidate in enumerate(land_images):
            if not isinstance(candidate, str) or not _valid_http_url(candidate):
                invalid.append(f"LandImages[{ordinal}]")
                continue
            entries.append(ParsedMediaEntry("land_image", candidate, ordinal))
    return ParsedMedia(tuple(entries), tuple(invalid))
