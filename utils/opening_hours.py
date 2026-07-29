import json
import re
from datetime import date


WEEKDAYS = (
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
)

VIETNAMESE_WEEKDAYS = {
    "Thứ Hai": "monday",
    "Thứ Ba": "tuesday",
    "Thứ Tư": "wednesday",
    "Thứ Năm": "thursday",
    "Thứ Sáu": "friday",
    "Thứ Bảy": "saturday",
    "Chủ Nhật": "sunday",
}

WEEKDAY_LABELS = {
    "monday": "Thứ Hai",
    "tuesday": "Thứ Ba",
    "wednesday": "Thứ Tư",
    "thursday": "Thứ Năm",
    "friday": "Thứ Sáu",
    "saturday": "Thứ Bảy",
    "sunday": "Chủ Nhật",
}

UNKNOWN_VALUE = "Đang cập nhật"
TIME_RANGE_PATTERN = re.compile(
    r"^(?P<open>[01]\d|2[0-3]):(?P<open_minute>[0-5]\d)"
    r"\s*[–—-]\s*"
    r"(?P<close>[01]\d|2[0-3]):(?P<close_minute>[0-5]\d)$"
)


def time_to_minutes(value):
    hour, minute = (int(part) for part in value.split(":"))
    return hour * 60 + minute


def minutes_to_time(value):
    value %= 24 * 60
    return f"{value // 60:02d}:{value % 60:02d}"


def _unknown_day(needs_review=False):
    return {
        "status": "unknown",
        "intervals": [],
        "needs_review": needs_review,
    }


def _parse_interval(value):
    match = TIME_RANGE_PATTERN.fullmatch(value.strip())
    if not match:
        raise ValueError(f"Khung giờ không hợp lệ: {value!r}")

    opening = f"{match.group('open')}:{match.group('open_minute')}"
    closing = f"{match.group('close')}:{match.group('close_minute')}"
    opening_minutes = time_to_minutes(opening)
    closing_minutes = time_to_minutes(closing)

    if opening_minutes == closing_minutes:
        duration = 24 * 60
        closes_next_day = True
    elif closing_minutes < opening_minutes:
        duration = closing_minutes + 24 * 60 - opening_minutes
        closes_next_day = True
    else:
        duration = closing_minutes - opening_minutes
        closes_next_day = False

    return {
        "open": opening,
        "close": closing,
        "closes_next_day": closes_next_day,
        "duration_minutes": duration,
        "needs_review": duration > 18 * 60,
    }


def parse_operation_hours(raw_value):
    raw = "" if raw_value is None else str(raw_value).strip()
    days = {weekday: _unknown_day() for weekday in WEEKDAYS}

    if not raw or raw.casefold() == UNKNOWN_VALUE.casefold():
        return {
            "status": "unknown",
            "needs_review": False,
            "parse_errors": [],
            "days": days,
        }

    errors = []
    seen = set()
    for segment in raw.split("|"):
        segment = segment.strip()
        if not segment:
            continue
        if ":" not in segment:
            errors.append(f"Thiếu tên ngày hoặc dấu hai chấm: {segment!r}")
            continue

        day_label, value = (part.strip() for part in segment.split(":", 1))
        weekday = VIETNAMESE_WEEKDAYS.get(day_label)
        if not weekday:
            errors.append(f"Tên ngày không hợp lệ: {day_label!r}")
            continue
        if weekday in seen:
            errors.append(f"Ngày bị lặp: {day_label}")
            continue
        seen.add(weekday)

        if value.casefold() == "đóng cửa":
            days[weekday] = {
                "status": "closed",
                "intervals": [],
                "needs_review": False,
            }
            continue
        if value.casefold() == "mở cửa cả ngày":
            days[weekday] = {
                "status": "open_24h",
                "intervals": [
                    {
                        "open": "00:00",
                        "close": "00:00",
                        "closes_next_day": True,
                        "duration_minutes": 24 * 60,
                        "needs_review": False,
                    }
                ],
                "needs_review": False,
            }
            continue

        intervals = []
        try:
            intervals = [
                _parse_interval(item)
                for item in value.split(",")
                if item.strip()
            ]
            if not intervals:
                raise ValueError("Không có khung giờ")
        except ValueError as error:
            errors.append(f"{day_label}: {error}")
            days[weekday] = _unknown_day(needs_review=True)
            continue

        days[weekday] = {
            "status": "open",
            "intervals": intervals,
            "needs_review": any(
                interval["needs_review"] for interval in intervals
            ),
        }

    missing_days = [
        WEEKDAY_LABELS[weekday]
        for weekday in WEEKDAYS
        if weekday not in seen
    ]
    if missing_days:
        errors.append("Thiếu ngày: " + ", ".join(missing_days))

    needs_review = bool(errors) or any(
        day["needs_review"] for day in days.values()
    )
    known_days = sum(
        day["status"] != "unknown" for day in days.values()
    )
    return {
        "status": "known" if known_days else "unknown",
        "needs_review": needs_review,
        "parse_errors": errors,
        "days": days,
    }


def opening_hours_to_json(value):
    return json.dumps(
        parse_operation_hours(value),
        ensure_ascii=False,
        separators=(",", ":"),
    )


def weekday_key(value):
    if isinstance(value, date):
        return WEEKDAYS[value.weekday()]
    raise TypeError("value must be datetime.date")


def find_visit_slot(day_schedule, earliest_minutes, duration_minutes, end_minutes):
    status = day_schedule.get("status", "unknown")
    if status == "closed":
        return None
    if status == "unknown":
        end = earliest_minutes + duration_minutes
        return (earliest_minutes, end) if end <= end_minutes else None

    intervals = day_schedule.get("intervals", [])
    if status == "open_24h":
        end = earliest_minutes + duration_minutes
        return (earliest_minutes, end) if end <= end_minutes else None

    for interval in intervals:
        opening = time_to_minutes(interval["open"])
        closing = time_to_minutes(interval["close"])
        if interval.get("closes_next_day"):
            closing += 24 * 60
        start = max(earliest_minutes, opening)
        end = start + duration_minutes
        if end <= min(closing, end_minutes):
            return start, end
    return None

