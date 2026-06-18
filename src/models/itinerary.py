from dataclasses import dataclass, field
from typing import List, Optional, Dict
from src.models.user_request import UserRequest, NormalizedConstraints
from src.models.place import CandidatePlace
from src.models.score_breakdown import ScoreBreakdown


@dataclass
class DraftItineraryItem:
    """
    An item in a draft itinerary.
    Matches Section 17 of the Design Doc.
    """
    day_index: int
    slot: str
    candidate: CandidatePlace
    estimated_cost: float
    estimated_duration_minutes: int
    estimated_travel_distance_km: float
    score_breakdown: ScoreBreakdown
    why_selected: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


@dataclass
class DraftItinerary:
    """
    A mutable draft itinerary being built.
    Matches Section 17 of the Design Doc.
    """
    request: UserRequest
    constraints: NormalizedConstraints
    days: List[List[DraftItineraryItem]] = field(default_factory=list)
    total_budget: float = 0.0
    estimated_total_cost: float = 0.0
    budget_remaining: float = 0.0
    budget_utilization: float = 0.0
    budget_gap: float = 0.0
    budget_status: str = "unknown"
    budget_warnings: List[str] = field(default_factory=list)
    total_estimated_time_minutes: int = 0
    route_summary: Dict = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)


@dataclass
class FrozenDraftItinerary:
    """
    An immutable snapshot of a draft itinerary ready for validation.
    Matches Section 17 of the Design Doc.
    """
    draft_id: str
    is_frozen: bool
    request: UserRequest
    constraints: NormalizedConstraints
    days: List[List[DraftItineraryItem]]
    total_budget: float
    estimated_total_cost: float
    budget_remaining: float
    budget_utilization: float
    budget_gap: float
    budget_status: str
    budget_warnings: List[str]
    total_estimated_time_minutes: int
    route_summary: Dict
    score_breakdowns: List[ScoreBreakdown]
    graph_traces: List[Dict]
    warnings: List[str]
    parent_draft_id: Optional[str] = None
