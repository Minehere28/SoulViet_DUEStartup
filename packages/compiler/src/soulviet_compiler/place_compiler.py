from __future__ import annotations

import hashlib
import unicodedata
from datetime import datetime
from uuid import UUID

from soulviet_contracts import (
    Activity,
    CompilationIssue,
    CompilationResult,
    EvidenceRef,
    ExternalPlaceId,
    MediaAsset,
    MoneyRange,
    OpeningSchedule,
    PlaceIR,
    PlaceType,
    ReviewEvidence,
    SourceProvenance,
    Vibe,
)

from soulviet_compiler.parsers import (
    normalized_text,
    nullable_text,
    parse_ewkb_point,
    parse_json_string_array,
    parse_media_info,
    parse_money_range,
    parse_opening_schedule,
    parse_optional_uuid,
    parse_rating_e2,
    parse_review_count,
    parse_timestamp,
    parse_uuid,
    source_taxonomy,
)
from soulviet_compiler.source_rows import RawPlaceRow


def _issue(
    row_number: int,
    field: str,
    code: str,
    severity: str,
    message: str,
) -> CompilationIssue:
    if severity == "info":
        return CompilationIssue(code, "info", row_number, message, field)
    if severity == "warning":
        return CompilationIssue(code, "warning", row_number, message, field)
    return CompilationIssue(code, "error", row_number, message, field)


def _evidence(
    source_record_id: UUID,
    field: str,
    content: str,
    ordinal: int | None = None,
) -> EvidenceRef:
    return EvidenceRef(
        source_record_id=source_record_id,
        field=field,
        ordinal=ordinal,
        content_sha256=hashlib.sha256(content.encode("utf-8")).hexdigest(),
    )


def _normalized_optional(value: str) -> str | None:
    text = nullable_text(value)
    return None if text is None else unicodedata.normalize("NFKC", text)


class PlaceIRCompiler:
    def compile(self, row: RawPlaceRow) -> CompilationResult:
        values = row.values
        issues: list[CompilationIssue] = []
        evidence: list[EvidenceRef] = []

        try:
            source_record_id = parse_uuid(values["Id"])
        except ValueError:
            issues.append(
                _issue(row.row_number, "Id", "INVALID_ID", "error", "Id must be a valid UUID")
            )
            issues.extend(row.adapter_issues)
            return CompilationResult(row.row_number, None, tuple(issues))

        partner_id = self._optional_uuid(values["PartnerId"], "PartnerId", row, issues)
        category_id = self._optional_uuid(values["CategoryId"], "CategoryId", row, issues)

        external_text = nullable_text(values["PlaceId"])
        external_id = (
            None
            if external_text is None
            else ExternalPlaceId(scheme="google_places", value=external_text)
        )
        if external_text is None:
            issues.append(
                _issue(
                    row.row_number,
                    "PlaceId",
                    "EXTERNAL_PLACE_ID_ABSENT",
                    "warning",
                    "External PlaceId is absent",
                )
            )

        address = _normalized_optional(values["Address"])
        if address is not None and address != values["Address"]:
            issues.append(
                _issue(
                    row.row_number,
                    "Address",
                    "ADDRESS_NORMALIZED",
                    "warning",
                    "Address boundary whitespace or Unicode form was normalized",
                )
            )

        province_id = self._optional_uuid(values["ProvinceId"], "ProvinceId", row, issues)

        name = normalized_text(values["Name"])
        if not name:
            issues.append(_issue(row.row_number, "Name", "INVALID_NAME", "error", "Name is blank"))

        place_types: list[PlaceType] = []
        seen_types: set[str] = set()
        try:
            code, label = source_taxonomy(values["Type"])
            place_types.append(PlaceType(code, label))
            seen_types.add(code)
        except ValueError:
            issues.append(_issue(row.row_number, "Type", "INVALID_TYPE", "error", "Type is blank"))

        description = _normalized_optional(values["Description"])
        if description is not None:
            evidence.append(_evidence(source_record_id, "Description", values["Description"]))

        opening_schedule, opening_warnings = self._opening(values["OperationHours"])
        issues.extend(
            _issue(
                row.row_number,
                "OperationHours",
                "OPENING_HOURS_UNAVAILABLE",
                "warning",
                message,
            )
            for message in opening_warnings
        )

        location = None
        try:
            location = parse_ewkb_point(values["Location"])
        except ValueError:
            issues.append(
                _issue(
                    row.row_number,
                    "Location",
                    "INVALID_LOCATION",
                    "error",
                    "Location must be an EWKB Point with SRID 4326",
                )
            )

        rating_e2 = self._optional_rating(values["RatingScore"], row, issues)
        review_count = self._optional_review_count(values["ReviewCount"], row, issues)

        try:
            reference_price = parse_money_range(values["ReferencePrice"])
        except ValueError:
            reference_price = MoneyRange(
                kind="unknown",
                source_label=normalized_text(values["ReferencePrice"]) or None,
            )
            issues.append(
                _issue(
                    row.row_number,
                    "ReferencePrice",
                    "INVALID_REFERENCE_PRICE",
                    "warning",
                    "ReferencePrice is unsupported and remains unknown",
                )
            )
        if nullable_text(values["ReferencePrice"]) is not None:
            evidence.append(_evidence(source_record_id, "ReferencePrice", values["ReferencePrice"]))

        all_types = self._string_array(values["AllTypes"], "AllTypes", row, issues)
        for _ordinal, type_label in all_types:
            try:
                type_code, clean_label = source_taxonomy(type_label)
            except ValueError:
                continue
            if type_code not in seen_types:
                place_types.append(PlaceType(type_code, clean_label))
                seen_types.add(type_code)

        activities: list[Activity] = []
        seen_activities: set[str] = set()
        for _ordinal, activity_label in self._string_array(
            values["Activities"], "Activities", row, issues
        ):
            activity_code, clean_label = source_taxonomy(activity_label)
            if activity_code not in seen_activities:
                activities.append(Activity(activity_code, clean_label))
                seen_activities.add(activity_code)

        reviews: list[ReviewEvidence] = []
        for ordinal, review_text in self._string_array(
            values["TopReviews"], "TopReviews", row, issues
        ):
            clean_review = normalized_text(review_text)
            reference = _evidence(source_record_id, "TopReviews", review_text, ordinal)
            evidence.append(reference)
            reviews.append(ReviewEvidence(clean_review, ordinal, reference))

        vibes: list[Vibe] = []
        vibe_text = nullable_text(values["VibeTag"])
        if vibe_text is not None:
            try:
                vibe_code, vibe_label = source_taxonomy(vibe_text)
                vibes.append(Vibe(vibe_code, vibe_label))
            except ValueError:
                issues.append(
                    _issue(
                        row.row_number,
                        "VibeTag",
                        "INVALID_VIBE",
                        "warning",
                        "VibeTag is unusable",
                    )
                )

        budget_tag = nullable_text(values["BudgetTag"])
        if budget_tag is not None:
            evidence.append(_evidence(source_record_id, "BudgetTag", values["BudgetTag"]))

        if nullable_text(values["AiContext"]) is not None:
            issues.append(
                _issue(
                    row.row_number,
                    "AiContext",
                    "AI_CONTEXT_PROVENANCE_ONLY",
                    "info",
                    "AiContext is retained as non-authoritative provenance only",
                )
            )

        created_at = self._optional_timestamp(values["CreatedAt"], "CreatedAt", row, issues)
        created_by = nullable_text(values["CreatedBy"])
        last_modified_at = self._optional_timestamp(
            values["LastModifiedAt"], "LastModifiedAt", row, issues
        )
        last_modified_by = nullable_text(values["LastModifiedBy"])

        media: list[MediaAsset] = []
        media_text = nullable_text(values["MediaInfo"])
        if media_text is not None:
            try:
                parsed_media = parse_media_info(media_text)
                for invalid_field in parsed_media.invalid_fields:
                    issues.append(
                        _issue(
                            row.row_number,
                            "MediaInfo",
                            "INVALID_MEDIA_ENTRY",
                            "warning",
                            f"Media entry is invalid: {invalid_field}",
                        )
                    )
                for entry in parsed_media.entries:
                    reference = _evidence(
                        source_record_id,
                        "MediaInfo",
                        entry.url,
                        entry.ordinal,
                    )
                    evidence.append(reference)
                    media.append(MediaAsset(entry.kind, entry.url, entry.ordinal, reference))
            except ValueError:
                issues.append(
                    _issue(
                        row.row_number,
                        "MediaInfo",
                        "INVALID_MEDIA_INFO",
                        "warning",
                        "MediaInfo is not a valid media object",
                    )
                )

        issues.extend(row.adapter_issues)
        if any(issue.severity == "error" for issue in issues):
            return CompilationResult(row.row_number, None, tuple(issues))
        if location is None:
            raise AssertionError("validated location unexpectedly absent")

        provenance = SourceProvenance(
            source_name=row.source.source_name,
            source_path=row.source.source_path,
            source_sha256=row.source.source_sha256,
            row_number=row.row_number,
            source_record_id=source_record_id,
            raw_row=row.source.raw_row,
            source_created_at=created_at,
            partner_id=partner_id,
            category_id=category_id,
            province_id=province_id,
            budget_tag=budget_tag,
            created_by=created_by,
            last_modified_at=last_modified_at,
            last_modified_by=last_modified_by,
        )
        place = PlaceIR(
            id=source_record_id,
            name=name,
            location=location,
            place_types=tuple(place_types),
            opening_schedule=opening_schedule,
            reference_price=reference_price,
            provenance=provenance,
            external_place_id=external_id,
            address=address,
            activities=tuple(activities),
            vibes=tuple(vibes),
            description=description,
            rating_e2=rating_e2,
            review_count=review_count,
            reviews=tuple(reviews),
            media=tuple(media),
            evidence=tuple(evidence),
        )
        return CompilationResult(row.row_number, place, tuple(issues))

    @staticmethod
    def _optional_uuid(
        value: str,
        field: str,
        row: RawPlaceRow,
        issues: list[CompilationIssue],
    ) -> UUID | None:
        try:
            return parse_optional_uuid(value)
        except ValueError:
            issues.append(
                _issue(
                    row.row_number,
                    field,
                    f"INVALID_{field.upper()}",
                    "warning",
                    f"{field} is not a valid UUID and remains raw provenance only",
                )
            )
            return None

    @staticmethod
    def _opening(value: str) -> tuple[OpeningSchedule, tuple[str, ...]]:
        return parse_opening_schedule(value)

    @staticmethod
    def _optional_rating(
        value: str,
        row: RawPlaceRow,
        issues: list[CompilationIssue],
    ) -> int | None:
        try:
            return parse_rating_e2(value)
        except ValueError:
            issues.append(
                _issue(
                    row.row_number,
                    "RatingScore",
                    "INVALID_RATING",
                    "warning",
                    "RatingScore is invalid and was omitted",
                )
            )
            return None

    @staticmethod
    def _optional_review_count(
        value: str,
        row: RawPlaceRow,
        issues: list[CompilationIssue],
    ) -> int | None:
        try:
            return parse_review_count(value)
        except ValueError:
            issues.append(
                _issue(
                    row.row_number,
                    "ReviewCount",
                    "INVALID_REVIEW_COUNT",
                    "warning",
                    "ReviewCount is invalid and was omitted",
                )
            )
            return None

    @staticmethod
    def _string_array(
        value: str,
        field: str,
        row: RawPlaceRow,
        issues: list[CompilationIssue],
    ) -> tuple[tuple[int, str], ...]:
        if nullable_text(value) is None:
            return ()
        try:
            parsed = parse_json_string_array(value)
        except ValueError:
            issues.append(
                _issue(
                    row.row_number,
                    field,
                    f"INVALID_{field.upper()}",
                    "warning",
                    f"{field} is not a JSON string array and was omitted",
                )
            )
            return ()
        for ordinal in parsed.invalid_ordinals:
            issues.append(
                _issue(
                    row.row_number,
                    field,
                    f"INVALID_{field.upper()}_ENTRY",
                    "warning",
                    f"{field} entry {ordinal} is invalid and was omitted",
                )
            )
        return parsed.values

    @staticmethod
    def _optional_timestamp(
        value: str,
        field: str,
        row: RawPlaceRow,
        issues: list[CompilationIssue],
    ) -> datetime | None:
        try:
            return parse_timestamp(value)
        except ValueError:
            issues.append(
                _issue(
                    row.row_number,
                    field,
                    f"INVALID_{field.upper()}",
                    "warning",
                    f"{field} is invalid and remains raw provenance only",
                )
            )
            return None
