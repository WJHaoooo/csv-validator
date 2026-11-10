"""Local-only smoke test of the installed package and Render launch command.

Starts a short-lived local process, uses public examples, then stops it.
No Render API calls, cloud resources, uploads to remote hosts or credentials.
"""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]


def multipart(parts):
    boundary = "csv-validator-local-smoke"
    body = b""
    for field, filename, data in parts:
        body += (f'--{boundary}\r\nContent-Disposition: form-data; name="{field}"; '
                 f'filename="{filename}"\r\nContent-Type: application/octet-stream\r\n\r\n').encode()
        body += data + b"\r\n"
    return body + f"--{boundary}--\r\n".encode(), f"multipart/form-data; boundary={boundary}"


def main():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    base = f"http://127.0.0.1:{port}"
    checks = []
    with tempfile.TemporaryDirectory(prefix="csv-validator-smoke-") as directory:
        temporary = Path(directory)
        uploads = temporary / "uploads"
        uploads.mkdir()
        env = {**os.environ, "PORT": str(port),
               "CSV_VALIDATOR_ALLOWED_HOSTS": "local-smoke.onrender.com",
               "CSV_VALIDATOR_TRUSTED_PROXY_IPS": "127.0.0.1/32",
               "TMPDIR": str(uploads), "TEMP": str(uploads), "TMP": str(uploads)}
        process = subprocess.Popen(
            [sys.executable, str(ROOT / "scripts/start_render.py")], cwd=ROOT, env=env,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )

        def request(path, data=None, extra=None):
            headers = {"Host": "local-smoke.onrender.com", "X-Forwarded-Proto": "https"}
            headers.update(extra or {})
            try:
                response = urlopen(Request(base + path, data=data, headers=headers), timeout=5)
            except HTTPError as exc:
                response = exc
            with response:
                return response.status, {k.lower(): v for k, v in response.headers.items()}, response.read()

        def post(path, parts):
            body, content_type = multipart(parts)
            return request(path, body, {"Content-Type": content_type, "Origin": "https://local-smoke.onrender.com"})

        try:
            for _ in range(100):
                if process.poll() is not None:
                    raise RuntimeError("Local launch failed; review deployment configuration.")
                try:
                    status, headers, body = request("/health")
                    break
                except URLError:
                    time.sleep(0.05)
            else:
                raise RuntimeError("Local startup deadline exceeded.")
            assert status == 200 and json.loads(body) == {"status": "ok"}
            checks.append("health")
            for path, mime in (("/", "text/html"), ("/static/style.css", "text/css"),
                               ("/static/app.js", "javascript"), ("/static/rules.js", "javascript")):
                status, headers, body = request(path)
                assert status == 200 and mime in headers["content-type"]
                assert "script-src 'self'" in headers["content-security-policy"]
                assert headers["x-content-type-options"] == "nosniff"
                assert headers["strict-transport-security"] == "max-age=86400"
                assert "server" not in headers
                if path == "/":
                    assert "敏感".encode() in body
                checks.append(path)
            csv = (ROOT / "examples/valid.csv").read_bytes()
            schema = (ROOT / "examples/schema.json").read_bytes()
            status, _, body = post("/api/csv/inspect", [("file", "../../example.csv", csv)])
            assert status == 200 and json.loads(body)["filename"] == "example.csv"
            assert json.loads(body)["preview_count"] == 3
            checks.append("inspect")
            status, _, body = post("/api/schema/validate", [("file", "schema.json", schema)])
            assert status == 200 and json.loads(body)["schema"] == json.loads(schema)
            checks.append("schema")
            status, headers, body = post("/api/csv/convert",
                                        [("file", "valid.csv", csv), ("schema", "schema.json", schema)])
            assert status == 200 and body == (ROOT / "examples/expected.json").read_bytes()
            assert "converted.json" in headers["content-disposition"]
            assert headers["cache-control"] == "no-store"
            output = temporary / "cli.json"
            cli = subprocess.run([sys.executable, "-m", "csv_validator.cli", "--csv",
                                  str(ROOT / "examples/valid.csv"), "--schema",
                                  str(ROOT / "examples/schema.json"), "--output", str(output)],
                                 capture_output=True, timeout=20, check=False)
            assert cli.returncode == 0 and output.read_bytes() == body
            checks.append("convert_equals_cli")
            status, headers, body = post("/api/csv/convert", [
                ("file", "invalid.csv", (ROOT / "examples/invalid.csv").read_bytes()),
                ("schema", "schema.json", schema)])
            assert status == 422 and json.loads(body)["error"]["code"] == "CSV_ROW_ERROR"
            assert "content-disposition" not in headers
            checks.append("invalid_no_download")
            payload, content_type = multipart([("file", "valid.csv", csv)])
            status, _, body = request("/api/csv/inspect", payload,
                {"Content-Type": content_type, "Origin": "https://untrusted.invalid"})
            assert status == 403 and json.loads(body)["error"]["code"] == "ORIGIN_NOT_ALLOWED"
            checks.append("cross_origin")
            status, _, body = request("/health", extra={"Host": "untrusted.invalid"})
            assert status == 400 and json.loads(body)["error"]["code"] == "INVALID_HOST"
            checks.append("host")
            status, _, body = request("/api/csv/inspect", b"--b\r\nbroken",
                                     {"Content-Type": "multipart/form-data; boundary=b"})
            assert status == 400 and json.loads(body)["error"]["code"] == "INVALID_UPLOAD"
            checks.append("multipart")
            assert list(uploads.iterdir()) == []
            checks.append("temporary_cleanup")
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
            _, logs = process.communicate()
        assert b"Traceback" not in logs and b"Example Gamma" not in logs
        checks.append("safe_logs_and_shutdown")
    print(json.dumps({"python": sys.version.split()[0], "platform": sys.platform,
                      "status": "passed", "checks": checks}, indent=2))


if __name__ == "__main__":
    main()
