from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from types import MappingProxyType
from typing import Literal
from uuid import UUID

IR_SCHEMA_VERSION = "1.0.0"


def _immutable_mapping(values: Mapping[str, str]) -> Mapping[str, str]:
    return MappingProxyType(dict(values))


@dataclass(frozen=True)
class ExternalPlaceId:
    scheme: str
    value: str

    def __post_init__(self) -> None:
        if not self.scheme or not self.value:
            raise ValueError("external place ID scheme and value must be non-empty")


@dataclass(frozen=True)
class GeoPoint:
    latitude_e7: int
    longitude_e7: int
    crs: Literal["EPSG:4326"] = "EPSG:4326"

    def __post_init__(self) -> None:
        if not -900_000_000 <= self.latitude_e7 <= 900_000_000:
            raise ValueError("latitude_e7 is outside EPSG:4326 bounds")
        if not -1_800_000_000 <= self.longitude_e7 <= 1_800_000_000:
            raise ValueError("longitude_e7 is outside EPSG:4326 bounds")


@dataclass(frozen=True)
class OpeningWindow:
    start_minute: int
    end_minute: int
    ends_next_day: bool = False

    def __post_init__(self) -> None:
        if not 0 <= self.start_minute <= 1439:
            raise ValueError("start_minute must be between 0 and 1439")
        if not 0 <= self.end_minute <= 1440:
            raise ValueError("end_minute must be between 0 and 1440")
        if self.ends_next_day:
            if self.end_minute > self.start_minute:
                raise ValueError("overnight windows must end at or before their start minute")
        elif self.start_minute >= self.end_minute:
            raise ValueError("ordinary windows must start before they end")


OpeningDayStatus = Literal["unknown", "closed", "open"]


@dataclass(frozen=True)
class OpeningDay:
    iso_weekday: int
    status: OpeningDayStatus
    windows: tuple[OpeningWindow, ...] = ()

    def __post_init__(self) -> None:
        if not 1 <= self.iso_weekday <= 7:
            raise ValueError("iso_weekday must be between 1 and 7")
        if self.status == "open" and not self.windows:
            raise ValueError("open days require at least one window")
        if self.status != "open" and self.windows:
            raise ValueError("unknown and closed days cannot contain windows")
        previous: OpeningWindow | None = None
        for window in self.windows:
            if previous is not None and window.start_minute < previous.start_minute:
                raise ValueError("opening windows must be ordered")
            if (
                previous is not None
                and not previous.ends_next_day
                and previous.end_minute > window.start_minute
            ):
                raise ValueError("opening windows must not overlap")
            previous = window


@dataclass(frozen=True)
class OpeningSchedule:
    days: tuple[OpeningDay, ...]
    timezone: Literal["Asia/Ho_Chi_Minh"] = "Asia/Ho_Chi_Minh"

    def __post_init__(self) -> None:
        if tuple(day.iso_weekday for day in self.days) != tuple(range(1, 8)):
            raise ValueError("opening schedule must contain ISO weekdays 1 through 7")


@dataclass(frozen=True)
class Money:
    amount_minor: int
    currency: Literal["VND"] = "VND"

    def __post_init__(self) -> None:
        if self.amount_minor < 0:
            raise ValueError("money cannot be negative")


MoneyRangeKind = Literal["free", "range", "open_ended", "unknown"]


@dataclass(frozen=True)
class MoneyRange:
    kind: MoneyRangeKind
    lower: Money | None = None
    upper: Money | None = None
    source_label: str | None = None

    def __post_init__(self) -> None:
        if self.kind == "unknown" and (self.lower is not None or self.upper is not None):
            raise ValueError("unknown money ranges cannot have bounds")
        if self.kind == "free":
            if self.lower != Money(0) or self.upper != Money(0):
                raise ValueError("free money ranges require two zero bounds")
        if self.kind == "range":
            if self.lower is None or self.upper is None:
                raise ValueError("bounded money ranges require lower and upper bounds")
            if self.lower.amount_minor > self.upper.amount_minor:
                raise ValueError("money range lower bound exceeds upper bound")
        if self.kind == "open_ended" and (self.lower is None or self.upper is not None):
            raise ValueError("open-ended money ranges require only a lower bound")


@dataclass(frozen=True)
class PlaceType:
    code: str
    label: str
    taxonomy: Literal["source"] = "source"


@dataclass(frozen=True)
class Activity:
    code: str
    label: str
    taxonomy: Literal["source"] = "source"


@dataclass(frozen=True)
class Vibe:
    code: str
    label: str
    taxonomy: Literal["source"] = "source"


@dataclass(frozen=True)
class EvidenceRef:
    source_record_id: UUID
    field: str
    content_sha256: str
    ordinal: int | None = None

    def __post_init__(self) -> None:
        if not self.field or len(self.content_sha256) != 64:
            raise ValueError("evidence references require a field and SHA-256 digest")


@dataclass(frozen=True)
class ReviewEvidence:
    text: str
    ordinal: int
    reference: EvidenceRef


MediaKind = Literal["video", "main_image", "land_image"]


@dataclass(frozen=True)
class MediaAsset:
    kind: MediaKind
    url: str
    ordinal: int
    reference: EvidenceRef


@dataclass(frozen=True)
class SourceProvenance:
    source_name: str
    source_path: str
    source_sha256: str
    row_number: int
    source_record_id: UUID
    raw_row: Mapping[str, str]
    source_created_at: datetime | None = None
    partner_id: UUID | None = None
    category_id: UUID | None = None
    province_id: UUID | None = None
    budget_tag: str | None = None
    created_by: str | None = None
    last_modified_at: datetime | None = None
    last_modified_by: str | None = None

    def __post_init__(self) -> None:
        if not self.source_name or not self.source_path or len(self.source_sha256) != 64:
            raise ValueError("source provenance requires source identity and SHA-256")
        if self.row_number < 2:
            raise ValueError("CSV source row numbers include the header and start at 2")
        object.__setattr__(self, "raw_row", _immutable_mapping(self.raw_row))


IssueSeverity = Literal["info", "warning", "error"]


@dataclass(frozen=True)
class CompilationIssue:
    code: str
    severity: IssueSeverity
    row_number: int
    message: str
    field: str | None = None


@dataclass(frozen=True)
class PlaceIR:
    id: UUID
    name: str
    location: GeoPoint
    place_types: tuple[PlaceType, ...]
    opening_schedule: OpeningSchedule
    reference_price: MoneyRange
    provenance: SourceProvenance
    schema_version: str = IR_SCHEMA_VERSION
    external_place_id: ExternalPlaceId | None = None
    address: str | None = None
    activities: tuple[Activity, ...] = ()
    vibes: tuple[Vibe, ...] = ()
    description: str | None = None
    rating_e2: int | None = None
    review_count: int | None = None
    reviews: tuple[ReviewEvidence, ...] = ()
    media: tuple[MediaAsset, ...] = ()
    evidence: tuple[EvidenceRef, ...] = ()
    extensions: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.schema_version != IR_SCHEMA_VERSION:
            raise ValueError("unsupported PlaceIR schema version")
        if not self.name or not self.place_types:
            raise ValueError("PlaceIR requires a name and at least one place type")
        if self.id != self.provenance.source_record_id:
            raise ValueError("PlaceIR identity must match provenance identity")
        if self.rating_e2 is not None and not 0 <= self.rating_e2 <= 500:
            raise ValueError("rating_e2 must be between 0 and 500")
        if self.review_count is not None and self.review_count < 0:
            raise ValueError("review_count cannot be negative")
        object.__setattr__(self, "extensions", _immutable_mapping(self.extensions))


@dataclass(frozen=True)
class CompilationResult:
    row_number: int
    place: PlaceIR | None
    issues: tuple[CompilationIssue, ...] = ()

    def __post_init__(self) -> None:
        has_error = any(issue.severity == "error" for issue in self.issues)
        if self.place is None and not has_error:
            raise ValueError("fatal compilation results require at least one error")
        if self.place is not None and has_error:
            raise ValueError("successful compilation results cannot contain errors")
