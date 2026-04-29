import random
from services.filter_service import FilterService
from utils.time_estimator import estimate_time
from utils.time_preference import get_best_time

class PlannerService:

    def __init__(self, graph_service):
        self.graph = graph_service

        self.filter = FilterService()

    def build_day_plan(
        self,
        seed_place,
        user,
        used_ids
    ):

        queue = [
            (
                seed_place["id"],
                0,
                0
            )
        ]

        visited = {
            seed_place["id"]
        }

        candidate_places = []

        while queue:

            current_id, depth, total_distance = queue.pop(0)

            

            if depth >= 2:
                continue

            neighbors = self.graph.get_neighbors(
                current_id
            )

            for edge in neighbors:

                next_id = edge["to"]

                if next_id in visited:
                    continue

                visited.add(next_id)

                place = self.graph.get_place(
                    next_id
                )

                place["value"] = self.graph.score_place(
                    place,
                    user
                )

                place["estimated_time"] = estimate_time(place)

                place["best_time"] = get_best_time(
                    place.get("types", [])
                )

                if not place:
                    continue

                if place["id"] in used_ids:
                    continue

                if place["rating"] < 4:
                    continue

                if not self.filter.match(
                    user.vibe,
                    place.get("vibes", []),
                    place.get("types", [])
                ):
                    continue

                distance = edge.get(
                    "distance",
                    999
                )

                new_total_distance = (
                    total_distance + distance
                )

                if new_total_distance > 20:
                    continue

                candidate_places.append({
                    "place": place,
                    "distance": distance
                })

                queue.append(
                    (
                        next_id,
                        depth + 1,
                        new_total_distance
                    )
                )

        candidate_places.sort(
            key=lambda x: (
                x["distance"],
                -x["place"]["rating"]
            )
        )

        selected = [seed_place]

        categories = {
            self.detect_category(seed_place)
        }
        for item in candidate_places:

            place = item["place"]

            category = self.detect_category(place)

            if category in categories:
                continue

            categories.add(category)

            if place["id"] in [
                p["id"]
                for p in selected
            ]:
                continue

            selected.append(place)

            if len(selected) >= 5:
                break

        return {
            "morning": selected[:2],
            "afternoon": selected[2:4],
            "evening": selected[4:]
        }

    def detect_category(self, place):

        types = place.get("types", [])

        if any(t in types for t in [
            "cafe",
            "coffee_shop",
            "tea_house"
        ]):
            return "cafe"

        if any(t in types for t in [
            "restaurant",
            "food",
            "seafood_restaurant"
        ]):
            return "food"

        if any(t in types for t in [
            "museum",
            "historical_landmark",
            "art_gallery"
        ]):
            return "culture"

        if any(t in types for t in [
            "beach",
            "park",
            "garden"
        ]):
            return "nature"

        return "general"