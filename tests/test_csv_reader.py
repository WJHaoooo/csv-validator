"""CSV header contract tests; no data-row validation or JSON output."""

from pathlib import Path

import pytest

from csv_validator.csv_reader import (
    CSVHeaderError,
    load_csv_header,
    read_csv_header,
    validate_headers,
)
from csv_validator.schema import SchemaError, validate_schema


@pytest.fixture
def schema():
    return validate_schema({"columns": {
        "id": {"type": "int", "required": True},
        "name": {"type": "str", "required": True},
        "score": {"type": "float", "required": False},
    }})


@pytest.mark.parametrize("headers", [
    ["id", "name", "score"],
    ["id", "name"],
    ["id", "name", "city"],
    ["city", "name", "score", "id"],
])
def test_valid_headers_preserve_order_and_input(schema, headers):
    before = headers.copy()
    assert validate_headers(headers, schema) is headers
    assert headers == before


@pytest.mark.parametrize(("headers", "reason", "name"), [
    ([], "blank CSV header record", None),
    ([""], "blank CSV header name", "''"),
    (["id", " \t", "name"], "blank CSV header name", "' \\t'"),
    (["id", "name", "id"], "duplicate CSV header", "'id'"),
    (["id", "name", "city", "city"], "duplicate CSV header", "'city'"),
    (["id"], "missing required column", "'name'"),
    (["ID", "name"], "missing required column", "'id'"),
    ([" id", "name"], "missing required column", "'id'"),
    (["id ", "name"], "missing required column", "'id'"),
])
def test_invalid_headers(schema, headers, reason, name):
    with pytest.raises(CSVHeaderError) as error:
        validate_headers(headers, schema)
    assert reason in str(error.value)
    if name is not None:
        assert name in str(error.value)


def test_exact_names_are_preserved_and_not_normalized():
    schema = validate_schema({"columns": {
        " id ": {"type": "int", "required": True},
        "ID": {"type": "str", "required": True},
    }})
    headers = [" id ", "ID", "id"]
    assert validate_headers(headers, schema) == headers


def test_optional_only_schema_allows_unrelated_header():
    schema = validate_schema({"columns": {
        "score": {"type": "float", "required": False},
    }})
    assert validate_headers(["city"], schema) == ["city"]


@pytest.mark.parametrize(("content", "expected"), [
    ('id,name,city\n1,Hao,Taipei\n', ["id", "name", "city"]),
    ('id,name\r\n1,Hao\r\n', ["id", "name"]),
    ('"full,name",age\n', ["full,name", "age"]),
    ('"say ""hello""",age\n', ['say "hello"', "age"]),
    ('"full\nname",age\n', ["full\nname", "age"]),
    ('"full\r\nname",age\r\n', ["full\r\nname", "age"]),
    ('姓名,age', ["姓名", "age"]),
    (' id ,ID,id\n', [" id ", "ID", "id"]),
])
def test_reader_uses_csv_records(tmp_path, content, expected):
    source = tmp_path / "input.csv"
    source.write_bytes(content.encode("utf-8"))
    assert read_csv_header(source) == expected
    assert read_csv_header(str(source)) == expected


def test_load_valid_header_does_not_process_rows_or_write_output(tmp_path, schema):
    source = tmp_path / "input.csv"
    # A malformed later record must not be parsed or validated in Task 003A.
    content = b'id,name,city\n"unterminated data row'
    source.write_bytes(content)
    assert load_csv_header(source, schema) == ["id", "name", "city"]
    assert {path.name: path.read_bytes() for path in tmp_path.iterdir()} == {
        "input.csv": content,
    }


@pytest.mark.parametrize(("content", "reason"), [
    (b"", "empty CSV file"),
    (b"\n", "blank CSV header record"),
    (b'""\n', "blank CSV header name"),
    (b"id,,name\n", "blank CSV header name"),
    (b"id,name,\n", "blank CSV header name"),
    (b" \t\r\n", "blank CSV header name"),
    (b"id,name,id\n", "duplicate CSV header"),
    (b"id,name,city,city\n", "duplicate CSV header"),
    (b"id,Name\n", "missing required column"),
    (b"id, name\n", "missing required column"),
    (b"\xff,name\n", "invalid UTF-8"),
    (b'"id,name\n', "malformed CSV header"),
    (b'"id"x,name\n', "malformed CSV header"),
])
def test_invalid_files_include_path_and_do_not_write(tmp_path, schema, content, reason):
    source = tmp_path / "input.csv"
    source.write_bytes(content)
    with pytest.raises(CSVHeaderError) as error:
        load_csv_header(source, schema)
    assert str(source) in str(error.value)
    assert reason in str(error.value)
    assert {path.name: path.read_bytes() for path in tmp_path.iterdir()} == {
        "input.csv": content,
    }


def test_csv_file_missing(tmp_path, schema):
    source = tmp_path / "missing.csv"
    with pytest.raises(CSVHeaderError) as error:
        load_csv_header(source, schema)
    assert str(source) in str(error.value)
    assert "cannot read CSV" in str(error.value)
    assert isinstance(error.value.__cause__, FileNotFoundError)
    assert list(tmp_path.iterdir()) == []


def test_csv_read_failure(tmp_path, schema, monkeypatch):
    source = tmp_path / "input.csv"

    def deny_open(self, *args, **kwargs):
        raise PermissionError("access denied for test")

    monkeypatch.setattr(Path, "open", deny_open)
    with pytest.raises(CSVHeaderError) as error:
        load_csv_header(source, schema)
    assert str(source) in str(error.value)
    assert "access denied for test" in str(error.value)
    assert isinstance(error.value.__cause__, PermissionError)


def test_schema_is_checked_before_csv_is_opened(tmp_path, monkeypatch):
    def unexpected_open(self, *args, **kwargs):
        pytest.fail("CSV must not be opened before schema validation")

    monkeypatch.setattr(Path, "open", unexpected_open)
    with pytest.raises(SchemaError, match="missing required property"):
        load_csv_header(tmp_path / "missing.csv", {})


def test_direct_header_validation_rejects_invalid_schema():
    with pytest.raises(SchemaError, match="JSON boolean"):
        validate_headers(["id"], {
            "columns": {"id": {"type": "int", "required": "true"}},
        })


def test_fail_fast_reports_first_header_problem(schema):
    with pytest.raises(CSVHeaderError) as error:
        validate_headers(["id", "id", ""], schema)
    assert "duplicate CSV header" in str(error.value)
    assert "blank CSV header" not in str(error.value)
    assert "missing required" not in str(error.value)
