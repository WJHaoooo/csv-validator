"""Explicit Render launcher. No wildcard proxy trust or development server."""
from collections.abc import Mapping
import ipaddress
import os
import re
import sys

import uvicorn


def configuration(environ: Mapping[str, str]) -> dict:
    port_text = environ.get("PORT", "")
    if not port_text.isascii() or not port_text.isdecimal() or not 1 <= int(port_text) <= 65535:
        raise ValueError("PORT must be an integer between 1 and 65535.")
    hosts = environ.get("CSV_VALIDATOR_ALLOWED_HOSTS", "").strip()
    render = environ.get("RENDER") == "true"
    hostname = environ.get("RENDER_EXTERNAL_HOSTNAME", "").lower()
    if render or not hosts:
        if not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.onrender\.com", hostname):
            raise ValueError("Set exact CSV_VALIDATOR_ALLOWED_HOSTS or a valid RENDER_EXTERNAL_HOSTNAME.")
        if not hosts:
            hosts = hostname
    hostnames = tuple(host.strip().lower() for host in hosts.split(","))
    for host in hostnames:
        if not re.fullmatch(r"[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?", host) or ".." in host:
            raise ValueError("Allowed hosts must be explicit DNS names or IPv4 addresses without ports.")
    proxies = environ.get("CSV_VALIDATOR_TRUSTED_PROXY_IPS", "").strip()
    networks = []
    for item in proxies.split(",") if proxies else []:
        try:
            network = ipaddress.ip_network(item.strip(), strict=False)
        except ValueError:
            raise ValueError("Trusted proxies must be verified IP addresses or CIDRs, never wildcard.") from None
        if network.prefixlen == 0:
            raise ValueError("Catch-all proxy networks are not allowed.")
        networks.append(network)
    for family in (4, 6):
        collapsed = ipaddress.collapse_addresses(n for n in networks if n.version == family)
        if any(n.prefixlen == 0 for n in collapsed):
            raise ValueError("Combined catch-all proxy networks are not allowed.")
    return {"host": "0.0.0.0", "port": int(port_text), "workers": 1,
            "proxy_headers": bool(networks), "forwarded_allow_ips": ",".join(map(str, networks)),
            "public_scheme": "https" if render else "",
            "access_log": False, "server_header": False, "log_level": "warning",
            "limit_concurrency": 8, "backlog": 16, "timeout_keep_alive": 5,
            "timeout_graceful_shutdown": 20, "allowed_hosts": ",".join(hostnames)}


def main() -> int:
    try:
        settings = configuration(os.environ)
    except ValueError as exc:
        print(f"Deployment configuration error: {exc}", file=sys.stderr)
        return 2
    os.environ["CSV_VALIDATOR_ALLOWED_HOSTS"] = settings.pop("allowed_hosts")
    # Public HTTPS is deployment configuration, not a claim from request headers.
    os.environ["CSV_VALIDATOR_PUBLIC_SCHEME"] = settings.pop("public_scheme")
    # Override Render's broad default; never inherit FORWARDED_ALLOW_IPS=*.
    os.environ["FORWARDED_ALLOW_IPS"] = settings["forwarded_allow_ips"]
    uvicorn.run("csv_validator.web:app", **settings)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
