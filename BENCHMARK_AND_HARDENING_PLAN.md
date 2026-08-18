# SoulViet Agent Benchmark and Hardening Plan

## Goal

Make the assistant autonomously produce a useful itinerary from a natural travel
request, while preserving hard constraints, minimizing unnecessary travel, and
never claiming success for an uncommitted draft.

The acceptance source of truth is
`benchmarks/agent_quality_cases.json`. The existing 35-case schema benchmark
remains useful, but it only proves that a payload can be validated; it does not
prove that the live model selects the payload or that the resulting itinerary is
good.

## Baseline confirmed on 2026-08-17

- Benchmark manifest: 10 end-to-end cases.
- Benchmark/evaluator tests: 40 passed together with the existing 35-case suite.
- Live `hoi_an_autoplan_without_clarification`: failed.
- Live agent state: `iterations=1`, `tool_calls=0`, `committed=false`, no
  validation report.
- Root behavior: the prompt asks the model to use tools, but the harness permits
  the first model response to end without a tool call.
- Current request schema can represent province-level `region`, but cannot
  represent a city/locality focus such as Hội An.
- A mutation is automatically replanned once. If validation is `partial`, the
  graph finalizes immediately instead of returning the report to a repair loop.
- Candidate ranking and multi-day assignment are still mostly score-first;
  route cost is optimized after the candidate pool has already been narrowed.

## Quality gates

No production phase is complete until all of these hold:

1. Existing unit suite stays green.
2. Existing 35 payload cases stay green.
3. The 10 live quality cases pass twice consecutively with fresh thread IDs.
4. No case returns `groq_langgraph_error`, asks for a place ID, or exposes the
   generic `partial` draft message for a feasible request.
5. Every committed result has `validation_report.acceptable=true`.
6. Route-only optimization never increases total distance and never changes the
   requested attraction set.

## Phase 1 — Harness enforcement and truthful finalization

### Changes

- Require a tool selection on the first agent decision of each user turn.
- Allow a normal text answer only after at least one relevant tool observation,
  or after an explicit clarification tool.
- Treat an empty/no-tool mutation response as a harness error and retry within a
  bounded budget rather than marking the turn completed.
- Split `completed`, `input_required`, `infeasible`, and `provider_error` into
  explicit terminal states.
- Never emit “updated” unless commit succeeded.

### Tests

- Model returns text without a tool on the first turn: harness retries.
- Read-only question: read tool first, then a text answer is allowed.
- Mutation: mutation tool, replan, validation and commit are all observable.
- Tool-call and iteration limits still terminate safely.

## Phase 2 — Locality-aware autonomous planning

### Data contract

- Add a canonical locality field during graph build (for example `Hội An`,
  `Sơn Trà`, `Huế`) derived from structured address/province data.
- Keep `region` as the province/city boundary and introduce a separate
  `location_focus` constraint. Do not overload place IDs or keyword lists.
- Add a graph locality resolver so the LLM can pass `query="Hội An"`; the
  executor resolves it against known localities and candidate density.

### Planner behavior

- A request such as “đi chơi Hội An” is sufficient to plan autonomously.
- Do not ask for named POIs or IDs when the locality has enough candidates.
- Start with a hard locality pool. If the pool is insufficient, expand by road
  travel radius in bounded steps and report the expansion explicitly.
- Expose locality purity in validation metrics.

### Gate

- Both Hội An benchmark cases reach at least 90% attraction locality purity,
  commit successfully, and do not request clarification.

## Phase 3 — Repair loop for `partial`

### Changes

- After replan, route `acceptable=false` back to a repair node instead of the
  generic finalizer.
- Classify validation failures into deterministic repair actions:
  - missing required place/day anchor;
  - required meal missing;
  - duplicate place/brand;
  - empty or underfilled day;
  - excluded type/category leakage;
  - distance/time-window overflow.
- Apply deterministic repairs before asking the LLM to revise a plan.
- Preserve all user hard constraints during repair.
- Bound repair attempts and retain the last committed itinerary on failure.
- If truly infeasible, return the exact conflicting constraints and one concrete
  relaxation choice; do not return the generic partial message.

### Gate

- `repair_partial_and_commit` passes.
- Synthetic infeasible tests terminate as `infeasible`, not `completed`.

## Phase 4 — Route-aware selection and multi-day assignment

### Intermediate implementation

- Compute the road-time matrix before final candidate selection.
- Cluster candidates spatially into the requested number of days.
- Rank within each cluster using recommendation utility minus travel cost.
- Assign required anchors first, then fill each day with nearby compatible
  candidates.
- Optimize day order and intra-day order while respecting meals, opening hours,
  duration and maximum distance.

### Later implementation

- Evaluate a single multi-vehicle Team Orienteering Problem with Time Windows
  model, where vehicles represent days and node drop penalties reflect
  recommendation utility.
- Keep the spatial-cluster planner as a deterministic fallback and comparison
  baseline.

### Metrics

- Total and per-day road distance.
- Total and maximum per-day travel minutes.
- Idle gaps and empty days.
- Preference/category coverage.
- Locality purity and duplicate count.

### Gate

- Route-only benchmark preserves the exact attraction set and has distance ratio
  `<= 1.0` versus the initial plan.
- Compound and lighter-day cases satisfy their semantic changes without
  increasing the relevant route cost.

## Phase 5 — Retrieval and ranking quality

- Add locality-aware lexical retrieval first.
- Add Vietnamese hybrid retrieval (BM25 plus precomputed multilingual
  embeddings) only after the lexical/locality baseline is measured.
- Build embeddings offline; runtime should use a compact matrix/index rather
  than requiring Torch inference.
- Add Bayesian rating smoothing, retain logarithmic review normalization, and
  add diversity/MMR or type quotas to avoid repetitive itineraries.
- Benchmark retrieval recall separately from route quality so a routing failure
  cannot hide a retrieval failure.

## Phase 6 — Architecture and performance hardening

These are important, but should follow the user-visible quality gates:

- Choose one data pipeline and one processed artifact; archive legacy graph
  artifacts instead of treating all of them as current.
- Measure Torch import/cold-start cost before replacing the artifact format.
- Load graph/configuration through FastAPI lifespan/dependency injection.
- Replace the O(n²) NEAR build with BallTree/cKDTree when dataset scale warrants
  it; keep a correctness comparison test.
- Centralize environment settings and pin dependencies with a lockable project
  configuration.
- Add CI, structured logging, benchmark result artifacts and regression trends.
- Prune old LangGraph checkpoints and measure SQLite contention before moving to
  Postgres.

Current-code notes that change the priority of the external review:

- FastAPI endpoints are synchronous `def`, so FastAPI already dispatches them to
  a worker thread; they are not currently blocking an `async def` event loop.
- SQLite memory already enables WAL and `busy_timeout=5000`.
- OR-Tools already has a bounded time limit.
- Graph is loaded once per service instance/process, not once per request, though
  multiple worker processes still duplicate memory.

## Commands

List cases:

```powershell
.\myenv\Scripts\python.exe -m scripts.benchmark_agent_quality --list
```

Run one case against a local server:

```powershell
.\myenv\Scripts\python.exe -m scripts.benchmark_agent_quality `
  --base-url http://127.0.0.1:8000 `
  --case hoi_an_autoplan_without_clarification
```

Run the complete live suite and save diagnostics:

```powershell
.\myenv\Scripts\python.exe -m scripts.benchmark_agent_quality `
  --base-url http://127.0.0.1:8000 `
  --output .benchmark-results/agent-quality.json
```
