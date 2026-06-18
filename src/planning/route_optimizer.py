import math
import uuid
from typing import List, Dict
from src.models.itinerary import DraftItinerary, FrozenDraftItinerary, DraftItineraryItem


class RouteOptimizer:
    """
    Optimizes route within days and freezes the draft.
    Matches Task T5.2 and Section 12/12A of Design Doc.
    """

    @staticmethod
    def optimize_and_freeze(draft: DraftItinerary) -> FrozenDraftItinerary:
        """
        Reorders items in each day for route efficiency and returns a FrozenDraftItinerary.
        """
        for day in draft.days:
            RouteOptimizer._reorder_day_by_distance(day)
            RouteOptimizer._compute_travel_metrics(day)

        # Freeze the draft
        frozen = FrozenDraftItinerary(
            draft_id=str(uuid.uuid4()),
            is_frozen=True,
            request=draft.request,
            constraints=draft.constraints,
            days=draft.days,
            total_budget=draft.total_budget,
            estimated_total_cost=draft.estimated_total_cost,
            budget_remaining=draft.budget_remaining,
            budget_utilization=draft.budget_utilization,
            budget_gap=draft.budget_gap,
            budget_status=draft.budget_status,
            budget_warnings=draft.budget_warnings,
            total_estimated_time_minutes=draft.total_estimated_time_minutes,
            route_summary=draft.route_summary,
            score_breakdowns=[item.score_breakdown for day in draft.days for item in day],
            graph_traces=[{"place_id": item.candidate.place_id, "edges": item.candidate.graph_edges} 
                          for day in draft.days for item in day],
            warnings=draft.warnings
        )
        return frozen

    @staticmethod
    def _reorder_day_by_distance(day: List[DraftItineraryItem]):
        """
        Simple greedy reordering based on distance.
        """
        if len(day) <= 2:
            return

        # Keep first item (e.g. Morning) and reorder others
        # This is a basic implementation; more complex logic could involve TSP or Clustering
        ordered = [day[0]]
        remaining = day[1:]
        
        while remaining:
            last = ordered[-1]
            next_item = min(remaining, 
                            key=lambda x: RouteOptimizer._haversine(
                                last.candidate.lat, last.candidate.lng,
                                x.candidate.lat, x.candidate.lng
                            ))
            ordered.append(next_item)
            remaining.remove(next_item)
        
        # Update slots to maintain sequence
        slots = [item.slot for item in day]
        for i, item in enumerate(ordered):
            item.slot = slots[i]
            
        day[:] = ordered

    @staticmethod
    def _compute_travel_metrics(day: List[DraftItineraryItem]):
        """
        Computes distance between consecutive items.
        """
        for i in range(1, len(day)):
            prev = day[i-1]
            curr = day[i]
            dist = RouteOptimizer._haversine(
                prev.candidate.lat, prev.candidate.lng,
                curr.candidate.lat, curr.candidate.lng
            )
            curr.estimated_travel_distance_km = dist

    @staticmethod
    def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """
        Calculates Haversine distance in km.
        """
        R = 6371.0
        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)
        a = (math.sin(dlat / 2)**2 + 
             math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2)**2)
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        return R * c
