from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.models.astromedia import Provider, Rights
from app.models.final_render import (
    MASTER_PROFILE_ID,
    SOCIAL_PROFILE_ID,
    FinalRenderArtifact,
    FinalRenderResult,
)
from app.models.finalization_e2e import (
    FinalizationE2EStatus,
    HumanFinalReviewDecision,
    HumanFinalReviewRecord,
)
from app.models.publication_package import (
    PublicationMetadata,
    PublicationPackageRequest,
    PublicationSupportAssetProbe,
    PublicationSupportManifest,
)
from app.models.video_base_e2e import (
    VideoBaseE2ECheck,
    VideoBaseE2EPlan,
    VideoBaseE2EStatus,
)
from app.services.centinela.av_runtime import VideoBaseManifest, build_finalization_request
from app.services.centinela.media_resolver import (
    FocalEvidence,
    MediaResolutionReport,
    ResolverGuardrails,
    SceneMediaEvidence,
    SemanticEvidence,
)
from app.services.centinela.orchestration import JobStatus, ProjectState
from app.services.centinela.production_spine import (
    STAGE_DESCRIPTORS,
    STRUCTURED_HUMAN_REVIEW_ARTIFACT_TYPE,
    SpineStage,
    StageArtifact,
    StageBinding,
    StageResult,
)
from app.services.centinela.project_foundation import ArtifactStore
from app.services.centinela.publication_package import (
    FINALIZATION_EVIDENCE_ARTIFACT_TYPE,
    PUBLICATION_INPUT_ARTIFACT_TYPE,
    PUBLICATION_MANIFEST_ARTIFACT_TYPE,
    PUBLICATION_PLAN_ARTIFACT_TYPE,
    PackageSource,
    PublicationPackageBlockedError,
    PublicationPackageInputRecord,
    PublicationPackageMaterializer,
    _compact_json_bytes,
    _make_sources,
    _package_support_bytes,
    _sha256_bytes,
    persist_publication_package_input,
    validate_rights_provenance,
)
from app.services.centinela.research_adapters.integration import C3ResearchControlCenter
from app.services.finalization_e2e import build_finalization_e2e
from app.services.publication_package import build_publication_package

NOW = datetime(2026, 9, 3, 20, 0, tzinfo=timezone.utc)
CONTEXT_HASH = "context-g006"
REVIEW_FIELDS = (
    "science_passed",
    "visual_passed",
    "audio_passed",
    "subtitles_passed",
    "rights_passed",
    "thumbnail_passed",
    "copy_passed",
)


class _FakeCatalog:
    def list_items(self, active_only=True):
        del active_only
        return []


def _review(**overrides) -> HumanFinalReviewRecord:
    values = {field: True for field in REVIEW_FIELDS}
    values.update(overrides)
    return HumanFinalReviewRecord(
        decision=HumanFinalReviewDecision.APPROVE,
        reviewer_ref="g006-reviewer",
        rationale="G-006 explicit structured review.",
        decided_at_utc=NOW,
        **values,
    )


def _fixture_stage_binding(stage: SpineStage) -> StageBinding:
    descriptor = STAGE_DESCRIPTORS[stage]

    def handler(context, payload):
        del payload
        return StageResult.complete(
            *(
                StageArtifact(
                    artifact_type=artifact_type,
                    payload={
                        "fixture": "G006",
                        "stage": stage.value,
                        "project_id": context.project_id,
                    },
                )
                for artifact_type in descriptor.required_artifact_types
            ),
            message=f"{stage.value} fixture complete",
        )

    return StageBinding(
        adapter_id=f"g006_fixture_{stage.value.lower()}",
        handler=handler,
        resource_class=descriptor.minimum_resource_class,
    )


def _advance_to_review(service: C3ResearchControlCenter, project_id: str) -> None:
    for stage in (
        SpineStage.RESEARCH,
        SpineStage.SCRIPT,
        SpineStage.SCENES,
        SpineStage.MEDIA,
        SpineStage.AUDIO,
        SpineStage.VIDEO_BASE,
        SpineStage.REVIEW_PREP,
    ):
        service.register_stage(stage, _fixture_stage_binding(stage), replace=True)
        schedule = service.spine.schedule_stage(project_id, stage, request={})
        record = service.spine.wait(schedule.job_id, timeout=10)
        assert record.status == JobStatus.SUCCEEDED
    assert service.project(project_id).state == ProjectState.READY_FOR_HUMAN_REVIEW


def _media_report() -> MediaResolutionReport:
    return MediaResolutionReport(
        subject="Jupiter",
        source_plan_context_hash=CONTEXT_HASH,
        selector_version="selector-g006",
        catalog_item_count=1,
        catalog_provider_counts={"OWN_MEDIA": 1},
        catalog_refreshed=False,
        scene_count=1,
        selected_count=1,
        unresolved_count=0,
        rights_review_count=0,
        review_required=False,
        publication_ready=True,
        scenes=[
            SceneMediaEvidence(
                scene_number=1,
                scene_key=f"{CONTEXT_HASH}:scene:1",
                query="Jupiter",
                candidate_count=0,
                candidates=[],
                semantic=SemanticEvidence(
                    requested=False,
                    analyzed=False,
                    method="g006_fixture",
                ),
                selection_status="SELECTED",
                selected_media_id="owned-jupiter-001",
                selected_provider=Provider.OWN_MEDIA,
                selected_rights_status=Rights.CONFIRMED_OWNED,
                selected_publication_eligible=True,
                focal=FocalEvidence(applicable=False, method="g006_fixture"),
            )
        ],
        guardrails=ResolverGuardrails(),
        generated_at_utc=NOW,
    )


def _persist_evidence(
    store: ArtifactStore,
    project_id: str,
    review_ref,
    review: HumanFinalReviewRecord,
):
    material_ref = store.put_json(
        project_id,
        "material_selection",
        {"fixture": "G006"},
        producer="g006-test",
        artifact_id="g006-material-selection",
    )
    audio_bundle_ref = store.put_json(
        project_id,
        "audio_bundle",
        {"fixture": "G006"},
        producer="g006-test",
        artifact_id="g006-audio-bundle",
    )
    audio_master_ref = store.put_bytes(
        project_id,
        "voice_master",
        b"G006 approved audio",
        producer="g006-test",
        artifact_id="g006-audio-master",
        suffix=".wav",
    )
    subtitle_ref = store.put_bytes(
        project_id,
        "subtitle_srt",
        b"1\n00:00:00,000 --> 00:00:01,000\nJupiter aprobado.\n",
        producer="g006-test",
        artifact_id="g006-subtitles",
        suffix=".srt",
    )
    media = _media_report()
    media_ref = store.put_json(
        project_id,
        "media_resolution",
        media.model_dump(mode="json"),
        producer="g006-test",
        artifact_id="g006-media-resolution",
        input_artifact_ids=(material_ref.artifact_id,),
    )
    base_master_ref = store.put_bytes(
        project_id,
        "video_base_master",
        b"G006 clean base master",
        producer="g006-test",
        artifact_id="g006-base-master",
        suffix=".mp4",
        input_artifact_ids=(media_ref.artifact_id,),
    )
    base_social_ref = store.put_bytes(
        project_id,
        "video_base_social",
        b"G006 clean base social",
        producer="g006-test",
        artifact_id="g006-base-social",
        suffix=".mp4",
        input_artifact_ids=(media_ref.artifact_id,),
    )
    video_manifest = VideoBaseManifest(
        subject="Jupiter",
        source_plan_context_hash=CONTEXT_HASH,
        source_audio_bundle_artifact_id=audio_bundle_ref.artifact_id,
        source_material_selection_artifact_id=material_ref.artifact_id,
        source_media_resolution_artifact_id=media_ref.artifact_id,
        social_video_artifact_id=base_social_ref.artifact_id,
        master_video_artifact_id=base_master_ref.artifact_id,
        review_preview_artifact_id="g006-review-preview-unused",
        subtitle_artifact_id=subtitle_ref.artifact_id,
        social_codec="h264",
        master_codec="h264",
        social_codec_fallback=False,
        master_codec_fallback=False,
        social_duration_seconds=2.0,
        master_duration_seconds=2.0,
        review_preview_duration_seconds=2.0,
        social_sha256=base_social_ref.sha256,
        master_sha256=base_master_ref.sha256,
        review_preview_sha256="0" * 64,
        smartfocal_scene_count=0,
        fit_scene_count=1,
        cover_scene_count=0,
        scene_count=1,
        social_render_manifest={"profile_id": "SOCIAL_VERTICAL_1080X1920"},
        master_render_manifest={"profile_id": "MASTER_VERTICAL_2160X3840"},
        generated_at_utc=NOW,
    )
    video_manifest_ref = store.put_json(
        project_id,
        "video_base_manifest",
        video_manifest.model_dump(mode="json"),
        producer="g006-test",
        artifact_id="g006-video-base-manifest",
        input_artifact_ids=(
            base_master_ref.artifact_id,
            base_social_ref.artifact_id,
            media_ref.artifact_id,
            subtitle_ref.artifact_id,
        ),
    )
    final_master_ref = store.put_bytes(
        project_id,
        "final_master_video",
        b"G006 final master with audio",
        producer="g006-test",
        artifact_id="g006-final-master",
        suffix=".mp4",
        input_artifact_ids=(
            base_master_ref.artifact_id,
            video_manifest_ref.artifact_id,
            media_ref.artifact_id,
            subtitle_ref.artifact_id,
            review_ref.artifact_id,
        ),
    )
    final_social_ref = store.put_bytes(
        project_id,
        "final_social_video",
        b"G006 final social with audio",
        producer="g006-test",
        artifact_id="g006-final-social",
        suffix=".mp4",
        input_artifact_ids=(
            base_social_ref.artifact_id,
            video_manifest_ref.artifact_id,
            media_ref.artifact_id,
            subtitle_ref.artifact_id,
            review_ref.artifact_id,
        ),
    )
    final_render = FinalRenderResult(
        project_id=project_id,
        input_fingerprint="a" * 64,
        manifest_artifact_id="g006-final-render-manifest",
        human_review_artifact_id=review_ref.artifact_id,
        human_review=review,
        video_base_manifest_artifact_id=video_manifest_ref.artifact_id,
        audio_bundle_artifact_id=audio_bundle_ref.artifact_id,
        media_resolution_artifact_id=media_ref.artifact_id,
        subtitle_artifact_id=subtitle_ref.artifact_id,
        subtitle_sha256=subtitle_ref.sha256,
        master=FinalRenderArtifact(
            profile_id=MASTER_PROFILE_ID,
            artifact_id=final_master_ref.artifact_id,
            file_path=str(store.resolve_artifact_path(project_id, final_master_ref.artifact_id)),
            sha256=final_master_ref.sha256,
            width=2160,
            height=3840,
            fps=30.0,
            codec="h264",
            duration_seconds=2.0,
            audio_stream_count=1,
            source_video_base_artifact_id=base_master_ref.artifact_id,
            source_video_base_sha256=base_master_ref.sha256,
            source_audio_artifact_id=audio_master_ref.artifact_id,
            source_subtitle_artifact_id=subtitle_ref.artifact_id,
            audio_codec="aac",
            ffprobe={},
        ),
        social=FinalRenderArtifact(
            profile_id=SOCIAL_PROFILE_ID,
            artifact_id=final_social_ref.artifact_id,
            file_path=str(store.resolve_artifact_path(project_id, final_social_ref.artifact_id)),
            sha256=final_social_ref.sha256,
            width=1080,
            height=1920,
            fps=30.0,
            codec="h264",
            duration_seconds=2.0,
            audio_stream_count=1,
            source_video_base_artifact_id=base_social_ref.artifact_id,
            source_video_base_sha256=base_social_ref.sha256,
            source_audio_artifact_id=audio_master_ref.artifact_id,
            source_subtitle_artifact_id=subtitle_ref.artifact_id,
            audio_codec="aac",
            ffprobe={},
        ),
        rights_provenance={
            "media_resolution_artifact_id": media_ref.artifact_id,
            "media_resolution_sha256": media_ref.sha256,
            "upstream_publication_ready": True,
            "human_review_rights_passed": True,
            "selected_media": [
                {
                    "scene_number": 1,
                    "media_id": "owned-jupiter-001",
                    "provider": Provider.OWN_MEDIA.value,
                    "rights_status": Rights.CONFIRMED_OWNED.value,
                    "publication_eligible": True,
                    "source_url": None,
                    "license_name": None,
                    "license_url": None,
                    "attribution": None,
                    "attribution_required": False,
                }
            ],
        },
        generated_at_utc=NOW,
    )
    final_render_ref = store.put_json(
        project_id,
        "final_render_manifest",
        final_render.model_dump(mode="json"),
        producer="g006-test",
        artifact_id=final_render.manifest_artifact_id,
        input_artifact_ids=(
            final_master_ref.artifact_id,
            final_social_ref.artifact_id,
            video_manifest_ref.artifact_id,
            audio_bundle_ref.artifact_id,
            media_ref.artifact_id,
            audio_master_ref.artifact_id,
            subtitle_ref.artifact_id,
            review_ref.artifact_id,
        ),
        provenance={"human_review_artifact_id": review_ref.artifact_id},
        metadata={"input_fingerprint": final_render.input_fingerprint},
    )
    return {
        "media": media,
        "media_ref": media_ref,
        "video_manifest": video_manifest,
        "video_manifest_ref": video_manifest_ref,
        "final_render": final_render,
        "final_render_ref": final_render_ref,
        "final_master_ref": final_master_ref,
        "final_social_ref": final_social_ref,
        "subtitle_ref": subtitle_ref,
    }


def _video_e2e_pass() -> VideoBaseE2EPlan:
    checks = [VideoBaseE2ECheck(check_id="g006-fixture", passed=True, detail="verified")]
    return VideoBaseE2EPlan(
        source_production_orchestrator_hash="g006-fixture",
        status=VideoBaseE2EStatus.VIDEO_BASE_E2E_PASS,
        real_artifact_present=True,
        check_count=1,
        passed_count=1,
        failed_count=0,
        checks=checks,
        video_base_e2e_hash="B" * 64,
        generated_at_utc=NOW,
    )


def _materializer_fixture(tmp_path):
    store = ArtifactStore(tmp_path / "store")
    project = store.create_project("G-006 materializer")
    review = _review()
    review_ref = store.put_json(
        project.project_id,
        STRUCTURED_HUMAN_REVIEW_ARTIFACT_TYPE,
        review.model_dump(mode="json"),
        producer="g006-test",
        artifact_id="g006-review",
    )
    evidence = _persist_evidence(store, project.project_id, review_ref, review)
    thumbnail_ref = store.put_bytes(
        project.project_id,
        "publication_thumbnail",
        b"\xff\xd8G006-thumbnail\xff\xd9",
        producer="g006-test",
        artifact_id="g006-thumbnail",
        suffix=".jpg",
        input_artifact_ids=(review_ref.artifact_id,),
    )
    thumbnail_path = store.resolve_artifact_path(project.project_id, thumbnail_ref.artifact_id)
    finalization = build_finalization_e2e(
        build_finalization_request(_video_e2e_pass(), evidence["final_render"])
    )
    assert finalization.status == FinalizationE2EStatus.FINALIZATION_E2E_PASS
    metadata = PublicationMetadata(
        title="Jupiter",
        caption="Júpiter, listo para publicación manual.",
        hashtags=["#astronomia"],
        youtube_description="G-006 fixture",
    )
    provenance_bytes, checklist_bytes = _package_support_bytes(
        evidence["final_render"],
        finalization,
        review_ref,
        review,
    )
    support = PublicationSupportManifest(
        thumbnail=PublicationSupportAssetProbe(
            source_path=str(thumbnail_path),
            present=True,
            sha256=thumbnail_ref.sha256,
        ),
        subtitles_es=PublicationSupportAssetProbe(
            source_path=str(
                store.resolve_artifact_path(project.project_id, evidence["subtitle_ref"].artifact_id)
            ),
            present=True,
            sha256=evidence["subtitle_ref"].sha256,
        ),
        provenance=PublicationSupportAssetProbe(
            present=True,
            sha256=_sha256_bytes(provenance_bytes),
        ),
        review_checklist=PublicationSupportAssetProbe(
            present=True,
            sha256=_sha256_bytes(checklist_bytes),
        ),
    )
    plan = build_publication_package(
        PublicationPackageRequest(
            finalization=finalization,
            metadata=metadata,
            support=support,
        )
    )
    sources = _make_sources(
        plan,
        metadata,
        evidence["final_render"],
        evidence["final_master_ref"],
        store.resolve_artifact_path(project.project_id, evidence["final_master_ref"].artifact_id),
        evidence["final_social_ref"],
        store.resolve_artifact_path(project.project_id, evidence["final_social_ref"].artifact_id),
        thumbnail_ref,
        thumbnail_path,
        evidence["subtitle_ref"],
        store.resolve_artifact_path(project.project_id, evidence["subtitle_ref"].artifact_id),
        provenance_bytes,
        checklist_bytes,
    )
    return {
        "store": store,
        "project_id": project.project_id,
        "review": review,
        "review_ref": review_ref,
        "evidence": evidence,
        "finalization": finalization,
        "metadata": metadata,
        "plan": plan,
        "sources": sources,
    }


def _materialize(env):
    return PublicationPackageMaterializer(env["store"]).materialize(
        env["project_id"],
        env["plan"],
        env["finalization"],
        env["review"],
        env["sources"],
        human_review_artifact_id=env["review_ref"].artifact_id,
        final_render_artifact_id=env["evidence"]["final_render_ref"].artifact_id,
    )


def test_rights_provenance_contract_accepts_current_owned_media(tmp_path):
    env = _materializer_fixture(tmp_path)
    media_ref, media = validate_rights_provenance(
        env["store"],
        env["project_id"],
        env["evidence"]["final_render"],
        env["evidence"]["video_manifest"],
        env["review"],
    )
    assert media_ref.artifact_id == env["evidence"]["media_ref"].artifact_id
    assert media.publication_ready is True


@pytest.mark.parametrize(
    "case",
    [
        "missing",
        "publication_not_ready",
        "review_rights_false",
        "media_id_missing",
        "media_sha_missing",
        "media_sha_mismatch",
        "selected_media_missing",
        "publication_eligibility_false",
        "rights_status_invalid",
        "project_mismatch",
        "lineage_mismatch",
    ],
)
def test_rights_provenance_fail_closed(tmp_path, case):
    env = _materializer_fixture(tmp_path)
    final_render = env["evidence"]["final_render"]
    video_manifest = env["evidence"]["video_manifest"]
    review = env["review"]
    provenance = dict(final_render.rights_provenance)

    if case == "missing":
        provenance = {}
    elif case == "publication_not_ready":
        provenance["upstream_publication_ready"] = False
    elif case == "review_rights_false":
        review = review.model_copy(update={"rights_passed": False})
    elif case == "media_id_missing":
        provenance["media_resolution_artifact_id"] = ""
    elif case == "media_sha_missing":
        provenance["media_resolution_sha256"] = ""
    elif case == "media_sha_mismatch":
        provenance["media_resolution_sha256"] = "0" * 64
    elif case == "selected_media_missing":
        provenance["selected_media"] = []
    elif case == "publication_eligibility_false":
        rows = [dict(row) for row in provenance["selected_media"]]
        rows[0]["publication_eligible"] = False
        provenance["selected_media"] = rows
    elif case == "rights_status_invalid":
        rows = [dict(row) for row in provenance["selected_media"]]
        rows[0]["rights_status"] = Rights.UNVERIFIED.value
        provenance["selected_media"] = rows
    elif case == "project_mismatch":
        final_render = final_render.model_copy(update={"project_id": "other-project"})
    elif case == "lineage_mismatch":
        video_manifest = video_manifest.model_copy(
            update={"source_media_resolution_artifact_id": "other-media"}
        )

    if case not in {"project_mismatch"}:
        final_render = final_render.model_copy(update={"rights_provenance": provenance})

    with pytest.raises(PublicationPackageBlockedError):
        validate_rights_provenance(
            env["store"],
            env["project_id"],
            final_render,
            video_manifest,
            review,
        )


def test_materializer_happy_path_has_exact_eight_assets_and_safety_flags(tmp_path):
    env = _materializer_fixture(tmp_path)
    result = _materialize(env)
    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert result.reused is False
    assert manifest["asset_count"] == 8
    assert {row["logical_name"] for row in manifest["assets"]} == set(env["sources"])
    assert not (result.package_dir / "manifest.json") in [
        result.package_dir / row["relative_path"] for row in manifest["assets"]
    ]
    assert manifest["manual_publication_only"] is True
    assert manifest["auto_publication"] is False
    assert manifest["authorization_to_publish"] is False
    assert manifest["marks_published"] is False
    assert manifest["uploads_files"] is False
    assert manifest["webhook_calls"] == 0
    assert manifest["package_network_calls"] == 0
    assert manifest["source_artifacts_preserved"] is True
    assert manifest["post_review_content_mutation"] is False

    plan = env["plan"]
    assert plan.planning_only is True
    assert plan.writes_files is False
    assert plan.uploads_files is False
    assert plan.network_calls == 0
    assert plan.webhook_calls == 0
    assert plan.auto_publication is False
    assert plan.authorization_to_publish is False
    assert plan.marks_published is False
    assert plan.manual_publication_only is True


@pytest.mark.parametrize("missing", sorted({
    "master",
    "social",
    "thumbnail",
    "subtitles_es",
    "provenance",
    "publication_checklist",
    "caption",
    "metadata",
}))
def test_materializer_blocks_each_missing_source(tmp_path, missing):
    env = _materializer_fixture(tmp_path)
    sources = dict(env["sources"])
    sources.pop(missing)
    with pytest.raises(PublicationPackageBlockedError):
        PublicationPackageMaterializer(env["store"]).materialize(
            env["project_id"],
            env["plan"],
            env["finalization"],
            env["review"],
            sources,
            human_review_artifact_id=env["review_ref"].artifact_id,
            final_render_artifact_id=env["evidence"]["final_render_ref"].artifact_id,
        )


def test_materializer_blocks_missing_finalization_and_review(tmp_path):
    env = _materializer_fixture(tmp_path)
    materializer = PublicationPackageMaterializer(env["store"])
    with pytest.raises(PublicationPackageBlockedError):
        materializer.materialize(
            env["project_id"],
            env["plan"],
            None,
            env["review"],
            env["sources"],
            human_review_artifact_id=env["review_ref"].artifact_id,
            final_render_artifact_id=env["evidence"]["final_render_ref"].artifact_id,
        )
    with pytest.raises(PublicationPackageBlockedError):
        materializer.materialize(
            env["project_id"],
            env["plan"],
            env["finalization"],
            None,
            env["sources"],
            human_review_artifact_id=env["review_ref"].artifact_id,
            final_render_artifact_id=env["evidence"]["final_render_ref"].artifact_id,
        )


def test_materializer_blocks_finalization_fail_and_review_6_of_7(tmp_path):
    env = _materializer_fixture(tmp_path)
    materializer = PublicationPackageMaterializer(env["store"])
    failed_finalization = env["finalization"].model_copy(
        update={"status": FinalizationE2EStatus.FINALIZATION_E2E_FAIL}
    )
    with pytest.raises(PublicationPackageBlockedError):
        materializer.materialize(
            env["project_id"],
            env["plan"],
            failed_finalization,
            env["review"],
            env["sources"],
            human_review_artifact_id=env["review_ref"].artifact_id,
            final_render_artifact_id=env["evidence"]["final_render_ref"].artifact_id,
        )
    review_6_of_7 = env["review"].model_copy(update={"copy_passed": False})
    with pytest.raises(PublicationPackageBlockedError):
        materializer.materialize(
            env["project_id"],
            env["plan"],
            env["finalization"],
            review_6_of_7,
            env["sources"],
            human_review_artifact_id=env["review_ref"].artifact_id,
            final_render_artifact_id=env["evidence"]["final_render_ref"].artifact_id,
        )


def test_materializer_blocks_source_hash_mismatch(tmp_path):
    env = _materializer_fixture(tmp_path)
    sources = dict(env["sources"])
    source = sources["master"]
    sources["master"] = PackageSource(
        "master",
        "0" * 64,
        artifact_id=source.artifact_id,
        path=source.path,
    )
    with pytest.raises(PublicationPackageBlockedError):
        PublicationPackageMaterializer(env["store"]).materialize(
            env["project_id"],
            env["plan"],
            env["finalization"],
            env["review"],
            sources,
            human_review_artifact_id=env["review_ref"].artifact_id,
            final_render_artifact_id=env["evidence"]["final_render_ref"].artifact_id,
        )


@pytest.mark.parametrize("unsafe", [Path("../escape.mp4"), Path("/tmp/g006-outside.mp4")])
def test_materializer_blocks_traversal_and_absolute_source(tmp_path, unsafe):
    env = _materializer_fixture(tmp_path)
    sources = dict(env["sources"])
    source = sources["master"]
    sources["master"] = PackageSource(
        "master",
        source.sha256,
        artifact_id=source.artifact_id,
        path=unsafe,
    )
    with pytest.raises(PublicationPackageBlockedError):
        PublicationPackageMaterializer(env["store"]).materialize(
            env["project_id"],
            env["plan"],
            env["finalization"],
            env["review"],
            sources,
            human_review_artifact_id=env["review_ref"].artifact_id,
            final_render_artifact_id=env["evidence"]["final_render_ref"].artifact_id,
        )


def test_materializer_blocks_symlink_escape(tmp_path):
    env = _materializer_fixture(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    package_root = env["store"].root / "publication-packages"
    try:
        package_root.symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("symlink creation is unavailable")
    with pytest.raises(PublicationPackageBlockedError):
        _materialize(env)


def test_materializer_write_failure_is_fail_closed(tmp_path, monkeypatch):
    env = _materializer_fixture(tmp_path)

    def fail_write(source, destination):
        del source, destination
        raise OSError("synthetic write failure")

    monkeypatch.setattr(
        PublicationPackageMaterializer,
        "_write_source",
        staticmethod(fail_write),
    )
    with pytest.raises(OSError):
        _materialize(env)
    parent = env["store"].root / "publication-packages" / env["project_id"]
    assert not list(parent.glob("publication-package-*"))


def test_materializer_reuses_identical_and_blocks_tampered_existing_package(tmp_path):
    env = _materializer_fixture(tmp_path)
    first = _materialize(env)
    second = _materialize(env)
    assert second.reused is True
    target = first.package_dir / "video" / "master_2160x3840.mp4"
    target.write_bytes(b"tampered")
    with pytest.raises(PublicationPackageBlockedError):
        _materialize(env)


def test_materializer_blocks_existing_identity_collision(tmp_path):
    env = _materializer_fixture(tmp_path)
    parent = env["store"].root / "publication-packages" / env["project_id"]
    parent.mkdir(parents=True)
    package_dir = parent / f"publication-package-{env['plan'].publication_package_hash.lower()[:24]}"
    package_dir.write_text("collision", encoding="utf-8")
    with pytest.raises(PublicationPackageBlockedError):
        _materialize(env)


def test_persisted_publication_input_is_review_scoped_and_idempotent(tmp_path):
    store = ArtifactStore(tmp_path / "store")
    project = store.create_project("G006 input")
    review = _review()
    review_ref = store.put_json(
        project.project_id,
        STRUCTURED_HUMAN_REVIEW_ARTIFACT_TYPE,
        review.model_dump(mode="json"),
        producer="g006-test",
        artifact_id="g006-review",
    )
    metadata = PublicationMetadata(title="Jupiter", caption="Caption", hashtags=[])
    first_input, first_thumbnail = persist_publication_package_input(
        store,
        project_id=project.project_id,
        review_ref=review_ref,
        thumbnail_bytes=b"\xff\xd8thumb\xff\xd9",
        thumbnail_filename="thumb.jpg",
        metadata=metadata,
    )
    second_input, second_thumbnail = persist_publication_package_input(
        store,
        project_id=project.project_id,
        review_ref=review_ref,
        thumbnail_bytes=b"\xff\xd8thumb\xff\xd9",
        thumbnail_filename="thumb.jpg",
        metadata=metadata,
    )
    assert first_input.artifact_id == second_input.artifact_id
    assert first_thumbnail.artifact_id == second_thumbnail.artifact_id
    assert review_ref.artifact_id in first_input.input_artifact_ids
    assert review_ref.artifact_id in first_thumbnail.input_artifact_ids


def test_control_center_final_approved_empty_request_runs_productive_publication_stage(tmp_path):
    service = C3ResearchControlCenter(
        store=ArtifactStore(tmp_path / "store"),
        catalog=_FakeCatalog(),
        register_default_media=False,
        register_default_av=False,
        max_workers=2,
    )
    try:
        project, _ = service.create_project("G006 ControlCenter", auto_start=False)
        _advance_to_review(service, project.project_id)
        review = _review()
        service.review(project.project_id, review=review)
        assert service.project(project.project_id).state == ProjectState.FINAL_APPROVED
        review_ref = service.spine._previous_receipt(
            project.project_id,
            SpineStage.PUBLICATION_PACKAGE,
        )
        assert review_ref is not None
        _persist_evidence(service.store, project.project_id, review_ref, review)
        service.prepare_publication_package_input(
            project.project_id,
            thumbnail_bytes=b"\xff\xd8approved-thumbnail\xff\xd9",
            thumbnail_filename="approved.jpg",
            title="Jupiter",
            caption="Caption aprobado",
            hashtags=["#astronomia"],
            youtube_description="Descripción aprobada",
        )

        before = service.project(project.project_id)
        assert before.state == ProjectState.FINAL_APPROVED
        assert before.capability_pending is False
        schedule = service.schedule_publication_package(project.project_id)
        assert schedule.job_id is not None
        persisted_job = service.jobs.get_job(schedule.job_id)
        assert persisted_job.payload["request"] == {}
        record = service.spine.wait(schedule.job_id, timeout=10)
        assert record.status == JobStatus.SUCCEEDED

        after = service.project(project.project_id)
        assert after.state == ProjectState.PUBLICATION_PACKAGE_READY
        assert after.capability_pending is False
        manifest_ref = service.store.get_latest_artifact(
            project.project_id,
            PUBLICATION_MANIFEST_ARTIFACT_TYPE,
        )
        manifest = service.store.read_json(
            project.project_id,
            manifest_ref.artifact_id,
            verify_integrity=True,
        )
        assert manifest["asset_count"] == 8
        assert manifest["manual_publication_only"] is True
        assert manifest["auto_publication"] is False
        assert manifest["authorization_to_publish"] is False
        assert manifest["marks_published"] is False
        assert manifest["uploads_files"] is False
        assert manifest["webhook_calls"] == 0
        assert manifest["package_network_calls"] == 0
        assert len(
            service.store.list_artifacts(
                project.project_id,
                artifact_type=FINALIZATION_EVIDENCE_ARTIFACT_TYPE,
            )
        ) == 1
        assert len(
            service.store.list_artifacts(
                project.project_id,
                artifact_type=PUBLICATION_PLAN_ARTIFACT_TYPE,
            )
        ) == 1
    finally:
        service.shutdown()


def test_control_center_rejects_persisted_publication_input_project_mismatch(tmp_path):
    service = C3ResearchControlCenter(
        store=ArtifactStore(tmp_path / "store"),
        catalog=_FakeCatalog(),
        register_default_media=False,
        register_default_av=False,
        max_workers=2,
    )
    try:
        project, _ = service.create_project("G006 mismatch", auto_start=False)
        _advance_to_review(service, project.project_id)
        review = _review()
        service.review(project.project_id, review=review)
        review_ref = service.spine._previous_receipt(
            project.project_id,
            SpineStage.PUBLICATION_PACKAGE,
        )
        assert review_ref is not None
        _persist_evidence(service.store, project.project_id, review_ref, review)
        input_ref, thumbnail_ref = service.prepare_publication_package_input(
            project.project_id,
            thumbnail_bytes=b"\xff\xd8approved-thumbnail\xff\xd9",
            thumbnail_filename="approved.jpg",
            title="Jupiter",
            caption="Caption aprobado",
        )
        valid = PublicationPackageInputRecord.model_validate(
            service.store.read_json(project.project_id, input_ref.artifact_id)
        )
        forged = valid.model_copy(update={"project_id": "other-project"})
        service.store.put_json(
            project.project_id,
            PUBLICATION_INPUT_ARTIFACT_TYPE,
            forged.model_dump(mode="json"),
            producer="g006-test",
            artifact_id="zzzz-g006-forged-input",
            input_artifact_ids=(review_ref.artifact_id, thumbnail_ref.artifact_id),
            metadata={"human_review_artifact_id": review_ref.artifact_id},
        )
        schedule = service.schedule_publication_package(project.project_id)
        record = service.spine.wait(schedule.job_id, timeout=10)
        assert record.status == JobStatus.SUCCEEDED
        assert service.project(project.project_id).state == ProjectState.BLOCKED
        assert not service.store.list_artifacts(
            project.project_id,
            artifact_type=PUBLICATION_MANIFEST_ARTIFACT_TYPE,
        )
    finally:
        service.shutdown()


def test_product_publication_page_routes_to_productive_manual_package_boundary():
    root = Path(__file__).resolve().parents[2]
    package_init = (root / "webui" / "product" / "__init__.py").read_text(encoding="utf-8")
    publication = (root / "webui" / "product" / "publication.py").read_text(encoding="utf-8")
    service = (
        root
        / "app"
        / "services"
        / "centinela"
        / "research_adapters"
        / "integration.py"
    ).read_text(encoding="utf-8")
    implementation = (
        root / "app" / "services" / "centinela" / "publication_package.py"
    ).read_text(encoding="utf-8")

    compile(package_init, "webui/product/__init__.py", "exec")
    compile(publication, "webui/product/publication.py", "exec")
    compile(service, "app/services/centinela/research_adapters/integration.py", "exec")
    compile(implementation, "app/services/centinela/publication_package.py", "exec")
    assert "pages.publication_page = publication.publication_page" in package_init
    assert "Preparar paquete para publicación manual" in publication
    assert "LISTO PARA PUBLICACIÓN MANUAL" in publication
    assert "schedule_publication_package" in publication
    assert "request={}" in service
    assert "invokes_network=False" in implementation
    assert "invokes_llm=False" in implementation
    assert "invokes_render=False" in implementation
    assert "auto_publication=False" in implementation
    for forbidden in (
        "import requests",
        "import httpx",
        "urllib.request",
        "OAuth",
        "social_api",
        "publish_post(",
        "schedule_post(",
    ):
        assert forbidden not in implementation


def test_generated_metadata_hash_contract_matches_planner_encoding():
    metadata = PublicationMetadata(
        title="Jupiter",
        caption="Caption",
        hashtags=["#astronomia"],
    )
    assert _sha256_bytes(_compact_json_bytes(metadata.model_dump(mode="json")))
