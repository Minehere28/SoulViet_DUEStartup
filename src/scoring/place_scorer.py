from typing import List, Dict, Optional
from src.models.place import CandidatePlace
from src.models.user_request import NormalizedConstraints
from src.models.score_breakdown import ScoreBreakdown


class PlaceScorer:
    """
    Computes place scores and breakdowns.
    Matches Task T4.1 and Section 9 of Design Doc.
    """

    def score(
        self, 
        candidate: CandidatePlace, 
        constraints: NormalizedConstraints,
        current_total_cost: float = 0.0
    ) -> ScoreBreakdown:
        """
        Computes the score for a single candidate.
        """
        breakdown = ScoreBreakdown()
        
        # 1. Style/Vibe Score
        style_score = self._compute_style_score(candidate, constraints)
        breakdown.style_score = style_score
        
        # 2. Rating Score
        rating_score = (candidate.rating or 0.0) / 5.0
        breakdown.rating_score = rating_score
        
        # 3. Budget (Soft) Signal
        item_cost = candidate.price_max or 0.0
        breakdown.estimated_item_cost = item_cost
        breakdown.price_category = candidate.price_category
        
        budget_score = self._compute_budget_fit_score(item_cost, constraints)
        breakdown.budget_score = budget_score
        
        # 4. Review Confidence
        review_confidence = min((candidate.review_count or 0) / 100.0, 1.0)
        breakdown.review_confidence_score = review_confidence
        
        # Total Score Calculation (Section 9 Formula)
        # total_score = style_score * 0.25 + type_score * 0.15 + budget_score * 0.15 + rating_score * 0.10 ...
        # Simplified weights for now
        total = (
            style_score * 0.40 +
            rating_score * 0.30 +
            budget_score * 0.20 +
            review_confidence * 0.10
        )
        
        breakdown.total_score = total
        return breakdown

    def _compute_style_score(self, candidate: CandidatePlace, constraints: NormalizedConstraints) -> float:
        """Heuristic for style matching."""
        if not constraints.style_tags:
            return 0.5
        
        matches = 0
        for tag in constraints.style_tags:
            if tag.lower() in [v.lower() for v in candidate.vibes]:
                matches += 1
        
        return matches / len(constraints.style_tags) if constraints.style_tags else 0.5

    def _compute_budget_fit_score(self, cost: float, constraints: NormalizedConstraints) -> float:
        """Soft signal for budget fit."""
        if constraints.daily_budget <= 0:
            return 1.0
            
        # If item cost is way above daily budget, lower score
        if cost > constraints.daily_budget * 1.5:
            return 0.2
        return 0.8
