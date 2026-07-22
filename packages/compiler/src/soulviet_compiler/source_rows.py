from __future__ import annotations

import csv
import hashlib
import io
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType

from soulviet_contracts import CompilationIssue

REQUIRED_HEADERS = (
    "Id",
    "PartnerId",
    "CategoryId",
    "PlaceId",
    "Address",
    "ProvinceId",
    "Name",
    "Type",
    "Description",
    "OperationHours",
    "Location",
    "RatingScore",
    "ReviewCount",
    "ReferencePrice",
    "AllTypes",
    "Activities",
    "TopReviews",
    "VibeTag",
    "BudgetTag",
    "AiContext",
    "CreatedAt",
    "CreatedBy",
    "LastModifiedAt",
    "LastModifiedBy",
    "MediaInfo",
)


class CsvInputError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _freeze(values: Mapping[str, str]) -> Mapping[str, str]:
    return MappingProxyType(dict(values))


@dataclass(frozen=True)
class RawSourceContext:
    source_name: str
    source_path: str
    source_sha256: str
    row_number: int
    raw_row: Mapping[str, str]

    def __post_init__(self) -> None:
        object.__setattr__(self, "raw_row", _freeze(self.raw_row))


@dataclass(frozen=True)
class RawPlaceRow:
    row_number: int
    values: Mapping[str, str]
    source: RawSourceContext
    adapter_issues: tuple[CompilationIssue, ...] = ()

    def __post_init__(self) -> None:
        frozen_values = _freeze(self.values)
        object.__setattr__(self, "values", frozen_values)
        if self.row_number != self.source.row_number:
            raise ValueError("raw row and source context row numbers must match")
        if dict(frozen_values) != dict(self.source.raw_row):
            raise ValueError("raw row values and source context must match")


class CsvPlaceRowAdapter:
    def read(
        self,
        input_path: Path,
        *,
        source_name: str,
        max_rows: int = 10,
    ) -> tuple[RawPlaceRow, ...]:
        if not source_name.strip():
            raise CsvInputError("INVALID_SOURCE_NAME", "source name must be non-empty")
        try:
            payload = input_path.read_bytes()
        except OSError as exc:
            raise CsvInputError("INPUT_UNREADABLE", "input file is missing or unreadable") from exc
        if payload.startswith(b"\xef\xbb\xbf"):
            raise CsvInputError("INVALID_UTF8_BOM", "input must be UTF-8 without a BOM")
        try:
            text = payload.decode("utf-8", errors="strict")
        except UnicodeDecodeError as exc:
            raise CsvInputError("INVALID_UTF8", "input is not valid UTF-8") from exc

        reader = csv.DictReader(io.StringIO(text, newline=""), strict=True)
        headers = reader.fieldnames
        if headers is None:
            raise CsvInputError("MISSING_HEADER", "input does not contain a CSV header")
        if len(headers) != len(set(headers)) or any(not header for header in headers):
            raise CsvInputError("INVALID_HEADER", "CSV headers must be unique and non-empty")
        missing = tuple(header for header in REQUIRED_HEADERS if header not in headers)
        if missing:
            raise CsvInputError(
                "MISSING_REQUIRED_HEADER",
                "missing required CSV header: " + ", ".join(missing),
            )
        additional = tuple(header for header in headers if header not in REQUIRED_HEADERS)
        source_sha256 = hashlib.sha256(payload).hexdigest()
        rows: list[RawPlaceRow] = []
        try:
            for row_number, parsed in enumerate(reader, start=2):
                if None in parsed or any(value is None for value in parsed.values()):
                    raise CsvInputError("MALFORMED_CSV", "CSV row width does not match its header")
                raw_row = {header: parsed[header] for header in headers}
                issues = tuple(
                    CompilationIssue(
                        code="UNREVIEWED_SOURCE_COLUMN",
                        severity="info",
                        row_number=row_number,
                        field=header,
                        message=f"Additional source column retained: {header}",
                    )
                    for header in additional
                )
                context = RawSourceContext(
                    source_name=source_name.strip(),
                    source_path=input_path.as_posix(),
                    source_sha256=source_sha256,
                    row_number=row_number,
                    raw_row=raw_row,
                )
                rows.append(
                    RawPlaceRow(
                        row_number=row_number,
                        values=raw_row,
                        source=context,
                        adapter_issues=issues,
                    )
                )
        except csv.Error as exc:
            raise CsvInputError("MALFORMED_CSV", "input contains malformed CSV") from exc

        if not 1 <= len(rows) <= max_rows:
            raise CsvInputError(
                "ROW_LIMIT",
                f"input must contain between 1 and {max_rows} data rows",
            )
        return tuple(rows)
