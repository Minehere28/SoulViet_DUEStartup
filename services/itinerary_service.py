from services.graph_service import GraphService
from services.llm_service import LLMService
from services.filter_service import FilterService
from services.cluster_service import ClusterService
from services.scoring_service import ScoringService 
from services.planner_service import PlannerService

from utils.time_preference import get_best_time

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

        self.planner = PlannerService(
            self.graph
        )
        self.scoring = ScoringService()

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
     

            candidates = []

            for place in places:

                if place["id"] in used_ids:
                    continue

                if not self.filter.match(
                    user.vibe,
                    place.get("vibes", []),
                    place.get("types", [])
                ):
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
                
                place["best_time"] = get_best_time(
                    place.get("types", [])
                )

                candidates.append(place)

            if not candidates:
                continue

            seed_place = max(
                candidates,
                key=lambda p: p["value"]
            )

            seed_place["estimated_time"] = estimate_time(
                seed_place
            )

            seed_place["best_time"] = get_best_time(
                seed_place.get("types", [])
            )

            plan = self.planner.build_day_plan(
                seed_place=seed_place,
                user=user,
                used_ids=used_ids
            )

            selected_places = (
                plan["morning"]
                + plan["afternoon"]
                + plan["evening"]
            )

            selected_places = self.remove_duplicate_types(
                selected_places
            )

            selected_places = self.graph.optimize_route(
                selected_places
            )

            selected_places = self.sort_by_time_semantic(
                selected_places
            )
            
            plan = {
                "morning": [],
                "afternoon": [],
                "evening": []
            }

            for p in selected_places:

                best_time = p.get(
                    "best_time",
                    "afternoon"
                )

                if best_time == "morning":

                    plan["morning"].append(p)

                elif best_time in [
                    "evening",
                    "night"
                ]:

                    plan["evening"].append(p)

                else:

                    plan["afternoon"].append(p)
            
            if not plan["evening"] and plan["afternoon"]:

                plan["evening"].append(
                    plan["afternoon"].pop()
                )

            for p in selected_places:
                used_ids.add(p["id"])
            
            total_cost = sum(
                p.get("price_max", 0)
                for p in selected_places
            )

            if total_cost > user.budget:
               continue

            total_time = sum(
                p.get("estimated_time", 60)
                for p in selected_places
            )

            if total_time > 600:
              continue
                    
            
            route_flow = []

            for i in range(len(selected_places) - 1):

                current = selected_places[i]

                nxt = selected_places[i + 1]

                route_flow.append({
                    "from": current["name"],
                    "to": nxt["name"]
                })

            if not plan["morning"] and selected_places:
                plan["morning"].append(
                    selected_places[0]
                )

            if (
                not plan["afternoon"]
                and len(selected_places) >= 2
            ):
                plan["afternoon"].append(
                    selected_places[1]
                )

            if (
                not plan["evening"]
                and len(selected_places) >= 3
            ):
                plan["evening"].append(
                    selected_places[2]
                )


            optimized_days.append({
                "score": round(
                    sum(p["value"] for p in selected_places)
                    / len(selected_places),
                    2
                ),

                "day": day_index + 1,

                "total_cost": total_cost,

                "total_time": total_time,

                "morning": plan["morning"],

                "afternoon": plan["afternoon"],

                "evening": plan["evening"],

                "route_flow": route_flow,
            })

        formatted_days = []

        for day in optimized_days:

            formatted_days.append({
                "day": day["day"],
                "score": day["score"],
                "total_cost": day["total_cost"],
                "total_time": day["total_time"],

                "morning": [
                    {
                        "name": p["name"],
                        "type": p.get("type", p.get("Type", "Unknown")),
                        "latitude": p.get("lat", p.get("Lat", 0.0)),
                        "longitude": p.get("lng", p.get("Lng", 0.0))
                    }
                    for p in day["morning"]
                ],

                "afternoon": [
                    {
                        "name": p["name"],
                        "type": p.get("type", p.get("Type", "Unknown")),
                        "latitude": p.get("lat", p.get("Lat", 0.0)),
                        "longitude": p.get("lng", p.get("Lng", 0.0))
                    }
                    for p in day["afternoon"]
                ],

                "evening": [
                    {
                        "name": p["name"],
                        "type": p.get("type", p.get("Type", "Unknown")),
                        "latitude": p.get("lat", p.get("Lat", 0.0)),
                        "longitude": p.get("lng", p.get("Lng", 0.0))
                    }
                    for p in day["evening"]
                ],

                "route_flow": day["route_flow"]
            })
            ai_content = (
            self.llm.generate_itinerary_text(
                itinerary_data=formatted_days,
                user=user
            )
        )

        return {
            "days": formatted_days,
            "ai_content": ai_content
        }
    
    def remove_duplicate_types(
        self,
        places
    ):

        used_categories = set()

        filtered = []

        for p in places:

            category = self.planner.detect_category(p)

            if category in used_categories:
                continue

            used_categories.add(category)

            filtered.append(p)

        return filtered

    def sort_by_time_semantic(
        self,
        places
    ):

        priority = {
            "morning": 1,
            "afternoon": 2,
            "evening": 3,
            "night": 4
        }

        return sorted(

            places,

            key=lambda p: priority.get(
                p.get(
                    "best_time",
                    "afternoon"
                ),
                99
            )
        )
    