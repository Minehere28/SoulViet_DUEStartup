from typing import Any, Optional


class PlaceNormalizer:
    """
    Normalizes place fields and coerces types safely.
    Matches Task T2.3 requirements.
    """
    
    @staticmethod
    def normalize_coordinate(value: Any) -> float:
        try:
            return float(value)
        except (ValueError, TypeError):
            return 0.0

    @staticmethod
    def normalize_rating(value: Any) -> Optional[float]:
        try:
            rating = float(value)
            if 0 <= rating <= 5:
                return rating
            return None
        except (ValueError, TypeError):
            return None

    @staticmethod
    def normalize_review_count(value: Any) -> int:
        try:
            return int(value)
        except (ValueError, TypeError):
            return 0

    @staticmethod
    def normalize_list(value: Any) -> list:
        if isinstance(value, list):
            return value
        if isinstance(value, str):
            if value.startswith('[') and value.endswith(']'):
                # Basic cleanup for JSON-like strings if needed, 
                # but idiomatic would be json.loads or simple split
                import json
                try:
                    return json.loads(value)
                except json.JSONDecodeError:
                    pass
            return [v.strip() for v in value.split(',') if v.strip()]
        return []
