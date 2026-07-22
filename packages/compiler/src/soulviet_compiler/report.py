from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, fields, is_dataclass
from datetime import datetime
from uuid import UUID

from soulviet_contracts import CompilationResult

from soulviet_compiler.source_rows import RawPlaceRow

REPORT_SCHEMA_VERSION = "1.0.0"
COMPILER_VERSION = "0.1.0"


@dataclass(frozen=True)
class CompilationSummary:
    input_rows: int
    compiled_rows: int
    fatal_rows: int
    info_count: int
    warning_count: int
    error_count: int


@dataclass(frozen=True)
class CompilationReport:
    report_schema_version: str
    compiler_version: str
    source_name: str
    source_path: str
    source_sha256: str
    results: tuple[CompilationResult, ...]
    summary: CompilationSummary


def build_report(
    rows: Sequence[RawPlaceRow],
    results: Sequence[CompilationResult],
) -> CompilationReport:
    if not rows or len(rows) != len(results):
        raise ValueError("report requires one result for every input row")
    first = rows[0].source
    if any(
        row.source.source_name != first.source_name
        or row.source.source_path != first.source_path
        or row.source.source_sha256 != first.source_sha256
        for row in rows
    ):
        raise ValueError("report rows must share source metadata")
    result_tuple = tuple(results)
    all_issues = tuple(issue for result in result_tuple for issue in result.issues)
    summary = CompilationSummary(
        input_rows=len(result_tuple),
        compiled_rows=sum(result.place is not None for result in result_tuple),
        fatal_rows=sum(result.place is None for result in result_tuple),
        info_count=sum(issue.severity == "info" for issue in all_issues),
        warning_count=sum(issue.severity == "warning" for issue in all_issues),
        error_count=sum(issue.severity == "error" for issue in all_issues),
    )
    return CompilationReport(
        report_schema_version=REPORT_SCHEMA_VERSION,
        compiler_version=COMPILER_VERSION,
        source_name=first.source_name,
        source_path=first.source_path,
        source_sha256=first.source_sha256,
        results=result_tuple,
        summary=summary,
    )


def _jsonable(value: object) -> object:
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if is_dataclass(value) and not isinstance(value, type):
        return {item.name: _jsonable(getattr(value, item.name)) for item in fields(value)}
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_jsonable(item) for item in value]
    return value


def _report_payload(report: CompilationReport) -> dict[str, object]:
    return {
        "report_schema_version": report.report_schema_version,
        "compiler_version": report.compiler_version,
        "source": {
            "name": report.source_name,
            "path": report.source_path,
            "sha256": report.source_sha256,
        },
        "summary": _jsonable(report.summary),
        "results": _jsonable(report.results),
    }


def render_report_json(report: CompilationReport, *, pretty: bool) -> str:
    if pretty:
        rendered = json.dumps(
            _report_payload(report),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    else:
        rendered = json.dumps(
            _report_payload(report),
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
    return rendered + "\n"
