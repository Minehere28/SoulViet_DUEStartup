TIME_PREFERENCE = {

    "morning": [
        "cafe",
        "coffee_shop",
        "tea_house",
        "bakery",
        "park",
        "beach",
        "garden",
    ],

    "afternoon": [
        "museum",
        "art_gallery",
        "historical_landmark",
        "historical_place",
        "library",
        "bridge",
    ],

    "evening": [
        "restaurant",
        "seafood_restaurant",
        "market",
        "night_market",
        "food_store",
        "cocktail_bar",
        "brewpub",
    ],

    "night": [
        "bar",
        "live_music_venue",
        "night_club",
    ]
}


def get_best_time(place_types):

    for time_slot, allowed_types in TIME_PREFERENCE.items():

        for t in place_types:

            if t in allowed_types:
                return time_slot

    return "afternoon"