"""Stable HTTPS callback transport for Instagram Business Login.

C12 intentionally keeps Instagram's OAuth callback transport separate from the
C8/C9 HTTP loopback flows used by YouTube and TikTok. Instagram receives a
stable, pre-registered HTTPS redirect URI while the actual receiver remains a
one-shot HTTP server bound only to 127.0.0.1. Tailscale Funnel terminates public
TLS only for the duration of the explicit authentication action.

The default flow is:

    explicit caller action
      -> local one-shot receiver on 127.0.0.1
      -> temporary Tailscale Funnel on stable *.ts.net:443
      -> system browser / Instagram Business Login
      -> state-validated callback
      -> Funnel OFF + local receiver closed
      -> short-lived token exchange

No long-lived token is requested by this module, no token or application secret
is persisted, and this module never publishes media.

Canonical policy:
    GENERAR -> REVISAR -> APROBAR -> PUBLICAR
    AUTO_PUBLICATION = False
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import threading
import webbrowser
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Protocol
from urllib.parse import parse_qs, urlsplit

import requests

from app.services.error_control import ErrorCategory, boundary_error, redact_secrets
from app.services.instagram_oauth import (
    InstagramOAuthCallback,
    InstagramShortLivedToken,
    build_instagram_business_authorization,
    exchange_instagram_authorization_code,
    validate_instagram_redirect_uri,
)

AUTO_PUBLICATION = False
INSTAGRAM_CALLBACK_ENABLED_ENV = "CENTINELA_INSTAGRAM_OAUTH_CALLBACK_ENABLED"
INSTAGRAM_CALLBACK_PROVIDER_ENV = "CENTINELA_INSTAGRAM_OAUTH_CALLBACK_PROVIDER"
INSTAGRAM_CLIENT_ID_ENV = "CENTINELA_INSTAGRAM_OAUTH_CLIENT_ID"
INSTAGRAM_CLIENT_SECRET_ENV = "CENTINELA_INSTAGRAM_OAUTH_CLIENT_SECRET"
INSTAGRAM_REDIRECT_URI_ENV = "CENTINELA_INSTAGRAM_OAUTH_REDIRECT_URI"
TAILSCALE_PROVIDER = "tailscale_funnel"
INSTAGRAM_CALLBACK_PATH = "/instagram/oauth/callback"
_CALLBACK_HOST = "127.0.0.1"
_PUBLIC_HTTPS_PORT = 443
_MAX_CALLBACK_ATTEMPTS = 5
_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})
_FALSE_VALUES = frozenset({"", "0", "false", "no", "off"})


@dataclass(frozen=True, slots=True)
class InstagramCallbackCredentials:
    client_id: str = field(repr=False)
    client_secret: str = field(repr=False)
    redirect_uri: str
    provider: str = TAILSCALE_PROVIDER


@dataclass(frozen=True, slots=True)
class InstagramCallbackSessionResult:
    token: InstagramShortLivedToken = field(repr=False)
    provider: str


@dataclass(frozen=True, slots=True)
class CliResult:
    returncode: int
    stdout: str = ""
    stderr: str = ""


class CommandRunner(Protocol):
    def __call__(self, argv: list[str], timeout_seconds: float) -> CliResult: ...


class ReceiverProtocol(Protocol):
    port: int

    def __enter__(self) -> ReceiverProtocol: ...

    def __exit__(self, exc_type, exc, traceback) -> None: ...

    def wait(self, *, timeout_seconds: float = 300.0) -> InstagramOAuthCallback: ...


class BridgeProtocol(Protocol):
    def start(self) -> None: ...

    def stop(self) -> None: ...


BrowserOpen = Callable[[str], bool]
ReceiverFactory = Callable[..., ReceiverProtocol]
BridgeFactory = Callable[..., BridgeProtocol]
TokenExchange = Callable[..., InstagramShortLivedToken]


def _error(
    code: str,
    category: ErrorCategory,
    message: str,
    *,
    operation: str,
    cause: BaseException | None = None,
    retryable: bool = False,
    details: dict[str, Any] | None = None,
):
    return boundary_error(
        code=code,
        category=category,
        message=message,
        operation=operation,
        component="instagram_oauth_callback",
        cause=cause,
        retryable=retryable,
        details=details,
    )


def instagram_callback_enabled(environ: Mapping[str, str] | None = None) -> bool:
    """Fail closed unless the Instagram HTTPS callback boundary is explicit."""
    source = os.environ if environ is None else environ
    value = str(source.get(INSTAGRAM_CALLBACK_ENABLED_ENV, "")).strip().lower()
    if value in _TRUE_VALUES:
        return True
    if value in _FALSE_VALUES:
        return False
    raise _error(
        "instagram_callback_gate_invalid",
        ErrorCategory.CONFIG,
        (
            f"{INSTAGRAM_CALLBACK_ENABLED_ENV} debe ser 1/true/yes/on o "
            "0/false/no/off."
        ),
        operation="instagram_oauth_callback.config",
    )


def validate_tailscale_instagram_redirect_uri(redirect_uri: str) -> str:
    """Require the one stable public callback shape certified for C12."""
    raw = validate_instagram_redirect_uri(redirect_uri)
    parsed = urlsplit(raw)
    host = (parsed.hostname or "").lower()
    if (
        not host.endswith(".ts.net")
        or host == ".ts.net"
        or parsed.port not in {None, _PUBLIC_HTTPS_PORT}
        or parsed.path != INSTAGRAM_CALLBACK_PATH
    ):
        raise _error(
            "instagram_callback_tailscale_redirect_invalid",
            ErrorCategory.VALIDATION,
            (
                "El callback Tailscale de Instagram debe usar "
                f"https://<dispositivo>.<tailnet>.ts.net{INSTAGRAM_CALLBACK_PATH}."
            ),
            operation="instagram_oauth_callback.validate_redirect",
        )
    return raw


def load_instagram_callback_credentials(
    *,
    environ: Mapping[str, str] | None = None,
) -> InstagramCallbackCredentials:
    """Read runtime configuration without exposing or persisting credentials."""
    if AUTO_PUBLICATION:
        raise RuntimeError("AUTO_PUBLICATION invariant was modified")
    if not instagram_callback_enabled(environ):
        raise _error(
            "instagram_callback_disabled",
            ErrorCategory.CONFIG,
            "El callback HTTPS de Instagram está desactivado.",
            operation="instagram_oauth_callback.config",
        )
    source = os.environ if environ is None else environ
    provider = str(source.get(INSTAGRAM_CALLBACK_PROVIDER_ENV, "")).strip().lower()
    if provider != TAILSCALE_PROVIDER:
        raise _error(
            "instagram_callback_provider_unsupported",
            ErrorCategory.CONFIG,
            "C12 requiere seleccionar explícitamente tailscale_funnel.",
            operation="instagram_oauth_callback.config",
        )
    client_id = str(source.get(INSTAGRAM_CLIENT_ID_ENV, "")).strip()
    client_secret = str(source.get(INSTAGRAM_CLIENT_SECRET_ENV, "")).strip()
    redirect_uri = str(source.get(INSTAGRAM_REDIRECT_URI_ENV, "")).strip()
    if not client_id or not client_secret or not redirect_uri:
        raise _error(
            "instagram_callback_credentials_missing",
            ErrorCategory.CONFIG,
            (
                "Faltan Instagram App ID, App Secret o redirect URI en el proceso local."
            ),
            operation="instagram_oauth_callback.config",
        )
    return InstagramCallbackCredentials(
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri=validate_tailscale_instagram_redirect_uri(redirect_uri),
    )


def callback_runtime_status(
    *,
    environ: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Return only secret-free readiness information for Product UI."""
    try:
        enabled = instagram_callback_enabled(environ)
        gate_valid = True
    except Exception:
        enabled = False
        gate_valid = False
    configured = False
    if enabled and gate_valid:
        try:
            load_instagram_callback_credentials(environ=environ)
        except Exception:
            configured = False
        else:
            configured = True
    return {
        "enabled": enabled,
        "gate_valid": gate_valid,
        "provider": TAILSCALE_PROVIDER if configured else "",
        "configured": configured,
        "token_persistence": False,
        "long_lived_token_default": False,
        "auto_publication": False,
    }


def _callback_failure(
    code: str,
    message: str,
    *,
    category: ErrorCategory = ErrorCategory.AUTH,
):
    return _error(
        code,
        category,
        message,
        operation="instagram_oauth_callback.receive",
    )


class InstagramOneShotCallbackReceiver:
    """One-shot, state-bound HTTP receiver intended only behind HTTPS Funnel."""

    def __init__(
        self,
        *,
        expected_state: str,
        callback_path: str = INSTAGRAM_CALLBACK_PATH,
        max_attempts: int = _MAX_CALLBACK_ATTEMPTS,
    ) -> None:
        state = str(expected_state or "")
        if len(state) < 32:
            raise ValueError("expected_state must contain at least 32 characters")
        if callback_path != INSTAGRAM_CALLBACK_PATH:
            raise ValueError("callback_path must use the canonical Instagram callback path")
        if not 1 <= max_attempts <= 20:
            raise ValueError("max_attempts must be between 1 and 20")
        self.expected_state = state
        self.callback_path = callback_path
        self.max_attempts = max_attempts
        self._event = threading.Event()
        self._callback: InstagramOAuthCallback | None = None
        self._failure: BaseException | None = None
        self._attempts = 0
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None
        self.port = 0

    def __enter__(self) -> InstagramOneShotCallbackReceiver:
        receiver = self

        class Handler(BaseHTTPRequestHandler):
            server_version = "CentinelaInstagramCallback/1"
            sys_version = ""

            def log_message(self, format: str, *args: object) -> None:
                # Query strings contain OAuth codes/state and must never hit logs.
                return

            def _reply(self, status: HTTPStatus, body: str) -> None:
                payload = body.encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.send_header("Content-Length", str(len(payload)))
                self.send_header("Cache-Control", "no-store")
                self.send_header("Pragma", "no-cache")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.end_headers()
                self.wfile.write(payload)

            def do_GET(self) -> None:
                parsed = urlsplit(self.path)
                if parsed.path != receiver.callback_path:
                    self._reply(HTTPStatus.NOT_FOUND, "Not found")
                    return
                receiver._attempts += 1
                query = parse_qs(parsed.query, keep_blank_values=True)
                state_values = query.get("state", [])
                code_values = query.get("code", [])
                error_values = query.get("error", [])

                if error_values:
                    receiver._failure = _callback_failure(
                        "instagram_callback_vendor_denied",
                        "Instagram devolvió una cancelación o error de autorización.",
                    )
                    receiver._event.set()
                    self._reply(HTTPStatus.BAD_REQUEST, "Authorization was not completed.")
                    return

                valid_shape = len(state_values) == 1 and len(code_values) == 1
                state = state_values[0] if len(state_values) == 1 else ""
                code = code_values[0] if len(code_values) == 1 else ""
                state_ok = bool(state) and secrets_compare(receiver.expected_state, state)
                if not valid_shape or not state_ok or not code:
                    if receiver._attempts >= receiver.max_attempts:
                        receiver._failure = _callback_failure(
                            "instagram_callback_attempt_limit",
                            "Se agotó el límite de callbacks OAuth inválidos.",
                        )
                        receiver._event.set()
                    self._reply(HTTPStatus.BAD_REQUEST, "Invalid OAuth callback.")
                    return

                receiver._callback = InstagramOAuthCallback(code=code, state=state)
                receiver._event.set()
                self._reply(
                    HTTPStatus.OK,
                    "Instagram autorizado. Puedes volver a EL CENTINELA DEL UNIVERSO.",
                )

            def do_POST(self) -> None:
                self._reply(HTTPStatus.METHOD_NOT_ALLOWED, "Method not allowed")

            def do_HEAD(self) -> None:
                self.send_response(HTTPStatus.METHOD_NOT_ALLOWED)
                self.send_header("Content-Length", "0")
                self.end_headers()

        try:
            server = ThreadingHTTPServer((_CALLBACK_HOST, 0), Handler)
            server.daemon_threads = True
        except OSError as exc:
            raise _error(
                "instagram_callback_loopback_unavailable",
                ErrorCategory.NETWORK,
                "No se pudo abrir el receptor local de Instagram en 127.0.0.1.",
                operation="instagram_oauth_callback.receive",
                cause=exc,
            ) from exc
        self._server = server
        self.port = int(server.server_address[1])
        thread = threading.Thread(
            target=server.serve_forever,
            name="centinela-instagram-oauth-callback",
            daemon=True,
        )
        self._thread = thread
        thread.start()
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        server = self._server
        thread = self._thread
        self._server = None
        self._thread = None
        if server is not None:
            server.shutdown()
            server.server_close()
        if thread is not None:
            thread.join(timeout=2.0)

    def wait(self, *, timeout_seconds: float = 300.0) -> InstagramOAuthCallback:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if not self._event.wait(timeout_seconds):
            raise _callback_failure(
                "instagram_callback_timeout",
                "No llegó un callback válido de Instagram dentro del tiempo permitido.",
                category=ErrorCategory.NETWORK,
            )
        if self._failure is not None:
            if isinstance(self._failure, Exception):
                raise self._failure
            raise RuntimeError("Instagram callback failed")
        if self._callback is None:
            raise _callback_failure(
                "instagram_callback_missing",
                "El callback de Instagram terminó sin un código válido.",
            )
        return self._callback


def secrets_compare(expected: str, actual: str) -> bool:
    """Small wrapper kept injectable/testable without exposing state values."""
    import secrets

    try:
        return secrets.compare_digest(expected, actual)
    except TypeError:
        return False


def _default_command_runner(argv: list[str], timeout_seconds: float) -> CliResult:
    try:
        completed = subprocess.run(
            argv,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            stdin=subprocess.DEVNULL,
            shell=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise _error(
            "tailscale_cli_timeout",
            ErrorCategory.SUBPROCESS,
            "Tailscale no respondió dentro del tiempo permitido.",
            operation="instagram_oauth_callback.tailscale",
            cause=exc,
            retryable=True,
        ) from exc
    except OSError as exc:
        raise _error(
            "tailscale_cli_execution_failed",
            ErrorCategory.SUBPROCESS,
            "No se pudo ejecutar el cliente de Tailscale.",
            operation="instagram_oauth_callback.tailscale",
            cause=exc,
        ) from exc
    return CliResult(
        returncode=int(completed.returncode),
        stdout=str(completed.stdout or ""),
        stderr=str(completed.stderr or ""),
    )


def _safe_cli_error(result: CliResult) -> str:
    text = result.stderr.strip() or result.stdout.strip()
    return redact_secrets(text[:500]) if text else ""


def _json_cli(result: CliResult, *, code: str, operation: str) -> dict[str, Any]:
    if result.returncode != 0:
        raise _error(
            code,
            ErrorCategory.SUBPROCESS,
            "Tailscale rechazó una comprobación local requerida.",
            operation=operation,
            details={"cli_message": _safe_cli_error(result)},
        )
    try:
        payload = json.loads(result.stdout or "{}")
    except json.JSONDecodeError as exc:
        raise _error(
            f"{code}_json_invalid",
            ErrorCategory.UPSTREAM,
            "Tailscale devolvió un estado JSON no válido.",
            operation=operation,
            cause=exc,
        ) from exc
    if not isinstance(payload, dict):
        raise _error(
            f"{code}_shape_invalid",
            ErrorCategory.UPSTREAM,
            "Tailscale devolvió un estado con formato inesperado.",
            operation=operation,
        )
    return payload


def _funnel_handler(
    payload: Mapping[str, Any],
    *,
    host: str,
) -> Mapping[str, Any] | None:
    web = payload.get("Web")
    if not isinstance(web, Mapping):
        return None
    server = web.get(f"{host}:{_PUBLIC_HTTPS_PORT}")
    if not isinstance(server, Mapping):
        return None
    handlers = server.get("Handlers")
    if not isinstance(handlers, Mapping):
        return None
    root = handlers.get("/")
    return root if isinstance(root, Mapping) else None


class TailscaleFunnelBridge:
    """Temporarily expose one local callback server through stable Funnel HTTPS."""

    def __init__(
        self,
        *,
        local_port: int,
        redirect_uri: str | None = None,
        executable: str | None = None,
        runner: CommandRunner = _default_command_runner,
        command_timeout_seconds: float = 15.0,
    ) -> None:
        if not 1 <= int(local_port) <= 65535:
            raise ValueError("local_port must be between 1 and 65535")
        if command_timeout_seconds <= 0:
            raise ValueError("command_timeout_seconds must be positive")
        self.local_port = int(local_port)
        self.redirect_uri = (
            validate_tailscale_instagram_redirect_uri(redirect_uri)
            if redirect_uri is not None
            else ""
        )
        self.host = (urlsplit(self.redirect_uri).hostname or "").lower() if self.redirect_uri else ""
        self.executable = executable or shutil.which("tailscale") or ""
        self.runner = runner
        self.command_timeout_seconds = command_timeout_seconds
        self._active = False

    @property
    def public_origin(self) -> str:
        return f"https://{self.host}" if self.host else ""

    def _run(self, args: list[str]) -> CliResult:
        if not self.executable:
            raise _error(
                "tailscale_cli_missing",
                ErrorCategory.DEPENDENCY,
                "No se encuentra el ejecutable tailscale en PATH.",
                operation="instagram_oauth_callback.tailscale",
            )
        return self.runner(
            [self.executable, *args],
            self.command_timeout_seconds,
        )

    def _node_status(self) -> dict[str, Any]:
        return _json_cli(
            self._run(["status", "--json"]),
            code="tailscale_status_failed",
            operation="instagram_oauth_callback.tailscale_status",
        )

    def _funnel_status(self) -> dict[str, Any]:
        return _json_cli(
            self._run(["funnel", "status", "--json"]),
            code="tailscale_funnel_status_failed",
            operation="instagram_oauth_callback.funnel_status",
        )

    def _preflight(self) -> None:
        status = self._node_status()
        if str(status.get("BackendState") or "") != "Running":
            raise _error(
                "tailscale_not_running",
                ErrorCategory.CONFIG,
                "Tailscale debe estar conectado antes de iniciar Instagram OAuth.",
                operation="instagram_oauth_callback.tailscale_preflight",
            )
        own = status.get("Self")
        dns_name = ""
        if isinstance(own, Mapping):
            dns_name = str(own.get("DNSName") or "").strip().rstrip(".").lower()
        if not dns_name or not dns_name.endswith(".ts.net"):
            raise _error(
                "tailscale_dns_identity_missing",
                ErrorCategory.VALIDATION,
                "Tailscale no devolvió un hostname *.ts.net verificable para este nodo.",
                operation="instagram_oauth_callback.tailscale_preflight",
            )
        if self.host and dns_name != self.host:
            raise _error(
                "tailscale_dns_identity_mismatch",
                ErrorCategory.VALIDATION,
                "El hostname del redirect de Instagram no coincide con este nodo Tailscale.",
                operation="instagram_oauth_callback.tailscale_preflight",
            )
        if not self.host:
            self.host = dns_name

        existing = _funnel_handler(self._funnel_status(), host=self.host)
        if existing is not None:
            raise _error(
                "tailscale_funnel_443_in_use",
                ErrorCategory.CONFIG,
                "Ya existe un Funnel HTTPS en 443; C12 no sobrescribirá configuración previa.",
                operation="instagram_oauth_callback.tailscale_preflight",
            )

    def start(self) -> None:
        if self._active:
            raise RuntimeError("Tailscale Funnel bridge is already active")
        self._preflight()
        target = f"http://{_CALLBACK_HOST}:{self.local_port}"
        result = self._run(
            ["funnel", "--bg", f"--https={_PUBLIC_HTTPS_PORT}", target]
        )
        if result.returncode != 0:
            raise _error(
                "tailscale_funnel_start_failed",
                ErrorCategory.SUBPROCESS,
                (
                    "No se pudo iniciar Tailscale Funnel. Debe estar habilitado y "
                    "autorizado previamente en el tailnet."
                ),
                operation="instagram_oauth_callback.funnel_start",
                details={"cli_message": _safe_cli_error(result)},
            )
        self._active = True

        status = self._funnel_status()
        handler = _funnel_handler(status, host=self.host)
        expected_proxy = target
        if handler is None or str(handler.get("Proxy") or "") != expected_proxy:
            try:
                self.stop()
            except BaseException as cleanup_exc:
                raise _error(
                    "tailscale_funnel_cleanup_failed_after_route_mismatch",
                    ErrorCategory.SUBPROCESS,
                    "El route de Funnel era inválido y además no se confirmó su cierre.",
                    operation="instagram_oauth_callback.funnel_start",
                    cause=cleanup_exc,
                ) from cleanup_exc
            raise _error(
                "tailscale_funnel_route_unverified",
                ErrorCategory.UPSTREAM,
                "Tailscale Funnel no confirmó el proxy HTTPS esperado.",
                operation="instagram_oauth_callback.funnel_start",
            )

        allowed = status.get("AllowFunnel")
        if not isinstance(allowed, Mapping) or allowed.get(
            f"{self.host}:{_PUBLIC_HTTPS_PORT}"
        ) is not True:
            try:
                self.stop()
            except BaseException as cleanup_exc:
                raise _error(
                    "tailscale_funnel_cleanup_failed_after_public_mismatch",
                    ErrorCategory.SUBPROCESS,
                    "Funnel no confirmó exposición pública y tampoco su cierre posterior.",
                    operation="instagram_oauth_callback.funnel_start",
                    cause=cleanup_exc,
                ) from cleanup_exc
            raise _error(
                "tailscale_funnel_public_not_confirmed",
                ErrorCategory.UPSTREAM,
                "Tailscale no confirmó que el endpoint esté expuesto mediante Funnel.",
                operation="instagram_oauth_callback.funnel_start",
            )

    def stop(self) -> None:
        if not self._active:
            return
        result = self._run(
            ["funnel", f"--https={_PUBLIC_HTTPS_PORT}", "off"]
        )
        if result.returncode != 0:
            raise _error(
                "tailscale_funnel_stop_failed",
                ErrorCategory.SUBPROCESS,
                "No se pudo cerrar el Funnel temporal de Instagram.",
                operation="instagram_oauth_callback.funnel_stop",
                details={"cli_message": _safe_cli_error(result)},
            )
        if _funnel_handler(self._funnel_status(), host=self.host) is not None:
            raise _error(
                "tailscale_funnel_still_active",
                ErrorCategory.UPSTREAM,
                "Tailscale sigue mostrando el Funnel de Instagram como activo.",
                operation="instagram_oauth_callback.funnel_stop",
            )
        self._active = False


def _open_system_browser(url: str) -> bool:
    return bool(webbrowser.open(url, new=2, autoraise=True))


def _default_receiver_factory(**kwargs: Any) -> InstagramOneShotCallbackReceiver:
    return InstagramOneShotCallbackReceiver(**kwargs)


def _default_bridge_factory(**kwargs: Any) -> TailscaleFunnelBridge:
    return TailscaleFunnelBridge(**kwargs)


def authorize_instagram_via_stable_https(
    *,
    environ: Mapping[str, str] | None = None,
    browser_open: BrowserOpen | None = None,
    receiver_factory: ReceiverFactory = _default_receiver_factory,
    bridge_factory: BridgeFactory = _default_bridge_factory,
    token_exchange: TokenExchange = exchange_instagram_authorization_code,
    session: requests.Session | None = None,
    timeout_seconds: float = 300.0,
    tailscale_executable: str | None = None,
    command_runner: CommandRunner = _default_command_runner,
) -> InstagramCallbackSessionResult:
    """Authenticate once and return only a short-lived token in memory.

    The public Funnel and local callback receiver are both closed before the code
    is exchanged for an access token. The caller is responsible for the separate
    publication approval boundary; authentication is never permission to publish.
    """
    if AUTO_PUBLICATION:
        raise RuntimeError("AUTO_PUBLICATION invariant was modified")
    if timeout_seconds <= 0 or timeout_seconds > 600:
        raise ValueError("timeout_seconds must be > 0 and <= 600")

    credentials = load_instagram_callback_credentials(environ=environ)
    request = build_instagram_business_authorization(
        client_id=credentials.client_id,
        redirect_uri=credentials.redirect_uri,
    )
    opener = browser_open or _open_system_browser

    receiver_context = receiver_factory(
        expected_state=request.state,
        callback_path=INSTAGRAM_CALLBACK_PATH,
    )
    with receiver_context as receiver:
        bridge = bridge_factory(
            local_port=receiver.port,
            redirect_uri=credentials.redirect_uri,
            executable=tailscale_executable,
            runner=command_runner,
        )
        bridge.start()
        callback: InstagramOAuthCallback | None = None
        primary_error: BaseException | None = None
        try:
            try:
                opened = bool(opener(request.authorization_url))
            except Exception as exc:
                raise _error(
                    "instagram_callback_browser_failed",
                    ErrorCategory.UPSTREAM,
                    "No se pudo abrir Instagram Business Login en el navegador.",
                    operation="instagram_oauth_callback.authorize",
                    cause=exc,
                ) from exc
            if not opened:
                raise _error(
                    "instagram_callback_browser_not_opened",
                    ErrorCategory.UPSTREAM,
                    "El navegador no confirmó la apertura de Instagram Business Login.",
                    operation="instagram_oauth_callback.authorize",
                )
            callback = receiver.wait(timeout_seconds=timeout_seconds)
        except BaseException as exc:
            primary_error = exc
        try:
            bridge.stop()
        except BaseException as cleanup_exc:
            if primary_error is not None:
                raise _error(
                    "instagram_callback_cleanup_failed_after_error",
                    ErrorCategory.SUBPROCESS,
                    (
                        "La autenticación falló y además no se pudo confirmar el cierre "
                        "del Funnel temporal."
                    ),
                    operation="instagram_oauth_callback.authorize",
                    cause=primary_error,
                    details={"cleanup_error": type(cleanup_exc).__name__},
                ) from cleanup_exc
            raise
        if primary_error is not None:
            raise primary_error
        if callback is None:
            raise _error(
                "instagram_callback_missing_after_wait",
                ErrorCategory.AUTH,
                "Instagram OAuth terminó sin callback verificable.",
                operation="instagram_oauth_callback.authorize",
            )

    # Receiver + public Funnel are now closed before the external token exchange.
    token = token_exchange(
        request,
        callback,
        client_id=credentials.client_id,
        client_secret=credentials.client_secret,
        session=session,
    )
    return InstagramCallbackSessionResult(
        token=token,
        provider=TAILSCALE_PROVIDER,
    )


def callback_transport_audit() -> list[dict[str, Any]]:
    """Truthful cost/licence snapshot used by docs/UI without selecting paid SaaS."""
    return [
        {
            "provider": "Tailscale Funnel",
            "classification": "FREEMIUM + CLIENTE MAYORITARIAMENTE OSS",
            "cost": "0 € en plan Personal",
            "stable_https": True,
            "own_domain_required": False,
            "account_required": True,
            "current_decision": "CANDIDATO PRINCIPAL / PRUEBA PC",
        },
        {
            "provider": "zrok hosted public",
            "classification": "OPEN SOURCE + SERVICIO HOSTED GRATUITO",
            "cost": "0 €",
            "stable_https": True,
            "own_domain_required": False,
            "account_required": True,
            "current_decision": "NO PRINCIPAL PARA OAUTH",
            "caveat": "Free sin tarjeta puede mostrar interstitial anti-phishing.",
        },
        {
            "provider": "Cloudflare Named Tunnel",
            "classification": "CLIENTE OSS + SERVICIO PROPIETARIO",
            "cost": "Tunnel 0 €, dominio propio no garantizado a coste 0",
            "stable_https": True,
            "own_domain_required": True,
            "account_required": True,
            "current_decision": "NO COMPENSA COMO DEFAULT 0 €",
        },
    ]
