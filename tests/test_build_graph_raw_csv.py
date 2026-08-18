import pandas as pd

from scripts.build_graph import build_graph


def test_build_graph_accepts_raw_soulviet_csv(tmp_path):
    source = tmp_path / "data-tourist-attraction.csv"
    pd.DataFrame([
        {
            "Id": "p1",
            "PartnerId": "",
            "CategoryId": "cat-1",
            "PlaceId": "ChIJexample",
            "Address": "55R4+57C, Hoà Hiệp Bắc, Liên Chiểu, Đà Nẵng, Việt Nam",
            "ProvinceId": "prov-1",
            "Name": "Bãi Sủng Cỏ",
            "Type": "tourist_attraction",
            "Description": "Bãi biển đẹp và hoang sơ.",
            "OperationHours": "Thứ Hai: 08:00–17:00 | Thứ Ba: 08:00–17:00",
            "Location": "0101000020E61000007C71F3D7F5095B40D9017C5CC0303040",
            "RatingScore": 4.5,
            "ReviewCount": 33,
            "ReferencePrice": "0đ",
            "AllTypes": '["tourist_attraction"]',
            "Activities": '["Tắm biển", "Chụp ảnh"]',
            "TopReviews": '["Rất đẹp"]',
            "VibeTag": 4,
            "BudgetTag": "Bình dân",
            "AiContext": "Tag trải nghiệm: Năng động & Phiêu lưu. Ngân sách: Bình dân",
            "CreatedAt": "2026-08-13",
            "CreatedBy": "",
            "LastModifiedAt": "2026-08-13",
            "LastModifiedBy": "",
            "MediaInfo": '{"MainImage": "https://example.com/main.jpg", "LandImages": ["https://example.com/1.jpg"]}',
        }
    ]).to_csv(source, index=False, encoding="utf-8-sig")

    output = tmp_path / "graph.pt"
    graph = build_graph(source, output)

    assert graph["metadata"]["node_count"] == 1
    assert graph["nodes"]["p1"]["id"] == "p1"
    assert graph["nodes"]["p1"]["lat"] != 0
    assert graph["nodes"]["p1"]["lng"] != 0
