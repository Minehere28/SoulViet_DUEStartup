import math

class ScoringService:

    def calculate(self, place, user):
        vibe_match = 1 if place.vibe == user.vibe else 0
        review_score = math.log(place.review_count + 1)
        price_match = 1 if place.price_max <= user.budget else 0.5

        score = (
            place.rating * 0.25 +
            review_score * 0.15 +
            vibe_match * 0.35 +
            price_match * 0.25
        )

        return score