# ADR-0003: Canonical Travel IR for the Fixture Compiler

- **Status:** Accepted
- **Date:** 2026-07-22
- **Decision owner:** SoulViet AI team
- **Applies from:** Phase 1 canonical Travel IR compiler slice

## Context

The reviewed v2 tourist-attraction CSV is an operational-looking source snapshot, not a runtime contract. It contains UUIDs, optional external place IDs, EWKB points, free-form Vietnamese opening hours and prices, JSON-encoded taxonomy/review/media fields, and generated text of uncertain authority.

The compiler must turn one source row into typed, deterministic Travel IR while retaining enough raw provenance to audit the result. It must distinguish unknown from false or free values, surface incomplete data explicitly, and never invent a taxonomy mapping or factual value.

## Decision

### Identity

`PlaceIR.id` is the source row’s `Id`, parsed as a UUID. It is the canonical internal identifier for this source snapshot.

`PlaceId` is optional. A blank value or literal `NULL` is absent; every other trimmed non-empty value becomes `ExternalPlaceId(scheme="google_places", value=<trimmed>)`. This slice performs neither online verification nor provider-specific regular-expression validation, so emitting an external ID does not claim that it exists or remains current. It is not the canonical key because 44 reviewed rows have no external ID and external-provider identifiers may change or disappear.

`CategoryId`, `ProvinceId`, `PartnerId`, and audit IDs are preserved in source provenance until a separate ontology/source-adapter ADR assigns them canonical meaning. The compiler must not infer province names, category semantics, or partner ownership.

### Versioning and raw-source preservation

`PlaceIR.schema_version` starts at `1.0.0` and follows semantic-versioning rules:

- a major version changes required meaning or removes/changes a field incompatibly;
- a minor version adds optional fields or issue codes;
- a patch version clarifies behaviour without changing the JSON shape.

Every successfully compiled `PlaceIR` has `SourceProvenance`. It includes source path/name, source-file SHA-256, 1-based CSV row number, the validated source record ID, optional source timestamp, and an immutable copy of all original column strings. Before canonical identity is validated, the compiler carries source metadata, row number, and raw values in an internal `RawSourceContext`; this is compiler input, not a canonical Travel IR contract. All 25 reviewed source columns are required at the CSV boundary. Additional unknown columns are allowed, retained in the raw context and in every successfully compiled `SourceProvenance.raw_row`, and produce one deterministic informational issue for each additional header on each input row; they are never discarded.

Raw provenance is audit material only. It is not automatically product-facing evidence and must not be rendered to end users without a later evidence/privacy decision.

### Canonical contract shape

The first slice uses frozen standard-library data classes and explicit JSON serializers. These are the required contracts; helper types such as `OpeningDay` may support them but do not create a separate domain boundary.

| Contract | Required shape and rules |
|---|---|
| `ExternalPlaceId` | `scheme: str`, `value: str`. For this source, a trimmed non-empty `PlaceId` emits `scheme="google_places"`; no online lookup or provider-specific pattern check is performed. |
| `GeoPoint` | `latitude_e7: int`, `longitude_e7: int`, `crs: Literal["EPSG:4326"]`. Coordinates are fixed-point degrees rounded deterministically to seven decimal places; floats never appear in IR. |
| `OpeningWindow` | `start_minute: int` in `0..1439`, `end_minute: int` in `0..1440`, `ends_next_day: bool`. Ordinary windows use `ends_next_day=False` and `start_minute < end_minute`; all-day is exactly `0` to `1440` with `ends_next_day=False`; overnight windows may have `end_minute <= start_minute` and must use `ends_next_day=True`. |
| `OpeningSchedule` | `timezone: "Asia/Ho_Chi_Minh"` plus exactly seven ISO-weekday `OpeningDay` values. A day is `unknown`, `closed`, or `open` with one or more ordered, non-overlapping windows. |
| `Money` | `currency: Literal["VND"]`, `amount_minor: int >= 0`. VND has zero decimal places in this contract, so one minor unit equals one VND. Floats and display strings are never authoritative amounts. |
| `MoneyRange` | `kind: Literal["free", "range", "open_ended", "unknown"]`, `lower: Money | None`, `upper: Money | None`, `source_label: str | None`. `free` is exactly zero; `unknown` has no bounds; an open-ended amount has only `lower`. |
| `PlaceType` | `code: str`, `label: str`, `taxonomy: Literal["source"]`. The code is deterministic source-token normalization, not an asserted ontology mapping. |
| `Activity` | Same source-token pattern as `PlaceType`; duplicate normalized values are removed in stable source order. |
| `Vibe` | Same source-token pattern as `PlaceType`. Numeric source values remain numeric labels/tokens; the compiler assigns no human meaning to them. |
| `EvidenceRef` | `source_record_id: UUID`, `field: str`, `ordinal: int | None`, `content_sha256: str`. It identifies an exact raw source field/value and does not itself validate truth. |
| `ReviewEvidence` | `text: str`, `ordinal: int`, `reference: EvidenceRef`. No author, timestamp, rating, or source URL is fabricated when absent. |
| `MediaAsset` | `kind: Literal["video", "main_image", "land_image"]`, `url: str`, `ordinal: int`, `reference: EvidenceRef`. URLs are retained as references and are never downloaded by the compiler. |
| `SourceProvenance` | Source identity, source hash, row number, source record ID, optional source-created timestamp, all raw column strings, and source-only UUIDs/labels that have no canonical mapping yet. |
| `CompilationIssue` | `code: str`, `severity: Literal["info", "warning", "error"]`, `row_number: int`, `field: str | None`, `message: str`. Messages are deterministic and do not dump unrestricted source content. |
| `CompilationResult` | One source-row outcome: `row_number`, `place: PlaceIR | None`, and ordered `issues: tuple[CompilationIssue, ...]`. A fatal row has `place=None` and at least one error. |
| `PlaceIR` | `schema_version`, canonical UUID `id`, optional `external_place_id`, required `name`, optional `address`, required `location`, non-empty `place_types`, optional activities/vibes/description, required `opening_schedule` and `reference_price` (both may express unknown), optional `rating_e2: int | None` in `[0, 500]`, optional non-negative `review_count`, reviews, media, evidence references, provenance, and an empty-by-default `extensions` mapping. |

The CLI report may add an aggregate `CompilationReport` envelope around ordered `CompilationResult` values. It is a compiler output/report type, not a new canonical travel fact contract.

### Required versus optional fields

A compiled `PlaceIR` requires a valid internal UUID, a non-blank name, a valid EPSG:4326 point, at least one normalized source place type, source provenance, and the current schema version.

The following are valid but optional or explicitly unknown: external ID, address, description, rating, review count, activities, vibes, reviews, media, price amount, and individual opening-day knowledge. An unknown price is represented by `MoneyRange(kind="unknown")`; it is never converted to free. Unknown hours are represented as an `OpeningSchedule` whose affected days are `unknown`; they are never converted to closed or all-day.

### Coordinates

The compiler supports only a hex-encoded little-endian EWKB 2D Point with SRID 4326 for this slice. It reads the source order as longitude then latitude, validates geographic bounds, rounds deterministically to E7 fixed-point integers, and emits latitude/longitude explicitly. Any other geometry, malformed hex, SRID mismatch, non-finite coordinate, or out-of-range point is a fatal row issue.

### Opening schedules

The source-specific parser recognises Vietnamese weekday segments and stores every schedule in `Asia/Ho_Chi_Minh`.

- `Đang cập nhật`, blank, or otherwise unavailable values produce `unknown` days and a warning.
- a closed marker produces a `closed` day with no windows.
- a 24-hour marker produces one open window from `00:00` to `24:00`.
- one ordinary interval produces one normal window.
- multiple same-day intervals produce ordered split windows.
- an interval whose end clock time is less than or equal to its start becomes an overnight window with `ends_next_day=True`; for example, `18:00–00:00` is `start_minute=1080`, `end_minute=0`, `ends_next_day=True`.

Malformed optional opening-hour data is recoverable: the affected day becomes `unknown` and the compiler emits a warning. The raw text remains in provenance. The compiler does not decide itinerary feasibility; a later validator is the final authority.

### Money

The v2 `ReferencePrice` source forms are interpreted deterministically:

- `0đ` → free with lower and upper amount 0;
- a bounded VND range → inclusive lower and upper `Money` amounts;
- `Từ <amount>` → open-ended range with a lower amount only;
- `Chưa phân loại`, blank, or an unparseable value → unknown.

`BudgetTag` is preserved as a source label only. It does not produce a canonical tier, entitlement, or planning policy. The compiler records a warning for malformed non-empty price text and never substitutes a cost.

### Taxonomy normalization

`Type`, `AllTypes`, `Activities`, and `VibeTag` are source taxonomy inputs. For each non-empty source label, normalize with Unicode NFKC, trim, case-fold, collapse internal whitespace, and prefix the resulting token with `source:`. Preserve the trimmed original in `label`.

The singular `Type` is required and is included first in `PlaceIR.place_types`; JSON `AllTypes` values then contribute stable, de-duplicated additional types. Numeric vibes such as `1`, `2`, `4`, `5`, and `6` remain source tokens. No Vietnamese label, category UUID, province UUID, or numeric code is mapped to product semantics in this ADR.

### Reviews, descriptions, generated context, and media

`TopReviews` must be a JSON array of strings. Each non-empty entry becomes `ReviewEvidence` with a stable ordinal and an `EvidenceRef` whose hash covers the original review text. Reviews are source testimony, not independently verified facts.

`Description` is retained as optional source text and receives an evidence reference. `AiContext` is preserved only in raw provenance because its generation and factual authority are undocumented; it must not be promoted to evidence or used to create facts. `MediaInfo` must be a JSON object with optional `VideoUrl`, `MainImage`, and `LandImages`; non-empty HTTP(S) URLs become `MediaAsset` values with references. The compiler does not fetch, inspect, or validate remote media.

### Validation severity and failure boundary

The compiler is deterministic and fail-visible:

- structural input failures—any missing reviewed header, invalid UTF-8, malformed CSV, or fixture row-count outside the slice limit—terminate the CLI without a successful report and use exit code 2; additional unknown headers are valid input;
- fatal row failures—invalid/missing `Id`, blank `Name`, invalid/missing `Type`, or invalid `Location`—produce a `CompilationResult` with `place=None`, an `error` issue, and contribute to exit code 1 after the report is written;
- recoverable source problems—missing external ID, invalid optional JSON, unavailable/malformed hours, invalid optional numeric values, unparseable price, or malformed media entry—emit warnings, preserve raw input, and compile the remaining valid row fields;
- informational issues record each preserved additional source column or benign normalisation.

Issues are emitted in stable field order. The compiler never catches an error and silently invents a fallback value.

The CSV adapter does not parse the canonical `Id`. The row compiler parses `Id`; only a valid UUID permits it to create `SourceProvenance` and `PlaceIR`. An invalid `Id` therefore produces no canonical provenance object, but the fatal result remains identifiable through the report's source metadata and the result row number.

### Forward compatibility

Every JSON report includes its report schema version and each `PlaceIR` includes its IR schema version. Consumers must ignore unrecognised optional fields within the same major version and preserve an `extensions` object for additive metadata. Consumers must reject an unsupported major version explicitly.

Unknown source columns, taxonomy labels, and source identifiers remain provenance; they do not require a schema change merely to survive compilation. Adding a new canonical semantic field requires an ADR and contract/test update.

## Consequences

### Positive

- Downstream systems receive stable IDs, typed geometry, typed money, schedules, evidence references, and explicit quality issues.
- The source snapshot remains auditable without making every source field product-visible.
- Unknown, free, closed, and unavailable values remain distinct.
- The compiler can be tested without operational infrastructure or an LLM.

### Costs

- The first IR is intentionally source-specific for EWKB, Vietnamese opening text, and VND.
- Raw provenance makes compiler output larger; this is acceptable for the fixture-only slice.
- Taxonomy codes are not yet rich product ontology identifiers.

## Rejected alternatives

### Use the external `PlaceId` as canonical identity

Rejected because it is absent on reviewed rows and belongs to an external provider.

### Represent money and coordinates as floats

Rejected because binary floating-point representation would make deterministic serialization and comparison needlessly fragile.

### Treat unknown price as free or unknown hours as closed

Rejected because both substitutions create false travel facts and can silently bias planning.

### Drop raw source fields after parsing

Rejected because compilation quality, evidence traces, and future migrations require auditable source context.

### Infer an ontology from source labels in the compiler

Rejected because the source codes and taxonomy meanings are not yet accepted. A later ontology ADR owns semantic mappings.

## Revisit triggers

Revisit this ADR when a second source system is added, when source-data provenance is formally resolved, when a canonical ontology is accepted, when additional currencies/geometries/timezones are supported, or when a product-facing evidence/privacy policy changes raw-field retention.
