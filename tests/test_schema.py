"""Contract tests for schema loading, parsing, and structural validation."""

import json
from pathlib import Path

import pytest

from csv_validator.schema import SchemaError, load_schema, parse_schema, validate_schema


@pytest.mark.parametrize("columns", [
    {"id": {"type": "int", "required": True}},
    {
        "id": {"type": "int", "required": True},
        "name": {"type": "str", "required": True},
        "score": {"type": "float", "required": False},
    },
    {" 姓名 ": {"type": "str", "required": False}},
])
def test_load_valid_schema(tmp_path, columns):
    expected = {"columns": columns}
    source = tmp_path / "schema.json"
    source.write_text(
        "\n  " + json.dumps(expected, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    assert load_schema(source) == expected
    assert load_schema(str(source)) == expected
    assert set(tmp_path.iterdir()) == {source}


@pytest.mark.parametrize(("data", "location", "reason"), [
    (None, "$", "expected an object"),
    ([], "$", "expected an object"),
    ("schema", "$", "expected an object"),
    (1, "$", "expected an object"),
    (True, "$", "expected an object"),
    ({}, '$["columns"]', "missing required"),
    ({"columns": {}}, '$["columns"]', "non-empty object"),
    *[({"columns": value}, '$["columns"]', "non-empty object")
      for value in (None, [], "id", 1, True)],
    ({"columns": {}, "extra": 1}, '$["extra"]', "unknown property"),
    *[({"columns": {name: {}}}, '$["columns"]', "non-blank")
      for name in ("", " ", "\t\n")],
    *[({"columns": {"id": value}}, '$["columns"]["id"]', "expected an object")
      for value in (None, [], "int", 1, True)],
    ({"columns": {"id": {}}}, '$["columns"]["id"]["type"]', "missing required"),
    ({"columns": {"id": {"type": "int"}}},
     '$["columns"]["id"]["required"]', "missing required"),
    ({"columns": {"id": {"required": True}}},
     '$["columns"]["id"]["type"]', "missing required"),
    ({"columns": {"id": {"type": "int", "required": True, "extra": 1}}},
     '$["columns"]["id"]["extra"]', "unknown property"),
    *[({"columns": {"id": {"type": value, "required": True}}},
       '$["columns"]["id"]["type"]', "expected one of")
      for value in ("INT", "Float", "bool", "", None, 1, True, [], {})],
    *[({"columns": {"id": {"type": "int", "required": value}}},
       '$["columns"]["id"]["required"]', "JSON boolean")
      for value in ("true", "false", 0, 1, None, [], {})],
])
def test_reject_invalid_structure(data, location, reason):
    with pytest.raises(SchemaError) as error:
        validate_schema(data)
    assert location in str(error.value)
    assert reason in str(error.value)


@pytest.mark.parametrize(("text", "location"), [
    ('{"columns": {}, "columns": {}}', '$["columns"]'),
    ('{"columns": {"id": {}, "id": {}}}', '$["columns"]["id"]'),
    ('{"columns": {"id": {"type": "int", "type": "str", "required": true}}}',
     '$["columns"]["id"]["type"]'),
    ('{"columns": {"id": {"type": "int", "required": true, "required": false}}}',
     '$["columns"]["id"]["required"]'),
    ('{"columns": {}, "extra": [{"key": 1, "key": 2}]}', '$["extra"][0]["key"]'),
    ('{"columns": {}, "colu\\u006dns": {}}', '$["columns"]'),
])
def test_reject_duplicate_keys(text, location):
    with pytest.raises(SchemaError) as error:
        parse_schema(text)
    assert location in str(error.value)
    assert "duplicate JSON object key" in str(error.value)


@pytest.mark.parametrize("text", [
    "", "{", '{"columns": {},}', '{"columns": {}} trailing',
    '{\n "columns": \n}',
])
def test_reject_json_syntax(text):
    with pytest.raises(SchemaError, match=r"JSON syntax error at line \d+, column \d+"):
        parse_schema(text)


@pytest.mark.parametrize("constant", ["NaN", "Infinity", "-Infinity"])
def test_reject_non_json_constants(constant):
    with pytest.raises(SchemaError, match="not a valid JSON constant"):
        parse_schema('{"columns": ' + constant + "}")


def test_load_missing_file(tmp_path):
    source = tmp_path / "missing.json"
    with pytest.raises(SchemaError) as error:
        load_schema(source)
    assert str(source) in str(error.value)
    assert "cannot read schema" in str(error.value)
    assert isinstance(error.value.__cause__, FileNotFoundError)
    assert list(tmp_path.iterdir()) == []


def test_load_read_failure(tmp_path, monkeypatch):
    source = tmp_path / "schema.json"
    source.write_text("{}", encoding="utf-8")

    def deny_read(self, *args, **kwargs):
        raise PermissionError("access denied for test")

    monkeypatch.setattr(Path, "read_text", deny_read)
    with pytest.raises(SchemaError) as error:
        load_schema(source)
    assert str(source) in str(error.value)
    assert "access denied for test" in str(error.value)
    assert isinstance(error.value.__cause__, PermissionError)
    assert set(tmp_path.iterdir()) == {source}


@pytest.mark.parametrize(("content", "reason"), [
    (b"\xff", "invalid UTF-8"),
    (b"{", "JSON syntax error"),
    (b'{"columns": {}}', "non-empty object"),
    (b'{"columns": {}, "columns": {}}', "duplicate JSON object key"),
])
def test_failed_load_does_not_write_files(tmp_path, content, reason):
    source = tmp_path / "schema.json"
    source.write_bytes(content)
    with pytest.raises(SchemaError) as error:
        load_schema(source)
    assert str(source) in str(error.value)
    assert reason in str(error.value)
    assert {path.name: path.read_bytes() for path in tmp_path.iterdir()} == {
        "schema.json": content,
    }


def test_fail_fast_returns_first_column_error():
    data = {"columns": {
        "first": {"type": "invalid", "required": True},
        "second": {"type": "int", "required": "true"},
    }}
    with pytest.raises(SchemaError) as error:
        validate_schema(data)
    assert '$["columns"]["first"]["type"]' in str(error.value)
    assert "second" not in str(error.value)


def test_validation_preserves_names_and_values():
    data = {"columns": {" id ": {"type": "int", "required": False}}}
    assert validate_schema(data) is data
    assert list(data["columns"]) == [" id "]
