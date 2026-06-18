from typing import List, Tuple
from src.models.place import CandidatePlace
from src.models.score_breakdown import ScoreBreakdown


class Reranker:
    """
    Ensures type and geographic diversity.
    Matches Task T4.2 and Section 10 of Design Doc.
    """

    @staticmethod
    def diversify(
        scored_candidates: List[Tuple[CandidatePlace, ScoreBreakdown]],
        limit: int = 20
    ) -> List[Tuple[CandidatePlace, ScoreBreakdown]]:
        """
        Reranks candidates to ensure diversity.
        """
        if not scored_candidates:
            return []

        # Sort by total score first
        scored_candidates.sort(key=lambda x: x[1].total_score, reverse=True)
        
        reranked = []
        seen_types = {}
        
        # Simple diversity: penalize if type already seen many times
        for candidate, score in scored_candidates:
            c_type = candidate.type
            seen_count = seen_types.get(c_type, 0)
            
            # Penalize diversity score based on frequency
            penalty = 0.1 * seen_count
            score.diversity_score = 1.0 - min(penalty, 0.5)
            
            # Apply penalty to total score for reranking
            score.total_score *= score.diversity_score
            
            reranked.append((candidate, score))
            seen_types[c_type] = seen_count + 1

        # Final sort after diversity penalty
        reranked.sort(key=lambda x: x[1].total_score, reverse=True)
        
        return reranked[:limit]
