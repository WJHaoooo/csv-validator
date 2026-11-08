"""W2 API integration: reuse core rules, no partial payload, bounded resources."""

from contextlib import closing
import json
from pathlib import Path
import subprocess
import sys
import tempfile

import pytest

from csv_validator import web_service
from tests.test_web import client, resources  # noqa: F401


def schema_bytes(columns):
    return json.dumps({"columns": columns}, ensure_ascii=False).encode("utf-8")


def convert(client, csv, schema):
    return client.post("/api/csv/convert", files={
        "file": ("input.csv", csv, "text/csv"),
        "schema": ("schema.json", schema, "application/json"),
    })


def test_complete_download_matches_real_cli_bytes(client):
    project = Path(__file__).resolve().parents[1]
    csv = project / "examples/valid.csv"
    schema = project / "examples/schema.json"
    response = convert(client, csv.read_bytes(), schema.read_bytes())
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("application/json")
    assert "converted.json" in response.headers["content-disposition"]
    assert response.headers["x-row-count"] == "3"
    assert response.headers["x-column-count"] == "3"
    assert response.headers["cache-control"] == "no-store"
    with tempfile.TemporaryDirectory() as directory:
        output = Path(directory) / "cli.json"
        command = [sys.executable, "-m", "csv_validator.cli", "--csv", str(csv),
                   "--schema", str(schema), "--output", str(output)]
        result = subprocess.run(command, capture_output=True, text=True, check=False, timeout=20)
        assert result.returncode == 0, result.stderr
        assert response.content == output.read_bytes()
    data = response.json()
    assert data[1]["name"] == "範例乙"
    assert data[1]["score"] is None
    assert data[2]["name"] == "  Example Gamma  "
    assert list(data[0]) == ["id", "name", "score"]


def test_selected_schema_drops_extra_csv_columns(client):
    schema = schema_bytes({"name": {"type": "str", "required": False}})
    response = convert(client, b"id,name,score\n001, Amy ,95.5\n", schema)
    assert response.status_code == 200
    assert response.json() == [{"name": " Amy "}]


def test_missing_optional_is_kept_as_null_and_schema_order_wins(client):
    schema = schema_bytes({
        "missing": {"type": "float", "required": False},
        "name": {"type": "str", "required": True},
        "id": {"type": "int", "required": True},
    })
    response = convert(client, b"id,name,city\n001,Amy,X\n", schema)
    assert response.status_code == 200
    assert response.json() == [{"missing": None, "name": "Amy", "id": 1}]
    assert list(response.json()[0]) == ["missing", "name", "id"]


def test_missing_required_reports_header_without_server_path(client):
    schema = schema_bytes({"missing": {"type": "str", "required": True}})
    response = convert(client, b"id\n1\n", schema)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "CSV_HEADER_ERROR"
    assert "'missing'" in response.json()["error"]["message"]
    assert "csv-validator-convert-" not in response.text
    assert "upload.csv" not in response.text


@pytest.mark.parametrize(("raw", "type_name", "required", "expected"), [
    ("001", "int", True, 1),
    ("-2.5e2", "float", True, -250.0),
    ("  raw  ", "str", False, "  raw  "),
    ("", "float", False, None),
    (" \t", "str", False, None),
])
def test_conversion_rules_at_http_boundary(client, raw, type_name, required, expected):
    import csv
    import io
    text = io.StringIO(newline="")
    writer = csv.writer(text)
    writer.writerows([["value"], [raw]])
    response = convert(client, text.getvalue().encode("utf-8"),
                       schema_bytes({"value": {"type": type_name, "required": required}}))
    assert response.status_code == 200, response.text
    assert response.json() == [{"value": expected}]


@pytest.mark.parametrize(("raw", "type_name", "required"), [
    ("", "str", True), ("   ", "int", True),
    ("3.5", "int", False), ("NaN", "float", False),
    ("Infinity", "float", True), ("1e309", "float", True),
])
def test_fail_fast_has_safe_cell_details_and_no_download(client, raw, type_name, required):
    import csv
    import io
    text = io.StringIO(newline="")
    csv.writer(text).writerows([["value"], ["1"], [raw], ["later"]])
    response = convert(client, text.getvalue().encode(),
                       schema_bytes({"value": {"type": type_name, "required": required}}))
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "CSV_ROW_ERROR"
    assert error["details"] == {
        "line": 3, "column": "value", "raw_value": raw,
        "raw_value_truncated": False, "expected_type": type_name,
    }
    assert "content-disposition" not in response.headers
    assert "csv-validator-convert-" not in response.text
    assert "Traceback" not in response.text


def test_original_value_is_bounded_and_markup_is_plain_json(client):
    raw = "<script>alert(1)</script>" * 20
    response = convert(client, ("value\n" + raw + "\n").encode(),
                       schema_bytes({"value": {"type": "int", "required": False}}))
    error = response.json()["error"]
    assert error["details"]["raw_value"] == raw[:256]
    assert error["details"]["raw_value_truncated"] is True


def test_multiline_record_error_uses_start_physical_line(client):
    csv = b'id,name\n1,"first\nsecond"\nbad,"third\nfourth"\n'
    schema = schema_bytes({"id": {"type": "int", "required": True}})
    response = convert(client, csv, schema)
    assert response.status_code == 422
    assert response.json()["error"]["details"]["line"] == 4


@pytest.mark.parametrize(("csv", "code"), [
    (b"id,name\n1\n", "CSV_ROW_ERROR"),
    (b"id,id\n1,2\n", "CSV_HEADER_ERROR"),
    (b'id\n1\n2\n3\n4\n5\n"unterminated', "CSV_ROW_ERROR"),
    (b"id\n1\n\xff", "INVALID_UTF8"),
])
def test_complete_csv_is_validated_not_just_the_preview(client, csv, code):
    response = convert(client, csv, schema_bytes({"id": {"type": "int", "required": True}}))
    assert response.status_code == 422
    assert response.json()["error"]["code"] == code
    assert "content-disposition" not in response.headers


def test_header_only_downloads_empty_array(client):
    response = convert(client, b"id\n", schema_bytes({"id": {"type": "str", "required": False}}))
    assert response.status_code == 200
    assert response.content == b"[]\n"
    assert response.headers["x-row-count"] == "0"


def test_schema_roundtrip_and_numeric_column_order(client):
    original = schema_bytes({
        "10": {"type": "str", "required": False},
        "2": {"type": "int", "required": True},
        "missing": {"type": "str", "required": False},
    })
    response = client.post("/api/schema/validate", files={"file": ("schema.json", original)})
    assert response.status_code == 200
    assert response.json()["column_order"] == ["10", "2", "missing"]
    saved = json.dumps(response.json()["schema"], ensure_ascii=False).encode()
    repeated = client.post("/api/schema/validate", files={"file": ("schema.json", saved)})
    assert repeated.json() == response.json()
    converted = convert(client, b"2,10,extra\n001,Amy,x\n", original)
    assert converted.status_code == 200
    assert list(converted.json()[0]) == ["10", "2", "missing"]


@pytest.mark.parametrize("content", [
    b"{", b"\xff", b'{"columns":{}}',
    b'{"columns":{"id":{"type":"int","required":1}}}',
    b'{"columns":{},"columns":{}}',
    b'{"columns":{"id":{"type":"str","required":false,"extra":1}}}',
])
def test_import_reuses_strict_schema_validation(client, content):
    response = client.post("/api/schema/validate", files={"file": ("schema.json", content)})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "SCHEMA_ERROR"
    assert response.json()["error"]["message"]
    assert "csv-validator-" not in response.text


def test_schema_has_priority_over_invalid_csv(client, monkeypatch):
    def unexpected_copy(*args, **kwargs):
        pytest.fail("CSV was processed before Schema validation")
    monkeypatch.setattr(web_service, "copy_csv", unexpected_copy)
    response = convert(client, b"\xff", b"{")
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "SCHEMA_ERROR"


def test_schema_limit_and_exact_boundary(client):
    schema = schema_bytes({"id": {"type": "str", "required": False}})
    exact = schema + b" " * (web_service.MAX_SCHEMA_BYTES - len(schema))
    response = client.post("/api/schema/validate", files={"file": ("schema.json", exact)})
    assert response.status_code == 200
    too_big = client.post("/api/schema/validate", files={"file": ("schema.json", exact + b" ")})
    assert too_big.status_code == 413
    assert too_big.json()["error"]["code"] == "SCHEMA_TOO_LARGE"


def test_csv_upload_limit_on_conversion(client):
    response = convert(client, b"x" * (5 * 1024 * 1024 + 1),
                       schema_bytes({"id": {"type": "str", "required": False}}))
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "FILE_TOO_LARGE"


def test_output_limit_stops_iterator_and_cleans_resources(client, monkeypatch):
    monkeypatch.setattr(web_service, "MAX_OUTPUT_BYTES", 90)
    original = web_service.iter_converted_rows
    consumed = []

    def tracked(path, schema):
        with closing(original(path, schema)) as rows:
            for row in rows:
                consumed.append(row)
                yield row
    monkeypatch.setattr(web_service, "iter_converted_rows", tracked)
    response = convert(client, b"id\n" + b"1\n" * 100,
                       schema_bytes({"id": {"type": "int", "required": True}}))
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "OUTPUT_TOO_LARGE"
    assert 0 < len(consumed) < 100
    assert "content-disposition" not in response.headers


def test_encoder_rejects_nonstandard_numbers_even_if_core_is_faulty(client, monkeypatch):
    def faulty_rows(*args):
        yield {"id": float("nan")}
    monkeypatch.setattr(web_service, "iter_converted_rows", faulty_rows)
    response = convert(client, b"id\n1\n", schema_bytes({"id": {"type": "float", "required": True}}))
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "JSON_WRITE_ERROR"
    assert "content-disposition" not in response.headers


def test_output_path_and_extra_fields_are_not_accepted(client):
    response = client.post("/api/csv/convert", files={
        "file": ("x.csv", b"id\n1\n"),
        "schema": ("schema.json", schema_bytes({"id": {"type": "int", "required": True}})),
        "output": (None, "C:/should-not-be-created.json"),
    })
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_UPLOAD"


def test_missing_schema(client):
    response = client.post("/api/csv/convert", files={"file": ("x.csv", b"id\n1\n")})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "MISSING_SCHEMA"


def test_unexpected_conversion_error_does_not_leak_paths_or_log_values(client, monkeypatch, caplog):
    def failure(*args, **kwargs):
        raise OSError("PRIVATE_DATA C:/internal/temp/secret.csv")
    monkeypatch.setattr(web_service, "copy_csv", failure)
    response = convert(client, b"id\n1\n", schema_bytes({"id": {"type": "str", "required": False}}))
    assert response.status_code == 500
    assert response.json() == {"error": {"code": "INTERNAL_ERROR", "message": "Unable to process the request."}}
    assert "PRIVATE_DATA" not in caplog.text


def test_first_semantic_error_precedes_later_invalid_utf8_like_cli(client):
    response = convert(
        client, b"id\nbad\n\xff\n",
        schema_bytes({"id": {"type": "int", "required": True}}),
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "CSV_ROW_ERROR"
    assert response.json()["error"]["details"]["line"] == 2


def test_missing_required_header_precedes_later_encoding_error(client):
    response = convert(
        client, b"id\n\xff\n",
        schema_bytes({"missing": {"type": "str", "required": True}}),
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "CSV_HEADER_ERROR"
    assert "missing" in response.json()["error"]["message"]


def test_large_integer_download_preserves_exact_digits(client):
    response = convert(
        client, b"id\n9007199254740993\n",
        schema_bytes({"id": {"type": "int", "required": True}}),
    )
    assert response.status_code == 200
    assert b"9007199254740993" in response.content
    assert response.json() == [{"id": 9007199254740993}]


def test_excessively_nested_schema_is_a_safe_input_error(client):
    response = client.post("/api/schema/validate", files={
        "file": ("schema.json", b"[" * 2000 + b"0" + b"]" * 2000),
    })
    assert response.status_code == 422
    assert response.json()["error"] == {
        "code": "SCHEMA_ERROR", "message": "Schema nesting is too deep.",
    }
