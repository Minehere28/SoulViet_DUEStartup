from src.models.user_request import UserRequest
from src.models.validation_result import ValidationResult
import math


class RequestValidator:
    """
    Implements validation logic for UserRequest.
    Matches requirements in T1.2 and Design Doc.
    """
    ALLOWED_VIBES = {"culture", "chill", "food", "adventure", "creative"}
    MIN_DURATION = 1
    MAX_DURATION = 7

    @staticmethod
    def validate(request: UserRequest) -> ValidationResult:
        errors = []
        passed_rules = []
        failed_rules = []

        # Duration check
        if request.duration < RequestValidator.MIN_DURATION or request.duration > RequestValidator.MAX_DURATION:
            errors.append({
                "field": "duration",
                "code": "out_of_range",
                "message": f"Duration must be between {RequestValidator.MIN_DURATION} and {RequestValidator.MAX_DURATION} days."
            })
            failed_rules.append("duration_check")
        else:
            passed_rules.append("duration_check")

        # Budget check
        if request.budget <= 0 or not math.isfinite(request.budget):
            errors.append({
                "field": "budget",
                "code": "invalid_value",
                "message": "Budget must be a finite number greater than 0."
            })
            failed_rules.append("budget_check")
        else:
            passed_rules.append("budget_check")

        # Vibe check
        if request.vibe.lower() not in RequestValidator.ALLOWED_VIBES:
            errors.append({
                "field": "vibe",
                "code": "invalid_choice",
                "message": f"Vibe must be one of: {', '.join(RequestValidator.ALLOWED_VIBES)}."
            })
            failed_rules.append("vibe_check")
        else:
            passed_rules.append("vibe_check")

        return ValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
            passed_rules=passed_rules,
            failed_rules=failed_rules
        )
