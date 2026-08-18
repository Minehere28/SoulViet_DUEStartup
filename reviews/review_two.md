# Review 2 — Đối chiếu ba phương án hardening SoulViet Agent

## Kết luận ngắn

Xếp hạng đề xuất:

1. **Candidate 3** — nền tốt nhất cho harness và bounded repair, nhưng locality validator sai semantics `nearby`, allocator chưa có depot và chưa có commit guard chống route regression.
2. **Candidate 2** — graph guard rõ, locality filter/validator nhất quán hơn, nhưng bảng locality hardcode chỉ có Hội An/Sơn Trà không mở rộng được; partition có các đường `KeyError`/`IndexError`; tool đầu vẫn có thể là clarification.
3. **Candidate 1** — ý tưởng locality động và route pool đáng giữ, nhưng protocol retry như diff hiện tại không thực sự retry và có thể kết thúc ngay; repair routing khó kiểm chứng hơn hai phương án còn lại.

Không nên áp nguyên xi phương án nào. Phiên bản cuối nên lấy state/outcome, first-turn toolset và bounded workflow của Candidate 3; lấy graph guard tách node và locality predicate thống nhất của Candidate 2; lấy locality discovery động/robust center và depot reset của Candidate 1; rồi bổ sung các phần cả ba bỏ sót: chat-first creation, UI status, tenant-safe checkpoint, SQLite concurrency, violation-directed repair, route regression gate và bộ benchmark máy chấm đủ 60 câu.

## 1. Các phát hiện chung từ production

### Critical — endpoint chat chưa hỗ trợ “tự lập lịch từ prompt” khi chưa có lịch

`AssistantRequest.current_request` là field bắt buộc và giao diện chặn `customizeTrip()` nếu `currentPlanRequest` chưa tồn tại. Benchmark live hiện cũng gọi `/plan` trước rồi mới gọi `/assistant/chat`. Vì vậy ca “Tôi muốn đi Hội An 2 ngày” hiện chỉ chứng minh khả năng **sửa một plan nền**, chưa chứng minh trải nghiệm user có thể mở chat và yêu cầu tạo chuyến đi trực tiếp.

Cả ba candidate đều bỏ sót contract này. Cần chọn một trong hai thiết kế và benchmark đúng thiết kế đó:

- Cho phép `current_request: UserRequest | None`, `current_itinerary=[]`, thêm tool `create_trip` nhận trip settings đầy đủ và server cấp default rõ ràng cho `vibe`, `start_date`, giờ/ngân sách; hoặc
- UI luôn gửi một draft request từ các control hiện tại dù chưa gọi `/plan`, bỏ guard “phải tạo lịch trước”, và agent dùng `apply_trip_changes` trên draft đó.

Phương án thứ hai ít thay API hơn, nhưng phải phân biệt draft form với itinerary đã commit. Test bắt buộc phải gọi `/assistant/chat` trực tiếp, không pre-seed `/plan`.

### Critical — checkpoint không được namespace theo user

LangGraph được invoke với `configurable.thread_id = thread_id` do client tự gửi. State checkpoint có cả messages. Nếu hai user dùng cùng `thread_id`, họ có thể đọc/ghi cùng conversation checkpoint. Long-term memory có namespace `user_id`, nhưng short-term checkpoint thì không. Ba candidate không đề cập.

Phải dùng internal checkpoint key dạng hash/tuple từ cả `user_id` và `thread_id`, hoặc dùng authenticated principal thay cho `user_id` client-supplied. Không nên trả internal key ra client. Thêm test hai user cùng `thread_id` không nhìn thấy messages/state của nhau.

### High — UI vẫn hiển thị thành công giả

`static/index.html` hiện chỉ xem `payload.requires_input`; mọi trạng thái khác đều hiển thị `Đã cập nhật` màu xanh. Dù backend đã trả `infeasible`, `tool_error` hay `provider_error`, UI vẫn nói thành công. Cả ba candidate chỉ sửa service response, không sửa consumer.

UI phải map rõ `committed`, `completed` (read-only), `input_required`, `infeasible`, `tool_error`, `provider_error`, `unavailable`; chỉ render “Đã cập nhật” khi `committed`. Read-only dùng “Đã trả lời”; infeasible/error không được ghi đè `currentPlanRequest/currentItinerary` nếu response không có commit.

### High — `.env.example` có key thật và đang được runtime load

Production gọi `load_dotenv('.env.example')` ở `agent/graph.py` và `services/llm_service.py`. Kiểm tra an toàn cho thấy `GROQ_API_KEY_1` và `GROQ_API_KEY_2` đều có value dài 56 ký tự. Ba candidate đều phát hiện đúng việc phải bỏ runtime load và rotate key.

Patch cuối phải kiểm tất cả biến nhạy cảm trong file mẫu, không chỉ Groq. Key đã từng push phải revoke/rotate; xóa ở HEAD không loại nó khỏi history. Test không được in secret, chỉ assert value rỗng/placeholder và quét pattern.

### High — memory SQLite dùng shared connection nhưng chưa có chiến lược concurrency

`AgentMemory` mở một connection checkpoint và một connection store với `check_same_thread=False`; service là singleton và endpoint sync chạy trong threadpool. WAL và `busy_timeout` giúp lock contention nhưng không biến cùng connection thành transaction-safe giữa nhiều thread. Concurrent request cùng/different thread có thể xen transaction hoặc lost update.

Patch cuối cần ít nhất:

- serialize theo internal conversation key đối với cùng thread;
- connection-per-request/per-thread hoặc pool/factory thay vì dùng một raw connection chung không khóa;
- test concurrent saves và concurrent invokes;
- lifecycle `close()` qua FastAPI lifespan;
- policy prune/checkpoint retention để SQLite không tăng vô hạn.

### High — machine benchmark mới có 10 case, không phải 60

`BENCHMARK_QUESTIONS_VI.md` có 60 prompt, nhưng `agent_quality_cases.json` mới có 10 case và các ca memory/multi-turn, clarification, undo, read-only chưa được máy chấm end-to-end. Các candidate nói quality gate 60 prompt nhưng chưa thiết kế manifest/runner cho 60 case.

Trước khi tuyên bố vượt benchmark, cần chuyển 60 câu thành structured fixtures, có setup plan, nhiều turn, snapshot trước/sau và expectation typed. Live LLM benchmark có thể tách khỏi deterministic contract tests để tiết kiệm quota, nhưng báo cáo phải chỉ rõ tầng nào đã chạy.

## 2. Review Candidate 1

### Điểm mạnh

- Chẩn đoán đúng các lỗi gốc: tool call optional, locality chỉ tới cấp region, `partial` không repair, candidate bị cắt trước road matrix và status API không trung thực.
- Locality resolver động theo dữ liệu hiện hữu tốt hơn bảng alias hardcode hai locality của Candidate 2.
- Phát hiện đúng bias `current_start`: production đang dùng điểm cuối ngày N làm depot ngày N+1. Việc reset mỗi ngày về hotel (nếu có) hoặc open route độc lập là cần thiết.
- Có ý thức giới hạn OSRM pool, giữ required/day anchors và không nới hard constraint trong repair.

### Lỗi/blocker

1. **Protocol retry diff không retry.** `_call_agent()` trả `messages=[response, HumanMessage(protocol...)]`. Reducer append làm message cuối là `HumanMessage`; `_route_after_agent()` đọc message cuối, thấy không có `tool_calls` và trả `END`. Graph không quay lại agent. Ngoài ra synthetic `HumanMessage` sẽ bị lưu như lời user thật, làm hỏng history/retrieval. Phải dùng node guard + conditional edge như Candidate 2/3 hoặc `SystemMessage`, không append fake user input.
2. `must_call_tool = tool_call_count == 0` dùng counter toàn turn thì được nếu reset chắc chắn, nhưng tên field global dễ nhầm với cumulative observability. Nên tách `turn_tool_call_count` và `lifetime_tool_call_count` (nếu cần).
3. Repair node được mô tả theo hai cách (`_route_after_repair` và lambda khác), dễ tạo self-loop khó audit. Bounded loop trong một deterministic workflow helper như Candidate 3 dễ chứng minh upper bound hơn.
4. Locality strict dùng substring trên `name + address + description`. Description có thể nhắc “gần Hội An” cho một điểm ngoài Hội An, tạo false positive. `median(lat/lng)` cũng không chống được anchors nhiễu theo cụm và không xác minh parent region beyond filter input.
5. Nearby validator chỉ kiểm strict. Nếu output bị lẫn điểm ngoài bán kính ở mode nearby, validator không phát hiện độc lập, trái mục tiêu “không tin metadata”.
6. `UpdateTripInput.location_focus` không thể biểu diễn “xóa focus”. Vì args được dump `exclude_none=True`, gửi null không tới executor. Chuyển từ “Hội An” sang “toàn Quảng Nam” cùng region sẽ giữ focus cũ.
7. `_route_aware_day_pools` có thể vượt capacity khi mọi pool đầy (`choices[0]` fallback), và không trả conflict khi required count vượt capacity. Nó cũng chỉ gán toàn bộ routing pool chứ chưa có stop criterion selection theo utility.
8. Không có production gate đảm bảo `reorder_only` không làm distance/travel time tăng; mới chỉ có benchmark assertion.

## 3. Review Candidate 2

### Điểm mạnh

- Guard output là node riêng và conditional routing rõ hơn Candidate 1; không pollute messages bằng fake HumanMessage.
- Locality filter và validator dùng cùng predicate cho cả strict/nearby, tránh inconsistency lớn của Candidate 3.
- Nêu đúng việc phải chuyển `valid = not hard_violations` xuống sau khi thêm locality violations.
- Repair tăng breadth/solver budget, có terminal state và boundary invariants cụ thể.
- Route partition dùng exact OSRM minutes và yêu cầu gap filler cũng phải tuân day pool.

### Lỗi/blocker

1. `LOCALITIES` hardcode chỉ Hội An và Sơn Trà. Bộ 60 câu còn “phố cổ Huế”, “ven biển Đà Nẵng”, locality tương lai và biến thể địa danh. Đây là taxonomy seed có thể dùng làm alias fallback, không thể là source duy nhất. Nó cũng đi ngược mục tiêu dựa trên graph/MCP thay vì tiếp tục thêm luật địa danh trong code.
2. Model validator gán `self.location_focus = locality.name`. Pydantic v2 thường cho phép khi `validate_assignment=False`, nhưng pattern an toàn là `model_validator(mode='before')` canonicalize input hoặc trả `model_copy(update=...)`; cần test exact version vì requirements chưa pin.
3. `_partition_candidates_by_route` seed `pools` bằng mọi required ID dù ID không nằm trong `by_id`. Khi anchor đó được dùng làm medoid, `minutes()` truy cập `by_id[anchor]` và `KeyError`. Nếu số candidate ít hơn số ngày, `remaining[0]` gây `IndexError`.
4. Toolset required đầu vẫn chứa `ask_user_clarification`; model có thể tiếp tục né ca Hội An bằng clarification dù `tool_choice='required'`. Candidate 3 xử lý tốt hơn bằng first-turn toolset không có clarification. Clarification hợp lệ vẫn làm được sau `get_trip_state`/`search_places` observation.
5. Guard đánh dấu bất kỳ text sau khi `tool_call_count > 0` là `read_completed`. Đây là tên outcome quá rộng: tool trước có thể là memory mutation, lỗi tool, hoặc protocol sequence khác. Outcome phải dựa vào class tool/observation và postcondition, không chỉ counter.
6. `_run_planning_workflow` luôn gọi replan từ attempt 0. Nếu model/workflow trước đó đã gọi replan, dễ chạy thừa. Counter “repair_attempt_count=3” đang đếm tổng plan attempts chứ không phải 3 repairs; observability và quality gate dễ hiểu sai.
7. Repair chỉ tăng candidate breadth/solver time. Với lỗi locality, duplicate brand, missing meal hay route regression, lặp search rộng hơn không bảo đảm thay đổi strategy; có thể trả cùng itinerary ba lần.
8. Tăng OR-Tools time multiplier trên từng attempt cộng với OSRM rebuild có thể kéo request rất lâu. Không có wall-clock budget/cancellation.
9. Candidate không patch UI, chat-first API, checkpoint isolation hay SQLite concurrency.

## 4. Review Candidate 3

### Điểm mạnh

- First-turn toolset loại `ask_user_clarification`, giải trực tiếp lỗi “Hội An đủ rõ nhưng model hỏi ID”. Cách hợp lý là model đọc state/search trước rồi mới được clarification nếu thật sự thiếu tham chiếu.
- Tách `turn_tool_call_count`, `repair_count`, `outcome`, `failure_report`; reset các field per-turn; mapping service dễ audit.
- Repair deterministic nằm trong automatic mutation workflow, không gọi thêm LLM và không commit khi `acceptable=false`.
- Khi infeasible, xóa draft nhưng giữ `current_request/current_itinerary`; đây là postcondition đúng.
- Allocator có utility + travel time thay vì chỉ balanced assignment, và test đề xuất kiểm route cost có thể thắng chênh relevance nhỏ.
- Nhận diện rõ giới hạn provider `tool_choice=required`, checkpoint migration, OSRM coordinate limit và reorder-only.

### Lỗi/blocker

1. **Locality filter và validator không cùng semantics.** `nearby` filter cho phép điểm trong bán kính, nhưng validator chỉ tăng `locality_match_count` cho direct textual match. Một itinerary nearby hợp lệ có thể bị `locality_ratio_unmet`. Validator phải dùng cùng resolved boundary predicate, đồng thời báo riêng `direct_ratio` và `in_boundary_ratio`.
2. `min_locality_ratio` nằm trong public `UserRequest` dù ghi chú nói model không được chỉnh. Client vẫn có thể gửi `0`, làm tắt quality gate. Đây là server policy/config hoặc computed threshold, không nên là mutable trip field.
3. Strict mode lọc 100% direct matches nhưng validator ngưỡng 0.9, semantics mâu thuẫn. Chọn rõ: strict = 1.0 in-bound; nearby = 1.0 in-bound với metric direct ratio để báo cáo.
4. Direct match vẫn dùng description, cùng false-positive với Candidate 1. Nearby mở rộng nếu gần **bất kỳ** anchor direct nào; một anchor mô tả nhiễu tạo vòng bán kính sai. Cần ưu tiên normalized administrative locality/address; name là fallback; description không được là bằng chứng strict.
5. Allocator `_minutes()` dùng candidate `id`, chưa dùng `routing_id`. Hiện attraction thường trùng, nhưng contract matrix đang hỗ trợ alias routing ID; helper nên thống nhất với `ItineraryService._routing_id`.
6. Allocator không dùng hotel depot trong seed/insertion objective, không kiểm capacity theo visit duration/opening windows và luôn fill tới `pool_size_per_day`. OR-Tools có thể drop nhiều điểm; route-aware “selection” chưa thật sự có stop condition khi objective dương.
7. `self.allocator` được inject ở constructor nhưng build lại tạo `RouteAwareAllocator(...)`, vô hiệu dependency injection và làm unit test/mock khó hơn.
8. Repair chỉ tăng route weight. Lỗi missing meal, category minimum, empty day, duplicate brand hay required place không được sửa theo nguyên nhân; hai attempt có thể hoàn toàn giống nhau.
9. Không có commit-time monotonic guard cho reorder-only, chat-first API/UI, checkpoint tenant isolation hoặc DB concurrency.

## 5. Phương án kết hợp nên triển khai

### 5.1 Harness và terminal state

Dùng flow của Candidate 3, nhưng guard thành node độc lập như Candidate 2:

```text
retrieve -> agent(required first-tool set) -> guard
  tool calls -> execute
  no tool, retry budget còn -> agent
  no tool, hết budget -> finalize(tool_error)

execute mutation -> plan attempt 0 -> validate
  acceptable -> commit -> finalize(committed)
  unacceptable -> violation-directed repair attempt 1..N
  exhausted/deadline/same-result -> discard draft -> finalize(infeasible)

execute read -> agent(auto) -> guard -> finalize(completed)
```

Invariants bắt buộc tại service boundary:

- `committed` => `state.committed is True`, report `acceptable is True`, itinerary/request là version mới.
- mutation không commit => status không bao giờ là `completed`.
- `completed` chỉ dành cho read/memory response có observation hợp lệ.
- `input_required` chỉ khi observation của clarification tool thành công.
- error/infeasible không thay current itinerary.

Không append synthetic HumanMessage. First-turn toolset bỏ clarification; genuine ambiguity có thể gọi `get_trip_state` hoặc `search_places` trước rồi clarification ở vòng auto. `tool_choice='required'` phải có provider capability integration test; nếu provider trả 400 thì `provider_error`, không fallback keyword router.

### 5.2 Locality contract

Schema:

```text
location_focus: canonical display name | null
location_mode: strict | nearby
location_radius_km
clear_location_focus: action-only boolean (tool schema)
```

Không để client/model chỉnh `min_locality_ratio`. Resolver nên kết hợp:

1. canonical locality metadata/alias được build offline từ dataset;
2. address/admin field normalized là bằng chứng mạnh;
3. known center/boundary hoặc robust center từ address anchors cho nearby;
4. name là fallback có confidence;
5. description chỉ dùng retrieval hint, không dùng strict membership.

Unknown locality không được silently fallback cả tỉnh. Nếu graph có đủ evidence thì resolve động; nếu không, trả `locality_not_found` cụ thể. Filter và validator phải gọi cùng immutable `ResolvedLocality.contains(place)`; validator vẫn tính độc lập từ output. Metrics gồm candidate count, direct/admin match ratio, in-bound ratio, expansion radius, outside IDs, resolver confidence và source.

Khi region hoặc scope thay đổi, dọn stale `required/excluded/allowed/day anchors`. Khi user nói “toàn Quảng Nam” trong khi region vốn đã là Quảng Nam, `clear_location_focus` phải xóa focus dù region không đổi.

### 5.3 Repair thực sự hữu hạn và có mục tiêu

Giới hạn đồng thời:

- `max_repair_attempts` (đề xuất 2 repair sau initial plan);
- end-to-end wall-clock deadline;
- signature chống lặp: hash request + constraints + attraction IDs/day/order + violations. Nếu signature lặp mà strategy không đổi, dừng sớm.

Repair strategy dựa trên violation, không chỉ “chạy lại”:

- `empty_days/no_attractions` -> tăng candidate breadth trong OSRM limit, giảm optional density target hợp lý;
- `missing_required_places/day` -> force candidate and required-day pool, kiểm opening/capacity conflict;
- `required_meal_unmet` -> reserve thêm restaurant candidates đúng slot/preference và route-aware meal insertion;
- `distance_limit/timeline` -> tăng route penalty, drop remote optional, không drop required;
- `duplicate_brands/place` -> blacklist duplicate optional và refill;
- `category_constraints_unmet` -> seed quota candidates trước allocation;
- `locality_*` -> không nới strict; trả infeasible nếu data thiếu;
- reorder regression -> thử allocator/order strategy khác, nếu vẫn tệ thì giữ lịch cũ.

Mỗi attempt log strategy, matrix source, planner duration, violations before/after. Không rebuild OSRM nếu candidate/depot set không đổi; cache per-request theo coordinate hash.

### 5.4 Route-aware planner

Tạo seed pool rộng nhưng bounded, prefilter bằng locality/hard constraints/haversine rồi chỉ một OSRM table cho candidate set. Dùng capacitated medoid/insertion heuristic có:

- hotel depot cost khi có start coordinate;
- disjoint required-day anchors;
- target capacity theo cả số điểm và tổng visit-window feasibility;
- utility normalized và deterministic tie-break;
- stop criterion để không nhồi candidate utility thấp/xa;
- `routing_id` nhất quán;
- gap filler chỉ dùng pool ngày tương ứng.

Mỗi ngày reset về hotel; nếu không có hotel thì open route độc lập. Nếu sản phẩm cần continuous multi-day route, thêm field explicit thay vì ngầm nối ngày.

Đối với `reorder_only`, lưu baseline snapshot trong constraints và validate đủ ba điều trước commit:

1. attraction multiset/set không đổi;
2. total road travel minutes không tăng (distance là metric phụ);
3. hard constraints vẫn đạt.

Nếu OSRM fallback sang haversine, response/benchmark phải đánh dấu degraded. Không nên tuyên bố road-time optimization đã được chứng minh bằng fallback. Live route gate nên yêu cầu tỷ lệ OSRM thật hoặc dùng fixture matrix deterministic để đánh giá algorithm.

### 5.5 API, UI, memory và security

- Hỗ trợ chat-first plan như mục Critical đầu tiên.
- Namespace checkpoint bằng authenticated user + thread; không tin user_id raw cho isolation.
- Per-thread lock/optimistic version để hai mutation concurrent không overwrite nhau; response mang itinerary version.
- Connection lifecycle/pool cho SQLite; concurrency tests.
- UI map terminal states; chỉ update plan state/render itinerary khi committed hoặc server trả version mới hợp lệ.
- Bỏ `.env.example` runtime load, rotate keys, pin dependency versions, không trả raw exception quá chi tiết ra client.

## 6. Tests bắt buộc trước merge

### Harness/LangGraph

1. Required binding được dùng ở decision đầu; toolset đầu không có clarification.
2. Provider ignore required tool: retry đúng N, không pollute HumanMessage, kết thúc `tool_error`.
3. Read tool -> model text -> `completed`, không commit.
4. Mutation success -> đúng một commit, report acceptable.
5. Partial -> repair success; số build đúng `1 + repair_count`.
6. Repair exhausted/same signature/deadline -> infeasible, current snapshot bất biến.
7. Tool exception, malformed Pydantic args, unknown tool, tool limit và provider error map đúng status.
8. Checkpoint cũ thiếu field mới vẫn đọc được; per-turn counters reset.

### Pydantic/tool contract

1. Existing request payload không locality vẫn validate.
2. Canonicalize accent/case; reject locality-parent mismatch có reason.
3. Explicit clear locality cùng region hoạt động.
4. Null/omitted phân biệt đúng qua model dump/tool validation.
5. Unknown extra fields bị forbid ở mutation contract; fake model `bind_tools` nhận kwargs.
6. Duration giảm dọn anchors/meal/day policies; region/focus đổi dọn stale IDs.

### Locality

1. Hội An/`hoi an`, Sơn Trà, phố cổ Huế và fixture locality không hardcode.
2. Address direct match; description mention không tạo strict membership.
3. Nearby point trong/ngoài boundary; validator và filter đồng nhất.
4. Unknown/zero candidates trả reason, không fallback tỉnh.
5. Meals không làm loãng attraction ratio; outside IDs được báo.
6. Dataset integration bảo đảm đủ candidate hoặc benchmark đánh dấu infeasible hợp lệ.

### Planner/route/performance

1. Hai/ba cụm matrix nhân tạo được phân ngày đúng, deterministic khi đảo input.
2. Required-day anchor không mất/không duplicate; candidate ít hơn day count không crash.
3. Required vượt capacity trả conflict, không overflow pool.
4. Hotel depot ảnh hưởng allocation; mỗi ngày reset depot.
5. Gap filler không xuyên day pool.
6. Reorder-only bảo toàn IDs và road minutes `<= baseline`; commit guard reject regression.
7. OSRM failure/degraded source được phản ánh; no-route cell không crash.
8. Candidate count luôn trong coordinate limit, URL/table failure fallback có observability.
9. Repair cache tránh OSRM call lặp khi pool không đổi; tổng thời gian nằm trong deadline.

### API/UI/memory/concurrency/security

1. Chat-first “Hội An 2 ngày” không gọi `/plan` trước vẫn commit và không hỏi ID.
2. UI `infeasible/tool_error/provider_error` không hiện “Đã cập nhật”.
3. Hai user cùng public `thread_id` không chia sẻ checkpoint/history.
4. Hai mutation concurrent cùng conversation có version conflict/serialization, không lost update.
5. Concurrent memory save/list/forget không gây SQLite transaction error.
6. `.env.example` không secret và runtime không load; key rotation checklist được hoàn tất.

### Benchmark 60 câu

Manifest phải biểu diễn đủ 60 câu, không chỉ 10. Mỗi case cần một hoặc nhiều assertion sau:

- must-use-tool và allowed terminal status;
- commit + acceptable cho mutation khả thi;
- no clarification/ID question khi locality đủ rõ;
- location focus/mode + in-bound ratio;
- exact day/position/meal slot/reference resolution;
- exclusions, exceptions, required IDs, no duplicates;
- baseline attraction set/distance/travel/idle comparisons;
- read-only snapshot bất biến;
- multi-turn user/thread identity, pronoun resolution, memory save/retrieve/forget;
- undo: snapshot restore thật hoặc status capability-not-supported trung thực theo spec đã chọn;
- no generic `partial` và no false success.

Chạy ba tầng và ghi riêng kết quả:

1. deterministic unit/contract tests (không Groq/OSRM public);
2. integration với graph thật và stable routing fixture;
3. live Groq + OSRM smoke/quality benchmark có quota/retry report.

## 7. Quality gate cuối

- Full unit/integration suite xanh, không regression test cũ.
- 60/60 fixtures được runner đọc; mọi assertion deterministic xanh.
- Không mutation nào có status `completed`; chỉ `committed` mới là cập nhật thành công.
- Hai ca chat-first locality commit mà không hỏi ID; strict in-bound ratio 1.0, nearby in-bound ratio 1.0 và direct ratio được báo riêng.
- Repair tối đa hai lần sau initial plan, không lặp signature, không vượt deadline.
- Reorder-only giữ nguyên attraction set và road travel minutes không tăng; guard nằm trong production, không chỉ benchmark.
- Infeasible/error giữ nguyên request/itinerary/version trước đó và UI không báo thành công.
- Không cross-user checkpoint leak, không SQLite concurrency error trong stress test.
- Không runtime load `.env.example`; mọi key từng lộ đã rotate.

Với các điều kiện trên, Candidate 3 là base phù hợp nhất, nhưng chỉ sau khi sửa locality semantics và bổ sung các boundary/benchmark còn thiếu. Candidate 2 đóng góp guard node và predicate consistency; Candidate 1 đóng góp locality discovery động và depot correction. Áp nguyên xi bất kỳ candidate nào hiện tại đều chưa đủ an toàn để coi là phiên bản cuối đã kiểm chứng.
