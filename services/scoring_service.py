import math


class ScoringService:

    def calculate(self, place, user):

        rating_score = self.rating_score(place)

        review_score = self.review_score(place)

        vibe_score = self.vibe_score(place, user)

        price_score = self.price_score(place, user)

        total_score = (
            rating_score * 0.2 +
            review_score * 0.1 +
            vibe_score * 0.3 +
            price_score * 0.4
        )

        return round(total_score, 2)

    def rating_score(self, place):

        rating = place.get("rating", 0)

        return rating / 5

    def review_score(self, place):

        review_count = place.get(
            "review_count",
            0
        )

        return math.log(review_count + 1) / 10

    def vibe_score(self, place, user):

        place_vibes = place.get("vibes", [])

        if user.vibe in place_vibes:
            return 1

        return 0

    def price_score(self, place, user):

        price_max = place.get("price_max")

        if not price_max:
            return 0.5

        ratio = price_max / user.budget

        if ratio > 1:
            return -1

        return 1 - ratio