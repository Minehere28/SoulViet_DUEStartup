# Current Status

## Phase

**Phase 1 — Canonical Travel IR compiler slice**

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

Implement the smallest complete compiler vertical slice:

```text
small source-derived CSV fixture
-> source-row adapter
-> deterministic parsers
-> PlaceIR compiler
-> validation report
-> JSON output through CLI
```

The first implementation task is to create exactly the workspace members, contracts, compiler, CLI, fixture, and tests named in Specification 0002. It must use only the small fixture and must not modify or process the complete dataset.

## Work allowed in Phase 1

Allowed:

- create the Python 3.11 uv workspace and only the files named by Specification 0002;
- implement standard-library canonical contracts, deterministic source parsing, report serialization, and CLI file output;
- add the source-derived fixture and its provenance manifest;
- add pytest, strict mypy, Ruff, unit, architecture-boundary, and CLI integration tests;
- update this status document with implementation results.

Not allowed:

- FastAPI, web routes, workers, Neo4j, Qdrant, databases, persistence, GraphRAG, vector search, BM25, embeddings, model providers, LangGraph, or agents;
- itinerary planning, routing, recommendation, live data, full-dataset migration, or generated indexes;
- package, service, or application folders not named by Specification 0002;
- changes to `dataset/data-tourist-attraction-v2.csv`;
- Git commit or push commands as part of the implementation task.

## Latest design-foundation record

- ADR-0002 selects Python 3.11, a PEP 621 uv workspace, package boundaries, pytest, strict mypy, Ruff, and a CLI composition root.
- ADR-0003 defines canonical `PlaceIR`, identity, provenance, fixed-point coordinates, money, opening schedules, evidence, media, and compilation issues/results.
- Specification 0002 defines the complete fixture-to-JSON compiler slice, exact files, CLI contract, parser rules, failure behaviour, tests, and acceptance criteria.
- No application code, package folder, dependency resolution, dataset change, Git commit, or push was performed by the design task.

## Known limitations and deferred decisions

- Dataset source ownership, licensing, review/media rights, freshness, and the relationship to upstream operational data remain unresolved. The compiler preserves provenance but does not establish factual authority.
- Repository-secret and Git-history remediation remain a separate security decision; no secret value is reproduced in active documentation.
- Ontology mappings for province/category/vibe/type codes are intentionally deferred; Phase 1 uses source-token normalization only.
- Structured retrieval baseline and evaluation, derived-index infrastructure, planning/validation semantics, workflow/model-provider boundaries, and backend delivery/persistence contracts remain future ADRs/slices.
