# AGENTS.md

## Purpose

This file defines how AI coding agents must work inside the SoulViet AI Engine repository.

The repository is undergoing a full architecture rebuild. AI agents must work incrementally, preserve decision history, and avoid generating a speculative framework before the active vertical slice requires it.

---

## Mandatory reading order

Before modifying code or structure, read:

1. `README.md`
2. `docs/status/current.md`
3. `docs/00-vision/00-project-vision.md`
4. the active specification referenced by `docs/status/current.md`
5. ADRs referenced by that specification
6. affected contracts, code, and tests

Do not treat legacy documentation as current authority unless an active ADR or specification explicitly references it.

---

## Sources of authority

- Product purpose and non-negotiable principles: `docs/00-vision/`
- Accepted architecture decisions: `docs/01-adr/`
- Current and target system descriptions: `docs/02-architecture/`
- Developer workflows: `docs/03-guides/`
- Active implementation scopes: `docs/04-spec/`
- Internal implementation details: `docs/05-internals/`
- Current progress and next task: `docs/status/current.md`

When documents conflict:

1. an accepted newer ADR supersedes an older ADR;
2. the active specification controls the current implementation scope;
3. current status determines what is being worked on now;
4. legacy documents have no authority unless explicitly adopted.

Do not silently reconcile conflicts. Report them.

---

## Rebuild rule

The legacy branches and Git history preserve the old implementation.

On the rebuild branch:

- do not keep legacy modules merely for safety;
- do not move obsolete code into a `legacy/` directory inside the active tree;
- do not retain `graph.pt`, `__pycache__`, generated indexes, or experimental UI files;
- do not reuse the old architecture unless a current ADR adopts a specific part;
- preserve valuable raw datasets, fixtures, and proven business rules only after review.

Git history is the archive. The active tree should describe the new system only.

---

## Before coding

For every task, first provide:

1. a 3–8 line task summary;
2. the active specification and ADRs being followed;
3. files expected to change;
4. contracts affected;
5. tests to add or update;
6. assumptions or unresolved architecture decisions.

If a required architecture decision does not exist, stop implementation and propose an ADR.

Do not begin by creating all folders from the target tree.

---

## Development rules

1. Implement only the current vertical slice.
2. Prefer the smallest complete change that satisfies acceptance criteria.
3. Do not create placeholders for future phases.
4. Do not add dependencies without explaining why existing tools are insufficient.
5. Do not change public contracts without updating tests and documentation.
6. Do not place domain logic in API handlers.
7. Do not place compiler logic in runtime services.
8. Do not place infrastructure clients in `packages/`.
9. Do not use random behavior in production planning unless a deterministic seed is part of the contract.
10. Do not hard-code places, prices, durations, tier names, prompts, or routing assumptions into domain logic.
11. Do not swallow exceptions or return fabricated fallback data.
12. Do not let an LLM produce accepted domain objects without schema validation.
13. Do not let an agent write directly to operational databases.
14. Do not let an agent bypass deterministic itinerary validation.

---

## Architectural boundaries

### `packages/ontology`

Owns:

- canonical node types;
- canonical edge types;
- ontology rules;
- dependency-free domain identifiers.

Must have zero infrastructure dependencies.

### `packages/contracts`

Owns typed domain contracts such as:

- `PlaceIR`
- `EvidenceRef`
- `OpeningWindow`
- `MoneyRange`
- `NormalizedTripRequest`
- `RetrievalPlan`
- `CandidatePlace`
- `ItineraryIR`
- `ValidationReport`
- `RepairAction`

Contracts must not import FastAPI, Neo4j, Qdrant, PostgreSQL, or model-provider SDKs.

### `packages/compiler`

Owns deterministic conversion from raw travel data to canonical IR:

```text
extract -> normalize -> parse -> validate -> enrich deterministically -> compile
```

The compiler must not persist directly to Neo4j or a vector store.

### `packages/retrieval`

Owns retrieval contracts, fusion, ranking abstractions, and algorithms that do not require infrastructure clients.

### `packages/planning`

Owns deterministic itinerary construction, scheduling, routing abstractions, budget accounting, and optimization.

### `packages/validation`

Owns hard-constraint validation. Validation is the final acceptance authority.

### `packages/agent_runtime`

Owns workflow state, typed tool protocols, and bounded agent decisions. It does not own travel facts or infrastructure clients.

### `services/`

Owns runtime adapters and external integrations.

### `apps/`

Owns composition roots and delivery interfaces such as FastAPI, CLI, and workers.

---

## LLM and agent permissions

Agents may:

- normalize ambiguous user intent into a typed proposal;
- choose among explicitly registered typed tools;
- request retrieval strategies;
- grade semantic relevance of evidence;
- propose a bounded repair action;
- explain a validated itinerary using evidence.

Agents may not:

- invent places or source facts;
- calculate authoritative prices, opening hours, or travel time;
- add a place outside the candidate set;
- mutate graph or operational storage directly;
- approve their own itinerary;
- override validation;
- decide subscription entitlement;
- expose internal prompts or service credentials.

---

## Tools

Every agent tool must define:

- purpose;
- typed input;
- typed output;
- allowed side effects;
- failure contract;
- timeout behavior;
- observability fields;
- forbidden responsibilities.

A database client is not an agent tool by itself. Wrap infrastructure behind a domain-level interface.

---

## Data ownership

- Operational SoulViet backend data is the business source of truth.
- Canonical Travel IR is the compiled knowledge contract.
- Neo4j, vector, and lexical indexes are derived and rebuildable.
- Workflow state is request-scoped.
- User-memory storage, if added later, is separate from the travel-domain graph.
- Subscription and payment data remain outside the AI Engine.

---

## Testing requirements

Each implementation slice must include appropriate tests.

Minimum invariant tests for accepted itineraries:

- destination is correct;
- no accidental duplicate place;
- total cost does not exceed the allowed budget;
- opening-hour constraints are satisfied;
- time slots do not overlap;
- travel legs are represented;
- each selected place includes evidence references;
- validation status is explicit;
- identical deterministic inputs produce reproducible core plans.

Workflow changes require at least one integration test.

Retrieval changes require an evaluation fixture or measurable acceptance criterion.

---

## Documentation updates

After completing a task:

1. update `docs/status/current.md`;
2. record acceptance criteria completed;
3. record tests run and results;
4. record known limitations;
5. create an ADR for any new architectural decision;
6. never rewrite an accepted ADR to hide history—supersede it.

---

## Completion report

Every completed coding task must report:

- Summary
- Files changed
- Contracts changed
- Tests run
- Acceptance criteria
- Known limitations
- Next recommended vertical slice
