from __future__ import annotations

import hashlib
import json
import math
import os
import shutil
import subprocess
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from app.models.schema import VideoFitMode
from app.models.video_base import (
    RenderSceneManifest,
    ResourceClass,
    VideoBasePlan,
    VideoBaseRenderAction,
    VideoBaseRenderManifest,
    VideoBaseRenderMode,
    VideoBaseRenderResult,
)
from app.services.resource_governor import governor
from app.utils import utils


class VideoBaseRenderError(RuntimeError):
    pass


def _sha256(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _fraction(value: str | None) -> float:
    if not value:
        return 0.0
    try:
        if "/" in value:
            numerator, denominator = value.split("/", 1)
            denominator_value = float(denominator)
            return float(numerator) / denominator_value if denominator_value else 0.0
        return float(value)
    except (TypeError, ValueError, ZeroDivisionError):
        return 0.0


def _resolve_ffprobe_binary(ffmpeg_binary: str) -> str:
    system = shutil.which("ffprobe")
    if system:
        return system
    ffmpeg_path = Path(ffmpeg_binary)
    if ffmpeg_path.is_absolute():
        sibling = ffmpeg_path.with_name(
            "ffprobe.exe" if os.name == "nt" else "ffprobe"
        )
        if sibling.is_file():
            return str(sibling)
    return "ffprobe"


def _run(command: list[str], *, timeout: float | None = None) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise VideoBaseRenderError(f"failed to execute {command[0]}: {exc}") from exc


def _error_text(result: subprocess.CompletedProcess) -> str:
    return (result.stderr or result.stdout or "").strip()


def _even_ceil(value: float) -> int:
    integer = max(2, int(math.ceil(value)))
    return integer if integer % 2 == 0 else integer + 1


def _crop_origin(resized: int, target: int, focal: float) -> int:
    maximum = max(0, resized - target)
    desired = int(focal * resized - target / 2)
    return max(0, min(desired, maximum))


def _rotation_filters(rotation: int) -> list[str]:
    rotation = int(rotation or 0) % 360
    if rotation == 90:
        return ["transpose=clock"]
    if rotation == 180:
        return ["hflip", "vflip"]
    if rotation == 270:
        return ["transpose=cclock"]
    return []


def _visual_filters(scene, width: int, height: int, fps: int) -> str:
    filters = _rotation_filters(scene.source_rotation_deg)
    source_width = max(1, int(scene.source_width))
    source_height = max(1, int(scene.source_height))

    mode = VideoFitMode(scene.fit_mode)
    if mode == VideoFitMode.fit:
        filters.extend(
            [
                f"scale={width}:{height}:force_original_aspect_ratio=decrease:force_divisible_by=2",
                f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=black",
            ]
        )
    elif mode == VideoFitMode.cover:
        scale = max(width / source_width, height / source_height)
        resized_width = _even_ceil(source_width * scale)
        resized_height = _even_ceil(source_height * scale)
        crop_x = _crop_origin(resized_width, width, scene.focal_x)
        crop_y = _crop_origin(resized_height, height, scene.focal_y)
        filters.extend(
            [
                f"scale={resized_width}:{resized_height}",
                f"crop={width}:{height}:{crop_x}:{crop_y}",
            ]
        )
    else:
        raise VideoBaseRenderError(f"unsupported fit mode: {mode}")

    filters.extend([f"fps={fps}", "setsar=1", "format=yuv420p"])
    return ",".join(filters)


def _codec_args(codec: str) -> list[str]:
    if codec == "h264_nvenc":
        return ["-c:v", "h264_nvenc", "-preset", "p5", "-cq", "19", "-b:v", "0"]
    if codec == "libx264":
        return ["-c:v", "libx264", "-preset", "medium", "-crf", "18"]
    raise VideoBaseRenderError(f"unsupported codec: {codec}")


@lru_cache(maxsize=8)
def _nvenc_real_probe(ffmpeg_binary: str) -> tuple[bool, str]:
    # Probe the exact Video Base V0.1 output geometry.
    #
    # Very small synthetic frames such as 64x64 can be rejected by NVENC
    # on otherwise fully supported GPUs. That creates a false negative and
    # incorrectly forces libx264 even when the real 1080x1920 path works.
    command = [
        ffmpeg_binary,
        "-hide_banner",
        "-loglevel",
        "error",
        "-f",
        "lavfi",
        "-i",
        "color=c=black:s=1080x1920:r=30",
        "-frames:v",
        "2",
        "-an",
        *_codec_args("h264_nvenc"),
        "-pix_fmt",
        "yuv420p",
        "-f",
        "null",
        "-",
    ]
    result = _run(command, timeout=20)
    return result.returncode == 0, _error_text(result)


def _ffmpeg_version(ffmpeg_binary: str) -> str:
    result = _run([ffmpeg_binary, "-version"], timeout=10)
    if result.returncode != 0:
        return "unknown"
    return (result.stdout or "").splitlines()[0].strip() or "unknown"


def _probe(path: Path, ffprobe_binary: str) -> dict:
    result = _run(
        [
            ffprobe_binary,
            "-v",
            "error",
            "-show_streams",
            "-show_format",
            "-of",
            "json",
            str(path),
        ],
        timeout=30,
    )
    if result.returncode != 0:
        raise VideoBaseRenderError(
            f"ffprobe failed for {path}: {_error_text(result)}"
        )
    try:
        return json.loads(result.stdout or "{}")
    except json.JSONDecodeError as exc:
        raise VideoBaseRenderError(f"invalid ffprobe JSON for {path}") from exc


def _video_probe_summary(data: dict) -> dict:
    streams = data.get("streams") or []
    videos = [stream for stream in streams if stream.get("codec_type") == "video"]
    audios = [stream for stream in streams if stream.get("codec_type") == "audio"]
    if not videos:
        raise VideoBaseRenderError("rendered file has no video stream")
    video = videos[0]
    try:
        duration = float(
            video.get("duration") or (data.get("format") or {}).get("duration") or 0.0
        )
    except (TypeError, ValueError):
        duration = 0.0
    return {
        "width": int(video.get("width") or 0),
        "height": int(video.get("height") or 0),
        "fps": _fraction(video.get("avg_frame_rate") or video.get("r_frame_rate")),
        "codec": str(video.get("codec_name") or ""),
        "pix_fmt": str(video.get("pix_fmt") or ""),
        "duration": max(0.0, duration),
        "audio_streams": len(audios),
    }


def _placeholder_png(path: Path, scene) -> None:
    image = Image.new("RGB", (1080, 1920), (22, 24, 28))
    draw = ImageDraw.Draw(image)
    try:
        font_big = ImageFont.truetype("arial.ttf", 64)
        font_small = ImageFont.truetype("arial.ttf", 38)
    except OSError:
        font_big = ImageFont.load_default()
        font_small = ImageFont.load_default()

    title = "PENDIENTE DE MATERIAL"
    subtitle = f"ESCENA {scene.scene_number}"
    reason = scene.placeholder_reason.value if scene.placeholder_reason else "UNRESOLVED"

    def centered(text, y, font):
        box = draw.textbbox((0, 0), text, font=font)
        x = (1080 - (box[2] - box[0])) // 2
        draw.text((x, y), text, fill=(235, 235, 235), font=font)

    centered(title, 760, font_big)
    centered(subtitle, 860, font_small)
    centered(reason, 930, font_small)
    image.save(path, format="PNG")


def _format_concat_path(path: Path) -> str:
    value = str(path.resolve()).replace("\\", "/")
    return value.replace("'", "'\\''")


class FFmpegSceneRenderer:
    def __init__(self, ffmpeg_binary: str | None = None, ffprobe_binary: str | None = None):
        self.ffmpeg_binary = ffmpeg_binary or utils.get_ffmpeg_binary()
        self.ffprobe_binary = ffprobe_binary or _resolve_ffprobe_binary(
            self.ffmpeg_binary
        )

    def _resolve_codec(
        self,
        requested: str,
        fallback: str,
    ) -> tuple[str, bool, bool | None, str | None]:
        if requested == "libx264":
            return "libx264", False, None, None

        if requested == "h264_nvenc":
            success, error = _nvenc_real_probe(self.ffmpeg_binary)

            if success:
                return "h264_nvenc", False, True, None

            reason = "NVENC_PROBE_FAILED"

            if error:
                reason += ": " + error

            return fallback, True, False, reason

        raise VideoBaseRenderError(
            f"unsupported requested codec: {requested}"
        )

    def _render_scene(self, scene, output_path: Path, codec: str, temp_dir: Path) -> None:
        if scene.render_action == VideoBaseRenderAction.PLACEHOLDER:
            placeholder_path = temp_dir / f"placeholder-{scene.scene_number:03d}.png"
            _placeholder_png(placeholder_path, scene)
            source_path = placeholder_path
            filters = (
                f"scale=1080:1920,setsar=1,fps=30,format=yuv420p"
            )
            command = [
                self.ffmpeg_binary,
                "-y",
                "-hide_banner",
                "-loglevel",
                "error",
                "-loop",
                "1",
                "-framerate",
                "30",
                "-i",
                str(source_path),
                "-t",
                f"{scene.duration_seconds:.6f}",
                "-vf",
                filters,
                "-an",
                *_codec_args(codec),
                "-pix_fmt",
                "yuv420p",
                "-movflags",
                "+faststart",
                str(output_path),
            ]
        elif scene.render_action == VideoBaseRenderAction.IMAGE:
            source_path = Path(scene.source_path)
            filters = _visual_filters(scene, 1080, 1920, 30)
            command = [
                self.ffmpeg_binary,
                "-y",
                "-hide_banner",
                "-loglevel",
                "error",
                "-loop",
                "1",
                "-framerate",
                "30",
                "-i",
                str(source_path),
                "-t",
                f"{scene.duration_seconds:.6f}",
                "-vf",
                filters,
                "-an",
                *_codec_args(codec),
                "-pix_fmt",
                "yuv420p",
                "-movflags",
                "+faststart",
                str(output_path),
            ]
        elif scene.render_action == VideoBaseRenderAction.VIDEO:
            source_path = Path(scene.source_path)
            filters = _visual_filters(scene, 1080, 1920, 30)
            command = [
                self.ffmpeg_binary,
                "-y",
                "-hide_banner",
                "-loglevel",
                "error",
                "-ss",
                f"{scene.source_start_s:.6f}",
                "-noautorotate",
                "-i",
                str(source_path),
                "-t",
                f"{scene.duration_seconds:.6f}",
                "-vf",
                filters,
                "-an",
                *_codec_args(codec),
                "-pix_fmt",
                "yuv420p",
                "-movflags",
                "+faststart",
                str(output_path),
            ]
        else:
            raise VideoBaseRenderError(
                f"unsupported render action: {scene.render_action}"
            )

        result = _run(command)
        if result.returncode != 0:
            raise VideoBaseRenderError(
                f"scene {scene.scene_number} encode failed with {codec}: {_error_text(result)}"
            )
        if not output_path.is_file() or output_path.stat().st_size <= 0:
            raise VideoBaseRenderError(
                f"scene {scene.scene_number} produced an empty segment"
            )

    def _render_segments(self, plan: VideoBasePlan, segments_dir: Path, temp_dir: Path, codec: str):
        segment_paths = []
        for scene in plan.scenes:
            segment_path = segments_dir / f"segment-{scene.scene_number:03d}.mp4"
            self._render_scene(scene, segment_path, codec, temp_dir)
            segment_paths.append(segment_path)
        return segment_paths

    def _concat(
        self,
        segments: list[Path],
        output_path: Path,
        output_dir: Path,
        codec: str,
        *,
        force_reencode: bool = False,
    ) -> str:
        concat_path = output_dir / "ffmpeg-concat-list.txt"
        concat_path.write_text(
            "".join(f"file '{_format_concat_path(path)}'\n" for path in segments),
            encoding="utf-8",
        )
        try:
            if not force_reencode:
                copy_result = _run(
                    [
                        self.ffmpeg_binary,
                        "-y",
                        "-hide_banner",
                        "-loglevel",
                        "error",
                        "-f",
                        "concat",
                        "-safe",
                        "0",
                        "-i",
                        str(concat_path),
                        "-c",
                        "copy",
                        "-movflags",
                        "+faststart",
                        str(output_path),
                    ]
                )
                if (
                    copy_result.returncode == 0
                    and output_path.is_file()
                    and output_path.stat().st_size > 0
                ):
                    return "copy"
                output_path.unlink(missing_ok=True)

            reencode_result = _run(
                [
                    self.ffmpeg_binary,
                    "-y",
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-f",
                    "concat",
                    "-safe",
                    "0",
                    "-i",
                    str(concat_path),
                    "-an",
                    *_codec_args(codec),
                    "-pix_fmt",
                    "yuv420p",
                    "-r",
                    "30",
                    "-movflags",
                    "+faststart",
                    str(output_path),
                ]
            )
            if reencode_result.returncode != 0:
                raise VideoBaseRenderError(
                    "concat failed: " + _error_text(reencode_result)
                )
            return "reencode"
        finally:
            concat_path.unlink(missing_ok=True)

    def _validate_final(self, plan: VideoBasePlan, output_path: Path) -> dict:
        summary = _video_probe_summary(_probe(output_path, self.ffprobe_binary))
        if summary["width"] != plan.output_width or summary["height"] != plan.output_height:
            raise VideoBaseRenderError(
                f"final resolution mismatch: {summary['width']}x{summary['height']}"
            )
        if abs(summary["fps"] - plan.fps) > 0.01:
            raise VideoBaseRenderError(f"final fps mismatch: {summary['fps']}")
        if summary["pix_fmt"] != "yuv420p":
            raise VideoBaseRenderError(
                f"final pixel format mismatch: {summary['pix_fmt']}"
            )
        if summary["audio_streams"] != 0:
            raise VideoBaseRenderError("Video Base V0.1 must not contain audio")

        expected = sum(scene.duration_seconds for scene in plan.scenes)
        tolerance = max(0.25, plan.scene_count / plan.fps + 0.1)
        if abs(summary["duration"] - expected) > tolerance:
            raise VideoBaseRenderError(
                f"final duration mismatch: expected={expected:.3f} actual={summary['duration']:.3f}"
            )
        return summary

    def render(
        self,
        plan: VideoBasePlan,
        *,
        task_id: str | None = None,
        keep_segments: bool = True,
    ) -> VideoBaseRenderResult:
        if plan.render_mode == VideoBaseRenderMode.CLEAN_BASE and not plan.clean_base_eligible:
            raise VideoBaseRenderError(
                "CLEAN_BASE blocked before FFmpeg: plan is not clean_base_eligible"
            )

        task_id = task_id or ("video-base-" + utils.get_uuid(remove_hyphen=True))
        output_dir = Path(utils.task_dir(task_id))
        segments_dir = output_dir / "segments"
        temp_dir = output_dir / "temp"
        segments_dir.mkdir(parents=True, exist_ok=True)
        temp_dir.mkdir(parents=True, exist_ok=True)
        final_path = output_dir / "video-base.mp4"
        manifest_path = output_dir / "render-manifest.json"

        with governor.acquire("video-base-render", ResourceClass.MEDIUM):
            (
                effective_codec,
                codec_fallback,
                nvenc_probe_success,
                codec_fallback_reason,
            ) = self._resolve_codec(
                plan.requested_codec,
                plan.fallback_codec,
            )

            try:
                segments = self._render_segments(
                    plan,
                    segments_dir,
                    temp_dir,
                    effective_codec,
                )

            except VideoBaseRenderError as exc:
                if effective_codec == plan.fallback_codec:
                    raise

                shutil.rmtree(
                    segments_dir,
                    ignore_errors=True,
                )

                segments_dir.mkdir(
                    parents=True,
                    exist_ok=True,
                )

                effective_codec = plan.fallback_codec
                codec_fallback = True
                codec_fallback_reason = (
                    "NVENC_RENDER_FAILED: " + str(exc)
                )

                segments = self._render_segments(
                    plan,
                    segments_dir,
                    temp_dir,
                    effective_codec,
                )

            concat_mode = self._concat(
                segments, final_path, output_dir, effective_codec
            )
            try:
                final_summary = self._validate_final(plan, final_path)
            except VideoBaseRenderError:
                if concat_mode != "copy":
                    raise
                # Some H.264 segments can be individually valid but expose timestamp
                # or parameter-set incompatibilities under stream-copy concatenation.
                # Re-encode once deterministically, then validate again.
                final_path.unlink(missing_ok=True)
                concat_mode = self._concat(
                    segments,
                    final_path,
                    output_dir,
                    effective_codec,
                    force_reencode=True,
                )
                final_summary = self._validate_final(plan, final_path)

            scene_manifests = []
            for scene, segment in zip(plan.scenes, segments, strict=True):
                segment_summary = _video_probe_summary(
                    _probe(segment, self.ffprobe_binary)
                )
                scene_manifests.append(
                    RenderSceneManifest(
                        scene_number=scene.scene_number,
                        material_selection_status=scene.material_selection_status,
                        render_action=scene.render_action,
                        selected_media_id=scene.selected_media_id,
                        provider=scene.provider,
                        rights_status=scene.rights_status,
                        source_path=scene.source_path,
                        source_fingerprint=scene.source_fingerprint,
                        source_duration_seconds=scene.source_duration_seconds,
                        source_start_s=scene.source_start_s,
                        requested_duration_seconds=scene.duration_seconds,
                        rendered_duration_seconds=segment_summary["duration"],
                        fit_mode=scene.fit_mode,
                        focal_x=scene.focal_x,
                        focal_y=scene.focal_y,
                        source_rotation_deg=scene.source_rotation_deg,
                        placeholder=scene.placeholder,
                        placeholder_reason=scene.placeholder_reason,
                        segment_path=str(segment),
                        segment_sha256=_sha256(segment),
                    )
                )

            manifest = VideoBaseRenderManifest(
                task_id=task_id,
                render_mode=plan.render_mode,
                output_width=plan.output_width,
                output_height=plan.output_height,
                fps=plan.fps,
                requested_codec=plan.requested_codec,
                effective_codec=effective_codec,
                codec_fallback=codec_fallback,
                codec_fallback_reason=codec_fallback_reason,
                ffmpeg_binary=self.ffmpeg_binary,
                nvenc_probe_success=nvenc_probe_success,
                concat_mode=concat_mode,
                ffmpeg_version=_ffmpeg_version(self.ffmpeg_binary),
                scene_count=plan.scene_count,
                placeholder_count=plan.placeholder_count,
                expected_duration_seconds=sum(
                    scene.duration_seconds for scene in plan.scenes
                ),
                rendered_duration_seconds=final_summary["duration"],
                final_video_path=str(final_path),
                final_video_sha256=_sha256(final_path),
                final_video_codec=final_summary["codec"],
                final_pixel_format=final_summary["pix_fmt"],
                final_audio_stream_count=final_summary["audio_streams"],
                scenes=scene_manifests,
                generated_at_utc=datetime.now(timezone.utc),
            )

            temp_manifest = manifest_path.with_suffix(".json.tmp")
            temp_manifest.write_text(
                json.dumps(
                    manifest.model_dump(mode="json"),
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            os.replace(temp_manifest, manifest_path)

            shutil.rmtree(temp_dir, ignore_errors=True)
            if not keep_segments:
                shutil.rmtree(segments_dir, ignore_errors=True)

        return VideoBaseRenderResult(
            task_id=task_id,
            output_dir=str(output_dir),
            video_path=str(final_path),
            manifest_path=str(manifest_path),
            requested_codec=plan.requested_codec,
            effective_codec=effective_codec,
            codec_fallback=codec_fallback,
            concat_mode=concat_mode,
            duration_seconds=final_summary["duration"],
            scene_count=plan.scene_count,
            placeholder_count=plan.placeholder_count,
        )
