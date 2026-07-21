# SoulViet AI Engine — Project Vision

## 1. Why this system exists

Travel planning is not a text-generation problem.

A useful itinerary must combine factual place data, semantic preferences, relationships between places, live constraints, route feasibility, time windows, and budget. A fluent answer that violates these constraints is a failed plan.

SoulViet AI Engine exists to produce travel plans that are:

- personalized;
- feasible;
- evidence-grounded;
- explainable;
- repairable;
- suitable for product integration.

---

## 2. Product promise

A user should be able to describe a trip naturally and receive a structured itinerary whose core claims can be traced to data.

The system should answer not only:

> Where should I go?

It should also answer:

- Why does this place fit me?
- Is it open at the planned time?
- Can I reach the next stop reasonably?
- Does the complete trip fit my budget?
- What evidence supports this recommendation?
- What can be replaced when I change one preference?

---

## 3. Core system model

SoulViet is built around compiled travel knowledge.

```text
Raw sources
    |
    v
Travel Knowledge Compiler
    |
    v
Canonical Travel IR
    |
    +--> structured read model
    +--> graph index
    +--> lexical index
    +--> vector index
    |
    v
Hybrid retrieval
    |
    v
Deterministic planning and validation
    |
    v
Bounded agentic explanation and repair
```

Canonical IR is the contract between ingestion and runtime.

---

## 4. Knowledge model

The initial domain is expected to represent concepts including:

- Place
- Province or destination
- Category
- Type
- Activity
- Vibe
- Cultural theme
- Time suitability
- Price range
- Opening window
- Evidence
- Travel relation

Expected relationship classes include:

- `LOCATED_IN`
- `IN_CATEGORY`
- `HAS_TYPE`
- `OFFERS_ACTIVITY`
- `HAS_VIBE`
- `REPRESENTS`
- `SUITABLE_AT`
- `NEAR`
- `SUPPORTED_BY`

The final taxonomy and edge rules must be accepted through architecture documentation and tests.

---

## 5. Retrieval vision

No single retrieval strategy is sufficient.

SoulViet will support a query-dependent combination of:

- structured filtering for hard constraints;
- lexical retrieval for exact names and terms;
- vector retrieval for semantic preference;
- graph retrieval for relations and multi-hop context;
- live tools for changing information such as route duration or weather.

Results are fused into typed candidates with provenance.

GraphRAG is an evidence-retrieval subsystem. It does not create or validate the final schedule.

---

## 6. Planning vision

The planner receives typed candidates and produces `ItineraryIR`.

Planning must account for:

- day and time windows;
- opening hours;
- estimated duration at each place;
- travel legs;
- total and per-day budget;
- activity diversity;
- required meal slots;
- traveler constraints;
- tier-based execution limits supplied by the backend.

Core arithmetic and feasibility decisions are deterministic.

---

## 7. Agentic vision

SoulViet uses bounded agents, not autonomous database-owning agents.

Initial agentic responsibilities may include:

- request understanding;
- retrieval strategy selection;
- semantic evidence grading;
- query repair;
- itinerary repair proposal;
- explanation of validated output.

The orchestration layer should be a typed state machine. An LLM is used only where probabilistic reasoning creates measurable value.

---

## 8. Evidence and trust

Every recommendation should preserve:

- canonical place ID;
- retrieval source;
- evidence references;
- ranking or relevance signals;
- validation result;
- data or index version where practical.

The product should be able to explain why a place was selected without asking the model to reconstruct a justification after the fact.

---

## 9. Integration boundary

The SoulViet backend owns identity, subscription, payment, quota, and product-facing itinerary persistence.

The AI Engine receives:

- a normalized or normalizable trip request;
- a signed internal identity and request context;
- an execution entitlement or policy;
- a request and idempotency identifier.

The AI Engine returns:

- structured itinerary data;
- evidence references;
- validation status;
- usage and execution metadata;
- explicit errors.

The frontend must not call the AI Engine directly.

---

## 10. Non-goals for the first release

The first release does not need:

- many specialized agents;
- fully autonomous web research;
- unbounded long-term memory;
- multimodal document ingestion;
- dynamic ontology mutation by an LLM;
- microservices for every component;
- perfect global route optimization;
- every planned directory populated.

The first goal is one reliable, measurable vertical slice.

---

## 11. First success scenario

Given:

- one supported destination;
- one day;
- a fixed budget;
- a small preference set;

the system must:

1. retrieve valid candidates;
2. produce a feasible structured itinerary;
3. stay within hard constraints;
4. attach evidence to every selected place;
5. pass deterministic validation;
6. work without LLM-generated travel facts;
7. produce reproducible core planning results.

Agentic behavior is added after this baseline works.
