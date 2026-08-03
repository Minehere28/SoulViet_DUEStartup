import re
import unicodedata


CATEGORY_ALIASES = {
    "bai bien": {"beach", "bai bien", "bien hoat dong duoi nuoc"},
    "bien": {"beach", "bai bien", "bien hoat dong duoi nuoc"},
    "chua": {"place of worship", "tam linh tin nguong"},
    "den": {"place of worship", "tam linh tin nguong"},
    "tam linh": {"place of worship", "tam linh tin nguong"},
}


def normalize_text(value):
    value = str(value or "").replace("đ", "d").replace("Đ", "D")
    value = unicodedata.normalize("NFKD", value)
    value = "".join(
        char for char in value if not unicodedata.combining(char)
    )
    return " ".join(re.sub(r"[^a-z0-9]+", " ", value.casefold()).split())


def normalize_command_text(value):
    """Normalize common Vietnamese chat abbreviations in user commands."""
    normalized = normalize_text(value)
    return re.sub(r"\b(?:k|ko|kh)\b", "khong", normalized)


def place_types(place):
    return {
        str(value).strip().casefold()
        for value in (
            place.get("type", ""),
            *place.get("types", []),
            *place.get("all_types", []),
        )
        if value
    }


def place_categories(place):
    return {
        str(value).strip().casefold()
        for value in (
            *place.get("activity_categories", []),
            *place.get("semantic_categories", []),
        )
        if value
    }


def matches_category(place, category):
    requested = normalize_text(category)
    targets = CATEGORY_ALIASES.get(requested, {requested})
    values = {
        normalize_text(value)
        for value in (
            place.get("type", ""),
            *place.get("types", []),
            *place.get("all_types", []),
            *place.get("activity_categories", []),
            *place.get("semantic_categories", []),
        )
        if value
    }
    return any(
        target == value or target in value or value in target
        for target in targets
        for value in values
        if target and value
    )
