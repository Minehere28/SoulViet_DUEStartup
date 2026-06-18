from dataclasses import dataclass
from typing import Optional, List


@dataclass
class Evidence:
    """
    Represents evidence for a recommendation or claim.
    Matches Task T2.1 and Section 17 placeholders.
    """
    source_field: str  # e.g., 'reviews', 'description'
    content: str
    place_id: str
    confidence_score: float = 1.0
    metadata: Optional[dict] = None
