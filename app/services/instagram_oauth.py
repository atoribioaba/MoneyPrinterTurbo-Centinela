"""Fail-closed Instagram Business Login protocol boundary for Centinela.

This module implements only the protocol pieces that can be certified without a
real Meta application or browser callback endpoint:

    authorization request -> callback validation -> short-lived token
    -> long-lived token -> current professional-account identity

It deliberately does NOT start a browser, receive HTTPS callbacks, persist any
credential/token, refresh tokens in the background, or publish media.

Canonical policy:
    GENERAR -> REVISAR -> APROBAR -> PUBLICAR
    AUTO_PUBLICATION = False
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass, field
from http import HTTPStatus
from typing import Any
from urllib.parse import urlencode, urlparse

import requests

from app.services.error_control import ErrorCategory, boundary_error, redact_secrets

AUTO_PUBLICATION = False
INSTAGRAM_AUTH_URL = "https://www.instagram.com/oauth/authorize"
INSTAGRAM_SHORT_TOKEN_URL = "https://api.instagram.com/oauth/access_token"
INSTAGRAM_LONG_TOKEN_URL = "https://graph.instagram.com/access_token"
INSTAGRAM_GRAPH_HOST = "https://graph.instagram.com"
INSTAGRAM_GRAPH_VERSION = "v26.0"
INSTAGRAM_BASIC_SCOPE = "instagram_business_basic"
INSTAGRAM_CONTENT_PUBLISH_SCOPE = "instagram_business_content_publish"
INSTAGRAM_PUBLISH_SCOPES = (
    INSTAGRAM_BASIC_SCOPE,
    INSTAGRAM_CONTENT_PUBLISH_SCOPE,
)
_DEFAULT_TIMEOUT = (15, 60)


@dataclass(frozen=True, slots=True)
class InstagramAuthorizationRequest:
    authorization_url: str = field(repr=False)
    redirect_uri: str
    state: str = field(repr=False)
    scopes: tuple[str, ...] = INSTAGRAM_PUBLISH_SCOPES


@dataclass(frozen=True, slots=True)
class InstagramOAuthCallback:
    code: str = field(repr=False)
    state: str = field(repr=False)


@dataclass(frozen=True, slots=True)
class InstagramShortLivedToken:
    access_token: str = field(repr=False)
    user_id: str
    scopes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class InstagramLongLivedToken:
    access_token: str = field(repr=False)
    user_id: str
    scopes: tuple[str, ...]
    expires_in: int


@dataclass(frozen=True, slots=True)
class InstagramAccountIdentity:
    user_id: str
    username: str


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
        component="instagram",
        cause=cause,
        retryable=retryable,
        details=details,
    )


def generate_instagram_oauth_state() -> str:
    """Generate a high-entropy CSRF token for one authorization attempt."""
    return secrets.token_urlsafe(32)


def validate_instagram_redirect_uri(redirect_uri: str) -> str:
    """Require a stable HTTPS callback URI suitable for Meta registration.

    Registration itself is a Meta App Dashboard action and is not inferred here.
    Query strings/fragments/userinfo are forbidden to keep callback matching simple
    and to avoid carrying secrets in the configured redirect URI.
    """
    raw = str(redirect_uri or "").strip()
    try:
        parsed = urlparse(raw)
        port = parsed.port
    except ValueError as exc:
        raise _error(
            "instagram_oauth_redirect_invalid",
            ErrorCategory.VALIDATION,
            "El redirect URI de Instagram no es válido.",
            operation="instagram_oauth.validate_redirect",
            cause=exc,
        ) from exc

    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or (port is not None and not 1 <= port <= 65535)
    ):
        raise _error(
            "instagram_oauth_https_redirect_required",
            ErrorCategory.VALIDATION,
            "Instagram Business Login requiere un redirect URI HTTPS limpio y registrado.",
            operation="instagram_oauth.validate_redirect",
        )
    return raw


def build_instagram_business_authorization(
    *,
    client_id: str,
    redirect_uri: str,
    state: str | None = None,
) -> InstagramAuthorizationRequest:
    """Build the minimum-scope Instagram Business Login authorization request."""
    if AUTO_PUBLICATION:
        raise RuntimeError("AUTO_PUBLICATION invariant was modified")
    client = str(client_id or "").strip()
    if not client:
        raise _error(
            "instagram_oauth_client_id_missing",
            ErrorCategory.CONFIG,
            "Falta el Instagram App ID.",
            operation="instagram_oauth.begin",
        )
    redirect = validate_instagram_redirect_uri(redirect_uri)
    csrf_state = str(state or generate_instagram_oauth_state()).strip()
    if len(csrf_state) < 32:
        raise _error(
            "instagram_oauth_state_invalid",
            ErrorCategory.VALIDATION,
            "El estado anti-CSRF de Instagram no tiene suficiente entropía.",
            operation="instagram_oauth.begin",
        )

    query = urlencode(
        {
            "client_id": client,
            "redirect_uri": redirect,
            "response_type": "code",
            "scope": ",".join(INSTAGRAM_PUBLISH_SCOPES),
            "state": csrf_state,
        }
    )
    return InstagramAuthorizationRequest(
        authorization_url=f"{INSTAGRAM_AUTH_URL}?{query}",
        redirect_uri=redirect,
        state=csrf_state,
    )


def validate_instagram_callback(
    request: InstagramAuthorizationRequest,
    callback: InstagramOAuthCallback,
) -> str:
    """Validate CSRF state and return the single-use authorization code."""
    if not secrets.compare_digest(request.state, str(callback.state or "")):
        raise _error(
            "instagram_oauth_state_mismatch",
            ErrorCategory.AUTH,
            "El estado OAuth de Instagram no coincide; se bloquea el intercambio.",
            operation="instagram_oauth.callback",
        )
    code = str(callback.code or "").strip()
    if not code:
        raise _error(
            "instagram_oauth_code_missing",
            ErrorCategory.AUTH,
            "El callback de Instagram no contiene código de autorización.",
            operation="instagram_oauth.callback",
        )
    return code


def _response_payload(response: requests.Response) -> dict[str, Any]:
    try:
        payload = response.json() if response.content else {}
    except ValueError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _raise_http_error(
    response: requests.Response,
    *,
    operation: str,
) -> None:
    payload = _response_payload(response)
    remote = str(
        payload.get("error_message")
        or payload.get("error_description")
        or payload.get("error")
        or payload.get("message")
        or ""
    )
    status = int(response.status_code)
    raise _error(
        f"instagram_oauth_http_{status}",
        ErrorCategory.AUTH if status in {400, 401, 403} else ErrorCategory.UPSTREAM,
        f"Instagram rechazó OAuth (HTTP {status}). {redact_secrets(remote)}".strip(),
        operation=operation,
        retryable=status == 429 or 500 <= status <= 599,
        details={"status_code": status},
    )


def _permissions(value: object) -> tuple[str, ...]:
    if isinstance(value, (list, tuple, set)):
        raw_items = [str(item).strip() for item in value]
    else:
        text = str(value or "").replace(",", " ")
        raw_items = text.split()
    return tuple(dict.fromkeys(item for item in raw_items if item))


def _unwrap_short_token_payload(payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("access_token"):
        return payload
    data = payload.get("data")
    if isinstance(data, list) and len(data) == 1 and isinstance(data[0], dict):
        return data[0]
    return payload


def _require_publish_scopes(scopes: tuple[str, ...]) -> None:
    missing = [scope for scope in INSTAGRAM_PUBLISH_SCOPES if scope not in scopes]
    if missing:
        raise _error(
            "instagram_oauth_publish_scope_missing",
            ErrorCategory.AUTH,
            "El consentimiento de Instagram no incluye todos los permisos de publicación requeridos.",
            operation="instagram_oauth.scope_check",
            details={"missing_scopes": ",".join(missing)},
        )


def exchange_instagram_authorization_code(
    request: InstagramAuthorizationRequest,
    callback: InstagramOAuthCallback,
    *,
    client_id: str,
    client_secret: str,
    session: requests.Session | None = None,
) -> InstagramShortLivedToken:
    """Exchange one validated authorization code for a short-lived IG user token."""
    code = validate_instagram_callback(request, callback)
    client = str(client_id or "").strip()
    secret = str(client_secret or "").strip()
    if not client or not secret:
        raise _error(
            "instagram_oauth_client_credentials_missing",
            ErrorCategory.CONFIG,
            "Faltan Instagram App ID y/o Instagram App Secret.",
            operation="instagram_oauth.exchange_code",
        )

    http = session or requests.Session()
    try:
        response = http.post(
            INSTAGRAM_SHORT_TOKEN_URL,
            data={
                "client_id": client,
                "client_secret": secret,
                "grant_type": "authorization_code",
                "redirect_uri": request.redirect_uri,
                "code": code,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=_DEFAULT_TIMEOUT,
        )
    except (requests.Timeout, requests.ConnectionError) as exc:
        raise _error(
            "instagram_oauth_exchange_network_failure",
            ErrorCategory.NETWORK,
            "No se pudo conectar con el intercambio OAuth de Instagram.",
            operation="instagram_oauth.exchange_code",
            cause=exc,
            retryable=True,
        ) from exc
    except requests.RequestException as exc:
        raise _error(
            "instagram_oauth_exchange_request_failure",
            ErrorCategory.NETWORK,
            "La petición de intercambio OAuth de Instagram falló.",
            operation="instagram_oauth.exchange_code",
            cause=exc,
        ) from exc

    if response.status_code != HTTPStatus.OK:
        _raise_http_error(response, operation="instagram_oauth.exchange_code")
    payload = _unwrap_short_token_payload(_response_payload(response))
    token = str(payload.get("access_token") or "").strip()
    user_id = str(payload.get("user_id") or "").strip()
    scopes = _permissions(payload.get("permissions"))
    if not token or not user_id:
        raise _error(
            "instagram_oauth_short_token_invalid",
            ErrorCategory.AUTH,
            "Instagram no devolvió un token corto y user_id válidos.",
            operation="instagram_oauth.exchange_code",
        )
    _require_publish_scopes(scopes)
    return InstagramShortLivedToken(
        access_token=token,
        user_id=user_id,
        scopes=scopes,
    )


def exchange_instagram_long_lived_token(
    short_token: InstagramShortLivedToken,
    *,
    client_secret: str,
    session: requests.Session | None = None,
) -> InstagramLongLivedToken:
    """Exchange a short-lived Instagram user token for the ~60-day token."""
    secret = str(client_secret or "").strip()
    token = str(short_token.access_token or "").strip()
    if not secret or not token:
        raise _error(
            "instagram_oauth_long_token_inputs_missing",
            ErrorCategory.CONFIG,
            "Faltan App Secret o token corto para el intercambio de larga duración.",
            operation="instagram_oauth.exchange_long_token",
        )
    _require_publish_scopes(short_token.scopes)

    http = session or requests.Session()
    try:
        response = http.get(
            INSTAGRAM_LONG_TOKEN_URL,
            params={
                "grant_type": "ig_exchange_token",
                "client_secret": secret,
                "access_token": token,
            },
            timeout=_DEFAULT_TIMEOUT,
        )
    except (requests.Timeout, requests.ConnectionError) as exc:
        raise _error(
            "instagram_oauth_long_token_network_failure",
            ErrorCategory.NETWORK,
            "No se pudo conectar con el intercambio de token largo de Instagram.",
            operation="instagram_oauth.exchange_long_token",
            cause=exc,
            retryable=True,
        ) from exc
    except requests.RequestException as exc:
        raise _error(
            "instagram_oauth_long_token_request_failure",
            ErrorCategory.NETWORK,
            "La petición de token largo de Instagram falló.",
            operation="instagram_oauth.exchange_long_token",
            cause=exc,
        ) from exc

    if response.status_code != HTTPStatus.OK:
        _raise_http_error(response, operation="instagram_oauth.exchange_long_token")
    payload = _response_payload(response)
    long_token = str(payload.get("access_token") or "").strip()
    expires_value = payload.get("expires_in")
    if not long_token or isinstance(expires_value, bool):
        raise _error(
            "instagram_oauth_long_token_invalid",
            ErrorCategory.AUTH,
            "Instagram no devolvió un token largo válido.",
            operation="instagram_oauth.exchange_long_token",
        )
    try:
        expires_in = int(expires_value)
    except (TypeError, ValueError) as exc:
        raise _error(
            "instagram_oauth_long_token_expiry_invalid",
            ErrorCategory.UPSTREAM,
            "Instagram devolvió una expiración de token no válida.",
            operation="instagram_oauth.exchange_long_token",
            cause=exc,
        ) from exc
    if expires_in <= 0:
        raise _error(
            "instagram_oauth_long_token_expiry_invalid",
            ErrorCategory.UPSTREAM,
            "Instagram devolvió una expiración de token no válida.",
            operation="instagram_oauth.exchange_long_token",
        )
    return InstagramLongLivedToken(
        access_token=long_token,
        user_id=short_token.user_id,
        scopes=short_token.scopes,
        expires_in=expires_in,
    )


def get_instagram_account_identity(
    token: InstagramLongLivedToken,
    *,
    api_version: str = INSTAGRAM_GRAPH_VERSION,
    session: requests.Session | None = None,
) -> InstagramAccountIdentity:
    """Resolve the current Instagram professional account from the long-lived token."""
    _require_publish_scopes(token.scopes)
    access_token = str(token.access_token or "").strip()
    version = str(api_version or "").strip("/")
    if not access_token or not version:
        raise _error(
            "instagram_oauth_identity_inputs_invalid",
            ErrorCategory.CONFIG,
            "Falta token o versión Graph para verificar la cuenta de Instagram.",
            operation="instagram_oauth.identity",
        )

    http = session or requests.Session()
    try:
        response = http.get(
            f"{INSTAGRAM_GRAPH_HOST}/{version}/me",
            params={
                "fields": "user_id,username",
                "access_token": access_token,
            },
            timeout=_DEFAULT_TIMEOUT,
        )
    except (requests.Timeout, requests.ConnectionError) as exc:
        raise _error(
            "instagram_oauth_identity_network_failure",
            ErrorCategory.NETWORK,
            "No se pudo verificar la identidad de la cuenta de Instagram.",
            operation="instagram_oauth.identity",
            cause=exc,
            retryable=True,
        ) from exc
    except requests.RequestException as exc:
        raise _error(
            "instagram_oauth_identity_request_failure",
            ErrorCategory.NETWORK,
            "La verificación de identidad de Instagram falló.",
            operation="instagram_oauth.identity",
            cause=exc,
        ) from exc

    if response.status_code != HTTPStatus.OK:
        _raise_http_error(response, operation="instagram_oauth.identity")
    payload = _response_payload(response)
    user_id = str(payload.get("user_id") or payload.get("id") or "").strip()
    username = str(payload.get("username") or "").strip()
    if not user_id or not username:
        raise _error(
            "instagram_oauth_identity_invalid",
            ErrorCategory.AUTH,
            "Instagram no devolvió una identidad profesional verificable.",
            operation="instagram_oauth.identity",
        )
    if token.user_id and token.user_id != user_id:
        raise _error(
            "instagram_oauth_identity_mismatch",
            ErrorCategory.AUTH,
            "El user_id del token cambió durante la verificación de identidad.",
            operation="instagram_oauth.identity",
        )
    return InstagramAccountIdentity(user_id=user_id, username=username)
