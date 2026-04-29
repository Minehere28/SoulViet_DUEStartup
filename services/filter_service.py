class FilterService:

    def __init__(self):
        self.blacklist_types = [
            "school",
            "university",
            "accounting",
            "bank",
            "atm",
            "hospital",
            "doctor",
            "pharmacy",
            "government_office",
            "corporate_office",
            "real_estate_agency",
            "insurance_agency",
            "lawyer",
            "post_office",
            "storage",
        ]
        self.vibes = {

            "chill": {
                "label": "Chữa lành & Yên bình",

                "types": [

                    # cafe / healing
                    "cafe",
                    "coffee_shop",
                    "tea_house",
                    "bakery",

                    # thiên nhiên
                    "park",
                    "garden",
                    "botanical_garden",
                    "beach",
                    "natural_feature",
                    "scenic_spot",

                    # nghỉ dưỡng
                    "spa",
                    "wellness_center",
                    "resort_hotel",
                    "bed_and_breakfast",

                    # outdoor nhẹ
                    "campground",
                ],
            },

            "food": {
                "label": "Ẩm thực & Đặc sản",

                "types": [

                    # restaurant
                    "restaurant",
                    "vietnamese_restaurant",
                    "seafood_restaurant",
                    "family_restaurant",
                    "breakfast_restaurant",
                    "barbecue_restaurant",
                    "pizza_restaurant",
                    "japanese_restaurant",
                    "korean_restaurant",
                    "indian_restaurant",

                    # local food
                    "food",
                    "food_store",
                    "market",
                    "farmers_market",
                    "bakery",
                    "bistro",
                    "gastropub",

                    # drink
                    "cafe",
                    "coffee_shop",
                    "tea_house",
                    "cocktail_bar",
                    "brewpub",
                ],
            },

            "culture": {
                "label": "Đậm văn hóa & Bản địa",

                "types": [

                    # lịch sử
                    "historical_landmark",
                    "historical_place",
                    "monument",

                    # nghệ thuật
                    "museum",
                    "art_museum",
                    "art_gallery",

                    # local culture
                    "community_center",
                    "library",
                    "book_store",

                    # tín ngưỡng
                    "place_of_worship",
                    "church",

                    # kiến trúc
                    "bridge",
                ],
            },

            "adventure": {
                "label": "Năng động & Phiêu lưu",

                "types": [

                    # vui chơi
                    "amusement_park",
                    "water_park",
                    "amusement_center",

                    # thể thao
                    "sports_complex",
                    "sports_club",
                    "sports_activity_location",

                    # outdoor
                    "hiking_area",
                    "campground",
                    "national_park",
                    "beach",

                    # biển
                    "marina",
                    "ferry_service",
                    "fishing_charter",

                    # trải nghiệm
                    "zoo",
                    "farm",
                ],
            },

            "creative": {
                "label": "Sáng tạo & Truyền cảm hứng",

                "types": [

                    # art
                    "art_gallery",
                    "art_studio",
                    "museum",

                    # chill creative
                    "book_store",
                    "library",
                    "coffee_shop",
                    "cafe",

                    # entertainment
                    "live_music_venue",
                    "movie_theater",

                    # modern vibe
                    "coworking_space",
                ],
            },

            "spiritual": {
                "label": "Tâm linh & Tín ngưỡng",

                "types": [

                    "place_of_worship",
                    "church",
                    "historical_landmark",
                    "historical_place",
                    "monument",
                ],
            },
        }
        self._label_to_types = {v["label"]: v["types"] for v in self.vibes.values()}

    def _resolve_types(self, user_vibe): 
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

    def match(
        self,
        user_vibe,
        place_vibes,
        place_types
    ):

        if self.is_blacklisted(place_types):
            return False

        return (
            self.match_vibe(
                user_vibe,
                place_vibes
            )
            or
            self.match_type(
                user_vibe,
                place_types
            )
        )
    def is_blacklisted(self, place_types):

        return any(
            t in self.blacklist_types
            for t in place_types
        )