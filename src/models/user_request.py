from dataclasses import dataclass, field
from typing import Optional, List, Dict


@dataclass
class UserRequest:
    """
    Represents the raw user request for an itinerary.
    Matches Section 17 of the Design Doc.
    """
    duration: int
    budget: float
    vibe: str
    location: Optional[str] = None
    pace: Optional[str] = None
    food_preference: Optional[str] = None
    must_see: List[str] = field(default_factory=list)
    avoid: List[str] = field(default_factory=list)
    group_size: Optional[int] = None
    travel_mode: Optional[str] = None
    start_time: Optional[str] = None


@dataclass
class NormalizedConstraints:
    """
    Represents the normalized constraints derived from a UserRequest.
    Matches Section 17 of the Design Doc.
    """
    days: int
    total_budget: float
    daily_budget: float
    budget_mode: str = "total_trip"
    target_budget_utilization: float = 0.85
    minimum_budget_utilization_warning_threshold: float = 0.5
    budget_buffer_ratio: float = 0.1
    style_key: str = ""
    style_tags: List[str] = field(default_factory=list)
    preferred_types: List[str] = field(default_factory=list)
    blacklist_types: List[str] = field(default_factory=list)
    pace_level: str = "normal"
    max_places_per_day: int = 4
    slots_per_day: List[str] = field(default_factory=lambda: ["morning", "lunch", "afternoon", "evening"])
    hard_constraints: Dict = field(default_factory=dict)
    soft_preferences: Dict = field(default_factory=dict)
