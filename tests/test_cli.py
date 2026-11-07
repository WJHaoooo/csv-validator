"""End-to-end CLI tests use the actual installed Python module."""

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from csv_validator import cli
from csv_validator.writer import JSONWriteError


@pytest.fixture
def files(tmp_path):
    schema = tmp_path / "schema.json"
    csv = tmp_path / "input.csv"
    output = tmp_path / "output.json"
    schema.write_text(json.dumps({"columns": {
        "id": {"type": "int", "required": True},
        "name": {"type": "str", "required": True},
        "score": {"type": "float", "required": False},
    }}), encoding="utf-8")
    csv.write_text("score,name,id,city\n95.5,小明,001,Taipei\n,Amy,2,Taichung\n80,Bob,3,Kaohsiung\n", encoding="utf-8")
    return csv, schema, output


def run_cli(*args):
    environment = os.environ.copy()
    environment["PYTHONIOENCODING"] = "utf-8"
    return subprocess.run(
        [sys.executable, "-m", "csv_validator.cli", *map(str, args)],
        capture_output=True, text=True, encoding="utf-8",
        env=environment, timeout=20, check=False,
    )


def execute(files):
    csv, schema, output = files
    return run_cli("--csv", csv, "--schema", schema, "--output", output)


def assert_failure(result, code, reason):
    assert result.returncode == code, result.stderr
    assert reason in result.stderr
    assert result.stdout == ""
    assert "Traceback" not in result.stderr


def test_end_to_end_success(files):
    csv, schema, output = files
    before = (csv.read_bytes(), schema.read_bytes())
    result = execute(files)
    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert "Converted 3 records" in result.stdout
    assert str(output) in result.stdout
    text = output.read_text(encoding="utf-8")
    data = json.loads(text)
    assert data == [
        {"id": 1, "name": "小明", "score": 95.5},
        {"id": 2, "name": "Amy", "score": None},
        {"id": 3, "name": "Bob", "score": 80.0},
    ]
    assert all(list(row) == ["id", "name", "score"] for row in data)
    assert "小明" in text and '"score": null' in text
    assert type(data[0]["id"]) is int and type(data[2]["score"]) is float
    assert (csv.read_bytes(), schema.read_bytes()) == before
    assert {p.name for p in output.parent.iterdir()} == {"input.csv", "schema.json", "output.json"}


def test_no_data_rows_writes_empty_array(files):
    csv, _, output = files
    csv.write_bytes(b"id,name\n")
    result = execute(files)
    assert result.returncode == 0, result.stderr
    assert output.read_bytes() == b"[]\n"
    assert "Converted 0 records" in result.stdout


@pytest.mark.parametrize("missing", ["--csv", "--schema", "--output"])
def test_missing_required_argument(files, missing):
    csv, schema, output = files
    values = {"--csv": csv, "--schema": schema, "--output": output}
    args = [item for flag, value in values.items() if flag != missing for item in (flag, value)]
    result = run_cli(*args)
    assert_failure(result, 2, missing)
    assert "required" in result.stderr
    assert not output.exists()


@pytest.mark.parametrize(("which", "content", "reason"), [
    ("schema", None, "cannot read schema"),
    ("schema", b"{", "JSON syntax error"),
    ("schema", b'{"columns": {}}', "non-empty object"),
    ("csv", None, "cannot read CSV"),
    ("csv", b"id,id\n", "duplicate CSV header"),
    ("csv", b"id,name\n1,\n", "required cell"),
    ("csv", b"id,name\n3.5,Amy\n", "ASCII decimal integer"),
    ("csv", b"id,name\n1,Amy,extra\n", "expected 2 fields, got 3"),
    ("csv", b"id,name\n1,Amy\n2,\xff\n", "line 3"),
])
def test_validation_failure_has_no_output(files, which, content, reason):
    csv, schema, output = files
    source = schema if which == "schema" else csv
    if content is None:
        source.unlink()
    else:
        source.write_bytes(content)
    before = {p.name: p.read_bytes() for p in output.parent.iterdir()}
    result = execute(files)
    assert_failure(result, 1, reason)
    assert str(source) in result.stderr
    assert {p.name: p.read_bytes() for p in output.parent.iterdir()} == before


def test_row_error_retains_full_diagnostics(files):
    csv, _, output = files
    csv.write_bytes(b"id,name\n1,Hao\nbad,Amy\n")
    result = execute(files)
    assert_failure(result, 1, "line 3")
    for part in (str(csv), "'id'", "'bad'", "expected int", "ASCII decimal integer"):
        assert part in result.stderr
    assert not output.exists()


def test_schema_precedes_output_and_csv_checks(files):
    csv, schema, output = files
    schema.write_bytes(b"{")
    csv.unlink()
    output.write_bytes(b"keep me")
    result = execute(files)
    assert_failure(result, 1, "JSON syntax error")
    assert output.read_bytes() == b"keep me"


@pytest.mark.parametrize("bad_csv", [False, True])
def test_existing_output_never_changes(files, bad_csv):
    csv, _, output = files
    if bad_csv:
        csv.write_bytes(b"id,name\nbad,Amy\n")
    output.write_bytes(b"existing content")
    result = execute(files)
    assert_failure(result, 1, "already exists")
    assert output.read_bytes() == b"existing content"


@pytest.mark.parametrize("which", ["csv", "schema"])
def test_output_cannot_be_input(files, which):
    csv, schema, _ = files
    target = csv if which == "csv" else schema
    before = target.read_bytes()
    result = run_cli("--csv", csv, "--schema", schema, "--output", target)
    assert_failure(result, 1, "conflicts with input")
    assert target.read_bytes() == before


def test_missing_output_directory(files):
    csv, schema, output = files
    output = output.parent / "missing" / "out.json"
    result = execute((csv, schema, output))
    assert_failure(result, 1, "output directory")
    assert not output.parent.exists()


def test_writer_failure_never_reports_success(files, monkeypatch, capsys):
    csv, schema, output = files

    def failed_writer(*args, **kwargs):
        raise JSONWriteError(f"{output}: simulated publication failure")

    monkeypatch.setattr(cli, "write_json", failed_writer)
    assert cli.main(["--csv", str(csv), "--schema", str(schema), "--output", str(output)]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "simulated publication failure" in captured.err
    assert not output.exists()


def test_unexpected_programming_error_is_not_hidden(files, monkeypatch):
    csv, schema, output = files

    def unexpected(*args, **kwargs):
        raise RuntimeError("unexpected bug")

    monkeypatch.setattr(cli, "convert_csv", unexpected)
    with pytest.raises(RuntimeError, match="unexpected bug"):
        cli.main(["--csv", str(csv), "--schema", str(schema), "--output", str(output)])
