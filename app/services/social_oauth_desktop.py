"""Runtime-only Desktop OAuth orchestration for manual social publication.

This layer connects the C8 protocol boundary to an explicitly initiated desktop
browser flow. App credentials are read from the process environment by default;
access and refresh tokens are returned only in memory and are never persisted.

Safety policy:
    GENERAR -> REVISAR -> APROBAR -> PUBLICAR
    AUTO_PUBLICATION = False
"""

from __future__ import annotations

import os
import webbrowser
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field

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
YOUTUBE_CLIENT_ID_ENV = "CENTINELA_YOUTUBE_OAUTH_CLIENT_ID"
YOUTUBE_CLIENT_SECRET_ENV = "CENTINELA_YOUTUBE_OAUTH_CLIENT_SECRET"
TIKTOK_CLIENT_KEY_ENV = "CENTINELA_TIKTOK_CLIENT_KEY"
TIKTOK_CLIENT_SECRET_ENV = "CENTINELA_TIKTOK_CLIENT_SECRET"
_DEFAULT_CALLBACK_TIMEOUT_SECONDS = 300.0

BrowserOpener = Callable[[str], bool]


@dataclass(frozen=True, slots=True)
class DesktopOAuthCredentials:
    platform: OAuthPlatform
    client_id: str = field(default="", repr=False)
    client_secret: str = field(default="", repr=False)
    client_key: str = field(default="", repr=False)


def oauth_environment_contract(platform: OAuthPlatform) -> tuple[str, ...]:
    """Return environment variable names required by one desktop provider."""
    if platform == OAuthPlatform.YOUTUBE:
        return (YOUTUBE_CLIENT_ID_ENV,)
    if platform == OAuthPlatform.TIKTOK:
        return (TIKTOK_CLIENT_KEY_ENV, TIKTOK_CLIENT_SECRET_ENV)
    raise boundary_error(
        code="desktop_oauth_platform_unsupported",
        category=ErrorCategory.VALIDATION,
        message="La plataforma OAuth Desktop no está soportada.",
        operation="social_oauth_desktop.environment_contract",
        component="oauth",
    )


def load_desktop_oauth_credentials(
    platform: OAuthPlatform,
    *,
    environ: Mapping[str, str] | None = None,
) -> DesktopOAuthCredentials:
    """Load app credentials from process environment without persisting them."""
    source = os.environ if environ is None else environ

    if platform == OAuthPlatform.YOUTUBE:
        client_id = str(source.get(YOUTUBE_CLIENT_ID_ENV, "") or "").strip()
        client_secret = str(source.get(YOUTUBE_CLIENT_SECRET_ENV, "") or "").strip()
        if not client_id:
            raise boundary_error(
                code="youtube_desktop_oauth_environment_missing",
                category=ErrorCategory.CONFIG,
                message=(
                    "Falta la credencial OAuth Desktop de YouTube en el entorno del proceso."
                ),
                operation="social_oauth_desktop.load_credentials",
                component="youtube",
                details={"required_environment": [YOUTUBE_CLIENT_ID_ENV]},
            )
        return DesktopOAuthCredentials(
            platform=platform,
            client_id=client_id,
            client_secret=client_secret,
        )

    if platform == OAuthPlatform.TIKTOK:
        client_key = str(source.get(TIKTOK_CLIENT_KEY_ENV, "") or "").strip()
        client_secret = str(source.get(TIKTOK_CLIENT_SECRET_ENV, "") or "").strip()
        missing = [
            name
            for name, value in (
                (TIKTOK_CLIENT_KEY_ENV, client_key),
                (TIKTOK_CLIENT_SECRET_ENV, client_secret),
            )
            if not value
        ]
        if missing:
            raise boundary_error(
                code="tiktok_desktop_oauth_environment_missing",
                category=ErrorCategory.CONFIG,
                message=(
                    "Faltan credenciales OAuth Desktop de TikTok en el entorno del proceso."
                ),
                operation="social_oauth_desktop.load_credentials",
                component="tiktok",
                details={"required_environment": missing},
            )
        return DesktopOAuthCredentials(
            platform=platform,
            client_key=client_key,
            client_secret=client_secret,
        )

    raise boundary_error(
        code="desktop_oauth_platform_unsupported",
        category=ErrorCategory.VALIDATION,
        message="La plataforma OAuth Desktop no está soportada.",
        operation="social_oauth_desktop.load_credentials",
        component="oauth",
    )


def _open_system_browser(url: str) -> bool:
    """Open the system browser only after an explicit caller action."""
    return bool(webbrowser.open(url, new=2, autoraise=True))


def _validate_credentials_for_platform(
    platform: OAuthPlatform,
    credentials: DesktopOAuthCredentials,
) -> None:
    if credentials.platform != platform:
        raise boundary_error(
            code="desktop_oauth_credentials_platform_mismatch",
            category=ErrorCategory.VALIDATION,
            message="Las credenciales OAuth no pertenecen a la plataforma seleccionada.",
            operation="social_oauth_desktop.authorize",
            component=platform.value,
        )


def authorize_desktop_oauth(
    platform: OAuthPlatform,
    *,
    credentials: DesktopOAuthCredentials | None = None,
    environ: Mapping[str, str] | None = None,
    browser_opener: BrowserOpener | None = None,
    timeout_seconds: float = _DEFAULT_CALLBACK_TIMEOUT_SECONDS,
    session: requests.Session | None = None,
) -> OAuthTokenSet:
    """Run one explicit Desktop OAuth consent flow and return runtime-only tokens."""
    if AUTO_PUBLICATION:
        raise RuntimeError("AUTO_PUBLICATION invariant was modified")
    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be positive")

    resolved = credentials or load_desktop_oauth_credentials(platform, environ=environ)
    _validate_credentials_for_platform(platform, resolved)
    state = generate_oauth_state()
    verifier = generate_code_verifier()
    opener = browser_opener or _open_system_browser

    with LoopbackOAuthReceiver(expected_state=state) as receiver:
        if platform == OAuthPlatform.YOUTUBE:
            request = build_youtube_desktop_authorization(
                client_id=resolved.client_id,
                redirect_uri=receiver.redirect_uri,
                state=state,
                code_verifier=verifier,
            )
        elif platform == OAuthPlatform.TIKTOK:
            request = build_tiktok_desktop_authorization(
                client_key=resolved.client_key,
                redirect_uri=receiver.redirect_uri,
                state=state,
                code_verifier=verifier,
            )
        else:
            raise boundary_error(
                code="desktop_oauth_platform_unsupported",
                category=ErrorCategory.VALIDATION,
                message="La plataforma OAuth Desktop no está soportada.",
                operation="social_oauth_desktop.authorize",
                component="oauth",
            )

        try:
            opened = bool(opener(request.authorization_url))
        except Exception as exc:
            raise boundary_error(
                code="desktop_oauth_browser_launch_failed",
                category=ErrorCategory.UPSTREAM,
                message="No se pudo abrir el navegador del sistema para autorizar la cuenta.",
                operation="social_oauth_desktop.authorize",
                component=platform.value,
                cause=exc,
            ) from exc
        if not opened:
            raise boundary_error(
                code="desktop_oauth_browser_launch_failed",
                category=ErrorCategory.UPSTREAM,
                message="El navegador del sistema no confirmó la apertura de OAuth.",
                operation="social_oauth_desktop.authorize",
                component=platform.value,
            )
        callback = receiver.wait(timeout_seconds=timeout_seconds)

    if platform == OAuthPlatform.YOUTUBE:
        return exchange_youtube_authorization_code(
            request,
            callback,
            client_id=resolved.client_id,
            client_secret=resolved.client_secret,
            session=session,
        )
    if platform == OAuthPlatform.TIKTOK:
        return exchange_tiktok_authorization_code(
            request,
            callback,
            client_key=resolved.client_key,
            client_secret=resolved.client_secret,
            session=session,
        )
    raise AssertionError("validated OAuth platform became unsupported")
