from __future__ import annotations

import argparse
import os
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path
from typing import NoReturn

from soulviet_compiler import (
    CsvInputError,
    CsvPlaceRowAdapter,
    PlaceIRCompiler,
    build_report,
    render_report_json,
)

DEFAULT_SOURCE_NAME = "soulviet-tourist-attraction-v2-fixture"


class CliUsageError(Exception):
    pass


class StableArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        raise CliUsageError(message)


def _parser() -> StableArgumentParser:
    parser = StableArgumentParser(prog="soulviet-compile-fixture")
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--source-name", default=DEFAULT_SOURCE_NAME)
    parser.add_argument("--pretty", action="store_true")
    return parser


def _atomic_write(destination: Path, content: str) -> None:
    parent = destination.parent
    if not parent.is_dir():
        raise OSError("output parent directory does not exist")
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="",
            delete=False,
            dir=parent,
            prefix=f".{destination.name}.",
            suffix=".tmp",
        ) as handle:
            temporary_path = Path(handle.name)
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, destination)
    except OSError:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
        raise


def _stderr(code: str, message: str) -> None:
    print(f"error[{code}]: {message}", file=sys.stderr)


def main(argv: Sequence[str] | None = None) -> int:
    try:
        arguments = _parser().parse_args(argv)
    except CliUsageError:
        _stderr("CLI_USAGE", "required arguments are invalid or missing")
        return 2

    try:
        rows = CsvPlaceRowAdapter().read(
            arguments.input,
            source_name=arguments.source_name,
            max_rows=10,
        )
        compiler = PlaceIRCompiler()
        results = tuple(compiler.compile(row) for row in rows)
        report = build_report(rows, results)
        rendered = render_report_json(report, pretty=arguments.pretty)
        _atomic_write(arguments.output, rendered)
    except CsvInputError as exc:
        _stderr(exc.code, exc.message)
        return 2
    except OSError:
        _stderr("OUTPUT_ERROR", "output file could not be written atomically")
        return 2
    except Exception:
        _stderr("INTERNAL_ERROR", "compiler failed unexpectedly")
        return 2
    return 1 if report.summary.fatal_rows else 0


if __name__ == "__main__":
    raise SystemExit(main())
