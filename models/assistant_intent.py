from datetime import date, time
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from models.user_request import (
    BudgetLevel,
    CategoryConstraint,
    RegionName,
    VibeName,
)


class RequestUpdates(BaseModel):
    model_config = ConfigDict(extra="forbid")

    duration: int | None = Field(default=None, ge=1, le=14)
    vibe: VibeName | None = None
    region: RegionName | None = None
    budget_level: BudgetLevel | None = None
    max_places_per_day: int | None = Field(default=None, ge=1, le=8)
    max_daily_distance_km: float | None = Field(default=None, gt=0, le=100)
    preferred_activities: list[str] | None = Field(default=None, max_length=10)
    start_date: date | None = None
    day_start_time: time | None = None
    day_end_time: time | None = None


class GraphQueryPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    seed_place_ids: list[str] | None = Field(default_factory=list, max_length=5)
    keywords: list[str] | None = Field(default_factory=list, max_length=10)
    types: list[str] | None = Field(default_factory=list, max_length=10)
    activity_categories: list[str] | None = Field(default_factory=list, max_length=10)
    vibes: list[str] | None = Field(default_factory=list, max_length=5)
    required_place_names: list[str] | None = Field(default_factory=list, max_length=10)
    excluded_place_names: list[str] | None = Field(default_factory=list, max_length=10)
    excluded_types: list[str] | None = Field(default_factory=list, max_length=20)
    excluded_activity_categories: list[str] | None = Field(
        default_factory=list, max_length=20
    )
    category_constraints: list[CategoryConstraint] | None = Field(
        default_factory=list, max_length=10
    )
    minimum_rating: float = Field(default=4.0, ge=0, le=5)
    expand_near: bool = False
    near_hops: int = Field(default=0, ge=0, le=1)
    include_similar: bool = False
    candidate_limit: int = Field(default=20, ge=5, le=90)

    @model_validator(mode="before")
    @classmethod
    def clean_null_lists(cls, values):
        if isinstance(values, dict):
            list_fields = [
                "seed_place_ids", "keywords", "types", "activity_categories",
                "vibes", "required_place_names", "excluded_place_names",
                "excluded_types", "excluded_activity_categories", "category_constraints"
            ]
            for field in list_fields:
                if values.get(field) is None:
                    values[field] = []
        return values

    def is_active(self):
        return bool(
            self.seed_place_ids
            or self.keywords
            or self.types
            or self.activity_categories
            or self.vibes
            or self.required_place_names
            or self.excluded_place_names
            or self.excluded_types
            or self.excluded_activity_categories
            or self.category_constraints
            or self.expand_near
            or self.include_similar
        )


class PlaceOperation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: Literal["remove"] = "remove"
    place_id: str | None = None
    day: int | None = Field(default=None, ge=1, le=14)
    position: int | None = Field(default=None, ge=0, le=20)
    item_type: Literal["attraction", "meal", "any"] = "attraction"

    @model_validator(mode="before")
    @classmethod
    def normalize_fields(cls, values):
        if isinstance(values, dict):
            if "type" in values and "action" not in values:
                values["action"] = values.pop("type")
            if values.get("position") == 0:
                values["position"] = 1
        return values


class AssistantIntent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    intent: Literal["modify_itinerary", "question", "unknown"]
    request_updates: RequestUpdates = Field(default_factory=RequestUpdates)
    graph_query: GraphQueryPlan = Field(default_factory=GraphQueryPlan)
    scope: Literal[
        "full_itinerary", "attractions_only", "meals_only",
        "single_day", "single_item",
    ] = "full_itinerary"
    meal_preferences: list[str] | None = Field(default_factory=list, max_length=10)
    operations: list[PlaceOperation] | None = Field(default_factory=list, max_length=10)
    needs_clarification: bool = False
    clarification_question: str | None = Field(default=None, max_length=300)

    @model_validator(mode="before")
    @classmethod
    def clean_null_lists(cls, values):
        if isinstance(values, dict):
            if values.get("meal_preferences") is None:
                values["meal_preferences"] = []
            if values.get("operations") is None:
                values["operations"] = []
        return values
