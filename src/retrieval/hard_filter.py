from typing import List, Dict, Set, Tuple
from src.models.place import CandidatePlace
from src.models.user_request import NormalizedConstraints


class HardFilter:
    """
    Removes candidates based on blacklist and mandatory constraints.
    Matches Task T3.2 and Section 8 of Design Doc.
    """

    @staticmethod
    def apply(
        candidates: List[CandidatePlace], 
        constraints: NormalizedConstraints,
        selected_ids: Set[str] = None
    ) -> Tuple[List[CandidatePlace], List[Dict[str, str]]]:
        """
        Applies hard filters to candidates.
        Returns (accepted_candidates, rejected_candidates_with_reasons).
        """
        accepted = []
        rejected = []
        selected_ids = selected_ids or set()

        for c in candidates:
            # 1. Duplicate check
            if c.place_id in selected_ids:
                rejected.append({"id": c.place_id, "reason": "duplicate_in_itinerary"})
                continue

            # 2. Blacklist type check
            if c.type in constraints.blacklist_types:
                rejected.append({"id": c.place_id, "reason": "blacklisted_type"})
                continue

            # 3. Mandatory coordinate check (for routing)
            if c.lat == 0.0 or c.lng == 0.0:
                rejected.append({"id": c.place_id, "reason": "missing_coordinates"})
                continue

            # 4. Minimum data check
            if not c.name or c.name == "Unknown":
                rejected.append({"id": c.place_id, "reason": "missing_name"})
                continue

            accepted.append(c)

        return accepted, rejected
