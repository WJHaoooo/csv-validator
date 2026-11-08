"""Audit installed package names/versions with OSV (no source/data sent).

Exit 0: no matches; 1: advisories found; 2: audit unavailable/incomplete.
Run in the intended deployment environment. Not a zero-vulnerability guarantee.
"""
from datetime import datetime, timezone
from importlib.metadata import distributions
import json
import sys
from urllib.error import URLError
from urllib.request import Request, urlopen


def main() -> int:
    packages = sorted({
        (dist.metadata["Name"], dist.version)
        for dist in distributions() if dist.metadata["Name"]
    })
    request = Request(
        "https://api.osv.dev/v1/querybatch",
        data=json.dumps({"queries": [
            {"package": {"name": name, "ecosystem": "PyPI"}, "version": version}
            for name, version in packages
        ]}).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST",
    )
    try:
        with urlopen(request, timeout=30) as response:
            body = response.read(4 * 1024 * 1024 + 1)
        if len(body) > 4 * 1024 * 1024:
            raise ValueError("Audit response exceeds limit.")
        results = json.loads(body)["results"]
        if len(results) != len(packages) or any(not isinstance(item, dict) for item in results):
            raise ValueError("Incomplete audit response.")
        findings = [
            {"name": name, "version": version,
             "advisories": sorted({v["id"] for v in result.get("vulns", [])})}
            for (name, version), result in zip(packages, results) if result.get("vulns")
        ]
    except (URLError, TimeoutError, OSError, ValueError, KeyError, TypeError):
        print("Audit unavailable/incomplete; do not treat as a clean result.", file=sys.stderr)
        return 2
    print(json.dumps({
        "checked_at_utc": datetime.now(timezone.utc).isoformat(),
        "source": "https://api.osv.dev/v1/querybatch",
        "packages_scanned": len(packages),
        "packages": [{"name": name, "version": version} for name, version in packages],
        "findings": findings,
    }, ensure_ascii=False, indent=2))
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
