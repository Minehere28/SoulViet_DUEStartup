# SoulViet Restructuring Implementation Backlog

This backlog defines the granular tasks required to restructure the SoulViet backend into the deterministic engine architecture.

## Task Dependencies & Order
Tasks are ordered to build the foundation (Models/Core) first, followed by the pipeline layers (Retrieval -> Scoring -> Planning -> Validation), and finally the API orchestration and cleanup.

---

### Phase 1: Models & Request Validation

**Task ID:** T1.1
**Goal:** Define core data contracts for User Request and Normalized Constraints.
**Files to create:**
- `src/models/user_request.py`
**Files to modify:** None
**Dependencies:** None
**Acceptance Criteria:**
- `UserRequest` class includes all fields from Section 17 of Design Doc.
- `NormalizedConstraints` class includes all fields from Section 17 of Design Doc.
- Classes use type hints for all attributes.

**Task ID:** T1.2
**Goal:** Implement the Request Validator service.
**Files to create:**
- `src/validation/request_validator.py`
**Files to modify:** None
**Dependencies:** T1.1
**Acceptance Criteria:**
- Implements checks for numeric duration (1-7 days), numeric budget (>0), and supported vibes.
- Returns `ValidationResult` with structured errors if constraints are violated.

---

### Phase 2: Data & Graph Infrastructure

**Task ID:** T2.1
**Goal:** Define the Place model and Evidence schema.
**Files to create:**
- `src/models/place.py`
- `src/models/evidence.py`
**Files to modify:** None
**Dependencies:** T1.1
**Acceptance Criteria:**
- `CandidatePlace` includes fields for ID, Name, coordinates, price, ratings, and image.
- `Evidence` model supports tracing source fields (reviews, description).

**Task ID:** T2.2
**Goal:** Implement the Graph Store for artifact consumption.
**Files to create:**
- `src/graph/graph_store.py`
**Files to modify:** None
**Dependencies:** T2.1
**Acceptance Criteria:**
- Loads `graph.pt` from the data directory.
- Provides thread-safe read access to nodes and edges.
- Implements `get_place(id)` and `get_all_places()`.

**Task ID:** T2.3
**Goal:** Implement Field Normalizers.
**Files to create:**
- `src/normalization/place_normalizer.py`
- `src/normalization/price_normalizer.py`
**Files to modify:** None
**Dependencies:** T2.2
**Acceptance Criteria:**
- Coerces numeric fields (Lat/Lng/Rating) safely.
- Normalizes price ranges into `price_min`, `price_max`, and `price_category`.

---

### Phase 3: Retrieval & Graph Traversal

**Task ID:** T3.1
**Goal:** Implement Bounded Beam Search Graph Traversal.
**Files to create:**
- `src/graph/graph_retriever.py`
**Files to modify:** None
**Dependencies:** T2.2, T2.3
**Acceptance Criteria:**
- Implements Beam Search with `depth_limit` and `beam_width`.
- Computes `expansion_score` for edges.
- Returns `RankedGraphPath` with deterministic ordering.

**Task ID:** T3.2
**Goal:** Implement Candidate Generation and Hard Filtering.
**Files to create:**
- `src/retrieval/candidate_generator.py`
- `src/retrieval/hard_filter.py`
**Files to modify:** None
**Dependencies:** T3.1
**Acceptance Criteria:**
- `CandidateGenerator` maps graph nodes to `CandidatePlace` records.
- `HardFilter` removes candidates based on blacklist and mandatory constraints.
- Returns `accepted_candidates` and `rejected_candidates` with reasons.

---

### Phase 4: Scoring & Utility Optimization

**Task ID:** T4.1
**Goal:** Implement Place Scorer with Score Breakdown.
**Files to create:**
- `src/models/score_breakdown.py`
- `src/scoring/place_scorer.py`
**Files to modify:** None
**Dependencies:** T3.2
**Acceptance Criteria:**
- Computes `total_score` based on formula in Section 9 of Design Doc.
- Returns detailed `ScoreBreakdown` (style, rating, price, etc.).
- Budget is treated as a soft signal only.

**Task ID:** T4.2
**Goal:** Implement Reranker and Utility Optimizer.
**Files to create:**
- `src/scoring/reranker.py`
- `src/scoring/utility_optimizer.py`
**Files to modify:** None
**Dependencies:** T4.1
**Acceptance Criteria:**
- `Reranker` ensures type and geographic diversity.
- `UtilityOptimizer` computes marginal utility per cost for ranking.
- Tie-breaking uses deterministic rules (ID/Name).

---

### Phase 5: Planning & Routing

**Task ID:** T5.1
**Goal:** Implement Day and Slot Planning logic.
**Files to create:**
- `src/planning/day_planner.py`
- `src/planning/slot_assigner.py`
**Files to modify:** None
**Dependencies:** T4.2
**Acceptance Criteria:**
- Assigns ranked candidates into Morning/Lunch/Afternoon/Evening slots.
- Enforces structural rules (no duplicates within day, slot compatibility).
- Planner does NOT mutate state; returns a `DraftItinerary`.

**Task ID:** T5.2
**Goal:** Implement Route Optimization and Draft Freezing.
**Files to create:**
- `src/planning/route_optimizer.py`
- `src/models/itinerary.py`
**Files to modify:** None
**Dependencies:** T5.1
**Acceptance Criteria:**
- Applies Haversine distance-based reordering within days.
- Produces `FrozenDraftItinerary` which is immutable after creation.

---

### Phase 6: Validation Layer

**Task ID:** T6.1
**Goal:** Implement Budget and Constraint Validators.
**Files to create:**
- `src/validation/budget_validator.py`
- `src/validation/itinerary_validator.py`
**Files to modify:** None
**Dependencies:** T5.2
**Acceptance Criteria:**
- `BudgetValidator` enforces the hard `total_budget` ceiling.
- `ItineraryValidator` checks for duplicates, minimum items, and route feasibility.
- Returns `ValidationResult` (pass/fail) with structured error/warning lists.

---

### Phase 7: State, LLM & Orchestration

**Task ID:** T7.1
**Goal:** Implement Itinerary State Store and Acceptance logic.
**Files to create:**
- `src/state/itinerary_state_store.py`
**Files to modify:** None
**Dependencies:** T6.1
**Acceptance Criteria:**
- Persists only accepted itineraries (post-validation).
- Updates `used_ids` only after a successful validation pass.
- Supports versioning for future chat refinements.

**Task ID:** T7.2
**Goal:** Implement Grounded LLM Response Writer.
**Files to create:**
- `src/llm/llm_client.py`
- `src/llm/response_writer.py`
**Files to modify:** None
**Dependencies:** T7.1
**Acceptance Criteria:**
- `ResponseWriter` receives only validated JSON data.
- Generates `ai_text` without adding or changing itinerary items.

**Task ID:** T7.3
**Goal:** Implement the Core Engine Orchestrator.
**Files to create:**
- `src/planning/itinerary_engine.py`
**Files to modify:** None
**Dependencies:** T7.2
**Acceptance Criteria:**
- Implements the `build_itinerary` pseudocode from Section 18 of Design Doc.
- Manages the repair/fallback loop (up to 3 retries).

---

### Phase 8: API Integration

**Task ID:** T8.1
**Goal:** Create FastAPI Routes for Planning.
**Files to create:**
- `src/api/itinerary_routes.py`
- `src/api/health_routes.py`
**Files to modify:** None
**Dependencies:** T7.3
**Acceptance Criteria:**
- `POST /plan` endpoint validates request and invokes `itinerary_engine`.
- Returns structured `PlanResponse` from Section 17 of Design Doc.

**Task ID:** T8.2
**Goal:** Refactor app entry point.
**Files to create:** None
**Files to modify:**
- `app.py`
**Dependencies:** T8.1
**Acceptance Criteria:**
- Includes routers from `src/api/`.
- Removes legacy routing logic.

---

### Phase 9: Cleanup & Verification

**Task ID:** T9.1
**Goal:** Remove obsolete code and verify preservation.
**Files to create:** None
**Files to modify:** None
**Dependencies:** T8.2
**Acceptance Criteria:**
- `services/` and `views/` directories are deleted.
- `docs/` and `data/` directories remain unchanged.
- `src/` contains all runtime logic.
