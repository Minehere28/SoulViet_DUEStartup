# Phương án 2 — Tool-first harness, locality contract, bounded repair và route-aware partition

## Phạm vi và kết luận chẩn đoán

Phương án này được xây dựng độc lập từ code production và benchmark hiện tại. Nó không thay router bằng một bộ luật từ khóa mới. LLM vẫn là thành phần hiểu ý định và chọn tool; harness chỉ cưỡng chế các postcondition có thể kiểm tra được.

Các lỗi gốc:

1. `bind_tools()` chỉ quảng bá tool. `_route_after_agent()` đi thẳng tới `END` nếu model trả text, vì vậy mutation có thể mang trạng thái `completed` dù `tool_calls=0`, `committed=false`.
2. `UserRequest` chỉ có `region`; `GraphService.filter_places()` chỉ so sánh `place["region"]`. Hội An và Sơn Trà không trở thành ràng buộc candidate.
3. Sau mutation, `_execute_tools()` replan đúng một lần. Nếu report là `partial`, graph vẫn `finalize`, đưa thuật ngữ nội bộ cho user và không sửa tiếp.
4. Candidate được cắt theo recommendation score trước khi có matrix; sau đó từng ngày lấy lần lượt từ một pool chung. OR-Tools tối ưu thứ tự trong ngày nhưng không chia candidate thành cụm đường đi cho nhiều ngày.
5. `LangGraphAssistantService` suy diễn mọi kết quả không clarification là `completed`, không dựa trên terminal state/postcondition.
6. `agent/graph.py` và legacy `services/llm_service.py` nạp `.env.example`; file mẫu không được là secret source.

Nguyên tắc thiết kế:

- Mọi lượt mới phải có ít nhất một tool call; dùng `tool_choice="required"` và một guard ở harness nếu provider không tuân thủ. Không phân loại bằng keyword.
- Locality là field có kiểu trong request/tool contract, được resolver ánh xạ sang vùng và predicate dữ liệu.
- Repair là vòng lặp deterministic, tối đa 3 lần, không tự nới hard constraint. Thử lại planner với candidate breadth/time budget lớn dần; hết vòng trả `infeasible` cùng violation cụ thể.
- Candidate được phân cụm theo OSRM travel time trước khi tối ưu từng ngày.
- API status xuất phát từ `terminal_status`, không suy ra từ việc request HTTP trả 200.

## Unified diff đề xuất

### 1. Không dùng `.env.example` trong runtime

```diff
diff --git a/agent/graph.py b/agent/graph.py
@@
 load_dotenv()
-load_dotenv(".env.example", override=False)
diff --git a/services/llm_service.py b/services/llm_service.py
@@
 load_dotenv()
-load_dotenv(".env.example", override=False)
diff --git a/.env.example b/.env.example
@@
-GROQ_API_KEY=<giá trị thật nếu đang có>
+# Copy this file to .env and keep .env out of Git.
+GROQ_API_KEY=
+GROQ_MODEL=openai/gpt-oss-20b
+GROQ_TIMEOUT_SECONDS=120
+GROQ_MAX_RETRIES=1
+AGENT_MAX_REPAIR_ATTEMPTS=3
```

Không đưa giá trị cũ vào diff/log. Key từng tồn tại trong Git phải revoke ngoài code.

### 2. Locality resolver dùng dữ liệu địa chỉ và bán kính

```diff
diff --git a/utils/locality.py b/utils/locality.py
new file mode 100644
--- /dev/null
+++ b/utils/locality.py
@@
+from dataclasses import dataclass
+from math import asin, cos, radians, sin, sqrt
+
+from utils.place_matching import normalize_text
+
+
+@dataclass(frozen=True)
+class LocalitySpec:
+    name: str
+    region: str
+    aliases: tuple[str, ...]
+    address_terms: tuple[str, ...]
+    center: tuple[float, float]
+    default_radius_km: float
+
+
+LOCALITIES = (
+    LocalitySpec(
+        name="Hội An",
+        region="Quảng Nam",
+        aliases=("hoi an", "pho co hoi an", "phố cổ hội an"),
+        address_terms=("hoi an",),
+        center=(15.8801, 108.3380),
+        default_radius_km=8.0,
+    ),
+    LocalitySpec(
+        name="Sơn Trà",
+        region="Đà Nẵng",
+        aliases=("son tra", "ban dao son tra", "bán đảo sơn trà"),
+        address_terms=("son tra",),
+        center=(16.1066, 108.2770),
+        default_radius_km=10.0,
+    ),
+)
+
+
+def resolve_locality(value: str | None) -> LocalitySpec | None:
+    query = normalize_text(value or "")
+    if not query:
+        return None
+    for spec in LOCALITIES:
+        aliases = {normalize_text(alias) for alias in spec.aliases}
+        if query == normalize_text(spec.name) or query in aliases:
+            return spec
+    return None
+
+
+def _distance_km(a_lat, a_lng, b_lat, b_lng):
+    earth_radius_km = 6371.0088
+    lat_delta = radians(b_lat - a_lat)
+    lng_delta = radians(b_lng - a_lng)
+    value = (
+        sin(lat_delta / 2) ** 2
+        + cos(radians(a_lat)) * cos(radians(b_lat))
+        * sin(lng_delta / 2) ** 2
+    )
+    return 2 * earth_radius_km * asin(sqrt(value))
+
+
+def locality_match(place, focus, mode="strict", radius_km=None):
+    spec = resolve_locality(focus)
+    if spec is None:
+        # Không âm thầm coi locality lạ là hợp lệ.
+        return False
+    searchable = normalize_text(
+        f"{place.get('name', '')} {place.get('address', '')}"
+    )
+    if any(normalize_text(term) in searchable for term in spec.address_terms):
+        return True
+    if mode != "nearby":
+        return False
+    lat = float(place.get("lat") or 0)
+    lng = float(place.get("lng") or 0)
+    if not lat or not lng:
+        return False
+    radius = float(radius_km or spec.default_radius_km)
+    return _distance_km(lat, lng, *spec.center) <= radius
```

Không dùng fuzzy substring để resolve tên locality vì dễ ánh xạ nhầm prompt dài. LLM truyền field đã trích xuất; resolver chỉ canonicalize/validate.

```diff
diff --git a/models/user_request.py b/models/user_request.py
@@
 from pydantic import BaseModel, ConfigDict, Field, model_validator
+from utils.locality import resolve_locality
@@
 class UserRequest(BaseModel):
@@
     region: RegionName = Field(...)
+    location_focus: str | None = Field(
+        default=None, min_length=2, max_length=80,
+        description="Locality nhỏ hơn tỉnh/thành, ví dụ Hội An hoặc Sơn Trà.",
+    )
+    location_mode: Literal["strict", "nearby"] = "strict"
+    location_radius_km: float | None = Field(default=None, gt=0, le=50)
@@
     def validate_daily_time_window(self):
+        if self.location_focus:
+            locality = resolve_locality(self.location_focus)
+            if locality is None:
+                raise ValueError("Unsupported location_focus")
+            if locality.region != self.region:
+                raise ValueError(
+                    f"location_focus {locality.name} belongs to {locality.region}"
+                )
+            self.location_focus = locality.name
         if self.day_end_time <= self.day_start_time:
```

```diff
diff --git a/agent/tools.py b/agent/tools.py
@@
 from utils.place_matching import normalize_text, place_categories, place_types
+from utils.locality import resolve_locality, locality_match
@@
 class UpdateTripInput(BaseModel):
@@
     region: RegionName | None = None
+    location_focus: str | None = Field(default=None, min_length=2, max_length=80)
+    location_mode: str | None = Field(default=None, pattern="^(strict|nearby)$")
+    location_radius_km: float | None = Field(default=None, gt=0, le=50)
@@
     def _tool_update_trip_settings(self, args, state):
         values = self._working_request(state)
         old_region = values.get("region")
+        if args.get("location_focus"):
+            locality = resolve_locality(args["location_focus"])
+            if locality is None:
+                raise ValueError(
+                    "Unsupported locality; use ask_user_clarification only "
+                    "when the locality itself is genuinely ambiguous"
+                )
+            args = {**args, "location_focus": locality.name, "region": locality.region}
         values.update({key: value for key, value in args.items() if value is not None})
@@
         if args.get("region") and args["region"] != old_region:
             constraints.pop("allowed_place_ids", None)
+        if args.get("location_focus"):
+            constraints.pop("allowed_place_ids", None)
```

```diff
diff --git a/services/graph_service.py b/services/graph_service.py
@@
 from utils.place_matching import ...
+from utils.locality import locality_match
@@
             if place["region"] != user.region:
                 continue
+            if user.location_focus and not locality_match(
+                place,
+                user.location_focus,
+                user.location_mode,
+                user.location_radius_km,
+            ):
+                continue
             result.append(place)
```

```diff
diff --git a/services/itinerary_validator.py b/services/itinerary_validator.py
@@
 from utils.place_matching import matches_category, place_categories, place_types
+from utils.locality import locality_match
@@
         all_idle_gaps = []
+        locality_attractions = 0
+        locality_mismatches = []
@@
                 else:
                     attraction_count += 1
+                    if user.location_focus:
+                        if locality_match(
+                            place, user.location_focus,
+                            user.location_mode, user.location_radius_km,
+                        ):
+                            locality_attractions += 1
+                        else:
+                            locality_mismatches.append(place_id)
@@
         if missing_required_ids:
             quality_violations.append("missing_required_places")
+        if locality_mismatches:
+            hard_violations.extend(
+                f"outside_locality:{place_id}"
+                for place_id in locality_mismatches
+            )
+            valid = False
@@
                 "total_distance_km": round(...),
+                "locality_focus": user.location_focus,
+                "locality_match_ratio": (
+                    round(locality_attractions / attraction_count, 3)
+                    if attraction_count and user.location_focus else 1.0
+                ),
+                "outside_locality_place_ids": locality_mismatches,
```

Lưu ý: đoạn `valid = not hard_violations` hiện nằm trước quality checks; patch thật phải chuyển phép gán đó xuống sau khi locality violation được thêm, tránh `acceptable=true` giả.

### 3. Cưỡng chế tool ở lượt đầu và terminal state trung thực

```diff
diff --git a/agent/state.py b/agent/state.py
@@
 class SoulVietAgentState(TypedDict, total=False):
@@
     error: dict | None
+    no_tool_retry_count: int
+    repair_attempt_count: int
+    terminal_status: str
```

```diff
diff --git a/agent/graph.py b/agent/graph.py
@@
 class SoulVietAgentGraph:
     MAX_ITERATIONS = 8
     MAX_TOOL_CALLS = 16
+    MAX_NO_TOOL_RETRIES = 2
+    MAX_REPAIR_ATTEMPTS = max(
+        1, int(os.getenv("AGENT_MAX_REPAIR_ATTEMPTS", "3"))
+    )
@@
-        self.model_with_tools = (
-            self.model.bind_tools(AGENT_TOOLS) if self.model else None
-        )
+        self.model_tools_required = (
+            self.model.bind_tools(AGENT_TOOLS, tool_choice="required")
+            if self.model else None
+        )
+        self.model_with_tools = (
+            self.model.bind_tools(AGENT_TOOLS, tool_choice="auto")
+            if self.model else None
+        )
@@
     def available(self):
-        return self.model_with_tools is not None
+        return self.model_tools_required is not None
@@
     def _call_agent(self, state):
@@
-        response = self.model_with_tools.invoke([
+        must_use_tool = (
+            state.get("tool_call_count", 0) == 0
+            or (
+                state.get("dirty", False)
+                and not (state.get("validation_report") or {}).get("acceptable")
+            )
+        )
+        bound_model = (
+            self.model_tools_required if must_use_tool else self.model_with_tools
+        )
+        response = bound_model.invoke([
@@
-    @staticmethod
-    def _route_after_agent(state):
+    def _guard_agent_output(self, state):
         message = state["messages"][-1]
         if getattr(message, "tool_calls", None):
-            return "tools"
-        return END
+            return {"no_tool_retry_count": 0, "terminal_status": "running"}
+        if state.get("tool_call_count", 0) > 0:
+            return {"terminal_status": "read_completed"}
+        retries = state.get("no_tool_retry_count", 0) + 1
+        if retries <= self.MAX_NO_TOOL_RETRIES:
+            return {"no_tool_retry_count": retries, "terminal_status": "running"}
+        return {
+            "no_tool_retry_count": retries,
+            "terminal_status": "tool_required_failed",
+            "error": {"type": "tool_required_failed"},
+        }
+
+    @staticmethod
+    def _route_after_guard(state):
+        message = state["messages"][-1]
+        if getattr(message, "tool_calls", None):
+            return "tools"
+        if state.get("terminal_status") == "running":
+            return "agent"
+        return "finalize"
@@
         builder.add_node("agent", self._call_agent)
+        builder.add_node("guard_agent_output", self._guard_agent_output)
@@
-        builder.add_conditional_edges("agent", self._route_after_agent)
+        builder.add_edge("agent", "guard_agent_output")
+        builder.add_conditional_edges(
+            "guard_agent_output", self._route_after_guard,
+            {"tools": "tools", "agent": "agent", "finalize": "finalize"},
+        )
@@
                 "error": None,
+                "no_tool_retry_count": 0,
+                "repair_attempt_count": 0,
+                "terminal_status": "running",
```

`tool_choice="required"` là contract với provider; guard là lớp kiểm chứng độc lập. Nó không nhìn từ khóa user và không tự chọn tool.

### 4. Bounded repair loop, không trả `partial` chung chung

Thay block automatic workflow trong `_execute_tools()` bằng helper deterministic. Mỗi lần thử vẫn giữ nguyên hard constraints; chỉ tăng search breadth và solver budget.

```diff
diff --git a/agent/graph.py b/agent/graph.py
@@
+    def _run_planning_workflow(self, local_state):
+        automatic = []
+        updates = {}
+        first_attempt = int(local_state.get("repair_attempt_count", 0))
+        for attempt in range(first_attempt, self.MAX_REPAIR_ATTEMPTS):
+            observation, tool_updates = self.executor.execute(
+                "replan_itinerary", {"repair_attempt": attempt}, local_state
+            )
+            local_state.update(tool_updates)
+            updates.update(tool_updates)
+            automatic.append(observation)
+            updates["repair_attempt_count"] = attempt + 1
+            report = local_state.get("validation_report") or {}
+            if report.get("acceptable"):
+                observation, tool_updates = self.executor.execute(
+                    "commit_itinerary", {}, local_state
+                )
+                local_state.update(tool_updates)
+                updates.update(tool_updates)
+                updates["terminal_status"] = "committed"
+                automatic.append(observation)
+                return automatic, updates
+        updates["terminal_status"] = "infeasible"
+        return automatic, updates
@@
         if (
             should_run_workflow
             and local_state.get("dirty")
             and "commit_itinerary" not in called_workflow
         ):
             try:
-                if "replan_itinerary" not in called_workflow:
-                    ... one replan ...
-                report = local_state.get("validation_report") or {}
-                if report.get("acceptable"):
-                    ... commit ...
+                automatic, workflow_updates = self._run_planning_workflow(
+                    local_state
+                )
+                local_state.update(workflow_updates)
+                updates.update(workflow_updates)
+                tool_names.extend(
+                    [item["tool"] for item in automatic if item.get("tool")]
+                )
             except Exception as error:
@@
+                updates["terminal_status"] = "tool_error"
@@
-        auto_finalize = bool(model_called_names) and not all(
-            name in self.READ_TOOLS for name in model_called_names
-        )
+        if "ask_user_clarification" in model_called_names:
+            updates["terminal_status"] = "input_required"
+        auto_finalize = updates.get("terminal_status") in {
+            "committed", "infeasible", "input_required", "tool_error"
+        }
@@
     def _finalize_tools(state):
@@
-        if state.get("committed"):
+        if state.get("terminal_status") == "committed" and state.get("committed"):
             return {"messages": [AIMessage(content=(
                 "Đã cập nhật, lập lại và kiểm tra hành trình thành công."
             ))]}
-        if state.get("dirty"):
+        if state.get("terminal_status") == "infeasible":
             report = state.get("validation_report") or {}
+            violations = [
+                *report.get("hard_violations", []),
+                *report.get("quality_violations", []),
+            ]
             return {"messages": [AIMessage(content=(
-                "Mình đã tạo bản nháp nhưng chưa commit vì lịch chưa thỏa các "
-                f"ràng buộc ({report.get('status', 'chưa xác định')})."
+                "Mình chưa thể tạo lịch hợp lệ mà vẫn giữ nguyên mọi yêu cầu. "
+                "Các ràng buộc đang xung đột: "
+                + ", ".join(violations[:5])
             ))]}
+        if state.get("terminal_status") == "tool_required_failed":
+            return {"messages": [AIMessage(content=(
+                "Agent không thực hiện được bước công cụ bắt buộc; lịch cũ được giữ nguyên."
+            ))]}
```

```diff
diff --git a/agent/tools.py b/agent/tools.py
@@
     def _tool_replan_itinerary(self, _args, state):
+        repair_attempt = max(0, int(_args.get("repair_attempt", 0)))
         request = UserRequest.model_validate(self._working_request(state))
@@
             optimization_policy=constraints.get("optimization_policy", {}),
+            repair_attempt=repair_attempt,
         )
@@
         summary["validation_status"] = report["status"]
+        summary["repair_attempt"] = repair_attempt
```

`ItineraryService.build(..., repair_attempt=0)` dùng attempt để tăng solver time/candidate breadth, không bỏ exclusion, không tăng distance limit và không đổi locality mode:

```diff
diff --git a/services/itinerary_service.py b/services/itinerary_service.py
@@
     def build(...,
         optimization_policy=None,
+        repair_attempt=0,
     ):
@@
-        desired_candidates = (requested_places * 5 + 1) // 2
+        candidate_multiplier = min(4, 2 + int(repair_attempt))
+        desired_candidates = requested_places * candidate_multiplier
@@
         optimized_places = self.optimizer.optimize(
@@
+            search_time_multiplier=1 + repair_attempt,
         )
diff --git a/services/route_optimizer.py b/services/route_optimizer.py
@@
     def optimize(...,
         required_place_ids=None,
+        search_time_multiplier=1,
     ):
@@
         search.time_limit.FromMilliseconds(
-            max(50, self.time_limit_milliseconds)
+            max(50, self.time_limit_milliseconds * search_time_multiplier)
         )
```

Các call site `_recover_nonempty_route()` cũng truyền multiplier, hoặc giữ default; không thay signature positional phía trước để tránh regression.

### 5. Phân cụm candidate theo exact route time trước khi tối ưu từng ngày

```diff
diff --git a/services/itinerary_service.py b/services/itinerary_service.py
@@
+    @classmethod
+    def _partition_candidates_by_route(
+        cls, candidates, route_matrix, day_count, required_by_day
+    ):
+        """Balanced deterministic medoid assignment using OSRM minutes."""
+        pools = [set(required_by_day[index]) for index in range(day_count)]
+        by_id = {place["id"]: place for place in candidates}
+
+        def minutes(left_id, right_id):
+            if left_id == right_id:
+                return 0
+            left = by_id[left_id]
+            right = by_id[right_id]
+            left_id = left.get("routing_id", left["id"])
+            right_id = right.get("routing_id", right["id"])
+            return route_matrix["metrics"][(left_id, right_id)][
+                "duration_minutes"
+            ]
+
+        ranked = sorted(
+            candidates,
+            key=lambda place: (
+                -place.get("query_priority", 0),
+                -place.get("recommendation_score", 0),
+                place["id"],
+            ),
+        )
+        medoids = []
+        for day in range(day_count):
+            anchored = next(iter(sorted(pools[day])), None)
+            if anchored:
+                medoids.append(anchored)
+                continue
+            remaining = [p["id"] for p in ranked if p["id"] not in medoids]
+            if not medoids:
+                medoids.append(remaining[0])
+            else:
+                medoids.append(max(
+                    remaining,
+                    key=lambda pid: min(minutes(pid, seed) for seed in medoids),
+                ))
+            pools[day].add(medoids[-1])
+
+        target_load = max(1, (len(candidates) + day_count - 1) // day_count)
+        already = set().union(*pools)
+        for place in ranked:
+            place_id = place["id"]
+            if place_id in already:
+                continue
+            day = min(range(day_count), key=lambda index: (
+                minutes(place_id, medoids[index])
+                + max(0, len(pools[index]) - target_load) * 60,
+                len(pools[index]),
+                index,
+            ))
+            pools[day].add(place_id)
+            already.add(place_id)
+        return pools
@@
     def _build_day(...,
         fill_idle_gaps=True,
+        allowed_place_ids=None,
     ):
@@
         eligible_remaining = [
             place for place in remaining
             if place["id"] not in reserved_place_ids
             or place["id"] in required_place_ids
         ]
+        if allowed_place_ids is not None:
+            allowed_place_ids = set(allowed_place_ids) | required_place_ids
+            eligible_remaining = [
+                place for place in eligible_remaining
+                if place["id"] in allowed_place_ids
+            ]
@@
         route_matrix = self.routing.build_matrix(routing_places)
@@
         for place_id, requested_day in (required_place_days or {}).items():
             ...
+        day_candidate_pools = self._partition_candidates_by_route(
+            candidates, route_matrix, user.duration, required_by_day
+        )
@@
                 self._build_day(
@@
                     optimization_policy.get("fill_idle_gaps", True),
+                    day_candidate_pools[day_index],
                 )
```

Hai điểm phải sửa kèm để route metric trung thực:

- Nếu user có `start_lat/start_lng`, mỗi ngày phải bắt đầu lại từ start location/hotel, không lấy điểm cuối ngày trước làm điểm đầu ngày sau. Nếu không có start location, dùng open route cho từng ngày.
- Gap filler cũng chỉ nhận candidate trong `day_candidate_pools[day_index]`; nếu truyền toàn bộ `remaining`, nó sẽ phá cụm vừa tạo.

Patch bổ sung:

```diff
diff --git a/services/itinerary_service.py b/services/itinerary_service.py
@@
-                    [place for place in remaining if allowed_for_day(place)],
+                    [
+                        place for place in remaining
+                        if allowed_for_day(place)
+                        and (
+                            allowed_place_ids is None
+                            or place["id"] in allowed_place_ids
+                        )
+                    ],
@@
-            if end_place:
-                source_place_id = self._routing_id(end_place)
-                current_start = { ... previous day end ... }
+            # Mỗi ngày là một route độc lập từ nơi lưu trú nếu có.
+            current_start = start_place
```

Không thay objective bằng khoảng cách Euclid sau khi đã có OSRM. Clustering dùng `duration_minutes`; OR-Tools tiếp tục xử lý opening windows, visit time và max distance.

### 6. Service không báo `completed` giả

```diff
diff --git a/services/langgraph_assistant_service.py b/services/langgraph_assistant_service.py
@@
-        requires_input = "ask_user_clarification" in state.get(
-            "last_tool_names", []
-        )
+        terminal_status = state.get("terminal_status", "tool_error")
+        requires_input = terminal_status == "input_required"
@@
             "agent": {
-                "status": "input_required" if requires_input else "completed",
+                "status": terminal_status,
                 "requires_input": requires_input,
@@
                 "error": state.get("error"),
+                "repair_attempts": state.get("repair_attempt_count", 0),
             },
```

Invariant ở boundary:

```python
if terminal_status == "committed":
    assert state.get("committed") is True
    assert (state.get("validation_report") or {}).get("acceptable") is True
if terminal_status == "read_completed":
    assert state.get("tool_call_count", 0) >= 1
if terminal_status in {"infeasible", "tool_error", "tool_required_failed"}:
    assert state.get("committed") is not True
```

Nên biến assertions trên thành helper `_validate_terminal_state()` ném lỗi nội bộ trước khi serialize, thay vì chỉ để comment.

### 7. Prompt làm rõ “locality đủ để lập lịch, không hỏi ID”

```diff
diff --git a/agent/prompts/system.md b/agent/prompts/system.md
@@
+- Khi người dùng nêu locality đủ rõ như Hội An hoặc Sơn Trà, hãy dùng
+  apply_trip_changes.trip_settings.location_focus. Locality là đủ để tự chọn candidate;
+  không hỏi place ID và không bắt người dùng liệt kê địa điểm cụ thể.
+- Với yêu cầu lập lịch/chỉnh lịch, tool call đầu phải là apply_trip_changes và chứa
+  toàn bộ constraint đã hiểu. Harness sẽ tự replan, repair, validate và commit.
+- Không nói từ trạng thái nội bộ `partial` với người dùng. Nếu repair hết giới hạn,
+  chỉ nêu các constraint cụ thể đang xung đột và giữ lịch đã commit trước đó.
+- Không tự mở rộng `location_mode=strict` sang vùng lân cận. Chỉ dùng `nearby` khi
+  người dùng nói “quanh”, “gần” hoặc cho phép mở rộng khu vực.
```

Đây là hướng dẫn semantic cho LLM, không phải keyword router trong Python.

## Tests cần thêm/sửa

### Unit: tool guard và terminal state

```diff
diff --git a/tests/test_agent_graph.py b/tests/test_agent_graph.py
@@
 class ScriptedModel:
@@
-    def bind_tools(self, _tools):
+    def bind_tools(self, _tools, **kwargs):
+        self.tool_choices = getattr(self, "tool_choices", [])
+        self.tool_choices.append(kwargs.get("tool_choice"))
         return self
@@
+def test_first_turn_retries_when_provider_ignores_required_tool(tmp_path):
+    model = ScriptedModel([
+        AIMessage(content="Tự trả lời sai"),
+        AIMessage(content="", tool_calls=[{
+            "name": "get_itinerary_summary", "args": {},
+            "id": "read-1", "type": "tool_call",
+        }]),
+        AIMessage(content="Lịch hiện có một ngày."),
+    ])
+    agent = SoulVietAgentGraph(memory=AgentMemory(tmp_path), model=model)
+    state = agent.invoke("u", "t", "Lịch có mấy ngày?", request_data(), [{
+        "day": 1, "places": [], "total_distance_km": 0,
+    }])
+    assert state["tool_call_count"] == 1
+    assert state["terminal_status"] == "read_completed"
+    assert len(model.calls) == 3
+
+
+def test_no_tool_exhaustion_is_not_completed(tmp_path):
+    model = ScriptedModel([AIMessage(content="không tool") for _ in range(3)])
+    agent = SoulVietAgentGraph(memory=AgentMemory(tmp_path), model=model)
+    state = agent.invoke("u", "t", "Tạo lịch", request_data(), [])
+    assert state["terminal_status"] == "tool_required_failed"
+    assert state["committed"] is False
```

### Unit: bounded repair

Không phụ thuộc Groq. Inject executor/planner giả trả `partial`, `partial`, rồi `success`; assert 3 replans, đúng một commit. Ca luôn partial assert đúng `MAX_REPAIR_ATTEMPTS`, `terminal_status=infeasible`, current itinerary không đổi và answer không chứa `partial`.

```python
def test_partial_is_repaired_and_committed_without_extra_llm_call(...):
    # scripted LLM chỉ gọi apply_trip_changes một lần
    # fake executor trả reports: partial, partial, success
    assert state["repair_attempt_count"] == 3
    assert state["terminal_status"] == "committed"
    assert state["committed"] is True

def test_repair_exhaustion_preserves_committed_itinerary(...):
    assert state["terminal_status"] == "infeasible"
    assert state["current_itinerary"] == initial_itinerary
    assert "partial" not in state["messages"][-1].content.casefold()
```

### Unit: locality

```diff
diff --git a/tests/test_locality.py b/tests/test_locality.py
new file mode 100644
--- /dev/null
+++ b/tests/test_locality.py
@@
+from utils.locality import locality_match, resolve_locality
+
+def test_resolves_hoi_an_and_son_tra_to_parent_regions():
+    assert resolve_locality("Hội An").region == "Quảng Nam"
+    assert resolve_locality("bán đảo Sơn Trà").region == "Đà Nẵng"
+
+def test_strict_locality_uses_address_not_region_only():
+    hoi_an = {"name": "X", "address": "Cẩm Phô, Hội An", "lat": 0, "lng": 0}
+    tam_ky = {"name": "Y", "address": "Tam Kỳ, Quảng Nam", "lat": 0, "lng": 0}
+    assert locality_match(hoi_an, "Hội An", "strict")
+    assert not locality_match(tam_ky, "Hội An", "strict")
```

Integration với graph thật:

```python
def test_hoi_an_request_filters_every_attraction_to_locality():
    user = UserRequest(..., region="Quảng Nam", location_focus="Hội An")
    places = GraphService().filter_places(user)
    assert len(places) >= user.duration * user.max_places_per_day
    assert all(locality_match(place, "Hội An") for place in places)
```

### Unit: route-aware partition

Dùng matrix nhân tạo với hai cụm `{A,B,C}` và `{X,Y,Z}`: intra-cluster 5 phút, inter-cluster 90 phút. Assert mỗi pool chỉ chứa một cụm, các required-day anchor đúng ngày, output deterministic khi input đảo thứ tự. Thêm test gap filler không lấy candidate từ pool ngày khác.

### API/service

```python
def test_service_never_reports_completed_without_a_tool():
    state = {"terminal_status": "tool_required_failed", "tool_call_count": 0,
             "committed": False, "messages": [AIMessage(content="failed")]}
    response = service.customize(...)
    assert response["agent"]["status"] == "tool_required_failed"
    assert response["agent"]["status"] != "completed"

def test_committed_status_requires_acceptable_report():
    # expect internal invariant failure for inconsistent injected state
```

### Benchmark assertions bổ sung

Trong `scripts/benchmark_agent_quality.py`:

- Mutation/autoplan: `tool_calls >= 1`, `agent.status == "committed"`, `committed=true`, `acceptable=true`.
- Read-only: `tool_calls >= 1`, `status == "read_completed"`.
- Mọi case: cấm answer chứa `partial`, `place id`, `id cụ thể` nếu `requires_input=false` được kỳ vọng.
- Locality lấy metric validator trước; fallback evaluator bằng normalized `name + address` chỉ để báo cáo.
- Route case so sánh exact `total_travel_time_minutes` trước/sau, không chỉ km.
- Báo `repair_attempts` và violations trong JSON output.

Các quality case tối thiểu cần chạy live sau unit tests:

1. “Tôi muốn đi Hội An 2 ngày…” → `location_focus=Hội An`, không clarification, locality ratio 1.0, committed.
2. “Tôi muốn nghỉ dưỡng quanh Sơn Trà…” → `location_mode=nearby`, committed.
3. “Giữ nguyên địa điểm, chỉ tối ưu đường…” → tập attraction ID bằng nhau, travel time không tăng.
4. Constraint khả thi nhưng planner attempt 0 partial → repair rồi commit.
5. Constraint thật sự xung đột → `infeasible`, lịch cũ nguyên vẹn, nêu violation cụ thể.

## Rủi ro và cách kiểm soát

1. Groq/OpenAI-compatible endpoint có thể không hỗ trợ `tool_choice="required"` cho một model. Guard vẫn phát hiện, nhưng retry sẽ không giúp nếu provider luôn bỏ qua. Khi khởi động nên chạy capability probe; model không hỗ trợ phải được đánh dấu unavailable thay vì silently degrade.
2. Địa chỉ dataset có thể thiếu dấu hoặc thiếu cấp hành chính. `normalize_text` xử lý dấu; `nearby` xử lý thiếu address. Với `strict`, thiếu dữ liệu phải bị loại để giữ tính trung thực. Cần báo locality candidate count trong observability.
3. Medoid seed “xa nhất” có thể tạo cụm xa nơi lưu trú. Khi có start location, seed score nên cộng travel time từ hotel và giới hạn theo `max_daily_distance_km`; test benchmark sẽ phát hiện. Bước nâng cấp tiếp theo là capacitated k-medoids có hotel depot.
4. Tăng repair attempt làm tăng latency OSRM/OR-Tools. Matrix chỉ build một lần trong mỗi build nhưng mỗi attempt hiện build lại. Tối ưu sau correctness: cache matrix theo `(candidate IDs, start coordinates)` trong một request.
5. Không được tự nới hard constraint trong repair. `repair_attempt` chỉ tăng breadth/time; test snapshot request/constraints trước-sau mỗi attempt.
6. Checkpoint cùng `thread_id` có state cũ. Các field mới phải có default qua `.get`; test migration bằng checkpoint được tạo từ state thiếu field.
7. Đổi cách reset depot từng ngày làm metric thấp hơn và đúng semantics “khách sạn mỗi ngày”, nhưng có thể đổi snapshot test hiện hữu. Nếu sản phẩm thực sự muốn hành trình liên tục nhiều ngày, thêm explicit `continuous_route` thay vì ngầm dùng điểm cuối hôm trước.

## Lệnh kiểm chứng theo thứ tự

```powershell
.\myenv\Scripts\python.exe -m pytest tests/test_locality.py tests/test_agent_graph.py tests/test_agent_tools.py tests/test_langgraph_assistant_service.py
.\myenv\Scripts\python.exe -m pytest tests/test_route_optimizer.py tests/test_itinerary_validator.py tests/test_agent_quality_benchmark.py
.\myenv\Scripts\python.exe -m pytest
.\myenv\Scripts\python.exe -m scripts.benchmark_recommendation
.\myenv\Scripts\python.exe -m scripts.benchmark_agent_quality --case hoi_an_autoplan_without_clarification
.\myenv\Scripts\python.exe -m scripts.benchmark_agent_quality
```

Quality gate trước merge:

- Unit/integration hiện hữu đều xanh.
- 100% mutation benchmark có `tool_calls>=1`; không case nào `completed` với `committed=false`.
- Hội An strict locality ratio = 1.0; Sơn Trà theo mode của case.
- Feasible partial tự repair và commit trong tối đa 3 attempt.
- Infeasible giữ nguyên itinerary cũ và không trả chuỗi `partial`.
- Route optimization không tăng total travel time; required place/day và exclusion vẫn đúng.
- `rg -n "load_dotenv\(.*env\.example|GROQ_API_KEY=.+" .` không tìm thấy runtime load hoặc secret value.

## Thứ tự triển khai

1. Secret/config và terminal-state invariant.
2. Tool-required model binding + guard.
3. Locality resolver/schema/filter/validator.
4. Repair loop hữu hạn.
5. Route-time partition và depot semantics.
6. Unit/integration full suite.
7. Chạy từng live benchmark để tiết kiệm quota; chỉ chạy toàn bộ khi các case đại diện đã xanh.

Phương án này ưu tiên sửa correctness tại boundary trước, rồi mới cải thiện planner. Nó giữ LLM làm reasoning/tool selection, còn harness chỉ thực thi, verify, retry hữu hạn và công bố trạng thái có bằng chứng.
