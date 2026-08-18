# Review 1 — kiểm tra chéo ba phương án

## Kết luận

Không nên áp nguyên xi phương án nào. **Candidate 3 là nền tốt nhất** cho harness vì có `turn_tool_call_count`, bounded repair nằm trong harness, loại `ask_user_clarification` khỏi toolset bắt buộc đầu tiên và dọn draft khi infeasible. Nên kết hợp nó với:

- guard node rõ ràng của Candidate 2 (nhưng sửa cách phân loại outcome);
- nguyên tắc validator kiểm output độc lập, reset depot mỗi ngày và các test cấu hình của Candidate 1;
- locality registry/index được build từ dữ liệu, thay vì hardcode hai locality của Candidate 2 hoặc substring tự do của Candidate 1/3;
- một lớp state transaction và postcondition route mới mà cả ba phương án còn thiếu.

Security phải làm trước: `.env.example` hiện chứa hai Groq key có vẻ là key thật và runtime đang chủ động nạp file này. Không ghi lại giá trị key trong log/review; phải xóa khỏi HEAD, ngừng load, revoke/rotate và kiểm tra Git history.

## So sánh nhanh

| Hạng mục | Candidate 1 | Candidate 2 | Candidate 3 | Chọn |
|---|---|---|---|---|
| Tool-first harness | Ý đúng nhưng nhánh retry đề xuất bị kết thúc sớm | Guard node dễ kiểm thử, nhưng cho phép clarification né action và gán `read_completed` quá rộng | Tốt nhất: required binding, retry node, first-tool set không clarification | C3 + cấu trúc guard của C2 |
| Groq GPT-OSS | Có required binding và fail rõ | Có capability probe nhưng startup probe tốn quota | Có required binding và nêu provider fallback | C3; live smoke opt-in, không probe startup |
| Terminal state | Có `operation_kind`, tương đối tương thích | Enum rõ nhưng đổi API mạnh | `committed/completed/input_required/infeasible/tool_error` rõ nhất | C3 + version/legacy mapping |
| Repair | Node loop nhưng chiến lược dễ lặp vô ích | Tăng breadth/time, không xử lý theo violation | Loop gọn, tăng route weight | C3 làm khung; repair theo violation |
| Locality | Dynamic text anchors, dễ false positive | Canonical region tốt nhưng hardcode chỉ Hội An/Sơn Trà | Dynamic và scalable hơn, nhưng nearby/validator mâu thuẫn | Registry dữ liệu + fallback direct match |
| Route allocation | Balanced medoid nhưng có edge cases và hầu như vẫn cấp hết pool | Medoid đơn giản, có duplicate seed/empty candidate bug | Tách service tốt, utility rõ hơn nhưng chưa phải insertion cost | C3 sau khi sửa objective/capacity/depot |
| Draft cleanup | Có thể để lại constraint draft | Để `dirty=true` sau infeasible | Xóa draft nhưng cũng có thể xóa constraint đã commit | Không chọn; tách current/draft constraints |
| Tests | Danh sách tốt, đặc biệt config/depot | Chi tiết guard/checkpoint | Bao quát benchmark và allocator | Kết hợp cả ba |

## Bảng phát hiện theo severity

| Severity | Phát hiện | Phạm vi | Sửa bắt buộc |
|---|---|---|---|
| Critical | Runtime load `.env.example`, file đang chứa credential có vẻ thật | Production + cả 3 cùng nhận ra | Xóa load ở `agent/graph.py` và `services/llm_service.py`; placeholder rỗng; rotate/revoke; secret scan history |
| Critical | Candidate 1 retry `tool_calls=0` trả thêm `AIMessage` + `HumanMessage`, nhưng `_route_after_agent` thấy message cuối không có tool và đi `END`; không hề retry | C1 | Bỏ patch này; dùng node guard/retry như C3/C2 |
| High | Constraint đã commit và constraint draft đang dùng chung `working_constraints`. C1 có thể giữ draft hỏng; C2 để draft dirty; C3 xóa `{}` và làm mất meal/scoped/optimization constraint đã commit | Cả 3 | Thêm `current_constraints` và `draft_constraints`; mutation clone current → draft; commit promote; fail discard draft |
| High | Checkpointer chỉ key theo `thread_id`; hai user dùng cùng thread ID có thể đọc lịch/messages của nhau | Production + cả 3 bỏ sót | Namespace checkpoint bằng user ID (hash/composite), đồng thời kiểm persisted `user_id`; test cross-user isolation |
| High | Nhiều tool call trong một AI message không atomic. Một mutation thành công, mutation sau lỗi, automatic workflow vẫn có thể replan/commit phần đầu | Production + cả 3 bỏ sót | Validate toàn bộ call trước, execute trên transaction copy, chỉ merge state khi cả batch thành công; lỗi thì rollback draft và không workflow |
| High | `reorder_only` chưa có postcondition production đảm bảo cùng tập ID và route không tệ hơn baseline; benchmark không thể thay invariant runtime | Cả 3 | Snapshot baseline IDs + travel minutes/km; validator bắt exact set và objective mới `<=` baseline trước commit |
| High | Repair của cả ba không dựa trên violation nên có thể build lại gần như cùng kết quả rồi hết vòng; tăng route weight/breadth còn có thể làm rỗng ngày hoặc bỏ optional quá mức | Cả 3 | Repair policy theo mã lỗi; assert mỗi attempt thay search config/state và có progress metric; dừng sớm nếu fingerprint output lặp |
| High | Locality C2 hardcode đúng hai nơi nên thất bại với phố cổ Huế/ven biển/các locality khác; C1/C3 substring cả description dễ nhận nhầm nội dung mô tả | Cả 3 | Build locality artifact từ address/admin fields, aliases, region, centroid, confidence; name/address ưu tiên, description không là nguồn strict mặc định |
| High | C3 `nearby` filter cho phép điểm bán kính nhưng validator chỉ đếm direct match và mặc định yêu cầu 90% direct; semantics tự mâu thuẫn | C3 | Validator dùng predicate theo mode; báo riêng `direct_ratio` và `eligible_ratio`; strict hard gate, nearby hard gate theo radius |
| High | C2 khi infeasible không clear draft/dirty; lượt sau có thể kế thừa mutation thất bại từ checkpoint | C2 | Transaction state như trên; reset toàn bộ turn-local field và discard draft khi terminal |
| High | Route allocator chưa mô hình depot/return leg; current planner còn nối ngày sau từ điểm cuối ngày trước. Reset mỗi ngày đúng hơn, nhưng route mở vẫn under-report nếu thiếu hotel, và route có hotel vẫn không tính đường về | Cả 3 | Explicit `route_mode=open|return_to_start`; mỗi ngày dùng cùng depot; objective/metrics phải cùng semantics trước-sau |
| Medium | C2 guard gán `read_completed` sau bất kỳ tool nào và text; memory mutation/tool error cũng có thể bị phân loại như read | C2 | Theo dõi `operation_kind` từ tool thực tế: read, itinerary_mutation, memory_mutation, clarification |
| Medium | C2 required toolset vẫn có clarification nên model có thể né prompt Hội An bằng câu hỏi ID; C3 xử lý tốt hơn | C2 | First-decision toolset không clarification; sau read observation mới cho phép clarification |
| Medium | C1 dùng `tool_call_count == 0` thay vì counter theo lượt; dễ sai khi checkpoint merge/reset thay đổi hoặc state cũ thiếu field | C1 | Counter `turn_tool_call_count` reset rõ mỗi invoke như C3; cumulative counter đặt tên khác |
| Medium | Candidate allocators dùng khoảng cách đến member gần nhất, không phải incremental route cost; farthest-first seed có thể chọn POI utility thấp, xa depot | Cả 3 | Dùng `d(a,p)+d(p,b)-d(a,b)`/medoid objective, depot cost, capacity và deterministic local improvement |
| Medium | C2 allocator có thể chọn một required ID làm medoid của ngày khác, có thể `KeyError` nếu required ID không trong candidate, và lỗi khi số ngày lớn hơn candidate | C2 | Sanitize anchors, ownership map một ID/một ngày, handle empty/short pool, property tests |
| Medium | C3 allocator thường lấp toàn bộ capacity (`3 * max_places/day`), nên “selection” không loại remote POI; repair tăng weight chủ yếu chỉ đổi ngày | C3 | Pool budget nhỏ/adaptive; stop khi marginal objective dương; reserve required/category candidates |
| Medium | Thay region/locality chưa có contract clear locality. Field optional không phân biệt “không gửi” và “xóa focus” | Cả 3 | `clear_location_focus: bool` hoặc patch operation; đổi region tự clear focus nếu không cung cấp focus mới |
| Medium | Locality focus và parent region có thể không khớp ở C1/C3; kết quả chỉ thành rỗng/infeasible thay vì canonicalize hợp lệ | C1/C3 | Resolver trả canonical parent region; tool update atomically set cả hai hoặc trả structured conflict |
| Medium | OSRM lỗi sẽ fallback Haversine nhưng benchmark route có thể vẫn xanh; không biết tối ưu là road-time hay fallback | Cả 3 | Expose `routing_source`, fallback ratio; deterministic unit matrix; live route gate có thể yêu cầu OSRM/mixed threshold |
| Medium | Status mới của C2/C3 (`committed`, `read_completed`) có thể phá frontend/tests/API consumer đang dùng `completed` | C2/C3 | Version response hoặc giữ `status=completed` legacy và thêm `outcome`; deprecate có test contract |
| Medium | Lỗi provider/tool hiện có thể trả `str(error)` về client; có nguy cơ lộ chi tiết nội bộ | Production + cả 3 | Public error code/message whitelist; full detail chỉ structured server log có redaction |
| Medium | `tool_choice="required"` phụ thuộc khả năng Groq GPT-OSS/OpenAI-compatible endpoint; unit fake không chứng minh request thật được chấp nhận | Cả 3 | Mock HTTP contract test và opt-in live smoke cho model cấu hình; provider reject → `provider_error`, không keyword fallback |
| Low | C3 đặt `min_locality_ratio` trong public `UserRequest` rồi nói model không được chỉnh; client `/plan` vẫn chỉnh được | C3 | Đưa threshold sang server settings/validator policy, không vào request public |
| Low | Candidate 1 trả mutation committed là `completed`, giữ tương thích nhưng vẫn mơ hồ giữa read và write | C1 | Tách `status` (legacy) và `outcome`/`operation_kind` |

## Đề xuất code cho tác nhân tổng hợp

### 1. State transaction và terminal contract

Đây phải là patch đầu tiên sau security:

```python
class SoulVietAgentState(TypedDict, total=False):
    current_request: dict
    current_itinerary: list[dict]
    current_constraints: dict
    draft_request: dict | None
    draft_itinerary: list[dict] | None
    draft_constraints: dict | None
    operation_kind: str | None
    outcome: str | None
    turn_tool_call_count: int
    cumulative_tool_call_count: int
    repair_count: int
    failure_report: dict | None
```

- `apply_trip_changes` tạo bản sao deep-copy của ba `current_*` vào draft.
- Toàn bộ batch tool được validate trước rồi chạy trên local transaction.
- `commit` chỉ chạy khi `acceptable=true`, promote cả request/itinerary/constraints.
- `infeasible/tool_error` chỉ xóa draft; không xóa `current_constraints`.
- Mọi field turn-local (`outcome`, error, counters, repair report) reset trong `invoke`.
- Checkpoint config dùng ID nội bộ derived từ cả `user_id` và `thread_id`; không đưa raw value vào path/log.

### 2. Tool gate

Dùng hướng C3 nhưng triển khai qua guard node rõ như C2:

```text
agent(required tool, first-decision tools without clarification)
  -> guard
     -> tool calls: execute
     -> none, retries left: correction node -> agent
     -> exhausted: provider/tool protocol error
```

Correction node nên thêm một system/developer-style protocol reminder ngắn, không thêm `HumanMessage` giả như C1. Sau khi có observation, dùng binding `auto`. Chỉ `read` mới quay lại LLM để tổng hợp; itinerary mutation được harness finalize deterministic. Memory mutation có outcome riêng hoặc `completed` với `operation_kind=memory_mutation`.

Không startup-probe Groq vì tốn quota và tăng cold start. Thêm integration test qua mocked endpoint xác nhận payload có `tool_choice=required`, và một lệnh live smoke opt-in. Nếu provider/model từ chối, trả `provider_error` rõ ràng.

### 3. Locality contract

Không chọn hai cực hardcode hoặc substring tự do. Build artifact, ví dụ `localities.json`, từ dataset:

```json
{
  "hoi_an": {
    "display_name": "Hội An",
    "aliases": ["phố cổ hội an"],
    "region": "Quảng Nam",
    "center": [15.88, 108.34],
    "place_ids": ["..."]
  }
}
```

Resolver:

1. canonical alias exact match;
2. nếu locality chưa có registry, direct match trên normalized address/admin field và chỉ chấp nhận khi suy ra một parent region duy nhất;
3. `strict`: place ID/admin locality match;
4. `nearby`: strict anchors hoặc bán kính từ centroid;
5. không anchor: trả `locality_not_found`, không fallback cả tỉnh.

Tool update phải hỗ trợ clear focus và canonicalize parent region. Validator báo `eligible_locality_ratio` theo đúng mode, cùng `direct_locality_ratio` để quan sát; strict locality là hard violation, không chỉ quality warning.

### 4. Repair loop có chiến lược

Giữ khung C3 (`attempt 0 + tối đa 2 repair`) nhưng chọn action theo report:

- `empty_days/no_attractions`: tăng breadth trong locality, không tăng radius strict;
- `large_idle_gap`: thay optional candidate gần route hoặc tắt tail-gap filler;
- `distance_exceeded`: tăng route penalty, remove/replace optional remote POI;
- `missing_required_places/day_anchor`: reserve required trước partition, tăng solver time;
- `required_meal_unmet`: reserve meal candidates đúng slot, enforce `near_route`;
- duplicate/support/category violation: điều chỉnh candidate quota/dedup trước solve;
- hard conflict thật: dừng sớm và trả conflict cụ thể.

Lưu fingerprint `(request, constraints, selected IDs, day assignment, report)`; nếu hai attempt giống nhau thì dừng, tránh chạy OSRM/OR-Tools vô ích. Không bao giờ nới exclusion, strict locality, max distance hay bỏ required place trong repair.

### 5. Route-aware planner

Dùng service tách riêng như C3, nhưng sửa objective:

- candidate pool rộng có giới hạn OSRM;
- required/day anchors được ownership trước;
- cluster có capacity và depot-aware;
- insertion cost là phần tăng của route, không chỉ khoảng cách tới member gần nhất;
- utility gồm relevance/category/locality, trừ route cost và diversity penalty;
- gap filler và meal candidate bắt buộc tôn trọng day pool;
- mỗi ngày reset về cùng depot; khai báo rõ open route hay return-to-start;
- lưu baseline route metric trong `current_constraints` khi `reorder_only` và reject commit nếu set ID đổi hoặc travel time/km tăng.

Ưu tiên `total_travel_time_minutes` cho objective; km là metric phụ. Cache matrix trong phạm vi request theo coordinate hash để repair không gọi lại OSRM khi pool không đổi.

### 6. API compatibility

Đề xuất response chuyển tiếp:

```json
{
  "agent": {
    "status": "completed",
    "outcome": "committed",
    "operation_kind": "itinerary_mutation",
    "committed": true,
    "turn_tool_calls": 1,
    "repair_attempts": 1
  }
}
```

`status` giữ giá trị cũ cho frontend trong một phiên bản; `outcome` mới mang enum chính xác. Invariant serializer:

- `outcome=committed` ⇒ committed và acceptable;
- itinerary mutation không commit ⇒ không được `status=completed` trừ khi status chỉ là transport legacy và UI đọc outcome;
- `infeasible/tool_error/provider_error` ⇒ current snapshot bất biến;
- `input_required` ⇒ có đúng một câu hỏi rõ ràng.

## Test gaps phải bổ sung

### Unit/deterministic

- required-tool retry thật sự quay lại model; C1 regression test bắt trường hợp message cuối là Human giả.
- first toolset không có clarification; sau observation có thể clarification.
- tool batch atomic: mutation 1 thành công, mutation 2 lỗi ⇒ không commit mutation 1.
- partial → repair success; repeated identical plan → stop; exhausted → current request/itinerary/constraints nguyên vẹn.
- checkpoint cũ thiếu field mới; turn counters reset; draft không rò sang lượt sau.
- hai `user_id` dùng cùng `thread_id` không thấy message/state nhau.
- hai request đồng thời cùng thread: optimistic revision/lock ngăn lost update.
- locality alias/accent/parent region/clear focus/unknown focus; strict và nearby dùng predicate nhất quán.
- fixtures dữ liệu thật cho Hội An, Sơn Trà, phố cổ Huế và ven biển Đà Nẵng; kiểm candidate count trước khi benchmark live.
- allocator: input đảo thứ tự vẫn deterministic; `days > candidates`; anchor không nằm trong pool; một ID không vào hai ngày; capacity; depot; asymmetric matrix; gap filler không vượt pool.
- reorder-only production invariant: exact IDs và route không tăng; không chỉ evaluator ngoài API.
- OSRM fallback được đánh dấu; benchmark road-time không xanh giả trên Haversine nếu case yêu cầu OSRM.
- meal `near_route`, đúng day/slot và preference; taxonomy indoor/outdoor/spiritual false-positive fixtures.
- secret scan không in secret và không tìm runtime `.env.example` load.

### Benchmark

Hiện manifest machine-readable mới có 10 ca, còn 60 câu chủ yếu là Markdown. Cần chuyển đủ 60 thành scenario manifest, trong đó multi-turn dùng cùng user/thread và có state assertions sau từng lượt. Evaluator phải thêm:

- `turn_tool_calls > 0`;
- `outcome` đúng loại thao tác;
- mutation khả thi phải committed + acceptable;
- locality ratio lấy từ validator, không chỉ substring description;
- route so cả travel minutes và km với baseline có cùng route mode/source;
- infeasible giữ nguyên cả request, itinerary và constraints;
- cấm clarification bằng `requires_input`, không chỉ dò chuỗi “place id”;
- kiểm answer không tuyên bố thành công khi outcome lỗi.

Chạy deterministic suite trước, sau đó chỉ chạy live Groq khi các invariant đã xanh để tiết kiệm quota.

## Checklist verification trước merge

- [ ] Không còn runtime load `.env.example`; credential cũ đã rotate/revoke.
- [ ] Secret scanner không phát hiện key trong HEAD; history đã được đánh giá riêng.
- [ ] First decision gửi `tool_choice=required`; provider bỏ tool bị retry hữu hạn rồi `provider_error/tool_error`.
- [ ] Prompt Hội An đủ dữ kiện không thể chọn clarification ở quyết định đầu.
- [ ] Mutation tool batch là atomic; không commit một phần sau tool error.
- [ ] `current_constraints` và `draft_constraints` tách biệt; infeasible không mất constraint đã commit.
- [ ] Checkpoint được namespace theo user + thread và có test isolation/concurrency.
- [ ] Locality canonicalize đúng parent region; strict/nearby validator nhất quán.
- [ ] Không có fallback im lặng từ locality rỗng sang toàn tỉnh.
- [ ] Repair tối đa cấu hình, có progress/fingerprint guard và không nới hard constraint.
- [ ] Reorder-only enforce exact attraction IDs và route không tăng ngay tại commit boundary.
- [ ] Day allocator tôn trọng anchor, capacity, depot, gap filler và meal route.
- [ ] Route source/fallback được expose; so sánh baseline/final dùng cùng semantics.
- [ ] API có `outcome` trung thực và compatibility test cho `status` cũ.
- [ ] Full pytest, recommendation benchmark và 60-case deterministic benchmark xanh.
- [ ] Live Groq smoke xác nhận GPT-OSS tool calling; full live benchmark chạy sau cùng và lưu JSON report.

## Thứ tự triển khai khuyến nghị

1. Security + response terminal invariant.
2. State transaction/current-vs-draft constraints + checkpoint isolation.
3. Required-tool gate và Groq contract tests.
4. Locality artifact/schema/filter/validator.
5. Bounded repair theo violation.
6. Route-aware allocator + depot + reorder-only postcondition.
7. Chuyển đủ 60 câu sang manifest và chạy deterministic, sau đó live Groq.
