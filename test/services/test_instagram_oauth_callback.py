from __future__ import annotations

import json
from pathlib import Path

import pytest
import requests

from app.services.error_control import CentinelaError
from app.services.instagram_oauth import (
    INSTAGRAM_BASIC_SCOPE,
    INSTAGRAM_CONTENT_PUBLISH_SCOPE,
    InstagramOAuthCallback,
    InstagramShortLivedToken,
)
from app.services.instagram_oauth_callback import (
    AUTO_PUBLICATION,
    INSTAGRAM_CALLBACK_ENABLED_ENV,
    INSTAGRAM_CALLBACK_PATH,
    INSTAGRAM_CALLBACK_PROVIDER_ENV,
    INSTAGRAM_CLIENT_ID_ENV,
    INSTAGRAM_CLIENT_SECRET_ENV,
    INSTAGRAM_REDIRECT_URI_ENV,
    TAILSCALE_PROVIDER,
    CliResult,
    InstagramOneShotCallbackReceiver,
    TailscaleFunnelBridge,
    authorize_instagram_via_stable_https,
    callback_runtime_status,
    callback_transport_audit,
    instagram_callback_enabled,
    load_instagram_callback_credentials,
    validate_tailscale_instagram_redirect_uri,
)


REDIRECT = (
    "https://centinela.tail123456.ts.net"
    "/instagram/oauth/callback"
)


def _env(**overrides: str) -> dict[str, str]:
    result = {
        INSTAGRAM_CALLBACK_ENABLED_ENV: "true",
        INSTAGRAM_CALLBACK_PROVIDER_ENV: TAILSCALE_PROVIDER,
        INSTAGRAM_CLIENT_ID_ENV: "ig-app-id",
        INSTAGRAM_CLIENT_SECRET_ENV: "ig-app-secret",
        INSTAGRAM_REDIRECT_URI_ENV: REDIRECT,
    }
    result.update(overrides)
    return result


def _token() -> InstagramShortLivedToken:
    return InstagramShortLivedToken(
        access_token="short",
        user_id="17841400000000001",
        scopes=(INSTAGRAM_BASIC_SCOPE, INSTAGRAM_CONTENT_PUBLISH_SCOPE),
    )


def test_auto_publication_is_false():
    assert AUTO_PUBLICATION is False


def test_callback_gate_is_fail_closed_and_rejects_ambiguous_values():
    assert instagram_callback_enabled({}) is False
    assert instagram_callback_enabled({INSTAGRAM_CALLBACK_ENABLED_ENV: "off"}) is False
    assert instagram_callback_enabled({INSTAGRAM_CALLBACK_ENABLED_ENV: "YES"}) is True
    with pytest.raises(CentinelaError) as exc_info:
        instagram_callback_enabled({INSTAGRAM_CALLBACK_ENABLED_ENV: "maybe"})
    assert exc_info.value.code == "instagram_callback_gate_invalid"


def test_runtime_config_requires_explicit_tailscale_and_hides_secrets():
    credentials = load_instagram_callback_credentials(environ=_env())
    assert credentials.provider == TAILSCALE_PROVIDER
    assert credentials.redirect_uri == REDIRECT
    assert "ig-app-secret" not in repr(credentials)
    assert "ig-app-id" not in repr(credentials)

    bad = _env(**{INSTAGRAM_CALLBACK_PROVIDER_ENV: "cloudflare_quick"})
    with pytest.raises(CentinelaError) as exc_info:
        load_instagram_callback_credentials(environ=bad)
    assert exc_info.value.code == "instagram_callback_provider_unsupported"


def test_runtime_status_is_secret_free():
    status = callback_runtime_status(environ=_env())
    assert status == {
        "enabled": True,
        "gate_valid": True,
        "provider": TAILSCALE_PROVIDER,
        "configured": True,
        "token_persistence": False,
        "long_lived_token_default": False,
        "auto_publication": False,
    }
    text = repr(status)
    assert "ig-app-secret" not in text
    assert "ig-app-id" not in text
    assert "tail123456" not in text


@pytest.mark.parametrize(
    "uri",
    [
        "http://centinela.tail123456.ts.net/instagram/oauth/callback",
        "https://example.com/instagram/oauth/callback",
        "https://centinela.tail123456.ts.net/other",
        "https://centinela.tail123456.ts.net:8443/instagram/oauth/callback",
        "https://centinela.tail123456.ts.net/instagram/oauth/callback?x=1",
    ],
)
def test_tailscale_redirect_contract_is_exact(uri: str):
    with pytest.raises(CentinelaError):
        validate_tailscale_instagram_redirect_uri(uri)


def test_one_shot_receiver_accepts_only_exact_state_bound_get():
    state = "s" * 48
    with InstagramOneShotCallbackReceiver(expected_state=state) as receiver:
        root = f"http://127.0.0.1:{receiver.port}"
        missing = requests.get(f"{root}/", timeout=2)
        assert missing.status_code == 404

        bad = requests.get(
            f"{root}{INSTAGRAM_CALLBACK_PATH}",
            params={"code": "code", "state": "x" * 48},
            timeout=2,
        )
        assert bad.status_code == 400

        good = requests.get(
            f"{root}{INSTAGRAM_CALLBACK_PATH}",
            params={"code": "one-use-code", "state": state},
            timeout=2,
        )
        assert good.status_code == 200
        callback = receiver.wait(timeout_seconds=1)

    assert callback.code == "one-use-code"
    assert callback.state == state
    assert "one-use-code" not in repr(callback)
    assert state not in repr(callback)


def test_receiver_rejects_duplicate_parameters_and_stops_after_attempt_limit():
    state = "s" * 48
    with InstagramOneShotCallbackReceiver(
        expected_state=state,
        max_attempts=2,
    ) as receiver:
        root = f"http://127.0.0.1:{receiver.port}{INSTAGRAM_CALLBACK_PATH}"
        response = requests.get(
            f"{root}?state={state}&state={state}&code=one&code=two",
            timeout=2,
        )
        assert response.status_code == 400
        response = requests.get(
            f"{root}?state={'x' * 48}&code=bad",
            timeout=2,
        )
        assert response.status_code == 400
        with pytest.raises(CentinelaError) as exc_info:
            receiver.wait(timeout_seconds=1)

    assert exc_info.value.code == "instagram_callback_attempt_limit"


def test_receiver_vendor_denial_contains_no_remote_query_text():
    state = "s" * 48
    with InstagramOneShotCallbackReceiver(expected_state=state) as receiver:
        root = f"http://127.0.0.1:{receiver.port}{INSTAGRAM_CALLBACK_PATH}"
        response = requests.get(
            root,
            params={
                "error": "access_denied",
                "error_description": "access_token=do-not-log-this",
                "state": state,
            },
            timeout=2,
        )
        assert response.status_code == 400
        with pytest.raises(CentinelaError) as exc_info:
            receiver.wait(timeout_seconds=1)

    assert exc_info.value.code == "instagram_callback_vendor_denied"
    assert "do-not-log-this" not in str(exc_info.value)


class _TailscaleRunner:
    def __init__(
        self,
        *,
        dns_name: str = "centinela.tail123456.ts.net.",
        preexisting: bool = False,
        start_returncode: int = 0,
        stop_returncode: int = 0,
    ) -> None:
        self.dns_name = dns_name
        self.preexisting = preexisting
        self.start_returncode = start_returncode
        self.stop_returncode = stop_returncode
        self.active = False
        self.proxy = ""
        self.calls: list[list[str]] = []

    def __call__(self, argv: list[str], timeout_seconds: float) -> CliResult:
        self.calls.append(list(argv))
        assert timeout_seconds > 0
        args = argv[1:]
        if args == ["status", "--json"]:
            return CliResult(
                0,
                json.dumps(
                    {
                        "BackendState": "Running",
                        "Self": {"DNSName": self.dns_name},
                    }
                ),
            )
        if args == ["funnel", "status", "--json"]:
            active = self.active or self.preexisting
            payload = {}
            if active:
                proxy = self.proxy or "http://127.0.0.1:9999"
                payload = {
                    "TCP": {"443": {"HTTPS": True}},
                    "Web": {
                        "centinela.tail123456.ts.net:443": {
                            "Handlers": {"/": {"Proxy": proxy}}
                        }
                    },
                    "AllowFunnel": {
                        "centinela.tail123456.ts.net:443": True
                    },
                }
            return CliResult(0, json.dumps(payload))
        if args[:3] == ["funnel", "--bg", "--https=443"]:
            if self.start_returncode:
                return CliResult(self.start_returncode, stderr="not authorized")
            self.active = True
            self.proxy = args[3]
            return CliResult(0, "started")
        if args == ["funnel", "--https=443", "off"]:
            if self.stop_returncode:
                return CliResult(self.stop_returncode, stderr="cannot stop")
            self.active = False
            self.preexisting = False
            self.proxy = ""
            return CliResult(0, "stopped")
        raise AssertionError(f"unexpected tailscale command: {argv}")


def test_tailscale_bridge_verifies_stable_dns_route_and_cleanup():
    runner = _TailscaleRunner()
    bridge = TailscaleFunnelBridge(
        local_port=43123,
        redirect_uri=REDIRECT,
        executable="tailscale",
        runner=runner,
    )

    bridge.start()
    assert runner.active is True
    assert runner.proxy == "http://127.0.0.1:43123"
    bridge.stop()
    assert runner.active is False
    assert ["tailscale", "funnel", "--https=443", "off"] in runner.calls


def test_tailscale_bridge_refuses_to_overwrite_existing_443_funnel():
    runner = _TailscaleRunner(preexisting=True)
    bridge = TailscaleFunnelBridge(
        local_port=43123,
        redirect_uri=REDIRECT,
        executable="tailscale",
        runner=runner,
    )

    with pytest.raises(CentinelaError) as exc_info:
        bridge.start()

    assert exc_info.value.code == "tailscale_funnel_443_in_use"
    assert not any(call[1:3] == ["funnel", "--bg"] for call in runner.calls)


def test_tailscale_bridge_refuses_dns_identity_mismatch():
    runner = _TailscaleRunner(dns_name="other.tail123456.ts.net.")
    bridge = TailscaleFunnelBridge(
        local_port=43123,
        redirect_uri=REDIRECT,
        executable="tailscale",
        runner=runner,
    )

    with pytest.raises(CentinelaError) as exc_info:
        bridge.start()

    assert exc_info.value.code == "tailscale_dns_identity_mismatch"


def test_tailscale_start_failure_is_fail_closed_without_browser_semantics():
    runner = _TailscaleRunner(start_returncode=1)
    bridge = TailscaleFunnelBridge(
        local_port=43123,
        redirect_uri=REDIRECT,
        executable="tailscale",
        runner=runner,
    )

    with pytest.raises(CentinelaError) as exc_info:
        bridge.start()

    assert exc_info.value.code == "tailscale_funnel_start_failed"
    assert runner.active is False


def test_tailscale_stop_failure_is_not_silently_ignored():
    runner = _TailscaleRunner(stop_returncode=1)
    bridge = TailscaleFunnelBridge(
        local_port=43123,
        redirect_uri=REDIRECT,
        executable="tailscale",
        runner=runner,
    )
    bridge.start()

    with pytest.raises(CentinelaError) as exc_info:
        bridge.stop()

    assert exc_info.value.code == "tailscale_funnel_stop_failed"


def test_authorization_lifecycle_closes_public_boundary_before_token_exchange():
    events: list[str] = []

    class Receiver:
        port = 45678

        def __init__(self, expected_state: str):
            self.expected_state = expected_state

        def __enter__(self):
            events.append("receiver_enter")
            return self

        def __exit__(self, exc_type, exc, traceback):
            events.append("receiver_exit")

        def wait(self, *, timeout_seconds: float = 300.0):
            events.append("receiver_wait")
            return InstagramOAuthCallback(code="code", state=self.expected_state)

    class Bridge:
        def start(self):
            events.append("bridge_start")

        def stop(self):
            events.append("bridge_stop")

    def receiver_factory(**kwargs):
        return Receiver(kwargs["expected_state"])

    def bridge_factory(**kwargs):
        assert kwargs["local_port"] == 45678
        assert kwargs["redirect_uri"] == REDIRECT
        return Bridge()

    def browser_open(url: str):
        assert url.startswith("https://www.instagram.com/oauth/authorize?")
        events.append("browser_open")
        return True

    def exchange(request, callback, **kwargs):
        assert callback.state == request.state
        assert kwargs["client_id"] == "ig-app-id"
        assert kwargs["client_secret"] == "ig-app-secret"
        events.append("token_exchange")
        return _token()

    result = authorize_instagram_via_stable_https(
        environ=_env(),
        browser_open=browser_open,
        receiver_factory=receiver_factory,
        bridge_factory=bridge_factory,
        token_exchange=exchange,
        tailscale_executable="tailscale",
    )

    assert result.provider == TAILSCALE_PROVIDER
    assert "short" not in repr(result)
    assert events == [
        "receiver_enter",
        "bridge_start",
        "browser_open",
        "receiver_wait",
        "bridge_stop",
        "receiver_exit",
        "token_exchange",
    ]


def test_browser_failure_closes_bridge_and_never_exchanges_token():
    events: list[str] = []

    class Receiver:
        port = 45678

        def __enter__(self):
            events.append("receiver_enter")
            return self

        def __exit__(self, exc_type, exc, traceback):
            events.append("receiver_exit")

        def wait(self, *, timeout_seconds=300):
            raise AssertionError("callback wait must not run")

    class Bridge:
        def start(self):
            events.append("bridge_start")

        def stop(self):
            events.append("bridge_stop")

    def exchange(*args, **kwargs):
        raise AssertionError("token exchange must not run")

    with pytest.raises(CentinelaError) as exc_info:
        authorize_instagram_via_stable_https(
            environ=_env(),
            browser_open=lambda url: False,
            receiver_factory=lambda **kwargs: Receiver(),
            bridge_factory=lambda **kwargs: Bridge(),
            token_exchange=exchange,
            tailscale_executable="tailscale",
        )

    assert exc_info.value.code == "instagram_callback_browser_not_opened"
    assert events == ["receiver_enter", "bridge_start", "bridge_stop", "receiver_exit"]


def test_cleanup_failure_after_primary_error_blocks_token_exchange():
    class Receiver:
        port = 45678

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return None

        def wait(self, *, timeout_seconds=300):
            raise AssertionError("must not wait")

    class Bridge:
        def start(self):
            return None

        def stop(self):
            raise CentinelaError(
                code="test_cleanup",
                category=__import__(
                    "app.services.error_control", fromlist=["ErrorCategory"]
                ).ErrorCategory.SUBPROCESS,
                message="cleanup",
                context=__import__(
                    "app.services.error_control", fromlist=["ErrorContext"]
                ).ErrorContext(operation="test"),
            )

    with pytest.raises(CentinelaError) as exc_info:
        authorize_instagram_via_stable_https(
            environ=_env(),
            browser_open=lambda url: False,
            receiver_factory=lambda **kwargs: Receiver(),
            bridge_factory=lambda **kwargs: Bridge(),
            token_exchange=lambda *args, **kwargs: (_ for _ in ()).throw(
                AssertionError("must not exchange")
            ),
            tailscale_executable="tailscale",
        )

    assert exc_info.value.code == "instagram_callback_cleanup_failed_after_error"


def test_transport_audit_prefers_free_stable_tailscale_without_claiming_full_oss():
    rows = callback_transport_audit()
    by_provider = {row["provider"]: row for row in rows}

    tailscale = by_provider["Tailscale Funnel"]
    assert tailscale["cost"] == "0 € en plan Personal"
    assert tailscale["stable_https"] is True
    assert tailscale["own_domain_required"] is False
    assert "MAYORITARIAMENTE OSS" in tailscale["classification"]

    zrok = by_provider["zrok hosted public"]
    assert "interstitial" in zrok["caveat"]
    assert zrok["current_decision"] == "NO PRINCIPAL PARA OAUTH"


def test_source_has_no_persistence_long_token_refresh_or_publication():
    source = Path("app/services/instagram_oauth_callback.py").read_text(
        encoding="utf-8"
    ).lower()
    forbidden = (
        "write_text(",
        "write_bytes(",
        "session_state",
        "credentialmanager",
        "refresh_access_token",
        "exchange_instagram_long_lived_token",
        "media_publish",
        "publish_reel(",
        "schedule.",
        "threading.timer",
        "shell=true",
        "funnel reset",
    )
    for marker in forbidden:
        assert marker not in source
