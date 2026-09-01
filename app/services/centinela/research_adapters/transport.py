from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlsplit

import requests

from .contracts import ResearchContext, ResearchDataError


DEFAULT_TIMEOUT_SECONDS = 20.0
DEFAULT_JSON_LIMIT_BYTES = 8 * 1024 * 1024
DEFAULT_BINARY_LIMIT_BYTES = 256 * 1024 * 1024


class RequestsResearchTransport:
    """C3-bounded HTTP transport: RESEARCH only, HTTPS only, host allowlist."""

    def __init__(
        self,
        *,
        allowed_hosts: set[str] | frozenset[str],
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        json_limit_bytes: int = DEFAULT_JSON_LIMIT_BYTES,
        binary_limit_bytes: int = DEFAULT_BINARY_LIMIT_BYTES,
    ) -> None:
        self.allowed_hosts = frozenset(host.casefold() for host in allowed_hosts)
        self.timeout_seconds = max(0.1, float(timeout_seconds))
        self.json_limit_bytes = max(1024, int(json_limit_bytes))
        self.binary_limit_bytes = max(1024, int(binary_limit_bytes))

    def _validate_url(self, context: ResearchContext, url: str) -> None:
        context.require_research()
        parsed = urlsplit(str(url or "").strip())
        if parsed.scheme != "https" or not parsed.hostname:
            raise ResearchDataError("research transport requires an HTTPS URL")
        if parsed.username is not None or parsed.password is not None:
            raise ResearchDataError("credentials in research URLs are forbidden")
        if parsed.hostname.casefold() not in self.allowed_hosts:
            raise ResearchDataError(f"research host is not allow-listed: {parsed.hostname}")

    @staticmethod
    def _headers(extra: Mapping[str, str] | None = None) -> dict[str, str]:
        headers = {
            "Accept": "application/json",
            "User-Agent": "El-Centinela-del-Universo/ResearchAdapter-v0.1",
        }
        if extra:
            headers.update({str(k): str(v) for k, v in extra.items()})
        return headers

    def get_json(
        self,
        context: ResearchContext,
        url: str,
        *,
        params: Mapping[str, Any] | None = None,
        json_body: Any | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> Any:
        self._validate_url(context, url)
        try:
            response = requests.get(
                url,
                params=dict(params or {}),
                json=json_body,
                headers=self._headers(headers),
                timeout=self.timeout_seconds,
                allow_redirects=False,
            )
        except requests.RequestException as exc:
            raise ResearchDataError("research HTTP request failed") from exc

        if 300 <= response.status_code < 400:
            raise ResearchDataError("redirects are forbidden for research adapters")
        if response.status_code < 200 or response.status_code >= 300:
            raise ResearchDataError(
                f"research source returned HTTP {response.status_code}"
            )

        raw = response.content
        if len(raw) > self.json_limit_bytes:
            raise ResearchDataError("research JSON response exceeds size limit")
        try:
            return response.json()
        except (ValueError, json.JSONDecodeError) as exc:
            raise ResearchDataError("research source did not return valid JSON") from exc

    def download(
        self,
        context: ResearchContext,
        url: str,
        destination: str | Path,
        *,
        headers: Mapping[str, str] | None = None,
    ) -> tuple[str, int]:
        """Download an already selected public asset atomically during RESEARCH only."""
        self._validate_url(context, url)
        path = Path(destination)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(path.name + ".part")
        total = 0
        digest = hashlib.sha256()

        try:
            with requests.get(
                url,
                headers=self._headers(headers),
                timeout=self.timeout_seconds,
                allow_redirects=False,
                stream=True,
            ) as response:
                if 300 <= response.status_code < 400:
                    raise ResearchDataError("redirects are forbidden for media download")
                if response.status_code < 200 or response.status_code >= 300:
                    raise ResearchDataError(
                        f"media source returned HTTP {response.status_code}"
                    )
                with temporary.open("wb") as handle:
                    for chunk in response.iter_content(chunk_size=1024 * 1024):
                        if not chunk:
                            continue
                        total += len(chunk)
                        if total > self.binary_limit_bytes:
                            raise ResearchDataError("media download exceeds size limit")
                        digest.update(chunk)
                        handle.write(chunk)
                    handle.flush()
                    os.fsync(handle.fileno())
            os.replace(temporary, path)
        except Exception:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
            raise

        return digest.hexdigest(), total
