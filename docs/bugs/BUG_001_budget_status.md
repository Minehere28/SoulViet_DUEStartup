# Bug Report: BUG_001_budget_status

## 1. Description
The integration test `test_full_pipeline_success` in `tests/test_pipeline.py` fails because the `budget_status` is returned as `"under_budget_warning"` instead of the expected `"good_value"`.

## 2. Root Cause
The root cause is a combination of restricted mock data and the `depth_limit` of the `GraphRetriever`.

- **File:** `src/planning/day_planner.py`
- **Lines:** 77-80
- **Logic:**
  ```python
  elif draft.budget_utilization < 0.5:
      draft.budget_status = "under_budget_warning"
  ```
- **Trace Analysis:**
  1. **Mock Candidates:** The test uses a 2-day duration with 4 slots per day, requiring 8 items.
  2. **Retrieval Depth:** `GraphRetriever.beam_search` uses a default `depth_limit` of 2.
  3. **Reachability:**
     - Seed: `P001` (Price: 50k)
     - Depth 1: `P002` (Price: 40k)
     - Depth 2: `P005` (Price: 60k)
     - `P003` is at Depth 3 (reachable from `P005`), so it is **not retrieved**.
     - `P004` is disconnected, so it is **not retrieved**.
  4. **Total Cost:** Only 3 candidates are retrieved. `total_cost` = 50k + 40k + 60k = **150,000**.
  5. **Utilization:** `total_budget` is **500,000**. `utilization` = 150,000 / 500,000 = **0.3**.
  6. **Outcome:** Since 0.3 < 0.5, the engine correctly assigns `"under_budget_warning"`.

## 3. Wrong Value vs Expected Value
- **Actual Value:** `"under_budget_warning"`
- **Expected Value:** `"good_value"`
- **Actual Utilization:** 0.3
- **Required Utilization for Pass:** >= 0.5

## 4. Recommended Fix
The fix should be applied to the **test mock data and configuration**, not the source code:
1. **Increase Connectivity:** Modify `self.edges` in `tests/test_pipeline.py` to ensure all 5 mock places are reachable within `depth_limit=2`. For example, connect `P001` directly to more nodes or decrease the depth of `P003`.
2. **Adjust Budget/Prices:** Set the `total_budget` in the test to a value that results in >0.5 utilization given the available mock items (e.g., set budget to 250,000 if total cost is 150,000).
3. **Seed More IDs:** Pass more than one seed ID to `beam_search` in the test to retrieve a wider pool of candidates immediately.
