"""Render fallback, explicit proxy trust and public HTTPS remain independent."""
import importlib.util
from pathlib import Path
import subprocess
import sys

import pytest
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from csv_validator import web
from csv_validator.web_security import SecuritySettings
from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("render_launcher", ROOT / "scripts/start_render.py")
launcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(launcher)


def environment():
    return {"PORT": "10000", "RENDER_EXTERNAL_HOSTNAME": "csv-validator-demo.onrender.com",
            "CSV_VALIDATOR_TRUSTED_PROXY_IPS": "127.0.0.1"}


def test_render_runtime_uses_explicit_port_single_worker_and_proxy_trust():
    config = launcher.configuration(environment())
    assert config["host"] == "0.0.0.0"
    assert config["port"] == 10000 and config["workers"] == 1
    assert config["allowed_hosts"] == "csv-validator-demo.onrender.com"
    assert config["forwarded_allow_ips"] == "127.0.0.1/32"
    assert config["access_log"] is False and config["server_header"] is False
    assert config["limit_concurrency"] == 8
    assert "reload" not in config


@pytest.mark.parametrize("key,value", [
    ("PORT", ""), ("PORT", "0"), ("PORT", "65536"), ("PORT", "１２３"),
    ("CSV_VALIDATOR_TRUSTED_PROXY_IPS", "*"),
    ("CSV_VALIDATOR_TRUSTED_PROXY_IPS", "0.0.0.0/0"),
    ("CSV_VALIDATOR_TRUSTED_PROXY_IPS", "::/0"),
    ("CSV_VALIDATOR_TRUSTED_PROXY_IPS", "0.0.0.0/1,128.0.0.0/1"),
    ("CSV_VALIDATOR_TRUSTED_PROXY_IPS", "::/1,8000::/1"),
    ("CSV_VALIDATOR_TRUSTED_PROXY_IPS", "proxy.example.com"),
    ("CSV_VALIDATOR_ALLOWED_HOSTS", "*"), ("CSV_VALIDATOR_ALLOWED_HOSTS", "https://demo.onrender.com"),
    ("RENDER_EXTERNAL_HOSTNAME", "demo.onrender.com.evil.test"),
])
def test_invalid_or_unverified_deployment_config_rejected(key, value):
    env = {**environment(), key: value}
    with pytest.raises(ValueError):
        launcher.configuration(env)


def test_render_inherited_wildcard_is_not_used():
    env = environment()
    env["FORWARDED_ALLOW_IPS"] = "*"
    assert launcher.configuration(env)["forwarded_allow_ips"] != "*"
    del env["CSV_VALIDATOR_TRUSTED_PROXY_IPS"]
    fallback = launcher.configuration(env)
    assert fallback["proxy_headers"] is False
    assert fallback["forwarded_allow_ips"] == ""


def test_explicit_custom_domains_and_mixed_proxy_networks():
    config = launcher.configuration({
        **environment(), "CSV_VALIDATOR_ALLOWED_HOSTS": "demo.onrender.com,example.test",
        "CSV_VALIDATOR_TRUSTED_PROXY_IPS": "127.0.0.1,2001:db8::/64",
    })
    assert config["allowed_hosts"] == "demo.onrender.com,example.test"
    assert config["forwarded_allow_ips"] == "127.0.0.1/32,2001:db8::/64"


@pytest.mark.parametrize("peer,expected", [("127.0.0.1", 200), ("192.0.2.5", 403)])
def test_proxy_trust_preserves_https_same_origin_and_rejects_forgery(peer, expected):
    app = ProxyHeadersMiddleware(
        web.create_app(SecuritySettings(allowed_hosts=("demo.onrender.com",))),
        trusted_hosts=["127.0.0.1"],
    )
    with TestClient(app, base_url="http://demo.onrender.com", client=(peer, 123)) as client:
        response = client.post("/api/csv/inspect",
            headers={"Origin": "https://demo.onrender.com", "X-Forwarded-Proto": "https"},
            files={"file": ("x.csv", b"id\n1\n")})
    assert response.status_code == expected
    if expected == 200:
        assert "strict-transport-security" in response.headers
        assert response.json()["columns"] == ["id"]
    else:
        assert response.json()["error"]["code"] == "ORIGIN_NOT_ALLOWED"
        assert "strict-transport-security" not in response.headers




@pytest.mark.parametrize("render", [False, True])
def test_launcher_without_proxy_starts_with_forwarded_headers_disabled(monkeypatch, render):
    import os
    captured = {}
    env = environment()
    env.pop("CSV_VALIDATOR_TRUSTED_PROXY_IPS")
    env["FORWARDED_ALLOW_IPS"] = "*"
    if render:
        env["RENDER"] = "true"
    for key in ("RENDER", "CSV_VALIDATOR_TRUSTED_PROXY_IPS", "CSV_VALIDATOR_ALLOWED_HOSTS"):
        monkeypatch.delenv(key, raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    def run(app, **kwargs):
        captured.update(kwargs)
        assert app == "csv_validator.web:app"
    monkeypatch.setenv("CSV_VALIDATOR_ALLOWED_HOSTS", "")
    monkeypatch.setenv("CSV_VALIDATOR_PUBLIC_SCHEME", "")
    monkeypatch.setattr(launcher.uvicorn, "run", run)
    assert launcher.main() == 0
    assert captured["proxy_headers"] is False
    assert captured["forwarded_allow_ips"] == ""
    assert os.environ["FORWARDED_ALLOW_IPS"] == ""
    assert os.environ["CSV_VALIDATOR_PUBLIC_SCHEME"] == ("https" if render else "")
    assert os.environ["CSV_VALIDATOR_ALLOWED_HOSTS"] == "csv-validator-demo.onrender.com"


@pytest.mark.parametrize("forwarded", [
    {},
    {"X-Forwarded-For": "203.0.113.66", "X-Forwarded-Proto": "https"},
    {"X-Forwarded-For": "127.0.0.1", "X-Forwarded-Proto": "http",
     "X-Forwarded-Host": "attacker.invalid"},
    {"Forwarded": 'for=203.0.113.66;proto=https;host="attacker.invalid"',
     "X-Forwarded-Proto": "ftp", "X-Forwarded-Port": "443"},
])
def test_render_fallback_keeps_peer_and_transport_but_checks_public_origin(forwarded):
    import uvicorn
    app = web.create_app(SecuritySettings(
        allowed_hosts=("demo.onrender.com",), public_scheme="https"))
    @app.get("/connection")
    async def connection(request: web.Request):
        return {"client": list(request.scope["client"]), "scheme": request.scope["scheme"]}
    config = launcher.configuration({
        "PORT": "10000", "RENDER": "true",
        "RENDER_EXTERNAL_HOSTNAME": "demo.onrender.com", "FORWARDED_ALLOW_IPS": "*",
    })
    server = uvicorn.Config(app, proxy_headers=config["proxy_headers"],
                            forwarded_allow_ips=config["forwarded_allow_ips"])
    server.load()
    with TestClient(server.loaded_app, base_url="http://demo.onrender.com",
                    client=("192.0.2.9", 1234)) as browser:
        response = browser.get("/connection", headers=forwarded)
        assert response.status_code == 200
        assert response.json() == {"client": ["192.0.2.9", 1234], "scheme": "http"}
        assert response.headers["strict-transport-security"] == "max-age=86400"
        for origin, status in (("https://demo.onrender.com", 200),
                               ("http://demo.onrender.com", 403),
                               ("https://attacker.invalid", 403)):
            response = browser.post("/api/csv/inspect",
                headers={**forwarded, "Origin": origin},
                files={"file": ("x.csv", b"id\n1\n")})
            assert response.status_code == status
            if status == 403:
                assert response.json()["error"]["code"] == "ORIGIN_NOT_ALLOWED"
        bad = browser.get("/health", headers={**forwarded, "Host": "attacker.invalid"})
        assert bad.status_code == 400
        assert bad.json()["error"]["code"] == "INVALID_HOST"


def test_render_requires_realistic_platform_hostname_even_with_explicit_host():
    with pytest.raises(ValueError):
        launcher.configuration({"PORT": "10000", "RENDER": "true",
                                "CSV_VALIDATOR_ALLOWED_HOSTS": "example.test"})


def test_canonical_https_is_not_taken_from_a_request_header_or_ambient_setting():
    config = launcher.configuration({
        "PORT": "10000", "CSV_VALIDATOR_ALLOWED_HOSTS": "localhost",
        "CSV_VALIDATOR_PUBLIC_SCHEME": "https",
    })
    assert config["public_scheme"] == ""
    with pytest.raises(ValueError, match="Public scheme"):
        SecuritySettings(public_scheme="http")
