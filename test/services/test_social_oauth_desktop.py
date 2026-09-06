from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from app.services import social_oauth_desktop as desktop
from app.services.error_control import CentinelaError
from app.services.social_oauth import OAuthCallback, OAuthPlatform, OAuthTokenSet


ROOT = Path(__file__).resolve().parents[2]


class _FakeReceiver:
    def __init__(self, *, expected_state: str):
        self.expected_state = expected_state
        self.redirect_uri = "http://127.0.0.1:45117/callback/"
        self.entered = False
        self.exited = False
        self.wait_timeout = None

    def __enter__(self):
        self.entered = True
        return self

    def __exit__(self, exc_type, exc, traceback):
        del exc_type, exc, traceback
        self.exited = True

    def wait(self, *, timeout_seconds: float):
        self.wait_timeout = timeout_seconds
        return OAuthCallback(code="runtime-code", state=self.expected_state)


def test_youtube_environment_credentials_are_runtime_only_and_repr_safe():
    credentials = desktop.load_desktop_oauth_credentials(
        OAuthPlatform.YOUTUBE,
        environ={
            desktop.YOUTUBE_CLIENT_ID_ENV: "youtube-client-id",
            desktop.YOUTUBE_CLIENT_SECRET_ENV: "youtube-client-secret",
        },
    )

    assert credentials.platform == OAuthPlatform.YOUTUBE
    assert credentials.client_id == "youtube-client-id"
    assert credentials.client_secret == "youtube-client-secret"
    assert "youtube-client-id" not in repr(credentials)
    assert "youtube-client-secret" not in repr(credentials)
    assert desktop.oauth_environment_contract(OAuthPlatform.YOUTUBE) == (
        desktop.YOUTUBE_CLIENT_ID_ENV,
    )


def test_tiktok_environment_credentials_fail_closed_when_incomplete():
    with pytest.raises(CentinelaError) as exc_info:
        desktop.load_desktop_oauth_credentials(
            OAuthPlatform.TIKTOK,
            environ={desktop.TIKTOK_CLIENT_KEY_ENV: "tiktok-key"},
        )

    assert exc_info.value.code == "tiktok_desktop_oauth_environment_missing"
    assert desktop.oauth_environment_contract(OAuthPlatform.TIKTOK) == (
        desktop.TIKTOK_CLIENT_KEY_ENV,
        desktop.TIKTOK_CLIENT_SECRET_ENV,
    )


def test_youtube_desktop_orchestrator_opens_browser_waits_loopback_and_exchanges(monkeypatch):
    receiver = _FakeReceiver(expected_state="state-fixed")
    request = SimpleNamespace(authorization_url="https://accounts.example/authorize")
    token = OAuthTokenSet(
        platform=OAuthPlatform.YOUTUBE,
        access_token="runtime-access-token",
    )
    calls = []

    monkeypatch.setattr(desktop, "generate_oauth_state", lambda: "state-fixed")
    monkeypatch.setattr(desktop, "generate_code_verifier", lambda: "V" * 64)
    monkeypatch.setattr(
        desktop,
        "LoopbackOAuthReceiver",
        lambda *, expected_state: receiver,
    )

    def fake_build(**kwargs):
        calls.append(("build", kwargs))
        return request

    def fake_exchange(request_arg, callback_arg, **kwargs):
        calls.append(("exchange", request_arg, callback_arg, kwargs))
        return token

    monkeypatch.setattr(desktop, "build_youtube_desktop_authorization", fake_build)
    monkeypatch.setattr(desktop, "exchange_youtube_authorization_code", fake_exchange)

    opened = []
    fake_session = object()
    result = desktop.authorize_desktop_oauth(
        OAuthPlatform.YOUTUBE,
        credentials=desktop.DesktopOAuthCredentials(
            platform=OAuthPlatform.YOUTUBE,
            client_id="youtube-client",
            client_secret="youtube-secret",
        ),
        browser_opener=lambda url: opened.append(url) or True,
        timeout_seconds=12.5,
        session=fake_session,
    )

    assert result is token
    assert receiver.entered is True
    assert receiver.exited is True
    assert receiver.wait_timeout == 12.5
    assert opened == [request.authorization_url]
    assert calls[0] == (
        "build",
        {
            "client_id": "youtube-client",
            "redirect_uri": receiver.redirect_uri,
            "state": "state-fixed",
            "code_verifier": "V" * 64,
        },
    )
    exchange = calls[1]
    assert exchange[0] == "exchange"
    assert exchange[1] is request
    assert exchange[2].code == "runtime-code"
    assert exchange[3]["client_id"] == "youtube-client"
    assert exchange[3]["client_secret"] == "youtube-secret"
    assert exchange[3]["session"] is fake_session


def test_tiktok_desktop_orchestrator_uses_client_key_and_secret(monkeypatch):
    receiver = _FakeReceiver(expected_state="state-tiktok")
    request = SimpleNamespace(authorization_url="https://tiktok.example/authorize")
    token = OAuthTokenSet(
        platform=OAuthPlatform.TIKTOK,
        access_token="runtime-access-token",
        scopes=("video.upload",),
    )
    calls = []

    monkeypatch.setattr(desktop, "generate_oauth_state", lambda: "state-tiktok")
    monkeypatch.setattr(desktop, "generate_code_verifier", lambda: "T" * 64)
    monkeypatch.setattr(
        desktop,
        "LoopbackOAuthReceiver",
        lambda *, expected_state: receiver,
    )
    monkeypatch.setattr(
        desktop,
        "build_tiktok_desktop_authorization",
        lambda **kwargs: calls.append(("build", kwargs)) or request,
    )

    def fake_exchange(request_arg, callback_arg, **kwargs):
        calls.append(("exchange", request_arg, callback_arg, kwargs))
        return token

    monkeypatch.setattr(desktop, "exchange_tiktok_authorization_code", fake_exchange)

    result = desktop.authorize_desktop_oauth(
        OAuthPlatform.TIKTOK,
        credentials=desktop.DesktopOAuthCredentials(
            platform=OAuthPlatform.TIKTOK,
            client_key="tiktok-key",
            client_secret="tiktok-secret",
        ),
        browser_opener=lambda url: url == request.authorization_url,
    )

    assert result is token
    assert calls[0][1]["client_key"] == "tiktok-key"
    exchange = calls[1]
    assert exchange[3]["client_key"] == "tiktok-key"
    assert exchange[3]["client_secret"] == "tiktok-secret"


def test_browser_launch_failure_is_fail_closed_before_token_exchange(monkeypatch):
    receiver = _FakeReceiver(expected_state="state")
    request = SimpleNamespace(authorization_url="https://accounts.example/authorize")
    exchanged = []

    monkeypatch.setattr(desktop, "generate_oauth_state", lambda: "state")
    monkeypatch.setattr(desktop, "generate_code_verifier", lambda: "Q" * 64)
    monkeypatch.setattr(
        desktop,
        "LoopbackOAuthReceiver",
        lambda *, expected_state: receiver,
    )
    monkeypatch.setattr(
        desktop,
        "build_youtube_desktop_authorization",
        lambda **kwargs: request,
    )
    monkeypatch.setattr(
        desktop,
        "exchange_youtube_authorization_code",
        lambda *args, **kwargs: exchanged.append((args, kwargs)),
    )

    with pytest.raises(CentinelaError) as exc_info:
        desktop.authorize_desktop_oauth(
            OAuthPlatform.YOUTUBE,
            credentials=desktop.DesktopOAuthCredentials(
                platform=OAuthPlatform.YOUTUBE,
                client_id="youtube-client",
            ),
            browser_opener=lambda url: False,
        )

    assert exc_info.value.code == "desktop_oauth_browser_launch_failed"
    assert exchanged == []
    assert receiver.exited is True
    assert receiver.wait_timeout is None


def test_credentials_platform_mismatch_blocks_before_browser(monkeypatch):
    opened = []
    monkeypatch.setattr(
        desktop,
        "LoopbackOAuthReceiver",
        lambda **kwargs: pytest.fail("receiver must not be created"),
    )

    with pytest.raises(CentinelaError) as exc_info:
        desktop.authorize_desktop_oauth(
            OAuthPlatform.YOUTUBE,
            credentials=desktop.DesktopOAuthCredentials(
                platform=OAuthPlatform.TIKTOK,
                client_key="wrong-platform",
                client_secret="secret",
            ),
            browser_opener=lambda url: opened.append(url) or True,
        )

    assert exc_info.value.code == "desktop_oauth_credentials_platform_mismatch"
    assert opened == []


def test_desktop_oauth_module_has_no_credential_persistence_path():
    source = (ROOT / "app" / "services" / "social_oauth_desktop.py").read_text(
        encoding="utf-8"
    )

    assert "save_config" not in source
    assert "config.toml" not in source
    assert "st.session_state" not in source
    assert ".write_text(" not in source
    assert ".write_bytes(" not in source
    assert "AUTO_PUBLICATION = False" in source
