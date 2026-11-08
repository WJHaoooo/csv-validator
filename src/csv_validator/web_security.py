"""Small ASGI security boundary; no authentication or distributed rate limiter."""

from dataclasses import dataclass
import os
import logging
from threading import BoundedSemaphore
from urllib.parse import urlsplit

from starlette.responses import JSONResponse


logger = logging.getLogger(__name__)


CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self'; "
    "img-src 'self' data:; connect-src 'self'; object-src 'none'; "
    "base-uri 'none'; frame-ancestors 'none'; form-action 'self'"
)


@dataclass(frozen=True)
class SecuritySettings:
    allowed_hosts: tuple[str, ...] = ("localhost", "127.0.0.1", "::1")
    max_active_requests: int = 2
    upload_timeout_seconds: float = 15.0

    def __post_init__(self):
        if not self.allowed_hosts or any(
            not host or "*" in host or "/" in host or "@" in host or host.strip() != host
            for host in self.allowed_hosts
        ):
            raise ValueError("Configure explicit allowed hostnames without wildcard, scheme or paths.")
        if not 1 <= self.max_active_requests <= 8:
            raise ValueError("API concurrency must be between 1 and 8 per worker.")
        if not 0 < self.upload_timeout_seconds <= 60:
            raise ValueError("Upload timeout must be positive and at most 60 seconds.")

    @classmethod
    def from_environment(cls):
        hosts = os.environ.get("CSV_VALIDATOR_ALLOWED_HOSTS", "localhost,127.0.0.1,::1")
        return cls(
            allowed_hosts=tuple(host.strip().lower() for host in hosts.split(",")),
            max_active_requests=int(os.environ.get("CSV_VALIDATOR_MAX_ACTIVE_REQUESTS", "2")),
            upload_timeout_seconds=float(os.environ.get("CSV_VALIDATOR_UPLOAD_TIMEOUT_SECONDS", "15")),
        )


def _origin(value: str):
    """Return an exact normalized origin, or reject ambiguous/userinfo URLs."""
    if any(character.isspace() for character in value) or "\\" in value:
        return None
    try:
        parts = urlsplit(value)
        if (
            parts.scheme not in ("http", "https") or not parts.hostname
            or parts.username is not None or parts.password is not None
            or parts.path not in ("", "/") or parts.query or parts.fragment
        ):
            return None
        return (parts.scheme, parts.hostname.lower(), parts.port or (443 if parts.scheme == "https" else 80))
    except ValueError:
        return None


class SecurityBoundary:
    """Reject before reading bodies; hold a permit until actual work finishes.

    BoundedSemaphore.acquire(False) does not wait or create an unbounded queue.
    Limits are per ASGI worker, not global across processes/replicas.
    """

    def __init__(self, app, settings: SecuritySettings):
        self.app = app
        self.settings = settings
        self.slots = BoundedSemaphore(settings.max_active_requests)

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        started = False

        async def secure_send(message):
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
                headers = dict(message.get("headers", []))
                headers.update({
                    b"content-security-policy": CSP.encode("ascii"),
                    b"x-content-type-options": b"nosniff",
                    b"x-frame-options": b"DENY",
                    b"referrer-policy": b"no-referrer",
                    b"permissions-policy": b"camera=(), microphone=(), geolocation=()",
                    b"cross-origin-resource-policy": b"same-origin",
                })
                headers[b"cache-control"] = b"no-cache" if scope["path"].startswith("/static/") else b"no-store"
                if scope.get("scheme") == "https":
                    headers[b"strict-transport-security"] = b"max-age=86400"
                message = {**message, "headers": list(headers.items())}
            await send(message)

        async def reject(status, code, message, retry=False):
            response = JSONResponse(
                {"error": {"code": code, "message": message}},
                status_code=status,
                headers={"Retry-After": "1"} if retry else None,
            )
            await response(scope, receive, secure_send)

        hosts = [value for key, value in scope["headers"] if key.lower() == b"host"]
        try:
            host = hosts[0].decode("ascii") if len(hosts) == 1 else ""
        except UnicodeDecodeError:
            host = ""
        expected = _origin(scope.get("scheme", "http") + "://" + host)
        if expected is None or expected[1] not in self.settings.allowed_hosts:
            return await reject(400, "INVALID_HOST", "Host is not allowed.")

        is_api = scope["path"].startswith("/api/")
        if is_api:
            origins = [value for key, value in scope["headers"] if key.lower() == b"origin"]
            fetch_sites = [value for key, value in scope["headers"] if key.lower() == b"sec-fetch-site"]
            try:
                origin = origins[0].decode("ascii") if len(origins) == 1 else ""
            except UnicodeDecodeError:
                origin = ""
            if (
                len(origins) > 1
                or (origins and _origin(origin) != expected)
                or (not origins and b"cross-site" in fetch_sites)
            ):
                return await reject(403, "ORIGIN_NOT_ALLOWED", "Cross-origin API requests are not allowed.")

        admitted = False
        if is_api and scope["method"] == "POST":
            admitted = self.slots.acquire(blocking=False)
            if not admitted:
                return await reject(503, "SERVER_BUSY", "Server is busy. Retry later.", retry=True)
        try:
            try:
                await self.app(scope, receive, secure_send)
            except Exception:
                if started:
                    raise  # An already-started response cannot be replaced.
                logger.error("Unexpected CSV web request failure.")
                await reject(500, "INTERNAL_ERROR", "Unable to process the request.")
        finally:
            if admitted:
                self.slots.release()
