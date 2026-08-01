import csv
import re
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
LEGACY_PATH = PROJECT_ROOT / "new_data_soulviet" / "data-tourist-attraction-v2.csv"
TARGET_PATH = PROJECT_ROOT / "new_data_soulviet" / "new_data.csv"

PRICE_FIELDS = [
    "EntranceFeeMin",
    "EntranceFeeMax",
    "TypicalSpendMin",
    "TypicalSpendMax",
    "PriceUnit",
    "PriceSource",
    "PriceVerifiedAt",
    "PriceConfidence",
    "PriceVerificationStatus",
]

ADMISSION_TYPES = {
    "amusement_park",
    "art_gallery",
    "historical_landmark",
    "historical_place",
    "museum",
    "tourist_attraction",
    "visitor_center",
    "zoo",
}

FREE_ENTRY_TYPES = {
    "bar",
    "beach",
    "cafe",
    "coffee_shop",
    "market",
    "park",
    "place_of_worship",
    "restaurant",
    "shopping_mall",
    "tea_house",
    "vietnamese_restaurant",
}

FALLBACK_SPEND = {
    "bar": (100_000, 300_000),
    "cafe": (35_000, 85_000),
    "coffee_shop": (35_000, 85_000),
    "market": (0, 150_000),
    "restaurant": (80_000, 250_000),
    "shopping_mall": (0, 200_000),
    "tea_house": (35_000, 100_000),
    "vietnamese_restaurant": (70_000, 220_000),
}


def parse_reference_price(value):
    normalized = (value or "").strip()
    if not normalized or normalized.casefold() == "chưa phân loại":
        return None
    amounts = [
        int(item.replace(".", ""))
        for item in re.findall(r"\d[\d.]*", normalized)
    ]
    if not amounts:
        return None
    if normalized.casefold().startswith("từ"):
        return amounts[0], amounts[0]
    if len(amounts) == 1:
        return amounts[0], amounts[0]
    return amounts[0], amounts[1]


def convert_price(legacy_row):
    place_type = (legacy_row.get("Type") or "").strip()
    parsed = parse_reference_price(legacy_row.get("ReferencePrice"))
    is_nonzero_legacy = parsed and parsed != (0, 0)

    entrance_min = entrance_max = 0
    spend_min = spend_max = 0
    source = "legacy_reference_price"
    confidence = "medium" if is_nonzero_legacy else "low"

    if is_nonzero_legacy and place_type in ADMISSION_TYPES:
        entrance_min, entrance_max = parsed
    elif is_nonzero_legacy:
        spend_min, spend_max = parsed
    elif place_type in FALLBACK_SPEND:
        spend_min, spend_max = FALLBACK_SPEND[place_type]
        source = "type_estimate"
    elif place_type not in ADMISSION_TYPES | FREE_ENTRY_TYPES:
        spend_min, spend_max = (30_000, 150_000)
        source = "type_estimate"

    return {
        "EntranceFeeMin": entrance_min,
        "EntranceFeeMax": entrance_max,
        "TypicalSpendMin": spend_min,
        "TypicalSpendMax": spend_max,
        "PriceUnit": "person",
        "PriceSource": source,
        "PriceVerifiedAt": "",
        "PriceConfidence": confidence,
        "PriceVerificationStatus": "estimated",
    }


def add_price_fields(legacy_path=LEGACY_PATH, target_path=TARGET_PATH):
    with Path(legacy_path).open(encoding="utf-8-sig", newline="") as source:
        legacy_rows = {
            row["Id"]: row
            for row in csv.DictReader(source)
        }

    with Path(target_path).open(encoding="utf-8-sig", newline="") as target:
        reader = csv.DictReader(target)
        rows = list(reader)
        original_fields = [
            field for field in reader.fieldnames if field not in PRICE_FIELDS
        ]

    missing = [row["Id"] for row in rows if row["Id"] not in legacy_rows]
    if missing:
        raise ValueError(f"Missing legacy price rows for {len(missing)} IDs")

    for row in rows:
        row.update(convert_price(legacy_rows[row["Id"]]))

    temp_path = Path(target_path).with_suffix(".csv.tmp")
    with temp_path.open("w", encoding="utf-8-sig", newline="") as target:
        writer = csv.DictWriter(target, fieldnames=original_fields + PRICE_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    temp_path.replace(target_path)
    return len(rows)


if __name__ == "__main__":
    count = add_price_fields()
    print(f"Updated {count} rows in {TARGET_PATH}")
