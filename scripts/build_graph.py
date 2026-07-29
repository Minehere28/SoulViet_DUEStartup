import argparse
import json
from itertools import combinations
from pathlib import Path

import pandas as pd
import torch

from utils.distance import haversine


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = PROJECT_ROOT / "new_data_soulviet" / "new_data.csv"
DEFAULT_OUTPUT = PROJECT_ROOT / "graph.pt"

REQUIRED_COLUMNS = {
    "Id",
    "Name",
    "Type",
    "AllTypes",
    "Address",
    "Lat",
    "Lng",
    "RatingScore",
    "ReviewCount",
    "OperationHours",
    "OpeningHours_JSON",
    "OpeningHoursStatus",
    "OpeningHoursNeedsReview",
    "OpeningHoursVerificationStatus",
    "VisitDurationMinutes",
    "VisitDurationSource",
    "VisitDurationConfidence",
    "Description",
    "Activities",
    "TopReviews",
    "VibeTag",
    "MainImage",
    "LandImages_JSON",
}

QUANG_NAM_PLACES = (
    "hội an",
    "tây giang",
    "tam kỳ",
    "điện bàn",
    "phú ninh",
    "duy xuyên",
    "nam trà my",
    "thăng bình",
    "đông giang",
    "đại lộc",
    "quế sơn",
    "tiên phước",
    "hiệp đức",
    "nông sơn",
    "bắc trà my",
    "phước sơn",
    "nam giang",
)

ACTIVITY_TAXONOMY = {
    "Ẩm thực": (
        "ẩm thực", "ăn", "món", "đặc sản", "bánh", "hải sản",
        "buffet", "nấu",
    ),
    "Cà phê & Đồ uống": (
        "cà phê", "cafe", "trà", "đồ uống", "cocktail", "rượu",
        "bia", "bartender",
    ),
    "Chụp ảnh & Check-in": (
        "chụp", "check-in", "check in", "sống ảo",
    ),
    "Văn hóa & Lịch sử": (
        "văn hóa", "lịch sử", "di tích", "bảo tàng", "truyền thống",
        "kiến trúc", "di sản",
    ),
    "Làng nghề & Thủ công": (
        "làng nghề", "thủ công", "làm gốm", "dệt", "nghề mộc",
        "đèn lồng", "chế tác", "tự tay làm",
    ),
    "Thiên nhiên & Ngắm cảnh": (
        "ngắm", "cảnh", "thiên nhiên", "hoàng hôn", "bình minh",
        "không khí", "vườn", "núi", "rừng", "hang động",
    ),
    "Biển & Hoạt động dưới nước": (
        "tắm biển", "tắm suối", "bơi", "lặn", "chèo thuyền",
        "kayak", "lướt sóng", "biển",
    ),
    "Ngoài trời & Phiêu lưu": (
        "trek", "leo", "đi bộ", "dạo bộ", "đi dạo", "đạp xe",
        "phượt", "cắm trại", "câu cá", "thể thao", "zipline",
    ),
    "Thư giãn & Chăm sóc sức khỏe": (
        "thư giãn", "chữa lành", "spa", "thiền", "yoga",
        "nghỉ ngơi", "làm mới bản thân", "massage",
    ),
    "Mua sắm & Quà lưu niệm": (
        "mua", "mua sắm", "quà", "lưu niệm",
    ),
    "Tâm linh & Tín ngưỡng": (
        "tín ngưỡng", "tâm linh", "cầu bình an", "cầu nguyện",
        "thắp hương", "hành hương", "lễ phật",
    ),
    "Nghệ thuật & Biểu diễn": (
        "nghệ thuật", "âm nhạc", "nhạc", "biểu diễn", "triển lãm",
        "múa", "hát",
    ),
    "Giải trí & Vui chơi": (
        "vui chơi", "giải trí", "trò chơi", "xem phim", "công viên",
    ),
    "Học tập & Làm việc": (
        "học", "tìm hiểu", "đọc sách", "làm việc", "workshop",
        "nghiên cứu",
    ),
    "Giao lưu & Kết nối": (
        "bạn bè", "tụ tập", "hẹn hò", "giao lưu", "trò chuyện",
        "kết nối",
    ),
    "Tham quan & Khám phá": (
        "tham quan", "thăm quan", "khám phá", "trải nghiệm",
    ),
}


def clean_text(value):
    if pd.isna(value):
        return ""
    return str(value).strip()


def clean_float(value, default=0.0):
    if pd.isna(value) or str(value).strip() == "":
        return default
    return float(value)


def clean_int(value, default=0):
    if pd.isna(value) or str(value).strip() == "":
        return default
    return int(float(value))


def clean_json_list(value):
    if pd.isna(value) or str(value).strip() == "":
        return []
    try:
        parsed = json.loads(value)
        if isinstance(parsed, str):
            parsed = json.loads(parsed)
        return parsed if isinstance(parsed, list) else []
    except (TypeError, ValueError, json.JSONDecodeError):
        return []


def clean_json_dict(value):
    if pd.isna(value) or str(value).strip() == "":
        return {}
    try:
        parsed = json.loads(value)
        if isinstance(parsed, str):
            parsed = json.loads(parsed)
        return parsed if isinstance(parsed, dict) else {}
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}


def clean_bool(value):
    if isinstance(value, bool):
        return value
    return str(value).strip().casefold() in {"true", "1", "yes"}


def infer_region(address):
    normalized_address = clean_text(address).lower()
    if (
        "quảng nam" in normalized_address
        or any(
            place in normalized_address
            for place in QUANG_NAM_PLACES
        )
    ):
        return "Quảng Nam"
    if (
        "đà nẵng" in normalized_address
        or "da nang" in normalized_address
    ):
        return "Đà Nẵng"
    if (
        "thừa thiên" in normalized_address
        or "huế" in normalized_address
    ):
        return "Thừa Thiên Huế"
    return ""


def classify_activities(activities):
    categories = set()
    for activity in activities:
        normalized_activity = clean_text(activity).lower()
        for category, keywords in ACTIVITY_TAXONOMY.items():
            if any(
                keyword in normalized_activity
                for keyword in keywords
            ):
                categories.add(category)

    if not categories and activities:
        categories.add("Trải nghiệm khác")
    return sorted(categories)


def validate_dataframe(dataframe):
    missing_columns = REQUIRED_COLUMNS - set(dataframe.columns)
    if missing_columns:
        raise ValueError(
            f"CSV is missing required columns: {sorted(missing_columns)}"
        )
    if dataframe["Id"].isna().any():
        raise ValueError("CSV contains missing Id values")
    if dataframe["Id"].duplicated().any():
        duplicates = dataframe.loc[dataframe["Id"].duplicated(), "Id"].tolist()
        raise ValueError(f"CSV contains duplicate Id values: {duplicates[:5]}")
    if dataframe[["Lat", "Lng"]].isna().any().any():
        raise ValueError("CSV contains missing Lat/Lng values")
    if not dataframe["Lat"].between(-90, 90).all():
        raise ValueError("CSV contains invalid latitude values")
    if not dataframe["Lng"].between(-180, 180).all():
        raise ValueError("CSV contains invalid longitude values")

    missing_region = dataframe[
        dataframe["Address"].map(infer_region).eq("")
    ]
    if not missing_region.empty:
        examples = missing_region["Address"].head(5).tolist()
        raise ValueError(
            f"Cannot infer Region for {len(missing_region)} places: {examples}"
        )


def create_nodes(dataframe):
    nodes = {}
    for row in dataframe.to_dict("records"):
        place_id = clean_text(row["Id"])
        activities = clean_json_list(row.get("Activities"))
        nodes[place_id] = {
            "id": place_id,
            "google_place_id": clean_text(row.get("PlaceId")),
            "name": clean_text(row.get("Name")),
            "type": clean_text(row.get("Type")),
            "all_types": clean_json_list(row.get("AllTypes")),
            "address": clean_text(row.get("Address")),
            "region": infer_region(row.get("Address")),
            "lat": clean_float(row.get("Lat")),
            "lng": clean_float(row.get("Lng")),
            "rating": clean_float(row.get("RatingScore")),
            "review_count": clean_int(row.get("ReviewCount")),
            "operation_hours": clean_text(row.get("OperationHours")),
            "opening_hours": clean_json_dict(
                row.get("OpeningHours_JSON")
            ),
            "opening_hours_status": clean_text(
                row.get("OpeningHoursStatus")
            ),
            "opening_hours_needs_review": clean_bool(
                row.get("OpeningHoursNeedsReview")
            ),
            "opening_hours_verification_status": clean_text(
                row.get("OpeningHoursVerificationStatus")
            ),
            "visit_duration_minutes": clean_int(
                row.get("VisitDurationMinutes"),
                default=90,
            ),
            "visit_duration_source": clean_text(
                row.get("VisitDurationSource")
            ),
            "visit_duration_confidence": clean_text(
                row.get("VisitDurationConfidence")
            ),
            "description": clean_text(row.get("Description")),
            "activities": activities,
            "activity_categories": classify_activities(activities),
            "reviews": clean_json_list(row.get("TopReviews")),
            "vibes": [clean_text(row.get("VibeTag"))]
            if clean_text(row.get("VibeTag"))
            else [],
            "main_image": clean_text(row.get("MainImage")),
            "images": clean_json_list(row.get("LandImages_JSON")),
        }
    return nodes


def create_near_edges(nodes, threshold_km):
    adjacency = {place_id: [] for place_id in nodes}
    for first, second in combinations(nodes.values(), 2):
        distance = haversine(
            first["lat"],
            first["lng"],
            second["lat"],
            second["lng"],
        )
        if distance > threshold_km:
            continue

        rounded_distance = round(distance, 3)
        adjacency[first["id"]].append(
            {"to": second["id"], "distance": rounded_distance}
        )
        adjacency[second["id"]].append(
            {"to": first["id"], "distance": rounded_distance}
        )
    return adjacency


def build_graph(input_path, output_path, threshold_km=2.0):
    dataframe = pd.read_csv(input_path)
    validate_dataframe(dataframe)

    nodes = create_nodes(dataframe)
    near = create_near_edges(nodes, threshold_km)
    edge_count = sum(len(neighbors) for neighbors in near.values())

    graph = {
        "metadata": {
            "schema_version": 3,
            "source": str(Path(input_path).resolve()),
            "node_count": len(nodes),
            "near_edge_count": edge_count,
            "near_threshold_km": threshold_km,
            "activity_taxonomy_version": 1,
            "activity_category_count": len(ACTIVITY_TAXONOMY) + 1,
            "opening_hours_parser_version": 1,
            "opening_hours_unknown_count": sum(
                node["opening_hours_status"] == "unknown"
                for node in nodes.values()
            ),
            "opening_hours_needs_review_count": sum(
                node["opening_hours_needs_review"]
                for node in nodes.values()
            ),
        },
        "nodes": nodes,
        "edges": {"near": near},
    }
    torch.save(graph, output_path)
    return graph


def parse_args():
    parser = argparse.ArgumentParser(
        description="Build graph.pt directly from SoulViet new_data.csv"
    )
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--threshold-km", type=float, default=2.0)
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    graph_data = build_graph(args.input, args.output, args.threshold_km)
    print(f"Created: {args.output.resolve()}")
    print(f"Nodes: {graph_data['metadata']['node_count']}")
    print(
        "Directed NEAR edges: "
        f"{graph_data['metadata']['near_edge_count']}"
    )
    print(
        "Threshold: "
        f"{graph_data['metadata']['near_threshold_km']} km"
    )
