from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.services.centinela.project_foundation import ArtifactStore
from app.services.error_control import CentinelaError
from app.services.instagram_ephemeral_https import (
    InstagramTunnelProvider,
    PreparedInstagramReel,
    TransportEvidence,
)
from app.services.instagram_manual_publication import (
    INSTAGRAM_PREPARED_REEL_ARTIFACT_TYPE,
    INSTAGRAM_PUBLISH_INTENT_ARTIFACT_TYPE,
    INSTAGRAM_PUBLISH_RECEIPT_ARTIFACT_TYPE,
    get_instagram_publish_receipt,
    get_unresolved_instagram_publish_intent,
    load_latest_prepared_instagram_reel,
    persist_prepared_instagram_reel,
    prepare_instagram_manual_publication,
    publish_instagram_manual_publication,
)
from app.services.social_publication import (
    PublicationMode,
    SocialPlatform,
    SocialResult,
)


PROJECT_ID = "projectc13"
MANIFEST_ID = "manifestc13"
PACKAGE_HASH = "a" * 64
VIDEO_HASH = "b" * 64
PATH_HASH = "c" * 64


def _store(tmp_path) -> ArtifactStore:
    store = ArtifactStore(tmp_path / "centinela")
    store.create_project("C13", project_id=PROJECT_ID)
    store.put_json(
        PROJECT_ID,
        "publication_manifest",
        {"ok": True},
        producer="test",
        artifact_id=MANIFEST_ID,
    )
    return store


def _prepared(*, user_id: str = "ig-user-1", container_id: str = "container-1") -> PreparedInstagramReel:
    evidence = TransportEvidence(
        provider=InstagramTunnelProvider.CLOUDFLARE_QUICK,
        public_origin="https://example.trycloudflare.com",
        public_path_sha256=PATH_HASH,
        local_media_sha256=VIDEO_HASH,
        remote_media_sha256=VIDEO_HASH,
        size_bytes=12345,
        content_type="video/mp4",
        head_status=200,
        get_status=200,
        range_status=206,
    )
    return PreparedInstagramReel(
        project_id=PROJECT_ID,
        manifest_artifact_id=MANIFEST_ID,
        publication_package_hash=PACKAGE_HASH,
        human_review_artifact_id="review-c13",
        social_video_sha256=VIDEO_HASH,
        ig_user_id=user_id,
        container_id=container_id,
        status="FINISHED",
        tunnel_provider=InstagramTunnelProvider.CLOUDFLARE_QUICK,
        transport_evidence=evidence,
    )


def _package(prepared: PreparedInstagramReel | None = None):
    item = prepared or _prepared()
    return SimpleNamespace(
        project_id=item.project_id,
        manifest_artifact_id=item.manifest_artifact_id,
        publication_package_hash=item.publication_package_hash,
        human_review_artifact_id=item.human_review_artifact_id,
        social_video_sha256=item.social_video_sha256,
    )


def _oauth(user_id: str = "ig-user-1", token: str = "runtime-secret-token"):
    return SimpleNamespace(
        token=SimpleNamespace(
            access_token=token,
            user_id=user_id,
            scopes=("instagram_business_basic", "instagram_business_content_publish"),
        )
    )


def test_prepared_roundtrip_persists_only_non_secret_evidence(tmp_path):
    store = _store(tmp_path)
    prepared = _prepared()

    ref = persist_prepared_instagram_reel(store, prepared)
    payload = store.read_json(PROJECT_ID, ref.artifact_id, verify_integrity=True)

    assert ref.artifact_type == INSTAGRAM_PREPARED_REEL_ARTIFACT_TYPE
    assert payload["contains_credentials"] is False
    assert payload["auto_publication"] is False
    text = str(payload).lower()
    assert "access_token" not in text
    assert "refresh_token" not in text
    assert "client_secret" not in text
    assert "runtime-secret-token" not in text

    loaded = load_latest_prepared_instagram_reel(store, PROJECT_ID)
    assert loaded is not None
    assert loaded.artifact_id == ref.artifact_id
    assert loaded.prepared == prepared


def test_prepare_requires_approval_before_verify_or_oauth(tmp_path, monkeypatch):
    store = _store(tmp_path)
    calls = []
    monkeypatch.setattr(
        "app.services.instagram_manual_publication.verify_publication_package",
        lambda *args, **kwargs: calls.append("verify"),
    )

    with pytest.raises(CentinelaError) as exc_info:
        prepare_instagram_manual_publication(
            store,
            PROJECT_ID,
            approved=False,
            oauth_authorize=lambda: calls.append("oauth"),
        )

    assert exc_info.value.code == "human_approval_required"
    assert calls == []


def test_prepare_preverifies_oauths_prepares_and_persists_without_token(tmp_path, monkeypatch):
    store = _store(tmp_path)
    prepared = _prepared()
    order = []

    def fake_verify(store_arg, project_id):
        assert store_arg is store
        assert project_id == PROJECT_ID
        order.append("verify")
        return _package(prepared)

    def fake_oauth():
        order.append("oauth")
        return _oauth()

    def fake_prepare(store_arg, project_id, **kwargs):
        assert store_arg is store
        assert project_id == PROJECT_ID
        assert kwargs["ig_user_id"] == prepared.ig_user_id
        assert kwargs["access_token"] == "runtime-secret-token"
        assert kwargs["approved"] is True
        order.append("prepare")
        return prepared

    monkeypatch.setattr(
        "app.services.instagram_manual_publication.verify_publication_package",
        fake_verify,
    )

    record = prepare_instagram_manual_publication(
        store,
        PROJECT_ID,
        approved=True,
        oauth_authorize=fake_oauth,
        prepare=fake_prepare,
    )

    assert order == ["verify", "oauth", "prepare"]
    assert record.prepared == prepared
    payload = store.read_json(PROJECT_ID, record.artifact_id, verify_integrity=True)
    assert "runtime-secret-token" not in str(payload)


def test_publish_requires_second_approval_before_loading_or_oauth(tmp_path):
    store = _store(tmp_path)
    calls = []

    with pytest.raises(CentinelaError) as exc_info:
        publish_instagram_manual_publication(
            store,
            PROJECT_ID,
            approved=False,
            oauth_authorize=lambda: calls.append("oauth"),
        )

    assert exc_info.value.code == "human_approval_required"
    assert calls == []


def test_publish_blocks_stale_package_before_second_oauth(tmp_path, monkeypatch):
    store = _store(tmp_path)
    persist_prepared_instagram_reel(store, _prepared())
    calls = []

    stale = _package()
    stale.publication_package_hash = "d" * 64
    monkeypatch.setattr(
        "app.services.instagram_manual_publication.verify_publication_package",
        lambda *args, **kwargs: stale,
    )

    with pytest.raises(CentinelaError) as exc_info:
        publish_instagram_manual_publication(
            store,
            PROJECT_ID,
            approved=True,
            oauth_authorize=lambda: calls.append("oauth"),
        )

    assert exc_info.value.code == "instagram_prepared_package_stale"
    assert calls == []


def test_publish_rejects_different_second_instagram_account(tmp_path, monkeypatch):
    store = _store(tmp_path)
    prepared = _prepared()
    persist_prepared_instagram_reel(store, prepared)
    calls = []
    monkeypatch.setattr(
        "app.services.instagram_manual_publication.verify_publication_package",
        lambda *args, **kwargs: _package(prepared),
    )

    def fake_publish(*args, **kwargs):
        calls.append("publish")
        return object()

    with pytest.raises(CentinelaError) as exc_info:
        publish_instagram_manual_publication(
            store,
            PROJECT_ID,
            approved=True,
            oauth_authorize=lambda: _oauth(user_id="another-account"),
            publish=fake_publish,
        )

    assert exc_info.value.code == "instagram_publish_account_mismatch"
    assert calls == []


def test_successful_publish_writes_receipt_and_blocks_duplicate_before_oauth(tmp_path, monkeypatch):
    store = _store(tmp_path)
    prepared = _prepared()
    record = persist_prepared_instagram_reel(store, prepared)
    order = []
    monkeypatch.setattr(
        "app.services.instagram_manual_publication.verify_publication_package",
        lambda *args, **kwargs: _package(prepared),
    )

    def fake_oauth():
        order.append("oauth")
        return _oauth()

    def fake_publish(store_arg, prepared_arg, **kwargs):
        assert store_arg is store
        assert prepared_arg == prepared
        assert kwargs == {"access_token": "runtime-secret-token", "approved": True}
        order.append("publish")
        return SocialResult(
            success=True,
            platform=SocialPlatform.INSTAGRAM,
            mode=PublicationMode.INSTAGRAM_REEL,
            remote_id="media-123",
            status="PUBLISHED",
        )

    result = publish_instagram_manual_publication(
        store,
        PROJECT_ID,
        approved=True,
        oauth_authorize=fake_oauth,
        publish=fake_publish,
    )

    assert result.success is True
    assert order == ["oauth", "publish"]
    intents = store.list_artifacts(PROJECT_ID, artifact_type=INSTAGRAM_PUBLISH_INTENT_ARTIFACT_TYPE)
    assert len(intents) == 1
    intent_payload = store.read_json(PROJECT_ID, intents[0].artifact_id, verify_integrity=True)
    assert intent_payload["status"] == "STARTED"
    assert intent_payload["contains_credentials"] is False
    assert "runtime-secret-token" not in str(intent_payload)
    receipt = get_instagram_publish_receipt(store, PROJECT_ID)
    assert receipt is not None
    assert receipt.prepared_artifact_id == record.artifact_id
    assert receipt.remote_id == "media-123"
    payload = store.read_json(PROJECT_ID, receipt.artifact_id, verify_integrity=True)
    assert payload["contains_credentials"] is False
    assert payload["auto_publication"] is False
    assert "runtime-secret-token" not in str(payload)

    second_calls = []
    with pytest.raises(CentinelaError) as exc_info:
        publish_instagram_manual_publication(
            store,
            PROJECT_ID,
            approved=True,
            oauth_authorize=lambda: second_calls.append("oauth"),
            publish=lambda *args, **kwargs: second_calls.append("publish"),
        )
    assert exc_info.value.code == "instagram_prepared_container_already_published"
    assert second_calls == []


def test_remote_success_plus_receipt_failure_blocks_automatic_assumption(tmp_path, monkeypatch):
    store = _store(tmp_path)
    prepared = _prepared()
    persist_prepared_instagram_reel(store, prepared)
    monkeypatch.setattr(
        "app.services.instagram_manual_publication.verify_publication_package",
        lambda *args, **kwargs: _package(prepared),
    )

    original_put_json = store.put_json

    def failing_put_json(project_id, artifact_type, payload, **kwargs):
        if artifact_type == INSTAGRAM_PUBLISH_RECEIPT_ARTIFACT_TYPE:
            raise OSError("disk unavailable")
        return original_put_json(project_id, artifact_type, payload, **kwargs)

    monkeypatch.setattr(store, "put_json", failing_put_json)

    def fake_publish(*args, **kwargs):
        return SocialResult(
            success=True,
            platform=SocialPlatform.INSTAGRAM,
            mode=PublicationMode.INSTAGRAM_REEL,
            remote_id="media-uncertain",
            status="PUBLISHED",
        )

    with pytest.raises(CentinelaError) as exc_info:
        publish_instagram_manual_publication(
            store,
            PROJECT_ID,
            approved=True,
            oauth_authorize=lambda: _oauth(),
            publish=fake_publish,
        )

    assert exc_info.value.code == "instagram_publish_receipt_persistence_failed"
    assert exc_info.value.retryable is False
    assert "No reintentes automáticamente" in exc_info.value.safe_message
    unresolved = get_unresolved_instagram_publish_intent(store, PROJECT_ID)
    assert unresolved is not None
    second_calls = []
    with pytest.raises(CentinelaError) as second_exc:
        publish_instagram_manual_publication(
            store,
            PROJECT_ID,
            approved=True,
            oauth_authorize=lambda: second_calls.append("oauth"),
            publish=lambda *args, **kwargs: second_calls.append("publish"),
        )
    assert second_exc.value.code == "instagram_publish_outcome_unresolved"
    assert second_calls == []


def test_publish_intent_persistence_failure_prevents_remote_call(tmp_path, monkeypatch):
    store = _store(tmp_path)
    prepared = _prepared()
    persist_prepared_instagram_reel(store, prepared)
    monkeypatch.setattr(
        "app.services.instagram_manual_publication.verify_publication_package",
        lambda *args, **kwargs: _package(prepared),
    )
    original_put_json = store.put_json
    calls = []

    def failing_put_json(project_id, artifact_type, payload, **kwargs):
        if artifact_type == INSTAGRAM_PUBLISH_INTENT_ARTIFACT_TYPE:
            raise OSError("intent disk failure")
        return original_put_json(project_id, artifact_type, payload, **kwargs)

    monkeypatch.setattr(store, "put_json", failing_put_json)
    with pytest.raises(CentinelaError) as exc_info:
        publish_instagram_manual_publication(
            store,
            PROJECT_ID,
            approved=True,
            oauth_authorize=lambda: _oauth(),
            publish=lambda *args, **kwargs: calls.append("publish"),
        )
    assert exc_info.value.code == "instagram_publish_intent_persistence_failed"
    assert calls == []
