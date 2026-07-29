from utils.distance import haversine


class SimilarityService:
    """Calculate place similarity on demand without materializing graph edges."""

    TYPE_WEIGHT = 0.40
    ACTIVITY_WEIGHT = 0.35
    VIBE_WEIGHT = 0.25

    def __init__(self, graph_service):
        self.graph = graph_service

    @staticmethod
    def _jaccard(first, second):
        first_set = {str(value).strip().lower() for value in first if value}
        second_set = {
            str(value).strip().lower() for value in second if value
        }
        union = first_set | second_set
        if not union:
            return 0.0
        return len(first_set & second_set) / len(union)

    def calculate_score(self, source, candidate):
        type_score = self._jaccard(
            source["types"],
            candidate["types"],
        )
        activity_score = self._jaccard(
            source["activity_categories"],
            candidate["activity_categories"],
        )
        vibe_score = self._jaccard(
            source["vibes"],
            candidate["vibes"],
        )
        total_score = (
            type_score * self.TYPE_WEIGHT
            + activity_score * self.ACTIVITY_WEIGHT
            + vibe_score * self.VIBE_WEIGHT
        )
        return {
            "total": total_score,
            "type": type_score,
            "activity": activity_score,
            "vibe": vibe_score,
        }

    def find_similar(
        self,
        place_id,
        top_k=5,
        same_region=True,
        max_distance_km=None,
        min_score=0.0,
    ):
        if top_k < 1:
            raise ValueError("top_k must be at least 1")
        if max_distance_km is not None and max_distance_km <= 0:
            raise ValueError("max_distance_km must be greater than 0")
        if not 0 <= min_score <= 1:
            raise ValueError("min_score must be between 0 and 1")

        source = self.graph.get_place(place_id)
        if source is None:
            raise ValueError(f"Unknown place id: {place_id}")

        results = []
        for candidate in self.graph.get_all_places():
            if candidate["id"] == source["id"]:
                continue
            if (
                same_region
                and source["region"]
                and candidate["region"] != source["region"]
            ):
                continue

            distance = haversine(
                source["lat"],
                source["lng"],
                candidate["lat"],
                candidate["lng"],
            )
            if (
                max_distance_km is not None
                and distance > max_distance_km
            ):
                continue

            scores = self.calculate_score(source, candidate)
            if scores["total"] < min_score:
                continue

            results.append(
                {
                    "id": candidate["id"],
                    "name": candidate["name"],
                    "region": candidate["region"],
                    "lat": candidate["lat"],
                    "lng": candidate["lng"],
                    "rating": candidate["rating"],
                    "review_count": candidate["review_count"],
                    "distance_km": round(distance, 3),
                    "similarity_score": round(scores["total"], 4),
                    "score_breakdown": {
                        "type": round(scores["type"], 4),
                        "activity": round(scores["activity"], 4),
                        "vibe": round(scores["vibe"], 4),
                    },
                    "shared_types": sorted(
                        set(source["types"]) & set(candidate["types"])
                    ),
                    "shared_activities": sorted(
                        set(source["activity_categories"])
                        & set(candidate["activity_categories"])
                    ),
                    "shared_vibes": sorted(
                        set(source["vibes"]) & set(candidate["vibes"])
                    ),
                }
            )

        results.sort(
            key=lambda item: (
                -item["similarity_score"],
                -item["rating"],
                -item["review_count"],
                item["distance_km"],
            )
        )
        return results[:top_k]
