import json
import math
from datetime import date, time

from langchain_core.tools import tool
from pydantic import BaseModel, ConfigDict, Field, model_validator

from models.user_request import (
    BudgetLevel, CategoryConstraint, LocationMode, RegionName, UserRequest,
    VibeName,
)
from services.graph_query_service import GraphQueryService
from services.itinerary_service import ItineraryService
from services.itinerary_validator import ItineraryValidator
from services.locality_service import ResolvedLocality
from models.assistant_intent import GraphQueryPlan
from utils.place_matching import normalize_text, place_categories, place_types
from utils.distance import haversine


class EmptyInput(BaseModel):
    model_config = ConfigDict(extra="ignore")


class DayInput(BaseModel):
    model_config = ConfigDict(extra="ignore")
    day: int = Field(ge=1, le=14)


class PlaceIdInput(BaseModel):
    model_config = ConfigDict(extra="ignore")
    place_id: str = Field(min_length=1, max_length=100)


class AddPlaceInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    place_id: str | None = Field(default=None, min_length=1, max_length=100)
    query: str | None = Field(default=None, min_length=2, max_length=200)
    day: int | None = Field(default=None, ge=1, le=14)
    day_strategy: str = Field(
        default="auto", pattern="^(auto|most_free)$"
    )

    @model_validator(mode="after")
    def require_place_reference(self):
        if not self.place_id and not self.query:
            raise ValueError("Provide place_id or query")
        return self


class AddPlaceMutationInput(BaseModel):
    """Public mutation reference: names are resolved by the harness, never by the LLM."""

    model_config = ConfigDict(extra="forbid")
    query: str = Field(min_length=2, max_length=200)
    day: int | None = Field(default=None, ge=1, le=14)
    day_strategy: str = Field(default="auto", pattern="^(auto|most_free)$")


class RemoveItemMutationInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query: str | None = Field(default=None, min_length=2, max_length=200)
    day: int | None = Field(default=None, ge=1, le=14)
    position: int | None = Field(default=None, ge=0, le=20)
    relative_position: str | None = Field(
        default=None, pattern="^(first|last)$"
    )
    item_type: str = Field(default="attraction", pattern="^(attraction|meal|any)$")

    @model_validator(mode="before")
    @classmethod
    def normalize_position(cls, values):
        if isinstance(values, dict) and values.get("position") == 0:
            values["position"] = 1
        return values

    @model_validator(mode="after")
    def require_reference(self):
        if not self.query and (
            self.day is None
            or (self.position is None and self.relative_position is None)
        ):
            raise ValueError("Provide a query, or both day and position")
        return self


class MemoryIdInput(BaseModel):
    model_config = ConfigDict(extra="ignore")
    memory_id: str = Field(min_length=1, max_length=100)


class SearchPlacesInput(BaseModel):
    model_config = ConfigDict(extra="ignore")
    query: str = Field(min_length=1, max_length=300)
    types: list[str] | None = Field(default_factory=list, max_length=10)
    activity_categories: list[str] | None = Field(default_factory=list, max_length=10)
    minimum_rating: float = Field(default=4.0, ge=0, le=5)
    limit: int = Field(default=10, ge=1, le=20)

    @model_validator(mode="before")
    @classmethod
    def clean_nulls(cls, values):
        if isinstance(values, dict):
            if values.get("types") is None:
                values["types"] = []
            if values.get("activity_categories") is None:
                values["activity_categories"] = []
        return values


class LocationScopeInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query: str = Field(
        min_length=2,
        max_length=120,
        description="Destination/locality text extracted from the user's request.",
    )


class UpdateTripInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    duration: int | None = Field(default=None, ge=1, le=14)
    vibe: VibeName | None = None
    region: RegionName | None = None
    location_focus: str | None = Field(
        default=None,
        min_length=2,
        max_length=120,
        description=(
            "Locality extracted from the user's destination request. The "
            "executor validates it against graph data and synchronizes region."
        ),
    )
    location_mode: LocationMode | None = None
    location_radius_km: float | None = Field(default=None, gt=0, le=50)
    clear_location_focus: bool = False
    budget_level: BudgetLevel | None = None
    max_places_per_day: int | None = Field(default=None, ge=1, le=8)
    max_daily_distance_km: float | None = Field(default=None, gt=0, le=100)
    max_daily_distance_is_hard: bool = Field(
        default=False,
        description=(
            "True only when the user explicitly states a maximum travel "
            "distance; false for application or model defaults."
        ),
    )
    start_date: date | None = None
    day_start_time: time | None = None
    day_end_time: time | None = None
    start_lat: float | None = Field(default=None, ge=-90, le=90)
    start_lng: float | None = Field(default=None, ge=-180, le=180)
    start_name: str | None = Field(default=None, max_length=120)

    @model_validator(mode="after")
    def require_change(self):
        if (
            self.max_daily_distance_is_hard
            and self.max_daily_distance_km is None
        ):
            raise ValueError(
                "A hard distance constraint requires max_daily_distance_km"
            )
        if not self.model_dump(exclude_none=True, exclude_defaults=True):
            raise ValueError("At least one trip setting is required")
        return self


class ActivitiesInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    activities: list[str] = Field(min_length=1, max_length=10)
    mode: str = Field(default="replace", pattern="^(replace|add|remove)$")


class RemoveItemInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    place_id: str | None = Field(default=None, max_length=100)
    query: str | None = Field(default=None, min_length=2, max_length=200)
    day: int | None = Field(default=None, ge=1, le=14)
    position: int | None = Field(default=None, ge=0, le=20)
    relative_position: str | None = Field(
        default=None, pattern="^(first|last)$"
    )
    item_type: str = Field(default="attraction", pattern="^(attraction|meal|any)$")

    @model_validator(mode="before")
    @classmethod
    def normalize_position(cls, values):
        if isinstance(values, dict) and values.get("position") == 0:
            values["position"] = 1
        return values

    @model_validator(mode="after")
    def require_reference(self):
        if (
            not self.place_id
            and not self.query
            and (
                self.day is None
                or (self.position is None and self.relative_position is None)
            )
        ):
            raise ValueError("Provide place_id, query, or both day and position")
        return self


class SaveMemoryInput(BaseModel):
    model_config = ConfigDict(extra="ignore")
    text: str = Field(min_length=3, max_length=500)
    kind: str = Field(default="preference", max_length=50)


class ClarificationInput(BaseModel):
    model_config = ConfigDict(extra="ignore")
    question: str = Field(min_length=3, max_length=300)


class UnsupportedRequestInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    capability: str = Field(pattern="^meal_planning$")
    request_summary: str = Field(
        min_length=3,
        max_length=300,
        description=(
            "A short Vietnamese summary of the unsupported part of the "
            "user's request, without inventing places or results."
        ),
    )


class CategoryConstraintInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    category: str = Field(
        min_length=1,
        max_length=120,
        description="Category requested or preferred by the user.",
    )
    min_count: int = Field(default=0, ge=0, le=50)
    max_count: int | None = Field(default=None, ge=0, le=50)
    target_count: int | None = Field(default=None, ge=0, le=50)
    mode: str = Field(
        default="soft",
        pattern="^(hard|soft)$",
        description=(
            "Use soft for preferences. Use hard only when the user explicitly "
            "requires an exact/minimum/maximum category count."
        ),
    )
    explicitly_required: bool = Field(
        default=False,
        description=(
            "True only when the user explicitly made this category count "
            "mandatory; never infer it from words such as prefer or like."
        ),
    )


class MealPreferencesInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    preferences: list[str] = Field(min_length=1, max_length=10)
    mode: str = Field(default="replace", pattern="^(replace|add|remove)$")


class MealRequestInput(BaseModel):
    """A meal requirement scoped to one day and one meal slot."""

    model_config = ConfigDict(extra="forbid")
    day: int | None = Field(default=None, ge=1, le=14)
    day_strategy: str = Field(
        default="auto", pattern="^(auto|most_free)$"
    )
    meal_slot: str = Field(pattern="^(lunch|dinner|cafe_break)$")
    preferences: list[str] = Field(min_length=1, max_length=10)
    required: bool = True
    near_route: bool = True

    @model_validator(mode="after")
    def require_day_selection(self):
        if self.day is None and self.day_strategy == "auto":
            raise ValueError("Provide day or day_strategy=most_free")
        return self


class ScopedExclusionInput(BaseModel):
    """Exclusions that apply to one day, with explicit place exceptions."""

    model_config = ConfigDict(extra="forbid")
    day: int = Field(ge=1, le=14)
    place_types: list[str] = Field(default_factory=list, max_length=20)
    activity_categories: list[str] = Field(default_factory=list, max_length=20)
    except_place_ids: list[str] = Field(default_factory=list, max_length=20)
    except_queries: list[str] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def require_filter(self):
        if not self.place_types and not self.activity_categories:
            raise ValueError("Provide a scoped place type or activity category")
        return self


class ScopedExclusionMutationInput(BaseModel):
    """Public scoped exclusion; exception names are resolved inside the graph."""

    model_config = ConfigDict(extra="forbid")
    day: int = Field(ge=1, le=14)
    place_types: list[str] = Field(default_factory=list, max_length=20)
    activity_categories: list[str] = Field(default_factory=list, max_length=20)
    except_queries: list[str] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def require_filter(self):
        if not self.place_types and not self.activity_categories:
            raise ValueError("Provide a scoped place type or activity category")
        return self


class DayPolicyInput(BaseModel):
    """Deterministic editing and density policy for one itinerary day."""

    model_config = ConfigDict(extra="forbid")
    day: int = Field(ge=1, le=14)
    max_places: int | None = Field(default=None, ge=1, le=8)
    remove_count: int = Field(default=0, ge=0, le=8)
    remove_strategy: str = Field(
        default="least_important",
        pattern="^(least_important|farthest|last)$",
    )
    fill_if_idle: bool = True


class OptimizationPolicyInput(BaseModel):
    """Trip-wide editing semantics separate from travel preferences."""

    model_config = ConfigDict(extra="forbid")
    preserve_existing_places: bool = False
    reorder_only: bool = False
    minimize_travel: bool = True
    fill_idle_gaps: bool = True


class ReplacePlaceInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    old_place_id: str | None = Field(default=None, min_length=1, max_length=100)
    old_query: str | None = Field(default=None, min_length=2, max_length=200)
    new_place_id: str | None = Field(default=None, min_length=1, max_length=100)
    new_query: str | None = Field(default=None, min_length=2, max_length=200)
    keep_same_day: bool = True

    @model_validator(mode="after")
    def require_old_and_new_references(self):
        if not self.old_place_id and not self.old_query:
            raise ValueError("Provide old_place_id or old_query")
        if not self.new_place_id and not self.new_query:
            raise ValueError("Provide new_place_id or new_query")
        return self


class ReplacePlaceMutationInput(BaseModel):
    """Public replacement reference; the model supplies names, not graph IDs."""

    model_config = ConfigDict(extra="forbid")
    old_query: str = Field(min_length=2, max_length=200)
    new_query: str = Field(min_length=2, max_length=200)
    keep_same_day: bool = True


class MovePlaceMutationInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query: str = Field(min_length=2, max_length=200)
    target_day: int = Field(ge=1, le=14)


class ExclusionFiltersInput(BaseModel):
    model_config = ConfigDict(extra="ignore")
    place_types: list[str] | None = Field(default_factory=list, max_length=20)
    activity_categories: list[str] | None = Field(default_factory=list, max_length=20)
    mode: str = Field(default="add", pattern="^(add|remove|replace)$")

    @model_validator(mode="before")
    @classmethod
    def clean_nulls(cls, values):
        if isinstance(values, dict):
            if values.get("place_types") is None:
                values["place_types"] = []
            if values.get("activity_categories") is None:
                values["activity_categories"] = []
        return values

    @model_validator(mode="after")
    def require_filter(self):
        if not self.place_types and not self.activity_categories:
            raise ValueError("Provide at least one exclusion filter")
        return self


class QualityPoliciesInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    exclude_shop_only_attractions: bool = True
    deduplicate_brands: bool = True


class ApplyTripChangesInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    trip_settings: UpdateTripInput | None = None
    activity_preferences: ActivitiesInput | None = None
    place_query: GraphQueryPlan | None = Field(
        default=None,
        description=(
            "LLM-authored semantic candidate query over real graph fields. "
            "Use keywords, types, activity_categories and vibes to express what "
            "the user wants; use match_mode=focused when that theme defines the trip."
        ),
    )
    category_constraints: list[CategoryConstraintInput] | None = Field(
        default_factory=list, max_length=10
    )
    add_places: list[AddPlaceMutationInput] | None = Field(
        default_factory=list, max_length=10
    )
    remove_places: list[RemoveItemMutationInput] | None = Field(
        default_factory=list, max_length=10
    )
    replacements: list[ReplacePlaceMutationInput] | None = Field(
        default_factory=list, max_length=10
    )
    move_places: list[MovePlaceMutationInput] | None = Field(
        default_factory=list, max_length=10
    )
    excluded_place_types: list[str] | None = Field(default_factory=list, max_length=20)
    excluded_activity_categories: list[str] | None = Field(
        default_factory=list, max_length=20
    )
    scoped_exclusions: list[ScopedExclusionMutationInput] | None = Field(
        default_factory=list, max_length=14
    )
    day_policies: list[DayPolicyInput] | None = Field(
        default_factory=list, max_length=14
    )
    optimization_policy: OptimizationPolicyInput | None = None
    quality_policies: QualityPoliciesInput | None = None

    @model_validator(mode="before")
    @classmethod
    def clean_null_lists(cls, values):
        if isinstance(values, dict):
            values = dict(values)
            # Tool-calling models sometimes flatten UpdateTripInput into the
            # outer object. Normalize that equivalent shape transactionally.
            flat_trip_settings = {
                field: values.pop(field)
                for field in list(values)
                if field in UpdateTripInput.model_fields
            }
            if flat_trip_settings:
                nested = dict(values.get("trip_settings") or {})
                values["trip_settings"] = {
                    **flat_trip_settings,
                    **nested,
                }
            list_fields = [
                "category_constraints", "add_places", "remove_places",
                "replacements", "move_places", "excluded_place_types", "excluded_activity_categories",
                "scoped_exclusions", "day_policies"
            ]
            for field in list_fields:
                if values.get(field) is None:
                    values[field] = []
        return values

    @model_validator(mode="after")
    def require_change(self):
        values = self.model_dump(exclude_none=True, exclude_defaults=True)
        if not values:
            raise ValueError("Provide at least one itinerary change")
        return self


class MovePlaceInput(BaseModel):
    model_config = ConfigDict(extra="ignore")
    place_id: str = Field(min_length=1, max_length=100)
    target_day: int = Field(ge=1, le=14)


@tool(args_schema=EmptyInput)
def get_trip_state():
    """Đọc yêu cầu chuyến đi và trạng thái working/validation hiện tại."""


@tool(args_schema=EmptyInput)
def get_itinerary_summary():
    """Đọc tóm tắt lịch hiện tại: ngày, điểm, quãng đường và chi phí."""


@tool(args_schema=DayInput)
def get_day_details(day: int):
    """Đọc chi tiết một ngày trong lịch hiện tại."""


@tool(args_schema=PlaceIdInput)
def get_place_details(place_id: str):
    """Đọc dữ liệu địa điểm thật bằng place ID."""


@tool(args_schema=SearchPlacesInput)
def search_places(query: str, types=None, activity_categories=None, minimum_rating=4, limit=10):
    """Tìm địa điểm trong graph để lấy ID thật trước khi thêm hoặc thay thế."""


@tool(args_schema=LocationScopeInput)
def resolve_location_scope(query: str):
    """Tra graph để phân giải locality sang region và kiểm tra nguồn candidate thật."""


@tool(args_schema=UpdateTripInput)
def update_trip_settings(**kwargs):
    """Cập nhật working request: ngày, vùng, vibe, ngân sách, giờ hoặc giới hạn."""


@tool(args_schema=ActivitiesInput)
def set_activity_preferences(activities: list[str], mode="replace"):
    """Thay, thêm hoặc bỏ các nhóm hoạt động ưu tiên trong working request."""


@tool(args_schema=CategoryConstraintInput)
def set_category_constraint(category: str, min_count=0, max_count=None, target_count=None, mode="hard"):
    """Đặt quy tắc đúng, tối thiểu, tối đa hoặc mục tiêu cho một nhóm hoạt động."""


@tool(args_schema=MealPreferencesInput)
def set_meal_preferences(preferences: list[str], mode="replace"):
    """Cập nhật sở thích ăn uống dùng khi planner chọn nhà hàng."""


@tool(args_schema=AddPlaceInput)
def require_place(place_id=None, query=None, day=None):
    """Thêm/bắt buộc địa điểm bằng ID hoặc tên; có thể ghim vào một ngày cụ thể."""


@tool(args_schema=PlaceIdInput)
def exclude_place(place_id: str):
    """Loại một địa điểm ID thật khỏi working request."""


@tool(args_schema=RemoveItemInput)
def remove_itinerary_item(place_id=None, query=None, day=None, position=None, item_type="attraction"):
    """Xóa mục theo ID, tên gần đúng, hoặc ngày/vị trí rồi loại nó khỏi lần lập lịch sau."""


@tool(args_schema=ReplacePlaceInput)
def replace_itinerary_item(old_place_id=None, old_query=None, new_place_id=None, new_query=None, keep_same_day=True):
    """Thay địa điểm bằng ID hoặc tên gần đúng và tùy chọn giữ cùng ngày."""


@tool(args_schema=ExclusionFiltersInput)
def set_exclusion_filters(place_types=None, activity_categories=None, mode="add"):
    """Thêm, bỏ hoặc thay danh sách loại địa điểm/nhóm hoạt động không được xuất hiện."""


@tool(args_schema=QualityPoliciesInput)
def apply_quality_policies(exclude_shop_only_attractions=True, deduplicate_brands=True):
    """Áp dụng chính sách planner: không dùng cửa hàng làm điểm chính và không lặp thương hiệu."""


@tool(args_schema=ApplyTripChangesInput)
def apply_trip_changes(**kwargs):
    """Áp dụng TOÀN BỘ yêu cầu sửa trong một lần: cài đặt, ưu tiên, thêm/xóa/thay địa điểm, loại trừ và chính sách. Phải giữ đủ mọi vế của câu người dùng."""


@tool(args_schema=MovePlaceInput)
def move_itinerary_item(place_id: str, target_day: int):
    """Ghim một địa điểm bắt buộc sang ngày đích khi lập lại lịch."""


@tool(args_schema=PlaceIdInput)
def lock_itinerary_item(place_id: str):
    """Giữ địa điểm hiện tại và ghim nó vào ngày đang có."""


@tool(args_schema=PlaceIdInput)
def unlock_itinerary_item(place_id: str):
    """Bỏ khóa ngày của địa điểm nhưng không tự xóa địa điểm đó."""


@tool(args_schema=EmptyInput)
def replan_itinerary():
    """Tạo working itinerary từ working request và tự chạy validation."""


@tool(args_schema=EmptyInput)
def validate_itinerary():
    """Kiểm tra working itinerary bằng validator deterministic."""


@tool(args_schema=EmptyInput)
def commit_itinerary():
    """Commit working itinerary đã validation thành công thành lịch hiện tại."""


@tool(args_schema=EmptyInput)
def rollback_working_changes():
    """Hủy toàn bộ thay đổi chưa commit và quay lại lịch hiện tại."""


@tool(args_schema=ClarificationInput)
def ask_user_clarification(question: str):
    """Yêu cầu người dùng làm rõ khi thiếu một quyết định bắt buộc."""


@tool(args_schema=UnsupportedRequestInput)
def report_unsupported_request(capability: str, request_summary: str):
    """Ghi nhận phần yêu cầu LLM đã hiểu nhưng MVP chưa hỗ trợ; không sửa lịch."""


@tool(args_schema=EmptyInput)
def list_user_memories():
    """Liệt kê các sở thích dài hạn mà SoulViet đang nhớ về người dùng."""


@tool(args_schema=SaveMemoryInput)
def save_user_memory(text: str, kind="preference"):
    """Lưu một sở thích ổn định mà người dùng đã nói rõ hoặc yêu cầu ghi nhớ."""


@tool(args_schema=MemoryIdInput)
def forget_user_memory(memory_id: str):
    """Xóa memory theo ID lấy từ list_user_memories."""


EXECUTOR_TOOLS = [
    get_trip_state,
    get_itinerary_summary,
    get_day_details,
    get_place_details,
    search_places,
    resolve_location_scope,
    update_trip_settings,
    set_activity_preferences,
    set_category_constraint,
    set_meal_preferences,
    require_place,
    exclude_place,
    remove_itinerary_item,
    replace_itinerary_item,
    set_exclusion_filters,
    apply_quality_policies,
    apply_trip_changes,
    move_itinerary_item,
    lock_itinerary_item,
    unlock_itinerary_item,
    replan_itinerary,
    validate_itinerary,
    commit_itinerary,
    rollback_working_changes,
    ask_user_clarification,
    report_unsupported_request,
    list_user_memories,
    save_user_memory,
    forget_user_memory,
]


AGENT_TOOLS = [
    get_trip_state,
    get_itinerary_summary,
    get_day_details,
    get_place_details,
    search_places,
    apply_trip_changes,
    ask_user_clarification,
    report_unsupported_request,
    list_user_memories,
    save_user_memory,
    forget_user_memory,
]


class SoulVietToolExecutor:
    def __init__(self, itinerary=None, memory=None):
        self.itinerary = itinerary or ItineraryService()
        self.graph = self.itinerary.graph
        self.query = GraphQueryService(self.graph)
        self.validator = ItineraryValidator()
        self.memory = memory

    @staticmethod
    def _ok(tool_name, data, summary):
        return {"ok": True, "tool": tool_name, "summary": summary, "data": data}

    @staticmethod
    def _summary(itinerary):
        return {
            "days": len(itinerary),
            "attraction_count": sum(
                place.get("item_type") != "meal"
                for day in itinerary for place in day.get("places", [])
            ),
            "total_distance_km": round(sum(
                float(day.get("total_distance_km") or 0) for day in itinerary
            ), 2),
            "estimated_spend_min": sum(
                int(day.get("estimated_spend_min") or 0) for day in itinerary
            ),
            "estimated_spend_max": sum(
                int(day.get("estimated_spend_max") or 0) for day in itinerary
            ),
        }

    @staticmethod
    def _working_request(state):
        return dict(state.get("working_request") or state["current_request"])

    @staticmethod
    def _working_constraints(state):
        draft = state.get("working_constraints")
        if draft is not None:
            return dict(draft)
        return dict(state.get("current_constraints") or {})

    def execute(self, name, args, state):
        handler = getattr(self, f"_tool_{name}", None)
        if handler is None:
            raise ValueError(f"Unknown tool: {name}")
        return handler(args, state)

    def _tool_get_trip_state(self, _args, state):
        data = {
            "current_request": state["current_request"],
            "working_request": state.get("working_request"),
            "dirty": state.get("dirty", False),
            "committed": state.get("committed", False),
            "validation_report": state.get("validation_report"),
        }
        return self._ok("get_trip_state", data, "Đã đọc trạng thái chuyến đi"), {}

    def _tool_get_itinerary_summary(self, _args, state):
        data = self._summary(state.get("current_itinerary") or [])
        return self._ok("get_itinerary_summary", data, "Đã tóm tắt lịch hiện tại"), {}

    def _tool_get_day_details(self, args, state):
        itinerary = state.get("current_itinerary") or []
        day = args["day"]
        if day > len(itinerary):
            raise ValueError(f"Itinerary does not have day {day}")
        data = itinerary[day - 1]
        return self._ok("get_day_details", data, f"Đã đọc ngày {day}"), {}

    def _tool_get_place_details(self, args, _state):
        place = self.graph.get_place(args["place_id"])
        if not place:
            raise ValueError("Unknown place ID")
        return self._ok("get_place_details", place, f"Đã đọc {place['name']}"), {}

    def _tool_search_places(self, args, state):
        request = UserRequest.model_validate(self._working_request(state))
        normalized_query = normalize_text(args["query"])
        query_terms = list(dict.fromkeys([
            normalized_query,
            *(
                token for token in normalized_query.split()
                if len(token) >= 3
            ),
        ]))[:10]
        plan = GraphQueryPlan(
            keywords=query_terms,
            types=args.get("types", []),
            activity_categories=args.get("activity_categories", []),
            minimum_rating=args.get("minimum_rating", 4),
            candidate_limit=max(5, args.get("limit", 10)),
        )
        result = self.query.search(request, plan)
        items = []
        for place_id in result["candidate_ids"][:args.get("limit", 10)]:
            place = self.graph.get_place(place_id)
            items.append({
                "id": place["id"], "name": place["name"],
                "type": place["type"], "region": place["region"],
                "rating": place["rating"],
                "activity_categories": place["activity_categories"],
            })
        return self._ok("search_places", items, f"Tìm thấy {len(items)} địa điểm"), {}

    def _tool_resolve_location_scope(self, args, _state):
        scope = ResolvedLocality.resolve_scope(
            self.graph.get_all_places(), args["query"]
        )
        region = scope.get("region")
        if region:
            regional_places = [
                place for place in self.graph.get_all_places()
                if place.get("region") == region
            ]
            locality = ResolvedLocality.resolve(
                regional_places, args["query"], "strict", 8,
                neighbor_lookup=self.graph.get_neighbors,
            )
            scoped_places = locality.filter(regional_places)
            scope["attraction_candidates"] = sum(
                self.itinerary._is_attraction(place)
                and not self.itinerary._is_food_place(place)
                and float(place.get("rating") or 0) >= 4
                for place in scoped_places
            )
            nearby = ResolvedLocality.resolve(
                regional_places, args["query"], "nearby", 8,
                neighbor_lookup=self.graph.get_neighbors,
            )
            scope["nearby_attraction_candidates"] = sum(
                self.itinerary._is_attraction(place)
                and not self.itinerary._is_food_place(place)
                and float(place.get("rating") or 0) >= 4
                for place in nearby.filter(regional_places)
            )
        else:
            scope["attraction_candidates"] = 0
            scope["nearby_attraction_candidates"] = 0
        return self._ok(
            "resolve_location_scope",
            scope,
            (
                f"Đã phân giải {args['query']} sang {region}"
                if region else f"Chưa phân giải được {args['query']}"
            ),
        ), {}

    def _tool_update_trip_settings(self, args, state):
        args = dict(args)
        values = self._working_request(state)
        old_region = values.get("region")
        old_focus = values.get("location_focus")
        old_duration = int(values.get("duration", 1))
        clear_focus = bool(args.pop("clear_location_focus", False))
        distance_is_hard = bool(
            args.pop("max_daily_distance_is_hard", False)
        )
        locality_resolution = None
        requested_focus = args.get("location_focus")
        if requested_focus and not clear_focus:
            locality_resolution = ResolvedLocality.resolve_scope(
                self.graph.get_all_places(), requested_focus
            )
            resolved_region = locality_resolution.get("region")
            explicit_region = args.get("region")
            if locality_resolution.get("ambiguous_regions"):
                choices = ", ".join(locality_resolution["ambiguous_regions"])
                raise ValueError(
                    f"Locality {requested_focus!r} is ambiguous across: {choices}"
                )
            if not resolved_region:
                raise ValueError(
                    f"Unknown locality in the place graph: {requested_focus}"
                )
            if explicit_region and explicit_region != resolved_region:
                raise ValueError(
                    f"Locality {requested_focus!r} belongs to {resolved_region}, "
                    f"not {explicit_region}"
                )
            args["region"] = resolved_region
        values.update({key: value for key, value in args.items() if value is not None})
        if clear_focus:
            values["location_focus"] = None
        locality_changed = (
            (args.get("region") and args["region"] != old_region)
            or values.get("location_focus") != old_focus
        )
        duration_changed = int(values.get("duration", old_duration)) != old_duration
        if locality_changed:
            values["required_place_ids"] = []
            values["excluded_place_ids"] = []
            values["exclusion_exception_place_ids"] = []
        request = UserRequest.model_validate(values)
        dumped = request.model_dump(mode="json")
        constraints = self._working_constraints(state)
        explicit_fields = set(constraints.get("explicit_request_fields", []))
        if "max_daily_distance_km" in args:
            if distance_is_hard:
                explicit_fields.add("max_daily_distance_km")
            else:
                explicit_fields.discard("max_daily_distance_km")
        constraints["explicit_request_fields"] = sorted(explicit_fields)
        duration = int(dumped["duration"])
        constraints["required_place_days"] = {
            place_id: day
            for place_id, day in constraints.get("required_place_days", {}).items()
            if int(day) <= duration
            and (
                not args.get("region")
                or (
                    self.graph.get_place(place_id)
                    and self.graph.get_place(place_id).get("region") == dumped["region"]
                )
            )
        }
        for field in ("meal_requests", "scoped_exclusions", "day_policies"):
            constraints[field] = [
                item for item in constraints.get(field, [])
                if int(item.get("day", 0)) <= duration
            ]
        if locality_changed:
            for field in (
                "allowed_place_ids", "candidate_priorities", "place_query",
                "place_query_metrics", "required_place_days",
                "mutation_invariants", "reorder_baseline",
            ):
                constraints.pop(field, None)
            constraints["scoped_exclusions"] = []
            constraints["day_policies"] = []
        elif duration_changed:
            constraints.pop("mutation_invariants", None)
            constraints.pop("reorder_baseline", None)
        data = dict(dumped)
        if locality_resolution:
            data["locality_resolution"] = locality_resolution
        return self._ok("update_trip_settings", data, "Đã cập nhật working request"), {
            "working_request": dumped,
            "working_constraints": constraints,
            "dirty": True,
            "committed": False,
        }

    def _tool_set_activity_preferences(self, args, state):
        values = self._working_request(state)
        current = list(values.get("preferred_activities", []))
        requested = args["activities"]
        if args.get("mode", "replace") == "replace":
            current = requested
        elif args["mode"] == "add":
            current = list(dict.fromkeys([*current, *requested]))
        else:
            removed = {item.casefold() for item in requested}
            current = [item for item in current if item.casefold() not in removed]
        values["preferred_activities"] = current
        request = UserRequest.model_validate(values)
        dumped = request.model_dump(mode="json")
        return self._ok("set_activity_preferences", current, "Đã cập nhật hoạt động ưu tiên"), {
            "working_request": dumped, "dirty": True, "committed": False,
        }

    def _tool_set_category_constraint(self, args, state):
        values = self._working_request(state)
        args = dict(args)
        explicitly_required = bool(args.pop("explicitly_required", False))
        if args.get("mode") == "hard" and not explicitly_required:
            args["mode"] = "soft"
        rule = CategoryConstraint.model_validate(args)
        rules = {
            item["category"].casefold(): item
            for item in values.get("category_constraints", [])
        }
        rules[rule.category.casefold()] = rule.model_dump(mode="json")
        values["category_constraints"] = list(rules.values())
        dumped = UserRequest.model_validate(values).model_dump(mode="json")
        return self._ok("set_category_constraint", rule.model_dump(mode="json"), "Đã cập nhật ràng buộc nhóm"), {
            "working_request": dumped, "dirty": True, "committed": False,
        }

    def _tool_set_meal_preferences(self, args, state):
        constraints = self._working_constraints(state)
        current = list(constraints.get("meal_preferences", []))
        requested = args["preferences"]
        mode = args.get("mode", "replace")
        if mode == "replace":
            current = requested
        elif mode == "add":
            current = list(dict.fromkeys([*current, *requested]))
        else:
            removed = {item.casefold() for item in requested}
            current = [item for item in current if item.casefold() not in removed]
        constraints["meal_preferences"] = current
        return self._ok("set_meal_preferences", current, "Đã cập nhật sở thích bữa ăn"), {
            "working_constraints": constraints, "dirty": True, "committed": False,
        }

    def _tool_set_meal_request(self, args, state):
        duration = int(self._working_request(state)["duration"])
        day = args.get("day")
        if day is None and args.get("day_strategy") == "most_free":
            itinerary = state.get("current_itinerary") or []
            day = min(
                range(1, duration + 1),
                key=lambda number: (
                    sum(
                        item.get("item_type", "attraction") != "meal"
                        for item in (
                            itinerary[number - 1].get("places", [])
                            if number <= len(itinerary) else []
                        )
                    ),
                    number,
                ),
            )
        if day is None:
            raise ValueError("Meal request requires a day")
        if day > duration:
            raise ValueError("Meal request day exceeds trip duration")
        args = {**args, "day": day}
        constraints = self._working_constraints(state)
        requests = list(constraints.get("meal_requests", []))
        key = (int(args["day"]), args["meal_slot"])
        requests = [
            item for item in requests
            if (int(item["day"]), item["meal_slot"]) != key
        ]
        requests.append(dict(args))
        constraints["meal_requests"] = requests
        return self._ok(
            "set_meal_request", args,
            f"Đã đặt yêu cầu {args['meal_slot']} cho ngày {args['day']}",
        ), {
            "working_constraints": constraints,
            "dirty": True,
            "committed": False,
        }

    def _tool_set_scoped_exclusion(self, args, state):
        duration = int(self._working_request(state)["duration"])
        if args["day"] > duration:
            raise ValueError("Scoped exclusion day exceeds trip duration")
        exception_ids = set(args.get("except_place_ids", []))
        for query in args.get("except_queries", []):
            exception_ids.add(
                self._resolve_place_reference(state, query=query)["id"]
            )
        constraints = self._working_constraints(state)
        filters = list(constraints.get("scoped_exclusions", []))
        new_filter = {
            "day": args["day"],
            "place_types": list(args.get("place_types", [])),
            "activity_categories": list(args.get("activity_categories", [])),
            "except_place_ids": sorted(exception_ids),
        }

        def filter_key(item):
            return (
                int(item["day"]),
                frozenset(
                    str(value).strip().casefold()
                    for value in item.get("place_types", [])
                ),
                frozenset(
                    str(value).strip().casefold()
                    for value in item.get("activity_categories", [])
                ),
            )

        new_key = filter_key(new_filter)
        filters = [
            item for item in filters if filter_key(item) != new_key
        ]
        filters.append(new_filter)
        constraints["scoped_exclusions"] = filters
        return self._ok(
            "set_scoped_exclusion", new_filter,
            f"Đã thêm bộ lọc riêng cho ngày {args['day']}",
        ), {
            "working_constraints": constraints,
            "dirty": True,
            "committed": False,
        }

    def _tool_set_optimization_policy(self, args, state):
        constraints = self._working_constraints(state)
        policy = {
            **constraints.get("optimization_policy", {}),
            **args,
        }
        values = self._working_request(state)
        current_ids = [
            item["id"]
            for day in state.get("current_itinerary") or []
            for item in day.get("places", [])
            if item.get("item_type", "attraction") != "meal"
        ]
        if policy.get("preserve_existing_places") or policy.get("reorder_only"):
            required = list(dict.fromkeys([
                *values.get("required_place_ids", []), *current_ids,
            ]))
            values["required_place_ids"] = required
        if policy.get("reorder_only"):
            constraints["allowed_place_ids"] = list(dict.fromkeys(current_ids))
            constraints["reorder_baseline"] = {
                "attraction_ids": list(current_ids),
                "total_travel_time_minutes": sum(
                    int(day.get("total_travel_time_minutes") or 0)
                    for day in state.get("current_itinerary") or []
                ),
                "routing_sources": sorted({
                    str(day.get("travel_time_source") or "unknown")
                    for day in state.get("current_itinerary") or []
                }),
            }
        constraints["optimization_policy"] = policy
        dumped = UserRequest.model_validate(values).model_dump(mode="json")
        return self._ok(
            "set_optimization_policy", policy,
            "Đã cập nhật chính sách tối ưu lịch trình",
        ), {
            "working_request": dumped,
            "working_constraints": constraints,
            "dirty": True,
            "committed": False,
        }

    def _tool_set_day_policy(self, args, state):
        duration = int(self._working_request(state)["duration"])
        day_number = int(args["day"])
        if day_number > duration:
            raise ValueError("Day policy exceeds trip duration")
        constraints = self._working_constraints(state)
        policies = {
            int(item["day"]): item
            for item in constraints.get("day_policies", [])
        }
        policies[day_number] = dict(args)
        constraints["day_policies"] = list(policies.values())

        values = self._working_request(state)
        remove_count = int(args.get("remove_count", 0))
        removed_ids = []
        itinerary = state.get("current_itinerary") or []
        if remove_count and day_number <= len(itinerary):
            explicitly_anchored = set(
                constraints.get("required_place_days", {})
            )
            items = [
                item for item in itinerary[day_number - 1].get("places", [])
                if item.get("item_type", "attraction") != "meal"
                and item.get("id") not in explicitly_anchored
            ]
            strategy = args.get("remove_strategy", "least_important")
            if strategy == "last":
                ranked = list(reversed(items))
            elif strategy == "farthest":
                ranked = sorted(
                    items,
                    key=lambda item: float(item.get("distance_from_previous_km") or 0),
                    reverse=True,
                )
            else:
                request = UserRequest.model_validate(values)
                ranked = sorted(items, key=lambda item: (
                    self.graph.score_place(
                        self.graph.get_place(item["id"]) or item, request
                    )["total"],
                    float(item.get("rating") or 0),
                    int(item.get("review_count") or 0),
                ))
            removed_ids = [item["id"] for item in ranked[:remove_count]]
            excluded = set(values.get("excluded_place_ids", []))
            excluded.update(removed_ids)
            values["excluded_place_ids"] = sorted(excluded)
            values["required_place_ids"] = [
                place_id
                for place_id in values.get("required_place_ids", [])
                if place_id not in set(removed_ids)
            ]
        dumped = UserRequest.model_validate(values).model_dump(mode="json")
        return self._ok(
            "set_day_policy",
            {"policy": dict(args), "removed_place_ids": removed_ids},
            f"Đã cập nhật mật độ ngày {day_number}",
        ), {
            "working_request": dumped,
            "working_constraints": constraints,
            "dirty": True,
            "committed": False,
        }

    def _change_place_constraint(self, state, place_id, required):
        place = self.graph.get_place(place_id)
        if not place:
            raise ValueError("Unknown place ID; call search_places first")
        values = self._working_request(state)
        required_ids = set(values.get("required_place_ids", []))
        excluded_ids = set(values.get("excluded_place_ids", []))
        exception_ids = set(values.get("exclusion_exception_place_ids", []))
        if required:
            required_ids.add(place_id)
            excluded_ids.discard(place_id)
            current_types = place_types(place)
            current_categories = place_categories(place)
            if (
                current_types & {
                    str(value).strip().casefold()
                    for value in values.get("excluded_place_types", [])
                }
                or current_categories & {
                    str(value).strip().casefold()
                    for value in values.get(
                        "excluded_activity_categories", []
                    )
                }
            ):
                exception_ids.add(place_id)
        else:
            excluded_ids.add(place_id)
            required_ids.discard(place_id)
            exception_ids.discard(place_id)
        values.update({
            "required_place_ids": sorted(required_ids),
            "excluded_place_ids": sorted(excluded_ids),
            "exclusion_exception_place_ids": sorted(exception_ids),
        })
        dumped = UserRequest.model_validate(values).model_dump(mode="json")
        return place, dumped

    def _resolve_place_reference(
        self, state, place_id=None, query=None, target_day=None,
    ):
        if place_id:
            place = self.graph.get_place(place_id)
            if not place:
                raise ValueError("Unknown place ID")
            if query:
                requested = normalize_text(query)
                actual = normalize_text(place.get("name"))
                if requested not in actual and actual not in requested:
                    raise ValueError(
                        "The supplied place ID does not match the requested name"
                    )
            return place
        if not query:
            raise ValueError("A place ID or query is required")

        request = UserRequest.model_validate(self._working_request(state))
        normalized = normalize_text(query)
        regional = [
            place for place in self.graph.get_all_places()
            if place.get("region") == request.region
        ]
        exact = [
            place for place in regional
            if normalize_text(place.get("name")) == normalized
        ]
        contained = [
            place for place in regional
            if normalized and normalized in normalize_text(place.get("name"))
        ]
        matches = exact or contained
        if not matches:
            terms = list(dict.fromkeys([
                normalized,
                *(part for part in normalized.split() if len(part) >= 3),
            ]))[:10]
            plan = GraphQueryPlan(
                keywords=terms,
                minimum_rating=0,
                candidate_limit=10,
            )
            result = self.query.search(request, plan)
            if result.get("semantic_match_count", 0):
                matches = [
                    self.graph.get_place(candidate_id)
                    for candidate_id in result["candidate_ids"]
                    if self.graph.get_place(candidate_id)
                ]
        if not matches:
            raise ValueError(f"No place matched query: {query}")
        current_ids = {
            item.get("id")
            for day in state.get("current_itinerary") or []
            for item in day.get("places", [])
        }
        target_places = []
        if target_day is not None:
            itinerary = state.get("current_itinerary") or []
            if 1 <= int(target_day) <= len(itinerary):
                target_places = itinerary[int(target_day) - 1].get("places", [])

        def route_distance(place):
            return min((
                haversine(
                    float(place.get("lat") or 0),
                    float(place.get("lng") or 0),
                    float(item.get("lat") or 0),
                    float(item.get("lng") or 0),
                )
                for item in target_places
                if item.get("lat") is not None and item.get("lng") is not None
            ), default=float("inf"))

        matches.sort(key=lambda place: (
            -int(normalize_text(place.get("name")) == normalized),
            -int(place.get("id") in current_ids),
            route_distance(place),
            -float(place.get("rating") or 0),
            -int(place.get("review_count") or 0),
        ))
        return matches[0]

    def _tool_require_place(self, args, state):
        day = args.get("day")
        if day is None and args.get("day_strategy") == "most_free":
            itinerary = state.get("current_itinerary") or []
            if itinerary:
                day = min(
                    range(1, len(itinerary) + 1),
                    key=lambda number: (
                        sum(
                            item.get("item_type", "attraction") != "meal"
                            for item in itinerary[number - 1].get("places", [])
                        ),
                        float(
                            itinerary[number - 1].get(
                                "total_travel_time_minutes", 0
                            ) or 0
                        ),
                    ),
                )
        place = self._resolve_place_reference(
            state,
            args.get("place_id"),
            args.get("query"),
            target_day=day,
        )
        place, dumped = self._change_place_constraint(state, place["id"], True)
        updates = {
            "working_request": dumped, "dirty": True, "committed": False,
        }
        constraints = self._working_constraints(state)
        if "allowed_place_ids" in constraints:
            allowed = list(constraints.get("allowed_place_ids", []))
            constraints["allowed_place_ids"] = list(dict.fromkeys([
                *allowed, place["id"],
            ]))
            priorities = dict(constraints.get("candidate_priorities", {}))
            priorities[place["id"]] = max(
                1000, int(priorities.get(place["id"], 0))
            )
            constraints["candidate_priorities"] = priorities
            updates["working_constraints"] = constraints
        if day is not None:
            if day > int(dumped["duration"]):
                raise ValueError("Target day exceeds trip duration")
            anchors = dict(constraints.get("required_place_days", {}))
            anchors[place["id"]] = day
            constraints["required_place_days"] = anchors
            updates["working_constraints"] = constraints
        return self._ok("require_place", {"id": place["id"], "name": place["name"]}, f"Đã bắt buộc {place['name']}"), {
            **updates,
        }

    def _tool_exclude_place(self, args, state):
        place, dumped = self._change_place_constraint(state, args["place_id"], False)
        constraints = self._working_constraints(state)
        anchors = dict(constraints.get("required_place_days", {}))
        anchors.pop(place["id"], None)
        constraints["required_place_days"] = anchors
        if "allowed_place_ids" in constraints:
            constraints["allowed_place_ids"] = [
                place_id for place_id in constraints["allowed_place_ids"]
                if place_id != place["id"]
            ]
        return self._ok("exclude_place", {"id": place["id"], "name": place["name"]}, f"Đã loại {place['name']}"), {
            "working_request": dumped,
            "working_constraints": constraints,
            "dirty": True,
            "committed": False,
        }

    def _tool_remove_itinerary_item(self, args, state):
        place_id = args.get("place_id")
        if not place_id and args.get("query"):
            place_id = self._resolve_place_reference(
                state, query=args["query"]
            )["id"]
        if not place_id:
            itinerary = state.get("current_itinerary") or []
            day = args["day"]
            if day > len(itinerary):
                raise ValueError(f"Itinerary does not have day {day}")
            items = itinerary[day - 1].get("places", [])
            item_type = args.get("item_type", "attraction")
            if item_type != "any":
                items = [item for item in items if (
                    item.get("item_type", "attraction") == item_type
                )]
            relative_position = args.get("relative_position")
            if relative_position == "first":
                position = 1
            elif relative_position == "last":
                position = len(items)
            else:
                position = args["position"]
            if position < 1 or position > len(items):
                raise ValueError("Position is outside the selected day")
            place_id = items[position - 1]["id"]
        return self._tool_exclude_place({"place_id": place_id}, state)

    @staticmethod
    def _day_for_place(state, place_id):
        for index, day in enumerate(state.get("current_itinerary") or [], start=1):
            if any(item.get("id") == place_id for item in day.get("places", [])):
                return index
        return None

    def _tool_replace_itinerary_item(self, args, state):
        old_place = self._resolve_place_reference(
            state, args.get("old_place_id"), args.get("old_query")
        )
        new_place = self._resolve_place_reference(
            state, args.get("new_place_id"), args.get("new_query")
        )
        _, values = self._change_place_constraint(state, old_place["id"], False)
        intermediate = {**state, "working_request": values}
        _, values = self._change_place_constraint(intermediate, new_place["id"], True)
        constraints = self._working_constraints(state)
        if "allowed_place_ids" in constraints:
            constraints["allowed_place_ids"] = list(dict.fromkeys([
                *(
                    place_id
                    for place_id in constraints["allowed_place_ids"]
                    if place_id != old_place["id"]
                ),
                new_place["id"],
            ]))
        updates = {
            "working_request": values,
            "working_constraints": constraints,
            "dirty": True,
            "committed": False,
        }
        if args.get("keep_same_day", True):
            day = self._day_for_place(state, old_place["id"])
            if day:
                anchors = dict(constraints.get("required_place_days", {}))
                anchors[new_place["id"]] = day
                anchors.pop(old_place["id"], None)
                constraints["required_place_days"] = anchors
                updates["working_constraints"] = constraints
        return self._ok("replace_itinerary_item", {
            "removed": old_place["name"], "required": new_place["name"],
        }, f"Đã chuẩn bị thay {old_place['name']} bằng {new_place['name']}"), updates

    def _tool_move_place_reference(self, args, state):
        place = self._resolve_place_reference(
            state, query=args["query"], target_day=args["target_day"]
        )
        return self._tool_move_itinerary_item({
            "place_id": place["id"],
            "target_day": args["target_day"],
        }, state)

    def _tool_set_exclusion_filters(self, args, state):
        values = self._working_request(state)
        mode = args.get("mode", "add")

        def merge(field, requested):
            current = list(values.get(field, []))
            if mode == "replace":
                return list(dict.fromkeys(requested))
            if mode == "add":
                return list(dict.fromkeys([*current, *requested]))
            removed = {item.casefold() for item in requested}
            return [item for item in current if item.casefold() not in removed]

        values["excluded_place_types"] = merge(
            "excluded_place_types", args.get("place_types", [])
        )
        values["excluded_activity_categories"] = merge(
            "excluded_activity_categories",
            args.get("activity_categories", []),
        )
        newly_excluded_types = {
            str(value).strip().casefold()
            for value in args.get("place_types", [])
        }
        newly_excluded_categories = {
            str(value).strip().casefold()
            for value in args.get("activity_categories", [])
        }
        values["exclusion_exception_place_ids"] = [
            place_id
            for place_id in values.get("exclusion_exception_place_ids", [])
            if not (
                self.graph.get_place(place_id)
                and (
                    newly_excluded_types
                    & place_types(self.graph.get_place(place_id))
                    or newly_excluded_categories
                    & place_categories(self.graph.get_place(place_id))
                )
            )
        ]
        dumped = UserRequest.model_validate(values).model_dump(mode="json")
        data = {
            "excluded_place_types": dumped["excluded_place_types"],
            "excluded_activity_categories": dumped[
                "excluded_activity_categories"
            ],
        }
        return self._ok(
            "set_exclusion_filters", data, "Đã cập nhật bộ lọc loại trừ"
        ), {
            "working_request": dumped,
            "dirty": True,
            "committed": False,
        }

    def _tool_apply_quality_policies(self, args, state):
        constraints = self._working_constraints(state)
        policies = dict(constraints.get("quality_policies", {}))
        policies.update({
            "exclude_shop_only_attractions": args.get(
                "exclude_shop_only_attractions", True
            ),
            "deduplicate_brands": args.get("deduplicate_brands", True),
        })
        constraints["quality_policies"] = policies
        return self._ok(
            "apply_quality_policies",
            policies,
            "Đã áp dụng chính sách chất lượng planner",
        ), {
            "working_constraints": constraints,
            "dirty": True,
            "committed": False,
        }

    def _enforce_mutation_semantics(self, args, original_state, state):
        """Turn edit commands into explicit postconditions over the current plan."""
        itinerary = original_state.get("current_itinerary") or []
        if not itinerary:
            return {}

        original_request = original_state.get("current_request") or {}
        values = self._working_request(state)
        trip_shape_changed = any(
            values.get(field) != original_request.get(field)
            for field in ("duration", "region", "location_focus")
        )
        if trip_shape_changed:
            return {}

        item_patch = bool(
            args.get("add_places")
            or args.get("remove_places")
            or args.get("replacements")
            or args.get("move_places")
        )
        day_reduction = any(
            int(policy.get("remove_count", 0)) > 0
            for policy in args.get("day_policies", [])
        )
        policy = args.get("optimization_policy") or {}
        exclusion_patch = bool(
            args.get("excluded_place_types")
            or args.get("excluded_activity_categories")
            or args.get("scoped_exclusions")
        )
        preserve = bool(
            item_patch
            or day_reduction
            or exclusion_patch
            or policy.get("preserve_existing_places")
            or policy.get("reorder_only")
        )
        if not preserve:
            return {}

        baseline_ids = []
        original_days = {}
        for day_number, day in enumerate(itinerary, start=1):
            for item in day.get("places", []):
                if item.get("item_type", "attraction") == "meal":
                    continue
                place_id = item.get("id")
                if place_id and place_id not in original_days:
                    baseline_ids.append(place_id)
                    original_days[place_id] = day_number

        request = UserRequest.model_validate(values)
        globally_eligible = {
            place["id"] for place in self.graph.filter_places(request)
        }
        constraints = self._working_constraints(state)
        scoped_forbidden = set()
        for scoped in constraints.get("scoped_exclusions", []):
            day_number = int(scoped["day"])
            exceptions = set(scoped.get("except_place_ids", []))
            excluded_types = {
                str(value).strip().casefold()
                for value in scoped.get("place_types", [])
            }
            excluded_categories = {
                str(value).strip().casefold()
                for value in scoped.get("activity_categories", [])
            }
            for place_id, original_day in original_days.items():
                if original_day != day_number or place_id in exceptions:
                    continue
                place = self.graph.get_place(place_id)
                if place and (
                    excluded_types & place_types(place)
                    or excluded_categories & place_categories(place)
                ):
                    scoped_forbidden.add(place_id)

        preserved_ids = [
            place_id
            for place_id in baseline_ids
            if place_id in globally_eligible
            and place_id not in scoped_forbidden
        ]
        added_ids = [
            place_id
            for place_id in values.get("required_place_ids", [])
            if place_id not in baseline_ids
            and place_id in globally_eligible
        ]
        required_ids = list(dict.fromkeys([*preserved_ids, *added_ids]))
        values["required_place_ids"] = required_ids

        exact_patch = bool(
            item_patch
            or day_reduction
            or policy.get("reorder_only")
        )
        if exact_patch:
            constraints["allowed_place_ids"] = list(required_ids)
        elif "allowed_place_ids" in constraints:
            constraints["allowed_place_ids"] = list(dict.fromkeys([
                *preserved_ids,
                *added_ids,
                *(
                    place_id
                    for place_id in constraints.get("allowed_place_ids", [])
                    if place_id in globally_eligible
                    and place_id not in scoped_forbidden
                ),
            ]))

        preserve_days = bool(
            (args.get("remove_places") or args.get("replacements"))
            and not args.get("add_places")
        ) or day_reduction or bool(
            policy.get("reorder_only")
        ) or exclusion_patch
        anchors = dict(constraints.get("required_place_days", {}))
        if preserve_days:
            baseline_anchors = {
                place_id: original_days[place_id]
                for place_id in preserved_ids
            }
            # Explicit ADD/REPLACE/MOVE anchors win over baseline day placement.
            anchors = {**baseline_anchors, **anchors}
        constraints["required_place_days"] = {
            place_id: day
            for place_id, day in anchors.items()
            if place_id in required_ids
        }

        expected_absent = sorted(set(baseline_ids) - set(preserved_ids))
        constraints["mutation_invariants"] = {
            "baseline_ids": baseline_ids,
            "preserved_ids": preserved_ids,
            "added_ids": added_ids,
            "expected_absent_ids": expected_absent,
            "exact_result_ids": required_ids if exact_patch else [],
            "original_days": original_days,
            "preserve_days": preserve_days,
        }
        dumped = UserRequest.model_validate(values).model_dump(mode="json")
        return {
            "working_request": dumped,
            "working_constraints": constraints,
            "dirty": True,
            "committed": False,
        }

    def _tool_apply_trip_changes(self, args, state):
        local_state = dict(state)
        updates = {}
        applied = []

        # Mutation invariants describe one transaction, not a permanent user
        # preference. Clear them before interpreting the next command.
        starting_constraints = self._working_constraints(local_state)
        starting_constraints.pop("mutation_invariants", None)
        starting_constraints.pop("reorder_baseline", None)
        if not args.get("optimization_policy"):
            previous_policy = dict(
                starting_constraints.get("optimization_policy", {})
            )
            previous_policy.update({
                "preserve_existing_places": False,
                "reorder_only": False,
            })
            starting_constraints["optimization_policy"] = previous_policy
        local_state["working_constraints"] = starting_constraints
        updates["working_constraints"] = starting_constraints

        def run(tool_name, tool_args):
            observation, tool_updates = self.execute(
                tool_name, tool_args, local_state
            )
            local_state.update(tool_updates)
            updates.update(tool_updates)
            applied.append({
                "tool": tool_name,
                "summary": observation.get("summary"),
                "data": observation.get("data"),
            })

        if args.get("trip_settings"):
            run("update_trip_settings", args["trip_settings"])
        if args.get("activity_preferences"):
            run("set_activity_preferences", args["activity_preferences"])
        for constraint in args.get("category_constraints", []):
            run("set_category_constraint", constraint)
        if args.get("optimization_policy"):
            run("set_optimization_policy", args["optimization_policy"])
        excluded_types = args.get("excluded_place_types", [])
        excluded_categories = args.get("excluded_activity_categories", [])
        if excluded_types or excluded_categories:
            run("set_exclusion_filters", {
                "place_types": excluded_types,
                "activity_categories": excluded_categories,
                "mode": "add",
            })
        for scoped_filter in args.get("scoped_exclusions", []):
            run("set_scoped_exclusion", scoped_filter)
        for place in args.get("add_places", []):
            run("require_place", place)
        for place in args.get("remove_places", []):
            run("remove_itinerary_item", place)
        for replacement in args.get("replacements", []):
            run("replace_itinerary_item", replacement)
        for move in args.get("move_places", []):
            run("move_place_reference", move)
        for policy in args.get("day_policies", []):
            run("set_day_policy", policy)
        if args.get("quality_policies"):
            run("apply_quality_policies", args["quality_policies"])
        if args.get("place_query"):
            request = UserRequest.model_validate(
                self._working_request(local_state)
            )
            plan = GraphQueryPlan.model_validate(args["place_query"])
            result = self.query.search(request, plan)
            constraints = self._working_constraints(local_state)
            constraints.update({
                "allowed_place_ids": result["candidate_ids"],
                "candidate_priorities": result["priorities"],
                "place_query": plan.model_dump(mode="json"),
                "place_query_metrics": {
                    "candidate_count": result["candidate_count"],
                    "semantic_match_count": result["semantic_match_count"],
                    "match_mode": plan.match_mode,
                },
            })
            query_update = {
                "working_constraints": constraints,
                "dirty": True,
                "committed": False,
            }
            local_state.update(query_update)
            updates.update(query_update)
            applied.append({
                "tool": "query_place_candidates",
                "summary": (
                    f"Đã chọn {result['candidate_count']} ứng viên từ graph "
                    f"({result['semantic_match_count']} khớp ngữ nghĩa)"
                ),
                "data": result,
            })
        mutation_updates = self._enforce_mutation_semantics(
            args, state, local_state
        )
        if mutation_updates:
            local_state.update(mutation_updates)
            updates.update(mutation_updates)
            applied.append({
                "tool": "enforce_mutation_invariants",
                "summary": "Đã khóa các địa điểm không liên quan đến thao tác sửa",
                "data": mutation_updates["working_constraints"].get(
                    "mutation_invariants", {}
                ),
            })
        return self._ok(
            "apply_trip_changes",
            {"applied": applied, "count": len(applied)},
            f"Đã áp dụng {len(applied)} nhóm thay đổi vào bản nháp",
        ), updates

    def _tool_move_itinerary_item(self, args, state):
        if args["target_day"] > int(self._working_request(state)["duration"]):
            raise ValueError("Target day exceeds trip duration")
        place, values = self._change_place_constraint(state, args["place_id"], True)
        constraints = self._working_constraints(state)
        anchors = dict(constraints.get("required_place_days", {}))
        anchors[place["id"]] = args["target_day"]
        constraints["required_place_days"] = anchors
        return self._ok("move_itinerary_item", {
            "id": place["id"], "name": place["name"], "day": args["target_day"],
        }, f"Đã ghim {place['name']} vào ngày {args['target_day']}"), {
            "working_request": values, "working_constraints": constraints,
            "dirty": True, "committed": False,
        }

    def _tool_lock_itinerary_item(self, args, state):
        day = self._day_for_place(state, args["place_id"])
        if day is None:
            raise ValueError("Place is not in the current itinerary")
        return self._tool_move_itinerary_item({
            "place_id": args["place_id"], "target_day": day,
        }, state)

    def _tool_unlock_itinerary_item(self, args, state):
        constraints = self._working_constraints(state)
        anchors = dict(constraints.get("required_place_days", {}))
        anchors.pop(args["place_id"], None)
        constraints["required_place_days"] = anchors
        return self._ok("unlock_itinerary_item", {"id": args["place_id"]}, "Đã bỏ khóa ngày"), {
            "working_constraints": constraints, "dirty": True, "committed": False,
        }

    def _tool_replan_itinerary(self, _args, state):
        request = UserRequest.model_validate(self._working_request(state))
        constraints = self._working_constraints(state)
        # Meal planning is outside the current tourist-attractions-only MVP.
        # Drop values persisted by older sessions so they cannot leak into a
        # newly generated itinerary after the public tool schema changed.
        constraints.pop("meal_preferences", None)
        constraints.pop("meal_requests", None)
        if (
            constraints.get("required_place_days")
            and "max_daily_distance_km"
            not in set(constraints.get("explicit_request_fields", []))
        ):
            required_by_day = {}
            for place_id, day in constraints["required_place_days"].items():
                place = self.graph.get_place(place_id)
                if place:
                    required_by_day.setdefault(int(day), []).append(place)
            required_span = max((
                haversine(
                    first["lat"], first["lng"], second["lat"], second["lng"]
                )
                for places in required_by_day.values()
                for index, first in enumerate(places)
                for second in places[index + 1:]
            ), default=0.0)
            effective_distance = min(
                100.0,
                max(
                    float(request.max_daily_distance_km),
                    # Road routes around mountains/coast can be materially
                    # longer than straight-line distance.
                    math.ceil(required_span * 2.0),
                ),
            )
            if effective_distance > request.max_daily_distance_km:
                values = request.model_dump(mode="json")
                values["max_daily_distance_km"] = effective_distance
                request = UserRequest.model_validate(values)
                constraints["operational_adjustments"] = {
                    "max_daily_distance_km": effective_distance,
                    "reason": "explicit_place_day_anchor",
                }
        filtered = self.graph.filter_places(request)
        attraction_candidate_count = sum(
            self.itinerary._is_attraction(place)
            and not self.itinerary._is_food_place(place)
            for place in filtered
        )
        itinerary = self.itinerary.build(
            request,
            candidate_ids=constraints.get("allowed_place_ids"),
            candidate_priorities=constraints.get("candidate_priorities"),
            required_place_days=constraints.get("required_place_days", {}),
            scoped_exclusions=constraints.get("scoped_exclusions", []),
            day_policies=constraints.get("day_policies", []),
            optimization_policy=constraints.get("optimization_policy", {}),
        )
        report = self._validate_with_constraints(itinerary, request, constraints)
        report["metrics"].update({
            "preflight_attraction_candidates": attraction_candidate_count,
            "preflight_required_nonempty_days": request.duration,
        })
        if attraction_candidate_count < request.duration:
            report["quality_violations"] = sorted(set([
                *report["quality_violations"],
                "insufficient_candidates_for_days",
            ]))
            report["acceptable"] = False
            report["status"] = (
                "infeasible" if attraction_candidate_count == 0 else "partial"
            )
        summary = self._summary(itinerary)
        summary["validation_status"] = report["status"]
        return self._ok("replan_itinerary", summary, "Đã lập và kiểm tra bản nháp"), {
            "working_request": request.model_dump(mode="json"),
            "working_constraints": constraints,
            "working_itinerary": itinerary,
            "validation_report": report,
            "dirty": True,
            "committed": False,
        }

    def _tool_validate_itinerary(self, _args, state):
        itinerary = state.get("working_itinerary")
        if itinerary is None:
            raise ValueError("No working itinerary; call replan_itinerary first")
        request = UserRequest.model_validate(self._working_request(state))
        report = self._validate_with_constraints(
            itinerary, request, self._working_constraints(state)
        )
        return self._ok("validate_itinerary", report, f"Validation: {report['status']}"), {
            "validation_report": report,
        }

    def _tool_commit_itinerary(self, _args, state):
        report = state.get("validation_report") or {}
        if not report.get("acceptable"):
            raise ValueError(
                "Working itinerary is not acceptable and cannot be committed"
            )
        if state.get("working_itinerary") is None:
            raise ValueError("No working itinerary to commit")
        request = self._working_request(state)
        itinerary = state["working_itinerary"]
        return self._ok("commit_itinerary", self._summary(itinerary), "Đã commit lịch hợp lệ"), {
            "current_request": request,
            "current_itinerary": itinerary,
            "working_request": None,
            "working_itinerary": None,
            "current_constraints": self._working_constraints(state),
            "working_constraints": None,
            "dirty": False,
            "committed": True,
        }

    def _tool_rollback_working_changes(self, _args, _state):
        return self._ok("rollback_working_changes", {}, "Đã hủy thay đổi chưa commit"), {
            "working_request": None,
            "working_itinerary": None,
            "working_constraints": None,
            "validation_report": None,
            "dirty": False,
            "committed": False,
        }

    def _tool_ask_user_clarification(self, args, _state):
        return self._ok(
            "ask_user_clarification",
            {"question": args["question"], "requires_input": True},
            "Hãy hỏi đúng câu clarification này rồi kết thúc lượt",
        ), {}

    def _tool_report_unsupported_request(self, args, state):
        item = {
            "capability": "meal_planning",
            "request_summary": args["request_summary"],
            "reason": "MVP hiện chỉ có dữ liệu điểm tham quan",
            "applied": False,
        }
        existing = list(state.get("unsupported_requests") or [])
        if not any(
            value.get("capability") == item["capability"]
            and value.get("request_summary") == item["request_summary"]
            for value in existing
        ):
            existing.append(item)
        return self._ok(
            "report_unsupported_request",
            item,
            "Đã ghi nhận phần yêu cầu ăn uống chưa được hỗ trợ",
        ), {"unsupported_requests": existing}

    def _validate_with_constraints(self, itinerary, request, constraints):
        report = self.validator.validate(itinerary, request, self.graph)
        unmet = []
        for place_id, requested_day in constraints.get(
            "required_place_days", {}
        ).items():
            day_index = int(requested_day) - 1
            present = (
                0 <= day_index < len(itinerary)
                and any(
                    item.get("id") == place_id
                    for item in itinerary[day_index].get("places", [])
                )
            )
            if not present:
                unmet.append({"place_id": place_id, "day": requested_day})
        if unmet:
            report["quality_violations"].append("required_place_day_unmet")
        report["metrics"]["unmet_place_day_anchors"] = unmet

        scoped_violations = []
        for scoped_filter in constraints.get("scoped_exclusions", []):
            day = int(scoped_filter["day"])
            if day < 1 or day > len(itinerary):
                scoped_violations.append(f"day_{day}:missing")
                continue
            exception_ids = set(scoped_filter.get("except_place_ids", []))
            excluded_types = {
                str(value).strip().casefold()
                for value in scoped_filter.get("place_types", [])
            }
            excluded_categories = {
                str(value).strip().casefold()
                for value in scoped_filter.get("activity_categories", [])
            }
            for item in itinerary[day - 1].get("places", []):
                if (
                    item.get("item_type", "attraction") == "meal"
                    or item.get("id") in exception_ids
                ):
                    continue
                if (
                    excluded_types & place_types(item)
                    or excluded_categories & place_categories(item)
                ):
                    scoped_violations.append(
                        f"day_{day}:excluded_place:{item.get('id')}"
                    )
        if scoped_violations:
            report["quality_violations"].append("scoped_exclusions_unmet")
        report["metrics"]["scoped_exclusion_violations"] = sorted(
            set(scoped_violations)
        )

        unmet_meals = []
        for meal_request in constraints.get("meal_requests", []):
            if not meal_request.get("required", True):
                continue
            day = int(meal_request["day"])
            meals = (
                itinerary[day - 1].get("places", [])
                if 1 <= day <= len(itinerary) else []
            )
            matches = [
                item for item in meals
                if item.get("item_type") == "meal"
                and item.get("meal_slot") == meal_request["meal_slot"]
                and self.itinerary._meal_preference_score(
                    item, meal_request.get("preferences", [])
                ) > 0
            ]
            if not matches:
                unmet_meals.append({
                    "day": day,
                    "meal_slot": meal_request["meal_slot"],
                    "preferences": meal_request.get("preferences", []),
                })
        if unmet_meals:
            report["quality_violations"].append("required_meal_unmet")
        report["metrics"]["unmet_meal_requests"] = unmet_meals

        day_policy_violations = []
        for policy in constraints.get("day_policies", []):
            day = int(policy["day"])
            if not policy.get("max_places") or not (1 <= day <= len(itinerary)):
                continue
            attraction_count = sum(
                item.get("item_type", "attraction") != "meal"
                for item in itinerary[day - 1].get("places", [])
            )
            if attraction_count > int(policy["max_places"]):
                day_policy_violations.append(f"day_{day}:place_limit")
        if day_policy_violations:
            report["quality_violations"].append("day_policy_unmet")
        report["metrics"]["day_policy_violations"] = day_policy_violations

        allowed_ids = set(constraints.get("allowed_place_ids", []))
        unexpected_ids = []
        if allowed_ids:
            unexpected_ids = sorted({
                item["id"]
                for day in itinerary
                for item in day.get("places", [])
                if item.get("item_type", "attraction") != "meal"
                and item["id"] not in allowed_ids
            })
        if unexpected_ids:
            report["quality_violations"].append("reorder_only_added_places")
        report["metrics"]["unexpected_place_ids"] = unexpected_ids

        baseline = constraints.get("reorder_baseline")
        if baseline and constraints.get("optimization_policy", {}).get("reorder_only"):
            result_ids = [
                item["id"]
                for day in itinerary
                for item in day.get("places", [])
                if item.get("item_type", "attraction") != "meal"
            ]
            if sorted(result_ids) != sorted(baseline.get("attraction_ids", [])):
                report["quality_violations"].append("reorder_only_changed_places")
            result_minutes = sum(
                int(day.get("total_travel_time_minutes") or 0)
                for day in itinerary
            )
            baseline_minutes = int(baseline.get("total_travel_time_minutes") or 0)
            comparable = all(
                day.get("travel_time_source") not in {None, "haversine_fallback"}
                for day in itinerary
            ) and "haversine_fallback" not in baseline.get("routing_sources", [])
            report["metrics"].update({
                "reorder_baseline_travel_minutes": baseline_minutes,
                "reorder_result_travel_minutes": result_minutes,
                "reorder_travel_metric_comparable": comparable,
            })
            if comparable and result_minutes > baseline_minutes:
                report["quality_violations"].append("reorder_only_route_regression")

        invariants = constraints.get("mutation_invariants") or {}
        result_ids = {
            item["id"]
            for day in itinerary
            for item in day.get("places", [])
            if item.get("item_type", "attraction") != "meal"
        }
        missing_preserved = sorted(
            set(invariants.get("preserved_ids", [])) - result_ids
        )
        unexpectedly_present = sorted(
            set(invariants.get("expected_absent_ids", [])) & result_ids
        )
        exact_ids = set(invariants.get("exact_result_ids", []))
        exact_mismatch = bool(exact_ids and result_ids != exact_ids)
        if missing_preserved:
            report["quality_violations"].append(
                "mutation_preservation_unmet"
            )
        if unexpectedly_present:
            report["quality_violations"].append(
                "mutation_removal_unmet"
            )
        if exact_mismatch:
            report["quality_violations"].append(
                "mutation_exact_set_unmet"
            )
        report["metrics"]["mutation_invariants"] = {
            "missing_preserved_ids": missing_preserved,
            "unexpectedly_present_ids": unexpectedly_present,
            "exact_set_mismatch": exact_mismatch,
        }

        report["quality_violations"] = sorted(set(
            report["quality_violations"]
        ))
        if report["quality_violations"]:
            report["acceptable"] = False
            if report["valid"] and report["status"] == "success":
                report["status"] = "partial"
        return report

    def _tool_list_user_memories(self, _args, state):
        items = self.memory.list(state["user_id"]) if self.memory else []
        return self._ok("list_user_memories", items, f"Có {len(items)} memory"), {}

    def _tool_save_user_memory(self, args, state):
        if not self.memory:
            raise ValueError("Memory store is unavailable")
        item = self.memory.save(state["user_id"], args["text"], args.get("kind", "preference"))
        return self._ok("save_user_memory", item, "Đã lưu sở thích dài hạn"), {}

    def _tool_forget_user_memory(self, args, state):
        if not self.memory:
            raise ValueError("Memory store is unavailable")
        self.memory.forget(state["user_id"], args["memory_id"])
        return self._ok("forget_user_memory", {"id": args["memory_id"]}, "Đã xóa memory"), {}


def observation_json(value):
    return json.dumps(value, ensure_ascii=False, default=str)
