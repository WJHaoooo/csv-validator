"""Contract and integration tests for CSV row conversion."""

import csv
import io
from pathlib import Path

import pytest

from csv_validator.converter import CSVRowError, convert_csv
from csv_validator.csv_reader import CSVHeaderError, load_csv_header
from csv_validator.schema import SchemaError, validate_schema


@pytest.fixture
def schema():
    return validate_schema({"columns": {
        "id": {"type": "int", "required": True},
        "name": {"type": "str", "required": True},
        "score": {"type": "float", "required": False},
    }})


@pytest.fixture
def write_csv(tmp_path):
    def write(headers, rows):
        path = tmp_path / "input.csv"
        with path.open("w", encoding="utf-8", newline="") as file:
            writer = csv.writer(file)
            writer.writerow(headers)
            writer.writerows(rows)
        return path
    return write


def one_column_schema(type_name, required=True):
    return validate_schema({"columns": {
        "value": {"type": type_name, "required": required},
    }})


def test_spec_example_order_and_no_output(write_csv, schema):
    path = write_csv(["score", "name", "id", "city"], [
        ["95.5", "Hao", "001", "Taipei"],
        ["", "Amy", "2", "Taichung"],
        ["80", "Bob", "3", "Kaohsiung"],
    ])
    before = path.read_bytes()
    result = convert_csv(path, schema)
    assert result == [
        {"id": 1, "name": "Hao", "score": 95.5},
        {"id": 2, "name": "Amy", "score": None},
        {"id": 3, "name": "Bob", "score": 80.0},
    ]
    assert all(list(row) == ["id", "name", "score"] for row in result)
    assert {file.name: file.read_bytes() for file in path.parent.iterdir()} == {
        "input.csv": before,
    }


@pytest.mark.parametrize(("raw", "expected"), [
    ("0", 0), ("+12", 12), ("-12", -12), ("001", 1),
    ("  -001 \t", -1),
])
def test_valid_int(write_csv, raw, expected):
    path = write_csv(["value"], [[raw]])
    result = convert_csv(path, one_column_schema("int"))
    assert result == [{"value": expected}]
    assert type(result[0]["value"]) is int


@pytest.mark.parametrize(("raw", "expected"), [
    ("12", 12.0), ("+12.5", 12.5), ("-0.25", -0.25),
    ("1e3", 1000.0), ("-2.5E-2", -0.025), ("+1e+2", 100.0),
    (".5", 0.5), ("5.", 5.0), ("-.5", -0.5), ("5.e2", 500.0),
    ("  01.50\t", 1.5),
])
def test_valid_float(write_csv, raw, expected):
    path = write_csv(["value"], [[raw]])
    result = convert_csv(path, one_column_schema("float"))
    assert result == [{"value": expected}]
    assert type(result[0]["value"]) is float


@pytest.mark.parametrize("raw", ["  Hao \t", "line1\nline2", 'a,"b"', "姓名"])
def test_str_preserves_nonempty_original(write_csv, raw):
    path = write_csv(["value"], [[raw]])
    assert convert_csv(path, one_column_schema("str")) == [{"value": raw}]


@pytest.mark.parametrize("type_name", ["int", "float", "str"])
@pytest.mark.parametrize("raw", ["", " \t\n"])
def test_optional_empty_cell_becomes_none(write_csv, type_name, raw):
    path = write_csv(["value"], [[raw]])
    assert convert_csv(path, one_column_schema(type_name, False)) == [{"value": None}]


def test_missing_optional_columns_and_ignored_extra_values(write_csv):
    schema = validate_schema({"columns": {
        "id": {"type": "int", "required": True},
        "number": {"type": "int", "required": False},
        "score": {"type": "float", "required": False},
        "name": {"type": "str", "required": False},
    }})
    path = write_csv(["city", "id"], [["", "2"], ["NaN", "1"]])
    result = convert_csv(str(path), schema)
    assert result == [
        {"id": 2, "number": None, "score": None, "name": None},
        {"id": 1, "number": None, "score": None, "name": None},
    ]
    assert list(result[0]) == ["id", "number", "score", "name"]


def test_header_only_returns_empty_list(write_csv, schema):
    path = write_csv(["id", "name"], [])
    assert convert_csv(path, schema) == []


@pytest.mark.parametrize(("type_name", "raw", "reason"), [
    *[("int", value, "ASCII decimal integer") for value in (
        "3.5", "1,000", "1_000", "0x10", "１２", "١٢", "1e3", "+", "--1", "1 2",
    )],
    *[("float", value, "decimal number") for value in (
        "NaN", "nan", "Infinity", "-inf", "1,000", "1_000", "0x1p2",
        "１２.５", "١.٢", "1e", ".", "1 2", "--1",
    )],
    ("float", "1e309", "must be finite"),
    ("float", "-1e9999", "must be finite"),
    ("int", "", "required cell"),
    ("str", " \t", "required cell"),
])
def test_invalid_values_have_diagnostics(write_csv, type_name, raw, reason):
    path = write_csv(["value"], [[raw]])
    before = path.read_bytes()
    with pytest.raises(CSVRowError) as error:
        convert_csv(path, one_column_schema(type_name))
    problem = error.value
    assert problem.path == path
    assert problem.line == 2
    assert problem.column == "value"
    assert problem.raw_value == raw
    assert problem.expected_type == type_name
    message = str(problem)
    for part in (str(path), "line 2", "'value'", repr(raw), type_name, reason):
        assert part in message
    assert {file.name: file.read_bytes() for file in path.parent.iterdir()} == {
        "input.csv": before,
    }


def test_optional_nonempty_invalid_value_is_rejected(write_csv):
    path = write_csv(["value"], [["bad"]])
    with pytest.raises(CSVRowError) as error:
        convert_csv(path, one_column_schema("float", False))
    assert error.value.raw_value == "bad"
    assert error.value.expected_type == "float"
    assert "decimal number" in str(error.value)


@pytest.mark.parametrize(("row", "actual"), [
    (["1"], 1),
    (["1", "Hao", "", "extra"], 4),
    ([], 0),
])
def test_row_width_is_checked_before_values(write_csv, schema, row, actual):
    path = write_csv(["id", "name", "score"], [row])
    with pytest.raises(CSVRowError) as error:
        convert_csv(path, schema)
    assert error.value.line == 2
    assert str(path) in str(error.value)
    assert f"expected 3 fields, got {actual}" in str(error.value)


def test_missing_extra_column_cell_still_fails(write_csv, schema):
    path = write_csv(["id", "name", "city"], [["1", "Hao"]])
    with pytest.raises(CSVRowError, match="expected 3 fields, got 2"):
        convert_csv(path, schema)


def test_trailing_delimiter_represents_optional_empty_cell(tmp_path, schema):
    path = tmp_path / "input.csv"
    path.write_bytes(b"id,name,score\n1,Hao,\n")
    assert convert_csv(path, schema) == [{"id": 1, "name": "Hao", "score": None}]


@pytest.mark.parametrize(("content", "line", "reason"), [
    (b'id,name\n1,Hao\n2,"unterminated', 3, "malformed CSV record"),
    (b'id,name\n1,Hao\n2,"Amy"x\n', 3, "malformed CSV record"),
    (b"id,name\n1,Hao\n2,\xff\n", 3, "invalid UTF-8"),
    (b'id,name\n1,"Hao\n\xff"\n', 2, "invalid UTF-8"),
])
def test_record_parsing_and_utf8_errors(tmp_path, schema, content, line, reason):
    path = tmp_path / "input.csv"
    path.write_bytes(content)
    with pytest.raises(CSVRowError) as error:
        convert_csv(path, schema)
    assert error.value.line == line
    assert str(path) in str(error.value)
    assert reason in str(error.value)
    assert error.value.__cause__ is not None
    assert path.read_bytes() == content
    assert list(tmp_path.iterdir()) == [path]


@pytest.mark.parametrize("newline", ["\n", "\r\n", "\r"])
def test_multiline_header_and_records_track_physical_start(tmp_path, newline):
    name = "full" + newline + "name"
    schema = validate_schema({"columns": {
        name: {"type": "str", "required": True},
        "id": {"type": "int", "required": True},
    }})
    content = newline.join([
        '"full', 'name",id',
        '"Hao', 'Taipei",1',
        '"Amy', 'Taichung",bad',
        "",
    ])
    path = tmp_path / "input.csv"
    path.write_bytes(content.encode("utf-8"))
    with pytest.raises(CSVRowError) as error:
        convert_csv(path, schema)
    assert error.value.line == 5
    assert error.value.column == "id"
    assert error.value.raw_value == "bad"
    assert "line 5" in str(error.value)


def test_fail_fast_does_not_consume_later_record_and_closes_file(monkeypatch, schema):
    class GuardedFile(io.StringIO):
        consumed = 0

        def __next__(self):
            self.consumed += 1
            if self.consumed > 3:
                pytest.fail("read beyond the first invalid data record")
            return super().__next__()

    file = GuardedFile("id,name\n1,Hao\nbad,Amy\n3,Bob\n")
    opens = []

    def open_once(self, *args, **kwargs):
        opens.append(self)
        return file

    monkeypatch.setattr(Path, "open", open_once)
    with pytest.raises(CSVRowError) as error:
        convert_csv("input.csv", schema)
    assert error.value.line == 3
    assert error.value.raw_value == "bad"
    assert file.consumed == 3
    assert file.closed
    assert opens == [Path("input.csv")]


def test_schema_validated_before_open(monkeypatch):
    def unexpected_open(self, *args, **kwargs):
        pytest.fail("opened CSV before validating schema")

    monkeypatch.setattr(Path, "open", unexpected_open)
    with pytest.raises(SchemaError, match="missing required property"):
        convert_csv("missing.csv", {})


@pytest.mark.parametrize(("content", "reason"), [
    (b"", "empty CSV file"),
    (b"id,id\n", "duplicate CSV header"),
    (b"id, \n", "blank CSV header"),
    (b"id,Name\n", "missing required column"),
    (b'"id"x,name\n', "malformed CSV header"),
    (b"id,\xff\n", "invalid UTF-8"),
])
def test_converter_reuses_header_contract(tmp_path, schema, content, reason):
    path = tmp_path / "input.csv"
    path.write_bytes(content)
    with pytest.raises(CSVHeaderError) as error:
        convert_csv(path, schema)
    assert str(path) in str(error.value)
    assert reason in str(error.value)


def test_header_only_reader_does_not_decode_invalid_later_record(tmp_path, schema):
    path = tmp_path / "input.csv"
    path.write_bytes(b"id,name\n1,\xff\n")
    assert load_csv_header(path, schema) == ["id", "name"]
    with pytest.raises(CSVRowError, match="line 2.*invalid UTF-8"):
        convert_csv(path, schema)


def test_converter_missing_file(tmp_path, schema):
    path = tmp_path / "missing.csv"
    with pytest.raises(CSVHeaderError) as error:
        convert_csv(path, schema)
    assert str(path) in str(error.value)
    assert isinstance(error.value.__cause__, FileNotFoundError)


def test_converter_read_failure(monkeypatch, schema):
    def denied_open(self, *args, **kwargs):
        raise PermissionError("access denied for test")

    monkeypatch.setattr(Path, "open", denied_open)
    with pytest.raises(CSVHeaderError) as error:
        convert_csv("input.csv", schema)
    assert "access denied for test" in str(error.value)
    assert isinstance(error.value.__cause__, PermissionError)
