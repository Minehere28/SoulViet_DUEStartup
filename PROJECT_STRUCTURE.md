# Cấu trúc và mô tả dự án SoulViet RAG

## 1. Tổng quan dự án

SoulViet RAG là một hệ thống đề xuất/ hỗ trợ du lịch theo phong cách trip planner, sử dụng dữ liệu địa điểm du lịch miền Trung Việt Nam và AI/graph-based retrieval để xây dựng lịch trình cá nhân hóa.

Dự án kết hợp các thành phần chính sau:
- Bộ dữ liệu du lịch và địa điểm
- Graph dữ liệu địa lý / semantic graph
- Hệ thống truy vấn và gợi ý lịch trình
- Mô hình/agent AI để tương tác với người dùng
- Service layer xử lý itinerary, routing, scoring, filtering

Mục tiêu chính:
- Hiểu nhu cầu du lịch của người dùng
- Tìm kiếm địa điểm phù hợp theo vùng, sở thích, ngân sách, thời lượng
- Tạo lịch trình tối ưu theo thời gian và khoảng cách
- Duy trì trải nghiệm người dùng qua memory / checkpoint

---

## 2. Công nghệ chính

- Python
- FastAPI
- LangGraph
- LangChain OpenAI
- Neo4j
- Pandas / Torch
- SQLite cho memory/checkpoints
- Or-Tools cho routing / itinerary optimization

---

## 3. Cấu trúc thư mục

```text
SoulViet-RAG/
├── app.py                          # Entry point chính của ứng dụng
├── README.md                      # Tài liệu hướng dẫn chính
├── PROJECT_STRUCTURE.md           # File mô tả cấu trúc dự án
├── requirements.txt               # Danh sách dependency
├── .env.example                   # Mẫu biến môi trường
├── graph.pt                       # Graph dữ liệu đã dựng sẵn
├── graph_legacy.pt                # Graph cũ / backup
├── graph_from_neo4j.pt            # Graph export từ Neo4j
├──
├── agent/                         # Logic agent / workflow / memory / tools
│   ├── __init__.py
│   ├── graph.py                   # Graph agent orchestration
│   ├── memory.py                  # Truy xuất / lưu memory người dùng
│   ├── state.py                  # State schema cho LangGraph
│   ├── tools.py                  # Các tool cho agent
│   └── prompts/
│       └── system.md              # Prompt hệ thống của agent
├── dataset/                       # Dataset cũ / tài liệu dữ liệu cũ
│   ├── SoulViet_Dataset.csv
│   └── data-tourist-attraction.csv
├── new_data_soulviet/             # Dataset hiện đang được project dùng
│   ├── data-tourist-attraction-v2.csv
│   ├── data-tourist-attraction.csv
│   ├── new_data.csv
│   └── clean_tourist_attractions.ipynb
├── models/                        # Model dữ liệu nền tảng
│   ├── assistant_intent.py
│   ├── assistant_request.py
│   ├── place.py
│   └── user_request.py
├── services/                      # Business logic & service layer
│   ├── assistant_service.py
│   ├── budget_service.py
│   ├── data_service.py
│   ├── filter_service.py
│   ├── gap_filler_service.py
│   ├── graph_query_service.py
│   ├── graph_service.py
│   ├── itinerary_service.py
│   ├── itinerary_validator.py
│   ├── langgraph_assistant_service.py
│   ├── llm_service.py
│   ├── neo4j_service.py
│   ├── place_requirement_service.py
│   ├── route_optimizer.py
│   ├── routing_service.py
│   ├── scoring_service.py
│   ├── similarity_service.py
│   └── __init__.py
├── scripts/                       # Script hỗ trợ xử lý dữ liệu / graph
│   ├── __init__.py
│   ├── add_price_fields.py
│   ├── benchmark_recommendation.py
│   ├── build_graph.py            # Tạo graph.pt từ CSV
│   ├── export_to_pt.py           # Export graph từ Neo4j ra .pt
│   └── import_to_neo4j.py        # Import dữ liệu vào Neo4j
├── static/                        # Frontend tĩnh (nếu có web UI mock/demo)
│   └── index.html
├── tests/                         # Unit tests cho module
│   ├── test_agent_benchmark_cases.py
│   ├── test_agent_graph.py
│   ├── test_agent_memory.py
│   ├── test_agent_tools.py
│   ├── test_assistant_service.py
│   ├── test_gap_filler_service.py
│   ├── test_graph_query_service.py
│   ├── test_itinerary_validator.py
│   ├── test_langgraph_assistant_service.py
│   ├── test_llm_service.py
│   ├── test_route_optimizer.py
│   ├── test_routing_service.py
│   ├── test_user_request.py
│   └── ...
├── utils/                         # Utility helpers
│   ├── __init__.py
│   ├── distance.py
│   ├── opening_hours.py
│   ├── place_matching.py
│   ├── visit_duration.py
│   └── __init__.py
├── views/                         # View/response layer cho API/HTML
│   ├── assistant_view.py
│   ├── place_view.py
│   └── travel_view.py
└── myenv/                         # Virtual environment local
```

---

## 4. Vai trò từng phần chính

### 4.1 agent/
Thư mục quản lý AI agent, workflow và cuộc trò chuyện:
- agent.graph.py: định nghĩa agent và orchestration workflow
- agent.memory.py: lưu lịch sử / hội thoại / memory người dùng
- agent.tools.py: tool cho AI gọi các chức năng như lấy itinerary summary, apply changes, replan

### 4.2 services/
Nhóm logic nghiệp vụ quan trọng:
- itinerary_service.py: tạo và tối ưu lịch trình
- routing_service.py: tính khoảng cách / đường đi giữa các điểm đến
- route_optimizer.py: tối ưu thứ tự các địa điểm
- scoring_service.py: chấm điểm địa điểm theo nhu cầu người dùng
- filter_service.py: lọc địa điểm theo điều kiện
- graph_query_service.py: truy vấn graph dữ liệu
- neo4j_service.py: kết nối và thao tác với Neo4j

### 4.3 models/
Quản lý dữ liệu domain model:
- Place: thông tin địa điểm
- UserRequest: payload người dùng gửi lên
- AssistantRequest / AssistantIntent: request và ý định AI

### 4.4 scripts/
Dùng để xử lý và xây dựng dữ liệu nền:
- build_graph.py: tái dựng graph.pt từ CSV
- import_to_neo4j.py: import vào Neo4j
- export_to_pt.py: export graph từ Neo4j sang file .pt
- benchmark_recommendation.py: kiểm tra hiệu năng đề xuất

### 4.5 utils/
Các hàm tiện ích dùng chung như:
- tính khoảng cách giữa 2 tọa độ
- parse opening hours
- ước tính thời lượng tham quan
- normalize text và mapping địa điểm

---

## 5. Dữ liệu và flow xử lý chính

### 5.1 Dữ liệu đầu vào
Hiện project đang mặc định dùng file raw dataset:
- new_data_soulviet/data-tourist-attraction.csv

File này chứa các thông tin:
- Id, PlaceId, Name, Type
- Address, lat/lng, rating, review count
- Description, Activities, TopReviews, VibeTag
- Media, opening hours, visit duration

### 5.2 Quá trình xây dựng graph
1. Đọc CSV dataset
2. Chuẩn hóa dữ liệu
3. Giải mã WKB location thành Lat/Lng
4. Parse opening hours
5. Ước tính visit duration
6. Tạo nodes cho mỗi địa điểm
7. Tính khoảng cách gần nhau và sinh edges NEAR
8. Lưu thành graph.pt

### 5.3 Hệ thống gợi ý lịch trình
- Người dùng nhập yêu cầu: thời lượng, vùng, ngân sách, vibe, sở thích
- Hệ thống lọc điểm đến phù hợp
- Tính điểm phù hợp bằng scoring
- Chọn địa điểm và sắp xếp theo routing optimization
- Validate lịch trình và bổ sung điểm thiếu
- Trả kết quả itinerary cho người dùng

---

## 6. Dataset hiện đang sử dụng

Dự án hiện đang chủ yếu tập trung vào:

- new_data_soulviet/data-tourist-attraction.csv
- graph.pt

Điều này có nghĩa là hệ thống đang hoạt động trên dataset raw đã được chuẩn hóa theo một pipeline nhất định, thay vì dùng file dataset cũ trong thư mục dataset/ hoặc file mới_data.csv chưa được chuẩn hóa đầy đủ.

---

## 7. Các lệnh thường dùng

### Build graph
```bash
python -m scripts.build_graph
```

### Chạy ứng dụng
```bash
python app.py
```

### Chạy test
```bash
pytest
```

### Export graph từ Neo4j
```bash
python -m scripts.export_to_pt
```

---

## 8. Lưu ý khi phát triển

- Không nên sửa trực tiếp file graph.pt nếu chưa rebuild từ dữ liệu nguồn.
- Với dataset mới, cần đảm bảo cột bắt buộc có đầy đủ và format đúng.
- Khi thay đổi schema dữ liệu, cần cập nhật cả script build_graph.py và các service phụ thuộc.
- Khi dùng Neo4j, cần kiểm tra biến môi trường trong file .env.

---

## 9. Kết luận

Dự án này là một hệ thống AI du lịch tích hợp:
- dữ liệu địa điểm
- graph tri thức
- recommendation logic
- itinerary planning
- memory và conversation agent

Nó hướng đến tạo ra một trợ lý du lịch cá nhân hóa, có khả năng hiểu nhu cầu người dùng, tìm điểm đến phù hợp và tạo lịch trình tối ưu theo từng chuyến đi.
