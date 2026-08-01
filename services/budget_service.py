class BudgetService:
    """Conservative, type-based spend estimates until partner prices exist."""

    LEVELS = {
        "economy": {"label": "Tiết kiệm", "daily_limit": 350_000, "factors": (0.75, 0.9)},
        "standard": {"label": "Tiêu chuẩn", "daily_limit": 700_000, "factors": (1.0, 1.0)},
        "premium": {"label": "Cao cấp", "daily_limit": 1_400_000, "factors": (1.25, 1.6)},
    }
    TYPE_RANGES = {
        "cafe": (35_000, 85_000), "coffee_shop": (35_000, 85_000),
        "restaurant": (80_000, 250_000), "vietnamese_restaurant": (70_000, 220_000),
        "seafood_restaurant": (150_000, 400_000), "bar": (100_000, 300_000),
        "cocktail_bar": (120_000, 320_000), "spa": (250_000, 700_000),
        "museum": (20_000, 100_000), "tourist_attraction": (0, 150_000),
        "amusement_park": (100_000, 350_000), "movie_theater": (90_000, 180_000),
        "shopping_mall": (0, 200_000), "market": (0, 150_000),
        "park": (0, 50_000), "beach": (0, 80_000),
        "temple": (0, 50_000), "pagoda": (0, 50_000),
    }
    DEFAULT_RANGE = (30_000, 150_000)

    @classmethod
    def estimate_place(cls, place, level):
        place_types = [place.get("type", ""), *place.get("all_types", []), *place.get("types", [])]
        ranges = [cls.TYPE_RANGES[item] for item in place_types if item in cls.TYPE_RANGES]
        stored_min = place.get("entrance_fee_min", 0) + place.get("typical_spend_min", 0)
        stored_max = place.get("entrance_fee_max", 0) + place.get("typical_spend_max", 0)
        if stored_min or stored_max:
            base_min, base_max = stored_min, stored_max
        else:
            base_min, base_max = ranges[0] if ranges else cls.DEFAULT_RANGE
        min_factor, max_factor = cls.LEVELS[level]["factors"]
        spend_min = round(base_min * min_factor / 1000) * 1000
        spend_max = round(base_max * max_factor / 1000) * 1000
        return {
            "spend_min": spend_min,
            "spend_max": spend_max,
            "expected_spend": round((spend_min + spend_max) / 2 / 1000) * 1000,
            "price_unit": place.get("price_unit", "person"),
            "price_source": place.get("price_source", "type_estimate"),
            "price_confidence": place.get("price_confidence", "low"),
            "price_verification_status": place.get(
                "price_verification_status", "estimated"
            ),
        }

    @classmethod
    def trip_limit(cls, level, duration):
        return cls.LEVELS[level]["daily_limit"] * duration
