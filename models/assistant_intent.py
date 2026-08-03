from datetime import date, time
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from models.user_request import BudgetLevel, RegionName, VibeName


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

    seed_place_ids: list[str] = Field(default_factory=list, max_length=5)
    keywords: list[str] = Field(default_factory=list, max_length=10)
    types: list[str] = Field(default_factory=list, max_length=10)
    activity_categories: list[str] = Field(default_factory=list, max_length=10)
    vibes: list[str] = Field(default_factory=list, max_length=5)
    minimum_rating: float = Field(default=4.0, ge=0, le=5)
    expand_near: bool = False
    near_hops: int = Field(default=0, ge=0, le=1)
    include_similar: bool = False
    candidate_limit: int = Field(default=20, ge=5, le=24)

    def is_active(self):
        return bool(
            self.seed_place_ids
            or self.keywords
            or self.types
            or self.activity_categories
            or self.vibes
            or self.expand_near
            or self.include_similar
        )


class PlaceOperation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: Literal["remove"]
    place_id: str | None = None
    day: int | None = Field(default=None, ge=1, le=14)
    position: int | None = Field(default=None, ge=1, le=10)


class AssistantIntent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    intent: Literal["modify_itinerary", "question", "unknown"]
    request_updates: RequestUpdates = Field(default_factory=RequestUpdates)
    graph_query: GraphQueryPlan = Field(default_factory=GraphQueryPlan)
    operations: list[PlaceOperation] = Field(default_factory=list, max_length=10)
    needs_clarification: bool = False
    clarification_question: str | None = Field(default=None, max_length=300)

