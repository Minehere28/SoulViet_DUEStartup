# Specification 0001: Repository Rebuild

- **Status:** Active; cleanup not started
- **Date:** 2026-07-22
- **Phase:** 0 — Repository and architecture foundation
- **Governing ADR:** `docs/01-adr/0001-rebuild-from-engine-restructure.md`

## 1. Purpose and scope

This specification defines the first structural cleanup of the SoulViet AI Engine repository. It inventories the current working tree, decides what may remain in the active tree, records reusable legacy knowledge, and defines the minimum tree and acceptance criteria for the cleanup commit.

This specification does not authorize production engine code. The cleanup must not create `packages/`, `services/`, `apps/`, agents, GraphRAG components, generated indexes, placeholder modules, or an in-tree legacy archive. Git history and preserved branches are the legacy archive, subject to the security decision in Section 13.

## 2. Authority and classification rules

This specification follows, in order:

1. `README.md`;
2. `AGENTS.md`;
3. `docs/status/current.md`;
4. `docs/00-vision/00-project-vision.md`;
5. ADR-0001.

The classifications mean:

- **KEEP** — retain the current item as active repository content.
- **KEEP AFTER REVIEW** — do not delete, rename, or treat the item as authoritative until the stated ownership, provenance, licensing, schema, or correctness review is complete.
- **REWRITE** — the concept may be needed, but the current implementation or text is not authoritative. Remove the current version during cleanup; create a replacement only when an approved vertical slice requires it.
- **DELETE FROM ACTIVE TREE** — remove the item from the version-controlled rebuild tree. Do not copy it to a `legacy/` directory; recover it from Git history if needed.

`REWRITE` does not authorize replacement code in the cleanup commit.

## 3. Repository assessment at specification time

The audit was performed on 2026-07-22 against commit `25adb16` while the working tree was checked out on `feat/engine-restructure-wip`.

- `rebuild/career-os-v2` did not yet exist locally.
- The repository had 88 tracked paths and pre-existing uncommitted foundation work.
- Twenty-four tracked paths were already absent from the working tree: one legacy CSV and 23 legacy documents.
- Twenty-nine tracked `.pyc` files remained.
- The active root still contained `graph.pt`, an obsolete `src/` prototype, a broken root API bootstrap, an experimental HTML client, and one legacy test file.
- An ignored local virtual environment contained 29,624 files and approximately 856 MiB. It is not repository content.
- An empty, untracked `.agents/` orchestration directory was present. It is local tool state, not project source.
- Git is configured with `core.ignorecase=true`; the transition from `docs/status/CURRENT_STATUS.md` to `docs/status/current.md` must be staged and verified deliberately.

The existing dirty-worktree changes belong to the user and are outside this specification task. No cleanup commit may be made on either legacy branch.

## 4. Root inventory

The “active tree” below means version-controlled repository content. Local Git metadata, ignored credentials, and ignored developer environments are not part of the minimum tracked tree.

| Current root item | Classification | Cleanup decision and reason |
|---|---|---|
| `.git/` | KEEP | Local repository metadata. Do not edit legacy refs as part of cleanup; `.git/` is not part of the tracked tree. |
| `.agents/` | DELETE FROM ACTIVE TREE | Empty, untracked local orchestration state. Never treat it as product source or include it in the tracked tree. Physical removal is not required by the cleanup commit. |
| `.gitignore` | REWRITE | It currently ignores only `myenv` and `.env`. It must prevent Python bytecode, tool caches, local environments, secrets, and the deprecated root graph artifact from being added again. |
| `.env` | DELETE FROM ACTIVE TREE | Ignored and untracked machine-local credentials. Never stage it. Physical deletion or credential migration is a local/security operation, not part of the cleanup commit. |
| `README.md` | KEEP | Current foundation authority describing the product, phase, target map, and dependency direction. The target map is not permission to scaffold empty directories. |
| `AGENTS.md` | KEEP | Current repository operating policy and architectural boundaries. |
| `app.py` | DELETE FROM ACTIVE TREE | Broken prototype bootstrap: it imports the absent `views.travel_view`, places delivery code at the root, and enables wildcard CORS. |
| `graph.pt` | DELETE FROM ACTIVE TREE | Deprecated generated PyTorch ZIP/pickle artifact. It is 8,894,177 bytes, has no active reproducible build path, and is loaded by legacy code with unsafe general deserialization. It must not remain a runtime input. |
| `index.html` | DELETE FROM ACTIVE TREE | Experimental UI that calls `http://127.0.0.1:8000/plan` directly, contrary to the backend integration boundary, and depends on CDN-loaded client libraries. |
| `requirements.txt` | DELETE FROM ACTIVE TREE | Four unpinned dependencies describe the old FastAPI/Neo4j prototype and are incomplete for the imports in `src/`. Packaging metadata must wait for a packaging ADR and the first executable slice. |
| root `__pycache__/` | DELETE FROM ACTIVE TREE | Generated bytecode is tracked and must be removed and ignored. |
| `dataset/` | KEEP AFTER REVIEW | Contains the only current candidate travel-data asset. Its schema is known, but upstream provenance, license, ownership, export lineage, and freshness policy are not. Section 5 is the retention gate. |
| `docs/` | KEEP | Retain only the current authority files and this specification. Legacy plans, generated research, duplicate status files, and empty scaffolding do not survive. |
| `myenv/` | DELETE FROM ACTIVE TREE | Ignored local Python 3.11 environment, not a portable dependency declaration or source asset. It need not be physically deleted by the commit, but it must never be tracked. |
| `src/` | REWRITE | Entire directory is a deterministic-engine WIP tied to `graph.pt`, placeholder policy, and unaccepted contracts. Remove it in cleanup; Section 6 records concepts worth reconsidering. |
| `tests/` | REWRITE | The only test is coupled to obsolete `src/` contracts and misses required itinerary invariants. Remove it in cleanup and recreate tests with the owning future slice. |

## 5. Data inventory and retention gate

### 5.1 `dataset/data-tourist-attraction-v2.csv` — KEEP AFTER REVIEW

Observed file identity:

- untracked, UTF-8 without BOM;
- 5,121,063 bytes;
- SHA-256 `38446971E7DF40E70475CC0FDD470F448FE6F3E838427FE5C94097376089F806`;
- 972 parsed records and 25 columns;
- 972 unique internal `Id` values;
- 928 unique external `PlaceId` values and 44 literal `NULL` values;
- 3 province identifiers and 82 type values.

Observed schema:

```text
Id
PartnerId
CategoryId
PlaceId
Address
ProvinceId
Name
Type
Description
OperationHours
Location
RatingScore
ReviewCount
ReferencePrice
AllTypes
Activities
TopReviews
VibeTag
BudgetTag
AiContext
CreatedAt
CreatedBy
LastModifiedAt
LastModifiedBy
MediaInfo
```

All `Location` values have the shape of little-endian EWKB points with SRID 4326. `AllTypes`, `Activities`, `TopReviews`, and `MediaInfo` parsed as JSON for all 972 rows. Opening-hour text includes unknown, all-day, closed, split-window, and overnight cases. Reference-price text includes zero cost, bounded VND ranges, an open-ended lower bound, and an unclassified value. These shapes are parser fixtures, not accepted domain contracts.

All rows share the same `CreatedAt` timestamp, while the filesystem modification time is later. The UUIDs, audit fields, and media URLs suggest an operational export, but that is an inference, not documented provenance. No repository file records:

- the data owner or exporting system;
- upstream tables and export query;
- snapshot/version identifier;
- license or permitted use of place data, review text, and media;
- how `Description` and `AiContext` were produced;
- lookup tables for province, category, type, vibe, or budget codes;
- refresh, retention, or deletion policy.

The file must remain byte-for-byte unchanged at its current path until a data owner completes that review. It is quarantined source material: it is not canonical IR, a runtime database, an evaluation set, or evidence that may be served to users. Do not move it to `travel-data/raw/` merely to match the target map. If the review rejects retention or chooses a different storage layout, a data ADR must supersede this part of the specification before cleanup.

### 5.2 `dataset/SoulViet_Dataset.csv` — DELETE FROM ACTIVE TREE, gated

This tracked file is already absent from the working tree but remains in `HEAD` and history.

- Git blob: `d5466c1155d2ade7f8a2f5904bb6dc96062d868a` (8,123,755 bytes).
- Introduced by commit `232d86b` (`clean data`) on 2026-04-10.
- Verified as 1,210 parsed records with 19 columns:

```text
PlaceId, Name, Type, AllTypes, Address, Lat, Lng, RatingScore,
ReviewCount, OperationHours, Description, MainImage, LandImages_JSON,
TopReviews_JSON, VibeTag, Generated_Description, Activities_JSON,
PriceCategory, PriceRange
```

All 928 non-null external IDs in the v2 file occur in the legacy file. The legacy file has 282 external IDs absent from v2, while v2 adds 44 rows without an external ID. V2 is therefore a curated or refreshed subset, not a demonstrated complete replacement.

A targeted audit also found a credential-like Google API value embedded in tracked legacy media URLs. The value must not be copied into new documentation or output. Removing the CSV from the active tree does not revoke the credential or remove it from Git history.

Before accepting the legacy CSV deletion, the data owner must document its upstream provenance and explain the 282 omitted records, and the credential owner must rotate or restrict the exposed value. The team must separately decide whether Git history can remain the archive or requires remediation. No raw-data deletion is performed by this specification task.

### 5.3 Current schema incompatibility

The current mapper cannot consume v2: it expects `Lat`/`Lng`, `PriceRange`, `Activities_JSON`, `TopReviews_JSON`, and `MainImage`, while v2 provides EWKB `Location`, `ReferencePrice`, `Activities`, `TopReviews`, and `MediaInfo`. This is another reason to remove the prototype rather than silently point it at the replacement file.

## 6. Source-code inventory

Every current `src/` file is listed below. All `REWRITE` items are removed during cleanup and remain available only through Git history until a later specification authorizes a replacement.

| Path | Classification | Reason / reusable concept |
|---|---|---|
| `src/__init__.py`; `src/graph/__init__.py`; `src/models/__init__.py`; `src/normalization/__init__.py`; `src/planning/__init__.py`; `src/retrieval/__init__.py`; `src/scoring/__init__.py`; `src/validation/__init__.py` | DELETE FROM ACTIVE TREE | Package markers and exports for the obsolete layout. Do not retain empty packages. |
| `src/graph/graph_store.py` | DELETE FROM ACTIVE TREE | Singleton runtime store hard-wired to `graph.pt` and `torch.load(..., weights_only=False)`. |
| `src/graph/graph_retriever.py` | REWRITE | Bounded traversal and traceability are candidates; current edge scores, depth, beam width, and graph schema are unevaluated placeholders. |
| `src/models/evidence.py` | REWRITE | Evidence is required, but this model lacks durable source, claim, version, and typed metadata contracts. |
| `src/models/graph_path.py` | REWRITE | Retrieval trace concepts may be useful after graph taxonomy and retrieval decisions. |
| `src/models/itinerary.py` | REWRITE | Omits authoritative opening windows, travel legs/times, evidence on selections, and validator-controlled acceptance. |
| `src/models/place.py` | REWRITE | Candidate-place vocabulary is useful, but this is neither canonical `PlaceIR` nor a validated retrieval contract. |
| `src/models/score_breakdown.py` | REWRITE | Score provenance is useful; the fields encode an unaccepted scoring design. |
| `src/models/user_request.py` | REWRITE | A normalized request is required, but current defaults hard-code product policy and taxonomy. |
| `src/models/validation_result.py` | REWRITE | A validation report is required, but current errors, metadata, and repair suggestions are weakly typed. |
| `src/normalization/place_normalizer.py` | REWRITE | Preserve numeric/JSON parsing cases. Do not preserve fabricated `0.0` coordinates, silent failure, or comma-splitting malformed JSON. It does not parse v2 EWKB. |
| `src/normalization/price_normalizer.py` | REWRITE | Preserve localized free/range fixture cases. Do not preserve mojibake matching, hard-coded price tiers, or treating an open-ended price as exact. |
| `src/planning/day_planner.py` | REWRITE | Duplicate prevention and explicit budget accounting are useful. Fixed 90-minute visits, zero travel, fixed slots, and acceptance of over-budget drafts are not. |
| `src/planning/route_optimizer.py` | REWRITE | The Haversine formula can become a tested geometry utility. Current greedy reordering changes slot meaning, omits travel duration/legs, creates random IDs, and freezes before validation. |
| `src/planning/slot_assigner.py` | REWRITE | Current meal/activity mappings are hard-coded, contain corrupted text, and ultimately accept any morning/afternoon candidate. |
| `src/retrieval/candidate_generator.py` | REWRITE | Mapping belongs behind compiler/source-adapter contracts and is incompatible with v2. Evidence references are always empty. |
| `src/retrieval/hard_filter.py` | REWRITE | Duplicate and explicit rejection concepts are useful. Destination, opening hours, time, budget, and other mandatory constraints are absent. |
| `src/scoring/place_scorer.py` | REWRITE | Uses unevaluated fixed weights and treats unknown price as free. |
| `src/scoring/reranker.py` | REWRITE | Mutates score objects and applies an unevaluated type-frequency penalty. |
| `src/scoring/utility_optimizer.py` | REWRITE | Fabricates a 10,000-VND cost and applies an unvalidated utility boost. |
| `src/validation/request_validator.py` | REWRITE | Positive finite budget is a useful rule. The 1–7 day bound and allowed-vibe set require explicit product/contract authority. |

### 6.1 Generated Python artifacts

Exactly 29 tracked `.pyc` files (66,089 bytes total) are **DELETE FROM ACTIVE TREE**:

- root `__pycache__/`: 1;
- `src/__pycache__/`: 1;
- `src/graph/__pycache__/`: 3;
- `src/models/__pycache__/`: 8;
- `src/normalization/__pycache__/`: 3;
- `src/planning/__pycache__/`: 4;
- `src/retrieval/__pycache__/`: 3;
- `src/scoring/__pycache__/`: 4;
- `src/validation/__pycache__/`: 2.

No cache path or `.pyc` file may remain tracked after cleanup.

## 7. Tests, fixtures, and reusable business rules

### 7.1 `tests/test_pipeline.py` — REWRITE

The repository has no standalone fixtures, golden files, evaluation data, schema tests, or parser tests. The only test file contains four `unittest` cases backed by inline `MagicMock` data:

- a prototype graph-to-itinerary flow;
- over-budget status labeling;
- type-blacklist filtering;
- invalid duration, budget, and vibe requests.

The five mock places (`P001`–`P005`) and six mock graph edges (`E001`–`E006`) may seed a future fixture only after encoding is corrected, place facts are marked synthetic or sourced, and destination, hours, duration, evidence, and travel-leg fields are added. The existing imports, expected status vocabulary, graph topology assumptions, and “frozen” behavior are not reusable.

The current test does not establish the required accepted-itinerary invariants: destination correctness, opening-hour feasibility, non-overlapping slots, represented travel legs and time, evidence on every selected place, validator authority, budget-safe acceptance, or reproducible core plans. It must be removed with `src/` and rewritten with the first owning vertical slice.

### 7.2 Review candidates worth carrying forward

These are reusable test inputs or rule candidates, not accepted implementations:

- strict parsing of UTF-8 CSV, literal `NULL`, JSON arrays/objects, EWKB Point/SRID 4326, bounded ratings, and review counts;
- price cases for free, bounded VND ranges, open-ended lower bounds, and unknown values;
- opening-hour cases for unknown, closed, all-day, split intervals, and overnight intervals;
- explicit rejection of malformed values instead of fabricated defaults;
- positive finite budget validation;
- duplicate selected-place rejection and explicit rejection reasons;
- deterministic ordering and tie-breaking;
- Haversine distance as a geometry estimate, never as authoritative road travel time;
- validation before state mutation or itinerary acceptance;
- retrieval fixtures with enough reachable candidates to make downstream assertions meaningful.

These current constants and policies are not accepted and must not be copied: vibe names or codes, duration caps, price tiers, score weights, graph decay, beam size/depth, diversity penalties, fixed slot taxonomy, 90-minute duration, retry counts, the 10,000-VND fallback, budget-utilization thresholds, and legacy status names.

The authoritative invariant set remains the one in `AGENTS.md`, not the behavior of this prototype.

## 8. Documentation inventory

### 8.1 Current authority

| Path | Classification | Reason |
|---|---|---|
| `README.md` | KEEP | Current product and architecture overview. |
| `AGENTS.md` | KEEP | Current agent workflow and boundary rules. |
| `docs/00-vision/00-project-vision.md` | KEEP | Product purpose and non-negotiable principles. |
| `docs/01-adr/0001-rebuild-from-engine-restructure.md` | KEEP | Accepted rebuild and archive decision; Section 13 records its triggered revisit condition. |
| `docs/status/current.md` | REWRITE | Keep as the sole status authority, activate this specification now, and update it again with cleanup results, verification, limitations, and the next slice. |
| `docs/04-spec/0001-repository-rebuild.md` | KEEP | Active scope for the structural cleanup. |

### 8.2 Obsolete legacy documents

All 23 paths below are **DELETE FROM ACTIVE TREE**. They are already absent in the working tree and must remain absent in the cleanup commit.

| Path | Why it must not remain authoritative |
|---|---|
| `docs/bugs/BUG_001_budget_status.md` | Couples a failing mock topology to an unaccepted 50% budget-utilization threshold and legacy status vocabulary. Preserve only the regression lesson recorded in Section 7. |
| `docs/plan/01_project_code_review.md` | Inventory of pre-restructure views, services, scripts, dataset, and `graph.pt`; source observations require re-verification. |
| `docs/plan/02_reference_learning_notes.md` | Large derivative research synthesis with speculative modules, infrastructure, and phases. |
| `docs/plan/03_architecture_decision.md` | Not an ADR; chooses controlled in-place migration and preservation of the old runnable MVP, directly superseded by ADR-0001. |
| `docs/plan/04_deterministic_itinerary_engine_design.md` | Obsolete pseudo-spec that predeclares a large tree and fixes unaccepted contracts, weights, slots, retries, and `graph.pt` runtime behavior. |
| `docs/plan/05_restructuring_plan.md` | Makes the obsolete design primary, retains `graph.pt`, preserves all legacy material, and scaffolds future modules. |
| `docs/plan/06_implementation_backlog.md` | Backlog derived from the obsolete design and placeholder module tree. |
| `docs/status/CURRENT_STATUS.md` | Superseded case variant that declares prototype components complete and records a failing legacy test. |
| `docs/status/soulviet_code_status_review.md` | Dated prototype review centered on old services, Groq, Neo4j, and `graph.pt`. |
| `docs/status/soulviet_implementation_plan.md` | Obsolete GraphRAG/chat/UI roadmap tied to the pre-restructure runtime and fixed scoring choices. |

The following `docs/repo_exp/` reports are also **DELETE FROM ACTIVE TREE**:

- `docs/repo_exp/RAG-Anything_for_graph.md`;
- `docs/repo_exp/Toonflowapp_for_graph.md`;
- `docs/repo_exp/Understand-Anything_for_graph.md`;
- `docs/repo_exp/ai-agents-for-beginners_for_graph.md`;
- `docs/repo_exp/awesome-llm-apps_for_graph.md`;
- `docs/repo_exp/colleague-skill_for_graph.md`;
- `docs/repo_exp/container-bay-plan-validator_for_graph.md`;
- `docs/repo_exp/conversational-state-machine_for_graph.md`;
- `docs/repo_exp/e-commerce-project_for_graph.md`;
- `docs/repo_exp/graphrag-code_for_graph.md`;
- `docs/repo_exp/medical-citation-agent_for_graph.md`;
- `docs/repo_exp/system-prompts-and-models-of-ai-tools_for_graph.md`;
- `docs/repo_exp/vibe-kanban_for_graph.md`.

They are generated cross-repository research, not SoulViet decisions. They contain unusable internal citation markers, time-sensitive external observations, unaccepted composite stacks, explicit speculation where source code was unavailable, overlapping material, and in one case prompt residue. No vendored implementation or verified project fixture is present. If a future decision needs those subjects, research primary sources in that focused ADR/evaluation task.

After deletion, `docs/bugs/`, `docs/plan/`, and `docs/repo_exp/` disappear naturally because Git does not track empty directories.

### 8.3 Empty documentation scaffolding

The physical working tree contains these empty directories:

| Directory | Classification | Decision |
|---|---|---|
| `docs/02-architecture/` | DELETE FROM ACTIVE TREE | Recreate only when an accepted architecture description exists. |
| `docs/03-guides/` | DELETE FROM ACTIVE TREE | Recreate only with a real workflow guide. |
| `docs/04-spec/` | KEEP | This specification makes the directory non-empty. |
| `docs/05-internals/` | DELETE FROM ACTIVE TREE | No current internal document exists. |
| `docs/06-api-reference/` | DELETE FROM ACTIVE TREE | No accepted API exists. |
| `docs/07-contributing/` | DELETE FROM ACTIVE TREE | No current contributing document exists. |
| `docs/someday/` | DELETE FROM ACTIVE TREE | Do not retain an empty speculative bucket. |

## 9. Exact cleanup operations

### 9.1 Preconditions

1. Create and check out `rebuild/career-os-v2` from `feat/engine-restructure-wip`; do not commit this specification or cleanup on a legacy branch.
2. Record the pre-cleanup commit IDs of all existing branch refs and verify they remain unchanged.
3. Resolve the credential rotation/restriction action and document the Git-history decision.
4. Obtain data-owner confirmation for both CSV snapshots, including the 282-record difference, source/license, and retention decision.
5. If either blocking decision changes this specification’s data or history assumptions, supersede or amend the specification before deleting data.

### 9.2 Retain or add

- retain `README.md`, `AGENTS.md`, the vision, ADR-0001, and lowercase current status;
- retain this specification;
- retain `dataset/data-tourist-attraction-v2.csv` unchanged only if its review permits repository retention;
- stage the `CURRENT_STATUS.md` to `current.md` case transition so only the lowercase path remains tracked.

### 9.3 Rewrite during cleanup

Rewrite `.gitignore` to cover, at minimum:

```text
.env
.env.*
!.env.example
.agents/
.venv/
venv/
myenv/
__pycache__/
*.py[cod]
.pytest_cache/
.mypy_cache/
.ruff_cache/
.coverage
coverage.xml
htmlcov/
graph.pt
travel-data/generated/
```

Update `docs/status/current.md` in the cleanup commit with completed acceptance criteria, verification performed, limitations, and the next approved documentation/vertical slice.

### 9.4 Remove

- `app.py`, `graph.pt`, `index.html`, and `requirements.txt`;
- the complete current `src/` tree;
- `tests/test_pipeline.py` and the resulting empty `tests/` directory;
- all tracked `__pycache__/` directories and `.pyc` files;
- `dataset/SoulViet_Dataset.csv`, but only after the data and security gates above;
- all legacy documents in Section 8.2;
- all empty placeholder directories in Section 8.3 except `docs/04-spec/`.

Do not create replacement source, dependency metadata, tests, interfaces, indexes, data products, or future target directories in this commit. Do not create `legacy/`.

Ignored `.agents/`, `.env`, and `myenv/` are local workspace state, not tracked cleanup operations. Any physical removal must be separately intentional and is not needed for the commit to satisfy this specification.

## 10. Exact minimum tracked tree after cleanup

Provided the v2 data review permits repository retention, the cleanup commit must leave exactly this minimum tracked tree:

```text
.
├── .gitignore
├── AGENTS.md
├── README.md
├── dataset/
│   └── data-tourist-attraction-v2.csv
└── docs/
    ├── 00-vision/
    │   └── 00-project-vision.md
    ├── 01-adr/
    │   └── 0001-rebuild-from-engine-restructure.md
    ├── 04-spec/
    │   └── 0001-repository-rebuild.md
    └── status/
        └── current.md
```

`.git/`, ignored `.agents/`, ignored `.env`, and ignored developer environments are intentionally not shown. There is no `pyproject.toml`, application, package, service, agent, knowledge, script, test, generated-data, UI, or empty placeholder directory yet.

If the v2 data review does not permit repository retention, do not silently omit or delete it. Accept a data ADR, update this specification and the exact tree, and preserve the reviewed snapshot in the approved versioned store before cleanup.

## 11. Cleanup commit acceptance criteria

### Branch and history safety

- [ ] The cleanup is committed only on `rebuild/career-os-v2` created from the recorded `feat/engine-restructure-wip` base.
- [ ] Existing local and remote legacy branch refs are unchanged.
- [ ] No `legacy/` directory or copied legacy source is introduced.
- [ ] The credential-like value has been rotated/restricted, a focused secret audit has been completed, and the history-retention/remediation decision is recorded.

### Exact tree and hygiene

- [ ] The tracked file list matches Section 10, except for substantive ADRs accepted before cleanup.
- [ ] `graph.pt` is not tracked and no retained runtime code loads it; historical mentions only describe its removal.
- [ ] No tracked `__pycache__/`, `.pyc`, `.env`, virtual environment, tool cache, generated index, or build output remains.
- [ ] `.gitignore` prevents the audited generated/local artifacts from being re-added.
- [ ] `app.py`, `index.html`, `requirements.txt`, `src/`, and `tests/` are absent.
- [ ] No `packages/`, `services/`, `apps/`, agents, GraphRAG code, or placeholder target directories were created.

### Data safety

- [ ] Both CSV schemas, lineage, source owner, license/usage rights, snapshot identity, and retention decision are documented.
- [ ] The 282 legacy-only external IDs and 44 v2 rows without external IDs have an explicit disposition.
- [ ] The retained v2 file is byte-for-byte unchanged from its reviewed version, with its row count and checksum recorded.
- [ ] The retained CSV is explicitly marked as quarantined source material, not canonical IR or a runtime source of truth.
- [ ] No raw dataset was destroyed before an approved preservation and provenance decision.

### Documentation authority

- [ ] Only lowercase `docs/status/current.md` is tracked; the uppercase legacy variant is absent on case-sensitive and case-insensitive checkouts.
- [ ] Every document in Section 8.2 is absent from the active tree.
- [ ] README, AGENTS, vision, accepted ADRs, this specification, and current status do not conflict about the active phase or runtime.
- [ ] `docs/status/current.md` records cleanup results, checks performed, known limitations, and the next approved scope.

### Verification

- [ ] The exact tracked-tree comparison passes.
- [ ] A repository scan for forbidden paths and generated artifacts passes.
- [ ] A repository scan finds no active runtime dependency on `graph.pt`.
- [ ] CSV shape, checksum, encoding, and structured-field parse checks pass for the retained snapshot.
- [ ] No production test suite is claimed: the cleanup contains no executable engine. Verification is structural, documentation, data-integrity, and secret-hygiene focused.

## 12. Known limitations of this specification

- The data audit establishes file shape, not factual correctness, completeness, freshness, license, or permission to use reviews and media.
- The targeted credential finding is not a complete repository-history secret audit.
- The old and replacement datasets cannot yet be declared source-of-truth snapshots.
- No legacy constant, threshold, taxonomy, score, or test expectation has been accepted as a new product contract.
- No Python version, packaging tool, framework, database, vector store, graph store, LLM provider, or workflow engine is selected here.

## 13. Decisions requiring separate ADRs

The first two decisions block or can change cleanup and must be addressed before the structural deletion commit:

1. **Repository secret and Git-history remediation.** Decide whether credential rotation/restriction is sufficient or whether history/branches must be rewritten. This is an explicit revisit trigger for ADR-0001 and cannot be handled by deleting the active CSV alone.
2. **Travel-data provenance and snapshot policy.** Decide the authoritative source owner, relationship between the two CSVs and operational backend, license/UGC rules, stable identity, versioning, retention, repository versus external storage, and whether/when `dataset/` becomes `travel-data/raw/`.

The following ADRs are required before their owning implementation slices:

3. **Python workspace and packaging:** supported Python version, package layout, dependency declaration, locking, and test tooling.
4. **Canonical Travel IR and schema validation:** identifiers, `PlaceIR`, evidence, money, opening windows, normalized requests, candidates, itineraries, travel legs, validation reports, and versioning.
5. **Ontology and graph ownership:** node/edge taxonomy, mapping ownership, and resolution of README’s proposed `packages/graph` versus the boundaries currently defined in `AGENTS.md`.
6. **Source adapter and changing-fact policy:** operational source contract, EWKB/JSON parsing failures, source timestamps, evidence rights, and freshness for prices, hours, routes, and weather.
7. **Money and scheduling semantics:** total-trip versus per-day/per-person budget, open-ended prices, timezone, overnight/split hours, visit-duration sources, and unknown-value behavior.
8. **Initial retrieval baseline and evaluation:** structured retrieval scope, fixture ownership, relevance/evidence metrics, deterministic tie-breaking, and the evidence required before adding lexical, vector, or graph retrieval.
9. **Derived-index infrastructure:** graph/vector/lexical technology choices, versioning, rebuild process, storage, and failure behavior. `graph.pt` is excluded regardless of the choice.
10. **Workflow and model-provider boundary:** typed state machine, bounded tools/repairs, provider selection, timeouts, observability, and evaluation gates.
11. **Delivery and persistence contract:** backend-to-engine API versioning, identity/idempotency, execution policy, itinerary persistence ownership, and deterministic versus operational identifiers.

Until these decisions are accepted, the next implementation scope must remain a written, measurable vertical slice rather than a global engine scaffold.
