import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

DATASET_SHA256 = "38446971E7DF40E70475CC0FDD470F448FE6F3E838427FE5C94097376089F806"


def test_installed_cli_compiles_fixture_deterministically(tmp_path: Path) -> None:
    fixture = Path("tests/fixtures/tourist_attraction_v2_compiler_fixture.csv")
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    executable = "soulviet-compile-fixture.exe" if os.name == "nt" else "soulviet-compile-fixture"
    command = Path(sys.executable).with_name(executable)
    base = [
        str(command),
        "--input",
        str(fixture),
        "--source-name",
        "soulviet-tourist-attraction-v2-fixture",
    ]
    first_run = subprocess.run(
        [*base, "--output", str(first)], capture_output=True, text=True, check=False
    )
    second_run = subprocess.run(
        [*base, "--output", str(second)], capture_output=True, text=True, check=False
    )
    assert first_run.returncode == 0, first_run.stderr
    assert second_run.returncode == 0, second_run.stderr
    assert first.read_bytes() == second.read_bytes()

    payload = json.loads(first.read_text(encoding="utf-8"))
    assert payload["report_schema_version"] == "1.0.0"
    assert payload["summary"]["input_rows"] == 6
    assert payload["summary"]["compiled_rows"] == 6
    assert payload["source"]["sha256"] == hashlib.sha256(fixture.read_bytes()).hexdigest()
    for result in payload["results"]:
        place = result["place"]
        assert place["id"] == place["provenance"]["source_record_id"]
        assert place["location"]["crs"] == "EPSG:4326"
        assert place["opening_schedule"]["days"]
        assert place["reference_price"]["kind"]

    dataset = Path("dataset/data-tourist-attraction-v2.csv")
    assert hashlib.sha256(dataset.read_bytes()).hexdigest().upper() == DATASET_SHA256
