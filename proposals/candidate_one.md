# Phương án 1 — Harness cưỡng chế giao thức, locality deterministic và planner route-aware

## 1. Chẩn đoán từ code production hiện tại

1. `agent/graph.py::_route_after_agent` kết thúc ngay khi model trả text và không có `tool_calls`. `bind_tools()` hiện dùng chế độ mặc định (`auto`), do đó prompt “Hội An” có thể kết thúc với `tool_calls=0` mà service vẫn gắn `status=completed`.
2. `UserRequest` chỉ có `region`; “Hội An”, “Sơn Trà” không có chỗ biểu diễn trong request. `GraphService.filter_places()` chỉ lọc theo tỉnh/thành, nên planner không thể bảo đảm locality purity.
3. `_execute_tools()` chỉ tự `replan` đúng một lần. Nếu `validation_report.acceptable == false`, graph đi thẳng tới `_finalize_tools` và lộ thông báo kỹ thuật `partial`.
4. `ItineraryService.build()` cắt candidate theo recommendation score trước khi tạo OSRM matrix; sau đó `_build_day()` lần lượt tiêu thụ cùng danh sách. Route cost chỉ tối ưu thứ tự trong một ngày, chưa tham gia đủ sớm vào chọn điểm và chia điểm giữa các ngày.
5. `LangGraphAssistantService` trả `completed` cho mọi trường hợp không clarification, kể cả mutation không commit.
6. `agent/graph.py` và `services/llm_service.py` cùng load `.env.example`; file mẫu hiện còn hai biến API key. Runtime không được đọc file mẫu và file mẫu không được chứa secret.

Nguyên tắc của phương án này: LLM vẫn quyết định tool từ semantic prompt; harness không phân loại bằng keyword. Harness chỉ cưỡng chế protocol (phải có tool observation), chạy workflow deterministic, giới hạn repair và công bố trạng thái trung thực.

## 2. Thiết kế luồng cuối

```text
user message
  -> retrieve memory
  -> agent(tool_choice="required" nếu lượt này chưa có tool)
     -> không tool: protocol retry tối đa 1, sau đó protocol_error
     -> read tool: observation -> agent(tool_choice="auto") -> completed
     -> ask clarification: input_required
     -> mutation tool: deterministic replan + validate
         -> acceptable: commit -> completed
         -> not acceptable and repair_count < 2: deterministic repair/replan
         -> vẫn không acceptable: giữ current itinerary, terminal=infeasible
```

`completed` có hai nghĩa hợp lệ: read-only đã có ít nhất một read tool, hoặc mutation đã commit. Mutation chưa commit tuyệt đối không được báo completed.

## 3. Patch đề xuất

### 3.1. Không đọc secret từ `.env.example`

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

```diff
diff --git a/.env.example b/.env.example
@@
-GROQ_API_KEY_1=<giá trị hiện tại>
-GROQ_API_KEY_2=<giá trị hiện tại>
+GROQ_API_KEY=
```

Ngoài patch: revoke/rotate mọi key từng nằm trong Git history; không tự động rewrite history trong cùng PR.

### 3.2. Schema locality có cấu trúc

```diff
diff --git a/models/user_request.py b/models/user_request.py
@@
 RegionName = Literal[
@@
 ]
+LocationMode = Literal["strict", "nearby"]
@@
 class UserRequest(BaseModel):
@@
     region: RegionName = Field(...)
+    location_focus: str | None = Field(
+        default=None,
+        min_length=2,
+        max_length=120,
+        description="Locality bên trong region, ví dụ Hội An hoặc Sơn Trà.",
+    )
+    location_mode: LocationMode = Field(
+        default="strict",
+        description="strict chỉ lấy địa điểm mang locality; nearby cho phép mở rộng quanh tâm locality.",
+    )
+    max_locality_expansion_km: float = Field(default=8.0, gt=0, le=40)
```

```diff
diff --git a/agent/tools.py b/agent/tools.py
@@
-    BudgetLevel, CategoryConstraint, RegionName, UserRequest, VibeName,
+    BudgetLevel, CategoryConstraint, LocationMode, RegionName, UserRequest, VibeName,
@@
 class UpdateTripInput(BaseModel):
@@
     region: RegionName | None = None
+    location_focus: str | None = Field(default=None, min_length=2, max_length=120)
+    location_mode: LocationMode | None = None
+    max_locality_expansion_km: float | None = Field(default=None, gt=0, le=40)
@@
     def _tool_update_trip_settings(self, args, state):
         values = self._working_request(state)
         old_region = values.get("region")
+        old_focus = values.get("location_focus")
@@
-        if args.get("region") and args["region"] != old_region:
+        locality_changed = (
+            (args.get("region") and args["region"] != old_region)
+            or ("location_focus" in args and args.get("location_focus") != old_focus)
+        )
+        if locality_changed:
             values["required_place_ids"] = []
             values["excluded_place_ids"] = []
@@
-        if args.get("region") and args["region"] != old_region:
+        if locality_changed:
             constraints.pop("allowed_place_ids", None)
```

Việc LLM điền `location_focus="Hội An"` không phải keyword router. Đây là structured extraction giống `duration`/`region`; quyết định gọi `apply_trip_changes` vẫn do model.

### 3.3. Locality resolver deterministic

```diff
diff --git a/services/locality_service.py b/services/locality_service.py
new file mode 100644
--- /dev/null
+++ b/services/locality_service.py
@@
+from statistics import median
+
+from utils.distance import haversine
+from utils.place_matching import normalize_text
+
+
+class LocalityService:
+    """Resolve a model-extracted locality against the graph, never against a keyword intent table."""
+
+    @staticmethod
+    def _text(place):
+        return normalize_text(" ".join((
+            str(place.get("name", "")),
+            str(place.get("address", "")),
+            str(place.get("description", "")),
+        )))
+
+    @classmethod
+    def textual_match(cls, place, focus):
+        needle = normalize_text(focus)
+        return bool(needle and needle in cls._text(place))
+
+    @classmethod
+    def resolve(cls, places, focus, mode="strict", expansion_km=8.0):
+        places = list(places)
+        if not focus:
+            return places, {"focus": None, "anchor_count": 0, "expanded": False}
+        anchors = [place for place in places if cls.textual_match(place, focus)]
+        if not anchors:
+            raise ValueError(f"Không tìm thấy locality {focus!r} trong region đã chọn")
+        center = (
+            median(float(place["lat"]) for place in anchors),
+            median(float(place["lng"]) for place in anchors),
+        )
+        if mode == "strict":
+            selected = anchors
+        else:
+            selected = [
+                place for place in places
+                if cls.textual_match(place, focus)
+                or haversine(center[0], center[1], place["lat"], place["lng"])
+                <= expansion_km
+            ]
+        return selected, {
+            "focus": focus,
+            "mode": mode,
+            "anchor_count": len(anchors),
+            "candidate_count": len(selected),
+            "center": center,
+            "expanded": mode == "nearby",
+        }
```

Áp dụng sau region/hard exclusions, trước scoring:

```diff
diff --git a/services/itinerary_service.py b/services/itinerary_service.py
@@
 from services.route_optimizer import RouteOptimizer
+from services.locality_service import LocalityService
@@
     def __init__(..., locality=None):
@@
+        self.locality = locality or LocalityService()
@@
         filtered = self.graph.filter_places(user)
+        filtered, locality_meta = self.locality.resolve(
+            filtered,
+            user.location_focus,
+            user.location_mode,
+            user.max_locality_expansion_km,
+        )
@@
         for day in days:
+            day["locality"] = locality_meta
```

Validator kiểm locality độc lập trên output, không tin metadata:

```diff
diff --git a/services/itinerary_validator.py b/services/itinerary_validator.py
@@
 from utils.place_matching import place_categories, place_types
+from services.locality_service import LocalityService
@@
         attraction_count = 0
+        locality_match_count = 0
@@
                 else:
                     attraction_count += 1
+                    if not user.location_focus or LocalityService.textual_match(
+                        place, user.location_focus
+                    ):
+                        locality_match_count += 1
@@
+        locality_ratio = (
+            locality_match_count / attraction_count if attraction_count else 0.0
+        )
+        if (
+            user.location_focus
+            and user.location_mode == "strict"
+            and locality_ratio < 1.0
+        ):
+            hard_violations.append("locality_focus_violated")
@@
                 "total_distance_km": ...,
+                "locality_focus": user.location_focus,
+                "locality_match_ratio": round(locality_ratio, 3),
```

### 3.4. Route cost tham gia chọn và chia candidate

Thay vì score-cut -> matrix -> greedy day, giữ một routing pool rộng (tối đa giới hạn OSRM), tạo matrix, rồi phân cụm theo travel time. Required/day anchors luôn thắng utility.

```diff
diff --git a/services/itinerary_service.py b/services/itinerary_service.py
@@
 class ItineraryService:
+    ROUTE_MINUTES_WEIGHT = 0.015
+
+    @staticmethod
+    def _symmetric_minutes(matrix, left, right):
+        a = matrix["metrics"][(left["id"], right["id"])]["duration_minutes"]
+        b = matrix["metrics"][(right["id"], left["id"])]["duration_minutes"]
+        return (a + b) / 2
+
+    def _route_aware_day_pools(
+        self, candidates, route_matrix, duration, per_day_limit,
+        required_by_day, repair_attempt=0,
+    ):
+        """Deterministic balanced k-medoids; returns disjoint candidate IDs per day."""
+        if not candidates:
+            return {day: set() for day in range(duration)}
+        ranked = sorted(candidates, key=lambda p: (
+            -int(p["id"] in set().union(*required_by_day.values())),
+            -p.get("recommendation_score", 0), p["id"],
+        ))
+        medoids = []
+        for day in range(duration):
+            anchored = next(
+                (p for p in ranked if p["id"] in required_by_day[day] and p not in medoids),
+                None,
+            )
+            if anchored is not None:
+                medoids.append(anchored)
+                continue
+            if not medoids:
+                medoids.append(next(p for p in ranked if p not in medoids))
+            else:
+                medoids.append(max(
+                    (p for p in ranked if p not in medoids),
+                    key=lambda p: (
+                        min(self._symmetric_minutes(route_matrix, p, m) for m in medoids),
+                        p.get("recommendation_score", 0),
+                    ),
+                ))
+            if len(medoids) == len(ranked):
+                break
+        while len(medoids) < duration:
+            medoids.append(medoids[-1])
+
+        pools = {day: set(required_by_day[day]) for day in range(duration)}
+        capacities = {day: per_day_limit for day in range(duration)}
+        required_ids = set().union(*required_by_day.values())
+        for place in ranked:
+            if place["id"] in required_ids:
+                continue
+            choices = sorted(range(duration), key=lambda day: (
+                self._symmetric_minutes(route_matrix, place, medoids[day]),
+                len(pools[day]), day,
+            ))
+            day = next((d for d in choices if len(pools[d]) < capacities[d]), choices[0])
+            pools[day].add(place["id"])
+
+        # Repair attempts increase travel penalty by dropping the weakest remote optional POI.
+        if repair_attempt:
+            for day, ids in pools.items():
+                optional = [p for p in ranked if p["id"] in ids - required_by_day[day]]
+                optional.sort(key=lambda p: (
+                    p.get("recommendation_score", 0)
+                    - self.ROUTE_MINUTES_WEIGHT * (1 + repair_attempt)
+                    * self._symmetric_minutes(route_matrix, p, medoids[day])
+                ))
+                if optional and len(ids) > 1:
+                    ids.discard(optional[0]["id"])
+        return pools
@@
-        candidates = self._deduplicate_brands(raw_candidates)
-        candidates = self._apply_category_limits(... )[:attraction_limit]
+        routing_pool_limit = min(
+            max(attraction_limit * 2, user.duration * self.MAX_CANDIDATES_PER_DAY),
+            max(1, available_osrm_slots - meal_reserve),
+        )
+        candidates = self._apply_category_limits(
+            self._deduplicate_brands(raw_candidates),
+            user.category_constraints,
+            required_ids,
+        )[:routing_pool_limit]
@@
         route_matrix = self.routing.build_matrix(routing_places)
@@
         for place_id, requested_day in (required_place_days or {}).items():
             ...
+        day_pools = self._route_aware_day_pools(
+            candidates,
+            route_matrix,
+            user.duration,
+            self.MAX_CANDIDATES_PER_DAY,
+            required_by_day,
+            repair_attempt,
+        )
@@
-                    candidates,
+                    [p for p in candidates if p["id"] in day_pools[day_index]],
```

Mở rộng chữ ký `build(..., repair_attempt=0)`. Không truyền `current_start` từ điểm cuối ngày trước sang ngày sau nếu user không có nơi xuất phát; mỗi ngày là open route độc lập. Nếu có hotel coordinate, mọi ngày đều dùng cùng `start_place`:

```diff
@@
-        current_start = start_place
@@
-                    current_start,
+                    start_place,
@@
-            if end_place:
-                current_start = {...}
+            # Không nối ngày N+1 từ điểm cuối ngày N.
```

Điều này sửa một bias lớn hiện tại: ngày sau đang bị coi là bắt đầu tại điểm cuối ngày trước dù người dùng thường quay về nơi lưu trú.

### 3.5. Repair loop hữu hạn và protocol state

```diff
diff --git a/agent/state.py b/agent/state.py
@@
     error: dict | None
+    operation_kind: str | None
+    terminal_status: str | None
+    repair_count: int
+    no_tool_retry_count: int
```

Thêm executor repair; nó không nới hard constraint:

```diff
diff --git a/agent/tools.py b/agent/tools.py
@@
+    def _tool_repair_itinerary(self, _args, state):
+        constraints = self._working_constraints(state)
+        attempt = int(state.get("repair_count", 0)) + 1
+        request = UserRequest.model_validate(self._working_request(state))
+        itinerary = self.itinerary.build(
+            request,
+            candidate_ids=constraints.get("allowed_place_ids"),
+            meal_preferences=constraints.get("meal_preferences", []),
+            required_place_days=constraints.get("required_place_days", {}),
+            meal_requests=constraints.get("meal_requests", []),
+            scoped_exclusions=constraints.get("scoped_exclusions", []),
+            day_policies=constraints.get("day_policies", []),
+            optimization_policy=constraints.get("optimization_policy", {}),
+            repair_attempt=attempt,
+        )
+        report = self._validate_with_constraints(itinerary, request, constraints)
+        return self._ok(
+            "repair_itinerary", {"attempt": attempt, "report": report},
+            f"Đã sửa và kiểm tra lại lần {attempt}",
+        ), {
+            "working_itinerary": itinerary,
+            "validation_report": report,
+            "repair_count": attempt,
+            "dirty": True,
+            "committed": False,
+        }
```

Trong graph, bind hai model và bắt tool ở lượt đầu của mỗi user turn:

```diff
diff --git a/agent/graph.py b/agent/graph.py
@@
 class SoulVietAgentGraph:
     MAX_ITERATIONS = 8
+    MAX_REPAIR_ATTEMPTS = 2
+    MAX_NO_TOOL_RETRIES = 1
@@
-        self.model_with_tools = (
-            self.model.bind_tools(AGENT_TOOLS) if self.model else None
-        )
+        self.model_with_tools = self.model.bind_tools(AGENT_TOOLS) if self.model else None
+        self.model_with_required_tool = (
+            self.model.bind_tools(AGENT_TOOLS, tool_choice="required")
+            if self.model else None
+        )
@@
     def _call_agent(self, state):
@@
-        response = self.model_with_tools.invoke([
+        must_call_tool = state.get("tool_call_count", 0) == 0
+        selected_model = (
+            self.model_with_required_tool if must_call_tool else self.model_with_tools
+        )
+        response = selected_model.invoke([
@@
+        if must_call_tool and not getattr(response, "tool_calls", None):
+            retries = int(state.get("no_tool_retry_count", 0)) + 1
+            if retries <= self.MAX_NO_TOOL_RETRIES:
+                return {
+                    "messages": [response, HumanMessage(content=(
+                        "Yêu cầu protocol: hãy chọn tool phù hợp để lấy observation; "
+                        "không trả lời trực tiếp."
+                    ))],
+                    "iteration_count": iteration,
+                    "no_tool_retry_count": retries,
+                }
+            return {
+                "messages": [AIMessage(content="Agent không tạo được tool call hợp lệ.")],
+                "iteration_count": iteration,
+                "terminal_status": "protocol_error",
+                "error": {"type": "missing_required_tool_call"},
+            }
         return {"messages": [response], "iteration_count": iteration}
```

Trong test fake model, đổi `bind_tools(self, _tools)` thành `bind_tools(self, _tools, **_kwargs)`.

Đánh dấu loại thao tác từ tool thực tế, không đọc keyword user:

```diff
@@
     def _execute_tools(self, state):
@@
+        operation_kind = state.get("operation_kind")
+        if self.MUTATION_TOOLS.intersection(tool_names):
+            operation_kind = "mutation"
+        elif operation_kind is None and set(tool_names).intersection(self.READ_TOOLS):
+            operation_kind = "read"
@@
-        auto_finalize = bool(model_called_names) and not all(...)
+        report = local_state.get("validation_report") or {}
+        if local_state.get("committed"):
+            terminal_status = "completed"
+            auto_finalize = True
+        elif operation_kind == "mutation" and local_state.get("dirty"):
+            terminal_status = None
+            auto_finalize = False
+        else:
+            terminal_status = state.get("terminal_status")
+            auto_finalize = bool(model_called_names) and not all(
+                name in self.READ_TOOLS for name in model_called_names
+            )
@@
+            "operation_kind": operation_kind,
+            "terminal_status": terminal_status,
```

Thêm node repair và routing:

```diff
@@
+    def _repair(self, state):
+        report = state.get("validation_report") or {}
+        if report.get("acceptable"):
+            observation, updates = self.executor.execute("commit_itinerary", {}, state)
+            return {**updates, "terminal_status": "completed"}
+        if int(state.get("repair_count", 0)) >= self.MAX_REPAIR_ATTEMPTS:
+            # current_request/current_itinerary không bị đổi; chỉ bỏ draft.
+            return {
+                "working_request": None,
+                "working_itinerary": None,
+                "dirty": False,
+                "committed": False,
+                "terminal_status": "infeasible",
+            }
+        _, updates = self.executor.execute("repair_itinerary", {}, state)
+        return updates
+
+    @staticmethod
+    def _route_after_repair(state):
+        report = state.get("validation_report") or {}
+        if report.get("acceptable"):
+            return "repair"  # node commits on entry
+        if state.get("terminal_status") == "infeasible":
+            return "finalize"
+        return "repair"
@@
     def _route_after_tools(state):
-        return "finalize" if state.get("auto_finalize") else "agent"
+        if state.get("operation_kind") == "mutation" and state.get("dirty"):
+            return "repair"
+        return "finalize" if state.get("auto_finalize") else "agent"
@@
         builder.add_node("tools", self._execute_tools)
+        builder.add_node("repair", self._repair)
@@
         builder.add_conditional_edges(
             "tools", self._route_after_tools,
-            {"finalize": "finalize", "agent": "agent"},
+            {"finalize": "finalize", "agent": "agent", "repair": "repair"},
         )
+        builder.add_conditional_edges(
+            "repair",
+            lambda state: "finalize" if (
+                state.get("committed") or state.get("terminal_status") == "infeasible"
+            ) else "repair",
+            {"finalize": "finalize", "repair": "repair"},
+        )
@@
                 "repair_count": 0,
+                "no_tool_retry_count": 0,
+                "operation_kind": None,
+                "terminal_status": None,
```

Lưu ý triển khai: `_execute_tools` hiện tự commit khi acceptable; có thể giữ đoạn đó. Node `repair` chỉ nhận case chưa acceptable. Sau mỗi repair, nếu report acceptable thì commit ngay ở lần node kế; tổng số build tối đa là `1 + MAX_REPAIR_ATTEMPTS`.

Finalizer không dùng từ `partial`; trả lý do có cấu trúc:

```diff
@@
-        if state.get("dirty"):
-            ... "bản nháp ... partial"
+        if state.get("terminal_status") == "infeasible":
+            report = state.get("validation_report") or {}
+            reasons = (
+                report.get("hard_violations", [])
+                + report.get("quality_violations", [])
+            )
+            detail = ", ".join(reasons[:4]) or "không đủ dữ liệu phù hợp"
+            return {"messages": [AIMessage(content=(
+                "Mình chưa thể tạo lịch thỏa đồng thời mọi ràng buộc. "
+                f"Lịch hiện tại được giữ nguyên. Nguyên nhân: {detail}."
+            ))]}
```

### 3.6. Trạng thái API trung thực

```diff
diff --git a/services/langgraph_assistant_service.py b/services/langgraph_assistant_service.py
@@
         requires_input = "ask_user_clarification" in state.get(...)
+        terminal_status = state.get("terminal_status")
+        operation_kind = state.get("operation_kind")
+        if requires_input:
+            status = "input_required"
+        elif terminal_status in {"protocol_error", "infeasible"}:
+            status = terminal_status
+        elif operation_kind == "mutation" and not state.get("committed", False):
+            status = "failed"
+        else:
+            status = "completed"
@@
-                "status": "input_required" if requires_input else "completed",
+                "status": status,
+                "operation_kind": operation_kind,
+                "repair_attempts": state.get("repair_count", 0),
```

Thêm invariant trước return trong development/test (hoặc test assertion):

```python
assert not (
    status == "completed"
    and operation_kind == "mutation"
    and not state.get("committed")
)
```

### 3.7. System prompt

```diff
diff --git a/agent/prompts/system.md b/agent/prompts/system.md
@@
+- Khi người dùng nêu một locality như Hội An hoặc Sơn Trà, tự điền
+  trip_settings.location_focus và lập lịch từ dữ liệu thật; không hỏi place ID hay buộc
+  người dùng kể từng địa điểm. Chỉ clarification nếu thiếu quyết định làm thay đổi bản chất chuyến đi.
+- Harness sẽ tự replan, validate, repair và commit. Không trả từ kỹ thuật `partial` cho người dùng.
+- Không tự nới location_mode, excluded types, required places hoặc giới hạn quãng đường.
```

## 4. Test cần thêm trước khi merge

### `tests/test_agent_graph.py`

1. `test_first_decision_uses_required_tool_choice`: fake model ghi kwargs của `bind_tools`; xác nhận invocation đầu dùng binding `required`.
2. `test_missing_first_tool_call_retries_then_protocol_error`: hai response text, `tool_calls=0`; xác nhận không completed, không commit.
3. `test_read_tool_can_answer_after_observation`: lượt đầu required read tool, lượt hai text; status completed.
4. `test_partial_enters_bounded_repair_and_commits`: fake itinerary trả partial lần đầu, success lần hai; xác nhận repair_count=1 và committed.
5. `test_repair_stops_after_two_and_keeps_current_itinerary`: ba lần không acceptable; current itinerary không đổi, status infeasible, answer không chứa `partial`.
6. `test_mutation_without_commit_is_never_completed`.

### `tests/test_locality_service.py`

- Unicode/case-fold: `Hội An` khớp `hoi an`.
- Strict chỉ giữ textual locality.
- Nearby giữ anchors và các điểm trong bán kính.
- Focus không tồn tại trả lỗi rõ ràng.

### `tests/test_itinerary_service.py` hoặc file mới `tests/test_route_aware_planner.py`

- Matrix có hai cụm xa nhau; hai ngày phải nhận hai pool rời, không zig-zag.
- Required place được giữ và đúng ngày.
- Tổng travel minutes route-aware <= baseline score-only.
- Mỗi ngày bắt đầu từ hotel khi có `start_lat/lng`; không bắt đầu từ điểm cuối ngày trước.
- Repair giảm/bằng distance nhưng không bỏ required place và không nới exclusion.

### `tests/test_itinerary_validator.py`

- Strict locality có điểm ngoài locality => `locality_focus_violated`.
- 100% Hội An => locality ratio 1.0 và acceptable nếu các rule khác đạt.

### `tests/test_langgraph_assistant_service.py`

- mutation dirty/uncommitted => `failed` hoặc `infeasible`, không `completed`.
- read-only tool result => `completed`, `committed=false` là hợp lệ.
- mutation committed => `completed`, `committed=true`.

### `tests/test_configuration.py`

Monkeypatch `load_dotenv` trước import/reload và xác nhận không call với `.env.example`; quét `.env.example` bảo đảm các key có value rỗng.

### Benchmark acceptance

Mở rộng evaluator bắt buộc:

- mutation case: `tool_calls >= 1`, `committed=true`, `agent.status=completed`.
- locality case: `request.location_focus` đúng và `validation_report.metrics.locality_match_ratio >= 0.9`.
- repair case: `repair_attempts <= 2`, không có forbidden `partial`.
- route case: total distance/travel không tăng so baseline.
- infeasible case: current itinerary bất biến và status=infeasible.

## 5. Rủi ro và cách chặn

- Groq/model không hỗ trợ `tool_choice="required"`: giữ guard `tool_calls=0` và protocol retry; khi khởi tạo nếu provider reject required, fail-fast cấu hình thay vì âm thầm completed.
- Textual locality có false positive từ description: ưu tiên `address`, sau đó `name`, chỉ dùng description để tìm anchor khi address không đủ; thêm fixture theo dữ liệu thật Hội An/Sơn Trà.
- Strict locality quá ít restaurant: meal có thể dùng `nearby` riêng nhưng chỉ trong bán kính và phải ghi metric; không tự mở rộng attraction locality.
- K-medoids O(n²): pool bị chặn dưới 100 coordinate nên phù hợp; cache OSRM matrix theo sorted coordinate hash để giảm latency.
- Repair lặp deterministic: `repair_attempt` phải thực sự tăng route penalty/drop optional remote place; test call count chặn vòng lặp vô nghĩa.
- Required places nhiều hơn capacity: trả infeasible có conflict cụ thể; không drop required.
- Checkpoint giữ state lượt trước: mọi counter/status/operation_kind phải reset trong input của mỗi `invoke`, trong khi messages/memory vẫn được checkpoint.
- `.env.example` từng có key: xóa ở HEAD chưa đủ nếu key đã push; bắt buộc rotate.

## 6. Lệnh kiểm chứng

```powershell
.\myenv\Scripts\python.exe -m pytest tests/test_configuration.py tests/test_locality_service.py tests/test_route_aware_planner.py tests/test_agent_graph.py tests/test_itinerary_validator.py tests/test_langgraph_assistant_service.py -q
.\myenv\Scripts\python.exe -m pytest -q
.\myenv\Scripts\python.exe -m scripts.benchmark_recommendation
.\myenv\Scripts\python.exe -m scripts.benchmark_agent_quality --case hoi_an_autoplan_without_clarification
.\myenv\Scripts\python.exe -m scripts.benchmark_agent_quality --case repair_partial_and_commit
.\myenv\Scripts\python.exe -m scripts.benchmark_agent_quality --case reorder_only_reduces_travel
.\myenv\Scripts\python.exe -m scripts.benchmark_agent_quality
```

Quality gate đề xuất: unit suite xanh; 10/10 quality cases pass; locality ratio >= 0.9; mọi mutation completed đều committed; repair <= 2; không response nào chứa thông báo `partial`; route optimization không làm tăng tổng distance so baseline.
