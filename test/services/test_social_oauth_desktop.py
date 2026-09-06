from __future__ import annotations

from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

import pytest

from app.services.error_control import CentinelaError
from app.services.social_oauth import (
    OAuthCallback,
    OAuthPlatform,
    TIKTOK_UPLOAD_SCOPE,
    YOUTUBE_UPLOAD_SCOPE,
)
from app.services.social_oauth_desktop import (
    DESKTOP_OAUTH_ENABLED_ENV,
    TIKTOK_CLIENT_KEY_ENV,
    TIKTOK_CLIENT_SECRET_ENV,
    YOUTUBE_CLIENT_ID_ENV,
    YOUTUBE_CLIENT_SECRET_ENV,
    DesktopOAuthCredentials,
    authorize_desktop,
    configured_desktop_oauth_platforms,
    desktop_oauth_enabled,
    load_desktop_oauth_credentials,
    oauth_runtime_status,
)


class _FakeResponse:
    def __init__(self, payload: dict, status_code: int = 200):
        self._payload = payload
        self.status_code = status_code
        self.content = b"{}"

    def json(self):
        return self._payload


class _FakeSession:
    def __init__(self, payload: dict, status_code: int = 200):
        self.response = _FakeResponse(payload, status_code)
        self.calls: list[dict] = []

    def post(self, url, **kwargs):
        self.calls.append({"url": url, **kwargs})
        return self.response


class _FakeReceiver:
    instances: list["_FakeReceiver"] = []

    def __init__(self, *, expected_state: str):
        self.expected_state = expected_state
        self.redirect_uri = "http://127.0.0.1:43199/callback/"
        self.wait_calls: list[float] = []
        self.entered = False
        self.exited = False
        type(self).instances.append(self)

    def __enter__(self):
        self.entered = True
        return self

    def __exit__(self, exc_type, exc, traceback):
        del exc_type, exc, traceback
        self.exited = True

    def wait(self, *, timeout_seconds: float = 300.0):
        self.wait_calls.append(timeout_seconds)
        return OAuthCallback(code="one-time-auth-code", state=self.expected_state)


def _youtube_env(**overrides):
    env = {
        DESKTOP_OAUTH_ENABLED_ENV: "1",
        YOUTUBE_CLIENT_ID_ENV: "fake-youtube-client-id",
    }
    env.update(overrides)
    return env


def _tiktok_env(**overrides):
    env = {
        DESKTOP_OAUTH_ENABLED_ENV: "true",
        TIKTOK_CLIENT_KEY_ENV: "fake-tiktok-client-key",
        TIKTOK_CLIENT_SECRET_ENV: "fake-tiktok-client-secret",
    }
    env.update(overrides)
    return env


def test_desktop_oauth_is_fail_closed_by_default_and_rejects_ambiguous_gate():
    assert desktop_oauth_enabled({}) is False
    assert desktop_oauth_enabled({DESKTOP_OAUTH_ENABLED_ENV: "off"}) is False
    assert desktop_oauth_enabled({DESKTOP_OAUTH_ENABLED_ENV: "YES"}) is True

    with pytest.raises(CentinelaError) as exc_info:
        desktop_oauth_enabled({DESKTOP_OAUTH_ENABLED_ENV: "maybe"})
    assert exc_info.value.code == "desktop_oauth_gate_invalid"


def test_runtime_credentials_never_appear_in_repr():
    credentials = DesktopOAuthCredentials(
        platform=OAuthPlatform.TIKTOK,
        client_identifier="client-key-secretish",
        client_secret="actual-client-secret",
    )
    text = repr(credentials)
    assert "client-key-secretish" not in text
    assert "actual-client-secret" not in text


def test_youtube_credentials_require_id_but_secret_is_optional():
    credentials = load_desktop_oauth_credentials(
        OAuthPlatform.YOUTUBE,
        environ=_youtube_env(),
    )
    assert credentials.platform == OAuthPlatform.YOUTUBE
    assert credentials.client_identifier == "fake-youtube-client-id"
    assert credentials.client_secret == ""

    with pytest.raises(CentinelaError) as exc_info:
        load_desktop_oauth_credentials(
            OAuthPlatform.YOUTUBE,
            environ={DESKTOP_OAUTH_ENABLED_ENV: "1"},
        )
    assert exc_info.value.code == "youtube_desktop_oauth_not_configured"


def test_tiktok_credentials_require_key_and_secret():
    credentials = load_desktop_oauth_credentials(
        OAuthPlatform.TIKTOK,
        environ=_tiktok_env(),
    )
    assert credentials.client_identifier == "fake-tiktok-client-key"
    assert credentials.client_secret == "fake-tiktok-client-secret"

    with pytest.raises(CentinelaError) as exc_info:
        load_desktop_oauth_credentials(
            OAuthPlatform.TIKTOK,
            environ={
                DESKTOP_OAUTH_ENABLED_ENV: "1",
                TIKTOK_CLIENT_KEY_ENV: "key-only",
            },
        )
    assert exc_info.value.code == "tiktok_desktop_oauth_not_configured"


def test_youtube_browser_flow_returns_ephemeral_token_without_persistence():
    _FakeReceiver.instances.clear()
    browser_urls: list[str] = []
    session = _FakeSession(
        {
            "access_token": "runtime-youtube-access-token",
            "refresh_token": "runtime-youtube-refresh-token",
            "expires_in": 3600,
            "scope": YOUTUBE_UPLOAD_SCOPE,
        }
    )

    result = authorize_desktop(
        OAuthPlatform.YOUTUBE,
        environ=_youtube_env(
            **{YOUTUBE_CLIENT_SECRET_ENV: "optional-local-youtube-secret"}
        ),
        browser_open=lambda url: browser_urls.append(url) or True,
        receiver_factory=_FakeReceiver,
        session=session,
        timeout_seconds=12.5,
    )

    assert result.platform == OAuthPlatform.YOUTUBE
    assert result.token.access_token == "runtime-youtube-access-token"
    assert result.token.refresh_token == "runtime-youtube-refresh-token"
    assert "runtime-youtube-access-token" not in repr(result)
    assert len(browser_urls) == 1
    query = parse_qs(urlparse(browser_urls[0]).query)
    assert query["scope"] == [YOUTUBE_UPLOAD_SCOPE]
    assert query["redirect_uri"] == ["http://127.0.0.1:43199/callback/"]
    assert len(_FakeReceiver.instances) == 1
    receiver = _FakeReceiver.instances[0]
    assert receiver.entered is True
    assert receiver.exited is True
    assert receiver.wait_calls == [12.5]
    assert len(session.calls) == 1
    assert session.calls[0]["data"]["client_secret"] == "optional-local-youtube-secret"


def test_tiktok_browser_flow_returns_ephemeral_token_and_video_upload_scope():
    _FakeReceiver.instances.clear()
    browser_urls: list[str] = []
    session = _FakeSession(
        {
            "access_token": "runtime-tiktok-access-token",
            "refresh_token": "runtime-tiktok-refresh-token",
            "expires_in": 86400,
            "refresh_expires_in": 31536000,
            "scope": TIKTOK_UPLOAD_SCOPE,
            "open_id": "creator-id",
        }
    )

    result = authorize_desktop(
        "tiktok",
        environ=_tiktok_env(),
        browser_open=lambda url: browser_urls.append(url) or True,
        receiver_factory=_FakeReceiver,
        session=session,
    )

    assert result.platform == OAuthPlatform.TIKTOK
    assert result.token.access_token == "runtime-tiktok-access-token"
    assert result.token.scopes == (TIKTOK_UPLOAD_SCOPE,)
    query = parse_qs(urlparse(browser_urls[0]).query)
    assert query["scope"] == [TIKTOK_UPLOAD_SCOPE]
    assert session.calls[0]["data"]["client_secret"] == "fake-tiktok-client-secret"


def test_browser_open_failure_blocks_before_callback_wait_and_token_exchange():
    _FakeReceiver.instances.clear()
    session = _FakeSession({"access_token": "must-not-be-used"})

    with pytest.raises(CentinelaError) as exc_info:
        authorize_desktop(
            "youtube",
            environ=_youtube_env(),
            browser_open=lambda url: False,
            receiver_factory=_FakeReceiver,
            session=session,
        )

    assert exc_info.value.code == "desktop_oauth_browser_not_opened"
    assert len(_FakeReceiver.instances) == 1
    assert _FakeReceiver.instances[0].wait_calls == []
    assert _FakeReceiver.instances[0].exited is True
    assert session.calls == []


def test_browser_exception_never_echoes_authorization_url():
    class BrowserFailure(RuntimeError):
        pass

    seen: list[str] = []

    def fail(url: str) -> bool:
        seen.append(url)
        raise BrowserFailure(f"cannot open {url}")

    with pytest.raises(CentinelaError) as exc_info:
        authorize_desktop(
            "youtube",
            environ=_youtube_env(),
            browser_open=fail,
            receiver_factory=_FakeReceiver,
            session=_FakeSession({}),
        )

    assert seen
    assert exc_info.value.code == "desktop_oauth_browser_failed"
    assert seen[0] not in str(exc_info.value)


def test_configured_platforms_and_status_are_secret_free():
    env = {
        DESKTOP_OAUTH_ENABLED_ENV: "1",
        YOUTUBE_CLIENT_ID_ENV: "youtube-id-never-render-me",
        TIKTOK_CLIENT_KEY_ENV: "tiktok-key-never-render-me",
        TIKTOK_CLIENT_SECRET_ENV: "tiktok-secret-never-render-me",
    }
    assert configured_desktop_oauth_platforms(environ=env) == (
        OAuthPlatform.YOUTUBE,
        OAuthPlatform.TIKTOK,
    )
    status = oauth_runtime_status(environ=env)
    assert status == {
        "enabled": True,
        "gate_valid": True,
        "youtube_configured": True,
        "tiktok_configured": True,
        "token_persistence": False,
        "refresh_token_persistence": False,
        "auto_publication": False,
    }
    rendered = repr(status)
    assert "youtube-id-never-render-me" not in rendered
    assert "tiktok-secret-never-render-me" not in rendered


def test_c9_source_has_no_persistent_config_or_streamlit_secret_state():
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    source = (root / "app" / "services" / "social_oauth_desktop.py").read_text(
        encoding="utf-8"
    )
    assert "config.toml" not in source
    assert "session_state" not in source
    assert "save_config" not in source
    assert "update_config" not in source
    assert "open(" not in source
    assert "write(" not in source
    assert "os.environ[" not in source
    assert "webbrowser.open" in source
    assert "AUTO_PUBLICATION = False" in source
