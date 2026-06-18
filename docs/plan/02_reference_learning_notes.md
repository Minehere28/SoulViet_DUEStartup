# SoulViet Reference Learning Notes

## SoulViet Project Context Snapshot

### 1. Current Project Goal

- SoulViet aims to become a personalized travel itinerary system: user enters trip information -> backend generates an itinerary -> chat appears only after the itinerary exists -> user chats to refine the itinerary -> system updates the itinerary from the current itinerary state.
- The product direction is Graph RAG for travel, but the LLM should remain a grounded writer/refiner over accepted structured itinerary data, not the source of truth for selecting places.
- The intended flow needs itinerary state/versioning so each chat edit can preserve current days, selected places, constraints, and change history.

### 2. Current Codebase Understanding

- **frontend/form:** `index.html` is a static frontend with `duration`, `budget`, and `vibe`, calling hard-coded `POST http://127.0.0.1:8000/plan`; it renders summary and AI text but has no chat panel or current itinerary state.
- **dataset:** `dataset/SoulViet_Dataset.csv` has 1210 places with id/name/type/address/lat/lng/rating/reviews/operation hours/descriptions/images/activities/vibe/price fields; runtime `graph.pt` currently exports only a subset.
- **models:** `UserRequest` manually parses raw dict fields and lacks validation; `Place` exists but active `/plan` flow mostly uses normalized dicts from `GraphService`.
- **services:** `GraphService`, `FilterService`, `ScoringService`, `ClusterService`, `PlannerService`, `ItineraryService`, and `LLMService` form the active generation path; `DataService`, `Neo4jService`, and `RoutingService` are present but not central to `/plan` runtime.
- **scripts:** `scripts/build_graph.py` imports CSV into Neo4j as `Place`, `Vibe`, `Type`, and `NEAR`; `scripts/export_to_pt.py` exports Neo4j data into `graph.pt`.
- **graph/retrieval/scoring/itinerary flow:** current runtime is graph-based heuristic retrieval, not full Graph RAG: hard filters + `NEAR` clusters + simple scoring + planner slots + route optimization + LLM text. It lacks vector search, evidence packages, citation, deterministic validator service, and chat state.
- **file plan/status hiện có:** `docs/plan/01_project_code_review.md`, `docs/status/soulviet_code_status_review.md`, and `docs/status/soulviet_implementation_plan.md` document current architecture, known bugs, target Graph RAG/chat flow, and phased implementation priorities.

### 3. Current Known Problems

- `used_ids` is updated before budget/time acceptance in `ItineraryService`; rejected days can still consume candidate places.
- Candidate places can be lost when a day is rejected because `used_ids` has already mutated.
- `PlannerService` scores `place` before checking `if not place`, so missing graph neighbors can crash.
- `GraphService.normalize_place` does not safely coerce numeric fields or normalize `types`/`vibes` to lists, which can break filtering, scoring, routing, and time estimation.
- Request validation is weak: `UserRequest` uses raw `int()`/`float()` casts and can return 500 for malformed input; backend does not enforce duration/budget/style constraints clearly.
- Frontend lacks itinerary state, `itinerary_id`, versioning, chat UI, chat endpoint integration, and robust `response.ok`/error handling.
- Frontend rendering is still summary-level and AI-text-heavy; it does not show rich place cards, address, reason/evidence, route, image, cost/time detail, or refinement state.
- Scoring and filtering are inconsistent: `FilterService` can match style/type, but `ScoringService.vibe_score` compares English vibe keys with Vietnamese labels and often under-scores valid places.
- Fallback slot filling can duplicate the same place across morning/afternoon/evening.
- Cluster generation uses `random.shuffle`, so results are not deterministic and are hard to test.
- Low budget or narrow vibe can return empty results without controlled fallback or explanation.
- Runtime artifact misses important evidence fields such as address, activities, top reviews, images, and operation hours.
- LLM/Groq client initialization is fragile and tied to service startup; fallback text is too generic.
- `requirements.txt` is incomplete for current imports, and git hygiene includes generated/binary/untracked artifacts.

### 4. How Reference Repo Lessons Should Be Applied

- When reading more `docs/repo_exp` files, always map lessons back to SoulViet's concrete runtime: `DataService`, `GraphService`, `FilterService`, `ScoringService`, `ClusterService`, `ItineraryService`, and the future `ValidatorService` / `ChatRefinementService`.
- Apply ingestion/data lessons to `DataService`, `scripts/build_graph.py`, `scripts/export_to_pt.py`, and `GraphService` schema normalization before adding complex retrieval.
- Apply graph/retrieval lessons to `GraphService`, a future `GraphRAGRetriever`, `FilterService`, `ScoringService`, and `ClusterService`: hard filter -> graph expansion -> semantic/evidence recall -> rerank -> validation-ready candidates.
- Apply scoring/recommendation lessons to `ScoringService` as explainable score breakdowns aligned with `FilterService` mappings.
- Apply planner/validator lessons to `ItineraryService` and a future `ValidatorService`: validate draft days before mutating `used_ids` or itinerary state.
- Apply chat/state lessons to a future `ChatRefinementService`, `ItineraryStateStore`, and frontend flow: form -> itinerary -> chat, where chat always edits the current itinerary state instead of starting from scratch.
- Apply grounding lessons by keeping structured itinerary and evidence as source of truth; `LLMService` should write or explain accepted data only.

### 5. Next Exp File To Read

- Already captured in this notes file: `docs/repo_exp/RAG-Anything_for_graph.md`, `docs/repo_exp/graphrag-code_for_graph.md`, and `docs/repo_exp/Understand-Anything_for_graph.md`.
- Next exp file to read: `docs/repo_exp/container-bay-plan-validator_for_graph.md`.

## 1. RAG / Graph RAG Core Lessons

### File: docs/repo_exp/RAG-Anything_for_graph.md

#### 1. Main Ideas

- Good Graph RAG for itinerary planning is a composite stack, not a graph-only or LLM-only system.
- RAG-Anything is most useful as a document and multimodal ingestion layer for PDFs, images, OCR, tables, office files, menus, maps, brochures, and schedules.
- Travel planning should separate graph reasoning from document reasoning: graph answers what is close, compatible, sequenceable, and constrained; document/vector retrieval answers what source text supports facts.
- The recommended stack is RAG-Anything ingestion -> canonical travel entity normalization -> Neo4j travel graph + Qdrant hybrid index -> graph ranker -> planner state machine -> deterministic validator -> editable UI/API.
- The LLM should not directly invent itinerary constraints or places; it should write, explain, or refine based on accepted candidates, evidence, and validator output.

#### 2. Architecture / Design Pattern

- Use a layered pipeline: travel sources -> parsers/importers -> canonical normalizer -> graph index + vector index -> hybrid retriever -> planner state machine -> validator -> frontend/API.
- Keep two retrieval stores with different responsibilities:
  - Graph store: `City`, `District`, `POI`, `Hotel`, `Restaurant`, `Route`, `TimeRule`, `Constraint`, `Itinerary`, `DayPlan`, `TimeSlot`.
  - Vector/hybrid store: descriptions, reviews, policies, menus, opening-hour notes, transit text, PDFs, images, and tables.
- RAG-Anything's class/mixin design suggests clear module boundaries: config, parser, processor, batch ingestion, query, multimodal query, callbacks, and storage configuration.
- The planner should ask small typed questions such as candidate retrieval, evidence lookup, route feasibility, opening-hour check, and slot assignment instead of asking an LLM to produce a full plan in one shot.
- Important outputs should be labeled as graph-supported, document-supported, or model-inferred so risky claims can be reviewed.

#### 3. RAG / Graph RAG Lessons

- **data ingestion:** Treat CSV/API data, PDFs, menus, schedules, maps, policy documents, reviews, and images as source inputs; do not rely only on current `graph.pt` fields.
- **parsing:** Parser output should keep source metadata and document status/cache keys so ingestion can be repeated, refreshed, and debugged.
- **chunking:** Chunking should preserve relation to source document, page/section/table/image, and target travel entity; chunks without entity links are weak for itinerary grounding.
- **indexing:** Index structured entities/relations in a graph and raw/messy evidence in a vector or hybrid index; stable IDs must connect graph nodes to evidence chunks.
- **embedding/vector retrieval:** Use dense/sparse hybrid search for natural-language intent and messy evidence such as reviews, descriptions, menus, policies, and OCR text.
- **entity extraction:** Extract travel-normalized entities such as `POI`, `City`, `District`, `Cuisine`, `Activity`, `OpeningHour`, `PriceBand`, `Policy`, `AccessibilityFeature`, and `TimeRule`.
- **relationship modeling:** Model relations such as `LOCATED_IN`, `TAGGED_AS`, `SUITABLE_FOR`, `OPEN_ON`, `NEAR_TO`, `CONNECTED_BY`, `SERVES`, `PREFERS`, `AVOIDS`, `HAS_SLOT`, `ASSIGNS`, and `EVIDENCE_FOR`.
- **graph construction:** Define SoulViet's canonical travel schema before importing more data; schema quality matters more than adding RAG tooling quickly.
- **graph retrieval:** Use user intent seeds like destination, vibe/theme, budget, starting location, must-visit places, mobility constraints, and time windows to expand graph candidates.
- **hybrid retrieval:** Fuse graph hits and vector/document hits, then rerank by feasibility; graph and vector retrieval should not compete without explicit score fusion.
- **reranking:** Rerank by graph score, vector score, rating, review confidence, budget fit, distance/travel time, slot compatibility, diversity, opening hours, and evidence quality.
- **grounding:** Require evidence for high-risk claims such as open hours, closures, accessibility, child/family suitability, transit conditions, booking rules, and refund policies.
- **evaluation:** Add travel-specific eval fixtures for budget, travel time, opening hours, day sequencing, rainy-day fallback, accessibility, family suitability, relevance@K, evidence precision, repair success, and user rating.

#### 4. Agent / Workflow Lessons

- **agent orchestration:** Separate roles: ingestion/parser, entity normalizer, graph retriever, document retriever, scorer/reranker, planner, validator, writer, and chat refiner.
- **tool calling:** Expose retrieval, route check, opening-hour check, price check, and validator as controlled tools; do not let the LLM freely choose ungrounded places.
- **state management:** Use a planner state machine for form submitted -> retrieval -> draft itinerary -> validation -> accepted itinerary -> chat-enabled -> refinement.
- **memory:** Store itinerary state, selected IDs, rejected candidates, user constraints, evidence references, and change history; chat must edit current state.
- **task decomposition:** Decompose itinerary generation into typed sub-questions: seed extraction, candidate retrieval, evidence collection, slot assignment, route optimization, validation, and explanation.
- **validator:** A deterministic validator should sit after planning and before acceptance; `used_ids` or itinerary state should mutate only after validation passes.
- **fallback/retry:** If retrieval is empty or validation fails, retry with controlled constraint relaxation and return reasons instead of silent `continue` or empty output.
- **human-in-the-loop:** For richer UX, expose candidates/conflicts/evidence so users can pin, reject, replace, or approve itinerary nodes.

#### 5. Applicable to SoulViet — Current Architecture

- **service nào nên sửa:** `GraphService` should normalize richer fields and expose evidence refs; `FilterService` and `ScoringService` should share the same style/type normalization; `ClusterService` should become deterministic; `ItineraryService` should validate before mutating `used_ids`; `LLMService` should remain a grounded writer only.
- **service nào nên thêm:** Add `ValidatorService` first, then `ItineraryStateService`, `ChatRefinementService`, and later `GraphRAGRetriever` / `EvidenceRetriever`.
- **file/module bị ảnh hưởng:** `scripts/build_graph.py`, `scripts/export_to_pt.py`, `services/graph_service.py`, `services/filter_service.py`, `services/scoring_service.py`, `services/cluster_service.py`, `services/itinerary_service.py`, `services/llm_service.py`, `models/user_request.py`, `views/travel_view.py`, and `index.html`.
- **ngắn hạn có thể làm:** Export more fields into `graph.pt`, normalize list/numeric fields, fix `used_ids`, add planner `place is None` guard, add request validation, add score breakdown, return structured itinerary with reason/evidence placeholders, and add validation report.
- **rủi ro khi vá tiếp kiến trúc cũ:** Current architecture mixes retrieval, planning, mutation, validation, and response formatting; patching too long can create a fragile monolith where chat refinement amplifies hidden state bugs.
- **cách áp dụng thực tế:** Treat RAG-Anything lessons as a direction for data/evidence readiness, but do not integrate full multimodal ingestion before Phase 1 correctness and structured itinerary output are stable.

#### 6. Applicable to SoulViet — Rebuilt Architecture

- **module/service mới:** `IngestionService`, `TravelEntityNormalizer`, `GraphIndexService`, `VectorIndexService`, `GraphRAGRetriever`, `EvidenceRetriever`, `RerankerService`, `ItineraryPlanner`, `ValidatorService`, `ItineraryStateStore`, `ChatRefinementService`, and `ResponseWriter`.
- **data flow mới:** form request -> request validation -> constraint extraction -> graph seed resolution -> graph retrieval -> vector/evidence retrieval -> score fusion/reranking -> day-slot planning -> validator -> save itinerary state -> response writer -> frontend itinerary view -> chat refinement loop.
- **graph schema mới:** Start with `City`, `District`, `POI`, `Restaurant`, `Hotel`, `Cuisine`, `Activity`, `Theme`, `PriceBand`, `TimeRule`, `Document`, `Evidence`, `Constraint`, `Itinerary`, `DayPlan`, and `TimeSlot`; edges include `LOCATED_IN`, `HAS_TYPE`, `HAS_VIBE`, `SERVES`, `OPEN_ON`, `NEAR_TO`, `CONNECTED_BY`, `SUITABLE_FOR`, `EVIDENCE_FOR`, `HAS_DAY`, `HAS_SLOT`, and `ASSIGNS`.
- **API contract mới:** `/plan` should return `itinerary_id`, `version`, `request`, `constraints`, structured `days/slots/places`, `score_breakdown`, `evidence`, `validation_report`, `warnings`, and optional `ai_text`; `/chat/refine` should accept `itinerary_id`, `version`, `message`, and optional locked/removed places.
- **frontend state flow:** form is visible first; after `/plan` succeeds, frontend stores current itinerary state and shows structured itinerary; chat appears only after itinerary exists; each chat result replaces state with a new version and change summary.
- **itinerary/chat/validator split:** Planner proposes drafts, validator approves/rejects with reasons, state store persists accepted versions, chat refiner parses edit intent and calls retriever/planner/validator, writer explains accepted changes.
- **architecture decision:** If rebuilding is allowed, prefer a clean service boundary around retrieval-state-validation before adding multimodal ingestion or a canvas UI.

#### 7. Risks / Anti-patterns

- Do not copy the whole RAG-Anything/LightRAG stack before defining SoulViet's canonical travel schema.
- Do not treat multimodal ingestion as a shortcut for itinerary correctness; parsed documents still need normalization, evidence links, and validators.
- Do not put all retrieval into vector search; travel planning needs graph constraints for route, distance, slot, budget, and compatibility.
- Do not let LLM output become the source of truth for selected places, open hours, or constraints.
- Do not add Neo4j + Qdrant + RAG-Anything + state machine + canvas UI all at once; phase the rebuild or the MVP will become harder to debug.
- Do not cite weak or stale evidence for high-risk travel claims.
- Do not keep mutating shared place dicts/state across planning steps without copy/version boundaries.

#### 8. Key Takeaways

1. Graph RAG for travel should be graph + vector + workflow + validator, not just graph or prompt engineering.
2. RAG-Anything is best used for ingestion and multimodal evidence, while SoulViet still needs its own travel schema and planner.
3. Graph retrieval and document retrieval should answer different questions and then be fused/reranked.
4. Deterministic validation must happen before accepting itinerary state or updating `used_ids`.
5. Chat refinement requires itinerary state/versioning; otherwise chat will not reliably edit the current plan.

#### 9. Impact On SoulViet Roadmap

- **Phase 0: architecture decision:** Decide whether to refactor current MVP or rebuild around clean retrieval-state-validation boundaries; define canonical travel schema first.
- **Phase 1: correctness:** Fix `used_ids`, planner guard, graph normalization, request validation, deterministic cluster behavior, and score/filter mismatch before deeper RAG work.
- **Phase 2: structured itinerary output:** Return structured days/slots/places with reasons, score breakdown, warnings, and evidence placeholders.
- **Phase 3: frontend rendering:** Render structured itinerary cards and evidence/reason fields, not only AI text.
- **Phase 4: itinerary state:** Add `itinerary_id`, version, selected IDs, constraints, evidence refs, and change history.
- **Phase 5: chat after itinerary:** Show chat only after itinerary is ready and send current itinerary identity/version with each message.
- **Phase 6: chat refinement:** Use intent parsing + retriever + planner + validator to update itinerary state; do not let LLM independently rewrite the plan.
- **Phase 7: validator service:** Add deterministic checks for budget, time, duplicates, route feasibility, opening hours, accessibility, and evidence requirements.
- **Phase 8: Graph RAG improvement:** Add richer graph schema, evidence export, vector/hybrid retrieval, score fusion, and eventually RAG-Anything-style multimodal ingestion.
- **Phase 9: evaluation:** Create fixtures and metrics for constraints, temporal feasibility, travel-time feasibility, grounding precision, relevance@K, diversity, budget deviation, and repair success.
- **Phase X: architecture rebuild nếu cần:** Rebuild as modular services if current orchestration becomes too tangled for stateful chat and validator-driven planning.

Next file to read: `docs/repo_exp/graphrag-code_for_graph.md`.

### File: docs/repo_exp/graphrag-code_for_graph.md

#### 1. Main Ideas

- GraphRAG-code shows a graph-first RAG pattern: build a knowledge graph from source entities and relationships, then use graph retrieval to assemble better LLM context.
- The core lesson for SoulViet is separation of index-time and query-time: parse/extract/index once, then query over stable graph/vector indexes many times.
- A graph index should model domain structure explicitly; for travel this means places, destinations, tags, routes, time slots, budgets, activities, evidence, and itinerary state rather than flat place dictionaries.
- Vector retrieval is useful for semantic seed discovery, but graph traversal and graph-native ranking are what provide architecture/domain awareness.
- Local/global/DRIFT-style search modes can map to travel product needs: local POI/day-slot search, global destination/theme overview, and expanding from a known place into nearby compatible clusters.

#### 2. Architecture / Design Pattern

- **graph-first retrieval:** Convert source data into typed nodes and typed relationships before asking LLMs to answer. Retrieval should follow graph structure, not only embedding similarity.
- **graph index:** The graph index is the primary structural index. It stores entity IDs, labels, properties, and relationship types so queries can ask "what connects to what".
- **graph engine:** A graph engine should resolve seed entities, traverse relevant edges, rank related nodes, and return structured context. This should be separate from low-level data loading.
- **MCP/tool interface:** If exposed as a tool, graph query should have typed inputs/outputs such as `resolve_entity`, `rank_neighbors`, `get_context`, or `explain_path`, not a free-form LLM graph prompt.
- **query engine:** Query-time flow should be: receive natural language -> resolve seed entities by structured lookup/vector search -> traverse graph -> rank candidates -> assemble context -> pass bounded context to LLM/writer.
- **context assembly:** Context should include node properties, relationship path, source/evidence references, and why each candidate was included.
- **index-time vs query-time:** Index-time handles parsing, entity extraction, relationship extraction, graph writes, embedding generation, and updates. Query-time handles seed resolution, traversal, ranking, context assembly, and response generation.

#### 3. RAG / Graph RAG Lessons

- **graph construction:** Build a property graph with domain-specific node labels, edge labels, and properties. Do not reduce SoulViet to `Place` + `NEAR` only.
- **node/entity modeling:** Code entities like module/class/function translate to travel entities like `Destination`, `Place`, `Tag`, `Style`, `BudgetLevel`, `TimeSlot`, `Cuisine`, `ActivityType`, `RouteSegment`, `UserRequest`, `Itinerary`, `ItineraryDay`, `ItineraryItem`, and `Evidence`.
- **edge/relationship modeling:** Code edges like imports/calls/inherits translate to travel edges such as `LOCATED_IN`, `HAS_TAG`, `SUITABLE_FOR_STYLE`, `NEAR`, `SAME_CLUSTER`, `BEST_AT_TIME`, `HAS_PRICE_LEVEL`, `RECOMMENDED_WITH`, `CONFLICTS_WITH`, `CONNECTED_TO`, `SELECTED_IN`, `REPLACED_BY`, and `GROUNDED_BY`.
- **property graph design:** Node/edge properties matter: distance, duration, cost, rating, review count, time window, confidence, source ID, freshness, and validation status should be queryable.
- **graph indexing:** Stable IDs are essential so graph nodes, vector chunks, itinerary items, and evidence all point to the same real-world place or fact.
- **graph traversal:** Traversal should be edge-aware and scope-aware. A query about "nearby food after museum" should follow `NEAR`, `CONNECTED_TO`, `SERVES`, and `BEST_AT_TIME`, not every edge type.
- **graph-native ranking:** Rank with structural signals such as edge type, path length, graph distance, cluster membership, connectivity, and compatibility, then combine with heuristic scores.
- **Personalized PageRank:** PPR-style ranking is useful when a request has seed nodes such as destination, style, budget level, and must-visit places; it can surface nodes structurally close to the user's intent.
- **forward/backward traversal:** Forward traversal can find next activities, nearby places, and connected route segments; backward traversal can explain why a candidate matches upstream constraints such as style, budget, slot, and evidence.
- **local search:** Best default for itinerary generation: retrieve around current destination, day, place, or slot under constraints.
- **global search:** Useful for destination overview and broad theme discovery, but too expensive/general as the default for day-by-day planning.
- **hybrid retrieval:** Use vector search to resolve fuzzy user language, then graph traversal/ranking to produce candidates with structural reasons.
- **context assembly cho LLM:** Context should be compact and structured: candidate, path/relation reason, relevant properties, evidence refs, validation flags, and alternatives.
- **evaluation/debug retrieval:** Log seed resolution, traversed edges, ranked nodes, dropped candidates, score components, and final context so bad itineraries can be debugged.

#### 4. Agent / Workflow Lessons

- **query planning:** Convert a user request into graph seeds and typed retrieval goals before querying: destination seed, style seed, budget seed, time-slot seed, and constraints.
- **graph query as tool:** Graph retrieval should be a deterministic tool called by planner/chat services, not hidden inside a prompt.
- **MCP/tool calling interface:** A future MCP/API layer can expose graph tools for resolve, traverse, rank, explain, and evidence lookup.
- **retrieval orchestration:** Retrieval should orchestrate semantic search, graph search, score fusion, context assembly, and fallback in a predictable order.
- **graph debugging:** Keep explainable retrieval traces: which seed produced which candidate, which edge path justified it, and why candidates were filtered.
- **explainability:** User-facing reasons can be generated from graph paths, e.g. "selected because it is near X, matches food/culture style, fits evening slot, and has evidence Y".
- **fallback/retry:** If graph traversal returns too few feasible candidates, relax soft filters in stages: expand cluster radius, broaden style tags, lower rating threshold, or add alternatives, while preserving hard constraints.

#### 5. Applicable to SoulViet — Current Architecture

- **`GraphService` nên sửa gì:** Add seed resolution, typed neighbor retrieval, edge-aware traversal, stable place IDs, safer property normalization, and a method that returns ranked candidates with reasons instead of raw neighbors only.
- **`build_graph.py` nên học gì:** Treat it as deterministic index-time logic. It should create richer nodes/edges and constraints, not only `Place`, `Vibe`, `Type`, and `NEAR`.
- **`export_to_pt.py` nên học gì:** Preserve graph semantics when exporting: node labels, relationship types, edge properties, stable IDs, evidence refs, price/time fields, and normalized tags.
- **`ClusterService` nên học gì:** Stop relying on random cluster shuffling as retrieval. Use graph clusters as one signal in ranking, with deterministic ordering and traceable candidate reasons.
- **`ScoringService` nên học gì:** Combine graph-native score with current heuristic score. Expose score breakdowns for style match, rating, budget fit, distance, slot fit, and evidence quality.
- **`ItineraryService` nên dùng graph retrieval thế nào:** It should request ranked candidates from a graph retriever, assign them into slots, validate feasibility, then mutate `used_ids` only after a day or item is accepted.
- **ngắn hạn có thể làm:** Add deterministic candidate ordering, return retrieval reasons, add score breakdown, preserve more properties in `graph.pt`, and split candidate retrieval from slot assignment.
- **rủi ro nếu vá tiếp kiến trúc cũ:** If graph traversal, scoring, clustering, slot planning, state mutation, and LLM writing remain tangled, SoulViet will call BFS over `NEAR` "Graph RAG" without getting real explainability or correctness.

#### 6. Applicable to SoulViet — Rebuilt Architecture

- **graph schema mới:** Use nodes: `Destination`, `Place`, `Tag`, `Style`, `BudgetLevel`, `TimeSlot`, `Cuisine`, `ActivityType`, `RouteSegment`, `UserRequest`, `Itinerary`, `ItineraryDay`, `ItineraryItem`, and `Evidence`.
- **module `GraphRAGRetriever`:** Yes. Add a dedicated `GraphRAGRetriever` that owns seed resolution, graph traversal, graph-native ranking, vector fusion, context assembly, and retrieval trace output.
- **graph ranking tách khỏi `GraphService`:** Yes. `GraphService` should be graph storage/query adapter; `GraphRAGRetriever` should implement retrieval strategy and ranking policy.
- **node/edge/property chia thế nào:** Nodes represent domain objects and state objects; edges represent semantic, spatial, temporal, route, selection, replacement, and grounding relationships; properties carry duration, cost, distance, confidence, source, freshness, and validation metadata.
- **retrieval pipeline mới:** request validation -> seed extraction -> semantic seed lookup -> graph traversal by allowed edge types -> PPR/graph score -> heuristic feasibility score -> evidence lookup -> context assembly -> planner.
- **API contract mới:** Retrieval/planning responses should include `candidate_id`, `place_id`, `graph_score`, `score_breakdown`, `matched_edges`, `path_reason`, `evidence_refs`, `warnings`, and `validation_status`.
- **itinerary planner nhận candidate thế nào:** Planner should receive immutable ranked candidates with properties and evidence; it should not query random neighbors internally or mutate retrieval results.
- **validator kiểm graph/state consistency:** Validator should check selected itinerary items exist in graph, slot assignments match `BEST_AT_TIME`/opening rules, route segments connect consecutive places, `SELECTED_IN` state is versioned, replacements use `REPLACED_BY`, and claims are `GROUNDED_BY` evidence.

#### 7. Risks / Anti-patterns

- Do not turn Graph RAG into simple BFS over `NEAR` and call it done.
- Do not assume one `NEAR` edge is enough for itinerary reasoning; travel needs style, time, budget, route, conflict, and evidence relations.
- Do not let graph ranking replace validator; ranking says "promising", validator says "allowed/feasible".
- Do not let the LLM choose nodes outside the graph or invent unstored places as accepted itinerary items.
- Do not make the graph too complex before the core schema and stable IDs are settled.
- Do not mutate itinerary state during retrieval; retrieval should be read-only and planning/state mutation should happen after validation.
- Do not use global/community search as the default for every itinerary request; local constrained retrieval is usually more relevant.
- Do not hide retrieval decisions; missing debug traces make Graph RAG failures hard to fix.

#### 8. Key Takeaways

1. Graph RAG needs a real property graph with typed nodes, typed edges, and queryable properties.
2. Index-time and query-time must be separated so retrieval is stable, debuggable, and reusable.
3. Graph-native ranking, including PPR-style seed expansion, is more meaningful than random BFS/cluster traversal.
4. The itinerary planner should consume ranked candidates; it should not be the graph retriever itself.
5. Retrieval traces and graph paths are essential for explainability, frontend reasons, and debugging.

#### 9. Impact On SoulViet Roadmap

- **Phase 0: architecture decision:** Decide whether graph ranking becomes a small refactor inside current services or a dedicated `GraphRAGRetriever` boundary.
- **Phase 1: correctness:** Fix current retrieval/planning mutation bugs and add deterministic retrieval order before expanding graph complexity.
- **Phase 2: structured itinerary output:** Include candidate IDs, score breakdowns, graph reasons, and warnings in structured output.
- **Phase 3: frontend rendering:** Show why each place was selected using graph path reasons and score components.
- **Phase 4: itinerary state:** Represent accepted places as itinerary items linked to graph place IDs and versioned state.
- **Phase 5: chat after itinerary:** Chat requests should refer to current itinerary/version and graph-linked items.
- **Phase 6: chat refinement:** Chat refinements should use graph retrieval for replacements and alternatives, not free-form LLM rewriting.
- **Phase 7: validator service:** Validate graph/state consistency, route connectivity, time-slot compatibility, duplicates, and grounded evidence.
- **Phase 8: Graph RAG improvement:** Add graph-native ranking, edge-aware traversal, vector seed lookup, PPR-style scoring, and context assembly.
- **Phase 9: evaluation:** Add retrieval debug fixtures and metrics for seed resolution, relevance@K, ranking stability, path correctness, and context grounding.
- **Phase X: architecture rebuild nếu cần:** Rebuild around `GraphService` as storage adapter, `GraphRAGRetriever` as ranking/retrieval layer, planner as scheduler, validator as gatekeeper, and writer as final explanation layer.

Next file to read: `docs/repo_exp/Understand-Anything_for_graph.md`.

### File: docs/repo_exp/Understand-Anything_for_graph.md

#### Main Ideas

- Understand-Anything is useful for learning how to turn a corpus into an interactive knowledge graph that users or agents can explore, search, and question.
- The strongest lesson for SoulViet is UI/UX graph reasoning, not code-domain analysis.
- Its structure suggests clear layers for analyzer, schema, persistence, embedding search, search, staleness/change handling, graph prompts, and dashboard/plugin experience.
- For travel, the same pattern can support exploration from city -> district -> POI -> route -> nearby restaurant -> opening-hour conflict.
- The file also reinforces the broader target stack: multimodal ingestion, hybrid retrieval, stateful planner, validator, memory, citations, and production infrastructure.

#### Architecture Pattern

- Treat the graph as an application-level reasoning interface:
  - Analyze source corpus into structured entities and relationships.
  - Persist a schema-aware graph representation.
  - Add embedding lookup and search over graph-linked content.
  - Expose graph exploration through UI/dashboard or plugin workflows.
  - Use prompts/agents to guide review, graph navigation, and tours over the knowledge graph.
- Reuse the layer boundaries, not the code analyzer assumptions:
  - Replace source-code analyzers with travel ingest for POIs, routes, hotels, opening hours, seasonal constraints, policies, and user preferences.
  - Keep graph search and embedding search as separate but connected modules.
  - Keep staleness/change ideas for source refresh, but adapt them from file changes to travel data freshness.

#### Graph RAG Lessons

- **graph construction:** Build a schema that can be explored by people and agents, not only queried by backend code. Travel graph nodes should support navigation across `City`, `District`, `POI`, `Restaurant`, `Hotel`, `TransportLeg`, `TimeRule`, `PolicyDoc`, and `UserPreference`.
- **entity extraction:** Analyzer logic must be rewritten for travel. Instead of file/path/module/language assumptions, extract POIs, addresses, categories, routes, opening hours, prices, policies, and constraints from travel sources.
- **relationship modeling:** Graph edges should make conflicts and exploration visible: `LOCATED_IN`, `NEARBY`, `REACHABLE_BY`, `OPEN_DURING`, `CONFLICTS_WITH`, `SUITABLE_FOR`, `REQUIRES_BOOKING`, `EVIDENCED_BY`, and `SAME_DAY_FEASIBLE_WITH`.
- **indexing:** Pair graph persistence with embedding search. Stable IDs should connect nodes to text evidence, source docs, and freshness metadata so stale travel facts can be reviewed.
- **retrieval:** Use graph exploration for reasoning paths, not just top-k answers. A planner or admin should be able to inspect why a POI was chosen, what nearby options exist, and which constraints may block it.
- **reranking:** Rerank retrieved nodes by structural fit plus travel feasibility: distance, slot compatibility, opening hours, price, evidence quality, user preference, and conflict count.
- **grounding:** Graph UI/search should surface source-backed facts for risky claims. Opening hours, booking requirements, seasonal limits, and accessibility should point back to evidence.
- **evaluation:** Add checks for graph navigability, stale data detection, search relevance, evidence linkage, and whether graph exploration reveals itinerary conflicts before final output.

#### Applicable to SoulViet

- **node/edge nên thêm:** Add travel graph entities that are useful to inspect visually: `City`, `District`, `POI`, `Hotel`, `Restaurant`, `TransportHub`, `TransportLeg`, `TimeRule`, `PolicyDoc`, `Evidence`, `UserPreference`, and `Itinerary`. Add edges such as `LOCATED_IN`, `NEARBY`, `REACHABLE_BY`, `OPEN_DURING`, `CONFLICTS_WITH`, `SUITABLE_FOR`, `EVIDENCED_BY`, and `ASSIGNED_TO_SLOT`.
- **service nào nên ảnh hưởng:** `services/graph_service.py` should eventually expose graph search/exploration APIs, not only neighbor lookup. `scripts/build_graph.py` should preserve schema and freshness metadata. `services/filter_service.py` and `services/scoring_service.py` should feed structured criteria into graph retrieval/reranking. A future admin/debug UI could use this pattern to inspect why an itinerary was generated.
- **retrieval nên cải thiện thế nào:** Add a graph explorer mindset to the retriever: resolve seeds -> search embeddings -> expand graph neighborhood -> expose conflicts/alternatives -> rerank with constraints -> return evidence-backed candidates. This makes retrieval explainable and debuggable.
- **itinerary builder nên học gì:** The builder should produce plans that can be inspected as graph paths: why this POI, what evidence supports it, what route connects it, what slot it fits, and what conflicts were checked. This supports human review and repair loops.

#### Risks / Anti-patterns

- Do not copy code-domain assumptions such as file paths, modules, language analyzers, fingerprints, or staleness logic without adapting them to travel data.
- Do not confuse an interactive graph UI with itinerary correctness; the planner still needs deterministic validation.
- Do not overfit to application-level graph persistence if SoulViet later needs Neo4j or another graph database for scale/querying.
- Do not let graph exploration become a raw developer-only feature; users need simplified explanations and actionable alternatives.
- Do not use embedding search as a substitute for schema quality; poor travel entities and edges will make the graph hard to trust.

# SoulViet Target Project Structure Inspired By Standard RAG Architecture

## 1. Why Standard RAG Structure Is Useful

- A standard RAG structure is useful because it separates ingestion, chunking, embeddings, vector DB, retrieval, prompts, LLM, API, utilities, tests, logs, config, and secrets into clear modules.
- Clear modules make the system easier to debug: ingestion bugs, retrieval bugs, prompt bugs, LLM bugs, and API bugs can be isolated instead of being hidden inside one orchestration file.
- It improves testability because each layer can have focused tests: loader tests, retriever tests, prompt/context tests, LLM wrapper tests, API contract tests, and regression/evaluation tests.
- It helps onboarding because new developers can quickly understand where data enters, where indexes are built, where retrieval happens, where prompts live, and where endpoints are defined.
- It helps productionization by separating `config.yaml`, `.env`, logs, monitoring, tests, and replaceable infrastructure from business logic.
- It makes components replaceable: embedding model, vector DB, graph DB, retriever, LLM provider, prompts, and API layer can change without rewriting the whole app.
- For SoulViet, this structure is a good mental model because it encourages separation of ingestion, retrieval, prompt, LLM, API, tests, logging, and config.
- However, generic RAG structure is not enough for itinerary planning because SoulViet has graph constraints, scheduling, budget/time validation, itinerary state, and chat refinement over current state.

## 2. Why SoulViet Should Not Copy It Directly

- SoulViet is not only a PDF/document chatbot; it must generate feasible travel itineraries under constraints.
- Travel itinerary planning needs graph constraints: nearby places, same cluster, same area, related style, route compatibility, and time-slot suitability.
- Budget, duration, travel time, duplicate places, pace, and style fit need deterministic validation instead of LLM judgment.
- Chat refinement needs itinerary state/versioning so the system edits the current itinerary instead of starting from scratch.
- Graph retrieval is different from chunk retrieval: it should retrieve places, paths, constraints, alternatives, and evidence, not just top-k text chunks.
- The LLM must not choose places outside the graph/dataset; it should write and explain accepted structured itinerary data.
- `chunking/` is not the current core module. The more important core modules are `graph/`, `retrieval/`, `scoring/`, `planning/`, `validation/`, `state/`, and `chat/`.
- If SoulViet copies a generic RAG structure directly, it can degrade into vector search + prompt, which is not a true Graph RAG itinerary planner.

## 3. Proposed Rebuilt SoulViet Structure

```text
soulviet/
├── README.md
├── requirements.txt
├── .env.example
├── .gitignore
├── config.yaml
├── app.py
├── main.py
├── dataset/
│   └── SoulViet_Dataset.csv
├── data/
│   ├── raw/
│   ├── processed/
│   └── artifacts/
│       └── graph.pt
├── src/
│   ├── ingestion/
│   │   ├── __init__.py
│   │   ├── csv_loader.py
│   │   ├── place_loader.py
│   │   └── source_loader.py
│   ├── normalization/
│   │   ├── __init__.py
│   │   ├── place_normalizer.py
│   │   ├── price_normalizer.py
│   │   ├── type_normalizer.py
│   │   └── vibe_normalizer.py
│   ├── graph/
│   │   ├── __init__.py
│   │   ├── graph_builder.py
│   │   ├── graph_store.py
│   │   ├── graph_schema.py
│   │   └── graph_retriever.py
│   ├── embeddings/
│   │   ├── __init__.py
│   │   └── embedder.py
│   ├── vectorstore/
│   │   ├── __init__.py
│   │   └── vector_store.py
│   ├── retrieval/
│   │   ├── __init__.py
│   │   ├── hybrid_retriever.py
│   │   ├── graph_ranker.py
│   │   └── reranker.py
│   ├── scoring/
│   │   ├── __init__.py
│   │   ├── place_scorer.py
│   │   └── score_breakdown.py
│   ├── planning/
│   │   ├── __init__.py
│   │   ├── itinerary_planner.py
│   │   ├── day_planner.py
│   │   ├── slot_assigner.py
│   │   └── route_optimizer.py
│   ├── validation/
│   │   ├── __init__.py
│   │   ├── request_validator.py
│   │   ├── itinerary_validator.py
│   │   ├── budget_validator.py
│   │   ├── time_validator.py
│   │   └── duplicate_validator.py
│   ├── state/
│   │   ├── __init__.py
│   │   ├── itinerary_state_store.py
│   │   └── conversation_state_machine.py
│   ├── chat/
│   │   ├── __init__.py
│   │   ├── refinement_service.py
│   │   ├── intent_parser.py
│   │   └── change_applier.py
│   ├── prompts/
│   │   ├── itinerary_planner.md
│   │   ├── itinerary_writer.md
│   │   ├── validator.md
│   │   └── chat_refinement.md
│   ├── llm/
│   │   ├── __init__.py
│   │   ├── llm_client.py
│   │   └── response_writer.py
│   ├── api/
│   │   ├── __init__.py
│   │   ├── routes.py
│   │   ├── itinerary_routes.py
│   │   └── chat_routes.py
│   ├── models/
│   │   ├── __init__.py
│   │   ├── place.py
│   │   ├── user_request.py
│   │   ├── itinerary.py
│   │   └── validation_result.py
│   └── utils/
│       ├── __init__.py
│       ├── distance.py
│       ├── time_estimator.py
│       └── logging.py
├── frontend/
│   ├── index.html
│   ├── app.js
│   └── styles.css
├── scripts/
│   ├── build_graph.py
│   ├── export_to_pt.py
│   └── rebuild_indexes.py
├── tests/
│   ├── test_request_validation.py
│   ├── test_graph_retrieval.py
│   ├── test_place_scoring.py
│   ├── test_itinerary_builder.py
│   ├── test_validator.py
│   └── test_chat_refinement.py
└── logs/
    └── app.log
```

- **`ingestion/`:** reads CSV/API/PDF/source data and prepares raw source records.
- **`normalization/`:** normalizes place fields, price, type, vibe, coordinates, opening hours, and list/numeric types.
- **`graph/`:** owns graph schema, graph building, graph store access, and graph retrieval primitives.
- **`embeddings/` and `vectorstore/`:** become useful after SoulViet has text evidence, reviews, descriptions, policy docs, or multimodal content needing semantic retrieval.
- **`retrieval/`:** orchestrates hybrid retrieval, graph ranking, reranking, hard filters, and candidate evidence packages.
- **`scoring/`:** scores places with explainable score breakdowns instead of opaque totals.
- **`planning/`:** builds itinerary by day, time slot, and route using ranked candidates.
- **`validation/`:** validates requests, itinerary feasibility, budget, time, duplicates, pace, and style consistency.
- **`state/`:** stores current itinerary and manages the state machine needed for chat refinement.
- **`chat/`:** parses refinement intent and applies changes to current itinerary state through retrieval/planning/validation.
- **`prompts/`:** keeps prompts outside code and separates planner/writer/validator/refinement prompt templates.
- **`llm/`:** contains LLM client and response writer; it must not own place selection logic.
- **`api/`:** defines endpoints such as `/plan`, `/itinerary`, `/chat/refine`, and `/health` with clear contracts.
- **`models/`:** defines domain models for places, requests, itineraries, validation results, evidence, and score breakdowns.
- **`frontend/`:** splits HTML, JS, and CSS instead of keeping all UI logic inside one `index.html`.
- **`tests/`:** tests each layer independently and prevents regression in validation, retrieval, planning, and chat refinement.

## 4. Mapping From Current SoulViet To Proposed Structure

| Current File/Service | New Module | Keep / Move / Rewrite | Reason |
| -------------------- | ---------- | --------------------- | ------ |
| `app.py` | `app.py`, `main.py`, `src/api/routes.py` | Keep light, move route setup | Keep as entrypoint/bootstrap only; route logic should move into API modules. |
| `index.html` | `frontend/index.html`, `frontend/app.js`, `frontend/styles.css` | Split / rewrite | Current frontend is MVP form/rendering; new flow needs itinerary cards, state, chat panel, and errors. |
| `views/travel_view.py` | `src/api/itinerary_routes.py` | Move / rewrite | API contract should return structured itinerary/state, not view-heavy or summary-only output. |
| `models/user_request.py` | `src/models/user_request.py`, `src/validation/request_validator.py` | Rewrite | Needs explicit validation, defaults, constraints, and safe parsing instead of raw casts. |
| `models/place.py` | `src/models/place.py` | Keep concept / rewrite fields | Place remains core but needs richer normalized fields, evidence refs, score fields, and graph IDs. |
| `services/graph_service.py` | `src/graph/graph_store.py`, `src/graph/graph_retriever.py`, `src/graph/graph_schema.py` | Split / rewrite | Current graph access should become storage adapter + schema + retrieval layer. |
| `services/filter_service.py` | `src/retrieval/hybrid_retriever.py`, `src/scoring/place_scorer.py` | Move / refactor | Filtering should become hard filter/retrieval criteria aligned with scoring normalization. |
| `services/scoring_service.py` | `src/scoring/place_scorer.py`, `src/scoring/score_breakdown.py` | Rewrite | Should return explainable score breakdown, not only a final score. |
| `services/cluster_service.py` | `src/retrieval/graph_ranker.py`, `src/planning/day_planner.py` | Split / refactor | Cluster logic mixes retrieval and planning; graph ranking should be deterministic and traceable. |
| `services/planner_service.py` | `src/planning/day_planner.py`, `src/planning/slot_assigner.py`, `src/planning/route_optimizer.py` | Split / rewrite | Planning should separate day construction, slot assignment, and route optimization. |
| `services/itinerary_service.py` | `src/planning/itinerary_planner.py`, `src/validation/itinerary_validator.py`, `src/state/itinerary_state_store.py` | Rewrite core | Current orchestration risks becoming a god service; planning, validation, and state must be separated. |
| `services/llm_service.py` | `src/llm/llm_client.py`, `src/llm/response_writer.py` | Move / rewrite | LLM should write/explain accepted data only, not select places or validate feasibility. |
| `scripts/build_graph.py` | `scripts/build_graph.py`, `src/graph/graph_builder.py` | Keep script, move reusable logic | Script can remain CLI entrypoint while graph build logic becomes importable/testable. |
| `scripts/export_to_pt.py` | `scripts/export_to_pt.py`, `src/graph/graph_store.py`, `data/artifacts/graph.pt` | Keep script, standardize artifact | Export should preserve normalized properties, graph IDs, edge types, and evidence refs. |
| `dataset/SoulViet_Dataset.csv` | `dataset/SoulViet_Dataset.csv`, `data/processed/`, `data/artifacts/` | Keep | Dataset is the main source; add processed/artifact outputs instead of replacing it. |

## 5. Incremental Refactor vs Rebuild

| Option | Pros | Cons | Risk | When To Choose |
| ------ | ---- | ---- | ---- | -------------- |
| Option A — Giữ kiến trúc hiện tại và refactor dần | Ít rủi ro trước mắt; giữ app đang chạy; sửa nhanh `used_ids`, normalization, request validation; phù hợp demo sớm. | `ItineraryService` dễ phình to; service boundaries chưa sạch; Graph RAG dễ thành BFS/heuristic; chat refinement khó nếu chưa có state/store; test khó khi orchestration dính nhiều trách nhiệm. | Càng vá càng khó rebuild; lỗi correctness lặp lại; khó production hóa. | Chọn khi cần demo trong vài ngày, muốn giữ flow hiện tại để kiểm chứng dataset, hoặc chưa quyết định API/domain model mới. |
| Option B — Rebuild core architecture theo cấu trúc mới | Boundary rõ; đúng hướng Graph RAG itinerary planner; dễ test từng tầng; dễ thêm validator/state/chat; dễ production hóa; dễ thay graph/vector/LLM layer. | Tốn thời gian hơn; cần define model/API rõ trước; có thể tạm thời phá flow demo nếu thiếu migration plan. | Over-engineering; rebuild quá lớn một lần dễ fail; chưa cần vectorstore/chunking nếu dataset hiện tại chưa đủ text evidence. | Chọn khi MVP hiện tại chưa quá xịn và có thể thay lõi, mục tiêu dài hơi, cần chat refinement/validator ổn, và muốn tránh vá chồng lên kiến trúc yếu. |

## 6. Recommended Decision

- Recommended direction: **Controlled Core Rebuild**.
- Do not rebuild the whole UI/backend in one shot. Keep the current MVP as a runnable baseline while extracting and rebuilding core architecture step by step.
- Start by stabilizing correctness, then design the new `src/` core, then migrate validation -> graph normalization/retrieval -> scoring -> planning -> state -> chat.
- Switch `/plan` to the new pipeline only after the new API/model contracts and validation path are stable.
- Refactor frontend after backend output contract is clear; otherwise UI work will chase unstable data shapes.

### Keep

- Keep `dataset/SoulViet_Dataset.csv` as the primary source data.
- Keep current graph build logic as raw material, but normalize schema and properties.
- Keep the ideas behind `GraphService`, `FilterService`, `ScoringService`, `ClusterService`, and `PlannerService`, but not necessarily their current boundaries.
- Keep the frontend MVP form for quick testing while backend contracts evolve.
- Keep `docs/plan` as the implementation knowledge base and decision record.

### Move / Refactor

- Split `GraphService` into graph store, graph retriever, and graph schema.
- Split `ScoringService` into place scorer and score breakdown.
- Split `PlannerService` into day planner, slot assigner, and route optimizer.
- Move `LLMService` into writer/explanation layer.
- Move `travel_view.py` into API routes with clear response contracts.

### Rewrite

- Rewrite `UserRequest` validation with clear schema and constraints.
- Rewrite `ItineraryService` orchestration core so planning, validation, and state are separate.
- Rewrite `used_ids` mutation flow so mutation happens only after validation/acceptance.
- Add itinerary state/versioning from scratch.
- Add chat refinement as a state-aware service, not a prompt-only feature.
- Rewrite frontend rendering/chat UI later when backend contracts are stable.

### Avoid

- Do not add chat before itinerary state exists.
- Do not add vector DB before graph/data normalization is stable.
- Do not let LLM choose places outside the dataset/graph.
- Do not keep `ItineraryService` as a god service.
- Do not call it Graph RAG if retrieval is only BFS over `NEAR`.

## 7. Migration Plan

### Phase 0: Architecture Decision

- **Mục tiêu:** Decide Controlled Core Rebuild vs incremental refactor and write `docs/plan/03_architecture_decision.md`.
- **Output:** Target structure, API contracts, model contracts, migration rule, and code freeze boundary.

### Phase 1: Fix Correctness In Current Code

- **Mục tiêu:** Keep the current app running and reduce wrong outputs.
- **Sửa:** update `used_ids` only after validation pass, guard `place is None`, normalize numeric/list graph fields, add basic request validation, and make fallback deterministic if not enough places.
- **Rule:** Do not add chat in this phase.

### Phase 2: Define New Domain Models And API Contracts

- **Mục tiêu:** Define structured itinerary output.
- **Models:** `Place`, `UserRequest`, `Itinerary`, `ItineraryDay`, `ItineraryItem`, `ValidationResult`, `ScoreBreakdown`, and `Evidence`.
- **API:** `POST /plan`, `GET /itinerary/{id}`, `POST /chat/refine`, and `GET /health`.

### Phase 3: Extract Validation Layer

- **Mục tiêu:** Separate validators from planner.
- **Modules:** `request_validator.py`, `itinerary_validator.py`, `budget_validator.py`, `time_validator.py`, and `duplicate_validator.py`.
- **Rule:** Planner creates drafts, validator checks them, and state mutates only after validation passes.

### Phase 4: Extract Graph/Retrieval Layer

- **Mục tiêu:** Separate graph loading, graph schema, retrieval, and ranking.
- **Modules:** `graph_schema.py`, `graph_store.py`, `graph_retriever.py`, `hybrid_retriever.py`, and `graph_ranker.py`.
- **Logic:** hard filter -> graph expansion -> score/rerank -> return candidates with evidence fields.

### Phase 5: Extract Planning Layer

- **Mục tiêu:** Split itinerary planning into clear modules.
- **Modules:** `itinerary_planner.py`, `day_planner.py`, `slot_assigner.py`, and `route_optimizer.py`.
- **Rule:** Do not mutate `used_ids` during retrieval; mutate only after accepted day/item; planner must not call LLM to choose places.

### Phase 6: Add Itinerary State

- **Mục tiêu:** Store current itinerary for chat refinement.
- **Modules:** `itinerary_state_store.py` and `conversation_state_machine.py`.
- **State:** `INIT`, `FORM_INPUT`, `BUILDING_ITINERARY`, `ITINERARY_READY`, `CHAT_ENABLED`, `REFINING_ITINERARY`, `ITINERARY_UPDATED`, and `ERROR`.

### Phase 7: Add Chat Refinement

- **Mục tiêu:** Show chat only after itinerary exists and edit current itinerary instead of regenerating from scratch.
- **Modules:** `refinement_service.py`, `intent_parser.py`, and `change_applier.py`.
- **Intent:** remove place, replace place, add food, reduce cost, make it lighter, increase culture, and change style.

### Phase 8: Improve Frontend Structure

- **Mục tiêu:** Split `index.html` into clear frontend modules.
- **Files:** `frontend/index.html`, `frontend/app.js`, and `frontend/styles.css`.
- **Flow:** form -> loading -> itinerary cards -> chat panel hidden until itinerary ready -> change summary -> error display.

### Phase 9: Add Tests/Evaluation

- **Mục tiêu:** Test correctness and prevent regression.
- **Tests:** request validation, graph normalization, graph retrieval, place scoring, itinerary builder, validator, and chat refinement.
- **Test cases:** 2 days/2 million/culture-heavy, 3 days/low budget, 1 day/light pace, too many days, too-low budget, chat remove place, chat add local food, chat reduce cost, graph missing edge, and dataset missing field.

## 8. Final Note For This Architecture Update

- Standard RAG project structure is valuable, but only as a foundation for modular thinking.
- SoulViet needs its own structure for a Graph RAG itinerary planner.
- The core SoulViet modules are not mainly `chunking/`, but:

```text
graph/
retrieval/
scoring/
planning/
validation/
state/
chat/
```

- If SoulViet rebuilds, it should rebuild with control and migration boundaries instead of deleting the current code all at once.
- The first priority is still correctness in the current pipeline before adding chat, vector DB, or large frontend UX changes.

## conversational-state-machine_for_graph.md

### 1. Main Ideas

- The exp file says the original repository could not be retrieved in full, but the useful pattern is clear: manage dialogue through explicit states, allowed transitions, actions, and state tracking.
- For SoulViet, conversation should not be free-form from the beginning. The product needs a controlled path: collect request -> build itinerary -> save accepted itinerary -> enable chat -> refine current itinerary.
- State machines are most useful as a guardrail around LLM behavior. The LLM can parse text or write explanations, but the backend state machine decides what can happen next.
- The approach is especially relevant for slot filling, retry, cancel, error recovery, and preventing chat from running before an itinerary exists.
- The main lesson is to make conversation flow explicit and backend-owned instead of scattered across frontend flags, route handlers, and prompts.

### 2. Architecture / Design Pattern

- **conversation state machine:** Represent each product stage as a named state with allowed transitions and transition actions.
- **slot filling:** Keep user request fields as slots: duration, budget, vibe/style, pace, food preference, start area, must-visit places, and constraints. Missing or invalid slots keep the flow in `FORM_INPUT`.
- **context switching:** Separate initial planning context from refinement context. A new trip request creates a new itinerary context; a chat message edits the current itinerary context only.
- **hold/resume:** Long work such as itinerary generation or refinement should move into a busy state, then resume into ready, updated, or error state.
- **state transition:** Transitions should be explicit: `INIT -> FORM_INPUT -> BUILDING_ITINERARY -> ITINERARY_READY -> CHAT_ENABLED -> REFINING_ITINERARY -> ITINERARY_UPDATED -> CHAT_ENABLED`.
- **entity validation:** Validate request entities before planning and validate itinerary/refinement entities before saving. The LLM may infer intent, but deterministic validators must approve changes.
- **route/service separation:** Routes should translate HTTP input/output only. Services should own request validation, state transition, planning, refinement, and state persistence.
- **schema/catalog:** SoulViet needs a small state catalog: `itinerary_id`, `version`, `state`, `request_slots`, `accepted_itinerary`, `pending_change`, `validation_errors`, `history`, and timestamps.

### 3. State Machine Lessons For SoulViet

- **INIT:** Entry state before any request is submitted. Store session metadata only if needed. Transition to `FORM_INPUT` when the user opens or starts the planner.
- **FORM_INPUT:** Collect and validate form slots. Store normalized request fields, missing slots, validation errors, and correction messages. Transition to `BUILDING_ITINERARY` only when required slots are valid.
- **BUILDING_ITINERARY:** Backend retrieves candidates, scores, plans, routes, and asks the LLM only to write grounded text. Store `itinerary_id`, request snapshot, draft, candidate references, and build status. Transition to `ITINERARY_READY` after validation passes or `ERROR` on system/generation failure.
- **ITINERARY_READY:** A valid itinerary exists. Store accepted itinerary, selected place IDs, validator report, cost/time summary, evidence refs, and version `1`. Transition to `CHAT_ENABLED` after backend state is saved and response is ready.
- **CHAT_ENABLED:** User can ask questions or request changes against the current itinerary. Store current `itinerary_id`, version, accepted itinerary, locks/removals, and chat history. Transition to `REFINING_ITINERARY` when a valid refinement intent arrives, or stay here for read-only Q&A.
- **REFINING_ITINERARY:** Backend parses refinement intent, retrieves replacements, applies proposed changes, and validates the new draft. Store pending intent, change set, candidate alternatives, base version, and validation result. Transition to `ITINERARY_UPDATED` on success or `ERROR`/`CHAT_ENABLED` with explanation on failure.
- **ITINERARY_UPDATED:** A new accepted version exists. Store updated itinerary, incremented version, change summary, previous version pointer, and validator report. Transition back to `CHAT_ENABLED` so the user can continue refining.
- **ERROR:** Represents recoverable or terminal system failure. Store error code, safe user message, failed state, retry action, and rollback target. Transition to `FORM_INPUT`, `BUILDING_ITINERARY`, or `CHAT_ENABLED` depending on where recovery should resume.

### 4. Applicable to Current SoulViet Architecture

| Current Module | Lesson | Short-term Action |
| -------------- | ------ | ----------------- |
| `index.html` | UI should follow backend state, not invent its own flow. | Hide chat until response includes `itinerary_id`, `version`, and ready/chat-enabled state. |
| `views/travel_view.py` | Route should be thin and state-aware. | Return structured state fields and validation errors; do not embed transition logic in route code. |
| `models/user_request.py` | Form fields are slots that need safe parsing and validation. | Replace raw casts with request validation result: valid slots, missing slots, invalid slots. |
| `services/itinerary_service.py` | Itinerary generation is a state transition, not just a function call. | Treat draft building and accepted itinerary saving as separate steps; mutate state only after validation. |
| `services/planner_service.py` | Planner should build drafts inside `BUILDING_ITINERARY`/`REFINING_ITINERARY`. | Return draft plus reasons/warnings without owning final acceptance. |
| `services/llm_service.py` | LLM should not decide state or accepted entities. | Keep it as writer/intent helper over structured data; never let it save itinerary changes directly. |
| future `ItineraryStateStore` | Backend needs itinerary identity, version, current state, and history. | Add in-memory/file-backed MVP store before chat refinement. |
| future `ChatRefinementService` | Chat must operate only after itinerary exists. | Accept `itinerary_id`, `version`, and message; parse intent, apply change, validate, then save new version. |

### 5. Applicable to Rebuilt SoulViet Architecture

- **`src/state/conversation_state_machine.py`:** Owns allowed states, transition rules, transition guards, and recovery paths.
- **`src/state/itinerary_state_store.py`:** Persists `itinerary_id`, version, accepted itinerary, request snapshot, validation report, selected IDs, pending changes, and history.
- **`src/chat/intent_parser.py`:** Converts chat text into typed intents such as remove, replace, add food, reduce cost, lighten schedule, increase culture, or change style.
- **`src/chat/refinement_service.py`:** Orchestrates refinement from current itinerary version through retrieval, change application, validation, and saved update.
- **`src/chat/change_applier.py`:** Applies typed changes to a copy of current itinerary, never directly to accepted state.
- **`src/validation/request_validator.py`:** Validates request slots before `BUILDING_ITINERARY` and returns structured errors instead of runtime exceptions.

New data flow:

```text
form submit
-> validate request
-> create itinerary state
-> build itinerary
-> validate
-> save accepted itinerary
-> enable chat
-> parse chat refinement
-> update itinerary version
-> validate again
-> return updated itinerary
```

### 6. Risks / Anti-patterns

- Do not let chat run when no accepted itinerary exists.
- Do not omit `itinerary_id` and `version`; chat refinement without identity/version can edit the wrong state.
- Do not let the LLM directly rewrite the accepted itinerary without passing through validators.
- Do not store important state only in the frontend while the backend remains stateless.
- Do not leave transitions vague, for example jumping from form submit directly to chat without saved itinerary state.
- Do not ignore cancel, error, and retry paths; long-running build/refine steps need recovery.
- Do not allow UI state and backend state to diverge; frontend should render the backend's current state/version.

### 7. Key Takeaways

1. SoulViet needs a backend-owned conversation state machine before reliable itinerary chat.
2. Slot filling belongs in request validation and `FORM_INPUT`, not inside planner or LLM prompts.
3. Chat refinement must be versioned and must edit the current accepted itinerary, not regenerate from scratch.
4. LLMs can parse or explain, but validators and state transitions decide what becomes accepted.
5. Error, retry, hold/resume, and cancel flows should be designed early because generation/refinement can fail.

### 8. Impact On Roadmap

| Phase | Impact |
| ----- | ------ |
| Phase 0: architecture decision | Choose Controlled Core Rebuild and define the state machine contract before adding chat. |
| Phase 1: correctness | Fix validation and mutation bugs first so state transitions save only correct data. |
| Phase 4: itinerary state | Add `itinerary_id`, version, accepted itinerary, selected IDs, request snapshot, and history. |
| Phase 5: chat after itinerary | Show chat only after `ITINERARY_READY`/`CHAT_ENABLED` and require itinerary identity/version. |
| Phase 6: chat refinement | Implement intent parsing, change application, validation, and version increment through `REFINING_ITINERARY`. |
| Phase 7: validator service | Make validators the gatekeeper for transitions into `ITINERARY_READY` and `ITINERARY_UPDATED`. |
| Phase X: controlled core rebuild | Extract `state/`, `chat/`, `validation/`, and `planning/` as clean modules while keeping current MVP as baseline. |

### 9. Decision Signal

- State machine ideas can be patched into the current architecture only as a short-term guard: return `itinerary_id`, `version`, and status from `/plan`, hide chat until ready, and avoid mutating accepted state before validation.
- For the real product, state/chat/refinement should be split into new modules because current route/service boundaries are too weak for versioned chat refinement.
- Chat should come after request validation, itinerary correctness, and itinerary state exist. In roadmap terms, chat UI can appear after Phase 4 and real refinement should wait until Phase 6.
- Recommended direction remains **Controlled Core Rebuild**: refactor gradually, but build new state/chat/refinement boundaries instead of forcing them into the current monolith.

Next file to read: `docs/repo_exp/container-bay-plan-validator_for_graph.md`.

## container-bay-plan-validator_for_graph.md

### 1. Main Ideas

- The file only gives a short note on `container-bay-plan-validator` itself and says the original repo is not directly related to RAG/travel, but its validation idea is still useful for SoulViet.
- The broader exp file recommends adding a dedicated `Validator` step after research/retrieval and planning to check whether the generated plan violates constraints such as time, opening hours, distance, and factual grounding.
- The validation mindset is: planner proposes, validator checks, and only validated output should be accepted or shown as reliable.
- Hard constraints should be deterministic and must fail the itinerary when violated; soft preferences should produce warnings, score penalties, or fallback/retry attempts.
- For SoulViet, this pattern directly addresses current bugs where state can mutate before a day/itinerary is known to be valid.

### 2. Architecture / Design Pattern

- **validator service:** Put validation in a separate service or layer after retrieval/planning and before state mutation. It should not be hidden inside prompt text or frontend checks.
- **rule engine:** Represent each check as a named rule with inputs, severity, pass/fail status, affected object, and repair suggestion.
- **constraint model:** Split constraints into hard constraints and soft preferences. Hard constraints block acceptance; soft preferences produce warnings or trigger fallback.
- **validation result model:** Return structured results with `is_valid`, `errors`, `warnings`, `failed_rules`, `passed_rules`, `repair_suggestions`, `severity`, affected day/slot/place, and retry metadata.
- **pass/fail/warning logic:** A plan is accepted only when all hard rules pass. Warning rules can pass the itinerary but should be visible to backend logs and frontend UI.
- **explainable error reporting:** Each failure should explain what failed, where it failed, why it matters, and what can be retried or relaxed.
- **deterministic validation:** Budget, duration, duplicate places, graph existence, route feasibility, and state/version checks must be code-based, not LLM-judged.
- **planner/validator separation:** Planner builds draft candidates and day plans; validator decides whether they are acceptable.
- **validation/state separation:** `used_ids`, itinerary state, and itinerary version should change only after validation passes.
- **fallback/retry after fail:** If hard validation fails, retry with controlled repair such as replacing a place, relaxing a soft style preference, reducing slot count, or expanding candidate radius.

### 3. Validation Lessons For SoulViet

#### Hard Constraints

- `duration` must be valid and within supported range.
- `budget` must be parseable, positive, and sufficient for requested hard budget mode.
- Each selected place must exist in the graph/dataset and have required fields for itinerary rendering and route/time logic.
- A place must not be duplicated across accepted itinerary items unless explicitly allowed.
- Hard budget must not be exceeded when user requires strict budget.
- A place with missing core data such as ID/name/coordinates should not be accepted into a route-dependent itinerary.
- `used_ids` must not update before validation pass.
- Chat refinement must not run before an accepted itinerary exists with `itinerary_id` and `version`.
- State/version must match before applying chat changes.
- LLM output must not introduce places outside accepted candidates or graph IDs.

#### Soft Preferences

- Vibe/style match should influence score and warnings, not always block itinerary creation.
- Higher rating and review count should be preferred but not required.
- Lower travel distance should be preferred, with warnings when the route is less efficient.
- Cultural depth, local food, scenic stops, and special experiences should be optimized as preference goals.
- Light pace should reduce schedule density; if not possible, return a warning and explain the tradeoff.
- Budget comfort margin should be preferred even when hard budget is not exceeded.
- Fallback can relax vibe/style or rating thresholds while preserving hard constraints.

#### Validation Areas

- **request validation:** Validate duration, budget, vibe/style, optional pace, and future form slots before retrieval.
- **place validation:** Check IDs, names, coordinates, price, type/vibe lists, graph membership, and evidence fields.
- **day plan validation:** Check each day has feasible slot count, no duplicates, acceptable travel distance, and enough time budget.
- **itinerary validation:** Check total days, total budget, selected IDs, route consistency, warnings, and validation report completeness.
- **budget validation:** Distinguish hard budget fail from soft cost warning.
- **time validation:** Check estimated visit duration and travel time against daily pace.
- **duplicate place validation:** Prevent repeated place IDs across accepted slots and across day retries.
- **route/distance validation:** Reject impossible or extreme route sequences; warn on inefficient but still possible sequences.
- **pace validation:** Warn or retry when the plan is too dense for the requested pace.
- **style/vibe matching validation:** Treat as soft unless the user explicitly makes it mandatory.
- **graph/state consistency validation:** Ensure itinerary items point to graph places and accepted state version is current.
- **evidence/grounding validation:** Require evidence refs for risky claims such as opening hours, booking requirements, accessibility, or closures when those features are added.
- **chat refinement validation:** Validate the proposed updated itinerary as a new draft before saving a new version.

### 4. Applicable to Current SoulViet Architecture

| Current Module | Validation Lesson | Short-term Action | Risk If Not Fixed |
| -------------- | ----------------- | ----------------- | ----------------- |
| `models/user_request.py` | Request slots need deterministic validation before services run. | Add safe parsing and return validation errors for duration/budget/vibe. | Bad input can cause 500s or invalid planning constraints. |
| `models/place.py` | Place model should define required itinerary fields. | Add/align normalized fields for ID, coordinates, price, types, vibes, rating, and evidence placeholders. | Planner may accept places that cannot be rendered, scored, or routed. |
| `services/graph_service.py` | Graph output must be normalized before filtering/scoring. | Coerce numeric fields and normalize `types`/`vibes` to lists. | Filtering, scoring, routing, and time estimates can silently break. |
| `services/filter_service.py` | Filtering should distinguish hard filters from soft preferences. | Keep hard filters strict; expose soft misses as warnings or score inputs. | Narrow requests can return empty results without a repair path. |
| `services/scoring_service.py` | Scoring is not validation. | Return score breakdown, but do not use score alone as pass/fail. | High score may hide hard violations; low score may wrongly reject feasible plans. |
| `services/cluster_service.py` | Candidate generation should be deterministic and read-only. | Remove random behavior or seed it; do not mutate accepted IDs during candidate exploration. | Results become hard to test and rejected candidates can affect later days. |
| `services/planner_service.py` | Planner must guard invalid candidates before scoring. | Check `place is None` before scoring or slot use. | Missing graph neighbors can crash generation. |
| `services/itinerary_service.py` | Validation must happen before `used_ids` and accepted itinerary mutate. | Build draft day, validate, then update `used_ids` only after accept. | Current `used_ids` bug can lose candidates when a day is rejected. |
| `views/travel_view.py` | API should return validation reports, not just generic errors. | Return structured errors/warnings and status codes for invalid request or failed planning. | Frontend cannot explain why planning failed or what user should change. |
| `index.html` | Frontend should display backend validation errors clearly. | Render errors, warnings, and retry suggestions; keep chat hidden until valid itinerary state exists. | Users see vague failures and may chat against missing/invalid state. |

### 5. Applicable to Rebuilt SoulViet Architecture

- Add `src/validation/request_validator.py` for form slot validation before retrieval.
- Add `src/validation/place_validator.py` for normalized place/candidate checks.
- Add `src/validation/day_plan_validator.py` for slot count, duplicate, route, time, and pace checks per day.
- Add `src/validation/itinerary_validator.py` as the aggregate validator before saving itinerary state.
- Add `src/validation/budget_validator.py`, `src/validation/time_validator.py`, `src/validation/duplicate_validator.py`, `src/validation/route_validator.py`, `src/validation/style_validator.py`, and `src/validation/state_validator.py` as focused rule groups.
- Add `src/models/validation_result.py` with fields: `is_valid`, `errors`, `warnings`, `failed_rules`, `passed_rules`, `repair_suggestions`, `severity`, `affected_day`, `affected_slot`, `affected_place_id`, `evidence_refs`, `can_retry`, and `retry_strategy`.
- Place validators between planner and state store: planner returns a draft, validators return a decision, and state store saves only accepted plans.
- Chat refinement should load current state/version, apply proposed changes to a copy, validate the copy, then save as a new version only if hard constraints pass.
- API responses should include `validation_report`, `warnings`, `retry_strategy`, and user-safe repair suggestions.
- Frontend should render validation feedback near the affected day/slot/place and show global warnings separately from blocking errors.

### 6. Validator Pipeline Design For SoulViet

```text
Validate user request
-> Retrieve candidate places (read-only)
-> Validate candidate places
-> Build draft day plan
-> Validate day plan
-> If hard constraint fails: do not mutate used_ids; retry or return structured errors
-> If soft preference fails: add warning or retry with controlled fallback
-> If pass: accept day/item
-> After accept: update used_ids
-> Validate full itinerary
-> Save itinerary state/version
-> Return structured response with validation report
```

- Retrieval is read-only and must not change selected IDs or itinerary state.
- Planning creates drafts and proposed changes only.
- Validator decides accept/reject and explains failures.
- State mutation happens only after validation pass.
- LLM cannot override validator decisions or introduce accepted entities outside validated data.

### 7. Risks / Anti-patterns

- Do not validate after mutating `used_ids` or saved itinerary state.
- Do not make validator rules vague or prompt-only.
- Do not mix scoring with validation; score optimizes, validation gates.
- Do not let the LLM decide pass/fail for hard constraints.
- Do not return generic errors such as "cannot build itinerary" without affected rule and repair suggestion.
- Do not make validators so rigid that no itinerary can pass; use warnings and fallback for soft preferences.
- Do not ignore warnings, because repeated warnings reveal retrieval/planning quality issues.
- Do not validate only in the frontend; backend must own correctness.
- Do not add chat refinement until validator and itinerary state/versioning exist.

### 8. Key Takeaways

1. **Bài học:** Planner and validator must be separate. **Áp dụng vào SoulViet:** `ItineraryService` should build drafts, then call validators before acceptance. **Ảnh hưởng đến phase nào:** Phase 1 and Phase 7.
2. **Bài học:** Hard constraints and soft preferences need different behavior. **Áp dụng vào SoulViet:** budget/duration/duplicates/state are hard; vibe/rating/pace are often soft. **Ảnh hưởng đến phase nào:** Phase 1, Phase 2, and Phase 7.
3. **Bài học:** Validation results must be explainable. **Áp dụng vào SoulViet:** API should return failed rules, affected place/day/slot, and retry suggestions. **Ảnh hưởng đến phase nào:** Phase 2 and Phase 3/frontend rendering.
4. **Bài học:** State mutation only after validation pass. **Áp dụng vào SoulViet:** fix `used_ids` mutation and save itinerary versions only after validator approval. **Ảnh hưởng đến phase nào:** Phase 1 and Phase 4.
5. **Bài học:** Retry/fallback should be controlled. **Áp dụng vào SoulViet:** relax soft preferences or replace invalid candidates without violating hard constraints. **Ảnh hưởng đến phase nào:** Phase 6, Phase 7, and Phase 9.

### 9. Impact On Roadmap

| Phase | Impact From container-bay-plan-validator | Suggested Action |
| ----- | ---------------------------------------- | ---------------- |
| Phase 0: architecture decision | Validator is a core architecture boundary, not a helper prompt. | Choose Controlled Core Rebuild and define validation contracts early. |
| Phase 1: correctness | Current bugs are mostly validation/mutation-order issues. | Fix `used_ids`, `place is None`, request parsing, graph normalization, and deterministic fallback. |
| Phase 2: structured itinerary output | Validation needs structured response fields. | Add `validation_report`, `errors`, `warnings`, and `retry_strategy` to `/plan`. |
| Phase 4: itinerary state | State must save only accepted validated itinerary versions. | Add state/version only after validation pass and keep validation report with state. |
| Phase 5: chat after itinerary | Chat availability is a validation/state rule. | Enable chat only for valid `itinerary_id` and current `version`. |
| Phase 6: chat refinement | Every refinement is a new draft requiring validation. | Validate changed itinerary copy before saving a new version. |
| Phase 7: validator service | This file directly supports a dedicated validator phase. | Build focused validators and shared `ValidationResult`. |
| Phase 8: Graph RAG improvement | Graph retrieval must feed validators with reliable IDs/properties/evidence. | Validate graph/state consistency and evidence refs for accepted items. |
| Phase 9: evaluation | Validation rules become testable acceptance criteria. | Add fixtures for budget, time, duplicates, missing fields, bad routes, and chat edits. |
| Phase X: controlled core rebuild | Clean planner/validator/state boundaries reduce monolith risk. | Extract validation before adding complex Graph RAG and refinement features. |

### 10. Decision Signal

- A small validator can be patched into current `ItineraryService` to fix urgent correctness bugs, especially `used_ids` mutation before validation pass.
- However, the repeated need to validate request, candidates, day plan, full itinerary, state, and chat changes is a strong signal to create a separate `ValidatorService` or `src/validation/` package.
- The `used_ids` bug is a clear architecture smell: planning, validation, and state mutation are currently too coupled.
- Validator work should begin in Phase 1 for correctness fixes, then become a dedicated Phase 7 service with shared `ValidationResult` and test fixtures.
- Chat refinement should wait until validator and itinerary state/versioning are in place; otherwise chat will amplify invalid state and hard-to-debug mutations.
- Recommendation: **Controlled Core Rebuild**. Patch urgent validation bugs in the MVP, but build clean validation/state boundaries as the foundation for itinerary chat and Graph RAG improvements.

Next file to read: `docs/repo_exp/medical-citation-agent_for_graph.md`.

## medical-citation-agent_for_graph.md

### 1. Main Ideas

- The exp file has limited direct public detail about `medical-citation-agent`, but the repo name and surrounding analysis point to a RAG agent focused on medical citation, evidence retrieval, and source-backed answers.
- The reusable lesson is not medical-domain logic; it is the discipline of making important answers traceable to retrieved evidence and deterministic source metadata.
- Citation/grounding matters because LLM output can sound fluent while inventing facts. In SoulViet, the same risk appears when the model explains destinations, costs, opening hours, suitability, or refinement changes without source-backed data.
- A citation-oriented system should attach source/evidence to claims before writing the final answer, not after the answer is generated.
- For SoulViet, the equivalent is a grounded itinerary: each selected place should carry structured reasons, score breakdown, evidence references, warnings, and validation status.
- The LLM should be a response writer over accepted itinerary/evidence, not the authority that chooses places or invents citations.

### 2. Architecture / Design Pattern

- **citation-first workflow:** Retrieve and organize evidence before final response generation. The final writer receives only accepted itinerary data, evidence bundles, and validation reports.
- **evidence retrieval:** Retrieve structured fields from the dataset/graph and, later, text evidence from descriptions, reviews, official pages, menus, opening hours, blogs, or OCR.
- **evidence bundle:** Package the evidence needed for each claim or itinerary item: source IDs, field names, raw values, normalized values, confidence, timestamps, and snippets when available.
- **claim extraction:** Split generated or planned outputs into checkable claims such as “this place matches culture,” “this route is nearby,” “this cost fits budget,” or “this place is open in the evening.”
- **source mapping:** Map every checkable claim back to a deterministic source such as dataset field, graph edge, validation rule, score component, or external source document.
- **verifier/checker:** Check whether a claim is supported, unsupported, contradicted, or only inferred. Unsupported claims should be removed, downgraded, or turned into warnings.
- **grounded response generation:** The writer produces natural language only from structured itinerary items, evidence refs, score breakdowns, and warnings.
- **separation:** Retrieval finds evidence, verification checks claims, and final answer generation explains accepted facts. These should not be one prompt blob.
- **deterministic citation metadata:** Evidence IDs and source IDs should be stable, reproducible, and stored with itinerary state so chat refinement can preserve or update them.
- **human-readable explanation:** Evidence should be shown as clear reasons and warnings, not only raw citation IDs.

### 3. Grounding / Citation Lessons For SoulViet

- Each place in an itinerary needs a `why_selected` field that explains the grounded reason for selection.
- Each reason should come from fields, tags, graph edges, score components, or evidence refs: type/vibe match, price fit, rating confidence, proximity, selected slot, route feasibility, and validation pass.
- Each recommendation should include `evidence_refs` when real source evidence exists, or structured grounding when only dataset/graph fields are available.
- Chat refinement must not invent new places outside the graph/dataset; replacement candidates must come from retrieval and keep evidence refs.
- `LLMService` should explain accepted itinerary data only. It should not create new facts, new source names, fake citations, or unsupported claims.
- SoulViet should distinguish certain data, source-backed evidence, and light LLM inference.
- If later adding web/API/review data, evidence/source validation becomes required: source freshness, source type, URL, source confidence, and field-to-claim support.
- Itinerary output should include `why_selected`, `score_breakdown`, `evidence_refs`, `warnings`, and `validation_report` so users can trust and debug recommendations.

#### Structured Grounding

- Structured grounding comes from current graph/dataset/runtime fields: `place_id`, `name`, `address`, `type`, `vibe`, `price`, `rating`, `review_count`, `lat/lng`, graph edges, selected slot, score breakdown, and validation report.
- This is the best short-term grounding source because SoulViet already has structured place data and graph relationships.
- Structured grounding can support claims such as “matches requested vibe,” “fits budget,” “is close to previous place,” “is assigned to evening slot,” or “passed duplicate validation.”

#### Source Evidence

- Source evidence comes from text or external sources: description, review snippet, opening hours, policy document, menu, travel blog, official page, image/OCR, `source_id`, and `last_verified_at`.
- SoulViet's dataset has fields that can become early source evidence, but the current runtime artifact does not preserve enough of them.
- Source evidence should be introduced gradually after the structured itinerary contract is stable, starting with dataset descriptions/reviews/opening hours/images before web crawling.

#### LLM Inference

- The LLM may write natural explanations, summarize reasons, explain trade-offs, write itinerary text, and phrase change summaries.
- The LLM must not create new facts, cite nonexistent sources, invent opening hours, invent prices, or add places outside accepted candidates.
- Any LLM-generated wording should be treated as presentation over grounded data, not as evidence.

### 4. Applicable to Current SoulViet Architecture

| Current Module | Grounding Lesson | Short-term Action | Risk If Not Fixed |
| -------------- | ---------------- | ----------------- | ----------------- |
| `dataset/SoulViet_Dataset.csv` | Dataset is the first evidence source, but fields need stable IDs and source meaning. | Treat descriptions, address, images, activities, operation hours, rating, reviews, type, vibe, and price as evidence-capable fields. | Itinerary claims will be based on vague LLM text instead of stored data. |
| `scripts/build_graph.py` | Graph nodes/edges should preserve evidence-related properties. | Add or keep source fields and stable place IDs when building Neo4j. | Graph cannot explain why a place was selected beyond `NEAR`. |
| `scripts/export_to_pt.py` | Runtime artifact should not drop evidence fields. | Export address, activities, images, opening hours, descriptions, review count, and source-like metadata into `graph.pt`. | Backend cannot ground UI cards or LLM explanations even if CSV has data. |
| `services/graph_service.py` | Retrieval should return candidate metadata and evidence refs, not raw neighbors only. | Normalize and expose `place_id`, address, type/vibe lists, price, rating, review count, graph reason, and placeholder `evidence_refs`. | Downstream services cannot build grounded reasons or citations. |
| `services/filter_service.py` | Filters are structured evidence for why a place matched or failed. | Return matched/missed criteria for style/type/budget instead of only filtered lists. | Users and validators cannot understand why candidates were included or excluded. |
| `services/scoring_service.py` | Score is explainable evidence, not just a number. | Return `score_breakdown` for vibe/type match, rating, review confidence, price fit, distance, slot fit, and fallback penalties. | LLM may invent reasons because the real scoring reason is hidden. |
| `services/cluster_service.py` | Proximity/cluster selection should be traceable. | Return cluster/proximity reason and deterministic ordering. | Route/location claims become ungrounded and hard to reproduce. |
| `services/planner_service.py` | Slot assignment should create structured grounding. | Include selected slot, reason for slot fit, estimated duration/cost, and warnings in draft items. | Itinerary text may claim a place fits morning/evening without support. |
| `services/itinerary_service.py` | Accepted itinerary should store `why_selected` and `evidence_refs`. | Build each item with `why_selected`, `score_breakdown`, `evidence_refs`, `warnings`, and `validation_status` before LLM writing. | Chat refinement and UI will lose the basis for current itinerary decisions. |
| `services/llm_service.py` | LLM should be a response writer only. | Pass structured itinerary/evidence into prompts and forbid unsupported facts/citations. | LLM can hallucinate sources, opening hours, or reasons. |
| `views/travel_view.py` | API should return grounded structured data. | Include item-level reasons, warnings, score breakdowns, evidence refs, and validation report in `/plan` response. | Frontend can only render generic AI text and cannot show trust signals. |
| `index.html` | Frontend should show grounding in user-readable form. | Render place cards with why selected, address, score/warnings, and evidence placeholders; keep citations simple for MVP. | Users cannot inspect or trust recommendations, and chat changes look arbitrary. |

### 5. Applicable to Rebuilt SoulViet Architecture

- Add `src/evidence/evidence_store.py` to persist evidence records and source metadata.
- Add `src/evidence/evidence_retriever.py` to fetch structured evidence and later text/source evidence for selected candidates.
- Add `src/evidence/source_mapper.py` to map dataset fields, graph edges, external docs, and validation rules into stable evidence IDs.
- Add `src/evidence/claim_verifier.py` to classify claims as supported, unsupported, contradicted, or inferred.
- Add `src/retrieval/context_builder.py` to assemble bounded context packages for planner, validator, and response writer.
- Keep `src/llm/response_writer.py` separate from retrieval and planning so the LLM only writes from accepted data.
- Add `src/models/evidence.py`, `src/models/score_breakdown.py`, and richer `src/models/itinerary.py` so evidence becomes part of domain models.
- Add `src/validation/evidence_validator.py` to check that high-risk claims and itinerary items have adequate grounding.

Suggested `Evidence` schema: `evidence_id`, `source_type`, `source_id`, `source_name`, `field_name`, `raw_value`, `normalized_value`, `confidence`, `last_verified_at`, `supports_claim`, `place_id`, `itinerary_item_id`, `url`, `snippet`.

Suggested `ItineraryItem` fields: `place_id`, `place_name`, `slot`, `estimated_cost`, `estimated_duration`, `why_selected`, `score_breakdown`, `evidence_refs`, `warnings`, `validation_status`.

- Evidence layer should sit between retrieval/planning and response writing: retriever returns candidates, context builder attaches evidence bundle, validator checks it, state store saves accepted evidence refs, and response writer explains it.
- Graph nodes/edges should carry evidence refs for facts such as type, vibe, location, price, opening hours, route/proximity, and source freshness.
- Itinerary items should keep evidence refs at item level, not only global response level, so chat refinement can update one item without losing the rest.
- Chat refinement should preserve evidence for unchanged items and regenerate evidence refs for replaced/updated items.
- API responses should return a compact `evidence` map keyed by evidence ID plus item-level `evidence_refs` to avoid duplicating long snippets.
- Frontend should show readable reasons by default and expandable evidence/source details when available.
- Validator should require structured grounding for every item and stronger source evidence for risky claims such as opening hours, closures, accessibility, booking rules, or official policy.

### 6. Grounded Itinerary Response Design

`POST /plan` should return: `itinerary_id`, `version`, `days`, `items`, `summary`, `total_estimated_cost`, `total_estimated_time`, `validation_report`, `warnings`, `evidence`, `ai_text`.

Each itinerary item should include: `place_id`, `name`, `address`, `slot`, `type`, `vibe`, `cost`, `duration`, `why_selected`, `score_breakdown`, `evidence_refs`, `alternatives`, `warnings`.

- Structured data is the source of truth; `ai_text` is presentation only.
- Evidence refs should travel with each item so users can see why a place was selected.
- The LLM should write `ai_text` from structured itinerary, validation report, and evidence bundle only.
- If evidence is missing, the API should return a warning or low confidence instead of letting the LLM fill the gap.
- Chat refinement must preserve existing evidence refs for unchanged items and update evidence refs for changed items.

### 7. Risks / Anti-patterns

- Do not create fake citations or placeholder sources that look real.
- Do not let the LLM invent source names, URLs, snippets, opening hours, policies, prices, or review claims.
- Do not attach unrelated evidence just to make an answer look grounded.
- Do not copy medical citation logic directly into travel; travel needs place, route, cost, slot, and preference grounding.
- Do not make citation too heavy for the MVP; start with structured grounding and evidence placeholders.
- Do not require every sentence to have a citation while the current dataset lacks real source documents.
- Do not call output grounded if it is only LLM-written prose without structured fields or source refs.
- Do not let chat refinement change itinerary items without updating evidence and validation status.
- Do not stuff too much evidence into prompts; use compact evidence bundles and IDs.
- Do not let citation replace validation; evidence says a fact is supported, while validation says an itinerary is feasible.

### 8. Key Takeaways

1. **Bài học:** Citation should be designed before final answer generation. **Áp dụng vào SoulViet:** build evidence bundles before `LLMService` writes itinerary text. **Ảnh hưởng đến phase nào:** Phase 2, Phase 3, and Phase 8.
2. **Bài học:** Structured data can be the first grounding layer. **Áp dụng vào SoulViet:** use `place_id`, fields, graph edges, score breakdown, and validation report before adding external citations. **Ảnh hưởng đến phase nào:** Phase 1 and Phase 2.
3. **Bài học:** LLM-written explanations are not evidence. **Áp dụng vào SoulViet:** make `LLMService` a response writer only and forbid unsupported facts. **Ảnh hưởng đến phase nào:** Phase 1, Phase 2, and Phase 6.
4. **Bài học:** Evidence must attach to items and claims, not only whole responses. **Áp dụng vào SoulViet:** store `evidence_refs` per itinerary item and update them during chat refinement. **Ảnh hưởng đến phase nào:** Phase 4, Phase 5, and Phase 6.
5. **Bài học:** Verification and validation are complementary. **Áp dụng vào SoulViet:** add evidence validation for source support and itinerary validation for feasibility. **Ảnh hưởng đến phase nào:** Phase 7, Phase 8, and Phase 9.

### 9. Impact On Roadmap

| Phase | Impact From medical-citation-agent | Suggested Action |
| ----- | ---------------------------------- | ---------------- |
| Phase 0: architecture decision | Evidence is a core boundary, not prompt decoration. | Choose Controlled Core Rebuild with future `evidence/`, `retrieval/`, `validation/`, and `llm/response_writer` separation. |
| Phase 1: correctness | Grounding starts with correct normalized fields. | Preserve IDs, numeric/list fields, address, ratings, price, and graph reasons. |
| Phase 2: structured itinerary output | Item-level grounding must be in the API contract. | Add `why_selected`, `score_breakdown`, `evidence_refs`, `warnings`, and `validation_report`. |
| Phase 3: frontend rendering | Users need readable trust signals. | Render reasons, warnings, address, scores, and expandable evidence/source details. |
| Phase 4: itinerary state | Evidence must persist with accepted itinerary versions. | Save item-level evidence refs and validation reports in itinerary state. |
| Phase 5: chat after itinerary | Chat should answer from current grounded itinerary. | Require `itinerary_id`/`version` and use accepted evidence for Q&A. |
| Phase 6: chat refinement | Replacement changes must update grounding. | Preserve evidence for unchanged items and regenerate/validate evidence for changed items. |
| Phase 7: validator service | Evidence support should be checked separately from feasibility. | Add `evidence_validator.py` for unsupported claims, source freshness, and high-risk fields. |
| Phase 8: Graph RAG improvement | Source evidence becomes stronger with hybrid retrieval. | Add evidence retriever, source mapper, context builder, and graph/vector evidence links. |
| Phase 9: evaluation | Grounding quality needs tests. | Evaluate evidence precision, unsupported claim rate, citation correctness, and hallucination rate. |
| Phase X: controlled core rebuild | Clean evidence boundaries reduce hallucination and monolith risk. | Extract evidence/context/response-writer modules while keeping MVP runnable. |

### 10. Decision Signal

- Evidence/grounding can be patched into the current architecture in a small way: add `why_selected`, `score_breakdown`, `warnings`, and placeholder `evidence_refs` inside `ItineraryService` and return them through `/plan`.
- Full citation should not be forced into the current `ItineraryService`; it needs separate `EvidenceService`, `ContextBuilder`, `ClaimVerifier`, and `ResponseWriter` boundaries to stay testable.
- SoulViet should not add full external citation immediately. Start with structured dataset grounding, then preserve richer dataset fields, then add external sources later.
- Evidence should begin from the structured dataset and graph because those are already available and deterministic. External web/API/review evidence should come after the schema, validation, and state contracts are stable.
- The LLM should only write final prose, summarize trade-offs, and explain accepted changes from structured itinerary and evidence bundle.
- Chat refinement should wait until itinerary state, validator, and minimum evidence grounding exist; otherwise it will amplify hallucinated reasons and unsupported replacements.
- Recommendation: **Controlled Core Rebuild**. Patch lightweight grounding into the MVP, but design evidence/context/response-writing as clean modules for the rebuilt core.

Next step: Task 2 Core Summary

## e-commerce-project_for_graph.md

### 1. Main Ideas

- The file describes an e-commerce Graph RAG/search system for product search and recommendation: API request -> request model -> graph retrieval -> optional vector retrieval -> result merge/ranking -> LLM answer.
- The reusable pattern is a production-oriented search/recommendation backend with clear service boundaries: API route, request schema, graph service, embedding service, RAG/search orchestrator, LLM service, dataset/build scripts, and runtime graph artifact.
- Products map to SoulViet places because both need catalog entities, categories/tags, price/budget, rating/popularity, user intent matching, filters, ranking, and explainable recommendations.
- Travel differs from e-commerce because SoulViet must produce a feasible itinerary, not just top-k places. Route, time, day/slot assignment, duplicates, pace, state, and validation are mandatory after ranking.
- The file emphasizes production basics: request validation, graph artifact loading errors, missing API key handling, dependency hygiene, tests, logging, monitoring, and clear API contracts.

### 2. Architecture / Design Pattern

- **entity/product catalog:** E-commerce uses `Product`, `Brand`, `Category`, `User`, and relations such as `BRAND_OF`, `IN_CATEGORY`, `BOUGHT`, `SIMILAR_TO`; SoulViet should use `Place`, `City`, `District`, `Type`, `Vibe`, `TimeSlot`, `Route`, `Evidence`, and `ItineraryItem`.
- **search service:** A route accepts `query`, `filters`, and `top_k`, validates them, then delegates to a search/RAG service. SoulViet should similarly keep `/plan` and future `/chat/refine` thin.
- **filter service:** Filters narrow impossible or mandatory constraints before ranking. Travel filters must distinguish hard constraints from soft preferences.
- **scoring/ranking service:** Graph results and vector results need normalized scores before fusion; rating, price, semantic match, and graph match cannot be blindly summed.
- **recommendation pipeline:** retrieve candidates -> dedupe -> score -> rerank -> explain -> generate final text. SoulViet adds planner and validator after recommendation.
- **user preference matching:** User query/filters in e-commerce map to travel slots: destination, duration, budget, vibe/style, pace, food preference, must-visit/avoid, and constraints.
- **API contract:** Return structured `results` plus optional LLM `answer`; for SoulViet return structured itinerary/candidates/score breakdown/warnings plus optional `ai_text`.
- **backend layering:** Route -> model validation -> orchestration service -> graph/vector/LLM adapters is a useful separation.
- **data model/schema:** Stable IDs and normalized fields are required; mismatch between model and graph data causes runtime failures.
- **cache/vector DB:** Vector retrieval and caching are useful later, but only after graph/data normalization and score fusion are stable.
- **observability/error handling:** Validate input, catch graph load/DB/API errors, log retrieval/ranking latency, and return user-safe errors.

### 3. Recommendation / Scoring Lessons For SoulViet

Travel places are like products because they are catalog entities with IDs, categories, prices, ratings, popularity, tags, and similarity relations. They are different because a travel recommendation must fit a sequence, time slot, route, total budget, pace, and current itinerary state.

#### Hard Filters

- Valid destination/city/area if provided.
- Place exists in graph/dataset and has required ID/name/coordinates.
- Request duration and budget are parseable and supported.
- Minimum budget and mandatory request constraints are satisfied.
- Place is not duplicate in accepted itinerary unless explicitly allowed.
- Slot/time/opening rule is satisfied when that data is available.
- Chat refinement has valid `itinerary_id` and current `version`.

#### Ranking Signals

- Vibe/style match and type/category match.
- Rating and review_count confidence.
- Budget fit and cost comfort margin.
- Distance, cluster fit, route adjacency, and graph score/path reason.
- Time-slot/opening-hour fit.
- Diversity across types/areas/experiences.
- Popularity balanced against personalization.
- Evidence confidence and grounding quality.
- Semantic score when vector/evidence retrieval exists.

#### Post-ranking Validation

- Total budget and day budget feasibility.
- Total time, travel time, route feasibility, and pace.
- Duplicate places across days/slots.
- State/version consistency for chat refinement.
- Evidence/grounding for high-risk claims.
- Validator approval before itinerary state mutation.

- Hard filters should run before scoring to reduce bad candidates, but soft preferences should become score components or warnings.
- Score breakdown should expose `total_score`, component scores, penalties, matched reasons, and warnings.
- Fallback should relax soft filters in a controlled order: expand radius, broaden vibe/type, lower rating threshold, add alternatives, or reduce schedule density; never violate hard constraints.
- Recommendation creates ranked candidates; planner builds a draft itinerary; validator decides accept/reject; LLM only writes/explains.

### 4. Applicable to Current SoulViet Architecture

| Current Module | Recommendation Lesson | Short-term Action | Risk If Not Fixed |
| -------------- | --------------------- | ----------------- | ----------------- |
| `dataset/SoulViet_Dataset.csv` | Treat places as a searchable catalog with stable fields. | Ensure IDs, type, vibe, price, rating, reviews, address, coordinates, opening hours, and descriptions are normalized. | Ranking will depend on missing/dirty fields. |
| `models/user_request.py` | Request is a search/recommendation contract. | Safely validate duration, budget, vibe/style, optional filters, and defaults. | Bad input causes 500s or invalid candidates. |
| `models/place.py` | Place model should match graph/runtime schema. | Add normalized fields and optional score/evidence placeholders. | Frontend and planner cannot trust candidate shape. |
| `services/filter_service.py` | Separate hard filters from soft preferences. | Hard-filter required constraints; return soft misses as score inputs/warnings. | Narrow requests return empty results or wrong rejects. |
| `services/scoring_service.py` | Ranking needs explainable score breakdown. | Return component scores: style/type/budget/rating/distance/time/diversity/graph/evidence plus penalties. | LLM/front-end must invent reasons. |
| `services/cluster_service.py` | Candidate order must be deterministic and traceable. | Remove random shuffle or seed it; return cluster reason/ranking trace. | Results are hard to test/debug. |
| `services/graph_service.py` | Graph search should return score and path reason. | Return `graph_score`, matched edges, source node, path reason, and normalized properties. | Graph RAG remains opaque BFS/NEAR. |
| `services/planner_service.py` | Planner should consume ranked candidates. | Guard invalid candidates and separate slot assignment from candidate retrieval. | Planner mixes search and planning and can crash. |
| `services/itinerary_service.py` | Itinerary is not top-k recommendation. | Orchestrate ranked candidates -> draft -> validation -> state mutation only after pass. | `used_ids`/state bugs and infeasible plans persist. |
| `views/travel_view.py` | API should expose structured ranking/validation output. | Return score breakdowns, reasons, warnings, and fallback messages. | Frontend cannot explain results. |
| `index.html` | UI should show reasons, warnings, and fallback state. | Render place cards with matched reasons, score hints, warnings, and validation errors. | Users see generic AI text and cannot trust choices. |

### 5. Applicable to Rebuilt SoulViet Architecture

- Add `src/retrieval/hard_filter.py` for required constraints.
- Add `src/retrieval/hybrid_retriever.py` for graph + optional semantic/evidence recall.
- Add `src/retrieval/graph_ranker.py` for graph score, path reason, and traversal ranking.
- Add `src/scoring/place_scorer.py` and `src/scoring/score_breakdown.py` for explainable scoring.
- Add `src/recommendation/candidate_generator.py` and `src/recommendation/reranker.py` for candidate recall, dedupe, score fusion, diversity, and fallback.
- Keep `src/planning/itinerary_planner.py` focused on day/slot itinerary drafts.
- Keep `src/validation/itinerary_validator.py` as the acceptance gate.

Recommended `ScoreBreakdown`: `total_score`, `style_score`, `type_score`, `budget_score`, `rating_score`, `distance_score`, `time_slot_score`, `diversity_score`, `graph_score`, `evidence_score`, `penalties`, `matched_reasons`, `warnings`.

- API responses should include item/candidate IDs, component scores, rank, reasons, warnings, fallback strategy used, validation report, and optional `ai_text`.
- Frontend should render user-readable reasons and warnings per place, not raw scores only.
- Chat refinement should reuse the same recommendation pipeline when replacing a place, adding food, reducing cost, or changing vibe, then validate and save a new itinerary version.

### 6. Travel Recommendation Pipeline Design

1. Validate user request.
2. Resolve destination/style/budget seeds.
3. Apply hard filters.
4. Retrieve candidates from graph.
5. Optionally retrieve semantic/evidence matches.
6. Score candidates with score breakdown.
7. Rerank for diversity and route feasibility.
8. Build draft itinerary by day/slot.
9. Validate draft itinerary.
10. If fail, retry with controlled fallback.
11. If pass, save itinerary state.
12. Return structured itinerary with reasons/evidence/warnings.

Recommendation creates candidate/ranking only. Planner creates the draft itinerary. Validator decides accept/reject. LLM only writes/explains. An itinerary is not a simple top-k list because sequence, budget, time, route, and state matter.

### 7. Risks / Anti-patterns

- Do not copy product ranking directly into travel itinerary planning.
- Do not pick top-score places and force them into a schedule.
- Do not ignore route, time, budget, pace, duplicates, and state constraints.
- Do not mix filtering, scoring, planning, validation, and mutation inside one god service.
- Do not let scoring replace validator decisions.
- Do not let rating/popularity dominate style, budget, route feasibility, or evidence quality.
- Do not use random shuffle in candidate selection when tests/debugging matter.
- Do not return unexplainable recommendations.
- Do not overbuild recommendation complexity before dataset/graph normalization is stable.

### 8. Key Takeaways

1. **Bài học:** Product search is a useful template for place candidate retrieval. **Áp dụng vào SoulViet:** model places as searchable catalog entities with filters, ranking, and reasons. **Ảnh hưởng đến phase nào:** Phase 1, Phase 2, Phase 8.
2. **Bài học:** Hard filters, ranking, and validation are different layers. **Áp dụng vào SoulViet:** split `FilterService`, `ScoringService`, planner, and validator responsibilities. **Ảnh hưởng đến phase nào:** Phase 1, Phase 7, Phase X.
3. **Bài học:** Hybrid graph/vector results need normalized score fusion. **Áp dụng vào SoulViet:** add graph_score, semantic_score, evidence_score, and score breakdown before LLM writing. **Ảnh hưởng đến phase nào:** Phase 2, Phase 8, Phase 9.
4. **Bài học:** Production RAG needs request validation and dependency/error handling. **Áp dụng vào SoulViet:** handle bad request, missing graph artifact, LLM/API errors, and empty results. **Ảnh hưởng đến phase nào:** Phase 1 and Phase 9.
5. **Bài học:** Top-k recommendation is not enough for itinerary. **Áp dụng vào SoulViet:** planner and validator must transform ranked candidates into feasible day/slot plans. **Ảnh hưởng đến phase nào:** Phase 5, Phase 7, Phase X.

### 9. Impact On Roadmap

| Phase | Impact From e-commerce-project | Suggested Action |
| ----- | ------------------------------ | ---------------- |
| Phase 0: architecture decision | Search/recommendation boundaries should be explicit. | Choose Controlled Core Rebuild and define retrieval/scoring/planning/validation contracts. |
| Phase 1: correctness | Fix request validation, graph artifact errors, normalized fields, deterministic fallback. | Stabilize MVP before adding complex ranking. |
| Phase 2: structured itinerary output | Score/reason fields belong in API output. | Add score breakdown, matched reasons, warnings, and validation report. |
| Phase 3: frontend rendering | Users need recommendation explanations. | Render score reasons, warnings, fallback notes, and structured place cards. |
| Phase 4: itinerary state | Accepted ranked selections need versioned persistence. | Store selected IDs, scores, reasons, warnings, validation reports. |
| Phase 5: chat after itinerary | Chat Q&A should read current ranked/accepted itinerary. | Require itinerary ID/version and expose current reasons. |
| Phase 6: chat refinement | Refinement should reuse recommendation pipeline. | Replace/add/reduce-cost changes call retrieval/scoring/planning/validation again. |
| Phase 7: validator service | Ranking cannot validate feasibility. | Build deterministic validators after candidate ranking and planning. |
| Phase 8: Graph RAG improvement | Graph + vector/evidence fusion becomes useful after normalization. | Add hybrid retriever, graph ranker, score fusion, evidence score. |
| Phase 9: evaluation | Recommendation quality needs metrics. | Test relevance, score stability, fallback behavior, duplicates, budget/time feasibility. |
| Phase X: controlled core rebuild | Current services are too coupled for production recommendation. | Extract hard filter, retrieval, scoring, reranking, planning, validation, state, chat. |

### 10. Decision Signal

- Some scoring fixes can be patched into current `FilterService`/`ScoringService`, especially hard-vs-soft filtering and score breakdown.
- The long-term design should split hard filter, graph retrieval, hybrid retrieval, scoring, reranking, planner, validator, and state into separate modules.
- `ItineraryService` should not continue owning retrieval, planning, validation, LLM writing, and mutation in one flow.
- Scoring should start in Phase 1/2 as explainable breakdowns, then mature in Phase 8 with graph/vector/evidence fusion.
- Chat refinement should reuse the same recommendation pipeline for replacements and additions, then validate before saving a new version.
- Recommendation: **Controlled Core Rebuild**. Patch urgent scoring/filtering into the MVP, but migrate toward clean recommendation/planning/validation boundaries.

Next step: Task 2 Core Summary

## Task 2 Core Summary

### 1. Core Files Read

- `docs/repo_exp/RAG-Anything_for_graph.md`
- `docs/repo_exp/graphrag-code_for_graph.md`
- `docs/repo_exp/Understand-Anything_for_graph.md`
- `docs/repo_exp/conversational-state-machine_for_graph.md`
- `docs/repo_exp/container-bay-plan-validator_for_graph.md`
- `docs/repo_exp/medical-citation-agent_for_graph.md`
- `docs/repo_exp/e-commerce-project_for_graph.md`

### 2. Top 20 Core Lessons For SoulViet

1. Graph RAG is graph + vector/evidence + workflow + validator, not BFS over `NEAR`.
2. Define a travel schema before adding more tools.
3. Keep index-time build/export separate from query-time retrieval/ranking.
4. Use stable IDs across dataset, graph, evidence, itinerary items, and state.
5. Separate hard filters, scoring/ranking, planning, validation, and state mutation.
6. Planner proposes drafts; validator accepts or rejects.
7. State mutates only after validation passes.
8. Itinerary is not top-k places; it is a feasible sequence under constraints.
9. Score breakdowns should explain style, type, budget, rating, distance, time, graph, evidence, penalties, and warnings.
10. Controlled fallback should relax soft preferences, not hard constraints.
11. LLM must not choose places outside graph/dataset.
12. LLM is a writer/explainer over accepted structured data.
13. Evidence/grounding should attach to itinerary items and claims.
14. Chat should appear only after an accepted itinerary exists.
15. Chat refinement requires `itinerary_id`, version, current state, and validation.
16. Route/API layers should stay thin; services own business logic.
17. Frontend should render structured itinerary, reasons, warnings, and validation state.
18. Production readiness needs input validation, dependency checks, logging, errors, tests, and docs.
19. Evaluation should cover retrieval relevance, budget/time feasibility, duplicates, grounding, and chat edits.
20. The best direction is Controlled Core Rebuild, not endless patching or a risky big-bang rewrite.

### 3. Lessons Grouped By Area

- **RAG / Graph RAG:** hybrid graph/vector/evidence retrieval, bounded context, LLM writer only.
- **Graph Schema / Retrieval:** typed nodes/edges, graph_score, path_reason, local constrained retrieval, stable IDs.
- **Recommendation / Scoring:** hard filters first, explainable scoring, reranking for diversity/route, controlled fallback.
- **Validation:** deterministic rules for request, place, day, budget, time, duplicate, route, state, evidence.
- **Evidence / Grounding:** item-level evidence refs, claim support, no fake citations, structured grounding first.
- **State Machine / Chat Refinement:** explicit states, slot filling, hold/resume, versioned refinement, retry/error handling.
- **Frontend / UX Flow:** form first, loading, itinerary cards, reasons/warnings, chat only after ready, updated version rendering.
- **Production Architecture:** service boundaries, config/env checks, logging, tests, CI, artifact handling, safe errors.

### 4. Current Architecture vs Rebuilt Architecture

| Area | Apply to Current Architecture | Apply to Rebuilt Architecture | Recommendation |
| ---- | ----------------------------- | ----------------------------- | -------------- |
| data ingestion / normalization | Preserve more CSV fields and coerce types in export/runtime. | Add `ingestion/` and `normalization/`. | Refactor now, rebuild boundary later. |
| graph schema | Improve `Place` properties and `NEAR` metadata. | Add typed travel graph schema. | Controlled rebuild. |
| graph retrieval | Return normalized candidates, graph score, reasons. | Add graph store + graph retriever/ranker. | Split gradually. |
| filter/scoring | Separate hard/soft filters and add score breakdown. | Add hard_filter, place_scorer, reranker. | Start immediately. |
| itinerary planning | Fix mutation and consume ranked candidates. | Add planning modules by day/slot/route. | Rewrite core. |
| validator | Patch request/day validation. | Add `validation/` package. | Must be separate. |
| evidence/grounding | Add reasons/evidence placeholders. | Add evidence store/retriever/verifier. | Structured grounding first. |
| itinerary state | Add simple ID/version after valid plan. | Add state store + state machine. | Before chat. |
| chat refinement | Do not add yet. | Add intent parser/refinement/change applier. | After state + validator. |
| frontend rendering | Render structured cards/errors/warnings. | Split frontend files and stateful UI. | Wait for API contract. |
| API contract | Return structured itinerary and validation report. | Define versioned `/plan`, `/itinerary`, `/chat/refine`. | Phase 2. |
| testing/evaluation | Add regression tests for known bugs. | Add layered unit/integration/eval tests. | Phase 9 and ongoing. |

### 5. Recommended Core Architecture Decision

- **Option A — Incremental Refactor:** good for quick demo and urgent fixes, but risks keeping `ItineraryService` as a god service.
- **Option B — Full Rebuild:** cleanest boundary, but risky if done as a big-bang rewrite before contracts are stable.
- **Option C — Controlled Core Rebuild:** recommended. Keep current MVP runnable while extracting validation, structured output, retrieval/scoring, planning, state, chat, evidence, and tests in phases.
- **Keep:** dataset, current MVP form, basic graph build/export ideas, and useful service concepts.
- **Refactor:** request validation, graph normalization, filter/scoring, structured API output, frontend rendering.
- **Rewrite:** itinerary orchestration, state/versioning, chat refinement, validator boundaries, response writer boundary.
- **Not now:** full vector DB, graph dashboard, big frontend rewrite, full external citation, free-form chat.

### 6. Proposed Target Core Modules

| Module | Role | Input | Output | Phase |
| ------ | ---- | ----- | ------ | ----- |
| `src/ingestion/` | Load raw data/sources. | CSV/API/docs | raw records | Phase 8 |
| `src/normalization/` | Normalize fields/types. | raw records | canonical places | Phase 1 |
| `src/graph/` | Build/query graph. | places/edges | graph candidates/paths | Phase 4/8 |
| `src/retrieval/` | Hard filter and hybrid recall. | request seeds | candidate set | Phase 4/8 |
| `src/scoring/` | Score and explain candidates. | candidates/request | score breakdown | Phase 2/8 |
| `src/planning/` | Build day/slot drafts. | ranked candidates | draft itinerary | Phase 5 |
| `src/validation/` | Gate correctness. | request/draft/state | validation result | Phase 3/7 |
| `src/state/` | Store itinerary versions/state. | accepted itinerary | state/version | Phase 4 |
| `src/chat/` | Parse/apply refinements. | message + state | proposed update | Phase 6 |
| `src/evidence/` | Retrieve/map/verify evidence. | places/claims | evidence refs | Phase 8 |
| `src/llm/` | Client and response writer. | accepted data | ai_text | Phase 2 |
| `src/api/` | Routes/contracts. | HTTP | structured JSON | Phase 2 |
| `src/models/` | Domain schemas. | data | typed objects | Phase 2 |
| `frontend/` | UI state/rendering. | API response | form/cards/chat | Phase 3/5 |
| `tests/` | Regression/evaluation. | fixtures | pass/fail metrics | Phase 9 |

### 7. Target Pipeline

```text
User form input
-> request validation
-> seed resolution
-> hard filter
-> graph retrieval
-> optional evidence/vector retrieval
-> scoring/reranking
-> draft itinerary planning
-> validator
-> accept itinerary
-> save itinerary state/version
-> render itinerary
-> enable chat
-> parse chat refinement
-> retrieve replacement/adjust candidates
-> validate updated itinerary
-> save new version
-> render updated itinerary
```

### 8. Phase Roadmap Based On Core Lessons

| Phase | Goal | Reason | Files/Modules | Done Criteria | Risk If Wrong |
| ----- | ---- | ------ | ------------- | ------------- | ------------- |
| Phase 0: Architecture decision | Write architecture decision. | Avoid random patching. | `docs/plan/03_architecture_decision.md` | Chosen boundaries/API. | Confused rebuild. |
| Phase 1: Correctness fixes in current MVP | Fix validation/mutation/normalization. | Stable base. | user_request, graph/filter/scoring/planner/itinerary | Known bugs fixed. | Bad plans persist. |
| Phase 2: Structured itinerary output | Return structured data. | Grounding/UI need contract. | API/models/llm | reasons/scores/warnings returned. | AI text remains source. |
| Phase 3: Frontend itinerary rendering | Show cards/reasons/errors. | Trust/UX. | `index.html`/frontend | Users see structured plan. | Opaque results. |
| Phase 4: Itinerary state/versioning | Persist accepted plan. | Required for chat. | state store | ID/version/state saved. | Chat edits wrong plan. |
| Phase 5: Chat after itinerary | Enable read-only/state-aware chat. | Chat only after ready. | frontend/api/state | Chat requires ID/version. | Premature chat. |
| Phase 6: Chat refinement | Apply versioned changes. | Real editing. | chat/retrieval/planning/state | update creates new version. | LLM rewrites freely. |
| Phase 7: Validator service | Dedicated deterministic validation. | Correctness gate. | validation package | hard/soft rules tested. | Scoring replaces validation. |
| Phase 8: Graph RAG improvement | Add richer graph/vector/evidence. | Better recall/grounding. | graph/retrieval/evidence | graph_score/evidence refs. | Tool overkill. |
| Phase 9: Tests/evaluation | Prevent regressions. | Production readiness. | tests/evals | fixtures pass. | Bugs return. |
| Phase X: Controlled core rebuild / migration | Move to clean `src/`. | Long-term maintainability. | all core modules | MVP migrated safely. | Big-bang failure. |

### 9. What Not To Do Yet

- Do not read optional files before Core Summary is accepted.
- Do not add chat before itinerary state exists.
- Do not add vector DB before graph normalization is stable.
- Do not call it Graph RAG if it is only BFS over `NEAR`.
- Do not let LLM choose places.
- Do not refactor frontend heavily before backend contract is stable.
- Do not build graph dashboard before itinerary output is correct.
- Do not stuff all evidence into prompts.
- Do not mix filter/scoring/planning/validation in one service.

### 10. Should We Read The Optional Files Next?

| File | Should Read Now? | Why / Why Not | Best Time To Read |
| ---- | ---------------- | ------------- | ----------------- |
| `Toonflowapp_for_graph.md` | Maybe later | Likely more UX/workflow than core correctness. | After architecture decision if UI flow needed. |
| `ai-agents-for-beginners_for_graph.md` | Later | Useful for agent patterns, but state/validator comes first. | Before chat agent design. |
| `awesome-llm-apps_for_graph.md` | Later | Broad inspiration, lower priority. | When exploring UX/LLM feature ideas. |
| `colleague-skill_for_graph.md` | Skip for now | Likely not core itinerary architecture. | Only if collaboration/agent skill pattern is needed. |
| `system-prompts-and-models-of-ai-tools_for_graph.md` | Later | Prompt/system design useful after boundaries exist. | Before final prompt/response writer work. |
| `vibe-kanban_for_graph.md` | Maybe later | Could inform workflow/project UX, not core planner. | After core roadmap if kanban-like UX is desired. |

Conclusion: next best step is to create `docs/plan/03_architecture_decision.md`. Optional files can wait unless the next focus is UX, agents, or prompt design.
 