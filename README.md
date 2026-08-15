# SoulViet DUE Startup

## Chạy dự án

```powershell
.\myenv\Scripts\Activate.ps1
python -m uvicorn app:app --reload
```

Mở:

- Web UI: <http://127.0.0.1:8000/>
- Swagger: <http://127.0.0.1:8000/docs>

## Tạo hành trình

`POST /plan`

```json
{
  "duration": 2,
  "vibe": "Chữa lành & Yên bình",
  "region": "Quảng Nam",
  "start_date": "2026-08-01",
  "day_start_time": "08:00",
  "day_end_time": "21:00",
  "max_places_per_day": 5,
  "max_daily_distance_km": 20,
  "start_lat": 16.0544,
  "start_lng": 108.2022,
  "start_name": "Khách sạn",
  "preferred_activities": ["Thiên nhiên & Ngắm cảnh"]
}
```

- `duration`: 1–14 ngày.
- `max_places_per_day`: tối đa 8; số điểm thực tế có thể ít hơn.
- `max_daily_distance_km`: lớn hơn 0 và tối đa 100 km.
- `preferred_activities`: tối đa 10 nhóm hoạt động.
- `start_lat` và `start_lng`: tùy chọn nhưng phải truyền cùng nhau. Khi có,
  OSRM sẽ tính chặng từ điểm xuất phát đến điểm tham quan đầu tiên.

Response là timeline theo ngày, gồm giờ đến/rời đi, thời lượng tham quan,
khoảng cách, cảnh báo giờ mở cửa và recommendation score có breakdown.
Khoảng cách và thời gian di chuyển được lấy từ ma trận đường bộ của OSRM
Table API. Nếu public OSRM không khả dụng hoặc không tìm thấy tuyến, response
sẽ ghi rõ `haversine_fallback` và `routing_fallback_reason`.
Mỗi ngày, tối đa 12 ứng viên khả thi được đưa vào Google OR-Tools. Thứ tự
địa điểm được tối ưu theo tổng thời gian từ ma trận OSRM, giờ mở cửa,
thời lượng tham quan, giới hạn số điểm và tổng quãng đường. Tuyến bắt đầu
từ điểm xuất phát nhưng không bắt buộc quay lại điểm đó.

Hai nhóm nhà hàng thay thế cũng được đưa trực tiếp vào cùng bài toán tối ưu:
ăn trưa `11:30-13:00` và ăn tối `18:00-19:30`. Mỗi bữa là một time window
cố định, không chiếm `max_places_per_day`; OR-Tools chọn tối đa một nhà hàng
cho mỗi bữa theo chi phí di chuyển OSRM của toàn tuyến. Timeline trả thêm
`item_type`, `meal_slot` và `meal_label`. Trạng thái giờ mở cửa `unknown` vẫn
được dùng như một giả định mềm nhưng không hiển thị cảnh báo cho người dùng.

## Tùy chỉnh bằng chatbot

`POST /assistant/chat`

```json
{
  "user_id": "user-123",
  "thread_id": "trip-da-nang-001",
  "message": "Ưu tiên biển, ít di chuyển và bỏ điểm đầu tiên ngày 1",
  "current_request": {
    "duration": 2,
    "vibe": "Chữa lành & Yên bình",
    "region": "Đà Nẵng",
    "start_date": "2026-08-01"
  },
  "current_itinerary": []
}
```

Chatbot chạy bằng LangGraph theo vòng lặp `agent → tool → observation → agent`.
`thread_id` ánh xạ tới SQLite checkpoint nên agent nhớ message, tool result và
working state qua nhiều lượt. Long-term preference memory được lưu trong
LangGraph SQLite Store theo namespace `user_id` và semantic retrieval tự động
trước mỗi lượt. Frontend mẫu tự tạo và giữ hai ID này trong `localStorage`.

Tool schema được sinh từ Pydantic. Các nhóm tool hiện có gồm đọc lịch/địa điểm,
tìm kiếm graph, cập nhật trip settings, activity/category/meal preference,
thêm/loại/thay/di chuyển/khóa địa điểm, replan, validate, commit/rollback và
quản lý memory. Model không được tự tạo place ID mà phải lấy ID qua tool tìm kiếm.

Mọi mutation chỉ ghi vào working state. `replan_itinerary` tái sử dụng graph,
OSRM và OR-Tools rồi chạy `ItineraryValidator`; `commit_itinerary` từ chối bản
nháp invalid hoặc partial. Vì vậy tool lỗi hay lịch không khả thi không ghi đè
lịch đã commit. Nếu Groq thiếu key hoặc model không hỗ trợ tool-calling,
endpoint trả `langgraph_unavailable` và không suy đoán bằng keyword.

Biến môi trường tùy chọn:

```dotenv
GROQ_API_KEY=...
GROQ_MODEL=openai/gpt-oss-20b
GROQ_REASONING_EFFORT=low
GROQ_MAX_COMPLETION_TOKENS=768
GROQ_REASONING_EFFORT=medium
OSRM_BASE_URL=http://router.project-osrm.org
OSRM_TIMEOUT_SECONDS=15
ROUTE_OPTIMIZER_TIME_LIMIT_MS=500
SOULVIET_AGENT_DB_DIR=.soulviet
```

`SOULVIET_AGENT_DB_DIR` chứa `checkpoints.sqlite3` (short-term/thread memory) và
`memories.sqlite3` (long-term user memory). Embedding retrieval bản local dùng
hash embedding deterministic, không gửi sở thích người dùng sang embedding API.

## API địa điểm và similarity động

```text
GET /places/{place_id}
GET /places/{place_id}/similar?top_k=5&same_region=true&min_score=0.1
```

Similarity được tính động từ Type (40%), Activity (35%) và Vibe (25%);
không tạo quan hệ `SIMILAR_TO`.

## Rebuild graph.pt

```powershell
python -m scripts.build_graph
```

Mặc định:

- Input: `new_data_soulviet/new_data.csv`
- Output: `graph.pt`
- Ngưỡng cạnh `NEAR`: 2 km

## Chạy benchmark gợi ý

Benchmark dùng graph thật và ma trận routing cố định để kết quả không phụ
thuộc tình trạng OSRM public:

```powershell
python -m scripts.benchmark_recommendation
```

Có thể kiểm tra lịch dài hơn, tối đa 14 ngày:

```powershell
python -m scripts.benchmark_recommendation --days 14
```

## Import Neo4j

Upsert dữ liệu:

```powershell
python -m scripts.import_to_neo4j
```

Xóa graph cũ rồi import lại:

```powershell
python -m scripts.import_to_neo4j --clear
```

`--clear` xóa toàn bộ node và relationship trong database Neo4j đang kết nối.
