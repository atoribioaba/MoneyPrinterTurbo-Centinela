from __future__ import annotations

import base64
import hashlib
import urllib.error
import urllib.request
from urllib.parse import parse_qs, urlparse

import pytest

from app.services.error_control import CentinelaError
from app.services.social_oauth import (
    TIKTOK_AUTH_URL,
    TIKTOK_TOKEN_URL,
    TIKTOK_UPLOAD_SCOPE,
    YOUTUBE_AUTH_URL,
    YOUTUBE_TOKEN_URL,
    YOUTUBE_UPLOAD_SCOPE,
    LoopbackOAuthReceiver,
    OAuthCallback,
    OAuthPlatform,
    build_tiktok_desktop_authorization,
    build_youtube_desktop_authorization,
    exchange_tiktok_authorization_code,
    exchange_youtube_authorization_code,
    generate_code_verifier,
)


class _FakeResponse:
    def __init__(self, status_code: int, payload: dict):
        self.status_code = status_code
        self._payload = payload
        self.content = b"{}"

    def json(self):
        return self._payload


class _FakeSession:
    def __init__(self, response: _FakeResponse):
        self.response = response
        self.calls: list[dict] = []

    def post(self, url, **kwargs):
        self.calls.append({"url": url, **kwargs})
        return self.response


def _query(url: str) -> dict[str, list[str]]:
    return parse_qs(urlparse(url).query)


def test_code_verifier_uses_pkce_length_contract():
    verifier = generate_code_verifier()
    assert 43 <= len(verifier) <= 128
    assert set(verifier) <= set(
        "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~"
    )
    with pytest.raises(ValueError):
        generate_code_verifier(42)
    with pytest.raises(ValueError):
        generate_code_verifier(129)


def test_youtube_desktop_authorization_is_loopback_pkce_and_minimal_scope():
    verifier = "A" * 64
    request = build_youtube_desktop_authorization(
        client_id="youtube-client",
        redirect_uri="http://127.0.0.1:43117/callback/",
        state="csrf-youtube",
        code_verifier=verifier,
    )

    parsed = urlparse(request.authorization_url)
    query = _query(request.authorization_url)
    expected_challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode("ascii")).digest()
    ).decode("ascii").rstrip("=")

    assert f"{parsed.scheme}://{parsed.netloc}{parsed.path}" == YOUTUBE_AUTH_URL
    assert query["client_id"] == ["youtube-client"]
    assert query["redirect_uri"] == [request.redirect_uri]
    assert query["scope"] == [YOUTUBE_UPLOAD_SCOPE]
    assert query["state"] == ["csrf-youtube"]
    assert query["code_challenge"] == [expected_challenge]
    assert query["code_challenge_method"] == ["S256"]
    assert request.scopes == (YOUTUBE_UPLOAD_SCOPE,)
    assert "csrf-youtube" not in repr(request)
    assert verifier not in repr(request)


def test_tiktok_desktop_authorization_uses_required_hex_pkce_and_video_upload_only():
    verifier = "B" * 64
    request = build_tiktok_desktop_authorization(
        client_key="tiktok-key",
        redirect_uri="http://127.0.0.1:43118/callback/",
        state="csrf-tiktok",
        code_verifier=verifier,
    )

    parsed = urlparse(request.authorization_url)
    query = _query(request.authorization_url)
    expected_challenge = hashlib.sha256(verifier.encode("ascii")).hexdigest()

    assert f"{parsed.scheme}://{parsed.netloc}{parsed.path}" == TIKTOK_AUTH_URL
    assert query["client_key"] == ["tiktok-key"]
    assert query["redirect_uri"] == [request.redirect_uri]
    assert query["scope"] == [TIKTOK_UPLOAD_SCOPE]
    assert query["state"] == ["csrf-tiktok"]
    assert query["code_challenge"] == [expected_challenge]
    assert query["code_challenge_method"] == ["S256"]
    assert request.scopes == (TIKTOK_UPLOAD_SCOPE,)


@pytest.mark.parametrize(
    "redirect_uri",
    [
        "https://example.com/callback/",
        "http://localhost:43117/callback/",
        "http://127.0.0.1/callback/",
        "http://127.0.0.1:43117/other/",
        "http://127.0.0.1:43117/callback/?token=bad",
        "http://127.0.0.1:43117/callback/#fragment",
    ],
)
def test_oauth_redirect_is_strictly_confined_to_canonical_loopback(redirect_uri):
    with pytest.raises(CentinelaError) as exc_info:
        build_youtube_desktop_authorization(
            client_id="youtube-client",
            redirect_uri=redirect_uri,
        )
    assert exc_info.value.code in {"oauth_redirect_invalid", "oauth_redirect_not_loopback"}


def test_loopback_receiver_accepts_one_valid_callback_without_logging_secrets():
    state = "state-valid-loopback"
    with LoopbackOAuthReceiver(expected_state=state) as receiver:
        url = f"{receiver.redirect_uri}?code=one-time-secret-code&state={state}"
        with urllib.request.urlopen(url, timeout=2) as response:
            body = response.read().decode("utf-8")
            assert response.status == 200
            assert "Autorización recibida" in body
        callback = receiver.wait(timeout_seconds=1)

    assert callback.code == "one-time-secret-code"
    assert callback.state == state
    assert "one-time-secret-code" not in repr(callback)
    assert state not in repr(callback)


def test_loopback_receiver_rejects_csrf_state_mismatch():
    with LoopbackOAuthReceiver(expected_state="expected-state") as receiver:
        url = f"{receiver.redirect_uri}?code=secret-code&state=attacker-state"
        with pytest.raises(urllib.error.HTTPError) as http_error:
            urllib.request.urlopen(url, timeout=2)
        assert http_error.value.code == 400
        with pytest.raises(CentinelaError) as exc_info:
            receiver.wait(timeout_seconds=1)

    assert exc_info.value.code == "oauth_state_mismatch"


def test_youtube_exchange_uses_pkce_and_returns_runtime_only_token():
    request = build_youtube_desktop_authorization(
        client_id="youtube-client",
        redirect_uri="http://127.0.0.1:43119/callback/",
        state="state-youtube",
        code_verifier="C" * 64,
    )
    callback = OAuthCallback(code="youtube-code", state="state-youtube")
    session = _FakeSession(
        _FakeResponse(
            200,
            {
                "access_token": "youtube-access-secret",
                "expires_in": 3600,
                "scope": YOUTUBE_UPLOAD_SCOPE,
                "token_type": "Bearer",
            },
        )
    )

    token = exchange_youtube_authorization_code(
        request,
        callback,
        client_id="youtube-client",
        session=session,
    )

    assert token.platform == OAuthPlatform.YOUTUBE
    assert token.access_token == "youtube-access-secret"
    assert token.expires_in == 3600
    assert token.scopes == (YOUTUBE_UPLOAD_SCOPE,)
    assert "youtube-access-secret" not in repr(token)
    assert len(session.calls) == 1
    call = session.calls[0]
    assert call["url"] == YOUTUBE_TOKEN_URL
    assert call["data"]["code"] == "youtube-code"
    assert call["data"]["code_verifier"] == "C" * 64
    assert call["data"]["redirect_uri"] == request.redirect_uri
    assert "client_secret" not in call["data"]


def test_tiktok_exchange_requires_secret_and_video_upload_scope():
    request = build_tiktok_desktop_authorization(
        client_key="tiktok-key",
        redirect_uri="http://127.0.0.1:43120/callback/",
        state="state-tiktok",
        code_verifier="D" * 64,
    )
    callback = OAuthCallback(code="tiktok-code", state="state-tiktok")

    with pytest.raises(CentinelaError) as missing_secret:
        exchange_tiktok_authorization_code(
            request,
            callback,
            client_key="tiktok-key",
            client_secret="",
            session=_FakeSession(_FakeResponse(200, {})),
        )
    assert missing_secret.value.code == "tiktok_oauth_client_credentials_missing"

    session = _FakeSession(
        _FakeResponse(
            200,
            {
                "access_token": "tiktok-access-secret",
                "refresh_token": "tiktok-refresh-secret",
                "expires_in": 86400,
                "refresh_expires_in": 31536000,
                "open_id": "creator-open-id",
                "scope": "video.upload",
                "token_type": "Bearer",
            },
        )
    )
    token = exchange_tiktok_authorization_code(
        request,
        callback,
        client_key="tiktok-key",
        client_secret="server-side-secret",
        session=session,
    )

    assert token.platform == OAuthPlatform.TIKTOK
    assert token.access_token == "tiktok-access-secret"
    assert token.refresh_token == "tiktok-refresh-secret"
    assert token.expires_in == 86400
    assert token.refresh_expires_in == 31536000
    assert token.scopes == (TIKTOK_UPLOAD_SCOPE,)
    assert token.open_id == "creator-open-id"
    assert "tiktok-access-secret" not in repr(token)
    assert "tiktok-refresh-secret" not in repr(token)
    call = session.calls[0]
    assert call["url"] == TIKTOK_TOKEN_URL
    assert call["data"]["client_key"] == "tiktok-key"
    assert call["data"]["client_secret"] == "server-side-secret"
    assert call["data"]["code_verifier"] == "D" * 64


def test_oauth_state_mismatch_blocks_before_token_endpoint():
    request = build_youtube_desktop_authorization(
        client_id="youtube-client",
        redirect_uri="http://127.0.0.1:43121/callback/",
        state="expected-state",
        code_verifier="E" * 64,
    )
    session = _FakeSession(_FakeResponse(200, {"access_token": "must-not-be-used"}))

    with pytest.raises(CentinelaError) as exc_info:
        exchange_youtube_authorization_code(
            request,
            OAuthCallback(code="code", state="wrong-state"),
            client_id="youtube-client",
            session=session,
        )

    assert exc_info.value.code == "oauth_state_mismatch"
    assert session.calls == []


def test_tiktok_missing_video_upload_scope_is_fail_closed():
    request = build_tiktok_desktop_authorization(
        client_key="tiktok-key",
        redirect_uri="http://127.0.0.1:43122/callback/",
        state="state",
        code_verifier="F" * 64,
    )
    session = _FakeSession(
        _FakeResponse(
            200,
            {
                "access_token": "token",
                "scope": "user.info.basic",
                "token_type": "Bearer",
            },
        )
    )

    with pytest.raises(CentinelaError) as exc_info:
        exchange_tiktok_authorization_code(
            request,
            OAuthCallback(code="code", state="state"),
            client_key="tiktok-key",
            client_secret="server-side-secret",
            session=session,
        )

    assert exc_info.value.code == "tiktok_oauth_scope_missing"


def test_oauth_http_error_never_echoes_client_secret_or_access_token():
    request = build_tiktok_desktop_authorization(
        client_key="tiktok-key",
        redirect_uri="http://127.0.0.1:43123/callback/",
        state="state",
        code_verifier="G" * 64,
    )
    session = _FakeSession(
        _FakeResponse(
            401,
            {
                "error": "invalid_client",
                "error_description": "client_secret=super-secret access_token=leaked-token",
            },
        )
    )

    with pytest.raises(CentinelaError) as exc_info:
        exchange_tiktok_authorization_code(
            request,
            OAuthCallback(code="code", state="state"),
            client_key="tiktok-key",
            client_secret="super-secret",
            session=session,
        )

    text = str(exc_info.value)
    assert exc_info.value.code == "tiktok_oauth_http_401"
    assert "super-secret" not in text
    assert "leaked-token" not in text
    assert "***REDACTED***" in text
