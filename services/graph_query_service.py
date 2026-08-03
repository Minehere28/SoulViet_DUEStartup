from services.similarity_service import SimilarityService


class GraphQueryService:
    """Turn a validated query plan into a small, explainable place pool."""

    def __init__(self, graph, similarity=None):
        self.graph = graph
        self.similarity = similarity or SimilarityService(graph)

    @staticmethod
    def _values(place):
        return [
            place.get("name", ""),
            place.get("description", ""),
            *place.get("types", []),
            *place.get("all_types", []),
            *place.get("activities", []),
            *place.get("activity_categories", []),
            *place.get("vibes", []),
        ]

    @classmethod
    def _query_score(cls, place, query):
        searchable = " ".join(
            str(value).casefold() for value in cls._values(place) if value
        )
        keyword_hits = sum(
            keyword.strip().casefold() in searchable
            for keyword in query.keywords
            if keyword.strip()
        )
        requested_types = {
            value.strip().casefold() for value in query.types if value.strip()
        }
        place_types = {
            str(value).strip().casefold()
            for value in [place.get("type", ""), *place.get("types", [])]
            if value
        }
        requested_activities = {
            value.strip().casefold()
            for value in query.activity_categories
            if value.strip()
        }
        place_activities = {
            str(value).strip().casefold()
            for value in place.get("activity_categories", [])
            if value
        }
        requested_vibes = {
            value.strip().casefold() for value in query.vibes if value.strip()
        }
        place_vibes = {
            str(value).strip().casefold()
            for value in place.get("vibes", [])
            if value
        }
        return (
            keyword_hits * 3
            + len(requested_types & place_types) * 2
            + len(requested_activities & place_activities) * 2
            + len(requested_vibes & place_vibes) * 2
        )

    def search(self, user, query):
        allowed = {
            place["id"]: place
            for place in self.graph.filter_places(user)
            if place["rating"] >= query.minimum_rating
        }
        ranked = sorted(
            allowed.values(),
            key=lambda place: (
                -self._query_score(place, query),
                -self.graph.score_place(place, user)["total"],
                -place["rating"],
                -place["review_count"],
            ),
        )

        selected = []
        provenance = {}
        priorities = {}

        def add(place_id, source, source_priority=0):
            if place_id not in allowed or place_id in provenance:
                return
            selected.append(place_id)
            provenance[place_id] = source
            priorities[place_id] = (
                self._query_score(allowed[place_id], query)
                + source_priority
            )

        for place_id in query.seed_place_ids:
            add(place_id, "explicit_seed", 100)

        seed_target = min(5, query.candidate_limit)
        has_semantic_filters = bool(
            query.keywords
            or query.types
            or query.activity_categories
            or query.vibes
        )
        matching = [
            place for place in ranked
            if self._query_score(place, query) > 0
        ]
        seed_pool = matching if has_semantic_filters and matching else ranked
        for place in seed_pool:
            if len(selected) >= seed_target:
                break
            add(place["id"], "ranked_seed", 50)

        seeds = list(selected)
        if query.include_similar and len(selected) < query.candidate_limit:
            for seed_id in seeds:
                for item in self.similarity.find_similar(
                    seed_id,
                    top_k=5,
                    same_region=True,
                    min_score=0.1,
                ):
                    add(
                        item["id"],
                        f"similar:{seed_id}",
                        20 + round(item["similarity_score"] * 10),
                    )
                    if len(selected) >= query.candidate_limit:
                        break
                if len(selected) >= query.candidate_limit:
                    break

        if query.expand_near and query.near_hops:
            for seed_id in seeds:
                neighbors = sorted(
                    self.graph.get_neighbors(seed_id),
                    key=lambda edge: edge.get("distance", 0),
                )
                for edge in neighbors:
                    add(edge["to"], f"near:{seed_id}", 5)
                    if len(selected) >= query.candidate_limit:
                        break
                if len(selected) >= query.candidate_limit:
                    break

        for place in ranked:
            if len(selected) >= query.candidate_limit:
                break
            add(place["id"], "ranked_fill")

        return {
            "candidate_ids": selected,
            "provenance": provenance,
            "priorities": priorities,
            "candidate_count": len(selected),
            "seed_ids": seeds,
            "near_hops": query.near_hops if query.expand_near else 0,
        }
