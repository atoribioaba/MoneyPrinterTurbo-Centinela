from __future__ import annotations

import hashlib
import json
import math
import os
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from pydantic import ValidationError

from app.models.astronomy_director import AstronomyVideoPlan
from app.models.material_selection import MaterialSelectionPlan
from app.models.schema import VideoFitMode
from app.models.video_base import (
    VideoBasePlan,
    VideoBasePlanRequest,
    VideoBaseRenderAction,
    VideoBaseRenderMode,
)
from app.services.astromedia import AstroMediaCatalog
from app.services.centinela.media_resolver import MediaResolutionReport
from app.services.centinela.orchestration import ResourceClass
from app.services.centinela.production_spine import (
    StageArtifact,
    StageBinding,
    StageResult,
)
from app.services.video_base_planner import (
    VIDEO_DURATION_TOLERANCE_SECONDS,
    VideoBasePlanBlockedError,
    VideoBasePlanError,
    VideoBasePlanner,
)
from app.services.video_base_renderer import (
    FFmpegSceneRenderer,
    VideoBaseRenderError,
)
from app.utils import utils

from .master_renderer import MasterRenderError, render_master
from .models import (
    R7_AV_RUNTIME_VERSION,
    AudioBundle,
    VideoBaseManifest,
)


class VideoExecutionError(RuntimeError):
    pass


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def _latest_ref(context: Any, artifact_type: str):
    refs = context.store.list_artifacts(
        context.project_id,
        artifact_type=artifact_type,
    )
    return refs[-1] if refs else None


def _crop_loss(width: int, height: int) -> float:
    if width <= 0 or height <= 0:
        return 1.0
    source = width / height
    target = 9 / 16
    if source >= target:
        return max(0.0, 1.0 - target / source)
    return max(0.0, 1.0 - source / target)


def _adapt_plan_to_real_audio(
    plan: VideoBasePlan,
    audio: AudioBundle,
    media: MediaResolutionReport,
) -> tuple[VideoBasePlan, dict[str, int]]:
    timing_by_scene = {
        item.scene_number: item for item in audio.scenes
    }
    media_by_scene = {
        item.scene_number: item for item in media.scenes
    }

    scenes = []
    smartfocal = 0
    fit_count = 0
    cover_count = 0

    for scene in plan.scenes:
        timing = timing_by_scene.get(scene.scene_number)
        evidence = media_by_scene.get(scene.scene_number)
        if timing is None or evidence is None:
            raise VideoExecutionError(
                f"R7 timing/media evidence missing for scene {scene.scene_number}"
            )
        if scene.placeholder:
            raise VideoExecutionError(
                f"R7 CLEAN_BASE refuses placeholder scene {scene.scene_number}"
            )

        duration = float(timing.duration_s)
        if (
            scene.render_action == VideoBaseRenderAction.VIDEO
            and scene.source_duration_seconds
            + VIDEO_DURATION_TOLERANCE_SECONDS
            < duration
        ):
            raise VideoExecutionError(
                f"scene {scene.scene_number} source is too short after real "
                f"TTS timing: source={scene.source_duration_seconds:.3f}s "
                f"audio={duration:.3f}s"
            )

        focal = evidence.focal
        loss = _crop_loss(scene.source_width, scene.source_height)
        use_cover = loss <= 0.15
        focal_x = 0.5
        focal_y = 0.5

        if focal.applicable and focal.confidence >= 0.35:
            use_cover = True
            focal_x = focal.focal_x
            focal_y = focal.focal_y
            smartfocal += 1

        mode = VideoFitMode.cover if use_cover else VideoFitMode.fit
        if mode == VideoFitMode.cover:
            cover_count += 1
        else:
            fit_count += 1

        scenes.append(
            scene.model_copy(
                update={
                    "duration_seconds": duration,
                    "fit_mode": mode,
                    "focal_x": focal_x,
                    "focal_y": focal_y,
                }
            )
        )

    adapted = plan.model_copy(update={"scenes": scenes})
    return adapted, {
        "smartfocal": smartfocal,
        "fit": fit_count,
        "cover": cover_count,
    }


def _ffmpeg() -> Path:
    value = Path(utils.get_ffmpeg_binary())
    if value.is_file():
        return value
    resolved = shutil.which(str(value)) or shutil.which("ffmpeg")
    if not resolved:
        raise VideoExecutionError("FFmpeg is not available")
    return Path(resolved)


def _ffprobe(ffmpeg: Path) -> Path:
    sibling = ffmpeg.with_name(
        "ffprobe.exe" if os.name == "nt" else "ffprobe"
    )
    if sibling.is_file():
        return sibling
    resolved = shutil.which("ffprobe")
    if not resolved:
        raise VideoExecutionError("ffprobe is not available")
    return Path(resolved)


def _probe_video(path: Path) -> dict[str, Any]:
    ffmpeg = _ffmpeg()
    result = subprocess.run(
        [
            str(_ffprobe(ffmpeg)),
            "-v",
            "error",
            "-show_streams",
            "-show_format",
            "-of",
            "json",
            str(path),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
        check=False,
    )
    if result.returncode != 0:
        raise VideoExecutionError(
            (result.stderr or result.stdout or "")[:1800]
        )
    payload = json.loads(result.stdout or "{}")
    videos = [
        item
        for item in payload.get("streams", [])
        if item.get("codec_type") == "video"
    ]
    audios = [
        item
        for item in payload.get("streams", [])
        if item.get("codec_type") == "audio"
    ]
    if len(videos) != 1:
        raise VideoExecutionError("preview must contain one video stream")
    video = videos[0]
    duration = float(
        video.get("duration")
        or (payload.get("format") or {}).get("duration")
        or 0.0
    )
    return {
        "width": int(video.get("width") or 0),
        "height": int(video.get("height") or 0),
        "duration": duration,
        "audio_streams": len(audios),
    }


def _materialize_audio(
    context: Any,
    audio: AudioBundle,
    output_dir: Path,
) -> Path:
    output = output_dir / "voice-master.wav"
    data = context.store.read_bytes(
        context.project_id,
        audio.voice_master_artifact_id,
        verify_integrity=True,
    )
    output.write_bytes(data)
    if _sha256(output) != audio.voice_master_sha256:
        raise VideoExecutionError(
            "materialized master voice SHA does not match AudioBundle"
        )
    return output


def _mux_preview(
    social_video: Path,
    master_audio: Path,
    output: Path,
    expected_audio_duration: float,
) -> dict[str, Any]:
    ffmpeg = _ffmpeg()
    result = subprocess.run(
        [
            str(ffmpeg),
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(social_video),
            "-i",
            str(master_audio),
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-ar",
            "48000",
            "-shortest",
            "-movflags",
            "+faststart",
            str(output),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=300,
        check=False,
    )
    if result.returncode != 0:
        raise VideoExecutionError(
            "review preview mux failed: "
            + (result.stderr or result.stdout or "")[:1800]
        )
    summary = _probe_video(output)
    if (
        summary["width"] != 1080
        or summary["height"] != 1920
        or summary["audio_streams"] != 1
        or not math.isfinite(summary["duration"])
        or abs(summary["duration"] - expected_audio_duration) > 0.75
    ):
        raise VideoExecutionError(
            "review preview validation failed: "
            + json.dumps(summary, ensure_ascii=False)
        )
    return summary


class VideoBaseStageAdapter:
    def __init__(
        self,
        catalog: AstroMediaCatalog | None = None,
    ) -> None:
        self.catalog = catalog or AstroMediaCatalog()

    def __call__(
        self,
        context: Any,
        payload: dict[str, Any],
    ) -> StageResult:
        del payload

        scene_ref = _latest_ref(context, "scene_plan")
        material_ref = _latest_ref(context, "material_selection")
        media_ref = _latest_ref(context, "media_resolution")
        audio_ref = _latest_ref(context, "audio_bundle")
        if any(
            item is None
            for item in (
                scene_ref,
                material_ref,
                media_ref,
                audio_ref,
            )
        ):
            return StageResult.needs_input(
                "scene_plan, media resolution and audio bundle are required for VIDEO_BASE"
            )

        assert scene_ref is not None
        assert material_ref is not None
        assert media_ref is not None
        assert audio_ref is not None

        try:
            scene_plan = AstronomyVideoPlan.model_validate(
                context.store.read_json(
                    context.project_id,
                    scene_ref.artifact_id,
                )
            )
            materials = MaterialSelectionPlan.model_validate(
                context.store.read_json(
                    context.project_id,
                    material_ref.artifact_id,
                )
            )
            media = MediaResolutionReport.model_validate(
                context.store.read_json(
                    context.project_id,
                    media_ref.artifact_id,
                )
            )
            audio = AudioBundle.model_validate(
                context.store.read_json(
                    context.project_id,
                    audio_ref.artifact_id,
                )
            )
        except (ValidationError, TypeError, ValueError) as exc:
            return StageResult.blocked(
                "R7 VIDEO_BASE input artifact validation failed",
                details={
                    "error_type": type(exc).__name__,
                    "error": str(exc)[:1600],
                },
            )

        if (
            scene_plan.context_hash != audio.source_plan_context_hash
            or materials.source_plan_context_hash
            != scene_plan.context_hash
            or media.source_plan_context_hash
            != scene_plan.context_hash
        ):
            return StageResult.blocked(
                "R7 VIDEO_BASE scientific/media/audio lineage mismatch"
            )
        if materials.unresolved_count != 0 or media.unresolved_count != 0:
            return StageResult.needs_input(
                "R7 VIDEO_BASE refuses unresolved scenes",
                details={
                    "material_unresolved": materials.unresolved_count,
                    "media_unresolved": media.unresolved_count,
                    "irrelevant_broll_substituted": False,
                },
            )

        try:
            context.report_progress(18, "VIDEO_BASE: validating selected media")
            planner = VideoBasePlanner(catalog=self.catalog)
            plan = planner.build(
                VideoBasePlanRequest(
                    plan=scene_plan,
                    materials=materials,
                    render_mode=VideoBaseRenderMode.CLEAN_BASE,
                    default_fit_mode=VideoFitMode.fit,
                    requested_codec="h264_nvenc",
                )
            )
            plan, framing = _adapt_plan_to_real_audio(
                plan,
                audio,
                media,
            )

            context.report_progress(38, "VIDEO_BASE: social 1080×1920")
            social = FFmpegSceneRenderer().render(
                plan,
                task_id=context.job_context.job_id + "-social",
                keep_segments=False,
            )
            social_path = Path(social.video_path)
            social_manifest = json.loads(
                Path(social.manifest_path).read_text(encoding="utf-8")
            )
            if int(social_manifest.get("final_audio_stream_count", -1)) != 0:
                raise VideoExecutionError(
                    "social clean base unexpectedly contains audio"
                )

            context.check_cancelled()
            context.report_progress(58, "VIDEO_BASE: master 2160×3840 desde originales")
            master = render_master(
                plan,
                task_id=context.job_context.job_id + "-master",
            )
            master_path = Path(master.video_path)

            context.check_cancelled()
            context.report_progress(78, "VIDEO_BASE: preview audiovisual")
            preview_dir = (
                Path(utils.task_dir(context.job_context.job_id))
                / "r7-preview"
            )
            preview_dir.mkdir(parents=True, exist_ok=True)
            audio_path = _materialize_audio(
                context,
                audio,
                preview_dir,
            )
            preview_path = preview_dir / "review-preview.mp4"
            preview_summary = _mux_preview(
                social_path,
                audio_path,
                preview_path,
                audio.duration_seconds,
            )
        except (
            VideoBasePlanBlockedError,
            VideoBasePlanError,
            VideoBaseRenderError,
            MasterRenderError,
            VideoExecutionError,
        ) as exc:
            return StageResult.needs_input(
                "R7 VIDEO_BASE cannot produce a clean reviewable timeline",
                details={
                    "error_type": type(exc).__name__,
                    "error": str(exc)[:1800],
                    "irrelevant_broll_substituted": False,
                    "master_derived_from_social": False,
                    "wangp_triggered": False,
                },
            )
        except Exception as exc:
            return StageResult.blocked(
                "R7 VIDEO_BASE execution failed",
                details={
                    "error_type": type(exc).__name__,
                    "error": str(exc)[:1800],
                },
            )

        social_id = "r7-video-social-" + uuid4().hex
        master_id = "r7-video-master-" + uuid4().hex
        preview_id = "r7-review-preview-" + uuid4().hex

        manifest = VideoBaseManifest(
            subject=scene_plan.subject,
            source_plan_context_hash=scene_plan.context_hash,
            source_audio_bundle_artifact_id=audio_ref.artifact_id,
            source_material_selection_artifact_id=material_ref.artifact_id,
            source_media_resolution_artifact_id=media_ref.artifact_id,
            social_video_artifact_id=social_id,
            master_video_artifact_id=master_id,
            review_preview_artifact_id=preview_id,
            subtitle_artifact_id=audio.subtitle_artifact_id,
            social_codec=social.effective_codec,
            master_codec=master.codec,
            social_codec_fallback=social.codec_fallback,
            master_codec_fallback=master.codec_fallback,
            social_duration_seconds=social.duration_seconds,
            master_duration_seconds=master.duration_seconds,
            review_preview_duration_seconds=preview_summary["duration"],
            social_sha256=_sha256(social_path),
            master_sha256=_sha256(master_path),
            review_preview_sha256=_sha256(preview_path),
            smartfocal_scene_count=framing["smartfocal"],
            fit_scene_count=framing["fit"],
            cover_scene_count=framing["cover"],
            scene_count=len(plan.scenes),
            social_render_manifest=social_manifest,
            master_render_manifest=master.manifest,
            generated_at_utc=datetime.now(timezone.utc),
        )

        common_inputs = (
            scene_ref.artifact_id,
            material_ref.artifact_id,
            media_ref.artifact_id,
            audio_ref.artifact_id,
        )
        return StageResult.complete(
            StageArtifact(
                artifact_type="video_base_social",
                source_path=str(social_path),
                suffix=".mp4",
                artifact_id=social_id,
                input_artifact_ids=common_inputs,
                provenance={
                    "av_runtime_version": R7_AV_RUNTIME_VERSION,
                    "profile": "SOCIAL_VERTICAL_1080X1920",
                    "source_mode": "DIRECT_FROM_SELECTED_SOURCE_MEDIA",
                },
                metadata={
                    "width": 1080,
                    "height": 1920,
                    "fps": 30,
                    "audio_streams": 0,
                },
            ),
            StageArtifact(
                artifact_type="video_base_master",
                source_path=str(master_path),
                suffix=".mp4",
                artifact_id=master_id,
                input_artifact_ids=common_inputs,
                provenance={
                    "av_runtime_version": R7_AV_RUNTIME_VERSION,
                    "profile": "MASTER_VERTICAL_2160X3840",
                    "source_mode": "DIRECT_FROM_SELECTED_SOURCE_MEDIA",
                    "derived_from_social": False,
                },
                metadata={
                    "width": 2160,
                    "height": 3840,
                    "fps": 30,
                    "audio_streams": 0,
                },
            ),
            StageArtifact(
                artifact_type="review_preview",
                source_path=str(preview_path),
                suffix=".mp4",
                artifact_id=preview_id,
                input_artifact_ids=(
                    social_id,
                    audio.voice_master_artifact_id,
                    *common_inputs,
                ),
                provenance={
                    "av_runtime_version": R7_AV_RUNTIME_VERSION,
                    "purpose": "HUMAN_REVIEW_PREVIEW",
                },
                metadata={
                    "width": 1080,
                    "height": 1920,
                    "audio_streams": 1,
                    "subtitle_burned_in": False,
                },
            ),
            StageArtifact(
                artifact_type="video_base_manifest",
                payload=manifest.model_dump(mode="json"),
                input_artifact_ids=(
                    social_id,
                    master_id,
                    preview_id,
                    *common_inputs,
                ),
                provenance={
                    "av_runtime_version": R7_AV_RUNTIME_VERSION,
                    "master_direct_from_selected_sources": True,
                    "master_derived_from_social": False,
                    "smartfocal_post_selection": True,
                },
                metadata={
                    "scene_count": manifest.scene_count,
                    "social_codec": manifest.social_codec,
                    "master_codec": manifest.master_codec,
                    "auto_publication": False,
                },
            ),
            message="R7 produced clean social/master video bases and review preview",
            details={
                "social": "1080x1920",
                "master": "2160x3840",
                "master_derived_from_social": False,
                "review_preview_audio": True,
                "subtitle_sidecar": True,
                "auto_publication": False,
            },
        )


def build_video_base_stage_binding(
    catalog: AstroMediaCatalog | None = None,
) -> StageBinding:
    return StageBinding(
        adapter_id="r7_video_base_executor_v01",
        handler=VideoBaseStageAdapter(catalog),
        resource_class=ResourceClass.HEAVY,
        producer_version=R7_AV_RUNTIME_VERSION,
        invokes_network=False,
        invokes_llm=False,
        invokes_render=True,
        auto_publication=False,
    )
