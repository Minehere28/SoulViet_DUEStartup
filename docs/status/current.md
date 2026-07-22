# Current Status

## Phase

**Phase 1 — Canonical Travel IR compiler slice (implementation complete; awaiting commit)**

## Completed Phase 0 — Repository and architecture foundation

The rebuild branch is active:

```text
rebuild/career-os-v2
```

Completed repository milestones:

- `104c411` — foundation documents established;
- `760841a` — legacy dataset replaced by `dataset/data-tourist-attraction-v2.csv`;
- `185239a` — legacy prototype runtime, experimental UI, old tests, `graph.pt`, and tracked Python bytecode removed.

Phase 0 acceptance criteria are complete:

- [x] `rebuild/career-os-v2` exists and legacy branches remain unchanged.
- [x] README, AGENTS, vision, ADR-0001, current status, and the repository-rebuild specification establish the rebuild authority.
- [x] Legacy runtime modules and obsolete documents no longer appear authoritative in the active tree.
- [x] The active tree contains no tracked `__pycache__` or Python bytecode.
- [x] `graph.pt` is not part of the runtime design or active tree.
- [x] The next implementation scope is a written vertical slice rather than a global rewrite.

The legacy system remains recoverable through Git history and preserved branches. It is not implementation authority.

## Active specification

```text
docs/04-spec/0002-canonical-travel-ir-compiler.md
```

The active specification is governed by:

- `docs/01-adr/0001-rebuild-from-engine-restructure.md`;
- `docs/01-adr/0002-python-workspace-and-package-boundaries.md`;
- `docs/01-adr/0003-canonical-travel-ir.md`.

## Active objective

Review and commit the completed compiler vertical slice:

```text
small source-derived CSV fixture
-> source-row adapter
-> deterministic parsers
-> PlaceIR compiler
-> validation report
-> JSON output through CLI
```

The exact workspace members, contracts, compiler, CLI, six-record fixture, provenance manifest, and tests named in Specification 0002 are implemented. The complete dataset was inspected only and remains unchanged.

## Completed Phase 1 acceptance criteria

- [x] Python 3.11 uv workspace, local dependency direction, and committed lockfile are defined.
- [x] The implementation tree matches the Specification 0002 creation manifest with no future placeholder directory.
- [x] The fixture contains exactly six complete unchanged source records and provenance metadata with verified hashes.
- [x] All 25 reviewed headers are required; additional headers are retained and reported deterministically.
- [x] `RawSourceContext` is created without parsing canonical `Id`; `place_compiler.py` owns canonical identity parsing.
- [x] Invalid `Id` produces `place=None` with an ordered fatal issue and no canonical provenance object.
- [x] ADR-0003 canonical contracts and deterministic JSON serialization are implemented with strict typing.
- [x] EWKB coordinates, fixed-point ratings, VND money, opening schedules, source taxonomy, JSON arrays, reviews, media, and timestamps are parsed deterministically.
- [x] Unknown, free, closed, all-day, normal, split, and overnight values remain distinct.
- [x] Evidence references and raw provenance are retained; `AiContext` remains provenance-only.
- [x] CLI output is atomic and deterministic with exit codes 0, 1, and 2.
- [x] Runtime code has no third-party dependency, network access, persistence, generated index, or out-of-scope component.

## Verification record

- `uv lock` — passed; 16 packages resolved and `uv.lock` generated.
- `uv sync --all-packages --dev` — passed; all three workspace members installed in the verification environment.
- `uv run ruff format --check .` — passed; 16 Python files formatted.
- `uv run ruff check .` — passed.
- `uv run mypy packages/contracts/src packages/compiler/src apps/cli/src` — passed with no issues in 9 source files.
- `uv run pytest` — passed: 33 tests.
- Two compact `soulviet-compile-fixture` runs exited 0 and produced byte-identical output with SHA-256 `05679D85C7865957D931DCB46BC7CB94279EB797E026EB9D625A8948BED71870`.
- Fixture extraction was verified byte-for-byte against source rows 2, 4, 17, 37, 49, and 205.
- Complete dataset SHA-256 remains `38446971E7DF40E70475CC0FDD470F448FE6F3E838427FE5C94097376089F806`.

## Next task

Commit the verified Phase 1 slice without adding generated caches or tool environments. Before implementing another capability, write and accept a focused specification for the next measurable vertical slice; the current recommendation remains a structured retrieval baseline over compiled fixture IR.

## Known limitations and deferred decisions

- Dataset source ownership, licensing, review/media rights, freshness, and the relationship to upstream operational data remain unresolved. The compiler preserves provenance but does not establish factual authority.
- Repository-secret and Git-history remediation remain a separate security decision; no secret value is reproduced in active documentation.
- Ontology mappings for province/category/vibe/type codes are intentionally deferred; Phase 1 uses source-token normalization only.
- Structured retrieval baseline and evaluation, derived-index infrastructure, planning/validation semantics, workflow/model-provider boundaries, and backend delivery/persistence contracts remain future ADRs/slices.
- The supplied dataset has no single record combining `Từ 500.000đ` with split opening hours; fixture coverage is collective across the open-ended-price record and the closed/split-window record, as permitted by Specification 0002.
