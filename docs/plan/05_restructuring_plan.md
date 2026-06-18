# Revised Restructuring Plan - SoulViet

## 1. Objective
Restructure the SoulViet repository from its current flat/service-based layout to the layered architecture defined in `docs/plan/04_deterministic_itinerary_engine_design.md`. This migration focuses on the backend runtime code while preserving critical data and documentation.

## 2. Implementation Specification
- **Primary Authority:** `docs/plan/04_deterministic_itinerary_engine_design.md`
- **Reference Only (Ignore for Implementation):**
  - `docs/plan/01_project_code_review.md`
  - `docs/plan/02_reference_learning_notes.md`
  - `docs/plan/03_architecture_decision.md`

## 3. Preservation Rules
The following directories and their contents MUST be preserved permanently and must not be deleted, renamed, moved, or modified during the restructuring:
- `docs/` (including all plans and status reports)
- `data/` (and its subdirectories once created)
- `dataset/` (source CSV data)

## 4. Migration Scope
The migration applies **ONLY** to:
- `services/`
- `views/`
- `app.py`

## 5. Target Structure
```text
soulviet/
├── app.py (refactored entry point)
├── main.py (new entry point if needed)
├── requirements.txt
├── dataset/ (preserved)
│   └── SoulViet_Dataset.csv
├── data/ (preserved/managed)
│   ├── raw/
│   ├── processed/
│   └── artifacts/
│       └── graph.pt
├── docs/ (preserved)
│   ├── plan/
│   ├── repo_exp/
│   └── status/
├── src/
│   ├── api/ (from views/ and app.py routing)
│   ├── models/ (from models/ and design spec)
│   ├── normalization/ (new logic from services/)
│   ├── graph/ (from services/graph_service.py)
│   ├── retrieval/ (from services/filter_service.py)
│   ├── scoring/ (from services/scoring_service.py)
│   ├── planning/ (from services/planner_service.py)
│   ├── validation/ (new validation logic)
│   ├── state/ (new state management)
│   ├── chat/ (new refinement logic)
│   ├── llm/ (from services/llm_service.py)
│   └── utils/ (from utils/)
├── frontend/ (from index.html split)
└── scripts/ (preserved/refactored)
```

## 6. Migration Phases

### Phase 1: Environment & Models
- Initialize `src/` directory structure.
- Migrate and expand `models/` into `src/models/` following the data contracts in Section 17 of the design doc.
- Implement `src/validation/request_validator.py`.

### Phase 2: Data & Graph Layer
- Implement `src/graph/graph_store.py` to load `graph.pt`.
- Implement `src/normalization/` for place, price, type, and vibe normalization.
- Implement `src/graph/graph_retriever.py` for bounded beam search.

### Phase 3: Retrieval & Filter Layer
- Implement `src/retrieval/candidate_generator.py`.
- Implement `src/retrieval/hard_filter.py`.

### Phase 4: Scoring & Utility Layer
- Implement `src/scoring/place_scorer.py` with explainable breakdowns.
- Implement `src/scoring/reranker.py` and `src/scoring/utility_optimizer.py`.

### Phase 5: Planning Layer
- Implement `src/planning/day_planner.py` and `src/planning/slot_assigner.py`.
- Implement `src/planning/route_optimizer.py` (Haversine-based).

### Phase 6: Validation Layer
- Implement `src/validation/itinerary_validator.py` as the hard authority for budget, time, and constraints.
- Implement `src/validation/budget_validator.py`.

### Phase 7: State & LLM Layer
- Implement `src/state/itinerary_state_store.py`.
- Implement `src/llm/response_writer.py` (Grounded LLM writer).

### Phase 8: API Layer & Integration
- Implement `src/api/itinerary_routes.py` (FastAPI).
- Refactor `app.py` to use the new `src/` modules.

### Phase 9: Cleanup
- **DELETE ONLY:**
  - `services/`
  - `views/`
- **VERIFY PRESERVATION:**
  - `docs/` and `data/` (or `dataset/`) must remain unchanged.

## 7. Confirmation
I confirm that the implementation will follow **ONLY** the architecture and logic defined in `docs/plan/04_deterministic_itinerary_engine_design.md`. All other materials are for reference only. The repository preservation rules will be strictly enforced.
