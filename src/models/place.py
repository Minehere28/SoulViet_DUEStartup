from dataclasses import dataclass, field
from typing import List, Dict, Optional


@dataclass
class CandidatePlace:
    """
    Represents a place candidate retrieved from the graph or dataset.
    Matches Section 17 of the Design Doc.
    """
    place_id: str
    name: str
    type: str
    types: List[str] = field(default_factory=list)
    vibes: List[str] = field(default_factory=list)
    address: str = ""
    lat: float = 0.0
    lng: float = 0.0
    rating: Optional[float] = None
    review_count: Optional[int] = None
    price_min: Optional[float] = None
    price_max: Optional[float] = None
    price_category: Optional[str] = None
    operation_hours: Optional[str] = None
    description: Optional[str] = None
    activities: List[str] = field(default_factory=list)
    reviews: List[Dict] = field(default_factory=list)
    image: Optional[str] = None
    graph_edges: List[Dict] = field(default_factory=list)
    evidence_refs: List[str] = field(default_factory=list)
