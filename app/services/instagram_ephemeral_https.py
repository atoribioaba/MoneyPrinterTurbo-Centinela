"""Fail-closed ephemeral HTTPS transport for approved Instagram Reels.

C10 exposes exactly one approved MP4 through a short-lived HTTPS tunnel so Meta
can fetch the media while an Instagram Reel container is created and processed.
The module never publishes automatically and deliberately splits the flow into
two human actions:

1. prepare_instagram_reel(): verify package -> ephemeral HTTPS -> create container
   -> wait for FINISHED -> tear transport down.
2. publish_prepared_instagram_reel(): fresh approval -> reverify package identity
   -> media_publish.

OAuth remains outside C10. Tokens enter at the call boundary, stay in memory, and
are never persisted by this module.

Safety policy:
    GENERAR -> REVISAR -> APROBAR -> PUBLICAR
    AUTO_PUBLICATION = False
"""

from __future__ import annotations

import hashlib
import os
import queue
import re
import secrets
import shutil
import subprocess
import threading
import time
from collections.abc import Callable, Iterator, Mapping
from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from enum import StrEnum
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlsplit

import requests

from app.services.centinela.manual_publication import (
    VerifiedPublicationPackage,
    verify_publication_package,
)
from app.services.centinela.project_foundation import ArtifactStore
from app.services.error_control import (
    CentinelaError,
    ErrorCategory,
    boundary_error,
    validate_local_media_file,
)
from app.services.social_publication import InstagramAdapter, SocialResult

AUTO_PUBLICATION = False

INSTAGRAM_EPHEMERAL_HTTPS_ENABLED_ENV = (
    "CENTINELA_INSTAGRAM_EPHEMERAL_HTTPS_ENABLED"
)
INSTAGRAM_TUNNEL_PROVIDER_ENV = "CENTINELA_INSTAGRAM_TUNNEL_PROVIDER"

_LOOPBACK_HOST = "127.0.0.1"
_DEFAULT_TTL_SECONDS = 15 * 60.0
_MAX_TTL_SECONDS = 30 * 60.0
_DEFAULT_STARTUP_TIMEOUT_SECONDS = 45.0
_DEFAULT_PROCESSING_TIMEOUT_SECONDS = 5 * 60.0
_DEFAULT_POLL_INTERVAL_SECONDS = 60.0
_MAX_STATUS_CHECKS = 5
_DEFAULT_HTTP_TIMEOUT = (15.0, 120.0)
_MAX_CONNECTIONS = 8
_READ_SIZE = 1024 * 1024
_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})
_FALSE_VALUES = frozenset({"", "0", "false", "no", "off"})
_HTTPS_URL_PATTERN = re.compile(r"https://[A-Za-z0-9._~:/?#\[\]@!$&'()*+,;=%-]+")
_SINGLE_RANGE_PATTERN = re.compile(r"bytes=(\d*)-(\d*)\Z")


class InstagramTunnelProvider(StrEnum):
    CLOUDFLARE_QUICK = "cloudflare_quick"
    ZROK_PUBLIC = "zrok_public"


@dataclass(frozen=True, slots=True)
class TunnelProviderFacts:
    provider: InstagramTunnelProvider
    executable_candidates: tuple[str, ...]
    allowed_hostname_suffixes: tuple[str, ...]
    classification: str
    software_license: str
    hosted_service: str
    cost: str
    conclusion: str
    caveat: str


_PROVIDER_FACTS: dict[InstagramTunnelProvider, TunnelProviderFacts] = {
    InstagramTunnelProvider.CLOUDFLARE_QUICK: TunnelProviderFacts(
        provider=InstagramTunnelProvider.CLOUDFLARE_QUICK,
        executable_candidates=("cloudflared",),
        allowed_hostname_suffixes=(".trycloudflare.com",),
        classification="OPEN SOURCE + 100 % GRATUITA (cliente); relay propietario gratuito",
        software_license="Apache-2.0",
        hosted_service="Cloudflare TryCloudflare Quick Tunnel",
        cost="0 € / no account or API key required for Quick Tunnels",
        conclusion="PRUEBA A/B",
        caveat="Cloudflare documenta Quick Tunnels para testing/desarrollo y sin SLA.",
    ),
    InstagramTunnelProvider.ZROK_PUBLIC: TunnelProviderFacts(
        provider=InstagramTunnelProvider.ZROK_PUBLIC,
        executable_candidates=("zrok2", "zrok"),
        allowed_hostname_suffixes=(".share.zrok.io",),
        classification="OPEN SOURCE + 100 % GRATUITA",
        software_license="Apache-2.0",
        hosted_service="zrok public frontend",
        cost="0 € hosted tier sujeto a los límites vigentes del servicio",
        conclusion="PRUEBA A/B",
        caveat="Hay que verificar en PC el fetch HTTPS directo del MP4 en el frontend hosted.",
    ),
}


@dataclass(frozen=True, slots=True)
class TransportEvidence:
    provider: InstagramTunnelProvider
    public_origin: str
    public_path_sha256: str
    local_media_sha256: str
    remote_media_sha256: str
    size_bytes: int
    content_type: str
    head_status: int
    get_status: int
    range_status: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider.value,
            "public_origin": self.public_origin,
            "public_path_sha256": self.public_path_sha256,
            "local_media_sha256": self.local_media_sha256,
            "remote_media_sha256": self.remote_media_sha256,
            "size_bytes": self.size_bytes,
            "content_type": self.content_type,
            "head_status": self.head_status,
            "get_status": self.get_status,
            "range_status": self.range_status,
        }


@dataclass(frozen=True, slots=True)
class PreparedInstagramReel:
    project_id: str
    manifest_artifact_id: str
    publication_package_hash: str
    human_review_artifact_id: str
    social_video_sha256: str
    ig_user_id: str
    container_id: str
    status: str
    tunnel_provider: InstagramTunnelProvider
    transport_evidence: TransportEvidence


@dataclass(frozen=True, slots=True)
class EphemeralHttpsSettings:
    enabled: bool
    provider: InstagramTunnelProvider | None


@dataclass(frozen=True, slots=True)
class SingleFileServerAddress:
    host: str
    port: int
    route: str

    @property
    def local_origin(self) -> str:
        return f"http://{self.host}:{self.port}"

    @property
    def local_url(self) -> str:
        return f"{self.local_origin}{self.route}"


@dataclass(slots=True)
class _MediaFingerprint:
    path: Path
    sha256: str
    size_bytes: int
    mtime_ns: int


class TunnelProcess(Protocol):
    stdout: Any
    stderr: Any

    def poll(self) -> int | None: ...
    def terminate(self) -> None: ...
    def kill(self) -> None: ...
    def wait(self, timeout: float | None = None) -> int: ...


ProcessFactory = Callable[..., TunnelProcess]
Sleep = Callable[[float], None]


def _error(
    code: str,
    message: str,
    *,
    category: ErrorCategory = ErrorCategory.VALIDATION,
    component: str = "instagram_ephemeral_https",
    retryable: bool = False,
    details: dict[str, Any] | None = None,
    cause: BaseException | None = None,
) -> CentinelaError:
    return boundary_error(
        code=code,
        category=category,
        message=message,
        operation="instagram_ephemeral_https",
        component=component,
        retryable=retryable,
        details=details,
        cause=cause,
    )


def ephemeral_https_settings(
    environ: Mapping[str, str] | None = None,
) -> EphemeralHttpsSettings:
    source = os.environ if environ is None else environ
    raw_enabled = str(source.get(INSTAGRAM_EPHEMERAL_HTTPS_ENABLED_ENV, "") or "").strip().lower()
    if raw_enabled in _TRUE_VALUES:
        enabled = True
    elif raw_enabled in _FALSE_VALUES:
        enabled = False
    else:
        raise _error(
            "instagram_ephemeral_https_gate_invalid",
            f"{INSTAGRAM_EPHEMERAL_HTTPS_ENABLED_ENV} contiene un valor no válido.",
            category=ErrorCategory.CONFIG,
        )

    raw_provider = str(source.get(INSTAGRAM_TUNNEL_PROVIDER_ENV, "") or "").strip().lower()
    if not enabled:
        if raw_provider:
            try:
                provider = InstagramTunnelProvider(raw_provider)
            except ValueError:
                provider = None
        else:
            provider = None
        return EphemeralHttpsSettings(enabled=False, provider=provider)

    if not raw_provider:
        raise _error(
            "instagram_tunnel_provider_missing",
            f"Falta {INSTAGRAM_TUNNEL_PROVIDER_ENV} para habilitar el transporte de Instagram.",
            category=ErrorCategory.CONFIG,
        )
    try:
        provider = InstagramTunnelProvider(raw_provider)
    except ValueError as exc:
        raise _error(
            "instagram_tunnel_provider_invalid",
            "El proveedor de túnel HTTPS de Instagram no está soportado.",
            category=ErrorCategory.CONFIG,
            cause=exc,
        ) from exc
    return EphemeralHttpsSettings(enabled=True, provider=provider)


def tunnel_provider_facts(
    provider: InstagramTunnelProvider | str,
) -> TunnelProviderFacts:
    try:
        normalized = InstagramTunnelProvider(provider)
    except ValueError as exc:
        raise _error(
            "instagram_tunnel_provider_invalid",
            "El proveedor de túnel HTTPS de Instagram no está soportado.",
            category=ErrorCategory.CONFIG,
            cause=exc,
        ) from exc
    return _PROVIDER_FACTS[normalized]


def iter_tunnel_provider_audit_rows() -> Iterator[dict[str, str]]:
    """Yield stable rows for the final open-source pipeline audit."""
    for provider in (
        InstagramTunnelProvider.CLOUDFLARE_QUICK,
        InstagramTunnelProvider.ZROK_PUBLIC,
    ):
        facts = _PROVIDER_FACTS[provider]
        yield {
            "provider": provider.value,
            "classification": facts.classification,
            "software_license": facts.software_license,
            "hosted_service": facts.hosted_service,
            "cost": facts.cost,
            "conclusion": facts.conclusion,
            "caveat": facts.caveat,
        }


def _sha256_file(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(_READ_SIZE), b""):
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


def _media_fingerprint(path: Path, expected_sha256: str) -> _MediaFingerprint:
    normalized = validate_local_media_file(
        path,
        operation="instagram_ephemeral_https.validate_media",
        allowed_extensions={".mp4"},
        max_size_bytes=1024**3,
    )
    try:
        stat = normalized.stat()
        actual_sha, actual_size = _sha256_file(normalized)
    except OSError as exc:
        raise _error(
            "instagram_ephemeral_media_unreadable",
            "No se pudo verificar el MP4 aprobado antes de exponerlo.",
            category=ErrorCategory.FILESYSTEM,
            cause=exc,
        ) from exc
    if actual_sha.lower() != str(expected_sha256 or "").strip().lower():
        raise _error(
            "instagram_ephemeral_media_hash_mismatch",
            "El MP4 ya no coincide con el SHA-256 del paquete aprobado.",
        )
    if actual_size != stat.st_size:
        raise _error(
            "instagram_ephemeral_media_size_changed",
            "El tamaño del MP4 cambió durante su verificación.",
        )
    return _MediaFingerprint(
        path=normalized,
        sha256=actual_sha.lower(),
        size_bytes=actual_size,
        mtime_ns=stat.st_mtime_ns,
    )


def _fingerprint_unchanged(media: _MediaFingerprint) -> bool:
    try:
        stat = media.path.stat()
    except OSError:
        return False
    return stat.st_size == media.size_bytes and stat.st_mtime_ns == media.mtime_ns


class _LimitedThreadingHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    request_queue_size = _MAX_CONNECTIONS
    allow_reuse_address = False


class EphemeralSingleFileServer(AbstractContextManager["EphemeralSingleFileServer"]):
    """Serve one immutable approved MP4 on 127.0.0.1 with GET/HEAD/Range only."""

    def __init__(
        self,
        media_path: str | Path,
        *,
        expected_sha256: str,
        ttl_seconds: float = _DEFAULT_TTL_SECONDS,
    ) -> None:
        if not 0 < ttl_seconds <= _MAX_TTL_SECONDS:
            raise ValueError("ttl_seconds must be > 0 and <= 1800")
        self._media = _media_fingerprint(Path(media_path), expected_sha256)
        self._ttl_seconds = float(ttl_seconds)
        self._token = secrets.token_urlsafe(32)
        self._route = f"/{self._token}/social_1080x1920.mp4"
        self._httpd: _LimitedThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None
        self._started_monotonic: float | None = None
        self._semaphore = threading.BoundedSemaphore(_MAX_CONNECTIONS)

    @property
    def address(self) -> SingleFileServerAddress:
        if self._httpd is None:
            raise RuntimeError("ephemeral server is not running")
        host, port = self._httpd.server_address[:2]
        return SingleFileServerAddress(host=str(host), port=int(port), route=self._route)

    @property
    def public_path_sha256(self) -> str:
        return hashlib.sha256(self._route.encode("utf-8")).hexdigest()

    def _expired(self) -> bool:
        if self._started_monotonic is None:
            return True
        return (time.monotonic() - self._started_monotonic) >= self._ttl_seconds

    def _handler_class(self):
        parent = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"
            server_version = "CentinelaEphemeral/1"
            sys_version = ""

            def log_message(self, format: str, *args: Any) -> None:
                del format, args

            def _reject(self, status: HTTPStatus) -> None:
                self.send_response(status)
                self.send_header("Content-Length", "0")
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.end_headers()

            def _common_headers(self, *, content_length: int) -> None:
                self.send_header("Content-Type", "video/mp4")
                self.send_header("Content-Length", str(content_length))
                self.send_header("Accept-Ranges", "bytes")
                self.send_header("Cache-Control", "no-store, max-age=0")
                self.send_header("X-Content-Type-Options", "nosniff")

            def _eligible(self) -> bool:
                split = urlsplit(self.path)
                if split.query or split.fragment or split.path != parent._route:
                    self._reject(HTTPStatus.NOT_FOUND)
                    return False
                if parent._expired():
                    self._reject(HTTPStatus.GONE)
                    return False
                if not _fingerprint_unchanged(parent._media):
                    self._reject(HTTPStatus.CONFLICT)
                    return False
                return True

            def _parse_range(self) -> tuple[int, int] | None:
                raw = str(self.headers.get("Range") or "").strip()
                if not raw:
                    return None
                match = _SINGLE_RANGE_PATTERN.fullmatch(raw)
                if not match:
                    return (-1, -1)
                first_raw, last_raw = match.groups()
                size = parent._media.size_bytes
                if not first_raw:
                    if not last_raw:
                        return (-1, -1)
                    suffix = int(last_raw)
                    if suffix <= 0:
                        return (-1, -1)
                    start = max(0, size - suffix)
                    return start, size - 1
                start = int(first_raw)
                if start >= size:
                    return (-1, -1)
                end = int(last_raw) if last_raw else size - 1
                if end < start:
                    return (-1, -1)
                return start, min(end, size - 1)

            def _serve(self, *, body: bool) -> None:
                if not parent._semaphore.acquire(blocking=False):
                    self._reject(HTTPStatus.SERVICE_UNAVAILABLE)
                    return
                try:
                    if not self._eligible():
                        return
                    byte_range = self._parse_range()
                    if byte_range == (-1, -1):
                        self.send_response(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE)
                        self.send_header(
                            "Content-Range", f"bytes */{parent._media.size_bytes}"
                        )
                        self.send_header("Content-Length", "0")
                        self.send_header("Cache-Control", "no-store")
                        self.end_headers()
                        return

                    if byte_range is None:
                        start = 0
                        end = parent._media.size_bytes - 1
                        status = HTTPStatus.OK
                    else:
                        start, end = byte_range
                        status = HTTPStatus.PARTIAL_CONTENT
                    length = end - start + 1

                    self.send_response(status)
                    self._common_headers(content_length=length)
                    if status == HTTPStatus.PARTIAL_CONTENT:
                        self.send_header(
                            "Content-Range",
                            f"bytes {start}-{end}/{parent._media.size_bytes}",
                        )
                    self.end_headers()
                    if not body:
                        return

                    try:
                        with parent._media.path.open("rb") as handle:
                            handle.seek(start)
                            remaining = length
                            while remaining > 0:
                                chunk = handle.read(min(_READ_SIZE, remaining))
                                if not chunk:
                                    raise OSError("unexpected EOF while serving approved MP4")
                                self.wfile.write(chunk)
                                remaining -= len(chunk)
                    except (BrokenPipeError, ConnectionResetError):
                        return
                finally:
                    parent._semaphore.release()

            def do_HEAD(self) -> None:  # noqa: N802
                self._serve(body=False)

            def do_GET(self) -> None:  # noqa: N802
                self._serve(body=True)

            def do_POST(self) -> None:  # noqa: N802
                self._reject(HTTPStatus.METHOD_NOT_ALLOWED)

            def do_PUT(self) -> None:  # noqa: N802
                self._reject(HTTPStatus.METHOD_NOT_ALLOWED)

            def do_DELETE(self) -> None:  # noqa: N802
                self._reject(HTTPStatus.METHOD_NOT_ALLOWED)

        return Handler

    def __enter__(self) -> "EphemeralSingleFileServer":
        if self._httpd is not None:
            return self
        try:
            self._httpd = _LimitedThreadingHTTPServer(
                (_LOOPBACK_HOST, 0),
                self._handler_class(),
            )
        except OSError as exc:
            raise _error(
                "instagram_ephemeral_loopback_bind_failed",
                "No se pudo abrir el servidor local efímero en 127.0.0.1.",
                category=ErrorCategory.NETWORK,
                cause=exc,
            ) from exc
        self._started_monotonic = time.monotonic()
        self._thread = threading.Thread(
            target=self._httpd.serve_forever,
            name="centinela-instagram-ephemeral-http",
            daemon=True,
        )
        self._thread.start()
        return self

    def close(self) -> None:
        httpd, thread = self._httpd, self._thread
        self._httpd = None
        self._thread = None
        if httpd is not None:
            httpd.shutdown()
            httpd.server_close()
        if thread is not None and thread.is_alive():
            thread.join(timeout=5.0)

    def __exit__(self, exc_type, exc, traceback) -> None:
        del exc_type, exc, traceback
        self.close()


@dataclass(slots=True)
class EphemeralTunnel(AbstractContextManager["EphemeralTunnel"]):
    provider: InstagramTunnelProvider
    local_origin: str
    startup_timeout_seconds: float = _DEFAULT_STARTUP_TIMEOUT_SECONDS
    process_factory: ProcessFactory = subprocess.Popen
    executable: str = ""
    public_origin: str = ""
    _process: TunnelProcess | None = field(default=None, init=False, repr=False)

    def _resolve_executable(self) -> str:
        facts = tunnel_provider_facts(self.provider)
        if self.executable:
            resolved = shutil.which(self.executable)
            if resolved:
                return resolved
            raise _error(
                "instagram_tunnel_executable_missing",
                f"No se encontró el ejecutable configurado para {self.provider.value}.",
                category=ErrorCategory.DEPENDENCY,
                details={"provider": self.provider.value},
            )
        for candidate in facts.executable_candidates:
            resolved = shutil.which(candidate)
            if resolved:
                return resolved
        raise _error(
            "instagram_tunnel_executable_missing",
            f"No se encontró el ejecutable necesario para {self.provider.value}.",
            category=ErrorCategory.DEPENDENCY,
            details={
                "provider": self.provider.value,
                "candidates": list(facts.executable_candidates),
            },
        )

    def _command(self, executable: str) -> list[str]:
        split = urlsplit(self.local_origin)
        if split.scheme != "http" or split.hostname != _LOOPBACK_HOST or split.port is None:
            raise _error(
                "instagram_tunnel_local_origin_invalid",
                "El túnel solo puede apuntar al servidor local 127.0.0.1.",
            )
        if self.provider == InstagramTunnelProvider.CLOUDFLARE_QUICK:
            return [
                executable,
                "tunnel",
                "--url",
                self.local_origin,
                "--no-autoupdate",
            ]
        backend = f"{split.hostname}:{split.port}"
        return [executable, "share", "public", backend]

    def _accepted_public_origin(self, candidate: str) -> str | None:
        split = urlsplit(candidate.strip().rstrip(".,);]"))
        facts = tunnel_provider_facts(self.provider)
        if (
            split.scheme.lower() != "https"
            or not split.hostname
            or split.username
            or split.password
            or split.query
            or split.fragment
        ):
            return None
        hostname = split.hostname.lower()
        if not any(
            hostname == suffix.lstrip(".") or hostname.endswith(suffix)
            for suffix in facts.allowed_hostname_suffixes
        ):
            return None
        if split.path not in {"", "/"}:
            return None
        return f"https://{split.netloc}"

    def __enter__(self) -> "EphemeralTunnel":
        if self.startup_timeout_seconds <= 0:
            raise ValueError("startup_timeout_seconds must be positive")
        executable = self._resolve_executable()
        command = self._command(executable)
        try:
            self._process = self.process_factory(
                command,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
            )
        except (OSError, ValueError) as exc:
            raise _error(
                "instagram_tunnel_start_failed",
                f"No se pudo iniciar {self.provider.value}.",
                category=ErrorCategory.SUBPROCESS,
                cause=exc,
            ) from exc

        if self._process.stdout is None:
            self.close()
            raise _error(
                "instagram_tunnel_output_missing",
                "El proceso de túnel no expone salida para descubrir su URL HTTPS.",
                category=ErrorCategory.SUBPROCESS,
            )

        output_queue: queue.Queue[str | None] = queue.Queue()

        def reader() -> None:
            try:
                for line in self._process.stdout:
                    output_queue.put(str(line))
            finally:
                output_queue.put(None)

        threading.Thread(
            target=reader,
            name="centinela-instagram-tunnel-output",
            daemon=True,
        ).start()

        deadline = time.monotonic() + self.startup_timeout_seconds
        try:
            while time.monotonic() < deadline:
                if self._process.poll() is not None:
                    raise _error(
                        "instagram_tunnel_exited_early",
                        f"{self.provider.value} terminó antes de publicar una URL HTTPS.",
                        category=ErrorCategory.SUBPROCESS,
                    )
                try:
                    line = output_queue.get(
                        timeout=min(0.25, max(0.01, deadline - time.monotonic()))
                    )
                except queue.Empty:
                    continue
                if line is None:
                    continue
                for match in _HTTPS_URL_PATTERN.findall(line):
                    accepted = self._accepted_public_origin(match)
                    if accepted:
                        self.public_origin = accepted
                        return self
            raise _error(
                "instagram_tunnel_start_timeout",
                f"{self.provider.value} no publicó una URL HTTPS a tiempo.",
                category=ErrorCategory.SUBPROCESS,
                retryable=True,
            )
        except Exception:
            self.close()
            raise

    def close(self) -> None:
        process = self._process
        self._process = None
        if process is None:
            return
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5.0)
            except (subprocess.TimeoutExpired, TimeoutError):
                process.kill()
                try:
                    process.wait(timeout=5.0)
                except Exception:
                    pass

    def __exit__(self, exc_type, exc, traceback) -> None:
        del exc_type, exc, traceback
        self.close()


def _public_media_url(
    tunnel: EphemeralTunnel,
    server: EphemeralSingleFileServer,
) -> str:
    if not tunnel.public_origin:
        raise _error(
            "instagram_tunnel_public_origin_missing",
            "El túnel no tiene una URL pública HTTPS verificada.",
        )
    return f"{tunnel.public_origin}{server.address.route}"


def _validate_remote_transport(
    *,
    public_url: str,
    provider: InstagramTunnelProvider,
    expected_sha256: str,
    expected_size: int,
    public_path_sha256: str,
    session: requests.Session | None = None,
) -> TransportEvidence:
    split = urlsplit(public_url)
    facts = tunnel_provider_facts(provider)
    if (
        split.scheme.lower() != "https"
        or not split.hostname
        or split.username
        or split.password
        or split.query
        or split.fragment
        or not any(
            split.hostname.lower() == suffix.lstrip(".")
            or split.hostname.lower().endswith(suffix)
            for suffix in facts.allowed_hostname_suffixes
        )
    ):
        raise _error(
            "instagram_public_url_untrusted",
            "La URL pública no pertenece al proveedor HTTPS seleccionado.",
        )

    client = session or requests.Session()

    def request(method: str, **kwargs: Any) -> requests.Response:
        try:
            return client.request(
                method,
                public_url,
                timeout=_DEFAULT_HTTP_TIMEOUT,
                allow_redirects=False,
                **kwargs,
            )
        except (requests.Timeout, requests.ConnectionError) as exc:
            raise _error(
                "instagram_transport_probe_network_failed",
                "No se pudo verificar el MP4 a través del túnel HTTPS.",
                category=ErrorCategory.NETWORK,
                retryable=True,
                cause=exc,
            ) from exc
        except requests.RequestException as exc:
            raise _error(
                "instagram_transport_probe_failed",
                "La verificación HTTPS del MP4 falló.",
                category=ErrorCategory.NETWORK,
                cause=exc,
            ) from exc

    head = request("HEAD")
    if head.status_code != HTTPStatus.OK:
        raise _error(
            "instagram_transport_head_invalid",
            f"El HEAD público devolvió HTTP {head.status_code}.",
            category=ErrorCategory.UPSTREAM,
        )
    head_length = str(head.headers.get("Content-Length") or "")
    head_type = str(head.headers.get("Content-Type") or "").split(";", 1)[0].strip().lower()
    if head_length != str(expected_size) or head_type != "video/mp4":
        raise _error(
            "instagram_transport_head_identity_mismatch",
            "El HEAD público no coincide con tamaño/tipo del MP4 aprobado.",
        )

    response = request("GET", stream=True)
    if response.status_code != HTTPStatus.OK:
        response.close()
        raise _error(
            "instagram_transport_get_invalid",
            f"El GET público devolvió HTTP {response.status_code}.",
            category=ErrorCategory.UPSTREAM,
        )
    digest = hashlib.sha256()
    total = 0
    try:
        for chunk in response.iter_content(chunk_size=_READ_SIZE):
            if not chunk:
                continue
            total += len(chunk)
            if total > expected_size:
                raise _error(
                    "instagram_transport_size_overflow",
                    "El recurso público supera el tamaño del MP4 aprobado.",
                )
            digest.update(chunk)
    finally:
        response.close()
    remote_sha = digest.hexdigest().lower()
    if total != expected_size or remote_sha != expected_sha256.lower():
        raise _error(
            "instagram_transport_hash_mismatch",
            "Los bytes recuperados por HTTPS no coinciden con el MP4 aprobado.",
            details={"expected_size": expected_size, "actual_size": total},
        )

    range_response = request("GET", headers={"Range": "bytes=0-0"}, stream=True)
    try:
        if range_response.status_code != HTTPStatus.PARTIAL_CONTENT:
            raise _error(
                "instagram_transport_range_invalid",
                f"El Range público devolvió HTTP {range_response.status_code}.",
                category=ErrorCategory.UPSTREAM,
            )
        content_range = str(range_response.headers.get("Content-Range") or "").strip()
        if content_range != f"bytes 0-0/{expected_size}":
            raise _error(
                "instagram_transport_range_identity_mismatch",
                "El Content-Range público no coincide con el MP4 aprobado.",
            )
        first = b"".join(range_response.iter_content(chunk_size=8))
        if len(first) != 1:
            raise _error(
                "instagram_transport_range_length_invalid",
                "La respuesta Range no devolvió exactamente un byte.",
            )
    finally:
        range_response.close()

    public_origin = f"https://{split.netloc}"
    return TransportEvidence(
        provider=provider,
        public_origin=public_origin,
        public_path_sha256=public_path_sha256,
        local_media_sha256=expected_sha256.lower(),
        remote_media_sha256=remote_sha,
        size_bytes=expected_size,
        content_type="video/mp4",
        head_status=int(head.status_code),
        get_status=int(HTTPStatus.OK),
        range_status=int(HTTPStatus.PARTIAL_CONTENT),
    )


def _same_verified_package(
    package: VerifiedPublicationPackage,
    prepared: PreparedInstagramReel,
) -> bool:
    return (
        package.project_id == prepared.project_id
        and package.manifest_artifact_id == prepared.manifest_artifact_id
        and package.publication_package_hash == prepared.publication_package_hash
        and package.human_review_artifact_id == prepared.human_review_artifact_id
        and package.social_video_sha256 == prepared.social_video_sha256
    )


def prepare_instagram_reel(
    store: ArtifactStore,
    project_id: str,
    *,
    ig_user_id: str,
    access_token: str,
    approved: bool = False,
    provider: InstagramTunnelProvider | str | None = None,
    environ: Mapping[str, str] | None = None,
    ttl_seconds: float = _DEFAULT_TTL_SECONDS,
    processing_timeout_seconds: float = _DEFAULT_PROCESSING_TIMEOUT_SECONDS,
    poll_interval_seconds: float = _DEFAULT_POLL_INTERVAL_SECONDS,
    instagram_adapter: InstagramAdapter | None = None,
    remote_session: requests.Session | None = None,
    server_factory: Callable[..., AbstractContextManager[EphemeralSingleFileServer]] = EphemeralSingleFileServer,
    tunnel_factory: Callable[..., AbstractContextManager[EphemeralTunnel]] = EphemeralTunnel,
    sleep: Sleep = time.sleep,
) -> PreparedInstagramReel:
    """Create and fully process an Instagram container, but never call media_publish."""
    if AUTO_PUBLICATION:
        raise RuntimeError("AUTO_PUBLICATION invariant was modified")
    if not approved:
        raise _error(
            "human_approval_required",
            "Preparar Instagram requiere una aprobación humana nueva y explícita.",
            component="instagram",
        )
    if not 0 < processing_timeout_seconds <= _DEFAULT_PROCESSING_TIMEOUT_SECONDS:
        raise ValueError("processing_timeout_seconds must be > 0 and <= 300")
    if poll_interval_seconds < _DEFAULT_POLL_INTERVAL_SECONDS:
        raise ValueError("poll_interval_seconds must be >= 60")

    settings = ephemeral_https_settings(environ)
    if not settings.enabled:
        raise _error(
            "instagram_ephemeral_https_disabled",
            "El transporte HTTPS efímero de Instagram está desactivado.",
            category=ErrorCategory.CONFIG,
            component="instagram",
        )
    if provider is None:
        resolved_provider = settings.provider
    else:
        try:
            resolved_provider = InstagramTunnelProvider(provider)
        except ValueError as exc:
            raise _error(
                "instagram_tunnel_provider_invalid",
                "El proveedor de túnel HTTPS de Instagram no está soportado.",
                category=ErrorCategory.CONFIG,
                component="instagram",
                cause=exc,
            ) from exc
        if settings.provider is not None and resolved_provider != settings.provider:
            raise _error(
                "instagram_tunnel_provider_mismatch",
                "El proveedor solicitado no coincide con la configuración habilitada.",
                category=ErrorCategory.CONFIG,
                component="instagram",
            )
    if resolved_provider is None:
        raise _error(
            "instagram_tunnel_provider_missing",
            "No hay proveedor de túnel HTTPS habilitado para Instagram.",
            category=ErrorCategory.CONFIG,
            component="instagram",
        )

    user_id = str(ig_user_id or "").strip()
    token = str(access_token or "").strip()
    if not user_id:
        raise _error(
            "instagram_user_id_missing",
            "Falta el ID de la cuenta profesional de Instagram.",
            category=ErrorCategory.CONFIG,
            component="instagram",
        )
    if not token:
        raise _error(
            "instagram_access_token_missing",
            "Falta el token efímero para preparar el Reel.",
            category=ErrorCategory.AUTH,
            component="instagram",
        )

    adapter = instagram_adapter or InstagramAdapter()
    package = verify_publication_package(store, project_id)
    fingerprint = _media_fingerprint(
        package.social_video_path,
        package.social_video_sha256,
    )

    try:
        with server_factory(
            fingerprint.path,
            expected_sha256=fingerprint.sha256,
            ttl_seconds=ttl_seconds,
        ) as server:
            with tunnel_factory(
                resolved_provider,
                server.address.local_origin,
            ) as tunnel:
                public_url = _public_media_url(tunnel, server)
                evidence = _validate_remote_transport(
                    public_url=public_url,
                    provider=resolved_provider,
                    expected_sha256=fingerprint.sha256,
                    expected_size=fingerprint.size_bytes,
                    public_path_sha256=server.public_path_sha256,
                    session=remote_session,
                )
                current_package = verify_publication_package(store, project_id)
                if (
                    current_package.manifest_artifact_id != package.manifest_artifact_id
                    or current_package.publication_package_hash
                    != package.publication_package_hash
                    or current_package.social_video_sha256
                    != package.social_video_sha256
                ):
                    raise _error(
                        "instagram_package_changed_before_container",
                        "El paquete cambió antes de crear el contenedor de Instagram.",
                        component="instagram",
                    )

                container = adapter.create_reel_container(
                    ig_user_id=user_id,
                    access_token=token,
                    video_url=public_url,
                    caption=package.metadata.caption,
                    approved=True,
                )
                container_id = str(container.remote_id or "").strip()
                if not container_id:
                    raise _error(
                        "instagram_container_missing",
                        "Instagram no devolvió un contenedor válido.",
                        category=ErrorCategory.UPSTREAM,
                        component="instagram",
                    )

                deadline = time.monotonic() + processing_timeout_seconds
                status = adapter.get_container_status(
                    container_id,
                    access_token=token,
                )
                status_checks = 1
                while (
                    status.status == "IN_PROGRESS"
                    and status_checks < _MAX_STATUS_CHECKS
                    and time.monotonic() < deadline
                ):
                    sleep(poll_interval_seconds)
                    status = adapter.get_container_status(
                        container_id,
                        access_token=token,
                    )
                    status_checks += 1
                if status.status != "FINISHED":
                    retryable = status.status == "IN_PROGRESS"
                    raise _error(
                        "instagram_container_processing_failed",
                        f"El contenedor de Instagram terminó en estado {status.status}.",
                        category=ErrorCategory.UPSTREAM,
                        component="instagram",
                        retryable=retryable,
                        details={"status": status.status},
                    )

                final_package = verify_publication_package(store, project_id)
                if (
                    final_package.manifest_artifact_id != package.manifest_artifact_id
                    or final_package.publication_package_hash
                    != package.publication_package_hash
                    or final_package.social_video_sha256
                    != package.social_video_sha256
                ):
                    raise _error(
                        "instagram_package_changed_during_processing",
                        "El paquete cambió mientras Instagram procesaba el contenedor.",
                        component="instagram",
                    )

                return PreparedInstagramReel(
                    project_id=package.project_id,
                    manifest_artifact_id=package.manifest_artifact_id,
                    publication_package_hash=package.publication_package_hash,
                    human_review_artifact_id=package.human_review_artifact_id,
                    social_video_sha256=package.social_video_sha256,
                    ig_user_id=user_id,
                    container_id=container_id,
                    status=status.status,
                    tunnel_provider=resolved_provider,
                    transport_evidence=evidence,
                )
    finally:
        token = ""


def publish_prepared_instagram_reel(
    store: ArtifactStore,
    prepared: PreparedInstagramReel,
    *,
    access_token: str,
    approved: bool = False,
    instagram_adapter: InstagramAdapter | None = None,
) -> SocialResult:
    """Publish a bound FINISHED container after a fresh second human action."""
    if AUTO_PUBLICATION:
        raise RuntimeError("AUTO_PUBLICATION invariant was modified")
    if not approved:
        raise _error(
            "human_approval_required",
            "media_publish requiere una aprobación humana nueva y explícita.",
            component="instagram",
        )

    token = str(access_token or "").strip()
    if not token:
        raise _error(
            "instagram_access_token_missing",
            "Falta el token efímero para publicar el Reel preparado.",
            category=ErrorCategory.AUTH,
            component="instagram",
        )
    if (
        prepared.status != "FINISHED"
        or not prepared.container_id
        or not prepared.ig_user_id
    ):
        raise _error(
            "instagram_prepared_container_invalid",
            "El contenedor preparado no conserva el estado/identidad necesarios.",
            component="instagram",
        )

    package = verify_publication_package(store, prepared.project_id)
    if not _same_verified_package(package, prepared):
        raise _error(
            "instagram_prepared_package_identity_mismatch",
            "El contenedor no pertenece al paquete aprobado vigente.",
            component="instagram",
        )

    adapter = instagram_adapter or InstagramAdapter()
    try:
        return adapter.publish_reel(
            ig_user_id=prepared.ig_user_id,
            container_id=prepared.container_id,
            access_token=token,
            approved=True,
        )
    finally:
        token = ""
