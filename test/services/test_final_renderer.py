from __future__ import annotations

import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.models.astromedia import Provider, Rights
from app.models.finalization_e2e import (
    FinalizationE2EStatus,
    HumanFinalReviewDecision,
    HumanFinalReviewRecord,
)
from app.models.video_base_e2e import VideoBaseE2EPlan, VideoBaseE2EStatus
from app.services.centinela.av_runtime import (
    AudioBundle,
    AudioSceneTiming,
    FinalRenderBlockedError,
    FinalRenderError,
    FinalRenderService,
    SubtitleCue,
    VideoBaseManifest,
    build_finalization_request,
)
from app.services.centinela.media_resolver import (
    FocalEvidence,
    MediaResolutionReport,
    ResolverGuardrails,
    SceneMediaEvidence,
    SemanticEvidence,
)
from app.services.centinela.orchestration import ProjectState, ProjectStateMachine
from app.services.centinela.production_spine import ProductionSpine
from app.services.centinela.project_foundation import ArtifactStore
from app.services.finalization_e2e import build_finalization_e2e

NOW = datetime(2026, 9, 2, 20, 0, tzinfo=timezone.utc)
REVIEW_FIELDS = (
    "science_passed",
    "visual_passed",
    "audio_passed",
    "subtitles_passed",
    "rights_passed",
    "thumbnail_passed",
    "copy_passed",
)


def _review(**overrides) -> HumanFinalReviewRecord:
    gates = {field: True for field in REVIEW_FIELDS}
    gates.update(overrides)
    return HumanFinalReviewRecord(
        decision=HumanFinalReviewDecision.APPROVE,
        reviewer_ref="g002-reviewer",
        rationale="G-002 structured final-render approval evidence.",
        decided_at_utc=NOW,
        **gates,
    )


def _advance_to_review(machine: ProjectStateMachine, project_id: str) -> None:
    for state in (
        ProjectState.RESEARCH_READY,
        ProjectState.SCRIPT_READY,
        ProjectState.SCENES_READY,
        ProjectState.MEDIA_READY,
        ProjectState.AUDIO_READY,
        ProjectState.VIDEO_BASE_READY,
        ProjectState.READY_FOR_HUMAN_REVIEW,
    ):
        machine.transition(
            project_id,
            state,
            reason=f"G002 fixture advance to {state.value}",
            actor="g002-test",
        )


def _fake_probe(path: Path) -> dict:
    name = path.name
    master = "master" in name
    final = name.startswith("final-")
    return {
        "width": 2160 if master else 1080,
        "height": 3840 if master else 1920,
        "fps": 30.0,
        "codec": "h264",
        "pix_fmt": "yuv420p",
        "duration": 2.0,
        "video_streams": 1,
        "audio_streams": 1 if final else 0,
        "subtitle_streams": 0,
    }


def _ffmpeg_runner(calls: list[list[str]]):
    def run(command: list[str]) -> subprocess.CompletedProcess[str]:
        calls.append(list(command))
        first_i = command.index("-i")
        second_i = command.index("-i", first_i + 1)
        base = Path(command[first_i + 1])
        audio = Path(command[second_i + 1])
        output = Path(command[-1])
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(b"G002-FINAL\n" + base.read_bytes() + b"\n" + audio.read_bytes())
        return subprocess.CompletedProcess(command, 0, "", "")

    return run


def _video_base_e2e_pass() -> VideoBaseE2EPlan:
    return VideoBaseE2EPlan(
        source_production_orchestrator_hash="orchestrator-g002",
        status=VideoBaseE2EStatus.VIDEO_BASE_E2E_PASS,
        real_artifact_present=True,
        check_count=0,
        passed_count=0,
        failed_count=0,
        checks=[],
        video_base_e2e_hash="video-base-e2e-g002",
        generated_at_utc=NOW,
    )


def _fixture(tmp_path: Path, *, rights_ready: bool = True):
    store = ArtifactStore(tmp_path / "store")
    manifest = store.create_project("G-002 final renderer")
    project_id = manifest.project_id
    machine = ProjectStateMachine(store)
    _advance_to_review(machine, project_id)

    material_ref = store.put_json(
        project_id,
        "material_selection",
        {"fixture": "G002"},
        producer="g002-test",
        artifact_id="g002-material-selection",
    )

    media = MediaResolutionReport(
        subject="Jupiter",
        source_plan_context_hash="context-g002",
        selector_version="selector-g002",
        catalog_item_count=1,
        catalog_provider_counts={"OWN_MEDIA": 1},
        catalog_refreshed=False,
        scene_count=1,
        selected_count=1,
        unresolved_count=0,
        rights_review_count=0 if rights_ready else 1,
        review_required=not rights_ready,
        publication_ready=rights_ready,
        scenes=[
            SceneMediaEvidence(
                scene_number=1,
                scene_key="context-g002:scene:1",
                query="Jupiter",
                candidate_count=0,
                candidates=[],
                semantic=SemanticEvidence(
                    requested=False,
                    analyzed=False,
                    method="g002_fixture",
                ),
                selection_status="SELECTED",
                selected_media_id="owned-jupiter-001",
                selected_provider=Provider.OWN_MEDIA,
                selected_rights_status=(
                    Rights.CONFIRMED_OWNED if rights_ready else Rights.UNVERIFIED
                ),
                selected_publication_eligible=rights_ready,
                focal=FocalEvidence(
                    applicable=False,
                    method="g002_fixture",
                ),
            )
        ],
        guardrails=ResolverGuardrails(),
        generated_at_utc=NOW,
    )
    media_ref = store.put_json(
        project_id,
        "media_resolution",
        media.model_dump(mode="json"),
        producer="g002-test",
        artifact_id="g002-media-resolution",
        input_artifact_ids=(material_ref.artifact_id,),
    )

    voice_raw_ref = store.put_bytes(
        project_id,
        "voice_raw",
        b"G002 approved raw voice",
        producer="g002-test",
        artifact_id="g002-voice-raw",
        suffix=".wav",
    )
    voice_master_ref = store.put_bytes(
        project_id,
        "voice_master",
        b"G002 approved mastered voice",
        producer="g002-test",
        artifact_id="g002-voice-master",
        suffix=".wav",
        input_artifact_ids=(voice_raw_ref.artifact_id,),
    )
    subtitle_ref = store.put_bytes(
        project_id,
        "subtitle_srt",
        b"1\n00:00:00,000 --> 00:00:01,800\nJupiter aprobado.\n",
        producer="g002-test",
        artifact_id="g002-subtitles",
        suffix=".srt",
        input_artifact_ids=(material_ref.artifact_id,),
    )

    audio = AudioBundle(
        subject="Jupiter",
        source_plan_context_hash="context-g002",
        source_final_script_hash="final-script-g002",
        source_material_selector_version="selector-g002",
        qwen_runtime_python="python",
        qwen_adapter="qwen-adapter",
        qwen_model_path="qwen-model",
        whisper_model="small",
        whisper_device="cpu",
        whisper_compute_type="int8",
        alignment_ratio=1.0,
        voice_raw_artifact_id=voice_raw_ref.artifact_id,
        voice_master_artifact_id=voice_master_ref.artifact_id,
        subtitle_artifact_id=subtitle_ref.artifact_id,
        voice_raw_sha256=voice_raw_ref.sha256,
        voice_master_sha256=voice_master_ref.sha256,
        subtitle_sha256=subtitle_ref.sha256,
        duration_seconds=2.0,
        channels=1,
        verified_i_lufs=-16.0,
        verified_tp_dbtp=-1.0,
        scene_count=1,
        scenes=[
            AudioSceneTiming(
                scene_number=1,
                start_s=0.0,
                end_s=2.0,
                duration_s=2.0,
                token_start=0,
                token_end=1,
            )
        ],
        subtitle_cue_count=1,
        subtitles=[
            SubtitleCue(
                index=1,
                scene_number=1,
                start_s=0.0,
                end_s=1.8,
                text="Jupiter aprobado.",
            )
        ],
        generated_at_utc=NOW,
    )
    audio_ref = store.put_json(
        project_id,
        "audio_bundle",
        audio.model_dump(mode="json"),
        producer="g002-test",
        artifact_id="g002-audio-bundle",
        input_artifact_ids=(
            voice_raw_ref.artifact_id,
            voice_master_ref.artifact_id,
            subtitle_ref.artifact_id,
            material_ref.artifact_id,
        ),
    )

    master_ref = store.put_bytes(
        project_id,
        "video_base_master",
        b"G002 approved clean master video base",
        producer="g002-test",
        artifact_id="g002-vb-master",
        suffix=".mp4",
        input_artifact_ids=(audio_ref.artifact_id, media_ref.artifact_id),
    )
    social_ref = store.put_bytes(
        project_id,
        "video_base_social",
        b"G002 approved clean social video base",
        producer="g002-test",
        artifact_id="g002-vb-social",
        suffix=".mp4",
        input_artifact_ids=(audio_ref.artifact_id, media_ref.artifact_id),
    )
    preview_ref = store.put_bytes(
        project_id,
        "review_preview",
        b"G002 review preview",
        producer="g002-test",
        artifact_id="g002-review-preview",
        suffix=".mp4",
        input_artifact_ids=(social_ref.artifact_id, audio_ref.artifact_id),
    )

    video_manifest = VideoBaseManifest(
        subject="Jupiter",
        source_plan_context_hash="context-g002",
        source_audio_bundle_artifact_id=audio_ref.artifact_id,
        source_material_selection_artifact_id=material_ref.artifact_id,
        source_media_resolution_artifact_id=media_ref.artifact_id,
        social_video_artifact_id=social_ref.artifact_id,
        master_video_artifact_id=master_ref.artifact_id,
        review_preview_artifact_id=preview_ref.artifact_id,
        subtitle_artifact_id=subtitle_ref.artifact_id,
        social_codec="h264",
        master_codec="h264",
        social_codec_fallback=False,
        master_codec_fallback=False,
        social_duration_seconds=2.0,
        master_duration_seconds=2.0,
        review_preview_duration_seconds=2.0,
        social_sha256=social_ref.sha256,
        master_sha256=master_ref.sha256,
        review_preview_sha256=preview_ref.sha256,
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
        producer="g002-test",
        artifact_id="g002-video-base-manifest",
        input_artifact_ids=(
            master_ref.artifact_id,
            social_ref.artifact_id,
            preview_ref.artifact_id,
            audio_ref.artifact_id,
            media_ref.artifact_id,
            material_ref.artifact_id,
        ),
    )

    return {
        "store": store,
        "machine": machine,
        "project_id": project_id,
        "media_ref": media_ref,
        "audio_ref": audio_ref,
        "voice_master_ref": voice_master_ref,
        "subtitle_ref": subtitle_ref,
        "master_ref": master_ref,
        "social_ref": social_ref,
        "video_manifest_ref": video_manifest_ref,
    }


def _approve(env) -> HumanFinalReviewRecord:
    record = _review()
    spine = ProductionSpine(env["store"], state_machine=env["machine"])
    try:
        spine.record_human_review(env["project_id"], review=record)
    finally:
        spine.shutdown(wait=True)
    assert env["machine"].current_state(env["project_id"]) == ProjectState.FINAL_APPROVED
    return record


def _force_final_approved(
    env,
    *,
    persisted_review: HumanFinalReviewRecord | None = None,
) -> None:
    metadata = {"fixture": "compromised-state-precondition"}
    if persisted_review is not None:
        ref = env["store"].put_json(
            env["project_id"],
            "human_final_review_record",
            persisted_review.model_dump(mode="json"),
            producer="g002-test",
            artifact_id="g002-forged-review",
        )
        metadata = {
            "human_review": True,
            "structured_review": True,
            "decision_artifact_id": ref.artifact_id,
            "decision": persisted_review.decision.value,
            "approved": True,
        }
    env["machine"].transition(
        env["project_id"],
        ProjectState.FINAL_APPROVED,
        reason="G002 adversarial state fixture",
        actor="g002-test",
        metadata=metadata,
        expected_state=ProjectState.READY_FOR_HUMAN_REVIEW,
    )


def _service(env, calls: list[list[str]] | None = None):
    calls = calls if calls is not None else []
    return FinalRenderService(
        env["store"],
        state_machine=env["machine"],
        ffmpeg_binary="ffmpeg",
        ffprobe_binary="ffprobe",
        command_runner=_ffmpeg_runner(calls),
        probe_runner=_fake_probe,
    )


def test_final_approved_renders_master_social_and_finalization_passes(tmp_path):
    env = _fixture(tmp_path)
    _approve(env)
    calls: list[list[str]] = []
    service = _service(env, calls)

    result = service.render(env["project_id"], work_dir=tmp_path / "work")

    assert result.post_review_content_mutation is False
    assert result.auto_publication is False
    assert result.master.width == 2160
    assert result.master.height == 3840
    assert result.master.fps == pytest.approx(30.0)
    assert result.master.audio_stream_count >= 1
    assert result.master.video_processing == "STREAM_COPY"
    assert result.master.source_video_base_artifact_id == env["master_ref"].artifact_id
    assert result.social.width == 1080
    assert result.social.height == 1920
    assert result.social.fps == pytest.approx(30.0)
    assert result.social.audio_stream_count >= 1
    assert result.social.video_processing == "STREAM_COPY"
    assert result.social.source_video_base_artifact_id == env["social_ref"].artifact_id
    assert result.master.subtitle_mode == "SIDECAR_PRESERVED"
    assert result.social.subtitle_mode == "SIDECAR_PRESERVED"
    assert result.subtitle_artifact_id == env["subtitle_ref"].artifact_id
    assert result.rights_provenance["upstream_publication_ready"] is True
    assert len(result.master.sha256) == 64
    assert len(result.social.sha256) == 64
    assert all("copy" in command for command in calls)
    assert all("scale=" not in " ".join(command) for command in calls)

    finalization = build_finalization_e2e(
        build_finalization_request(_video_base_e2e_pass(), result)
    )
    assert finalization.status == FinalizationE2EStatus.FINALIZATION_E2E_PASS
    assert finalization.verification_only is True
    assert finalization.renders_video is False
    assert finalization.modifies_media is False
    assert finalization.auto_publication is False
    assert finalization.authorization_to_publish is False


@pytest.mark.parametrize("case", ["pre_review", "six_of_seven", "missing_record"])
def test_final_render_preconditions_fail_closed(tmp_path, case):
    env = _fixture(tmp_path)
    if case == "six_of_seven":
        _force_final_approved(env, persisted_review=_review(science_passed=False))
    elif case == "missing_record":
        _force_final_approved(env)

    with pytest.raises(FinalRenderBlockedError):
        _service(env).render(env["project_id"], work_dir=tmp_path / "work")


def test_invalid_rights_fail_closed(tmp_path):
    env = _fixture(tmp_path, rights_ready=False)
    _approve(env)
    with pytest.raises(FinalRenderBlockedError, match="rights"):
        _service(env).render(env["project_id"], work_dir=tmp_path / "work")


@pytest.mark.parametrize("artifact_key", ["voice_master_ref", "subtitle_ref"])
def test_missing_approved_audio_or_subtitle_fails_closed(tmp_path, artifact_key):
    env = _fixture(tmp_path)
    _approve(env)
    ref = env[artifact_key]
    env["store"].resolve_artifact_path(env["project_id"], ref.artifact_id).unlink()

    with pytest.raises(FinalRenderBlockedError):
        _service(env).render(env["project_id"], work_dir=tmp_path / "work")


def test_tampered_video_base_hash_fails_closed(tmp_path):
    env = _fixture(tmp_path)
    _approve(env)
    path = env["store"].resolve_artifact_path(
        env["project_id"], env["master_ref"].artifact_id
    )
    path.write_bytes(b"tampered after approval")

    with pytest.raises(FinalRenderBlockedError, match="SHA256"):
        _service(env).render(env["project_id"], work_dir=tmp_path / "work")


def test_ffmpeg_failure_fails_closed(tmp_path):
    env = _fixture(tmp_path)
    _approve(env)

    def failed(command: list[str]) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(command, 1, "", "synthetic ffmpeg failure")

    service = FinalRenderService(
        env["store"],
        state_machine=env["machine"],
        ffmpeg_binary="ffmpeg",
        ffprobe_binary="ffprobe",
        command_runner=failed,
        probe_runner=_fake_probe,
    )
    with pytest.raises(FinalRenderError, match="FFmpeg"):
        service.render(env["project_id"], work_dir=tmp_path / "work")


def test_ffprobe_failure_fails_closed(tmp_path):
    env = _fixture(tmp_path)
    _approve(env)

    def failed_probe(path: Path) -> dict:
        raise FinalRenderError(f"synthetic ffprobe failure: {path.name}")

    service = FinalRenderService(
        env["store"],
        state_machine=env["machine"],
        ffmpeg_binary="ffmpeg",
        ffprobe_binary="ffprobe",
        command_runner=_ffmpeg_runner([]),
        probe_runner=failed_probe,
    )
    with pytest.raises(FinalRenderError, match="ffprobe"):
        service.render(env["project_id"], work_dir=tmp_path / "work")


def test_identical_inputs_reuse_durable_final_render(tmp_path):
    env = _fixture(tmp_path)
    _approve(env)
    calls: list[list[str]] = []
    service = _service(env, calls)

    first = service.render(env["project_id"], work_dir=tmp_path / "first")
    call_count = len(calls)
    second = service.render(env["project_id"], work_dir=tmp_path / "second")

    assert first.reused is False
    assert second.reused is True
    assert second.input_fingerprint == first.input_fingerprint
    assert second.master.artifact_id == first.master.artifact_id
    assert second.social.artifact_id == first.social.artifact_id
    assert second.master.sha256 == first.master.sha256
    assert second.social.sha256 == first.social.sha256
    assert len(calls) == call_count
    assert len(
        env["store"].list_artifacts(
            env["project_id"], artifact_type="final_master_video"
        )
    ) == 1
    assert len(
        env["store"].list_artifacts(
            env["project_id"], artifact_type="final_social_video"
        )
    ) == 1
    assert len(
        env["store"].list_artifacts(
            env["project_id"], artifact_type="final_render_manifest"
        )
    ) == 1
