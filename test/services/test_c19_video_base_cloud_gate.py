from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path

import pytest

from app.models.delivery_render import DeliveryRenderStatus
from app.models.material_selection import SelectionStatus
from app.models.video_base import (
    VIDEO_BASE_FPS,
    VIDEO_BASE_HEIGHT,
    VIDEO_BASE_WIDTH,
    VideoBasePlanRequest,
    VideoBaseRenderMode,
)
from app.services.delivery_render import build_delivery_render
from app.services.video_base_planner import (
    VideoBasePlanBlockedError,
    VideoBasePlanner,
)
from app.services import video_base_renderer
from app.services.video_base_renderer import FFmpegSceneRenderer
from app.utils import utils
from test.services.test_delivery_render import fixture as delivery_fixture
from test.services.test_video_base_renderer import FFMPEG, FFPROBE, placeholder_plan
from test.services.test_video_base_planner import (
    GetOnlyCatalog,
    astronomy_plan,
    material_plan,
)


def test_c19_f6_video_base_profile_is_exact_and_audio_free():
    materials = material_plan([SelectionStatus.NO_ADEQUATE_MEDIA] * 5)
    result = VideoBasePlanner(GetOnlyCatalog()).build(
        VideoBasePlanRequest(plan=astronomy_plan(), materials=materials)
    )

    assert (VIDEO_BASE_WIDTH, VIDEO_BASE_HEIGHT, VIDEO_BASE_FPS) == (1080, 1920, 30)
    assert (result.output_width, result.output_height, result.fps) == (1080, 1920, 30)
    assert result.audio_enabled is False
    assert result.requested_codec == "h264_nvenc"
    assert result.fallback_codec == "libx264"


def test_c19_f6_review_partial_may_plan_placeholders_but_clean_base_fails_closed():
    materials = material_plan([SelectionStatus.NO_ADEQUATE_MEDIA] * 5)
    planner = VideoBasePlanner(GetOnlyCatalog())

    review = planner.build(
        VideoBasePlanRequest(
            plan=astronomy_plan(),
            materials=materials,
            render_mode=VideoBaseRenderMode.REVIEW_PARTIAL,
        )
    )
    assert review.placeholder_count == 5
    assert review.clean_base_eligible is False

    with pytest.raises(VideoBasePlanBlockedError):
        planner.build(
            VideoBasePlanRequest(
                plan=astronomy_plan(),
                materials=materials,
                render_mode=VideoBaseRenderMode.CLEAN_BASE,
            )
        )


def test_c19_f30_profiles_are_master_and_social_original_source_rerenders():
    result = build_delivery_render(delivery_fixture(ready=True, nvenc=False))
    profiles = {profile.profile_id: profile for profile in result.profiles}

    master = profiles["MASTER_VERTICAL_2160X3840"]
    social = profiles["SOCIAL_VERTICAL_1080X1920"]
    assert (master.width, master.height, master.fps) == (2160, 3840, 30)
    assert (social.width, social.height, social.fps) == (1080, 1920, 30)
    assert master.source_strategy == "ORIGINAL_SOURCE_RERENDER"
    assert social.source_strategy == "ORIGINAL_SOURCE_RERENDER"
    assert result.upscales_social_to_master is False


def test_c19_f30_plan_hash_is_canonical_deterministic_and_mutation_sensitive():
    first = build_delivery_render(delivery_fixture(ready=False, nvenc=True))
    second = build_delivery_render(delivery_fixture(ready=False, nvenc=True))
    ready = build_delivery_render(delivery_fixture(ready=True, nvenc=True))

    assert re.fullmatch(r"[0-9A-F]{64}", first.delivery_render_hash)
    assert first.delivery_render_hash == second.delivery_render_hash
    assert first.delivery_render_hash != ready.delivery_render_hash


def test_c19_f30_remains_planning_only_even_with_positive_nvenc_hints():
    result = build_delivery_render(delivery_fixture(ready=True, nvenc=True))

    assert result.status == DeliveryRenderStatus.READY_FOR_EXPLICIT_RENDER_APPROVAL
    assert result.planning_only is True
    assert result.project_render_invocations == 0
    assert result.renders_project_video is False
    assert result.auto_publication is False
    assert result.human_render_approval_required is True
    assert all(profile.execution_ready is False for profile in result.profiles)


def test_c19_missing_nvenc_capability_falls_back_to_libx264():
    result = build_delivery_render(delivery_fixture(ready=True, nvenc=False))

    assert result.libx264_listed is True
    assert result.h264_nvenc_listed is False
    assert all(profile.fallback_codec == "libx264" for profile in result.profiles)
    assert all(profile.effective_codec_candidate == "libx264" for profile in result.profiles)


def test_c19_video_base_nvenc_probe_failure_uses_libx264_without_real_ffmpeg(
    monkeypatch,
):
    commands: list[list[str]] = []

    def fake_run(command, *, timeout=None):
        commands.append(list(command))
        return subprocess.CompletedProcess(
            command,
            returncode=1,
            stdout="",
            stderr="NVENC unavailable in cloud fixture",
        )

    video_base_renderer._nvenc_real_probe.cache_clear()
    monkeypatch.setattr(video_base_renderer, "_run", fake_run)
    renderer = video_base_renderer.FFmpegSceneRenderer(
        ffmpeg_binary="ffmpeg-c19-fixture",
        ffprobe_binary="ffprobe-c19-fixture",
    )

    effective, fallback, probe_success, reason = renderer._resolve_codec(
        "h264_nvenc",
        "libx264",
    )

    assert effective == "libx264"
    assert fallback is True
    assert probe_success is False
    assert reason is not None and reason.startswith("NVENC_PROBE_FAILED")
    assert len(commands) == 1
    probe = commands[0]
    assert "color=c=black:s=1080x1920:r=30" in probe
    assert "h264_nvenc" in probe
    assert "-f" in probe and "null" in probe

    video_base_renderer._nvenc_real_probe.cache_clear()


@pytest.mark.skipif(
    not FFMPEG or not FFPROBE,
    reason="FFmpeg/ffprobe required for the C19 manifest integrity gate",
)
def test_c19_video_base_manifest_hashes_the_exact_rendered_assets(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(utils, "task_dir", lambda sub_dir="": str(tmp_path / sub_dir))

    result = FFmpegSceneRenderer(FFMPEG, FFPROBE).render(
        placeholder_plan(requested_codec="libx264"),
        task_id="c19-manifest-integrity",
    )
    manifest = json.loads(Path(result.manifest_path).read_text(encoding="utf-8"))

    assert (manifest["output_width"], manifest["output_height"], manifest["fps"]) == (
        1080,
        1920,
        30,
    )
    assert manifest["final_video_path"] == result.video_path
    assert manifest["final_video_sha256"] == hashlib.sha256(
        Path(result.video_path).read_bytes()
    ).hexdigest()
    assert re.fullmatch(r"[0-9a-f]{64}", manifest["final_video_sha256"])

    assert len(manifest["scenes"]) == result.scene_count
    for scene in manifest["scenes"]:
        segment = Path(scene["segment_path"])
        assert scene["segment_sha256"] == hashlib.sha256(segment.read_bytes()).hexdigest()
        assert re.fullmatch(r"[0-9a-f]{64}", scene["segment_sha256"])
