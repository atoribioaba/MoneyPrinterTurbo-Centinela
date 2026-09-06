"""Desktop OAuth boundary for manual social publication.

This module acquires short-lived user access tokens for the already-certified
manual publication path. It does not persist access tokens, refresh tokens,
client secrets, or PKCE verifiers and it never invokes a publication adapter.

Canonical policy:
    GENERAR -> REVISAR -> APROBAR -> PUBLICAR
    AUTO_PUBLICATION = False

Supported cloud-safe protocol contracts:
- YouTube / Google OAuth installed-app flow: loopback redirect + PKCE S256.
- TikTok Login Kit Desktop: loopback redirect + required PKCE S256.

Physical browser/Windows Credential Manager integration remains a PC-return task.
"""

from __future__ import annotations

import base64
import hashlib
import secrets
import threading
from dataclasses import dataclass, field
from enum import StrEnum
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse

import requests

from app.services.error_control import ErrorCategory, boundary_error, redact_secrets

AUTO_PUBLICATION = False
YOUTUBE_UPLOAD_SCOPE = "https://www.googleapis.com/auth/youtube.upload"
TIKTOK_UPLOAD_SCOPE = "video.upload"
YOUTUBE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
YOUTUBE_TOKEN_URL = "https://oauth2.googleapis.com/token"
TIKTOK_AUTH_URL = "https://www.tiktok.com/v2/auth/authorize/"
TIKTOK_TOKEN_URL = "https://open.tiktokapis.com/v2/oauth/token/"
_LOOPBACK_HOST = "127.0.0.1"
_CALLBACK_PATH = "/callback/"
_DEFAULT_TIMEOUT = (15, 60)
_PKCE_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~"


class OAuthPlatform(StrEnum):
    YOUTUBE = "youtube"
    TIKTOK = "tiktok"


@dataclass(frozen=True, slots=True)
class OAuthAuthorizationRequest:
    platform: OAuthPlatform
    authorization_url: str
    redirect_uri: str
    state: str = field(repr=False)
    code_verifier: str = field(repr=False)
    scopes: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class OAuthCallback:
    code: str = field(repr=False)
    state: str = field(repr=False)
    scopes: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class OAuthTokenSet:
    platform: OAuthPlatform
    access_token: str = field(repr=False)
    refresh_token: str = field(default="", repr=False)
    expires_in: int = 0
    refresh_expires_in: int = 0
    scopes: tuple[str, ...] = ()
    open_id: str = ""


def generate_oauth_state() -> str:
    """Return a high-entropy anti-CSRF state token."""
    return secrets.token_urlsafe(32)


def generate_code_verifier(length: int = 64) -> str:
    """Generate an RFC 7636 verifier accepted by both current desktop flows."""
    if not 43 <= length <= 128:
        raise ValueError("PKCE code_verifier length must be between 43 and 128")
    return "".join(secrets.choice(_PKCE_ALPHABET) for _ in range(length))


def _google_s256(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def _tiktok_s256(verifier: str) -> str:
    # TikTok Desktop currently specifies SHA-256 encoded as lowercase hex.
    return hashlib.sha256(verifier.encode("ascii")).hexdigest()


def _validate_loopback_redirect(redirect_uri: str) -> str:
    raw = str(redirect_uri or "").strip()
    try:
        parsed = urlparse(raw)
        port = parsed.port
    except ValueError as exc:
        raise boundary_error(
            code="oauth_redirect_invalid",
            category=ErrorCategory.VALIDATION,
            message="El redirect URI OAuth local no es válido.",
            operation="social_oauth.validate_redirect",
            component="oauth",
            cause=exc,
        ) from exc

    if (
        parsed.scheme != "http"
        or parsed.hostname != _LOOPBACK_HOST
        or port is None
        or not 1 <= port <= 65535
        or parsed.path != _CALLBACK_PATH
        or parsed.params
        or parsed.query
        or parsed.fragment
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise boundary_error(
            code="oauth_redirect_not_loopback",
            category=ErrorCategory.VALIDATION,
            message=(
                "OAuth Desktop solo admite el callback local "
                "http://127.0.0.1:<puerto>/callback/."
            ),
            operation="social_oauth.validate_redirect",
            component="oauth",
        )
    return raw


def build_youtube_desktop_authorization(
    *,
    client_id: str,
    redirect_uri: str,
    state: str | None = None,
    code_verifier: str | None = None,
) -> OAuthAuthorizationRequest:
    client = str(client_id or "").strip()
    if not client:
        raise boundary_error(
            code="youtube_oauth_client_id_missing",
            category=ErrorCategory.CONFIG,
            message="Falta el OAuth client_id de YouTube/Google.",
            operation="social_oauth.youtube.begin",
            component="youtube",
        )
    redirect = _validate_loopback_redirect(redirect_uri)
    csrf_state = str(state or generate_oauth_state()).strip()
    verifier = str(code_verifier or generate_code_verifier()).strip()
    if not csrf_state or not 43 <= len(verifier) <= 128:
        raise boundary_error(
            code="youtube_oauth_ephemeral_state_invalid",
            category=ErrorCategory.VALIDATION,
            message="El estado efímero OAuth de YouTube no es válido.",
            operation="social_oauth.youtube.begin",
            component="youtube",
        )

    query = urlencode(
        {
            "client_id": client,
            "redirect_uri": redirect,
            "response_type": "code",
            "scope": YOUTUBE_UPLOAD_SCOPE,
            "state": csrf_state,
            "code_challenge": _google_s256(verifier),
            "code_challenge_method": "S256",
        }
    )
    return OAuthAuthorizationRequest(
        platform=OAuthPlatform.YOUTUBE,
        authorization_url=f"{YOUTUBE_AUTH_URL}?{query}",
        redirect_uri=redirect,
        state=csrf_state,
        code_verifier=verifier,
        scopes=(YOUTUBE_UPLOAD_SCOPE,),
    )


def build_tiktok_desktop_authorization(
    *,
    client_key: str,
    redirect_uri: str,
    state: str | None = None,
    code_verifier: str | None = None,
) -> OAuthAuthorizationRequest:
    key = str(client_key or "").strip()
    if not key:
        raise boundary_error(
            code="tiktok_oauth_client_key_missing",
            category=ErrorCategory.CONFIG,
            message="Falta el client_key de TikTok Login Kit.",
            operation="social_oauth.tiktok.begin",
            component="tiktok",
        )
    redirect = _validate_loopback_redirect(redirect_uri)
    csrf_state = str(state or generate_oauth_state()).strip()
    verifier = str(code_verifier or generate_code_verifier()).strip()
    if not csrf_state or not 43 <= len(verifier) <= 128:
        raise boundary_error(
            code="tiktok_oauth_ephemeral_state_invalid",
            category=ErrorCategory.VALIDATION,
            message="El estado efímero OAuth de TikTok no es válido.",
            operation="social_oauth.tiktok.begin",
            component="tiktok",
        )

    query = urlencode(
        {
            "client_key": key,
            "response_type": "code",
            "scope": TIKTOK_UPLOAD_SCOPE,
            "redirect_uri": redirect,
            "state": csrf_state,
            "code_challenge": _tiktok_s256(verifier),
            "code_challenge_method": "S256",
        }
    )
    return OAuthAuthorizationRequest(
        platform=OAuthPlatform.TIKTOK,
        authorization_url=f"{TIKTOK_AUTH_URL}?{query}",
        redirect_uri=redirect,
        state=csrf_state,
        code_verifier=verifier,
        scopes=(TIKTOK_UPLOAD_SCOPE,),
    )


def _validate_callback(
    request: OAuthAuthorizationRequest,
    callback: OAuthCallback,
) -> str:
    if request.platform not in {OAuthPlatform.YOUTUBE, OAuthPlatform.TIKTOK}:
        raise boundary_error(
            code="oauth_platform_unsupported",
            category=ErrorCategory.VALIDATION,
            message="La plataforma OAuth no está soportada.",
            operation="social_oauth.validate_callback",
            component="oauth",
        )
    if not secrets.compare_digest(request.state, callback.state):
        raise boundary_error(
            code="oauth_state_mismatch",
            category=ErrorCategory.AUTH,
            message="El estado OAuth no coincide; se bloquea el intercambio de tokens.",
            operation="social_oauth.validate_callback",
            component=request.platform.value,
        )
    code = str(callback.code or "").strip()
    if not code:
        raise boundary_error(
            code="oauth_authorization_code_missing",
            category=ErrorCategory.AUTH,
            message="El callback OAuth no contiene un código de autorización.",
            operation="social_oauth.validate_callback",
            component=request.platform.value,
        )
    return code


def _oauth_post(
    session: requests.Session,
    *,
    platform: OAuthPlatform,
    url: str,
    data: dict[str, str],
) -> dict[str, Any]:
    try:
        response = session.post(
            url,
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=_DEFAULT_TIMEOUT,
        )
    except (requests.Timeout, requests.ConnectionError) as exc:
        raise boundary_error(
            code=f"{platform.value}_oauth_network_failure",
            category=ErrorCategory.NETWORK,
            message=f"No se pudo conectar con OAuth de {platform.value}.",
            operation=f"social_oauth.{platform.value}.exchange",
            component=platform.value,
            retryable=True,
            cause=exc,
        ) from exc
    except requests.RequestException as exc:
        raise boundary_error(
            code=f"{platform.value}_oauth_request_failure",
            category=ErrorCategory.NETWORK,
            message=f"La petición OAuth de {platform.value} falló.",
            operation=f"social_oauth.{platform.value}.exchange",
            component=platform.value,
            cause=exc,
        ) from exc

    try:
        payload = response.json() if response.content else {}
    except ValueError:
        payload = {}
    payload = payload if isinstance(payload, dict) else {}

    if response.status_code != HTTPStatus.OK:
        remote_message = str(
            payload.get("error_description")
            or payload.get("error")
            or payload.get("message")
            or ""
        )
        raise boundary_error(
            code=f"{platform.value}_oauth_http_{response.status_code}",
            category=(
                ErrorCategory.AUTH
                if response.status_code in {400, 401, 403}
                else ErrorCategory.UPSTREAM
            ),
            message=(
                f"OAuth de {platform.value} rechazó el intercambio "
                f"(HTTP {response.status_code}). {redact_secrets(remote_message)}"
            ).strip(),
            operation=f"social_oauth.{platform.value}.exchange",
            component=platform.value,
            retryable=response.status_code >= 500,
            details={"status_code": response.status_code},
        )
    return payload


def _scope_tuple(value: object) -> tuple[str, ...]:
    text = str(value or "").replace(",", " ")
    return tuple(dict.fromkeys(item for item in text.split() if item))


def exchange_youtube_authorization_code(
    request: OAuthAuthorizationRequest,
    callback: OAuthCallback,
    *,
    client_id: str,
    client_secret: str = "",
    session: requests.Session | None = None,
) -> OAuthTokenSet:
    if request.platform != OAuthPlatform.YOUTUBE:
        raise boundary_error(
            code="youtube_oauth_request_platform_mismatch",
            category=ErrorCategory.VALIDATION,
            message="El request OAuth no pertenece a YouTube.",
            operation="social_oauth.youtube.exchange",
            component="youtube",
        )
    code = _validate_callback(request, callback)
    client = str(client_id or "").strip()
    if not client:
        raise boundary_error(
            code="youtube_oauth_client_id_missing",
            category=ErrorCategory.CONFIG,
            message="Falta el OAuth client_id de YouTube/Google.",
            operation="social_oauth.youtube.exchange",
            component="youtube",
        )
    data = {
        "client_id": client,
        "code": code,
        "code_verifier": request.code_verifier,
        "grant_type": "authorization_code",
        "redirect_uri": request.redirect_uri,
    }
    secret = str(client_secret or "").strip()
    if secret:
        data["client_secret"] = secret
    payload = _oauth_post(
        session or requests.Session(),
        platform=OAuthPlatform.YOUTUBE,
        url=YOUTUBE_TOKEN_URL,
        data=data,
    )
    access_token = str(payload.get("access_token") or "").strip()
    if not access_token:
        raise boundary_error(
            code="youtube_oauth_access_token_missing",
            category=ErrorCategory.AUTH,
            message="Google no devolvió un access token de YouTube.",
            operation="social_oauth.youtube.exchange",
            component="youtube",
        )
    scopes = _scope_tuple(payload.get("scope"))
    if scopes and YOUTUBE_UPLOAD_SCOPE not in scopes:
        raise boundary_error(
            code="youtube_oauth_scope_missing",
            category=ErrorCategory.AUTH,
            message="El token de YouTube no incluye el scope youtube.upload requerido.",
            operation="social_oauth.youtube.exchange",
            component="youtube",
        )
    return OAuthTokenSet(
        platform=OAuthPlatform.YOUTUBE,
        access_token=access_token,
        refresh_token=str(payload.get("refresh_token") or "").strip(),
        expires_in=int(payload.get("expires_in") or 0),
        scopes=scopes or (YOUTUBE_UPLOAD_SCOPE,),
    )


def exchange_tiktok_authorization_code(
    request: OAuthAuthorizationRequest,
    callback: OAuthCallback,
    *,
    client_key: str,
    client_secret: str,
    session: requests.Session | None = None,
) -> OAuthTokenSet:
    if request.platform != OAuthPlatform.TIKTOK:
        raise boundary_error(
            code="tiktok_oauth_request_platform_mismatch",
            category=ErrorCategory.VALIDATION,
            message="El request OAuth no pertenece a TikTok.",
            operation="social_oauth.tiktok.exchange",
            component="tiktok",
        )
    code = _validate_callback(request, callback)
    key = str(client_key or "").strip()
    secret = str(client_secret or "").strip()
    if not key or not secret:
        raise boundary_error(
            code="tiktok_oauth_client_credentials_missing",
            category=ErrorCategory.CONFIG,
            message="TikTok Desktop requiere client_key y client_secret en el proceso local.",
            operation="social_oauth.tiktok.exchange",
            component="tiktok",
        )
    payload = _oauth_post(
        session or requests.Session(),
        platform=OAuthPlatform.TIKTOK,
        url=TIKTOK_TOKEN_URL,
        data={
            "client_key": key,
            "client_secret": secret,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": request.redirect_uri,
            "code_verifier": request.code_verifier,
        },
    )
    access_token = str(payload.get("access_token") or "").strip()
    scopes = _scope_tuple(payload.get("scope"))
    if not access_token:
        raise boundary_error(
            code="tiktok_oauth_access_token_missing",
            category=ErrorCategory.AUTH,
            message="TikTok no devolvió un access token.",
            operation="social_oauth.tiktok.exchange",
            component="tiktok",
        )
    if TIKTOK_UPLOAD_SCOPE not in scopes:
        raise boundary_error(
            code="tiktok_oauth_scope_missing",
            category=ErrorCategory.AUTH,
            message="El token de TikTok no incluye video.upload.",
            operation="social_oauth.tiktok.exchange",
            component="tiktok",
        )
    return OAuthTokenSet(
        platform=OAuthPlatform.TIKTOK,
        access_token=access_token,
        refresh_token=str(payload.get("refresh_token") or "").strip(),
        expires_in=int(payload.get("expires_in") or 0),
        refresh_expires_in=int(payload.get("refresh_expires_in") or 0),
        scopes=scopes,
        open_id=str(payload.get("open_id") or "").strip(),
    )


class LoopbackOAuthReceiver:
    """One-shot localhost callback receiver with strict state/path validation."""

    def __init__(self, *, expected_state: str) -> None:
        state = str(expected_state or "").strip()
        if not state:
            raise ValueError("expected_state is required")
        self._expected_state = state
        self._event = threading.Event()
        self._callback: OAuthCallback | None = None
        self._error: BaseException | None = None
        receiver = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, format: str, *args: object) -> None:  # noqa: A002
                # Never log callback URLs; they contain one-time authorization codes.
                del format, args

            def do_GET(self) -> None:  # noqa: N802
                parsed = urlparse(self.path)
                if parsed.path != _CALLBACK_PATH:
                    self.send_error(HTTPStatus.NOT_FOUND)
                    return
                params = parse_qs(parsed.query, keep_blank_values=True)
                error = str((params.get("error") or [""])[0] or "").strip()
                state = str((params.get("state") or [""])[0] or "").strip()
                code = str((params.get("code") or [""])[0] or "").strip()
                scopes = _scope_tuple((params.get("scopes") or params.get("scope") or [""])[0])
                try:
                    if error:
                        description = str(
                            (params.get("error_description") or [""])[0] or ""
                        ).strip()
                        raise boundary_error(
                            code="oauth_authorization_denied",
                            category=ErrorCategory.AUTH,
                            message=(
                                "La autorización OAuth fue cancelada o rechazada. "
                                f"{redact_secrets(description)}"
                            ).strip(),
                            operation="social_oauth.loopback_callback",
                            component="oauth",
                        )
                    if not secrets.compare_digest(receiver._expected_state, state):
                        raise boundary_error(
                            code="oauth_state_mismatch",
                            category=ErrorCategory.AUTH,
                            message="El callback OAuth no supera la validación anti-CSRF.",
                            operation="social_oauth.loopback_callback",
                            component="oauth",
                        )
                    if not code:
                        raise boundary_error(
                            code="oauth_authorization_code_missing",
                            category=ErrorCategory.AUTH,
                            message="El callback OAuth no contiene código de autorización.",
                            operation="social_oauth.loopback_callback",
                            component="oauth",
                        )
                    receiver._callback = OAuthCallback(
                        code=code,
                        state=state,
                        scopes=scopes,
                    )
                    body = (
                        "<!doctype html><meta charset='utf-8'>"
                        "<title>El Centinela del Universo</title>"
                        "<h1>Autorización recibida</h1>"
                        "<p>Ya puedes cerrar esta pestaña y volver a El Centinela.</p>"
                    ).encode("utf-8")
                    self.send_response(HTTPStatus.OK)
                except BaseException as exc:  # boundary error must reach waiting thread
                    receiver._error = exc
                    body = (
                        "<!doctype html><meta charset='utf-8'>"
                        "<title>El Centinela del Universo</title>"
                        "<h1>Autorización bloqueada</h1>"
                        "<p>Vuelve a El Centinela para revisar el error.</p>"
                    ).encode("utf-8")
                    self.send_response(HTTPStatus.BAD_REQUEST)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                receiver._event.set()

        self._server = ThreadingHTTPServer((_LOOPBACK_HOST, 0), Handler)
        self._server.daemon_threads = True
        port = int(self._server.server_address[1])
        self.redirect_uri = f"http://{_LOOPBACK_HOST}:{port}{_CALLBACK_PATH}"
        self._thread = threading.Thread(
            target=self._server.serve_forever,
            name="centinela-oauth-loopback",
            daemon=True,
        )

    def __enter__(self) -> LoopbackOAuthReceiver:
        self.start()
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        del exc_type, exc, traceback
        self.close()

    def start(self) -> None:
        if not self._thread.is_alive():
            self._thread.start()

    def wait(self, *, timeout_seconds: float = 300.0) -> OAuthCallback:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if not self._thread.is_alive():
            self.start()
        if not self._event.wait(timeout_seconds):
            raise boundary_error(
                code="oauth_callback_timeout",
                category=ErrorCategory.NETWORK,
                message="No se recibió el callback OAuth local dentro del tiempo permitido.",
                operation="social_oauth.loopback_callback",
                component="oauth",
                retryable=True,
            )
        if self._error is not None:
            raise self._error
        if self._callback is None:
            raise boundary_error(
                code="oauth_callback_missing",
                category=ErrorCategory.UNKNOWN,
                message="El callback OAuth terminó sin resultado verificable.",
                operation="social_oauth.loopback_callback",
                component="oauth",
            )
        return self._callback

    def close(self) -> None:
        self._server.shutdown()
        self._server.server_close()
        if self._thread.is_alive():
            self._thread.join(timeout=2)
