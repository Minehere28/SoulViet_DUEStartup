import math

class ScoringService:

    def calculate(self, place, user):
        vibe_match = 1 if place.vibe == user.vibe else 0
        rating_score = min(max(place.rating / 5, 0), 1)
        review_score = math.log1p(place.review_count)

        score = (
            rating_score * 0.55
            + review_score * 0.10
            + vibe_match * 0.35
        )

        return score
