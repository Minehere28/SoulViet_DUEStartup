from services.similarity_service import SimilarityService
from utils.place_matching import matches_category, normalize_text, place_categories, place_types


class GraphQueryService:
    """Turn a validated query plan into a small, explainable place pool."""

    def __init__(self, graph, similarity=None):
        self.graph = graph
        self.similarity = similarity or SimilarityService(graph)

    @staticmethod
    def _normalize_text(value):
        return normalize_text(value)

    @classmethod
    def _matches_category(cls, place, category):
        return matches_category(place, category)

    def _resolve_names(self, names, user):
        if not names:
            return [], []
        regional = [
            place for place in self.graph.get_all_places()
            if place.get("region") == user.region
        ]
        resolved = []
        unresolved = []
        for requested_name in names:
            normalized = self._normalize_text(requested_name)
            exact = [
                place for place in regional
                if self._normalize_text(place.get("name")) == normalized
            ]
            matches = exact or [
                place for place in regional
                if normalized
                and normalized in self._normalize_text(place.get("name"))
            ]
            if not matches:
                unresolved.append(requested_name)
                continue
            matches.sort(key=lambda place: (
                -place.get("rating", 0), -place.get("review_count", 0)
            ))
            if matches[0]["id"] not in resolved:
                resolved.append(matches[0]["id"])
        return resolved, unresolved

    def resolve_constraints(self, user, query):
        required_ids, unresolved_required = self._resolve_names(
            query.required_place_names, user
        )
        excluded_ids, unresolved_excluded = self._resolve_names(
            query.excluded_place_names, user
        )
        return {
            "required_place_ids": required_ids,
            "excluded_place_ids": excluded_ids,
            "unresolved_required_place_names": unresolved_required,
            "unresolved_excluded_place_names": unresolved_excluded,
        }

    def semantic_candidates(self, user, query, limit=30):
        candidates = [
            place for place in self.graph.filter_places(user)
            if not place.get("roles") or "attraction" in place["roles"]
        ]
        candidates.sort(key=lambda place: (
            -self._query_score(place, query),
            -self.graph.score_place(place, user)["total"],
            -place.get("rating", 0),
            -place.get("review_count", 0),
        ))
        return [
            {
                "id": place["id"],
                "name": place.get("name", ""),
                "type": place.get("type", ""),
                "types": place.get("all_types", place.get("types", [])),
                "activities": place.get("activities", []),
                "activity_categories": place.get(
                    "activity_categories", []
                ),
                "vibes": place.get("vibes", []),
                "description": place.get("description", "")[:240],
            }
            for place in candidates[:limit]
        ]

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
        searchable = normalize_text(" ".join(
            str(value) for value in cls._values(place) if value
        ))
        keyword_hits = sum(
            normalize_text(keyword) in searchable
            for keyword in query.keywords
            if normalize_text(keyword)
        )
        requested_types = {
            normalize_text(value) for value in query.types if value.strip()
        }
        place_types = {
            normalize_text(value)
            for value in [place.get("type", ""), *place.get("types", [])]
            if value
        }
        activity_hits = sum(
            cls._matches_category(place, value)
            for value in query.activity_categories
            if value.strip()
        )
        requested_vibes = {
            normalize_text(value) for value in query.vibes if value.strip()
        }
        place_vibes = {
            normalize_text(value)
            for value in place.get("vibes", [])
            if value
        }
        return (
            keyword_hits * 3
            + len(requested_types & place_types) * 2
            + activity_hits * 2
            + len(requested_vibes & place_vibes) * 2
        )

    @classmethod
    def _matches_focus(cls, place, query):
        """Apply focused semantics without treating a loose text hit as a type hit."""
        requested_types = {
            normalize_text(value) for value in query.types if value.strip()
        }
        current_types = {
            normalize_text(value)
            for value in [
                place.get("type", ""),
                *place.get("types", []),
                *place.get("all_types", []),
            ]
            if value
        }
        structured_match = bool(requested_types & current_types)
        structured_match = structured_match or any(
            cls._matches_category(place, value)
            for value in query.activity_categories
            if value.strip()
        )
        requested_vibes = {
            normalize_text(value) for value in query.vibes if value.strip()
        }
        current_vibes = {
            normalize_text(value)
            for value in place.get("vibes", [])
            if value
        }
        structured_match = structured_match or bool(
            requested_vibes & current_vibes
        )
        has_structured_query = bool(
            requested_types or query.activity_categories or requested_vibes
        )
        return (
            structured_match
            if has_structured_query
            else cls._query_score(place, query) > 0
        )

    def search(self, user, query):
        required_name_ids, unresolved_required = self._resolve_names(
            query.required_place_names, user
        )
        excluded_name_ids, unresolved_excluded = self._resolve_names(
            query.excluded_place_names, user
        )
        all_required_ids = set([
            *getattr(user, "required_place_ids", []),
            *query.seed_place_ids,
            *required_name_ids,
        ])
        query_excluded_types = {
            value.strip().casefold() for value in query.excluded_types if value.strip()
        }
        query_excluded_categories = {
            value.strip().casefold()
            for value in query.excluded_activity_categories
            if value.strip()
        }
        allowed = {
            place["id"]: place
            for place in self.graph.filter_places(user)
            if (place["rating"] >= query.minimum_rating or place["id"] in all_required_ids)
            and place["id"] not in excluded_name_ids
            and not query_excluded_types.intersection(place_types(place))
            and not query_excluded_categories.intersection(
                place_categories(place)
            )
            and (
                not place.get("roles")
                or "attraction" in place["roles"]
            )
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

        hard_maxima = {
            rule.category: rule.max_count
            for rule in query.category_constraints
            if rule.mode == "hard" and rule.max_count is not None
        }
        preference_targets = {
            rule.category: (rule.target_count or rule.min_count)
            for rule in query.category_constraints
            if (rule.target_count or rule.min_count) > 0
        }

        def exceeds_category_max(place):
            for category, maximum in hard_maxima.items():
                if not self._matches_category(place, category):
                    continue
                current = sum(
                    self._matches_category(allowed[item], category)
                    for item in selected
                )
                if current >= maximum:
                    return True
            return False

        def exceeds_preference_target(place):
            for category, target in preference_targets.items():
                if not self._matches_category(place, category):
                    continue
                current = sum(
                    self._matches_category(allowed[item], category)
                    for item in selected
                )
                if current >= target:
                    return True
            return False

        def add(
            place_id,
            source,
            source_priority=0,
            enforce_maximum=True,
            enforce_preference_target=False,
        ):
            if place_id not in allowed or place_id in provenance:
                return
            if enforce_maximum and exceeds_category_max(allowed[place_id]):
                return
            if (
                enforce_preference_target
                and exceeds_preference_target(allowed[place_id])
            ):
                return
            selected.append(place_id)
            provenance[place_id] = source
            priorities[place_id] = (
                self._query_score(allowed[place_id], query)
                + source_priority
            )

        required_ids = list(dict.fromkeys([
            *getattr(user, "required_place_ids", []),
            *required_name_ids,
        ]))
        for place_id in required_ids:
            add(place_id, "required", 1000, enforce_maximum=False)
        for place_id in query.seed_place_ids:
            add(place_id, "explicit_seed", 100, enforce_maximum=False)

        for rule in query.category_constraints:
            desired = rule.target_count if rule.mode == "soft" else rule.min_count
            if desired is None or desired <= 0:
                continue
            current = sum(
                self._matches_category(allowed[item], rule.category)
                for item in selected
            )
            for place in ranked:
                if current >= desired:
                    break
                if self._matches_category(place, rule.category):
                    before = len(selected)
                    add(place["id"], f"quota:{rule.category}", 200)
                    current += int(len(selected) > before)

        seed_target = min(5, query.candidate_limit)
        has_semantic_filters = bool(
            query.keywords
            or query.types
            or query.activity_categories
            or query.vibes
        )
        matching = [
            place for place in ranked
            if (
                self._matches_focus(place, query)
                if query.match_mode == "focused"
                else self._query_score(place, query) > 0
            )
        ]
        if has_semantic_filters and query.match_mode == "focused":
            seed_pool = matching
        else:
            seed_pool = matching if has_semantic_filters and matching else ranked
        for place in seed_pool:
            if len(selected) >= seed_target:
                break
            query_score = self._query_score(place, query)
            add(
                place["id"],
                "ranked_seed" if query_score else "diverse_seed",
                50 if query_score else 0,
                enforce_preference_target=True,
            )

        seeds = list(selected)
        similarity_seeds = [
            place_id for place_id in seeds
            if provenance.get(place_id) != "diverse_seed"
        ]
        if query.include_similar and len(selected) < query.candidate_limit:
            for seed_id in similarity_seeds:
                for item in self.similarity.find_similar(
                    seed_id,
                    top_k=5,
                    same_region=True,
                    min_score=0.1,
                ):
                    if (
                        query.match_mode == "focused"
                        and not self._matches_focus(
                            allowed.get(item["id"], {}), query
                        )
                    ):
                        continue
                    add(
                        item["id"],
                        f"similar:{seed_id}",
                        20 + round(item["similarity_score"] * 10),
                        enforce_preference_target=True,
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
                    if (
                        query.match_mode == "focused"
                        and not self._matches_focus(
                            allowed.get(edge["to"], {}), query
                        )
                    ):
                        continue
                    add(
                        edge["to"],
                        f"near:{seed_id}",
                        5,
                        enforce_preference_target=True,
                    )
                    if len(selected) >= query.candidate_limit:
                        break
                if len(selected) >= query.candidate_limit:
                    break

        # Complete the semantic pool before considering generic high-quality
        # places. This makes LLM-authored themes effective without parsing the
        # user's sentence with application-side keyword rules.
        for place in matching:
            if len(selected) >= query.candidate_limit:
                break
            add(
                place["id"],
                "semantic_fill",
                40,
                enforce_preference_target=True,
            )

        if query.match_mode == "balanced":
            for place in ranked:
                if len(selected) >= query.candidate_limit:
                    break
                add(
                    place["id"],
                    "ranked_fill",
                    enforce_preference_target=True,
                )

            for place in ranked:
                if len(selected) >= query.candidate_limit:
                    break
                add(place["id"], "overflow_fill")

        return {
            "candidate_ids": selected,
            "provenance": provenance,
            "priorities": priorities,
            "candidate_count": len(selected),
            "semantic_match_count": len(matching),
            "seed_ids": seeds,
            "required_place_ids": required_ids,
            "resolved_required_place_ids": required_name_ids,
            "unresolved_required_place_names": unresolved_required,
            "resolved_excluded_place_ids": excluded_name_ids,
            "unresolved_excluded_place_names": unresolved_excluded,
            "near_hops": query.near_hops if query.expand_near else 0,
        }
