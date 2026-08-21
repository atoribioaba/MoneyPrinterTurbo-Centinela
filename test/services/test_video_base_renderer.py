from __future__ import annotations

import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pytest
from PIL import Image

from app.models.astromedia import MediaType, Provider, Rights
from app.models.material_selection import SelectionStatus
from app.models.schema import VideoFitMode
from app.models.video_base import (
    VideoBasePlan,
    VideoBaseRenderAction,
    VideoBaseRenderMode,
    VideoBaseScenePlan,
)
import app.services.video_base_renderer as renderer_module
from app.services.video_base_renderer import FFmpegSceneRenderer
from app.utils import utils


FFMPEG = shutil.which("ffmpeg")
FFPROBE = shutil.which("ffprobe")
pytestmark = pytest.mark.skipif(
    not FFMPEG or not FFPROBE,
    reason="FFmpeg/ffprobe required for F6 E2E tests",
)


def placeholder_plan(duration=1.0, requested_codec="libx264"):
    scene = VideoBaseScenePlan(
        scene_number=1,
        scene_key="ctx:scene:1",
        duration_seconds=duration,
        visual_requirement="Moon",
        narration="Narration",
        material_selection_status=SelectionStatus.NO_ADEQUATE_MEDIA,
        render_action=VideoBaseRenderAction.PLACEHOLDER,
        fit_mode=VideoFitMode.fit,
        renderable=True,
        clean_base_eligible=False,
        placeholder=True,
        placeholder_reason="NO_ADEQUATE_MEDIA",
    )
    return VideoBasePlan(
        subject="test",
        source_plan_context_hash="ctx",
        source_selector_version="test",
        render_mode=VideoBaseRenderMode.REVIEW_PARTIAL,
        requested_codec=requested_codec,
        scene_count=1,
        unresolved_count=1,
        placeholder_count=1,
        clean_base_eligible=False,
        source_materials_publication_ready=False,
        scenes=[scene],
        generated_at_utc=datetime.now(timezone.utc),
    )


def test_placeholder_e2e_is_1080x1920_30fps_no_audio(tmp_path, monkeypatch):
    monkeypatch.setattr(utils, "task_dir", lambda sub_dir="": str(tmp_path / sub_dir))
    result = FFmpegSceneRenderer(FFMPEG, FFPROBE).render(
        placeholder_plan(), task_id="f6-placeholder-test"
    )
    manifest = json.loads(Path(result.manifest_path).read_text(encoding="utf-8"))
    assert result.placeholder_count == 1
    assert manifest["output_width"] == 1080
    assert manifest["output_height"] == 1920
    assert manifest["fps"] == 30
    assert manifest["final_audio_stream_count"] == 0
    assert manifest["final_pixel_format"] == "yuv420p"
    assert Path(result.video_path).stat().st_size > 0


def test_image_cover_e2e(tmp_path, monkeypatch):
    monkeypatch.setattr(utils, "task_dir", lambda sub_dir="": str(tmp_path / sub_dir))
    image_path = tmp_path / "source.png"
    Image.new("RGB", (1920, 1080), (10, 20, 30)).save(image_path)
    scene = VideoBaseScenePlan(
        scene_number=1,
        scene_key="ctx:scene:1",
        duration_seconds=1.0,
        visual_requirement="Landscape",
        narration="Narration",
        material_selection_status=SelectionStatus.SELECTED,
        render_action=VideoBaseRenderAction.IMAGE,
        selected_media_id="media-1",
        source_path=str(image_path),
        media_type=MediaType.IMAGE,
        provider=Provider.OWN_MEDIA,
        rights_status=Rights.CONFIRMED_OWNED,
        publication_eligible=True,
        source_width=1920,
        source_height=1080,
        source_rotation_deg=0,
        source_duration_seconds=0.0,
        source_fingerprint="test",
        fit_mode=VideoFitMode.cover,
        focal_x=0.5,
        focal_y=0.5,
        renderable=True,
        clean_base_eligible=True,
        placeholder=False,
    )
    plan = VideoBasePlan(
        subject="test",
        source_plan_context_hash="ctx",
        source_selector_version="test",
        render_mode=VideoBaseRenderMode.CLEAN_BASE,
        requested_codec="libx264",
        scene_count=1,
        unresolved_count=0,
        placeholder_count=0,
        clean_base_eligible=True,
        source_materials_publication_ready=True,
        scenes=[scene],
        generated_at_utc=datetime.now(timezone.utc),
    )
    result = FFmpegSceneRenderer(FFMPEG, FFPROBE).render(
        plan, task_id="f6-image-test"
    )
    assert Path(result.video_path).is_file()
    assert result.duration_seconds == pytest.approx(1.0, abs=0.25)



def test_nvenc_probe_uses_real_output_geometry(monkeypatch):
    captured = {}

    def fake_run(command, *, timeout=None):
        captured["command"] = command

        return subprocess.CompletedProcess(
            command,
            0,
            "",
            "",
        )

    renderer_module._nvenc_real_probe.cache_clear()

    monkeypatch.setattr(
        renderer_module,
        "_run",
        fake_run,
    )

    try:
        success, error = renderer_module._nvenc_real_probe(
            "ffmpeg"
        )

    finally:
        renderer_module._nvenc_real_probe.cache_clear()

    assert success is True
    assert error == ""

    assert (
        "color=c=black:s=1080x1920:r=30"
        in captured["command"]
    )

    assert "h264_nvenc" in captured["command"]
    assert "p5" in captured["command"]
    assert "yuv420p" in captured["command"]


def test_nvenc_probe_failure_is_recorded_in_manifest(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(
        utils,
        "task_dir",
        lambda sub_dir="": str(tmp_path / sub_dir),
    )

    monkeypatch.setattr(
        renderer_module,
        "_nvenc_real_probe",
        lambda ffmpeg_binary: (
            False,
            "synthetic probe failure",
        ),
    )

    result = FFmpegSceneRenderer(
        FFMPEG,
        FFPROBE,
    ).render(
        placeholder_plan(
            requested_codec="h264_nvenc"
        ),
        task_id="f6-nvenc-fallback-trace-test",
    )

    manifest = json.loads(
        Path(result.manifest_path).read_text(
            encoding="utf-8"
        )
    )

    assert manifest["requested_codec"] == "h264_nvenc"
    assert manifest["effective_codec"] == "libx264"
    assert manifest["codec_fallback"] is True
    assert manifest["nvenc_probe_success"] is False
    assert manifest["ffmpeg_binary"] == FFMPEG

    assert manifest[
        "codec_fallback_reason"
    ].startswith(
        "NVENC_PROBE_FAILED:"
    )

    assert (
        "synthetic probe failure"
        in manifest["codec_fallback_reason"]
    )
