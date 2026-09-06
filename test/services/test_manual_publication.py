from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from app.services.centinela.manual_publication import (
    ManualPublicationPlatform,
    publish_verified_package,
    verify_publication_package,
)
from app.services.centinela.orchestration import (
    PROGRESSION_STATES,
    ProjectState,
    ProjectStateMachine,
)
from app.services.centinela.project_foundation import ArtifactStore
from app.services.centinela.publication_package import (
    PUBLICATION_MANIFEST_ARTIFACT_TYPE,
    TARGETS,
)
from app.services.error_control import CentinelaError


class _FakeYouTube:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def upload_private(self, video_path, **kwargs):
        self.calls.append({"video_path": Path(video_path), **kwargs})
        return {"platform": "youtube", "status": "uploaded_private"}


class _FakeTikTok:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def upload_to_inbox(self, video_path, **kwargs):
        self.calls.append({"video_path": Path(video_path), **kwargs})
        return {"platform": "tiktok", "status": "uploaded_to_inbox"}


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _advance(store: ArtifactStore, project_id: str, target: ProjectState) -> None:
    machine = ProjectStateMachine(store)
    current = machine.current_state(project_id)
    start = PROGRESSION_STATES.index(current) + 1
    stop = PROGRESSION_STATES.index(target) + 1
    for state in PROGRESSION_STATES[start:stop]:
        machine.transition(
            project_id,
            state,
            reason="C6 test progression",
            actor="c6-test",
        )


def _fixture(
    tmp_path: Path,
    *,
    ready: bool = True,
    manifest_auto_publication: bool = False,
):
    store = ArtifactStore(tmp_path / "store")
    project = store.create_project("C6 verified manual publication")
    target = (
        ProjectState.PUBLICATION_PACKAGE_READY
        if ready
        else ProjectState.FINAL_APPROVED
    )
    _advance(store, project.project_id, target)

    if not ready:
        return store, project.project_id, None

    package_dir = (
        store.root
        / "publication-packages"
        / project.project_id
        / "publication-package-c6fixture"
    )
    package_dir.mkdir(parents=True)

    metadata = {
        "title": "Júpiter sobre el horizonte",
        "caption": "Júpiter, listo para publicación manual.",
        "hashtags": ["#astronomia", "#jupiter"],
        "youtube_description": "Descripción YouTube aprobada.",
    }
    payloads = {
        "master": b"C6 master video",
        "social": b"C6 approved social video",
        "thumbnail": b"C6 thumbnail",
        "subtitles_es": b"1\n00:00:00,000 --> 00:00:01,000\nJupiter.\n",
        "provenance": b'{"rights":"verified"}\n',
        "publication_checklist": b'{"review_7_of_7":true}\n',
        "caption": metadata["caption"].encode("utf-8"),
        "metadata": (json.dumps(metadata, ensure_ascii=False, sort_keys=True) + "\n").encode(
            "utf-8"
        ),
    }

    rows = []
    for logical_name, relative_path in TARGETS.items():
        path = package_dir / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        data = payloads[logical_name]
        path.write_bytes(data)
        digest = _sha(data)
        rows.append(
            {
                "logical_name": logical_name,
                "relative_path": relative_path,
                "size_bytes": len(data),
                "sha256": digest,
                "source_artifact_id": f"c6-source-{logical_name}",
                "source_sha256": digest,
            }
        )

    review_id = "c6-review-approved"
    manifest = {
        "version": "g006-publication-package-v0.1",
        "project_id": project.project_id,
        "package_id": "publication-package-c6fixture",
        "publication_package_hash": "a" * 64,
        "human_review_artifact_id": review_id,
        "final_render_artifact_id": "c6-final-render",
        "asset_count": 8,
        "assets": rows,
        "source_artifacts_preserved": True,
        "post_review_content_mutation": False,
        "manual_publication_only": True,
        "auto_publication": manifest_auto_publication,
        "authorization_to_publish": False,
        "marks_published": False,
        "uploads_files": False,
        "webhook_calls": 0,
        "package_network_calls": 0,
    }
    store.put_json(
        project.project_id,
        PUBLICATION_MANIFEST_ARTIFACT_TYPE,
        manifest,
        producer="c6-test",
        artifact_id="c6-publication-manifest",
        provenance={
            "package_dir": str(package_dir),
            "human_review_artifact_id": review_id,
            "final_render_artifact_id": "c6-final-render",
        },
        metadata={
            "asset_count": 8,
            "manual_publication_only": True,
            "auto_publication": manifest_auto_publication,
            "authorization_to_publish": False,
        },
    )
    return store, project.project_id, package_dir


def test_manual_publication_requires_fresh_explicit_approval(tmp_path: Path):
    store, project_id, _ = _fixture(tmp_path)
    youtube = _FakeYouTube()

    with pytest.raises(CentinelaError) as exc_info:
        publish_verified_package(
            store,
            project_id,
            ManualPublicationPlatform.YOUTUBE,
            access_token="ephemeral-token",
            youtube_adapter=youtube,
        )

    assert exc_info.value.code == "human_approval_required"
    assert youtube.calls == []


def test_project_must_be_publication_package_ready(tmp_path: Path):
    store, project_id, _ = _fixture(tmp_path, ready=False)
    youtube = _FakeYouTube()

    with pytest.raises(CentinelaError) as exc_info:
        publish_verified_package(
            store,
            project_id,
            "youtube",
            access_token="ephemeral-token",
            approved=True,
            youtube_adapter=youtube,
        )

    assert exc_info.value.code == "publication_package_not_ready"
    assert youtube.calls == []


def test_verified_youtube_uses_only_approved_package_payload_and_metadata(tmp_path: Path):
    store, project_id, _ = _fixture(tmp_path)
    youtube = _FakeYouTube()

    result = publish_verified_package(
        store,
        project_id,
        "youtube",
        access_token="ephemeral-token",
        approved=True,
        youtube_adapter=youtube,
    )

    assert result["status"] == "uploaded_private"
    assert len(youtube.calls) == 1
    call = youtube.calls[0]
    assert call["video_path"].read_bytes() == b"C6 approved social video"
    assert call["access_token"] == "ephemeral-token"
    assert call["title"] == "Júpiter sobre el horizonte"
    assert call["description"] == "Descripción YouTube aprobada."
    assert call["tags"] == ["#astronomia", "#jupiter"]
    assert call["approved"] is True


def test_verified_tiktok_uses_same_certified_social_asset(tmp_path: Path):
    store, project_id, _ = _fixture(tmp_path)
    tiktok = _FakeTikTok()

    result = publish_verified_package(
        store,
        project_id,
        "tiktok",
        access_token="ephemeral-token",
        approved=True,
        tiktok_adapter=tiktok,
    )

    assert result["status"] == "uploaded_to_inbox"
    assert len(tiktok.calls) == 1
    assert tiktok.calls[0]["video_path"].read_bytes() == b"C6 approved social video"
    assert tiktok.calls[0]["approved"] is True


def test_tampered_social_asset_blocks_before_any_network_adapter(tmp_path: Path):
    store, project_id, package_dir = _fixture(tmp_path)
    assert package_dir is not None
    (package_dir / TARGETS["social"]).write_bytes(b"tampered after approval")
    youtube = _FakeYouTube()

    with pytest.raises(CentinelaError) as exc_info:
        publish_verified_package(
            store,
            project_id,
            "youtube",
            access_token="ephemeral-token",
            approved=True,
            youtube_adapter=youtube,
        )

    assert exc_info.value.code == "publication_package_asset_integrity_mismatch"
    assert youtube.calls == []


def test_auto_publication_marker_regression_blocks_package(tmp_path: Path):
    store, project_id, _ = _fixture(tmp_path, manifest_auto_publication=True)

    with pytest.raises(CentinelaError) as exc_info:
        verify_publication_package(store, project_id)

    assert exc_info.value.code == "publication_package_safety_contract_invalid"


def test_instagram_is_fail_closed_until_hosted_bytes_can_be_verified(tmp_path: Path):
    store, project_id, _ = _fixture(tmp_path)

    with pytest.raises(CentinelaError) as exc_info:
        publish_verified_package(
            store,
            project_id,
            "instagram",
            access_token="ephemeral-token",
            approved=True,
        )

    assert exc_info.value.code == "instagram_verified_hosting_required"
