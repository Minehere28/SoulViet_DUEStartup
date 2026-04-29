from services.graph_service import GraphService
from services.llm_service import LLMService
from services.filter_service import FilterService
from services.cluster_service import ClusterService
from services.scoring_service import ScoringService
from services.optimizer_service import OptimizerService

from utils.time_estimator import estimate_time


class ItineraryService:

    def __init__(self):

        self.graph = GraphService()

        self.llm = LLMService()

        self.filter = FilterService()

        self.cluster = ClusterService(
            self.graph,
            self.filter
        )

        self.scoring = ScoringService()

        self.optimizer = OptimizerService()

    def build(self, user):

        clusters = self.cluster.generate_candidates(
            user=user,
            limit=10
        )

        if not clusters:
            return {
                "days": [],
                "ai_content": "Không tìm thấy địa điểm phù hợp."
            }

        optimized_days = []

        used_ids = set()

        for day_index in range(user.duration):

            if day_index >= len(clusters):
                break

            cluster = clusters[day_index]
            places = cluster["places"]

            edges = cluster["edges"]        

            candidates = []

            for place in places:

                if place["id"] in used_ids:
                    continue

                place["value"] = self.scoring.calculate(
                    place,
                    user
                )

                place["cost"] = place.get(
                    "price_max",
                    50000
                )

                place["estimated_time"] = (
                    estimate_time(place)
                ) 

                candidates.append(place)

            if not candidates:
                continue

            optimized = self.optimizer.optimize(
                candidates=candidates,
                edges=edges,        
                max_budget=user.budget,
                max_time=480
            )

            selected_places = optimized["places"]

            for p in selected_places:
                used_ids.add(p["id"])

            optimized_days.append({
                "day": day_index + 1,

                "score": round(
                    optimized["score"],
                    2
                ),

                "total_cost": optimized[
                    "total_cost"
                ],

                "total_time": optimized[
                    "total_time"
                ],

                "locations": [

                    {
                        "name": p["name"],

                        "rating": p.get(
                            "rating",
                            0
                        ),

                        "vibes": p.get(
                            "vibes",
                            []
                        ),

                        "types": p.get(
                            "types",
                            []
                        ),

                        "estimated_time":
                            p.get(
                                "estimated_time",
                                60
                            ),

                        "price":
                            p.get(
                                "price_max",
                                0
                            ),

                        "description":
                            p.get(
                                "description",
                                ""
                            )
                    }

                    for p in selected_places
                ]
            })

        ai_content = (
            self.llm.generate_itinerary_text(
                itinerary_data=optimized_days,
                user=user
            )
        )

        return {
            "days": optimized_days,
            "ai_content": ai_content
        }