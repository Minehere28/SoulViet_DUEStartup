from typing import List, Tuple, Set
from src.models.user_request import UserRequest, NormalizedConstraints
from src.models.place import CandidatePlace
from src.models.score_breakdown import ScoreBreakdown
from src.models.itinerary import DraftItinerary, DraftItineraryItem
from src.planning.slot_assigner import SlotAssigner


class DayPlanner:
    """
    Assembles ranked candidates into draft days and slots.
    Matches Task T5.1 and Section 11 of Design Doc.
    """

    @staticmethod
    def plan_days(
        ranked_candidates: List[Tuple[CandidatePlace, ScoreBreakdown]],
        constraints: NormalizedConstraints,
        selected_ids: Set[str] = None
    ) -> DraftItinerary:
        """
        Builds a DraftItinerary by assigning candidates to slots across days.
        """
        draft = DraftItinerary(
            request=None, # To be filled by orchestrator
            constraints=constraints,
            total_budget=constraints.total_budget
        )
        
        used_in_draft = selected_ids or set()
        
        for day_idx in range(constraints.days):
            day_items: List[DraftItineraryItem] = []
            
            for slot in constraints.slots_per_day:
                # Find the best ranked candidate for this slot that hasn't been used
                best_match = None
                best_score = None
                
                for candidate, score in ranked_candidates:
                    if candidate.place_id in used_in_draft:
                        continue
                    
                    if SlotAssigner.is_suitable(candidate, slot):
                        best_match = candidate
                        best_score = score
                        break
                
                if best_match:
                    item = DraftItineraryItem(
                        day_index=day_idx,
                        slot=slot,
                        candidate=best_match,
                        estimated_cost=best_match.price_max or 0.0,
                        estimated_duration_minutes=90, # Placeholder duration
                        estimated_travel_distance_km=0.0,
                        score_breakdown=best_score,
                        why_selected=[f"Top ranked candidate for {slot} slot"]
                    )
                    day_items.append(item)
                    used_in_draft.add(best_match.place_id)
            
            draft.days.append(day_items)
            
        # Compute summary metrics
        DayPlanner._update_summary(draft)
        return draft

    @staticmethod
    def _update_summary(draft: DraftItinerary):
        total_cost = 0.0
        for day in draft.days:
            for item in day:
                total_cost += item.estimated_cost
        
        draft.estimated_total_cost = total_cost
        draft.budget_remaining = draft.total_budget - total_cost
        draft.budget_gap = draft.budget_remaining
        if draft.total_budget > 0:
            draft.budget_utilization = total_cost / draft.total_budget
        
        if total_cost > draft.total_budget:
            draft.budget_status = "over_budget"
        elif draft.budget_utilization < 0.5:
            draft.budget_status = "under_budget_warning"
        else:
            draft.budget_status = "good_value"
