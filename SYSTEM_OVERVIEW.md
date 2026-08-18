# Tổng quan hệ thống SoulViet RAG

## 1. Mục tiêu hệ thống

SoulViet RAG là một hệ thống hỗ trợ cá nhân hóa lịch trình du lịch theo vùng miền, sở thích, ngân sách và thời gian. Hệ thống không chỉ là một bộ lọc địa điểm đơn giản, mà là một hệ thống AI + graph + planner với khả năng:

- nhận hiểu yêu cầu của người dùng
- tìm địa điểm phù hợp trong dữ liệu du lịch
- tạo lịch trình theo từng ngày
- tối ưu thứ tự đi lại
- kiểm tra logic lịch trình
- có thể điều chỉnh lại lịch trình dựa trên thay đổi yêu cầu
- lưu memory và duy trì ngữ cảnh hội thoại

Nói ngắn gọn: đây là một “travel planning assistant” chạy trên dữ liệu địa điểm Việt Nam, có tính khả dụng cao và khả năng tương tác gần gũi với người dùng.

---

## 2. Hệ thống đang làm gì thực sự?

Hệ thống có 3 tầng logic chính:

### Tầng 1: Dữ liệu nền
Dữ liệu địa điểm du lịch được lưu trong dataset và được tiền xử lý thành một graph chứa:
- ID địa điểm
- tên, loại, mô tả
- vị trí (lat/lng)
- đơn vị, giá, hoạt động, đánh giá
- hoạt động gợi ý, vibe, hình ảnh

File chính:
- new_data_soulviet/data-tourist-attraction.csv
- scripts/build_graph.py
- graph.pt

### Tầng 2: Logic nghiệp vụ
Hệ thống xử lý:
- lọc địa điểm theo vùng, vibe, ngân sách, loại địa điểm
- tính điểm phù hợp theo sở thích
- tạo itinerary theo ngày
- sắp xếp thứ tự để giảm khoảng cách di chuyển
- kiểm tra quy tắc lịch trình như số điểm tối đa/ngày, thời gian, duplication, ràng buộc loại hình

Các file trọng tâm:
- services/itinerary_service.py
- services/routing_service.py
- services/route_optimizer.py
- services/scoring_service.py
- services/filter_service.py
- services/itinerary_validator.py

### Tầng 3: AI agent layer
Mô hình AI không chỉ trả lời văn bản, mà còn gọi tool, thao tác dữ liệu và điều khiển luồng:
- nhận request từ người dùng
- đọc memory và lịch sử hội thoại
- trả về itinerary hoặc giải thích
- thực hiện chỉnh sửa lịch trình nếu người dùng yêu cầu

Các file trọng tâm:
- agent/graph.py
- agent/tools.py
- agent/memory.py
- agent/state.py
- services/langgraph_assistant_service.py

---

## 3. Luồng dữ liệu hiện tại

### 3.1 Bước 1: Đọc dữ liệu nguồn
Dữ liệu đầu vào là file CSV raw:
- new_data_soulviet/data-tourist-attraction.csv

File này chứa dữ liệu như:
- Id
- Address
- Name
- Type
- Description
- OperationHours
- Location (WKB geo)
- ReviewCount
- RatingScore
- Activities
- TopReviews
- MediaInfo
- VibeTag

### 3.2 Bước 2: Chuẩn hóa dữ liệu
scripts/build_graph.py sẽ:
- đọc file CSV
- decode Location từ WKB sang Lat/Lng
- normalize JSON fields
- parse opening hours
- loại bỏ / xử lý dữ liệu thiếu
- tính visit duration
- sinh các field cần thiết cho graph như:
  - OpeningHours_JSON
  - OpeningHoursStatus
  - OpeningHoursNeedsReview
  - VisitDurationMinutes
  - EntranceFeeMin / Max
  - TypicalSpendMin / Max
  - PriceSource / PriceConfidence

### 3.3 Bước 3: Tạo graph
Sau khi có dataset đã chuẩn hóa, hệ thống xây dựng graph theo từng địa điểm:
- mỗi node = một place
- mỗi node chứa metadata về địa điểm
- edges NEAR được tính bằng khoảng cách Haversine giữa các địa điểm
- nếu khoảng cách <= 2km thì tạo edge gần nhau

Kết quả là file graph.pt chứa:
- metadata
- nodes
- edges.near

### 3.4 Bước 4: Truy vấn / đề xuất
Khi người dùng yêu cầu đi du lịch, hệ thống:
- đọc request
- lọc địa điểm theo tiêu chí
- sắp xếp choice theo điểm đánh giá
- tạo itinerary hàng ngày
- đưa ra gợi ý phù hợp hơn hoặc dựa trên graph query

---

## 4. Logic planning hiện tại

### 4.1 UserRequest
UserRequest chứa các thông tin chính như:
- duration: số ngày
- region: vùng muốn đi
- vibe: cảm giác mong muốn (yên bình, năng động, văn hóa...)
- budget: ngân sách
- start_date
- start_lat / start_lng (nếu có)
- excluded_place_ids / excluded_place_types
- max_places_per_day

File:
- models/user_request.py

### 4.2 ItineraryService
This is trung tâm của logic “lên lịch”. Nó tạo ít nhất các thành phần sau:
- xây dựng danh sách candidate places
- lọc theo vùng và loại địa điểm
- chọn địa điểm phù hợp
- tính khoảng cách / thời gian di chuyển
- tối ưu thứ tự đi qua các điểm
- kiểm tra ngày nào còn chỗ, ngày nào thừa / thiếu

Logic này nằm ở:
- services/itinerary_service.py

### 4.3 ItineraryValidator
Sau khi build itinerary, hệ thống chạy validator để kiểm tra:
- có quá nhiều điểm trong một ngày không
- có điểm trùng lặp không
- liệu lịch trình còn đang đúng giờ / đúng khoảng cách không
- liệu có thiếu loại địa điểm cần thiết không
- liệu có ràng buộc về category / nội dung không

Nếu vi phạm, hệ thống sẽ cố gắng sửa hoặc báo lỗi.

---

## 5. Logic score / matching

Dữ liệu địa điểm được chấm điểm dựa trên nhiều yếu tố:
- vùng địa lý
- loại địa điểm
- hoạt động / nội dung mô tả
- vibe
- budget
- đánh giá người dùng
- khoảng cách so với user start point

Các file quan trọng:
- services/scoring_service.py
- services/similarity_service.py
- services/filter_service.py

Mục tiêu là trả về một danh sách địa điểm có độ phù hợp cao nhất với yêu cầu của người dùng.

---

## 6. Logic graph và Neo4j

Hệ thống có 2 cách lưu trữ và truy vấn dữ liệu:

### Cách 1: Graph local dạng .pt
- được sinh bởi scripts/build_graph.py
- lưu trong file graph.pt
- dùng cho recommendation nhanh, offline

### Cách 2: Neo4j graph
- import bằng scripts/import_to_neo4j.py
- export bằng scripts/export_to_pt.py
- dùng cho truy vấn quan hệ như:
  - same region
  - similar places
  - node relationships

Trong Neo4j, các node có thể liên kết như:
- Place
- Type
- Vibe
- Activity
- Region

và có mối quan hệ như:
- NEAR
- HAS_TYPE
- HAS_VIBE
- SUPPORTS_ACTIVITY
- LOCATED_IN

---

## 7. Agent hiện tại hoạt động như thế nào?

Agent ở đây không chỉ là chatbot đơn thuần. Nó là một “orchestrator” điều phối nhiều bước.

### 7.1 agent/graph.py
Đây là file quan trọng nhất về workflow AI:
- nhận user message
- khởi tạo lịch trình
- truy xuất memory
- gọi tool để thao tác với itinerary
- cập nhật state
- trả kết quả cho người dùng

### 7.2 agent/tools.py
Tool trong agent có nhiệm vụ:
- lấy tổng quan lịch trình
- thêm / xóa điểm
- thay đổi cấu hình trip
- replan itinerary
- commit các thay đổi

### 7.3 agent/memory.py
Memory được lưu ở:
- SQLite checkpoint / memory

Chức năng:
- lưu ngữ cảnh hội thoại
- nhớ sở thích người dùng
- tái sử dụng thông tin trong các lượt hội thoại sau

---

## 8. Mô hình ra quyết định hiện tại

Hệ thống hiện tại có xu hướng làm theo pattern sau:

1. người dùng đưa request
2. request được parse ra cấu trúc chuẩn bằng model schema
3. hệ thống xây dựng candidate pool từ graph / data
4. các điểm được sắp xếp theo scoring
5. itinerary được tạo / validate
6. agent phản hồi bằng văn bản dạng tự nhiên, vừa giải thích vừa đưa lịch trình
7. nếu user yêu cầu chỉnh sửa, hệ thống chạy lại replan và commit thay đổi

Điểm mạnh: rất phù hợp cho kịch bản du lịch cá nhân hóa.
Điểm yếu: phụ thuộc nhiều vào dữ liệu dạng place và logic chính quy; nếu dữ liệu không đồng nhất có thể gây lỗi ở bước validate hoặc matching.

---

## 9. Các vấn đề / ràng buộc cần lưu ý

### 9.1 Mối quan hệ với dataset
Project có nhiều phiên bản dữ liệu:
- dataset/
- new_data_soulviet/
- new_data.csv
- data-tourist-attraction.csv

Điều này dễ gây nhầm lẫn. Hiện tại, hệ thống đang làm việc chủ yếu với file raw đã được chuẩn hóa ở:
- new_data_soulviet/data-tourist-attraction.csv

### 9.2 Bổ sung field mới cần đồng bộ nhiều nơi
Nếu bạn thêm cột mới trong CSV, cần cập nhật:
- scripts/build_graph.py
- các service đọc dữ liệu graph
- validate logic / schema

### 9.3 Graph và dữ liệu phải đồng nhất
Nếu graph được build từ file chưa chuẩn hóa, các lỗi có thể xuất hiện ở:
- thiếu Lat/Lng
- sai region
- sai ngày mở cửa
- sai estimated duration

---

## 10. Tổng kết kiến trúc ngắn gọn

Hệ thống SoulViet RAG được xây dựng theo mô hình:

```text
Raw CSV dataset
    ↓
Data normalization / enrichment
    ↓
Graph build (nodes + edges)
    ↓
Filtering + scoring + routing
    ↓
Itinerary validation
    ↓
AI agent orchestration
    ↓
User-facing travel assistant
```

Nói cách khác:

- dữ liệu là nền tảng
- graph là cấu trúc tri thức
- services là logic xử lý nghiệp vụ
- agent là lớp giao tiếp với người dùng

Đây là một hệ thống khá hoàn chỉnh cho một travel recommendation platform có tính cá nhân hóa và tương tác AI.

---

## 11. Nếu bạn muốn hiểu nhanh nhất

Bạn nên đọc theo thứ tự này:

1. [README.md](README.md)
2. [scripts/build_graph.py](scripts/build_graph.py)
3. [services/itinerary_service.py](services/itinerary_service.py)
4. [services/routing_service.py](services/routing_service.py)
5. [agent/graph.py](agent/graph.py)
6. [agent/tools.py](agent/tools.py)
7. [models/user_request.py](models/user_request.py)

Đọc theo thứ tự trên sẽ giúp bạn nắm được logic chính của hệ thống trong khoảng 1–2 giờ.
