"""Render launch configuration: fail closed before opening a listening socket."""
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
    ("CSV_VALIDATOR_TRUSTED_PROXY_IPS", ""), ("CSV_VALIDATOR_TRUSTED_PROXY_IPS", "*"),
    ("CSV_VALIDATOR_TRUSTED_PROXY_IPS", "0.0.0.0/0"),
    ("CSV_VALIDATOR_TRUSTED_PROXY_IPS", "::/0"),
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
    with pytest.raises(ValueError, match="verified"):
        launcher.configuration(env)


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


def test_launcher_without_proxy_configuration_exits_before_server_starts():
    import os
    env = dict(os.environ)
    env.update(environment())
    env.pop("CSV_VALIDATOR_TRUSTED_PROXY_IPS")
    result = subprocess.run([sys.executable, str(ROOT / "scripts/start_render.py")],
                            env=env, capture_output=True, text=True, timeout=10)
    assert result.returncode == 2
    assert "verified ingress" in result.stderr and "Traceback" not in result.stderr
