class FilterService:

    def __init__(self):
        self.vibes = {
            "chill": {
                "label": "Chữa lành & Yên bình",
                "types": [
                    "cafe", "coffee_shop", "tea_house", "yoga_studio",
                    "wellness_center", "health", "garden", "botanical_garden",
                    "park", "beach", "natural_feature", "scenic_spot",
                    "campground", "bed_and_breakfast", "resort_hotel", "lounge_bar",
                ],
            },
            "food": {
                "label": "Ẩm thực & Đặc sản",
                "types": [
                    "food", "restaurant", "seafood_restaurant", "vietnamese_restaurant",
                    "korean_restaurant", "japanese_restaurant", "indian_restaurant",
                    "family_restaurant", "breakfast_restaurant", "pizza_restaurant",
                    "barbecue_restaurant", "bistro", "gastropub", "bakery",
                    "food_store", "farmers_market", "market", "beer_garden",
                    "brewpub", "cocktail_bar", "bar", "cafe", "coffee_shop", "tea_house",
                ],
            },
            "culture": {
                "label": "Đậm văn hóa & Bản địa",
                "types": [
                    "museum", "art_museum", "art_gallery", "art_studio",
                    "art_studiohistorical", "historical_landmark", "historical_place",
                    "library", "educational_institution", "community_center",
                    "association_or_organization", "monument", "bridge",
                    "tour_agency", "travel_agency", "place_of_worship", "church",
                ],
            },
            "adventure": {
                "label": "Năng động & Phiêu lưu",
                "types": [
                    "amusement_park", "amusement_center", "water_park",
                    "sports_complex", "sports_club", "sports_school",
                    "sports_activity_location", "hiking_area", "national_park",
                    "zoo", "farm", "playground", "campground",
                    "fishing_charter", "marina", "ferry_service",
                ],
            },
            "creative": {
                "label": "Sáng tạo & Truyền cảm hứng",
                "types": [
                    "art_gallery", "art_studio", "art_studiohistorical",
                    "coworking_space", "book_store", "live_music_venue",
                    "movie_theater", "night_club", "irish_pub",
                ],
            },
            "spiritual": {
                "label": "Tâm linh & Tín ngưỡng",
                "types": [
                    "place_of_worship", "church", "historical_landmark",
                    "historical_place", "monument",
                ],
            },
        }

        self._label_to_types = {v["label"]: v["types"] for v in self.vibes.values()}

    def _resolve_types(self, user_vibe):
        """Return the types list for an English key or a Vietnamese label."""
        entry = self.vibes.get(user_vibe.lower())
        if entry:
            return entry["types"]
        return self._label_to_types.get(user_vibe, [])

    def match_vibe(self, user_vibe, place_vibes):
        label = self.vibes.get(user_vibe.lower(), {}).get("label")
        return label in place_vibes if label else False

    def match_type(self, user_vibe, place_types):
        allowed = self._resolve_types(user_vibe)
        return any(t and t != "nan" and t in allowed for t in place_types)

    def match(self, user_vibe, place_vibes, place_types):
        """True if vibe label OR establishment type matches the user's vibe."""
        return self.match_vibe(user_vibe, place_vibes) or self.match_type(user_vibe, place_types)