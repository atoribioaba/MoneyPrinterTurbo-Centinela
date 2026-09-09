from __future__ import annotations

import json
from collections.abc import Callable, Iterable
from urllib.parse import urlparse
from urllib.request import Request, urlopen


DEFAULT_USER_AGENT = "ElCentinelaDelUniverso/1.0 (+scientific-data-client)"


def _validate_https_host(url: str, allowed_hosts: set[str]) -> str:
    parsed = urlparse(url)
    if parsed.scheme.lower() != "https":
        raise ValueError("scientific provider URL must use HTTPS")
    host = (parsed.hostname or "").lower()
    if not host or host not in allowed_hosts:
        raise ValueError(f"scientific provider host is not allowlisted: {host or 'missing'}")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("scientific provider URL must not contain credentials")
    return host


def fetch_json_https(
    url: str,
    *,
    allowed_hosts: Iterable[str],
    timeout_seconds: float = 15.0,
    max_bytes: int = 2_000_000,
    opener: Callable = urlopen,
) -> dict:
    """Fetch one bounded JSON document from an explicitly allowlisted HTTPS host.

    This helper deliberately performs one request and no retry/backoff loop. Provider
    adapters remain responsible for caching and user-trigger semantics. Redirects are
    accepted only when the final URL is still HTTPS and on the same explicit allowlist.
    """
    if not 1.0 <= float(timeout_seconds) <= 60.0:
        raise ValueError("timeout_seconds must be between 1 and 60")
    if not 1 <= int(max_bytes) <= 10_000_000:
        raise ValueError("max_bytes must be between 1 and 10000000")

    hosts = {str(host).strip().lower() for host in allowed_hosts if str(host).strip()}
    if not hosts:
        raise ValueError("at least one allowed host is required")
    _validate_https_host(url, hosts)

    request = Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": DEFAULT_USER_AGENT,
        },
        method="GET",
    )
    with opener(request, timeout=float(timeout_seconds)) as response:
        status = int(getattr(response, "status", 200))
        if status != 200:
            raise ValueError(f"scientific provider returned HTTP {status}")
        final_url = str(response.geturl())
        _validate_https_host(final_url, hosts)
        raw = response.read(int(max_bytes) + 1)

    if len(raw) > int(max_bytes):
        raise ValueError("scientific provider response exceeds configured byte limit")
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("scientific provider returned invalid UTF-8 JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError("scientific provider JSON root must be an object")
    return payload
