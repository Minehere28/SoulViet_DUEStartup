class GapFillerService:
    """Fill large timeline gaps without relaxing any hard constraint."""

    def __init__(self, minimum_gap_minutes=90, candidate_limit=30):
        self.minimum_gap_minutes = minimum_gap_minutes
        self.candidate_limit = candidate_limit

    @staticmethod
    def _attraction_count(route):
        return sum(place.get("item_type") != "meal" for place in route)

    def fill(
        self,
        route,
        candidates,
        simulate,
        max_places,
        reserved_place_ids=None,
        protected_place_ids=None,
    ):
        reserved_place_ids = set(reserved_place_ids or [])
        protected_place_ids = set(protected_place_ids or [])
        current_route = list(route)
        current = simulate(current_route)
        added_ids = []
        removed_places = []
        if current is None:
            return current_route, None, added_ids, removed_places

        available = [
            place for place in candidates
            if place["id"] not in reserved_place_ids
            and place.get("item_type") != "meal"
        ][: self.candidate_limit]
        while (
            available
            and self._attraction_count(current_route) < max_places
            and current["max_idle_gap_minutes"] >= self.minimum_gap_minutes
        ):
            best = None
            for candidate in available:
                for position in range(len(current_route) + 1):
                    trial_route = [
                        *current_route[:position],
                        candidate,
                        *current_route[position:],
                    ]
                    trial = simulate(trial_route)
                    if trial is None:
                        continue
                    reduction = (
                        current["max_idle_gap_minutes"]
                        - trial["max_idle_gap_minutes"]
                    )
                    if reduction <= 0:
                        continue
                    rank = (
                        trial["max_idle_gap_minutes"],
                        trial["total_idle_minutes"],
                        trial["total_distance_km"],
                        -candidate.get("query_priority", 0),
                        -candidate.get("recommendation_score", 0),
                    )
                    if best is None or rank < best[0]:
                        best = (rank, trial_route, trial, candidate)
            if best is None:
                break
            _, current_route, current, selected = best
            added_ids.append(selected["id"])
            available = [
                place for place in available
                if place["id"] != selected["id"]
            ]

        if current["max_idle_gap_minutes"] >= self.minimum_gap_minutes:
            best_swap = None
            for candidate in available:
                for remove_index, removed in enumerate(current_route):
                    if (
                        removed.get("item_type") == "meal"
                        or removed["id"] in protected_place_ids
                    ):
                        continue
                    shortened = [
                        *current_route[:remove_index],
                        *current_route[remove_index + 1:],
                    ]
                    for position in range(len(shortened) + 1):
                        trial_route = [
                            *shortened[:position],
                            candidate,
                            *shortened[position:],
                        ]
                        trial = simulate(trial_route)
                        if trial is None or (
                            trial["max_idle_gap_minutes"]
                            >= current["max_idle_gap_minutes"]
                        ):
                            continue
                        preference_loss = max(
                            0,
                            removed.get("query_priority", 0)
                            - candidate.get("query_priority", 0),
                        )
                        rank = (
                            trial["max_idle_gap_minutes"],
                            trial["total_idle_minutes"],
                            preference_loss,
                            trial["total_distance_km"],
                            -candidate.get("recommendation_score", 0),
                        )
                        if best_swap is None or rank < best_swap[0]:
                            best_swap = (
                                rank,
                                trial_route,
                                trial,
                                candidate,
                                removed,
                            )
            if best_swap is not None:
                _, current_route, current, selected, removed = best_swap
                added_ids.append(selected["id"])
                removed_places.append(removed)

        if (
            current["max_idle_gap_minutes"] >= self.minimum_gap_minutes
            and not removed_places
            and self._attraction_count(current_route) < max_places
        ):
            beam = []
            beam_candidates = available[:15]
            for remove_index, removed in enumerate(current_route):
                if (
                    removed.get("item_type") == "meal"
                    or removed["id"] in protected_place_ids
                ):
                    continue
                shortened = [
                    *current_route[:remove_index],
                    *current_route[remove_index + 1:],
                ]
                for first in beam_candidates:
                    for position in range(len(shortened) + 1):
                        intermediate_route = [
                            *shortened[:position],
                            first,
                            *shortened[position:],
                        ]
                        intermediate = simulate(intermediate_route)
                        if intermediate is None:
                            continue
                        beam.append((
                            (
                                intermediate["max_idle_gap_minutes"],
                                intermediate["total_idle_minutes"],
                                intermediate["total_distance_km"],
                            ),
                            intermediate_route,
                            first,
                            removed,
                        ))
            beam.sort(key=lambda item: item[0])
            best_pair = None
            for _, intermediate_route, first, removed in beam[:20]:
                for second in beam_candidates:
                    if second["id"] == first["id"]:
                        continue
                    for position in range(len(intermediate_route) + 1):
                        trial_route = [
                            *intermediate_route[:position],
                            second,
                            *intermediate_route[position:],
                        ]
                        trial = simulate(trial_route)
                        if trial is None or (
                            trial["max_idle_gap_minutes"]
                            >= current["max_idle_gap_minutes"]
                        ):
                            continue
                        preference_loss = max(
                            0,
                            removed.get("query_priority", 0)
                            - first.get("query_priority", 0)
                            - second.get("query_priority", 0),
                        )
                        rank = (
                            trial["max_idle_gap_minutes"],
                            trial["total_idle_minutes"],
                            preference_loss,
                            trial["total_distance_km"],
                        )
                        if best_pair is None or rank < best_pair[0]:
                            best_pair = (
                                rank,
                                trial_route,
                                trial,
                                first,
                                second,
                                removed,
                            )
            if best_pair is not None:
                (
                    _, current_route, current, first, second, removed
                ) = best_pair
                added_ids.extend([first["id"], second["id"]])
                removed_places.append(removed)

        return current_route, current, added_ids, removed_places
