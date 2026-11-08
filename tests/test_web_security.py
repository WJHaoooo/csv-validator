"""Security boundary regressions; all requests stay in-process/local."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
import csv
import io
import json
from pathlib import Path
from threading import Event

import anyio
from fastapi.testclient import TestClient
import pytest

from csv_validator import web
from csv_validator.web_security import SecurityBoundary, SecuritySettings
from tests.test_web import client, resources  # noqa: F401


@pytest.mark.parametrize("path", ["/", "/health", "/static/app.js", "/missing"])
def test_security_headers_and_no_debug_docs(client, path):
    response = client.get(path)
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert "script-src 'self'" in response.headers["content-security-policy"]
    assert "'unsafe-inline'" not in response.headers["content-security-policy"]
    assert response.headers["referrer-policy"] == "no-referrer"
    assert response.headers["cache-control"] == ("no-cache" if path.startswith("/static/") else "no-store")
    assert "strict-transport-security" not in response.headers
    assert "access-control-allow-origin" not in response.headers
    for docs in ("/docs", "/redoc", "/openapi.json"):
        assert client.get(docs).status_code == 404


def test_https_host_and_hsts():
    app = web.create_app(SecuritySettings(allowed_hosts=("example.test",)))
    with TestClient(app, base_url="https://example.test") as browser:
        response = browser.get("/health")
        assert response.status_code == 200
        assert response.headers["strict-transport-security"] == "max-age=86400"
        assert browser.get("/health", headers={"host": "attacker.test"}).json()["error"]["code"] == "INVALID_HOST"


@pytest.mark.parametrize("headers,status,code", [
    ({"host": "evil.test"}, 400, "INVALID_HOST"),
    ({"host": "localhost@evil.test"}, 400, "INVALID_HOST"),
    ({"origin": "https://evil.test"}, 403, "ORIGIN_NOT_ALLOWED"),
    ({"origin": "null"}, 403, "ORIGIN_NOT_ALLOWED"),
    ({"origin": "http://localhost:81"}, 403, "ORIGIN_NOT_ALLOWED"),
    ({"origin": "http://localhost/path"}, 403, "ORIGIN_NOT_ALLOWED"),
    ({"sec-fetch-site": "cross-site"}, 403, "ORIGIN_NOT_ALLOWED"),
    ([("origin", "http://localhost"), ("origin", "http://localhost")], 403, "ORIGIN_NOT_ALLOWED"),
    ([("host", "localhost"), ("host", "localhost")], 400, "INVALID_HOST"),
])
def test_host_and_origin_rejected_before_spool(client, resources, headers, status, code):
    response = client.post("/api/csv/inspect", headers=headers, content=b"not read")
    assert response.status_code == status
    assert response.json()["error"]["code"] == code
    assert response.headers["cache-control"] == "no-store"
    assert resources == ([], [])


@pytest.mark.parametrize("headers", [{}, {"origin": "http://localhost"}, {"sec-fetch-site": "same-origin"}])
def test_same_origin_and_nonbrowser_clients_work(client, headers):
    response = client.post("/api/csv/inspect", headers=headers, files={"file": ("a.csv", b"id\n1\n")})
    assert response.status_code == 200


def test_active_work_rejects_burst_without_queue_or_tempfiles(resources, monkeypatch):
    entered, release = Event(), Event()
    original = web._inspect_file

    def blocked(file):
        entered.set()
        assert release.wait(5), "test failed to release worker"
        return original(file)

    monkeypatch.setattr(web, "_inspect_file", blocked)
    app = web.create_app(SecuritySettings(max_active_requests=1))
    with TestClient(app, base_url="http://localhost") as browser, ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(browser.post, "/api/csv/inspect", files={"file": ("a.csv", b"id\n1\n")})
        try:
            assert entered.wait(3)
            before = len(resources[1])
            for _ in range(20):
                response = browser.post("/api/csv/inspect", content=b"must not parse")
                assert response.status_code == 503
                assert response.json()["error"]["code"] == "SERVER_BUSY"
                assert response.headers["retry-after"] == "1"
            assert len(resources[1]) == before
            assert browser.get("/health").status_code == 200
        finally:
            release.set()
        assert pending.result(timeout=5).status_code == 200
        assert browser.post("/api/csv/inspect", files={"file": ("b.csv", b"id\n")}).status_code == 200


def test_slow_incomplete_upload_times_out_and_closes_partial_spool(resources):
    app = web.create_app(SecuritySettings(upload_timeout_seconds=0.03))
    messages = []
    scope = {
        "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
        "method": "POST", "scheme": "http", "path": "/api/csv/inspect",
        "raw_path": b"/api/csv/inspect", "query_string": b"", "root_path": "",
        "headers": [(b"host", b"localhost"), (b"content-type", b"multipart/form-data; boundary=b")],
        "client": ("127.0.0.1", 1), "server": ("localhost", 80),
    }

    async def run():
        delivered = False

        async def receive():
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type": "http.request", "more_body": True, "body":
                        b'--b\r\nContent-Disposition: form-data; name="file"; filename="x.csv"\r\n\r\nid\n'}
            await anyio.sleep_forever()

        async def send(message):
            messages.append(message)
        await app(scope, receive, send)

    asyncio.run(run())
    assert messages[0]["status"] == 408
    data = json.loads(b"".join(m.get("body", b"") for m in messages))
    assert data["error"]["code"] == "UPLOAD_TIMEOUT"
    assert len(resources[1]) == 1 and resources[1][0].closed


def test_full_real_output_limit_not_only_mocked_limit(client):
    # A tiny CSV plus missing optional columns expands well beyond 8 MiB.
    columns = {f"missing{i}": {"type": "str", "required": False} for i in range(256)}
    response = client.post("/api/csv/convert", files={
        "file": ("a.csv", b"id\n" + b"1\n" * 1600),
        "schema": ("s.json", json.dumps({"columns": columns}).encode()),
    })
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "OUTPUT_TOO_LARGE"
    assert "content-disposition" not in response.headers
    assert "missing0" not in response.text


@pytest.mark.parametrize("data", [
    b'id\n"' + b"x" * (csv.field_size_limit() + 1) + b'"\n',
    b'id\n"line1\nline2\n',
])
def test_large_and_malformed_multiline_fields_fail_cleanly(client, data):
    response = client.post("/api/csv/inspect", files={"file": ("a.csv", data)})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_CSV"
    assert "csv-validator-" not in response.text


@pytest.mark.parametrize("filename", ["../../outside.csv", r"C:\private\outside.csv", "<script>alert(1)</script>.csv"])
def test_hostile_names_and_content_are_data_not_paths(client, filename):
    hostile = '<img src=x onerror=alert(1)>'
    content = io.StringIO(newline="")
    csv.writer(content).writerows([[hostile], ["<script>alert(1)</script>\nnext"]])
    response = client.post("/api/csv/inspect", files={"file": (filename, content.getvalue().encode())})
    assert response.status_code == 200
    assert response.json()["columns"] == [hostile]
    assert response.json()["preview"] == [["<script>alert(1)</script>\nnext"]]
    assert "/" not in response.json()["filename"] and "\\" not in response.json()["filename"]
    assert response.headers["content-type"].startswith("application/json")


def test_frontend_uses_text_sinks_and_discloses_server_processing():
    static = Path(web.STATIC_DIRECTORY)
    source = "\n".join(path.read_text(encoding="utf-8") for path in static.glob("*.js"))
    for unsafe in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "eval("):
        assert unsafe not in source
    assert "textContent" in source
    page = (static / "index.html").read_text(encoding="utf-8")
    assert "伺服器" in page and "敏感" in page


@pytest.mark.parametrize("kwargs", [
    {"allowed_hosts": ("*",)}, {"allowed_hosts": ()},
    {"max_active_requests": 0}, {"max_active_requests": 9},
    {"upload_timeout_seconds": 0}, {"upload_timeout_seconds": float("nan")},
])
def test_invalid_security_configuration_fails_closed(kwargs):
    with pytest.raises(ValueError):
        SecuritySettings(**kwargs)


@pytest.mark.parametrize("headers", [
    b"X-Many: value\r\n" * 20,
    b"X-Large: " + b"x" * 5000 + b"\r\n",
])
def test_multipart_header_bombs_rejected_by_patched_parser(client, headers):
    body = (b'--b\r\nContent-Disposition: form-data; name="file"; filename="a.csv"\r\n'
            + headers + b"\r\nid\n1\n\r\n--b--\r\n")
    response = client.post("/api/csv/inspect", content=body,
                           headers={"content-type": "multipart/form-data; boundary=b"})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_UPLOAD"


def test_lone_surrogate_in_schema_is_safe_input_error(client):
    raw = b'{"columns":{"\\ud800":{"type":"str","required":false}}}'
    response = client.post("/api/schema/validate", files={"file": ("s.json", raw)})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "SCHEMA_ERROR"
    assert response.json()["error"]["message"] == "Schema contains invalid Unicode text."


def test_unexpected_response_failure_has_headers_and_no_traceback(caplog):
    app = web.create_app()
    @app.get("/broken")
    async def broken():
        raise RuntimeError("PRIVATE_CONTENT C:/internal/secret.csv")
    with TestClient(app, base_url="http://localhost") as browser:
        response = browser.get("/broken")
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "INTERNAL_ERROR"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert "PRIVATE_CONTENT" not in response.text + caplog.text
    assert "Traceback" not in response.text + caplog.text


def test_cooperative_cancellation_does_not_release_slot_while_worker_runs():
    release = Event()

    async def run():
        entered = anyio.Event()
        cancelled = anyio.Event()
        scopes = []

        def work():
            anyio.from_thread.run_sync(entered.set)
            assert release.wait(3)

        async def inner(scope, receive, send):
            await web.run_in_threadpool(work)
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b"ok"})

        boundary = SecurityBoundary(inner, SecuritySettings(max_active_requests=1))
        scope = {"type": "http", "scheme": "http", "path": "/api/csv/convert",
                 "method": "POST", "headers": [(b"host", b"localhost")]}
        messages = []

        async def receive():
            pytest.fail("boundary must not read rejected body")

        async def send(message):
            messages.append(message)

        async def first():
            with anyio.CancelScope() as cancel:
                scopes.append(cancel)
                await boundary(scope, receive, send)
            cancelled.set()

        async with anyio.create_task_group() as tasks:
            tasks.start_soon(first)
            await entered.wait()
            scopes[0].cancel()
            try:
                await boundary(scope, receive, send)
                assert messages[0]["status"] == 503
                assert not cancelled.is_set()
            finally:
                release.set()
        assert cancelled.is_set()
        messages.clear()
        await boundary(scope, receive, send)
        assert messages[0]["status"] == 200

    anyio.run(run)
