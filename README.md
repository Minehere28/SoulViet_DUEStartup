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
  "preferred_activities": ["Thiên nhiên & Ngắm cảnh"]
}
```

- `duration`: 1–14 ngày.
- `max_places_per_day`: 1–6.
- `max_daily_distance_km`: lớn hơn 0 và tối đa 100 km.
- `preferred_activities`: tối đa 10 nhóm hoạt động.

Response là timeline theo ngày, gồm giờ đến/rời đi, thời lượng tham quan,
khoảng cách, cảnh báo giờ mở cửa và recommendation score có breakdown.
Thời gian di chuyển hiện vẫn là ước tính Haversine, chưa phải routing đường bộ.

## Tùy chỉnh bằng chatbot

`POST /assistant/chat`

```json
{
  "message": "Đổi thành 3 ngày, 4 địa điểm mỗi ngày, trong 10 km",
  "current_request": {
    "duration": 2,
    "vibe": "Chữa lành & Yên bình",
    "region": "Đà Nẵng",
    "start_date": "2026-08-01"
  }
}
```

Backend nhận diện thay đổi có cấu trúc và build lại hành trình trước khi gọi
LLM. Nếu OpenRouter thiếu key, timeout hoặc hết quota, endpoint vẫn trả hành
trình cùng phản hồi local.

Biến môi trường tùy chọn:

```dotenv
OPENROUTER_API_KEY=...
OPENROUTER_MODEL=openrouter/free
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
