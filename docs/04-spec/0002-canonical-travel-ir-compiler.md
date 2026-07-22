# Specification 0002: Canonical Travel IR Fixture Compiler

- **Status:** Active
- **Date:** 2026-07-22
- **Phase:** 1 — Canonical Travel IR compiler slice
- **Governing ADRs:**
  - `docs/01-adr/0001-rebuild-from-engine-restructure.md`
  - `docs/01-adr/0002-python-workspace-and-package-boundaries.md`
  - `docs/01-adr/0003-canonical-travel-ir.md`

## 1. Objective

Implement one complete, deterministic vertical slice that compiles a small CSV fixture extracted unchanged from `dataset/data-tourist-attraction-v2.csv` into canonical `PlaceIR` records and a JSON validation report.

```text
small v2 CSV fixture
        |
        v
typed source-row adapter
        |
        v
deterministic parsers
        |
        v
PlaceIR compiler
        |
        v
CompilationReport JSON
        |
        v
CLI file output
```

This is a compiler and contract slice, not a travel-planning feature. It establishes typed data, provenance, deterministic parsing, visible failure behaviour, and executable tooling for later slices.

## 2. Scope and boundaries

### In scope

- Python 3.11 `uv` workspace and PEP 621 metadata defined by ADR-0002;
- frozen standard-library canonical contract data classes defined by ADR-0003;
- a source-row adapter for the v2 CSV header and a fixture of exactly six complete source records;
- deterministic parsers for the source fields listed in Section 7;
- one row compiler, aggregate report serializer, and file-output CLI;
- unit tests, an import-boundary test, and one CLI integration test;
- fixture provenance and deterministic JSON output.

### Explicit non-goals

- FastAPI, HTTP handlers, web UIs, workers, or any delivery mechanism other than the CLI;
- Neo4j, Qdrant, PostgreSQL, Redis, object storage, persistence, or database clients;
- GraphRAG, graph construction, BM25, lexical retrieval, vector search, embeddings, reranking, or evaluation ranking metrics;
- LLMs, agents, LangGraph, model-provider SDKs, prompts, repair workflows, or generated travel facts;
- itinerary planning, routing, opening-hour feasibility validation, budgeting, recommendation, or user requests;
- full-dataset migration, automatic discovery of the repository dataset, scheduled ingestion, or a generated index;
- ontology mapping beyond deterministic source-token normalisation;
- downloading images/media or treating `AiContext` as evidence.

No dependency or directory outside the tree in Section 5 may be added in this slice.

## 3. Source boundary and fixture policy

The supplied dataset remains read-only. The implementation must not modify, rename, or migrate `dataset/data-tourist-attraction-v2.csv`.

Create `tests/fixtures/tourist_attraction_v2_compiler_fixture.csv` by copying exactly six complete source records and the original 25-column header from the supplied dataset. Do not alter values, normalise text in the fixture, add synthetic columns, or include the full file.

The six selected records must collectively include these real source shapes:

1. a bounded VND price and one normal opening interval;
2. `0đ` and an all-day opening value;
3. `Từ 500.000đ` and split opening intervals;
4. `Chưa phân loại` and `Đang cập nhật` hours;
5. a closed weekday; and
6. an overnight opening interval.

`tests/fixtures/tourist_attraction_v2_compiler_fixture.provenance.json` must record:

- source path `dataset/data-tourist-attraction-v2.csv`;
- replacement-data commit `760841a`;
- reviewed source SHA-256 `38446971E7DF40E70475CC0FDD470F448FE6F3E838427FE5C94097376089F806`;
- the six selected internal `Id` values, source-row numbers, and selection rationale;
- fixture row count, fixture SHA-256, and extraction date.

The CLI is intentionally fixture-scoped. It accepts one to ten source rows only and rejects a larger CSV with a structural input failure. This prevents the first implementation from becoming a silent full-dataset migration tool.

Synthetic invalid rows may be constructed inside unit tests only. They must not be added to the extracted source fixture or written back to the supplied dataset.

## 4. Observed source schema

The reviewed file has 972 rows and these 25 columns:

```text
Id, PartnerId, CategoryId, PlaceId, Address, ProvinceId, Name, Type,
Description, OperationHours, Location, RatingScore, ReviewCount,
ReferencePrice, AllTypes, Activities, TopReviews, VibeTag, BudgetTag,
AiContext, CreatedAt, CreatedBy, LastModifiedAt, LastModifiedBy, MediaInfo
```

Observed source shapes relevant to this slice:

- `Id`, `CategoryId`, and `ProvinceId` are UUID-shaped values; 44 rows have literal `NULL` external `PlaceId` values.
- `Location` is a hex EWKB point with SRID 4326; its encoded coordinate order is longitude then latitude.
- `AllTypes`, `Activities`, and `TopReviews` are JSON arrays; `MediaInfo` is a JSON object with `VideoUrl`, `MainImage`, and `LandImages`.
- `OperationHours` includes 187 `Đang cập nhật` values and real all-day, closed, normal, split-window, and overnight cases.
- `ReferencePrice` has six reviewed forms: `0đ`, two bounded VND ranges, one higher bounded VND range, `Từ 500.000đ`, and `Chưa phân loại`.
- `VibeTag` values are source codes, not accepted product meanings; `BudgetTag` is a source label, not an entitlement or planning tier.

## 5. Exact files and minimum implementation tree

The implementation commit creates exactly the following code, configuration, fixture, and test paths. Empty future directories are prohibited.

```text
.
├── pyproject.toml
├── uv.lock
├── apps/
│   └── cli/
│       ├── pyproject.toml
│       └── src/
│           └── soulviet_cli/
│               ├── __init__.py
│               └── main.py
├── packages/
│   ├── compiler/
│   │   ├── pyproject.toml
│   │   └── src/
│   │       └── soulviet_compiler/
│   │           ├── __init__.py
│   │           ├── source_rows.py
│   │           ├── parsers.py
│   │           ├── place_compiler.py
│   │           └── report.py
│   └── contracts/
│       ├── pyproject.toml
│       └── src/
│           └── soulviet_contracts/
│               ├── __init__.py
│               └── travel_ir.py
└── tests/
    ├── fixtures/
    │   ├── tourist_attraction_v2_compiler_fixture.csv
    │   └── tourist_attraction_v2_compiler_fixture.provenance.json
    ├── integration/
    │   └── test_compile_fixture_cli.py
    └── unit/
        ├── architecture/
        │   └── test_dependency_boundaries.py
        ├── compiler/
        │   ├── test_csv_row_adapter.py
        │   ├── test_parsers.py
        │   ├── test_place_compiler.py
        │   └── test_report_json.py
        └── contracts/
            └── test_travel_ir.py
```

The root `pyproject.toml` defines the uv workspace, Python 3.11 requirement, shared `pytest`, `mypy`, and Ruff configuration, and development dependency group. Member projects define only their distribution metadata and workspace-local dependencies:

```text
soulviet-cli -> soulviet-compiler -> soulviet-contracts
```

No `services/`, `ontology/`, `retrieval/`, `planning/`, `validation/`, API, worker, data-output, or generated-index path is created.

### Exact creation manifest

The tree above is exhaustive. The implementation may create only these files:

| Area | Exact file paths |
|---|---|
| Workspace | `pyproject.toml`; `uv.lock` |
| Contracts | `packages/contracts/pyproject.toml`; `packages/contracts/src/soulviet_contracts/__init__.py`; `packages/contracts/src/soulviet_contracts/travel_ir.py` |
| Compiler | `packages/compiler/pyproject.toml`; `packages/compiler/src/soulviet_compiler/__init__.py`; `packages/compiler/src/soulviet_compiler/source_rows.py`; `packages/compiler/src/soulviet_compiler/parsers.py`; `packages/compiler/src/soulviet_compiler/place_compiler.py`; `packages/compiler/src/soulviet_compiler/report.py` |
| CLI | `apps/cli/pyproject.toml`; `apps/cli/src/soulviet_cli/__init__.py`; `apps/cli/src/soulviet_cli/main.py` |
| Fixture | `tests/fixtures/tourist_attraction_v2_compiler_fixture.csv`; `tests/fixtures/tourist_attraction_v2_compiler_fixture.provenance.json` |
| Tests | `tests/unit/architecture/test_dependency_boundaries.py`; `tests/unit/contracts/test_travel_ir.py`; `tests/unit/compiler/test_csv_row_adapter.py`; `tests/unit/compiler/test_parsers.py`; `tests/unit/compiler/test_place_compiler.py`; `tests/unit/compiler/test_report_json.py`; `tests/integration/test_compile_fixture_cli.py` |

## 6. Typed interfaces

The implementation uses standard-library data classes, `Path`, `Mapping`, `Sequence`, `Protocol`, `UUID`, and JSON-compatible primitives. Public functions are fully type-checked under `mypy --strict`.

```python
@dataclass(frozen=True)
class RawSourceContext:
    source_name: str
    source_path: str
    source_sha256: str
    row_number: int
    raw_row: Mapping[str, str]


@dataclass(frozen=True)
class RawPlaceRow:
    row_number: int
    values: Mapping[str, str]
    source: RawSourceContext
    adapter_issues: tuple[CompilationIssue, ...] = ()


class CsvPlaceRowAdapter(Protocol):
    def read(
        self,
        input_path: Path,
        *,
        source_name: str,
        max_rows: int = 10,
    ) -> tuple[RawPlaceRow, ...]: ...


class PlaceIRCompiler(Protocol):
    def compile(self, row: RawPlaceRow) -> CompilationResult: ...


@dataclass(frozen=True)
class CompilationReport:
    report_schema_version: str
    source_name: str
    source_path: str
    source_sha256: str
    results: tuple[CompilationResult, ...]
    summary: CompilationSummary


def render_report_json(report: CompilationReport, *, pretty: bool) -> str: ...
```

`source_rows.py` owns `RawSourceContext`, header validation, UTF-8 decoding, CSV parsing, row limits, source-file hashing, and raw row capture. It creates `RawSourceContext` without parsing the canonical `Id`, requires all 25 reviewed headers from Section 4, permits additional headers, preserves every additional value in `RawSourceContext.raw_row`, and attaches an `info` `UNREVIEWED_SOURCE_COLUMN` issue for each additional header to each row in deterministic input-header order. `RawSourceContext` must be defined in the existing `source_rows.py`; no additional file is created for it. `RawPlaceRow.row_number` must equal `RawPlaceRow.source.row_number`, and `RawPlaceRow.values` must contain the same complete raw mapping as `RawPlaceRow.source.raw_row`. A missing reviewed header is structural; an additional header is not. `parsers.py` owns pure deterministic field parsers. `place_compiler.py` owns orchestration from `RawPlaceRow` to `CompilationResult`, including the ordered adapter issues, and is the only component that parses the canonical `Id`. A valid `Id` permits it to create `SourceProvenance` and `PlaceIR`, copying the complete raw mapping into `SourceProvenance.raw_row`. An invalid `Id` produces `place=None` and an ordered fatal issue without constructing `SourceProvenance`. `report.py` owns aggregate summary and canonical JSON conversion. `main.py` owns only arguments, file-system errors, output writing, and exit codes.

The CLI must not contain parser/domain logic. The compiler package must not import the CLI or any infrastructure module. `test_dependency_boundaries.py` must inspect package imports and fail on prohibited module prefixes such as `fastapi`, `neo4j`, `qdrant_client`, `langgraph`, model-provider SDKs, `services`, or `soulviet_cli` from domain packages.

## 7. Source-column parsing rules

All 25 reviewed source columns listed in Section 4 are required headers. A missing one is a structural failure. Additional unknown headers are allowed: their values are retained verbatim in `RawSourceContext.raw_row`, copied into `SourceProvenance.raw_row` for every successfully compiled place, and each additional header produces an `info` `UNREVIEWED_SOURCE_COLUMN` issue for every row in deterministic input-header order. No column is silently lost.

| Source column | Compiler action | Failure behaviour |
|---|---|---|
| `Id` | Parse UUID; populate canonical `PlaceIR.id` and provenance record ID. | Missing/malformed is fatal row error. |
| `PartnerId` | Preserve raw; parse as optional source UUID only when valid. No canonical meaning. | Warning on non-null malformed UUID. |
| `CategoryId` | Preserve raw and optional source UUID in provenance. Do not infer category semantics. | Warning on malformed non-null UUID. |
| `PlaceId` | Trim; literal `NULL`/blank becomes absent. Any other trimmed non-empty value becomes `ExternalPlaceId(scheme="google_places", value=<trimmed>)`. No online verification or provider-specific regex is used, and the value is not asserted to exist or be current. | No row issue solely because a non-empty value is unusual. |
| `Address` | Trim non-empty text into optional `PlaceIR.address`; preserve raw. | Warning only when source whitespace is discarded. |
| `ProvinceId` | Preserve raw and optional source UUID in provenance. Do not infer destination names. | Warning on malformed non-null UUID. |
| `Name` | Unicode-normalise and trim into required `PlaceIR.name`; preserve raw. | Blank/missing is fatal row error. |
| `Type` | Required first `PlaceType` via source-token normalisation. | Blank/missing is fatal row error. |
| `Description` | Optional trimmed source text plus `EvidenceRef`; preserve raw. | Warning for non-empty unusable text; do not invent a description. |
| `OperationHours` | Parse to `OpeningSchedule` using ADR-0003 rules and retain raw text. | Warning plus unknown affected day(s) for optional parse failure. |
| `Location` | Decode little-endian EWKB 2D Point SRID 4326; validate range; emit E7 `GeoPoint`. | Missing/malformed/wrong geometry or SRID is fatal row error. |
| `RatingScore` | Parse decimal rating in `[0, 5]` into optional fixed-point `rating_e2` (hundredths). | Warning and `None` when invalid. |
| `ReviewCount` | Parse non-negative integer into optional count. | Warning and `None` when invalid. |
| `ReferencePrice` | Parse `MoneyRange` as free, inclusive range, open-ended lower bound, or unknown. | Warning and `unknown` for malformed non-empty text. |
| `AllTypes` | Parse JSON array of strings; source-normalise, stable-dedupe, and append after `Type`. | Warning and omit malformed/invalid optional entries. |
| `Activities` | Parse JSON array of strings into stable, deduplicated `Activity` values. | Warning and emit empty tuple on invalid JSON. |
| `TopReviews` | Parse JSON array of strings into ordered `ReviewEvidence` values and references. | Warning and emit empty tuple on invalid JSON/entries. |
| `VibeTag` | Parse one source label/code into zero or one `Vibe`; do not map semantics. | Warning and omit unusable non-empty text. |
| `BudgetTag` | Preserve source label in provenance and price evidence only; do not create a tier. | Warning only for unusable non-empty text. |
| `AiContext` | Preserve verbatim in provenance only. It is excluded from `PlaceIR` evidence. | Informational issue when non-empty, explaining non-authoritative retention. |
| `CreatedAt` | Parse ISO-8601 UTC timestamp into optional provenance timestamp; preserve raw. | Warning and retain raw if malformed. |
| `CreatedBy` | Preserve raw source audit value; literal `NULL` becomes absent. | No row failure. |
| `LastModifiedAt` | Preserve raw source audit value; parse optional timestamp only when valid. | Warning and retain raw if malformed non-null. |
| `LastModifiedBy` | Preserve raw source audit value; literal `NULL` becomes absent. | No row failure. |
| `MediaInfo` | Parse object keys `VideoUrl`, `MainImage`, and `LandImages`; emit only non-empty HTTP(S) `MediaAsset` values with references. | Warning and omit invalid JSON/URLs/entries. |

Parser rules common to all fields:

- treat the literal source string `NULL` as absence only for fields documented as nullable; never convert it to a fabricated identifier or value;
- normalise strings with Unicode NFKC, trim boundary whitespace, and preserve the pre-normalised source value in provenance;
- issue order follows the table order, then array ordinal;
- never use random IDs, current time, network access, locale-sensitive formatting, or a model call;
- serialize mappings with stable keys and retain source-row order in the report.

## 8. CLI contract

The installed console script is:

```text
soulviet-compile-fixture
```

Command form:

```text
uv run soulviet-compile-fixture \
  --input tests/fixtures/tourist_attraction_v2_compiler_fixture.csv \
  --output .tmp/compiled-fixture.json \
  --source-name soulviet-tourist-attraction-v2-fixture \
  --pretty
```

Arguments:

| Argument | Required | Meaning |
|---|---:|---|
| `--input PATH` | yes | UTF-8 v2 fixture CSV with all 25 reviewed headers and 1–10 records. Additional headers are allowed, preserved in provenance, and reported as informational issues. |
| `--output PATH` | yes | JSON report destination. Its parent directory must already exist. |
| `--source-name NAME` | no | Provenance label; default `soulviet-tourist-attraction-v2-fixture`. |
| `--pretty` | no | Indent JSON without changing data ordering or semantics. |

Illustrative input shape (not a replacement for the unchanged fixture):

```csv
"Id","PartnerId",...,"ReferencePrice",...,"MediaInfo"
"<uuid>","NULL",...,"0đ",...,"{\"VideoUrl\":\"\",\"MainImage\":\"https://...\",\"LandImages\":[]}"
```

Illustrative report shape:

```json
{
  "report_schema_version": "1.0.0",
  "source": {
    "name": "soulviet-tourist-attraction-v2-fixture",
    "path": "tests/fixtures/tourist_attraction_v2_compiler_fixture.csv",
    "sha256": "<fixture-sha256>"
  },
  "summary": {
    "input_rows": 6,
    "compiled_rows": 6,
    "fatal_rows": 0,
    "warning_count": 3
  },
  "results": [
    {
      "row_number": 2,
      "place": {
        "schema_version": "1.0.0",
        "id": "<source-uuid>",
        "location": {
          "crs": "EPSG:4326",
          "latitude_e7": 160000000,
          "longitude_e7": 1080000000
        },
        "reference_price": {
          "kind": "free",
          "lower": {"currency": "VND", "amount_minor": 0},
          "upper": {"currency": "VND", "amount_minor": 0}
        }
      },
      "issues": []
    }
  ]
}
```

The output is written atomically in the destination directory. Re-running the command with identical fixture bytes and arguments must produce byte-identical compact JSON; `--pretty` changes whitespace only.

Exit codes:

| Code | Meaning |
|---:|---|
| `0` | Every row compiled; warnings may be present in the report. |
| `1` | Input structure was valid and a report was written, but one or more rows had fatal compilation errors. |
| `2` | CLI, file-system, encoding, CSV/header, or fixture-size failure; no successful report is written. |

## 9. Failure behaviour and observability

| Condition | Result |
|---|---|
| Input path missing, unreadable, invalid UTF-8, malformed CSV, any missing reviewed header, more than 10 rows, or unwritable output | Exit 2 with a concise stderr message; do not emit a successful report. Additional unknown headers are valid and are retained with deterministic informational issues. |
| Required row identity/name/type/location invalid | Include ordered `CompilationIssue` values, emit `place=null` for that row, identify it through report source metadata and row number, write the aggregate report, and exit 1. An invalid `Id` does not create `SourceProvenance`. |
| Optional source field invalid or unknown | Retain raw field in provenance, emit warning, compile remaining valid fields, exit 0 if no fatal row exists. |
| Unsupported future report major version read by a future consumer | Reject explicitly; the first CLI only writes version `1.0.0`. |
| Unexpected internal exception | Propagate to the CLI boundary as exit 2 with a stable error code; do not return fabricated JSON. |

The JSON report must expose source hash, source path, row number, issue code/severity/field, aggregate counts, canonical schema version, and deterministic compiler version. It must not log credentials, write raw rows to stderr, download media, or contact a network service.

## 10. Tests

### Unit tests

| Test file | Required coverage |
|---|---|
| `tests/unit/contracts/test_travel_ir.py` | Contract invariants: UUID identity, E7 coordinate bounds, money range free/unknown/open-ended distinction, opening schedule invariants (including all-day and overnight bounds), and immutable/default-safe collections. |
| `tests/unit/compiler/test_csv_row_adapter.py` | All 25 reviewed headers required; UTF-8/no-BOM input; fixture row limit; source hash; `RawSourceContext` construction without canonical `Id` parsing; raw-row preservation; accepted additional headers retained with deterministic informational issues; missing header; invalid UTF-8; and malformed CSV. |
| `tests/unit/compiler/test_parsers.py` | EWKB decoding, coordinate order, all six price forms, taxonomy normalisation, valid/invalid JSON, rating/review count, and all opening-hour states: unknown, closed, all-day, normal, split, overnight. |
| `tests/unit/compiler/test_place_compiler.py` | Canonical `Id` parsing; `SourceProvenance` construction only for a valid `Id`; invalid-`Id` fatal results with `place=None`; other required-field fatal errors; recoverable optional-field warnings; blank/literal-`NULL` versus arbitrary non-empty external `PlaceId` handling; evidence references; `AiContext` exclusion from evidence; deterministic issue order; and no fabricated defaults. |
| `tests/unit/compiler/test_report_json.py` | Stable row/issue/key ordering, compact versus pretty semantic equality, source hash inclusion, aggregate counts, and repeated-run byte equality for compact output. |
| `tests/unit/architecture/test_dependency_boundaries.py` | Enforce the ADR-0002 import graph and reject prohibited infrastructure/framework imports in domain packages. |

### Integration test

`tests/integration/test_compile_fixture_cli.py` invokes the installed `soulviet-compile-fixture` command as a subprocess against the six-row fixture and a temporary output path. It asserts:

- exit code 0;
- valid JSON report with six ordered results;
- output schema version and source hash match the fixture;
- all six places have canonical IDs, E7 points, provenance, and explicit price/opening representations;
- report warnings, if any, are explicit and stable;
- a second compact run writes byte-identical JSON;
- the repository’s full `dataset/data-tourist-attraction-v2.csv` is not passed to the CLI or changed by the test.

No test downloads media or accesses a network, database, model provider, or legacy branch.

## 11. Implementation acceptance criteria

- [ ] Root and member `pyproject.toml` files implement ADR-0002 with Python 3.11, uv workspace membership, local dependency direction, pytest, mypy, and Ruff configuration.
- [ ] The implementation tree matches Section 5 exactly, with no future placeholder directory.
- [ ] The fixture contains exactly six complete unmodified source records, the original header, and complete provenance metadata.
- [ ] All 25 reviewed source headers are required; a missing reviewed header exits 2, while every additional header is preserved in `RawSourceContext.raw_row`, copied to successful `SourceProvenance.raw_row`, and emits a deterministic informational issue per row.
- [ ] `RawSourceContext` is defined in `source_rows.py`; the adapter does not parse canonical `Id`, and `place_compiler.py` creates `SourceProvenance` only after `Id` validation.
- [ ] An invalid `Id` produces an ordered fatal issue and `place=None`; the result remains identifiable by report source metadata and row number.
- [ ] `PlaceIR`, all ADR-0003 required contracts, `CompilationReport`, and typed public interfaces exist and pass strict type checking.
- [ ] Internal UUID and optional external ID remain distinct in JSON and tests.
- [ ] Coordinates are decoded from EWKB as EPSG:4326 E7 integers with correct longitude/latitude order.
- [ ] Price output distinguishes free, range, open-ended, and unknown without floats or fabricated values.
- [ ] Opening output represents unknown, closed, all-day, normal, split, and overnight cases explicitly, including the specified minute bounds and `18:00–00:00` overnight representation.
- [ ] Source taxonomy is normalised deterministically without semantic mapping of source category/province/vibe codes.
- [ ] Reviews, description, and media include evidence references; `AiContext` is provenance-only.
- [ ] Fatal versus recoverable failures follow Sections 7 and 9; no exception is silently swallowed.
- [ ] CLI output is deterministic, atomically written, and has the documented exit codes.
- [ ] All unit tests, the CLI integration test, `mypy --strict`, Ruff check, and Ruff format check pass.
- [ ] No runtime third-party dependency, network access, full-dataset migration, generated index, or out-of-scope component is introduced.

## 12. Known limitations and next slice

The first compiler understands only the reviewed CSV shape, VND, Vietnam time zone, EWKB points, and source-token taxonomy. It does not prove source factual accuracy, source licensing, external-ID validity, or opening-hour freshness. It compiles evidence references; it does not grade evidence or validate an itinerary.

The recommended next vertical slice after this one is a documented structured retrieval baseline over compiled fixture IR, but only after this compiler’s output schema, parser tests, and evaluation fixture are accepted.
