# SoulViet AI Engine

> Evidence-grounded, constraint-aware travel itinerary planning using hybrid GraphRAG and bounded agentic workflows.

SoulViet AI Engine is the planning and retrieval subsystem behind the SoulViet travel platform. It converts normalized travel knowledge and live constraints into feasible, explainable, and versioned itineraries.

This repository is being rebuilt from first principles. The previous prototype remains available in Git history and archived branches, but its runtime architecture is not the authority for the new system.

---

## Project status

The project is currently in **Phase 1 — Canonical Travel IR compiler slice**.

The active specification is:

`docs/04-spec/0002-canonical-travel-ir-compiler.md`

No new production engine should be implemented until the foundational documents, domain boundaries, and first vertical slice have been reviewed.

Current status:

- Legacy branches are preserved.
- The active rebuild branch is `rebuild/career-os-v2`.
- `graph.pt` is absent from the active tree and is not part of the runtime design.
- The old deterministic-engine design is reference material only.
- The new architecture follows a compiler-first, canonical-IR approach inspired by Career OS.
- The final system will combine hybrid GraphRAG, deterministic planning, validation, and bounded agentic orchestration.

See [`docs/status/current.md`](docs/status/current.md).

---

## Product goal

Given a user's travel request, SoulViet must produce an itinerary that:

- stays within the selected destination;
- respects budget and trip duration;
- respects opening hours and time windows;
- accounts for travel time;
- matches activities, vibe, and traveler preferences;
- avoids accidental duplication and infeasible schedules;
- explains why each place was selected;
- attaches evidence to recommendations;
- supports later refinement without silently breaking constraints.

---

## Architectural thesis

SoulViet separates knowledge compilation, retrieval, planning, validation, and language generation.

```text
Operational travel data and documents
                |
                v
       Travel Knowledge Compiler
                |
                v
        Canonical Travel IR
          /      |       \
         v       v        v
 Relational   Graph     Search indexes
 read model   index     lexical/vector
         \       |        /
          \      |       /
           Hybrid Retrieval
                  |
                  v
          CandidatePlace[]
                  |
                  v
     Deterministic Itinerary Planner
                  |
                  v
            Validator
           /         \
        PASS          FAIL
         |             |
         v             v
 Explanation     Bounded repair loop
         \             /
          \           /
           ItineraryIR
```

GraphRAG retrieves relationships and evidence. It does not replace the itinerary optimizer.

Agents may understand requests, choose typed tools, grade evidence, request repairs, and explain accepted plans. Agents do not own travel facts and cannot bypass deterministic validation.

---

## Core principles

1. **Travel knowledge first**  
   LLM output is not a source of truth.

2. **Compile before retrieval**  
   Raw records must be normalized into canonical IR before indexing.

3. **Indexes are derived artifacts**  
   Graph, vector, and lexical indexes must be rebuildable.

4. **Hard constraints precede preferences**  
   Destination, opening hours, budget, time, and route feasibility are enforced by code.

5. **Graph for relations, vector for meaning**  
   Retrieval modes solve different classes of queries.

6. **Agents use typed tools**  
   Agents never access databases directly.

7. **Validator is the final authority**  
   An itinerary is not accepted until deterministic validation passes.

8. **Evidence travels with recommendations**  
   Every selected place must retain evidence references and scoring provenance.

9. **Plan before presentation**  
   `ItineraryIR` must exist independently of chat, web, or mobile rendering.

10. **Evaluation before complexity**  
    New agents, retrievers, rerankers, and algorithms require measurable benefit.

---

## System boundaries

### SoulViet Backend

The main SoulViet backend owns:

- authentication and users;
- subscriptions and payments;
- quota reservation and settlement;
- itinerary persistence visible to the product;
- signed internal requests to the AI Engine.

### SoulViet AI Engine

The AI Engine owns:

- request normalization;
- retrieval planning and routing;
- structured, lexical, vector, and graph retrieval;
- evidence fusion and reranking;
- itinerary planning and route optimization;
- deterministic validation;
- bounded repair workflows;
- explanation from accepted evidence;
- execution metrics returned to the backend.

The AI Engine must not read or mutate payment tables.

---

## Target repository structure

This structure is a target map. Do not create empty modules before an active implementation slice needs them.

```text
.
├── README.md
├── AGENTS.md
├── pyproject.toml
├── apps/
│   ├── api/
│   ├── cli/
│   └── worker/
├── packages/
│   ├── ontology/
│   ├── contracts/
│   ├── compiler/
│   ├── graph/
│   ├── retrieval/
│   ├── planning/
│   ├── validation/
│   └── agent_runtime/
├── services/
│   ├── postgres/
│   ├── neo4j/
│   ├── vector_store/
│   ├── lexical_search/
│   ├── maps/
│   ├── embedding/
│   └── llm/
├── travel-data/
│   ├── raw/
│   ├── fixtures/
│   └── generated/
├── knowledge/
├── docs/
│   ├── 00-vision/
│   ├── 01-adr/
│   ├── 02-architecture/
│   ├── 03-guides/
│   ├── 04-spec/
│   ├── 05-internals/
│   ├── 06-api-reference/
│   ├── 07-contributing/
│   ├── status/
│   └── someday/
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── golden/
│   └── evals/
└── scripts/
```

---

## Dependency direction

```text
apps -> services -> packages
```

Forbidden dependency directions:

```text
packages -> services
packages -> FastAPI
ontology -> database drivers
planning -> LLM provider SDK
validation -> agent runtime
```

`packages/ontology` must have zero infrastructure dependencies.

---

## AI-agent reading order

Before writing code, read:

1. `README.md`
2. `AGENTS.md`
3. `docs/status/current.md`
4. `docs/00-vision/00-project-vision.md`
5. the active specification under `docs/04-spec/`
6. ADRs referenced by that specification
7. relevant contracts and tests

Do not read every legacy document and treat it as current authority.

---

## Planned implementation sequence

1. Repository foundation and legacy cleanup.
2. Canonical contracts and ontology.
3. Travel Knowledge Compiler.
4. Structured retrieval baseline.
5. Lexical and vector retrieval.
6. Graph indexing and GraphRAG retrieval.
7. Hybrid fusion and evidence grading.
8. Deterministic planner and validator.
9. Bounded agentic repair workflow.
10. Backend integration and execution policy.

Each phase must produce a testable vertical slice.

---

## Development commands

Commands are intentionally not fixed yet. They will be introduced with `pyproject.toml`, the initial package layout, and the first executable slice.

Until then, do not invent commands in documentation.
