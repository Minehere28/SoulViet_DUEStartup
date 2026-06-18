# SoulViet Engine - Current Status Report

## 1. Source Code Inventory (`src/`)

| File Path | Purpose | Status |
| :--- | :--- | :--- |
| `src/models/user_request.py` | Typed contracts for UserRequest and NormalizedConstraints | Complete |
| `src/models/validation_result.py` | Contract for validation outcomes and repair suggestions | Complete |
| `src/models/place.py` | Data model for CandidatePlace with UI and graph fields | Complete |
| `src/models/evidence.py` | Data model for tracing recommendation sources | Complete |
| `src/models/graph_path.py` | Contracts for RankedGraphPath and RankedSubgraph | Complete |
| `src/models/score_breakdown.py` | Granular scoring metrics for explainability | Complete |
| `src/models/itinerary.py` | Contracts for Draft and Frozen itinerary items | Complete |
| `src/validation/request_validator.py` | Business rule validation for duration, budget, and vibe | Complete |
| `src/graph/graph_store.py` | Thread-safe singleton for `graph.pt` artifact access | Complete |
| `src/graph/graph_retriever.py` | Bounded Beam Search graph traversal engine | Complete |
| `src/normalization/place_normalizer.py` | Type coercion and list normalization for place data | Complete |
| `src/normalization/price_normalizer.py` | Price parsing and category normalization | Complete |
| `src/retrieval/candidate_generator.py` | Maps graph nodes to CandidatePlace objects | Complete |
| `src/retrieval/hard_filter.py` | Deterministic rejection of invalid candidates | Complete |
| `src/scoring/place_scorer.py` | Weighted scoring engine for candidate ranking | Complete |
| `src/scoring/reranker.py` | Diversity-aware candidate reordering | Complete |
| `src/scoring/utility_optimizer.py` | Marginal utility per cost optimization | Complete |
| `src/planning/day_planner.py` | Slot assignment and day assembly logic | **Partial** (Hardcoded 90m duration) |
| `src/planning/slot_assigner.py` | Rule-based suitability check for time slots | Complete |
| `src/planning/route_optimizer.py` | Haversine distance-based reordering and draft freezing | Complete |

## 2. Test Suite Status (`tests/`)

| Test File | Passed | Failed | Notes |
| :--- | :--- | :--- | :--- |
| `tests/test_pipeline.py` | 3 | 1 | `test_full_pipeline_success` fails due to mock graph reachability (BUG_001) |

- **test_over_budget_status**: PASS
- **test_hard_filter_blacklist**: PASS
- **test_request_validation_errors**: PASS
- **test_full_pipeline_success**: **FAIL** (Returns `under_budget_warning` instead of `good_value`)

## 3. Known Bugs (`docs/bugs/`)

- **BUG_001_budget_status.md**: Integration test failure caused by sparse mock graph connectivity and retrieval depth limits.

## 4. Execution Summary

### What is Fully Working (End-to-End Logic)
- **Request Validation**: Safe parsing and rejection of invalid user inputs.
- **Graph Retrieval**: Bounded beam search correctly traverses nodes and edges.
- **Candidate Processing**: Normalization, enrichment, and hard filtering are operational.
- **Scoring & Ranking**: Candidates are scored, diversified, and optimized for utility.
- **Draft Freezing**: The system produces immutable `FrozenDraftItinerary` objects.

### What is Partially Implemented
- **Day Planning**: Slot assignment is working, but item duration is currently a placeholder (90m).
- **Graph Metadata**: The graph retriever uses a simplified expansion score; richer style/vibe matching is pending.

### What is Missing (Not Yet Built)
- **Phase 6**: Budget and Itinerary Validators (Final hard authority).
- **Phase 7**: State Store, Orchestrator, and LLM Response Writer.
- **Phase 8/9**: API Layer, `app.py` refactor, and legacy cleanup.

### What is Broken
- **Integration Test Mock**: The pipeline test fails to retrieve enough items to satisfy the "good value" utilization threshold because the mock graph edges are incomplete relative to the search depth.
