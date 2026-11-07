"""Public examples are executable acceptance fixtures for the installed CLI."""

import os
from pathlib import Path
import subprocess
import sys


EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


def run_example(csv_name, output):
    environment = os.environ.copy()
    environment["PYTHONIOENCODING"] = "utf-8"
    return subprocess.run(
        [
            sys.executable, "-m", "csv_validator.cli",
            "--csv", str(EXAMPLES / csv_name),
            "--schema", str(EXAMPLES / "schema.json"),
            "--output", str(output),
        ],
        capture_output=True, text=True, encoding="utf-8",
        env=environment, timeout=20, check=False,
    )


def test_valid_example_matches_documented_output_and_refuses_overwrite(tmp_path):
    output = tmp_path / "output.json"
    expected = (EXAMPLES / "expected.json").read_bytes()
    result = run_example("valid.csv", output)
    assert result.returncode == 0, result.stderr
    assert "Converted 3 records" in result.stdout
    assert result.stderr == ""
    assert output.read_bytes() == expected

    refused = run_example("valid.csv", output)
    assert refused.returncode == 1
    assert refused.stdout == ""
    assert "already exists" in refused.stderr
    assert output.read_bytes() == expected
    assert list(tmp_path.iterdir()) == [output]


def test_invalid_example_reports_the_documented_error_without_output(tmp_path):
    output = tmp_path / "invalid-output.json"
    result = run_example("invalid.csv", output)
    assert result.returncode == 1
    assert result.stdout == ""
    for detail in ("invalid.csv", "line 2", "'id'", "'not-an-int'", "expected int"):
        assert detail in result.stderr
    assert "Traceback" not in result.stderr
    assert list(tmp_path.iterdir()) == []
