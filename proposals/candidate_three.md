# Candidate 3 — Deterministic harness gates + locality-first route planning

## Phạm vi và nguyên tắc

Phương án này được thiết kế độc lập từ code production và benchmark hiện tại. Nó không dùng bộ phân loại từ khóa để quyết định tool. LLM vẫn là bộ não hiểu ý định và tạo tool call; harness chỉ cưỡng chế các bất biến vận hành: lượt đầu phải dùng tool, mutation phải replan/validate/repair/commit, và API không được báo `completed` khi chưa hoàn tất.

Không đổi hard constraint trong repair loop. Nếu không khả thi sau số lần giới hạn, lịch đã commit trước đó được giữ nguyên và API trả `infeasible` cùng nguyên nhân cụ thể.

## Chẩn đoán từ code hiện tại

1. `bind_tools(AGENT_TOOLS)` đang để `tool_choice=auto`; `_route_after_agent` kết thúc ngay nếu model trả text. Do đó ca Hội An có thể `tool_calls=0`, `committed=false` nhưng service vẫn ghi `completed`.
2. `UserRequest` chỉ biểu diễn tỉnh/thành (`region`), không có locality nhỏ hơn như Hội An/Sơn Trà. `GraphService.filter_places()` chỉ lọc `place["region"] == user.region`.
3. `_execute_tools()` chỉ replan một lần. Nếu report không `acceptable`, graph đi thẳng vào `_finalize_tools()` và lộ thông báo kỹ thuật `partial`.
4. Candidate được cắt theo recommendation score trước khi biết road matrix. Sau đó từng ngày lấy tuần tự từ một danh sách chung; chưa có phép gán candidate vào cụm ngày theo route cost.
5. `LangGraphAssistantService` suy trạng thái bằng `input_required ? ... : completed`, không dựa trên outcome thật.
6. `agent/graph.py` và legacy `services/llm_service.py` đều load `.env.example`; file mẫu không được là nguồn secret runtime.

## Thiết kế tổng thể

```text
Human prompt
  -> LLM + tool_choice=required (không có clarification ở toolset đầu)
  -> tool observation
  -> nếu read-only: LLM tổng hợp câu trả lời
  -> nếu mutation:
       apply all changes atomically
       -> replan attempt 0
       -> validate
       -> acceptable: commit
       -> not acceptable: deterministic repair attempt 1..2
       -> acceptable: commit
       -> vẫn lỗi: discard draft, giữ lịch cũ, outcome=infeasible
  -> API ánh xạ outcome trung thực
```

Locality là dữ liệu có cấu trúc do LLM điền vào tool (`location_focus="Hội An"`), không phải keyword router. Resolver đối chiếu locality với name/address/description trong graph, sau đó có thể mở rộng theo bán kính nếu `location_mode="nearby"`.

Planner tạo road matrix trên một seed pool đủ rộng rồi dùng route-aware allocator để vừa chọn vừa chia ứng viên vào các ngày. OR-Tools vẫn tối ưu thứ tự và time window trong từng ngày.

## Unified diff đề xuất

### 1. Không load secret từ `.env.example`

```diff
diff --git a/agent/graph.py b/agent/graph.py
@@
 load_dotenv()
-load_dotenv(".env.example", override=False)
```

```diff
diff --git a/services/llm_service.py b/services/llm_service.py
@@
 load_dotenv()
-load_dotenv(".env.example", override=False)
```

`.env.example` phải chỉ chứa placeholder, tuyệt đối không chứa key thật:

```diff
diff --git a/.env.example b/.env.example
@@
-GROQ_API_KEY=<real key>
+GROQ_API_KEY=
 GROQ_MODEL=openai/gpt-oss-20b
+AGENT_MAX_REPAIR_ATTEMPTS=2
+AGENT_REQUIRED_TOOL_RETRIES=2
```

Key từng xuất hiện trong Git phải revoke/rotate ngoài code.

### 2. Schema locality có cấu trúc

```diff
diff --git a/models/user_request.py b/models/user_request.py
@@
 BudgetLevel = Literal["economy", "standard", "premium"]
+LocationMode = Literal["strict", "nearby"]
@@ class UserRequest(BaseModel):
     region: RegionName = Field(...)
+    location_focus: str | None = Field(
+        default=None,
+        min_length=2,
+        max_length=120,
+        description="Locality inside region, e.g. Hội An or Sơn Trà.",
+    )
+    location_mode: LocationMode = Field(
+        default="strict",
+        description="strict keeps textual locality matches; nearby may expand by radius.",
+    )
+    max_locality_expansion_km: float = Field(default=8.0, gt=0, le=50)
+    min_locality_ratio: float = Field(default=0.9, ge=0, le=1)
```

```diff
diff --git a/agent/tools.py b/agent/tools.py
@@
-from models.user_request import (...)
+from models.user_request import (..., LocationMode)
@@ class UpdateTripInput(BaseModel):
     region: RegionName | None = None
+    location_focus: str | None = Field(default=None, min_length=2, max_length=120)
+    location_mode: LocationMode | None = None
+    max_locality_expansion_km: float | None = Field(default=None, gt=0, le=50)
@@ def _tool_update_trip_settings(self, args, state):
         if args.get("region") and args["region"] != old_region:
             values["required_place_ids"] = []
             values["excluded_place_ids"] = []
+            if "location_focus" not in args:
+                values["location_focus"] = None
```

Không cho model chỉnh `min_locality_ratio`; đây là quality gate của server.

### 3. Locality resolver dùng dữ liệu graph, không dùng routing keyword

```diff
diff --git a/utils/locality.py b/utils/locality.py
new file mode 100644
--- /dev/null
+++ b/utils/locality.py
@@
+from utils.distance import haversine
+from utils.place_matching import normalize_text
+
+
+def locality_text(place):
+    return normalize_text(" ".join(str(place.get(field) or "") for field in (
+        "name", "address", "description",
+    )))
+
+
+def direct_locality_match(place, focus):
+    needle = normalize_text(focus)
+    return bool(needle and needle in locality_text(place))
+
+
+def resolve_locality(places, focus, mode="strict", radius_km=8.0):
+    """Return (eligible places, direct ids). Empty direct matches stay empty.
+
+    The caller can report locality_not_found instead of silently falling back
+    to the whole province.
+    """
+    places = list(places)
+    if not focus:
+        return places, set()
+    direct = [place for place in places if direct_locality_match(place, focus)]
+    direct_ids = {place["id"] for place in direct}
+    if mode == "strict" or not direct:
+        return direct, direct_ids
+    eligible = []
+    for place in places:
+        if place["id"] in direct_ids or any(
+            haversine(place["lat"], place["lng"], anchor["lat"], anchor["lng"])
+            <= radius_km
+            for anchor in direct
+        ):
+            eligible.append(place)
+    return eligible, direct_ids
```

```diff
diff --git a/services/graph_service.py b/services/graph_service.py
@@
 from utils.place_matching import place_categories, place_types
+from utils.locality import resolve_locality
@@ def filter_places(self, user):
-        for place in self.nodes.values():
+        regional = [
+            place for place in self.nodes.values()
+            if place["region"] == user.region
+        ]
+        locality_places, _ = resolve_locality(
+            regional,
+            user.location_focus,
+            user.location_mode,
+            user.max_locality_expansion_km,
+        )
+        for place in locality_places:
@@
-            if place["region"] != user.region:
-                continue
             result.append(place)
```

Validator kiểm locality bằng attraction (meal không làm loãng tỷ lệ):

```diff
diff --git a/services/itinerary_validator.py b/services/itinerary_validator.py
@@
 from utils.place_matching import matches_category, place_categories, place_types
+from utils.locality import direct_locality_match
@@ def validate(itinerary, user):
         attraction_count = 0
+        locality_match_count = 0
@@
                 else:
                     attraction_count += 1
+                    if user.location_focus and direct_locality_match(place, user.location_focus):
+                        locality_match_count += 1
@@
+        locality_ratio = (
+            locality_match_count / attraction_count
+            if user.location_focus and attraction_count else
+            (1.0 if not user.location_focus else 0.0)
+        )
+        if user.location_focus and locality_ratio < user.min_locality_ratio:
+            quality_violations.append("locality_ratio_unmet")
@@
             "metrics": {
+                "location_focus": user.location_focus,
+                "locality_match_count": locality_match_count,
+                "locality_ratio": round(locality_ratio, 3),
```

### 4. Route-aware selection và multi-day allocation

```diff
diff --git a/services/route_aware_allocator.py b/services/route_aware_allocator.py
new file mode 100644
--- /dev/null
+++ b/services/route_aware_allocator.py
@@
+class RouteAwareAllocator:
+    """Choose and partition POIs using road time plus recommendation utility."""
+
+    def __init__(self, route_weight=1.0):
+        self.route_weight = float(route_weight)
+
+    @staticmethod
+    def _minutes(matrix, source_id, target_id):
+        forward = matrix["metrics"][(source_id, target_id)]["duration_minutes"]
+        backward = matrix["metrics"][(target_id, source_id)]["duration_minutes"]
+        return (float(forward) + float(backward)) / 2
+
+    def allocate(
+        self,
+        candidates,
+        route_matrix,
+        day_count,
+        pool_size_per_day,
+        required_by_day=None,
+    ):
+        required_by_day = required_by_day or {}
+        by_id = {place["id"]: place for place in candidates}
+        pools = {day: [] for day in range(day_count)}
+        assigned = set()
+        for day, ids in required_by_day.items():
+            for place_id in ids:
+                if place_id in by_id and place_id not in assigned:
+                    pools[day].append(place_id)
+                    assigned.add(place_id)
+
+        # Seed empty days with high-utility POIs far from existing seeds. This
+        # prevents all days from collapsing onto the same cluster.
+        ranked = sorted(candidates, key=lambda p: (
+            -float(p.get("query_priority", 0)),
+            -float(p.get("recommendation_score", 0)),
+            p["id"],
+        ))
+        for day in range(day_count):
+            if pools[day]:
+                continue
+            options = [p for p in ranked if p["id"] not in assigned]
+            if not options:
+                break
+            existing_seeds = [ids[0] for ids in pools.values() if ids]
+            seed = max(options, key=lambda p: (
+                min((self._minutes(route_matrix, p["id"], other)
+                     for other in existing_seeds), default=0),
+                float(p.get("recommendation_score", 0)),
+            ))
+            pools[day].append(seed["id"])
+            assigned.add(seed["id"])
+
+        score_values = [float(p.get("recommendation_score", 0)) for p in candidates]
+        lo, hi = min(score_values, default=0), max(score_values, default=1)
+        def utility(place):
+            score = float(place.get("recommendation_score", 0))
+            normalized = (score - lo) / max(hi - lo, 1e-9)
+            return normalized * 60 + float(place.get("query_priority", 0)) * 0.2
+
+        # Global best insertion means route cost affects both selection and day.
+        while True:
+            best = None
+            for place in candidates:
+                if place["id"] in assigned:
+                    continue
+                for day, ids in pools.items():
+                    if len(ids) >= pool_size_per_day:
+                        continue
+                    incremental = min(
+                        (self._minutes(route_matrix, place["id"], member) for member in ids),
+                        default=0,
+                    )
+                    objective = self.route_weight * incremental - utility(place)
+                    choice = (objective, place["id"], day)
+                    if best is None or choice < best[0]:
+                        best = (choice, place["id"], day)
+            if best is None:
+                break
+            _, place_id, day = best
+            pools[day].append(place_id)
+            assigned.add(place_id)
+        return {day: set(ids) for day, ids in pools.items()}
```

Nối allocator vào planner sau khi có matrix nhưng trước vòng build ngày:

```diff
diff --git a/services/itinerary_service.py b/services/itinerary_service.py
@@
 from services.route_optimizer import RouteOptimizer
+from services.route_aware_allocator import RouteAwareAllocator
@@ class ItineraryService:
-    def __init__(...):
+    def __init__(..., allocator=None):
         ...
+        self.allocator = allocator or RouteAwareAllocator()
@@ def _build_day(
         fill_idle_gaps=True,
+        allowed_candidate_ids=None,
     ):
@@
         eligible_remaining = [
             place for place in remaining
             if place["id"] not in reserved_place_ids
             or place["id"] in required_place_ids
         ]
+        if allowed_candidate_ids is not None:
+            eligible_remaining = [
+                place for place in eligible_remaining
+                if place["id"] in allowed_candidate_ids
+                or place["id"] in required_place_ids
+            ]
@@ gap filler candidates
-                    place for place in remaining
-                    if allowed_for_day(place)
+                    place for place in remaining
+                    if allowed_for_day(place)
+                    and (allowed_candidate_ids is None or place["id"] in allowed_candidate_ids)
@@ def build(
         optimization_policy=None,
+        repair_attempt=0,
     ):
@@ after route_matrix and required_by_day are created
+        route_weight = 1.0 + max(0, int(repair_attempt)) * 0.75
+        allocator = RouteAwareAllocator(route_weight=route_weight)
+        candidate_pools = allocator.allocate(
+            candidates,
+            route_matrix,
+            user.duration,
+            pool_size_per_day=max(user.max_places_per_day * 3, 6),
+            required_by_day=required_by_day,
+        )
@@ call _build_day
                     optimization_policy.get("fill_idle_gaps", True),
+                    candidate_pools.get(day_index, set()),
                 )
```

Hai chi tiết bắt buộc khi áp patch thật:

- `required_by_day` phải được tính và áp `required_place_days` trước khi gọi allocator (di chuyển block allocator xuống sau block override ngày).
- Seed pool trước OSRM nên rộng tối đa trong giới hạn `MAX_OSRM_COORDINATES`; không cắt còn đúng số chỗ cần đi. `repair_attempt=1/2` tăng route weight nhưng không tăng hard limit hay tự nới locality.

### 5. Repair loop giới hạn và outcome rõ ràng

```diff
diff --git a/agent/state.py b/agent/state.py
@@ class SoulVietAgentState(TypedDict, total=False):
+    turn_tool_call_count: int
+    required_tool_failures: int
+    repair_count: int
+    outcome: str | None
+    failure_report: dict | None
```

Tách helper replan để repair có thể tái sử dụng mà không tạo tool call giả:

```diff
diff --git a/agent/tools.py b/agent/tools.py
@@ class SoulVietToolExecutor:
+    def build_and_validate(self, state, repair_attempt=0):
+        request = UserRequest.model_validate(self._working_request(state))
+        constraints = self._working_constraints(state)
+        itinerary = self.itinerary.build(
+            request,
+            candidate_ids=constraints.get("allowed_place_ids"),
+            meal_preferences=constraints.get("meal_preferences", []),
+            required_place_days=constraints.get("required_place_days", {}),
+            meal_requests=constraints.get("meal_requests", []),
+            scoped_exclusions=constraints.get("scoped_exclusions", []),
+            day_policies=constraints.get("day_policies", []),
+            optimization_policy=constraints.get("optimization_policy", {}),
+            repair_attempt=repair_attempt,
+        )
+        report = self._validate_with_constraints(itinerary, request, constraints)
+        report["repair_attempt"] = repair_attempt
+        return request, constraints, itinerary, report
@@ def _tool_replan_itinerary(self, _args, state):
-        request = ...
-        ... duplicated build/validate ...
+        request, constraints, itinerary, report = self.build_and_validate(state, 0)
```

Trong graph, automatic workflow chạy bounded loop. Đây là control flow deterministic, không đọc keyword prompt:

```diff
diff --git a/agent/graph.py b/agent/graph.py
@@ class SoulVietAgentGraph:
     MAX_TOOL_CALLS = 16
+    MAX_REPAIR_ATTEMPTS = max(0, int(os.getenv("AGENT_MAX_REPAIR_ATTEMPTS", "2")))
+    REQUIRED_TOOL_RETRIES = max(0, int(os.getenv("AGENT_REQUIRED_TOOL_RETRIES", "2")))
@@ def _execute_tools(self, state):
         total_calls = state.get("tool_call_count", 0) + len(calls)
+        turn_calls = state.get("turn_tool_call_count", 0) + len(calls)
@@ automatic mutation workflow
             if "replan_itinerary" not in called_workflow:
                 observation, tool_updates = self.executor.execute(...)
                 ...
             report = local_state.get("validation_report") or {}
+            repair_count = 0
+            while not report.get("acceptable") and repair_count < self.MAX_REPAIR_ATTEMPTS:
+                repair_count += 1
+                request, constraints, itinerary, report = self.executor.build_and_validate(
+                    local_state, repair_attempt=repair_count
+                )
+                tool_updates = {
+                    "working_request": request.model_dump(mode="json"),
+                    "working_constraints": constraints,
+                    "working_itinerary": itinerary,
+                    "validation_report": report,
+                    "dirty": True,
+                    "committed": False,
+                    "repair_count": repair_count,
+                }
+                local_state.update(tool_updates)
+                updates.update(tool_updates)
+                automatic.append({
+                    "ok": report.get("acceptable", False),
+                    "tool": "repair_itinerary",
+                    "summary": f"Repair attempt {repair_count}: {report.get('status')}",
+                    "data": report,
+                })
+                tool_names.append("repair_itinerary")
             if report.get("acceptable"):
                 ... commit ...
+                updates["outcome"] = "committed"
+            else:
+                failure_report = report
+                updates.update({
+                    "working_request": None,
+                    "working_itinerary": None,
+                    "working_constraints": {},
+                    "validation_report": report,
+                    "failure_report": failure_report,
+                    "dirty": False,
+                    "committed": False,
+                    "outcome": "infeasible",
+                })
+                local_state.update(updates)
@@ updates.update
             "tool_call_count": total_calls,
+            "turn_tool_call_count": turn_calls,
```

Không gọi repair cho read-only. Không commit nếu `acceptable=false`. `current_request/current_itinerary` chỉ đổi trong `_tool_commit_itinerary`, nên failure luôn giữ lịch cũ.

Finalizer không lộ `partial` chung chung:

```diff
diff --git a/agent/graph.py b/agent/graph.py
@@ def _finalize_tools(state):
         if state.get("committed"):
-            return {"messages": [AIMessage(content="Đã cập nhật...")]}
+            return {"messages": [AIMessage(content="Đã cập nhật và kiểm tra hành trình thành công.")], "outcome": "committed"}
-        if state.get("dirty"):
-            ... partial message ...
+        if state.get("outcome") == "infeasible":
+            report = state.get("failure_report") or state.get("validation_report") or {}
+            violations = [
+                *report.get("hard_violations", []),
+                *report.get("quality_violations", []),
+            ]
+            detail = ", ".join(dict.fromkeys(violations)) or "không tìm được lịch khả thi"
+            return {"messages": [AIMessage(content=(
+                "Mình chưa thể tạo lịch thỏa toàn bộ ràng buộc: " + detail
+                + ". Lịch hiện tại được giữ nguyên."
+            ))], "outcome": "infeasible"}
@@
-        return {"messages": [AIMessage(content=(summaries ...))]}
+        return {"messages": [AIMessage(content=(summaries ...))], "outcome": "completed"}
```

### 6. Lượt đầu bắt buộc tool, không keyword routing

Toolset đầu không có `ask_user_clarification`, vì prompt đủ dữ liệu như “2 ngày ở Hội An” không được phép né hành động bằng cách hỏi ID. Sau một read/action tool, model có thể dùng clarification ở lượt kế nếu thực sự thiếu quyết định bắt buộc.

```diff
diff --git a/agent/graph.py b/agent/graph.py
@@ class SoulVietAgentGraph:
+    FIRST_TURN_TOOLS = [
+        tool for tool in AGENT_TOOLS
+        if tool.name != "ask_user_clarification"
+    ]
@@ def __init__(...):
         self.model_with_tools = (
             self.model.bind_tools(AGENT_TOOLS) if self.model else None
         )
+        self.model_required_tool = (
+            self.model.bind_tools(self.FIRST_TURN_TOOLS, tool_choice="required")
+            if self.model else None
+        )
@@ def _call_agent(self, state):
-        response = self.model_with_tools.invoke([
+        decision_model = (
+            self.model_required_tool
+            if state.get("turn_tool_call_count", 0) == 0
+            else self.model_with_tools
+        )
+        response = decision_model.invoke([
@@ def _route_after_agent(state):
         if getattr(message, "tool_calls", None):
             return "tools"
+        if state.get("turn_tool_call_count", 0) == 0:
+            if state.get("required_tool_failures", 0) < self.REQUIRED_TOOL_RETRIES:
+                return "required_tool_retry"
+            return "required_tool_error"
         return END
+
+    @staticmethod
+    def _record_required_tool_failure(state):
+        return {"required_tool_failures": state.get("required_tool_failures", 0) + 1}
+
+    @staticmethod
+    def _required_tool_error(_state):
+        return {
+            "messages": [AIMessage(content="Model không tạo được tool call bắt buộc; lịch được giữ nguyên.")],
+            "outcome": "tool_error",
+            "error": {"type": "required_tool_call_missing"},
+        }
@@ def _build_graph(self):
+        builder.add_node("required_tool_retry", self._record_required_tool_failure)
+        builder.add_node("required_tool_error", self._required_tool_error)
         builder.add_conditional_edges(
             "agent", self._route_after_agent,
+            {
+                "tools": "tools",
+                "required_tool_retry": "required_tool_retry",
+                "required_tool_error": "required_tool_error",
+                END: END,
+            },
         )
+        builder.add_edge("required_tool_retry", "agent")
+        builder.add_edge("required_tool_error", END)
@@ def invoke(... initial state):
+                "turn_tool_call_count": 0,
+                "required_tool_failures": 0,
+                "repair_count": 0,
+                "outcome": None,
+                "failure_report": None,
```

Lưu ý khi code thật: `_route_after_agent` hiện là `@staticmethod`; đổi thành instance method để đọc `REQUIRED_TOOL_RETRIES`. Mapping conditional phải dùng đúng API LangGraph đang pin. Test compile graph sẽ bắt lỗi này.

### 7. Trạng thái API trung thực

```diff
diff --git a/services/langgraph_assistant_service.py b/services/langgraph_assistant_service.py
@@ def customize(self, assistant_request):
         requires_input = "ask_user_clarification" in state.get("last_tool_names", [])
+        outcome = state.get("outcome")
+        if requires_input:
+            outcome = "input_required"
+        elif state.get("error") and outcome not in {"infeasible"}:
+            outcome = "tool_error"
+        elif state.get("committed"):
+            outcome = "committed"
+        elif not outcome:
+            outcome = "completed" if state.get("turn_tool_call_count", 0) else "tool_error"
@@ response
-            "agent": {
-                "status": "input_required" if requires_input else "completed",
+            "agent": {
+                "status": outcome,
                 "requires_input": requires_input,
                 "iterations": state.get("iteration_count", 0),
                 "tool_calls": state.get("tool_call_count", 0),
+                "turn_tool_calls": state.get("turn_tool_call_count", 0),
+                "repair_attempts": state.get("repair_count", 0),
```

Ý nghĩa terminal state:

- `committed`: mutation đã validate acceptable và commit.
- `completed`: read-only/memory request đã dùng tool và trả lời xong.
- `input_required`: thiếu dữ liệu thật sự bắt buộc.
- `infeasible`: đã repair đủ số lần, hard constraints vẫn không thỏa; lịch cũ giữ nguyên.
- `tool_error`: model vi phạm tool protocol hoặc executor lỗi.
- `provider_error`/`unavailable`: lỗi Groq/config như hiện tại nhưng đổi tên nhất quán.

### 8. System prompt

```diff
diff --git a/agent/prompts/system.md b/agent/prompts/system.md
@@
+- Khi người dùng nêu một locality như Hội An, Sơn Trà hoặc phố cổ Huế,
+  hãy điền trip_settings.location_focus và tự lập lịch từ dữ liệu graph.
+  Không hỏi place ID hoặc bắt người dùng liệt kê địa điểm.
+- Dùng location_mode=strict khi người dùng nói chỉ/tập trung tại locality;
+  dùng nearby khi họ nói quanh/gần locality và cho phép mở rộng.
+- Validation và repair do harness điều phối. Không tuyên bố đã cập nhật nếu
+  outcome chưa phải committed; không dùng từ trạng thái kỹ thuật `partial`
+  làm câu trả lời cho người dùng.
```

## Test cần thêm/sửa

### `tests/test_locality.py`

```python
from utils.locality import direct_locality_match, resolve_locality


def test_accent_insensitive_direct_locality_match():
    place = {"id": "1", "name": "Chùa Cầu", "address": "Hội An, Quảng Nam", "description": "", "lat": 15.88, "lng": 108.33}
    assert direct_locality_match(place, "hoi an")


def test_strict_locality_never_silently_falls_back():
    places = [{"id": "1", "name": "Tam Kỳ", "address": "Quảng Nam", "description": "", "lat": 15.5, "lng": 108.5}]
    eligible, direct = resolve_locality(places, "Hội An", "strict", 8)
    assert eligible == []
    assert direct == set()
```

### `tests/test_agent_graph.py`

Sửa mock để nhận kwargs:

```python
class ScriptedModel:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []
        self.bind_calls = []

    def bind_tools(self, tools, **kwargs):
        self.bind_calls.append(([tool.name for tool in tools], kwargs))
        return self
```

Thêm các test:

```python
def test_first_decision_uses_required_tool_choice(tmp_path):
    model = ScriptedModel([AIMessage(content="", tool_calls=[{
        "name": "get_trip_state", "args": {}, "id": "c1", "type": "tool_call",
    }]), AIMessage(content="Đã đọc lịch.")])
    agent = SoulVietAgentGraph(memory=AgentMemory(tmp_path), model=model)
    agent.invoke("u", "t", "Xem lịch", request_data(), [])
    assert any(kwargs.get("tool_choice") == "required" for _, kwargs in model.bind_calls)
    first_tools = next(tools for tools, kwargs in model.bind_calls if kwargs.get("tool_choice") == "required")
    assert "ask_user_clarification" not in first_tools


def test_missing_required_tool_call_retries_then_tool_error(tmp_path):
    model = ScriptedModel([AIMessage(content="no tool")] * 3)
    agent = SoulVietAgentGraph(memory=AgentMemory(tmp_path), model=model)
    state = agent.invoke("u", "t", "Lập lịch Hội An", request_data(), [])
    assert state["outcome"] == "tool_error"
    assert state["current_itinerary"] == []


def test_partial_runs_bounded_repair_and_never_commits_invalid(tmp_path, monkeypatch):
    # Script one mutation. Stub build_and_validate: partial, partial, success.
    # Assert repair_count == 2, committed is True, last names contain two repairs.
    ...


def test_exhausted_repair_keeps_current_itinerary(tmp_path, monkeypatch):
    # Stub all reports unacceptable.
    # Assert outcome=infeasible, committed=False, dirty=False and original itinerary unchanged.
    ...
```

### `tests/test_route_aware_allocator.py`

```python
def test_nearby_places_are_grouped_in_same_day():
    # A-B = 5 min, C-D = 5 min, cross-cluster = 90 min.
    # Assert each resulting pool is {A,B} or {C,D}.
    ...


def test_required_day_anchor_is_never_moved():
    # required_by_day={1: {"C"}}
    # Assert C belongs to day index 1 only.
    ...


def test_route_cost_can_beat_small_relevance_difference():
    # Two near candidates with scores 0.80/0.79 vs far score 0.81.
    # Pool capacity forces allocator to choose compact pair.
    ...
```

### `tests/test_itinerary_validator.py`

```python
def test_validator_rejects_low_locality_purity():
    # Request strict Hội An, itinerary has one Hội An + two Tam Kỳ attractions.
    # Assert acceptable=False, locality_ratio_unmet and ratio=1/3.
    ...
```

### `tests/test_langgraph_assistant_service.py`

```python
def test_uncommitted_mutation_is_not_reported_completed():
    # Fake state outcome=infeasible, committed=False.
    # Assert agent.status == "infeasible".
    ...


def test_read_only_with_tool_is_completed():
    # Fake state outcome=completed, turn_tool_call_count=1.
    # Assert completed but committed=False.
    ...
```

### Benchmark assertions

Mở rộng evaluator để bắt protocol và repair:

```diff
diff --git a/scripts/benchmark_agent_quality.py b/scripts/benchmark_agent_quality.py
@@ def evaluate_case(...):
+    if expected.get("must_use_tool", True):
+        _record(failures, response.get("agent", {}).get("turn_tool_calls", 0) > 0,
+                "agent did not use a tool in this turn")
+    if expected.get("committed"):
+        _record(failures, response.get("agent", {}).get("status") == "committed",
+                "mutation terminal status is not committed")
```

Các ca locality trong manifest thêm:

```json
{
  "must_use_tool": true,
  "committed": true,
  "forbidden_answer_substrings": ["place id", "địa điểm cụ thể", "partial", "bản nháp"]
}
```

## Rủi ro và cách giảm thiểu

1. **Groq/model không hỗ trợ `tool_choice="required"` đúng chuẩn.** Test một request nhỏ lúc startup hoặc integration test. Nếu provider trả 400, không fallback về keyword router; trả `provider_error` rõ ràng hoặc dùng model Groq có hỗ trợ tools.
2. **Locality text không tồn tại trong dataset.** Resolver trả rỗng và report `locality_not_found`, không âm thầm mở rộng cả tỉnh. Sau này bổ sung bảng locality chuẩn hóa offline, không hardcode routing intent.
3. **OSRM coordinate limit.** Seed pool phải giữ dưới `MAX_OSRM_COORDINATES`; meals được reserve như hiện tại. Có thể dùng haversine prefilter trước OSRM nhưng kết quả cuối vẫn chấm bằng road matrix.
4. **Allocator greedy không đạt global optimum.** Nó là bước phân cụm/chọn trước OR-Tools, có deterministic tie-break. Benchmark distance before/after quyết định có cần nâng lên k-medoids/Team Orienteering hay không.
5. **Repair tốn thời gian.** Chỉ chạy khi report không acceptable, tối đa 2 lần; log duration từng attempt. Không gọi LLM thêm trong repair.
6. **Checkpoint giữ state lượt trước.** Các field `turn_tool_call_count`, `repair_count`, `outcome`, `failure_report` phải reset trong payload `invoke()` mỗi lượt; chỉ `messages` dùng reducer cộng dồn.
7. **Reorder-only.** Toàn bộ current attraction IDs phải vừa là `allowed_place_ids` vừa required; allocator phải đặt mọi required ID vào pool. Nếu thật sự infeasible do giờ mở cửa, trả `infeasible`, không bỏ lén địa điểm.

## Lệnh kiểm chứng

```powershell
.\myenv\Scripts\python.exe -m pytest tests/test_locality.py tests/test_route_aware_allocator.py tests/test_agent_graph.py tests/test_agent_tools.py tests/test_itinerary_validator.py tests/test_langgraph_assistant_service.py -q
.\myenv\Scripts\python.exe -m pytest -q
.\myenv\Scripts\python.exe -m scripts.benchmark_recommendation
.\myenv\Scripts\python.exe -m uvicorn app:app --reload
.\myenv\Scripts\python.exe -m scripts.benchmark_agent_quality --output benchmark-results/agent-quality.json
```

Quality gate đề xuất:

- Unit/integration test: 100% xanh.
- 60 prompt benchmark: mọi mutation có `turn_tool_calls > 0`; không status `completed` nếu `committed=false`.
- Hai ca Hội An: commit, không clarification, locality ratio >= 0.9.
- Mutation khả thi: không xuất chuỗi `partial`/`bản nháp chưa commit`.
- Reorder-only: tập attraction không đổi và total distance mới <= baseline.
- Compound constraints: không trùng, không vi phạm exclusion, đúng ngày/meal slot.
- Repair attempts <= 2; infeasible giữ nguyên itinerary đầu vào.

## Thứ tự triển khai an toàn

1. Secret/config và terminal status.
2. Required-tool gate cùng test mock/provider.
3. Locality schema/resolver/filter/validator.
4. Repair loop bounded, giữ nguyên lịch cũ khi fail.
5. Route-aware allocator và benchmark distance.
6. Chạy toàn bộ deterministic suite rồi mới chạy Groq benchmark để tiết kiệm quota.

