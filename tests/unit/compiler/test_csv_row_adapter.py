import csv
import hashlib
from pathlib import Path

import pytest
from soulviet_compiler.source_rows import (
    REQUIRED_HEADERS,
    CsvInputError,
    CsvPlaceRowAdapter,
)


def _write_csv(path: Path, headers: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)


def _blank_row(headers: list[str]) -> dict[str, str]:
    return dict.fromkeys(headers, "")


def test_adapter_builds_raw_context_without_parsing_id(tmp_path: Path) -> None:
    path = tmp_path / "invalid-id.csv"
    headers = list(REQUIRED_HEADERS)
    row = _blank_row(headers)
    row["Id"] = "not-a-uuid"
    _write_csv(path, headers, [row])
    result = CsvPlaceRowAdapter().read(path, source_name="fixture")
    assert result[0].values["Id"] == "not-a-uuid"
    assert result[0].source.raw_row["Id"] == "not-a-uuid"
    assert result[0].source.source_sha256 == hashlib.sha256(path.read_bytes()).hexdigest()


def test_adapter_accepts_and_reports_additional_headers(tmp_path: Path) -> None:
    path = tmp_path / "extra.csv"
    headers = [*REQUIRED_HEADERS, "FutureB", "FutureA"]
    row = _blank_row(headers)
    row["FutureB"] = "preserved-b"
    row["FutureA"] = "preserved-a"
    _write_csv(path, headers, [row])
    result = CsvPlaceRowAdapter().read(path, source_name="fixture")[0]
    assert result.source.raw_row["FutureB"] == "preserved-b"
    assert [issue.field for issue in result.adapter_issues] == ["FutureB", "FutureA"]
    assert {issue.code for issue in result.adapter_issues} == {"UNREVIEWED_SOURCE_COLUMN"}


def test_adapter_rejects_missing_header(tmp_path: Path) -> None:
    path = tmp_path / "missing.csv"
    headers = list(REQUIRED_HEADERS[:-1])
    _write_csv(path, headers, [_blank_row(headers)])
    with pytest.raises(CsvInputError, match="missing required CSV header") as caught:
        CsvPlaceRowAdapter().read(path, source_name="fixture")
    assert caught.value.code == "MISSING_REQUIRED_HEADER"


def test_adapter_enforces_row_limit(tmp_path: Path) -> None:
    path = tmp_path / "too-many.csv"
    headers = list(REQUIRED_HEADERS)
    _write_csv(path, headers, [_blank_row(headers) for _ in range(11)])
    with pytest.raises(CsvInputError) as caught:
        CsvPlaceRowAdapter().read(path, source_name="fixture")
    assert caught.value.code == "ROW_LIMIT"


def test_adapter_rejects_invalid_utf8_bom_and_malformed_csv(tmp_path: Path) -> None:
    invalid = tmp_path / "invalid.csv"
    invalid.write_bytes(b"\xff\xfe")
    with pytest.raises(CsvInputError) as invalid_error:
        CsvPlaceRowAdapter().read(invalid, source_name="fixture")
    assert invalid_error.value.code == "INVALID_UTF8"

    bom = tmp_path / "bom.csv"
    bom.write_bytes(b"\xef\xbb\xbf" + b",".join(header.encode() for header in REQUIRED_HEADERS))
    with pytest.raises(CsvInputError) as bom_error:
        CsvPlaceRowAdapter().read(bom, source_name="fixture")
    assert bom_error.value.code == "INVALID_UTF8_BOM"

    malformed = tmp_path / "malformed.csv"
    malformed.write_text(",".join(REQUIRED_HEADERS) + '\n"unterminated', encoding="utf-8")
    with pytest.raises(CsvInputError) as malformed_error:
        CsvPlaceRowAdapter().read(malformed, source_name="fixture")
    assert malformed_error.value.code == "MALFORMED_CSV"


def test_extracted_fixture_has_six_rows_and_original_header() -> None:
    fixture = Path("tests/fixtures/tourist_attraction_v2_compiler_fixture.csv")
    rows = CsvPlaceRowAdapter().read(fixture, source_name="fixture")
    assert len(rows) == 6
    assert tuple(rows[0].values) == REQUIRED_HEADERS
