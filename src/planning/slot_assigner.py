from typing import List, Optional
from src.models.place import CandidatePlace


class SlotAssigner:
    """
    Assigns candidates to slots based on type and suitability.
    Matches Task T5.1 and Section 11 of Design Doc.
    """
    
    SLOTS = ["morning", "lunch", "afternoon", "evening"]

    @staticmethod
    def is_suitable(candidate: CandidatePlace, slot: str) -> bool:
        """
        Determines if a candidate is suitable for a specific slot.
        """
        slot = slot.lower()
        c_types = [t.lower() for t in candidate.types]
        c_type = candidate.type.lower()
        
        # Meal slot logic
        if slot in ["lunch", "evening"]:
            # Prefer restaurants/food for lunch/evening slots
            food_types = ["restaurant", "cafe", "food", "quán ăn"]
            if any(ft in c_type or ft in t for ft in food_types for t in c_types):
                return True
            # For evening, also allow nightlife/entertainment
            if slot == "evening":
                entertainment_types = ["bar", "pub", "nightlife", "cinema", "park"]
                if any(et in c_type or et in t for et in entertainment_types for t in c_types):
                    return True
            return False

        # Morning/Afternoon logic
        if slot in ["morning", "afternoon"]:
            # Prefer sightseeing, culture, landmarks
            sightseeing_types = ["sightseeing", "culture", "museum", "landmark", "park", "temple", "pagoda"]
            if any(st in c_type or st in t for st in sightseeing_types for t in c_types):
                return True
            return True # Fallback to True for general sightseeing

        return True
