from typing import List, Tuple
from src.models.place import CandidatePlace
from src.models.score_breakdown import ScoreBreakdown
from src.models.user_request import NormalizedConstraints


class UtilityOptimizer:
    """
    Computes marginal utility per cost for ranking.
    Matches Task T4.2 and Section 9A of Design Doc.
    """

    @staticmethod
    def optimize(
        candidates: List[Tuple[CandidatePlace, ScoreBreakdown]],
        constraints: NormalizedConstraints
    ) -> List[Tuple[CandidatePlace, ScoreBreakdown]]:
        """
        Adjusts scores based on marginal utility per cost.
        """
        for candidate, score in candidates:
            cost = score.estimated_item_cost or 10000.0 # Avoid div by zero
            if cost == 0:
                cost = 10000.0
                
            # marginal_utility = utility / cost
            # In our case, utility is the total_score
            marginal_utility = score.total_score / (cost / 100000.0) # Normalized to 100k units
            score.marginal_utility_per_cost = marginal_utility
            
            # Utility optimization is a soft signal
            # We add a small boost for high marginal utility
            score.total_score += min(marginal_utility * 0.05, 0.1)

        # Re-sort
        candidates.sort(key=lambda x: x[1].total_score, reverse=True)
        return candidates
