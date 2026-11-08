"""W0 API contract, bounded resource use, and cleanup regression tests."""

import asyncio
from pathlib import Path

from fastapi.testclient import TestClient
import pytest
import starlette.formparsers

from csv_validator import web


@pytest.fixture
def resources(tmp_path, monkeypatch):
    directories = []
    spools = []
    original_directory = web.tempfile.TemporaryDirectory
    original_spool = starlette.formparsers.SpooledTemporaryFile

    def tracked_directory(*args, **kwargs):
        kwargs["dir"] = tmp_path
        directory = original_directory(*args, **kwargs)
        directories.append(Path(directory.name))
        return directory

    def tracked_spool(*args, **kwargs):
        file = original_spool(*args, **kwargs)
        spools.append(file)
        return file

    monkeypatch.setattr(web.tempfile, "TemporaryDirectory", tracked_directory)
    monkeypatch.setattr(starlette.formparsers, "SpooledTemporaryFile", tracked_spool)
    yield directories, spools
    assert all(not directory.exists() for directory in directories)
    assert all(file.closed for file in spools)
    assert list(tmp_path.iterdir()) == []


@pytest.fixture
def client(resources):
    with TestClient(web.app) as client:
        yield client


def assert_error(response, status, code, message):
    assert response.status_code == status
    assert response.json() == {"error": {"code": code, "message": message}}
    assert "Traceback" not in response.text
    assert "csv-validator-upload-" not in response.text


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.parametrize("content", [
    b"id,name\n1,Hao\n",
    "id,姓名\n1,範例\n".encode("utf-8"),
    b'"full,name",age\n"line1\nline2",20\n',
    b"id\n",
])
def test_valid_csv_upload(client, content, resources):
    response = client.post("/api/csv/inspect", files={"file": ("input.csv", content, "text/csv")})
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    directories, spools = resources
    assert len(directories) == len(spools) == 1
    assert not directories[0].exists() and spools[0].closed


@pytest.mark.parametrize(("content", "status", "code", "message"), [
    (b"", 400, "EMPTY_FILE", "CSV file is empty."),
    (b"\xff\n", 422, "INVALID_UTF8", "CSV file must be valid UTF-8."),
    (b"id\n1\n\xff\n", 422, "INVALID_UTF8", "CSV file must be valid UTF-8."),
    (b"id\n\xe4\xb8", 422, "INVALID_UTF8", "CSV file must be valid UTF-8."),
    (b'"unterminated\n', 422, "INVALID_CSV", "Unable to parse the CSV file."),
    (b'id\n"unterminated\n', 422, "INVALID_CSV", "Unable to parse the CSV file."),
    (b'"id"x\n', 422, "INVALID_CSV", "Unable to parse the CSV file."),
    (b"\n", 422, "INVALID_CSV", "Unable to read a CSV header."),
])
def test_invalid_upload_cleanup_and_error_contract(client, content, status, code, message):
    response = client.post("/api/csv/inspect", files={"file": ("input.csv", content)})
    assert_error(response, status, code, message)


def test_missing_file(client):
    assert_error(client.post("/api/csv/inspect"), 400, "MISSING_FILE",
                 "Provide one CSV file in the 'file' field.")


def test_wrong_field_is_missing_file_and_still_closed(client):
    response = client.post("/api/csv/inspect", files={"wrong": ("input.csv", b"id\n")})
    assert_error(response, 400, "MISSING_FILE", "Provide one CSV file in the 'file' field.")


@pytest.mark.parametrize("case", ["text", "multiple", "boundary", "truncated", "raw"])
def test_invalid_multipart_contract(client, case):
    if case == "text":
        response = client.post("/api/csv/inspect", files={"file": (None, "not a file")})
    elif case == "multiple":
        response = client.post("/api/csv/inspect", files=[
            ("file", ("a.csv", b"id\n")), ("file", ("b.csv", b"id\n")),
        ])
    elif case == "boundary":
        response = client.post("/api/csv/inspect", content=b"bad", headers={"content-type": "multipart/form-data"})
    elif case == "truncated":
        body = b'--boundary\r\nContent-Disposition: form-data; name="file"; filename="x.csv"\r\n\r\nid\n'
        response = client.post("/api/csv/inspect", content=body,
                               headers={"content-type": "multipart/form-data; boundary=boundary"})
    else:
        response = client.post("/api/csv/inspect", content=b"id\n", headers={"content-type": "text/csv"})
        assert_error(response, 400, "INVALID_UPLOAD",
                     "Use multipart/form-data with one 'file' field.")
        return
    assert_error(response, 400, "INVALID_UPLOAD", "Invalid multipart upload.")


def csv_bytes_of_size(size):
    block = b"x" * 1023 + b"\n"
    remaining = size - 2
    return b"a\n" + block * (remaining // len(block)) + b"x" * (remaining % len(block))


def test_exactly_five_mib_is_accepted(client):
    response = client.post("/api/csv/inspect", files={
        "file": ("input.csv", csv_bytes_of_size(web.MAX_UPLOAD_BYTES)),
    })
    assert response.status_code == 200 and response.json()["status"] == "ok"


def test_one_byte_over_five_mib_is_rejected(client):
    response = client.post("/api/csv/inspect", files={
        "file": ("input.csv", csv_bytes_of_size(web.MAX_UPLOAD_BYTES + 1)),
    })
    assert_error(response, 413, "FILE_TOO_LARGE", "CSV file exceeds 5 MiB.")


def test_request_body_limit_cleans_partial_spool_without_content_length(resources):
    prefix = (
        b"--boundary\r\nContent-Disposition: form-data; name=\"file\"; "
        b"filename=\"input.csv\"\r\nContent-Type: text/csv\r\n\r\n"
    )
    chunks = [prefix, b"id\n" + b"x" * (2 * 1024 * 1024),
              b"x" * web.MAX_UPLOAD_BYTES]
    messages = []
    scope = {
        "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
        "method": "POST", "scheme": "http", "path": "/api/csv/inspect",
        "raw_path": b"/api/csv/inspect", "query_string": b"",
        "headers": [(b"content-type", b"multipart/form-data; boundary=boundary")],
        "client": ("test", 1234), "server": ("test", 80), "root_path": "",
    }

    async def receive():
        if chunks:
            return {"type": "http.request", "body": chunks.pop(0), "more_body": True}
        return {"type": "http.disconnect"}

    async def send(message):
        messages.append(message)

    asyncio.run(web.app(scope, receive, send))
    assert next(message["status"] for message in messages if message["type"] == "http.response.start") == 413
    body = b"".join(message.get("body", b"") for message in messages)
    assert b'"FILE_TOO_LARGE"' in body
    assert resources[1] and all(file.closed for file in resources[1])
    assert resources[0] == []  # Rejected before creating the inspection copy.


def test_reads_are_bounded_and_client_filename_never_selects_path(client, monkeypatch):
    original = web._inspect_file
    original_reader = web.open_csv_reader
    requested_sizes = []
    inspected_paths = []

    class BoundedFile:
        def __init__(self, file):
            self.file = file

        def read(self, size):
            assert 0 < size <= web.CHUNK_BYTES
            requested_sizes.append(size)
            return self.file.read(size)

    def inspect(file):
        return original(BoundedFile(file))

    def reader(path):
        inspected_paths.append(path)
        assert path.name == "upload.csv" and path.exists()
        return original_reader(path)

    monkeypatch.setattr(web, "_inspect_file", inspect)
    monkeypatch.setattr(web, "open_csv_reader", reader)
    response = client.post("/api/csv/inspect", files={
        "file": ("../../escape.txt", b"id\n1\n", "application/octet-stream"),
    })
    assert response.status_code == 200
    assert requested_sizes and inspected_paths
    assert all(not path.exists() for path in inspected_paths)


def test_utf8_character_split_across_chunks_is_valid(client, monkeypatch):
    monkeypatch.setattr(web, "CHUNK_BYTES", 4)
    response = client.post("/api/csv/inspect", files={
        "file": ("input.csv", "id\n範例\n".encode("utf-8")),
    })
    assert response.status_code == 200


@pytest.mark.parametrize("failure", ["parse", "write", "read", "csv_read"])
def test_unexpected_failure_is_sanitized_and_all_temp_files_close(client, monkeypatch, caplog, failure):
    secret = "PRIVATE_CSV_CONTENT /internal/temporary/path"
    if failure == "parse":
        def fail_reader(path):
            raise RuntimeError(secret)
        monkeypatch.setattr(web, "open_csv_reader", fail_reader)
    elif failure in ("write", "csv_read"):
        original_open = Path.open
        def fail_open(path, *args, **kwargs):
            if path.name == "upload.csv" and (
                failure == "write" or (args and args[0] == "r")
            ):
                raise PermissionError(secret)
            return original_open(path, *args, **kwargs)
        monkeypatch.setattr(Path, "open", fail_open)
    else:
        original_inspect = web._inspect_file
        class FailedRead:
            def read(self, size):
                raise OSError(secret)
        monkeypatch.setattr(web, "_inspect_file", lambda file: original_inspect(FailedRead()))
    response = client.post("/api/csv/inspect", files={"file": ("input.csv", b"id\nPRIVATE_CSV_CONTENT\n")})
    assert_error(response, 500, "INTERNAL_ERROR", "Unable to process the request.")
    assert secret not in caplog.text and "PRIVATE_CSV_CONTENT" not in caplog.text


def test_inspect_does_not_perform_schema_conversion(client):
    response = client.post("/api/csv/inspect", files={"file": ("input.csv", b"id,name\nnot-an-int\n")})
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["preview"] == [["not-an-int"]]


def test_http_error_uses_same_envelope(client):
    assert_error(client.get("/not-found"), 404, "HTTP_ERROR", "Not Found")
