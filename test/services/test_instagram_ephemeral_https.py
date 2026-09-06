from __future__ import annotations

import hashlib
from pathlib import Path
from types import SimpleNamespace

import pytest
import requests

from app.services.centinela.manual_publication import VerifiedPublicationPackage
from app.services.error_control import CentinelaError
from app.services.instagram_ephemeral_https import (
    INSTAGRAM_EPHEMERAL_HTTPS_ENABLED_ENV,
    INSTAGRAM_TUNNEL_PROVIDER_ENV,
    EphemeralSingleFileServer,
    EphemeralTunnel,
    InstagramTunnelProvider,
    PreparedInstagramReel,
    TransportEvidence,
    _validate_remote_transport,
    ephemeral_https_settings,
    iter_tunnel_provider_audit_rows,
    prepare_instagram_reel,
    publish_prepared_instagram_reel,
)
from app.services.social_publication import (
    PublicationMode,
    SocialPlatform,
    SocialResult,
)


def _write_mp4(tmp_path: Path, payload: bytes = b"centinela-video-bytes" * 64):
    path = tmp_path / "social_1080x1920.mp4"
    path.write_bytes(payload)
    return path, payload, hashlib.sha256(payload).hexdigest()


def _enabled_env(provider: str = "cloudflare_quick") -> dict[str, str]:
    return {
        INSTAGRAM_EPHEMERAL_HTTPS_ENABLED_ENV: "1",
        INSTAGRAM_TUNNEL_PROVIDER_ENV: provider,
    }


def _verified_package(path: Path, sha256: str, *, package_hash: str = "a" * 64):
    return VerifiedPublicationPackage(
        project_id="project-c10",
        manifest_artifact_id="manifest-1",
        publication_package_hash=package_hash,
        human_review_artifact_id="review-7of7",
        package_dir=path.parent,
        social_video_path=path,
        social_video_sha256=sha256,
        metadata=SimpleNamespace(caption="Caption aprobado"),
    )


def test_feature_gate_is_fail_closed_and_provider_is_explicit():
    disabled = ephemeral_https_settings({})
    assert disabled.enabled is False
    assert disabled.provider is None

    with pytest.raises(CentinelaError) as exc_info:
        ephemeral_https_settings({INSTAGRAM_EPHEMERAL_HTTPS_ENABLED_ENV: "maybe"})
    assert exc_info.value.code == "instagram_ephemeral_https_gate_invalid"

    with pytest.raises(CentinelaError) as exc_info:
        ephemeral_https_settings({INSTAGRAM_EPHEMERAL_HTTPS_ENABLED_ENV: "true"})
    assert exc_info.value.code == "instagram_tunnel_provider_missing"

    enabled = ephemeral_https_settings(_enabled_env("zrok_public"))
    assert enabled.enabled is True
    assert enabled.provider == InstagramTunnelProvider.ZROK_PUBLIC


def test_provider_audit_rows_are_stable_and_cost_truthful():
    rows = list(iter_tunnel_provider_audit_rows())
    assert [row["provider"] for row in rows] == [
        "tailscale_funnel",
        "cloudflare_quick",
        "zrok_public",
    ]
    assert rows[0]["software_license"].startswith("BSD-3-Clause")
    assert rows[0]["classification"].startswith("FREEMIUM")
    assert rows[0]["conclusion"] == "MANTENER"
    assert rows[1]["software_license"] == "Apache-2.0"
    assert "propietario" in rows[1]["classification"].lower()
    assert rows[2]["classification"] == "OPEN SOURCE + 100 % GRATUITA"
    assert rows[1]["conclusion"] == rows[2]["conclusion"] == "PRUEBA A/B"


def test_single_file_server_serves_only_exact_mp4_and_supports_range(tmp_path):
    path, payload, sha256 = _write_mp4(tmp_path)

    with EphemeralSingleFileServer(
        path,
        expected_sha256=sha256,
        ttl_seconds=5,
    ) as server:
        assert server.address.host == "127.0.0.1"
        assert server.address.route.endswith("/social_1080x1920.mp4")
        assert "social_1080x1920.mp4" not in server.public_path_sha256

        head = requests.head(server.address.local_url, timeout=3)
        assert head.status_code == 200
        assert head.headers["Content-Type"] == "video/mp4"
        assert int(head.headers["Content-Length"]) == len(payload)
        assert head.headers["Accept-Ranges"] == "bytes"

        full = requests.get(server.address.local_url, timeout=3)
        assert full.status_code == 200
        assert full.content == payload

        ranged = requests.get(
            server.address.local_url,
            headers={"Range": "bytes=2-9"},
            timeout=3,
        )
        assert ranged.status_code == 206
        assert ranged.content == payload[2:10]
        assert ranged.headers["Content-Range"] == f"bytes 2-9/{len(payload)}"

        suffix = requests.get(
            server.address.local_url,
            headers={"Range": "bytes=-4"},
            timeout=3,
        )
        assert suffix.status_code == 206
        assert suffix.content == payload[-4:]

        invalid = requests.get(
            server.address.local_url,
            headers={"Range": f"bytes={len(payload)}-"},
            timeout=3,
        )
        assert invalid.status_code == 416

        root = requests.get(server.address.local_origin + "/", timeout=3)
        assert root.status_code == 404
        query = requests.get(server.address.local_url + "?leak=1", timeout=3)
        assert query.status_code == 404
        post = requests.post(server.address.local_url, timeout=3)
        assert post.status_code == 405


def test_single_file_server_blocks_media_mutation(tmp_path):
    path, _, sha256 = _write_mp4(tmp_path)
    with EphemeralSingleFileServer(path, expected_sha256=sha256, ttl_seconds=5) as server:
        path.write_bytes(b"changed")
        response = requests.get(server.address.local_url, timeout=3)
        assert response.status_code == 409


def test_tunnel_commands_and_hostname_allowlists_are_fail_closed():
    tailscale = EphemeralTunnel(
        InstagramTunnelProvider.TAILSCALE_FUNNEL,
        "http://127.0.0.1:43122",
    )
    assert tailscale._command("tailscale") == [
        "tailscale",
        "funnel",
        "--https=443",
        "http://127.0.0.1:43122",
    ]
    assert (
        tailscale._accepted_public_origin("https://centinela.tail123456.ts.net")
        == "https://centinela.tail123456.ts.net"
    )
    assert (
        tailscale._accepted_public_origin("https://centinela.tail123456.ts.net.evil.example")
        is None
    )

    cloudflare = EphemeralTunnel(
        InstagramTunnelProvider.CLOUDFLARE_QUICK,
        "http://127.0.0.1:43123",
    )
    assert cloudflare._command("cloudflared") == [
        "cloudflared",
        "tunnel",
        "--url",
        "http://127.0.0.1:43123",
        "--no-autoupdate",
    ]
    assert (
        cloudflare._accepted_public_origin(
            "https://abc-123.trycloudflare.com"
        )
        == "https://abc-123.trycloudflare.com"
    )
    assert (
        cloudflare._accepted_public_origin(
            "https://abc.trycloudflare.com.evil.example"
        )
        is None
    )
    assert (
        cloudflare._accepted_public_origin(
            "http://abc.trycloudflare.com"
        )
        is None
    )

    zrok = EphemeralTunnel(
        InstagramTunnelProvider.ZROK_PUBLIC,
        "http://127.0.0.1:43124",
    )
    assert zrok._command("zrok") == [
        "zrok",
        "share",
        "public",
        "127.0.0.1:43124",
    ]
    assert (
        zrok._accepted_public_origin("https://abc.share.zrok.io")
        == "https://abc.share.zrok.io"
    )


class _FakeTailscaleBridge:
    def __init__(self):
        self.public_origin = "https://centinela.tail123456.ts.net"
        self.started = False
        self.stopped = False

    def start(self):
        self.started = True

    def stop(self):
        self.stopped = True


def test_tailscale_ephemeral_tunnel_reuses_certified_bridge_and_cleans_up():
    bridge = _FakeTailscaleBridge()
    tunnel = EphemeralTunnel(
        InstagramTunnelProvider.TAILSCALE_FUNNEL,
        "http://127.0.0.1:43125",
        tailscale_bridge_factory=lambda **kwargs: bridge,
    )
    with tunnel as active:
        assert active.public_origin == "https://centinela.tail123456.ts.net"
        assert bridge.started is True
        assert bridge.stopped is False
    assert bridge.stopped is True
    assert tunnel.public_origin == ""


class _FakeResponse:
    def __init__(
        self,
        status_code: int,
        *,
        headers: dict[str, str] | None = None,
        body: bytes = b"",
    ):
        self.status_code = status_code
        self.headers = headers or {}
        self._body = body
        self.closed = False

    def iter_content(self, chunk_size: int):
        for start in range(0, len(self._body), chunk_size):
            yield self._body[start : start + chunk_size]

    def close(self):
        self.closed = True


class _RemoteSession:
    def __init__(self, payload: bytes):
        self.payload = payload
        self.calls: list[tuple[str, dict]] = []

    def request(self, method, url, **kwargs):
        self.calls.append((method, {"url": url, **kwargs}))
        if method == "HEAD":
            return _FakeResponse(
                200,
                headers={
                    "Content-Type": "video/mp4",
                    "Content-Length": str(len(self.payload)),
                },
            )
        headers = kwargs.get("headers") or {}
        if headers.get("Range") == "bytes=0-0":
            return _FakeResponse(
                206,
                headers={
                    "Content-Type": "video/mp4",
                    "Content-Length": "1",
                    "Content-Range": f"bytes 0-0/{len(self.payload)}",
                },
                body=self.payload[:1],
            )
        return _FakeResponse(
            200,
            headers={
                "Content-Type": "video/mp4",
                "Content-Length": str(len(self.payload)),
            },
            body=self.payload,
        )


def test_remote_transport_requires_exact_sha_size_type_and_range(tmp_path):
    _, payload, sha256 = _write_mp4(tmp_path)
    evidence = _validate_remote_transport(
        public_url=(
            "https://unit-test.trycloudflare.com/"
            "opaque/social_1080x1920.mp4"
        ),
        provider=InstagramTunnelProvider.CLOUDFLARE_QUICK,
        expected_sha256=sha256,
        expected_size=len(payload),
        public_path_sha256="b" * 64,
        session=_RemoteSession(payload),
    )
    assert evidence.remote_media_sha256 == sha256
    assert evidence.local_media_sha256 == sha256
    assert evidence.size_bytes == len(payload)
    assert evidence.head_status == 200
    assert evidence.get_status == 200
    assert evidence.range_status == 206
    assert evidence.public_origin == "https://unit-test.trycloudflare.com"


def test_remote_transport_accepts_verified_tailscale_origin(tmp_path):
    _, payload, sha256 = _write_mp4(tmp_path)
    evidence = _validate_remote_transport(
        public_url=(
            "https://centinela.tail123456.ts.net/"
            "opaque/social_1080x1920.mp4"
        ),
        provider=InstagramTunnelProvider.TAILSCALE_FUNNEL,
        expected_sha256=sha256,
        expected_size=len(payload),
        public_path_sha256="e" * 64,
        session=_RemoteSession(payload),
    )
    assert evidence.provider == InstagramTunnelProvider.TAILSCALE_FUNNEL
    assert evidence.public_origin == "https://centinela.tail123456.ts.net"
    assert evidence.remote_media_sha256 == sha256


def test_remote_transport_rejects_untrusted_host_and_changed_bytes(tmp_path):
    _, payload, sha256 = _write_mp4(tmp_path)
    with pytest.raises(CentinelaError) as exc_info:
        _validate_remote_transport(
            public_url="https://unit-test.trycloudflare.com.evil.example/file.mp4",
            provider=InstagramTunnelProvider.CLOUDFLARE_QUICK,
            expected_sha256=sha256,
            expected_size=len(payload),
            public_path_sha256="c" * 64,
            session=_RemoteSession(payload),
        )
    assert exc_info.value.code == "instagram_public_url_untrusted"

    changed = payload[:-1] + bytes([payload[-1] ^ 1])
    with pytest.raises(CentinelaError) as exc_info:
        _validate_remote_transport(
            public_url="https://unit-test.trycloudflare.com/file.mp4",
            provider=InstagramTunnelProvider.CLOUDFLARE_QUICK,
            expected_sha256=sha256,
            expected_size=len(payload),
            public_path_sha256="c" * 64,
            session=_RemoteSession(changed),
        )
    assert exc_info.value.code == "instagram_transport_hash_mismatch"


class _FakeServer:
    def __init__(self, media_path, *, expected_sha256, ttl_seconds):
        del media_path, expected_sha256, ttl_seconds
        self.address = SimpleNamespace(
            local_origin="http://127.0.0.1:43120",
            route="/opaque/social_1080x1920.mp4",
        )
        self.public_path_sha256 = "d" * 64
        self.entered = False
        self.exited = False

    def __enter__(self):
        self.entered = True
        return self

    def __exit__(self, exc_type, exc, traceback):
        del exc_type, exc, traceback
        self.exited = True


class _FakeTunnel:
    def __init__(self, provider, local_origin):
        self.provider = provider
        self.local_origin = local_origin
        self.public_origin = "https://unit-test.trycloudflare.com"
        self.entered = False
        self.exited = False

    def __enter__(self):
        self.entered = True
        return self

    def __exit__(self, exc_type, exc, traceback):
        del exc_type, exc, traceback
        self.exited = True


class _InstagramAdapter:
    def __init__(self, statuses=("IN_PROGRESS", "FINISHED")):
        self.statuses = list(statuses)
        self.created: list[dict] = []
        self.status_calls: list[tuple[str, str]] = []
        self.published: list[dict] = []

    def create_reel_container(self, **kwargs):
        self.created.append(kwargs)
        return SocialResult(
            success=True,
            platform=SocialPlatform.INSTAGRAM,
            mode=PublicationMode.INSTAGRAM_REEL,
            remote_id="container-123",
            status="container_created",
            requires_user_action=True,
        )

    def get_container_status(self, container_id, *, access_token):
        self.status_calls.append((container_id, access_token))
        status = self.statuses.pop(0) if self.statuses else "FINISHED"
        return SocialResult(
            success=True,
            platform=SocialPlatform.INSTAGRAM,
            mode=PublicationMode.INSTAGRAM_REEL,
            remote_id=container_id,
            status=status,
            requires_user_action=True,
        )

    def publish_reel(self, **kwargs):
        self.published.append(kwargs)
        return SocialResult(
            success=True,
            platform=SocialPlatform.INSTAGRAM,
            mode=PublicationMode.INSTAGRAM_REEL,
            remote_id="media-456",
            status="published",
            requires_user_action=False,
        )


def test_prepare_instagram_reel_is_phase_one_only_and_cleans_transport(
    tmp_path,
    monkeypatch,
):
    from app.services import instagram_ephemeral_https as module

    path, payload, sha256 = _write_mp4(tmp_path)
    package = _verified_package(path, sha256)
    monkeypatch.setattr(module, "verify_publication_package", lambda *args: package)

    servers: list[_FakeServer] = []
    tunnels: list[_FakeTunnel] = []

    def server_factory(*args, **kwargs):
        instance = _FakeServer(*args, **kwargs)
        servers.append(instance)
        return instance

    def tunnel_factory(*args, **kwargs):
        instance = _FakeTunnel(*args, **kwargs)
        tunnels.append(instance)
        return instance

    adapter = _InstagramAdapter()
    prepared = prepare_instagram_reel(
        object(),
        "project-c10",
        ig_user_id="17841400000000000",
        access_token="runtime-token",
        approved=True,
        environ=_enabled_env(),
        instagram_adapter=adapter,
        remote_session=_RemoteSession(payload),
        server_factory=server_factory,
        tunnel_factory=tunnel_factory,
        sleep=lambda _: None,
        processing_timeout_seconds=5,
        poll_interval_seconds=60,
    )

    assert prepared.container_id == "container-123"
    assert prepared.status == "FINISHED"
    assert prepared.social_video_sha256 == sha256
    assert prepared.tunnel_provider == InstagramTunnelProvider.CLOUDFLARE_QUICK
    assert prepared.transport_evidence.remote_media_sha256 == sha256
    assert adapter.created[0]["approved"] is True
    assert adapter.created[0]["video_url"].startswith(
        "https://unit-test.trycloudflare.com/"
    )
    assert adapter.published == []
    assert servers[0].entered is True and servers[0].exited is True
    assert tunnels[0].entered is True and tunnels[0].exited is True


def test_prepare_requires_fresh_approval_and_feature_gate(tmp_path, monkeypatch):
    from app.services import instagram_ephemeral_https as module

    path, _, sha256 = _write_mp4(tmp_path)
    package = _verified_package(path, sha256)
    monkeypatch.setattr(module, "verify_publication_package", lambda *args: package)

    with pytest.raises(CentinelaError) as exc_info:
        prepare_instagram_reel(
            object(),
            "project-c10",
            ig_user_id="123",
            access_token="token",
            approved=False,
            environ=_enabled_env(),
        )
    assert exc_info.value.code == "human_approval_required"

    with pytest.raises(CentinelaError) as exc_info:
        prepare_instagram_reel(
            object(),
            "project-c10",
            ig_user_id="123",
            access_token="token",
            approved=True,
            environ={},
        )
    assert exc_info.value.code == "instagram_ephemeral_https_disabled"


def test_prepare_cleans_transport_when_meta_processing_fails(tmp_path, monkeypatch):
    from app.services import instagram_ephemeral_https as module

    path, payload, sha256 = _write_mp4(tmp_path)
    package = _verified_package(path, sha256)
    monkeypatch.setattr(module, "verify_publication_package", lambda *args: package)
    servers: list[_FakeServer] = []
    tunnels: list[_FakeTunnel] = []

    def server_factory(*args, **kwargs):
        instance = _FakeServer(*args, **kwargs)
        servers.append(instance)
        return instance

    def tunnel_factory(*args, **kwargs):
        instance = _FakeTunnel(*args, **kwargs)
        tunnels.append(instance)
        return instance

    with pytest.raises(CentinelaError) as exc_info:
        prepare_instagram_reel(
            object(),
            "project-c10",
            ig_user_id="123",
            access_token="token",
            approved=True,
            environ=_enabled_env(),
            instagram_adapter=_InstagramAdapter(("ERROR",)),
            remote_session=_RemoteSession(payload),
            server_factory=server_factory,
            tunnel_factory=tunnel_factory,
            sleep=lambda _: None,
            processing_timeout_seconds=5,
            poll_interval_seconds=60,
        )
    assert exc_info.value.code == "instagram_container_processing_failed"
    assert servers[0].exited is True
    assert tunnels[0].exited is True


def _prepared(package: VerifiedPublicationPackage) -> PreparedInstagramReel:
    return PreparedInstagramReel(
        project_id=package.project_id,
        manifest_artifact_id=package.manifest_artifact_id,
        publication_package_hash=package.publication_package_hash,
        human_review_artifact_id=package.human_review_artifact_id,
        social_video_sha256=package.social_video_sha256,
        ig_user_id="17841400000000000",
        container_id="container-123",
        status="FINISHED",
        tunnel_provider=InstagramTunnelProvider.CLOUDFLARE_QUICK,
        transport_evidence=TransportEvidence(
            provider=InstagramTunnelProvider.CLOUDFLARE_QUICK,
            public_origin="https://unit-test.trycloudflare.com",
            public_path_sha256="d" * 64,
            local_media_sha256=package.social_video_sha256,
            remote_media_sha256=package.social_video_sha256,
            size_bytes=package.social_video_path.stat().st_size,
            content_type="video/mp4",
            head_status=200,
            get_status=200,
            range_status=206,
        ),
    )


def test_media_publish_is_a_separate_second_human_action(tmp_path, monkeypatch):
    from app.services import instagram_ephemeral_https as module

    path, _, sha256 = _write_mp4(tmp_path)
    package = _verified_package(path, sha256)
    prepared = _prepared(package)
    monkeypatch.setattr(module, "verify_publication_package", lambda *args: package)
    adapter = _InstagramAdapter()

    with pytest.raises(CentinelaError) as exc_info:
        publish_prepared_instagram_reel(
            object(),
            prepared,
            access_token="runtime-token",
            approved=False,
            instagram_adapter=adapter,
        )
    assert exc_info.value.code == "human_approval_required"
    assert adapter.published == []

    result = publish_prepared_instagram_reel(
        object(),
        prepared,
        access_token="runtime-token",
        approved=True,
        instagram_adapter=adapter,
    )
    assert result.status == "published"
    assert adapter.published == [
        {
            "ig_user_id": prepared.ig_user_id,
            "container_id": prepared.container_id,
            "access_token": "runtime-token",
            "approved": True,
        }
    ]


def test_second_phase_rejects_stale_package_identity(tmp_path, monkeypatch):
    from app.services import instagram_ephemeral_https as module

    path, _, sha256 = _write_mp4(tmp_path)
    original = _verified_package(path, sha256, package_hash="a" * 64)
    changed = _verified_package(path, sha256, package_hash="b" * 64)
    prepared = _prepared(original)
    monkeypatch.setattr(module, "verify_publication_package", lambda *args: changed)
    adapter = _InstagramAdapter()

    with pytest.raises(CentinelaError) as exc_info:
        publish_prepared_instagram_reel(
            object(),
            prepared,
            access_token="runtime-token",
            approved=True,
            instagram_adapter=adapter,
        )
    assert exc_info.value.code == "instagram_prepared_package_identity_mismatch"
    assert adapter.published == []


def test_meta_polling_contract_is_rate_limit_conservative():
    with pytest.raises(ValueError, match="<= 300"):
        prepare_instagram_reel(
            object(),
            "project-c10",
            ig_user_id="123",
            access_token="token",
            approved=True,
            environ=_enabled_env(),
            processing_timeout_seconds=301,
        )

    with pytest.raises(ValueError, match=">= 60"):
        prepare_instagram_reel(
            object(),
            "project-c10",
            ig_user_id="123",
            access_token="token",
            approved=True,
            environ=_enabled_env(),
            poll_interval_seconds=59,
        )


def test_c10_source_has_no_secret_persistence_or_auto_publish():
    root = Path(__file__).resolve().parents[2]
    source = (
        root / "app" / "services" / "instagram_ephemeral_https.py"
    ).read_text(encoding="utf-8")
    assert "AUTO_PUBLICATION = False" in source
    assert "session_state" not in source
    assert "save_config" not in source
    assert "update_config" not in source
    assert ".write_text(" not in source
    assert ".write_bytes(" not in source
    assert "media_publish" in source
    assert "publish_prepared_instagram_reel" in source
