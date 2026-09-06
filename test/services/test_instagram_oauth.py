from __future__ import annotations

from urllib.parse import parse_qs, urlparse

import pytest
import requests

from app.services.error_control import CentinelaError
from app.services.instagram_oauth import (
    AUTO_PUBLICATION,
    INSTAGRAM_AUTH_URL,
    INSTAGRAM_BASIC_SCOPE,
    INSTAGRAM_CONTENT_PUBLISH_SCOPE,
    INSTAGRAM_LONG_TOKEN_URL,
    INSTAGRAM_SHORT_TOKEN_URL,
    InstagramAuthorizationRequest,
    InstagramLongLivedToken,
    InstagramOAuthCallback,
    InstagramShortLivedToken,
    build_instagram_business_authorization,
    exchange_instagram_authorization_code,
    exchange_instagram_long_lived_token,
    get_instagram_account_identity,
    validate_instagram_callback,
    validate_instagram_redirect_uri,
)


class _Response:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload if payload is not None else {}
        self.content = b"{}" if payload is not None else b""

    def json(self):
        if isinstance(self._payload, BaseException):
            raise self._payload
        return self._payload


class _Session:
    def __init__(self):
        self.posts = []
        self.gets = []
        self.post_responses = []
        self.get_responses = []

    def post(self, url, **kwargs):
        self.posts.append((url, kwargs))
        response = self.post_responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return response

    def get(self, url, **kwargs):
        self.gets.append((url, kwargs))
        response = self.get_responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return response


def _request(state="s" * 48):
    return build_instagram_business_authorization(
        client_id="ig-app-123",
        redirect_uri="https://auth.example.test/instagram/callback",
        state=state,
    )


def _short_token():
    return InstagramShortLivedToken(
        access_token="short-secret",
        user_id="17841400000000001",
        scopes=(INSTAGRAM_BASIC_SCOPE, INSTAGRAM_CONTENT_PUBLISH_SCOPE),
    )


def _long_token():
    return InstagramLongLivedToken(
        access_token="long-secret",
        user_id="17841400000000001",
        scopes=(INSTAGRAM_BASIC_SCOPE, INSTAGRAM_CONTENT_PUBLISH_SCOPE),
        expires_in=5_184_000,
    )


def test_auto_publication_invariant_is_false():
    assert AUTO_PUBLICATION is False


def test_authorization_uses_instagram_business_login_minimum_publish_scopes():
    request = _request()
    parsed = urlparse(request.authorization_url)
    query = parse_qs(parsed.query)

    assert f"{parsed.scheme}://{parsed.netloc}{parsed.path}" == INSTAGRAM_AUTH_URL
    assert query["client_id"] == ["ig-app-123"]
    assert query["redirect_uri"] == ["https://auth.example.test/instagram/callback"]
    assert query["response_type"] == ["code"]
    assert query["state"] == ["s" * 48]
    assert query["scope"] == [
        f"{INSTAGRAM_BASIC_SCOPE},{INSTAGRAM_CONTENT_PUBLISH_SCOPE}"
    ]
    assert request.scopes == (INSTAGRAM_BASIC_SCOPE, INSTAGRAM_CONTENT_PUBLISH_SCOPE)


@pytest.mark.parametrize(
    "redirect_uri",
    [
        "http://localhost:8000/callback",
        "http://127.0.0.1:8000/callback",
        "https://user:password@example.test/callback",
        "https://example.test/callback?token=secret",
        "https://example.test/callback#fragment",
        "not-a-url",
    ],
)
def test_redirect_uri_is_fail_closed_to_clean_https(redirect_uri):
    with pytest.raises(CentinelaError):
        validate_instagram_redirect_uri(redirect_uri)


def test_generated_state_is_not_exposed_by_repr():
    request = build_instagram_business_authorization(
        client_id="ig-app-123",
        redirect_uri="https://auth.example.test/callback",
    )

    assert len(request.state) >= 32
    assert request.state not in repr(request)
    assert request.authorization_url not in repr(request)


def test_callback_state_mismatch_blocks_before_exchange():
    request = _request()
    with pytest.raises(CentinelaError) as exc_info:
        validate_instagram_callback(
            request,
            InstagramOAuthCallback(code="code-secret", state="x" * 48),
        )

    assert exc_info.value.code == "instagram_oauth_state_mismatch"
    assert "code-secret" not in str(exc_info.value)


def test_short_token_exchange_requires_state_and_publish_scopes():
    session = _Session()
    session.post_responses.append(
        _Response(
            200,
            {
                "access_token": "ig-short-secret",
                "user_id": "17841400000000001",
                "permissions": (
                    f"{INSTAGRAM_BASIC_SCOPE},{INSTAGRAM_CONTENT_PUBLISH_SCOPE}"
                ),
            },
        )
    )
    request = _request()
    callback = InstagramOAuthCallback(code="one-use-code", state=request.state)

    result = exchange_instagram_authorization_code(
        request,
        callback,
        client_id="ig-app-123",
        client_secret="app-secret",
        session=session,
    )

    assert result.user_id == "17841400000000001"
    assert result.scopes == (INSTAGRAM_BASIC_SCOPE, INSTAGRAM_CONTENT_PUBLISH_SCOPE)
    assert "ig-short-secret" not in repr(result)
    assert session.posts[0][0] == INSTAGRAM_SHORT_TOKEN_URL
    sent = session.posts[0][1]
    assert sent["data"] == {
        "client_id": "ig-app-123",
        "client_secret": "app-secret",
        "grant_type": "authorization_code",
        "redirect_uri": "https://auth.example.test/instagram/callback",
        "code": "one-use-code",
    }
    assert sent["headers"]["Content-Type"] == "application/x-www-form-urlencoded"


def test_short_token_exchange_accepts_single_data_wrapper():
    session = _Session()
    session.post_responses.append(
        _Response(
            200,
            {
                "data": [
                    {
                        "access_token": "wrapped-token",
                        "user_id": "17841400000000001",
                        "permissions": [
                            INSTAGRAM_BASIC_SCOPE,
                            INSTAGRAM_CONTENT_PUBLISH_SCOPE,
                        ],
                    }
                ]
            },
        )
    )
    request = _request()

    result = exchange_instagram_authorization_code(
        request,
        InstagramOAuthCallback(code="code", state=request.state),
        client_id="ig-app-123",
        client_secret="app-secret",
        session=session,
    )

    assert result.access_token == "wrapped-token"


def test_missing_content_publish_scope_is_rejected():
    session = _Session()
    session.post_responses.append(
        _Response(
            200,
            {
                "access_token": "ig-short-secret",
                "user_id": "17841400000000001",
                "permissions": INSTAGRAM_BASIC_SCOPE,
            },
        )
    )
    request = _request()

    with pytest.raises(CentinelaError) as exc_info:
        exchange_instagram_authorization_code(
            request,
            InstagramOAuthCallback(code="code", state=request.state),
            client_id="ig-app-123",
            client_secret="app-secret",
            session=session,
        )

    assert exc_info.value.code == "instagram_oauth_publish_scope_missing"
    assert INSTAGRAM_CONTENT_PUBLISH_SCOPE in exc_info.value.context.safe_details()[
        "missing_scopes"
    ]


def test_oauth_http_error_redacts_remote_secret_text():
    session = _Session()
    session.post_responses.append(
        _Response(400, {"error_message": "access_token=very-secret-value"})
    )
    request = _request()

    with pytest.raises(CentinelaError) as exc_info:
        exchange_instagram_authorization_code(
            request,
            InstagramOAuthCallback(code="code", state=request.state),
            client_id="ig-app-123",
            client_secret="app-secret",
            session=session,
        )

    assert exc_info.value.code == "instagram_oauth_http_400"
    assert "very-secret-value" not in str(exc_info.value)
    assert "***REDACTED***" in str(exc_info.value)


def test_network_failure_is_retryable_but_has_no_automatic_retry():
    session = _Session()
    session.post_responses.append(requests.ConnectionError("offline"))
    request = _request()

    with pytest.raises(CentinelaError) as exc_info:
        exchange_instagram_authorization_code(
            request,
            InstagramOAuthCallback(code="code", state=request.state),
            client_id="ig-app-123",
            client_secret="app-secret",
            session=session,
        )

    assert exc_info.value.retryable is True
    assert len(session.posts) == 1


def test_exchange_short_token_for_long_lived_token():
    session = _Session()
    session.get_responses.append(
        _Response(
            200,
            {
                "access_token": "ig-long-secret",
                "token_type": "bearer",
                "expires_in": 5_184_000,
            },
        )
    )

    result = exchange_instagram_long_lived_token(
        _short_token(),
        client_secret="app-secret",
        session=session,
    )

    assert result.user_id == "17841400000000001"
    assert result.expires_in == 5_184_000
    assert "ig-long-secret" not in repr(result)
    assert session.gets[0][0] == INSTAGRAM_LONG_TOKEN_URL
    assert session.gets[0][1]["params"] == {
        "grant_type": "ig_exchange_token",
        "client_secret": "app-secret",
        "access_token": "short-secret",
    }


def test_invalid_long_token_expiry_is_fail_closed():
    session = _Session()
    session.get_responses.append(
        _Response(200, {"access_token": "ig-long-secret", "expires_in": 0})
    )

    with pytest.raises(CentinelaError) as exc_info:
        exchange_instagram_long_lived_token(
            _short_token(),
            client_secret="app-secret",
            session=session,
        )

    assert exc_info.value.code == "instagram_oauth_long_token_expiry_invalid"


def test_identity_resolves_instagram_user_id_and_username():
    session = _Session()
    session.get_responses.append(
        _Response(
            200,
            {"user_id": "17841400000000001", "username": "elcentineladeluniverso"},
        )
    )

    identity = get_instagram_account_identity(_long_token(), session=session)

    assert identity.user_id == "17841400000000001"
    assert identity.username == "elcentineladeluniverso"
    url, kwargs = session.gets[0]
    assert url == "https://graph.instagram.com/v26.0/me"
    assert kwargs["params"]["fields"] == "user_id,username"
    assert kwargs["params"]["access_token"] == "long-secret"


def test_identity_mismatch_is_rejected():
    session = _Session()
    session.get_responses.append(
        _Response(
            200,
            {"user_id": "17841499999999999", "username": "other-account"},
        )
    )

    with pytest.raises(CentinelaError) as exc_info:
        get_instagram_account_identity(_long_token(), session=session)

    assert exc_info.value.code == "instagram_oauth_identity_mismatch"


def test_protocol_source_contains_no_persistence_or_background_refresh_paths():
    from pathlib import Path

    source = Path("app/services/instagram_oauth.py").read_text(encoding="utf-8").lower()
    forbidden = (
        "open(\"config.toml",
        "write_text(",
        "write_bytes(",
        "session_state",
        "schedule.",
        "threading.timer",
        "refresh_access_token",
        "media_publish",
    )
    for marker in forbidden:
        assert marker not in source


def test_token_dataclasses_hide_access_tokens_from_repr():
    assert "short-secret" not in repr(_short_token())
    assert "long-secret" not in repr(_long_token())
    callback = InstagramOAuthCallback(code="auth-code-secret", state="state-secret")
    assert "auth-code-secret" not in repr(callback)
    assert "state-secret" not in repr(callback)


def test_authorization_request_rejects_short_caller_supplied_state():
    with pytest.raises(CentinelaError) as exc_info:
        build_instagram_business_authorization(
            client_id="ig-app-123",
            redirect_uri="https://auth.example.test/callback",
            state="weak",
        )

    assert exc_info.value.code == "instagram_oauth_state_invalid"


def test_authorization_request_type_keeps_url_secret_from_repr():
    request = InstagramAuthorizationRequest(
        authorization_url="https://www.instagram.com/oauth/authorize?state=secret",
        redirect_uri="https://auth.example.test/callback",
        state="s" * 48,
    )
    assert "state=secret" not in repr(request)
