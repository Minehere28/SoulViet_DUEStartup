import math

from utils.place_matching import place_categories


class ScoringService:
    """Explainable recommendation score for the canonical graph schema."""

    WEIGHTS = {
        "rating": 0.30,
        "popularity": 0.15,
        "vibe": 0.30,
        "activity": 0.15,
        "schedule_quality": 0.10,
    }

    def __init__(self, max_review_count=0):
        self.max_log_reviews = math.log1p(max_review_count)

    @staticmethod
    def _activity_score(place, user):
        preferences = {
            value.strip().casefold()
            for value in user.preferred_activities
            if value.strip()
        }
        if not preferences:
            return 1.0

        categories = place_categories(place)
        if not categories:
            return 0.0
        return len(preferences & categories) / len(preferences)

    @staticmethod
    def _schedule_quality(place):
        if place.get("opening_hours_needs_review"):
            return 0.2
        if place.get("opening_hours_status") == "unknown":
            return 0.4
        return 1.0

    def calculate(self, place, user):
        components = {
            "rating": min(max(place["rating"] / 5, 0), 1),
            "popularity": (
                math.log1p(place["review_count"]) / self.max_log_reviews
                if self.max_log_reviews
                else 0.0
            ),
            "vibe": 1.0 if user.vibe in place["vibes"] else 0.0,
            "activity": self._activity_score(place, user),
            "schedule_quality": self._schedule_quality(place),
        }
        weighted = {
            name: components[name] * weight
            for name, weight in self.WEIGHTS.items()
        }
        return {
            "total": round(sum(weighted.values()), 6),
            "components": {
                name: round(value, 6)
                for name, value in components.items()
            },
            "weights": dict(self.WEIGHTS),
        }
