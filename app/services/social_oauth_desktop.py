"""Ephemeral system-browser orchestration for Centinela social OAuth.

C9 composes the protocol primitives from :mod:`app.services.social_oauth` into a
single desktop interaction:

    explicit UI action -> localhost receiver -> system browser -> OAuth callback
    -> token exchange -> in-memory token result

Nothing in this module persists access tokens, refresh tokens, PKCE state,
client secrets, or publication approval. It also does not publish media.
"""

from __future__ import annotations

import os
import webbrowser
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol

import requests

from app.services.error_control import ErrorCategory, boundary_error
from app.services.social_oauth import (
    LoopbackOAuthReceiver,
    OAuthPlatform,
    OAuthTokenSet,
    build_tiktok_desktop_authorization,
    build_youtube_desktop_authorization,
    exchange_tiktok_authorization_code,
    exchange_youtube_authorization_code,
    generate_code_verifier,
    generate_oauth_state,
)

AUTO_PUBLICATION = False
DESKTOP_OAUTH_ENABLED_ENV = "CENTINELA_DESKTOP_OAUTH_ENABLED"
YOUTUBE_CLIENT_ID_ENV = "CENTINELA_YOUTUBE_OAUTH_CLIENT_ID"
YOUTUBE_CLIENT_SECRET_ENV = "CENTINELA_YOUTUBE_OAUTH_CLIENT_SECRET"
TIKTOK_CLIENT_KEY_ENV = "CENTINELA_TIKTOK_CLIENT_KEY"
TIKTOK_CLIENT_SECRET_ENV = "CENTINELA_TIKTOK_CLIENT_SECRET"

_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})
_FALSE_VALUES = frozenset({"", "0", "false", "no", "off"})


class _Receiver(Protocol):
    redirect_uri: str

    def __enter__(self) -> _Receiver: ...

    def __exit__(self, exc_type, exc, traceback) -> None: ...

    def wait(self, *, timeout_seconds: float = 300.0): ...


ReceiverFactory = Callable[..., _Receiver]
BrowserOpen = Callable[[str], bool]


@dataclass(frozen=True, slots=True)
class DesktopOAuthCredentials:
    """Runtime-only application credentials; secrets never appear in repr."""

    platform: OAuthPlatform
    client_identifier: str = field(repr=False)
    client_secret: str = field(default="", repr=False)


@dataclass(frozen=True, slots=True)
class DesktopOAuthSessionResult:
    """Successful ephemeral OAuth result returned to the caller in memory only."""

    token: OAuthTokenSet = field(repr=False)
    platform: OAuthPlatform


def _blocked(
    code: str,
    message: str,
    *,
    component: str = "desktop_oauth",
    cause: BaseException | None = None,
):
    return boundary_error(
        code=code,
        category=ErrorCategory.CONFIG,
        message=message,
        operation="social_oauth_desktop.authorize",
        component=component,
        cause=cause,
    )


def desktop_oauth_enabled(environ: Mapping[str, str] | None = None) -> bool:
    """Fail closed unless the local desktop OAuth boundary is explicitly enabled."""
    source = os.environ if environ is None else environ
    raw = str(source.get(DESKTOP_OAUTH_ENABLED_ENV, "")).strip().lower()
    if raw in _TRUE_VALUES:
        return True
    if raw in _FALSE_VALUES:
        return False
    raise _blocked(
        "desktop_oauth_gate_invalid",
        (
            f"{DESKTOP_OAUTH_ENABLED_ENV} debe ser 1/true/yes/on o "
            "0/false/no/off."
        ),
    )


def load_desktop_oauth_credentials(
    platform: OAuthPlatform | str,
    *,
    environ: Mapping[str, str] | None = None,
) -> DesktopOAuthCredentials:
    """Read application credentials from process environment without persisting them."""
    if AUTO_PUBLICATION:
        raise RuntimeError("AUTO_PUBLICATION invariant was modified")
    if not desktop_oauth_enabled(environ):
        raise _blocked(
            "desktop_oauth_disabled",
            "OAuth Desktop está desactivado en este entorno.",
        )

    try:
        normalized = OAuthPlatform(platform)
    except ValueError as exc:
        raise _blocked(
            "desktop_oauth_platform_unsupported",
            "La plataforma OAuth Desktop solicitada no está soportada.",
            cause=exc,
        ) from exc

    source = os.environ if environ is None else environ
    if normalized == OAuthPlatform.YOUTUBE:
        client_id = str(source.get(YOUTUBE_CLIENT_ID_ENV, "")).strip()
        client_secret = str(source.get(YOUTUBE_CLIENT_SECRET_ENV, "")).strip()
        if not client_id:
            raise _blocked(
                "youtube_desktop_oauth_not_configured",
                f"Falta {YOUTUBE_CLIENT_ID_ENV} en el proceso local.",
                component="youtube",
            )
        return DesktopOAuthCredentials(
            platform=normalized,
            client_identifier=client_id,
            client_secret=client_secret,
        )

    client_key = str(source.get(TIKTOK_CLIENT_KEY_ENV, "")).strip()
    client_secret = str(source.get(TIKTOK_CLIENT_SECRET_ENV, "")).strip()
    if not client_key or not client_secret:
        raise _blocked(
            "tiktok_desktop_oauth_not_configured",
            (
                f"Faltan {TIKTOK_CLIENT_KEY_ENV} y/o "
                f"{TIKTOK_CLIENT_SECRET_ENV} en el proceso local."
            ),
            component="tiktok",
        )
    return DesktopOAuthCredentials(
        platform=normalized,
        client_identifier=client_key,
        client_secret=client_secret,
    )


def _open_system_browser(url: str) -> bool:
    """Open the vendor authorization URL without copying it to logs or UI."""
    return bool(webbrowser.open(url, new=2, autoraise=True))


def authorize_desktop(
    platform: OAuthPlatform | str,
    *,
    environ: Mapping[str, str] | None = None,
    browser_open: BrowserOpen | None = None,
    receiver_factory: ReceiverFactory = LoopbackOAuthReceiver,
    session: requests.Session | None = None,
    timeout_seconds: float = 300.0,
) -> DesktopOAuthSessionResult:
    """Run one explicit browser OAuth session and return its token in memory.

    The caller remains responsible for the separate publication approval gate.
    OAuth consent is authentication, never authorization to publish.
    """
    if AUTO_PUBLICATION:
        raise RuntimeError("AUTO_PUBLICATION invariant was modified")
    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be positive")

    credentials = load_desktop_oauth_credentials(platform, environ=environ)
    state = generate_oauth_state()
    verifier = generate_code_verifier()
    opener = browser_open or _open_system_browser

    try:
        receiver_context = receiver_factory(expected_state=state)
    except (OSError, RuntimeError, ValueError) as exc:
        raise boundary_error(
            code="desktop_oauth_loopback_unavailable",
            category=ErrorCategory.NETWORK,
            message="No se pudo abrir el callback OAuth local en 127.0.0.1.",
            operation="social_oauth_desktop.authorize",
            component=credentials.platform.value,
            cause=exc,
        ) from exc

    with receiver_context as receiver:
        if credentials.platform == OAuthPlatform.YOUTUBE:
            request = build_youtube_desktop_authorization(
                client_id=credentials.client_identifier,
                redirect_uri=receiver.redirect_uri,
                state=state,
                code_verifier=verifier,
            )
        else:
            request = build_tiktok_desktop_authorization(
                client_key=credentials.client_identifier,
                redirect_uri=receiver.redirect_uri,
                state=state,
                code_verifier=verifier,
            )

        try:
            opened = bool(opener(request.authorization_url))
        except Exception as exc:
            raise boundary_error(
                code="desktop_oauth_browser_failed",
                category=ErrorCategory.UPSTREAM,
                message="No se pudo abrir el navegador del sistema para OAuth.",
                operation="social_oauth_desktop.authorize",
                component=credentials.platform.value,
                cause=exc,
            ) from exc
        if not opened:
            raise boundary_error(
                code="desktop_oauth_browser_not_opened",
                category=ErrorCategory.UPSTREAM,
                message="El navegador del sistema no confirmó la apertura de OAuth.",
                operation="social_oauth_desktop.authorize",
                component=credentials.platform.value,
            )

        callback = receiver.wait(timeout_seconds=timeout_seconds)
        if credentials.platform == OAuthPlatform.YOUTUBE:
            token = exchange_youtube_authorization_code(
                request,
                callback,
                client_id=credentials.client_identifier,
                client_secret=credentials.client_secret,
                session=session,
            )
        else:
            token = exchange_tiktok_authorization_code(
                request,
                callback,
                client_key=credentials.client_identifier,
                client_secret=credentials.client_secret,
                session=session,
            )

    return DesktopOAuthSessionResult(token=token, platform=credentials.platform)


def configured_desktop_oauth_platforms(
    *,
    environ: Mapping[str, str] | None = None,
) -> tuple[OAuthPlatform, ...]:
    """Return only platforms whose runtime credentials pass the fail-closed gate."""
    try:
        if not desktop_oauth_enabled(environ):
            return ()
    except Exception:
        return ()

    configured: list[OAuthPlatform] = []
    for platform in (OAuthPlatform.YOUTUBE, OAuthPlatform.TIKTOK):
        try:
            load_desktop_oauth_credentials(platform, environ=environ)
        except Exception:
            continue
        configured.append(platform)
    return tuple(configured)


def oauth_runtime_status(
    *,
    environ: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Return a secret-free Product/UI status snapshot."""
    try:
        enabled = desktop_oauth_enabled(environ)
        gate_valid = True
    except Exception:
        enabled = False
        gate_valid = False
    configured = configured_desktop_oauth_platforms(environ=environ) if gate_valid else ()
    return {
        "enabled": enabled,
        "gate_valid": gate_valid,
        "youtube_configured": OAuthPlatform.YOUTUBE in configured,
        "tiktok_configured": OAuthPlatform.TIKTOK in configured,
        "token_persistence": False,
        "refresh_token_persistence": False,
        "auto_publication": False,
    }
