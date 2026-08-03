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

LLM chỉ tạo intent và graph query dạng JSON đã được Pydantic kiểm tra. Backend
chọn seed node, có thể mở rộng quan hệ `NEAR` tối đa một hop, rồi tái sử dụng
OSRM và OR-Tools để tạo lịch. `ItineraryValidator` kiểm tra lại giới hạn km,
timeline, số điểm, địa điểm đóng cửa và trùng lặp trước khi LLM giải thích kết
quả. Câu hỏi về lịch hiện tại không chạy lại route planner.

Nếu OpenRouter thiếu key, timeout hoặc hết quota, các lệnh phổ biến vẫn được
nhận diện bằng rule local. `current_itinerary` là tùy chọn nhưng cần được gửi
để hiểu các tham chiếu như "điểm đầu tiên" hoặc trả lời về lịch hiện tại.

Biến môi trường tùy chọn:

```dotenv
OPENROUTER_API_KEY=...
OPENROUTER_MODEL=openrouter/free
OSRM_BASE_URL=http://router.project-osrm.org
OSRM_TIMEOUT_SECONDS=15
ROUTE_OPTIMIZER_TIME_LIMIT_MS=500
```

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
