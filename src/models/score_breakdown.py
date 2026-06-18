from dataclasses import dataclass, field
from typing import List, Dict, Optional


@dataclass
class ScoreBreakdown:
    """
    Detailed score breakdown for a place candidate.
    Matches Section 17 of the Design Doc.
    """
    total_score: float = 0.0
    style_score: float = 0.0
    type_score: float = 0.0
    budget_score: float = 0.0
    item_budget_score: float = 0.0
    budget_efficiency_score: float = 0.0
    budget_utilization_score: float = 0.0
    marginal_utility_per_cost: float = 0.0
    estimated_item_cost: Optional[float] = None
    price_category: Optional[str] = None
    price_range: Optional[str] = None
    budget_reason: Optional[str] = None
    rating_score: float = 0.0
    review_confidence_score: float = 0.0
    distance_score: float = 0.0
    time_slot_score: float = 0.0
    diversity_score: float = 0.0
    graph_score: float = 0.0
    evidence_score: float = 0.0
    penalties: List[Dict] = field(default_factory=list)
    matched_reasons: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
