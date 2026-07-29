import json


TYPE_DURATION_RULES = (
    (("amusement_park", "water_park", "zoo", "national_park"), 180),
    (("shopping_mall", "campground", "resort_hotel"), 150),
    (("beach", "hiking_area", "sports_complex"), 120),
    (("museum", "art_gallery", "art_museum", "historical"), 120),
    (("restaurant", "bar", "pub", "night_club", "live_music"), 90),
    (("cafe", "coffee_shop", "tea_house", "bakery"), 75),
    (("market", "gift_shop", "store", "shopping"), 75),
    (("place_of_worship", "church", "monument"), 75),
    (("tourist_attraction", "scenic_spot", "park", "garden"), 90),
)


def _normalize_types(primary_type, all_types=None):
    values = []
    for value in (primary_type,):
        if value:
            text = str(value).strip()
            if text.startswith("["):
                try:
                    parsed = json.loads(text)
                    values.extend(str(item) for item in parsed)
                    continue
                except (TypeError, ValueError, json.JSONDecodeError):
                    pass
            values.append(text)
    if isinstance(all_types, str):
        try:
            all_types = json.loads(all_types)
        except (TypeError, ValueError, json.JSONDecodeError):
            all_types = []
    if isinstance(all_types, list):
        values.extend(str(item) for item in all_types)
    return [value.casefold() for value in values]


def estimate_visit_duration(primary_type, all_types=None):
    normalized_types = _normalize_types(primary_type, all_types)
    for keywords, minutes in TYPE_DURATION_RULES:
        if any(
            keyword in place_type
            for place_type in normalized_types
            for keyword in keywords
        ):
            return {
                "minutes": minutes,
                "source": "type_estimate",
                "confidence": "medium",
            }
    return {
        "minutes": 90,
        "source": "default_estimate",
        "confidence": "low",
    }
