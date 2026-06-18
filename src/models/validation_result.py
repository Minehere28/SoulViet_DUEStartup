from dataclasses import dataclass, field
from typing import List, Dict, Optional


@dataclass
class ValidationResult:
    """
    Represents the result of a validation check.
    Matches Section 17 of the Design Doc.
    """
    is_valid: bool
    errors: List[Dict] = field(default_factory=list)
    warnings: List[Dict] = field(default_factory=list)
    failed_rules: List[str] = field(default_factory=list)
    passed_rules: List[str] = field(default_factory=list)
    repair_suggestions: List[str] = field(default_factory=list)
    affected_day: Optional[int] = None
    affected_slot: Optional[str] = None
    affected_place_id: Optional[str] = None
    can_retry: bool = False
    retry_strategy: Optional[str] = None
