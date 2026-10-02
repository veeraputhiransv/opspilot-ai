"""SSRF-safe outbound HTTP for adapters."""

from urllib.parse import urlparse

import httpx

from app.core.errors import PolicyViolation

ALLOWED_HOSTS = {
    "api.github.com",
    "hooks.slack.com",
    "slack.com",
}


def assert_public_https(url: str, extra_hosts: set[str] | None = None) -> None:
    parsed = urlparse(url)
    if parsed.scheme != "https":
        raise PolicyViolation("Integration URL must use HTTPS.")
    host = (parsed.hostname or "").lower()
    allowed = ALLOWED_HOSTS | (extra_hosts or set())
    if host not in allowed and not host.endswith(".slack.com"):
        raise PolicyViolation(f"Integration host is not allowlisted: {host}")
    if host in {"localhost", "127.0.0.1", "0.0.0.0", "::1"}:
        raise PolicyViolation("Integration URL cannot target loopback.")


async def request_json(
    method: str,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    json: dict | None = None,
    params: dict | None = None,
    extra_hosts: set[str] | None = None,
) -> dict | list:
    assert_public_https(url, extra_hosts)
    async with httpx.AsyncClient(timeout=15, follow_redirects=False) as client:
        response = await client.request(method, url, headers=headers, json=json, params=params)
        response.raise_for_status()
        if not response.content:
            return {"status_code": response.status_code}
        return response.json()
