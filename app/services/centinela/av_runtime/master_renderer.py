from __future__ import annotations

import hashlib
import json
import math
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.models.schema import VideoFitMode
from app.models.video_base import (
    VideoBasePlan,
    VideoBaseRenderAction,
)
from app.utils import utils


MASTER_WIDTH = 2160
MASTER_HEIGHT = 3840
MASTER_FPS = 30


class MasterRenderError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class MasterRenderResult:
    video_path: str
    width: int
    height: int
    fps: float
    duration_seconds: float
    codec: str
    codec_fallback: bool
    nvenc_probe_success: bool
    sha256: str
    manifest: dict[str, Any]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def _run(
    command: list[str],
    *,
    timeout: int = 1800,
) -> subprocess.CompletedProcess[str]:
    try:
        result = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise MasterRenderError(
            f"failed to execute {command[0]}: {exc}"
        ) from exc
    if result.returncode != 0:
        message = (result.stderr or result.stdout or "").strip()
        raise MasterRenderError(message[:2400])
    return result


def _ffmpeg() -> Path:
    value = Path(utils.get_ffmpeg_binary())
    if value.is_file():
        return value
    resolved = shutil.which(str(value)) or shutil.which("ffmpeg")
    if not resolved:
        raise MasterRenderError("FFmpeg is not available")
    return Path(resolved)


def _ffprobe(ffmpeg: Path) -> Path:
    sibling = ffmpeg.with_name(
        "ffprobe.exe" if os.name == "nt" else "ffprobe"
    )
    if sibling.is_file():
        return sibling
    resolved = shutil.which("ffprobe")
    if not resolved:
        raise MasterRenderError("ffprobe is not available")
    return Path(resolved)


def _fraction(value: str | None) -> float:
    if not value:
        return 0.0
    if "/" in value:
        left, right = value.split("/", 1)
        denominator = float(right)
        return float(left) / denominator if denominator else 0.0
    return float(value)


def _probe(path: Path, ffprobe: Path) -> dict[str, Any]:
    payload = json.loads(
        _run(
            [
                str(ffprobe),
                "-v",
                "error",
                "-show_streams",
                "-show_format",
                "-of",
                "json",
                str(path),
            ],
            timeout=60,
        ).stdout
        or "{}"
    )
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
        raise MasterRenderError(
            f"expected one video stream, found {len(videos)}"
        )
    video = videos[0]
    duration = float(
        video.get("duration")
        or (payload.get("format") or {}).get("duration")
        or 0.0
    )
    return {
        "width": int(video.get("width") or 0),
        "height": int(video.get("height") or 0),
        "fps": _fraction(
            video.get("avg_frame_rate")
            or video.get("r_frame_rate")
        ),
        "codec": str(video.get("codec_name") or ""),
        "pix_fmt": str(video.get("pix_fmt") or ""),
        "duration": duration,
        "audio_streams": len(audios),
    }


def _even_ceil(value: float) -> int:
    integer = max(2, int(math.ceil(value)))
    return integer if integer % 2 == 0 else integer + 1


def _crop_origin(resized: int, target: int, focal: float) -> int:
    maximum = max(0, resized - target)
    desired = int(focal * resized - target / 2)
    return max(0, min(desired, maximum))


def _filters(scene) -> str:
    filters: list[str] = []
    rotation = int(scene.source_rotation_deg or 0) % 360
    if rotation == 90:
        filters.append("transpose=clock")
    elif rotation == 180:
        filters.extend(["hflip", "vflip"])
    elif rotation == 270:
        filters.append("transpose=cclock")

    source_width = max(1, int(scene.source_width))
    source_height = max(1, int(scene.source_height))
    mode = VideoFitMode(scene.fit_mode)

    if mode == VideoFitMode.fit:
        filters.extend(
            [
                (
                    f"scale={MASTER_WIDTH}:{MASTER_HEIGHT}:"
                    "force_original_aspect_ratio=decrease:"
                    "force_divisible_by=2"
                ),
                (
                    f"pad={MASTER_WIDTH}:{MASTER_HEIGHT}:"
                    "(ow-iw)/2:(oh-ih)/2:color=black"
                ),
            ]
        )
    elif mode == VideoFitMode.cover:
        scale = max(
            MASTER_WIDTH / source_width,
            MASTER_HEIGHT / source_height,
        )
        resized_width = _even_ceil(source_width * scale)
        resized_height = _even_ceil(source_height * scale)
        crop_x = _crop_origin(
            resized_width,
            MASTER_WIDTH,
            scene.focal_x,
        )
        crop_y = _crop_origin(
            resized_height,
            MASTER_HEIGHT,
            scene.focal_y,
        )
        filters.extend(
            [
                f"scale={resized_width}:{resized_height}",
                (
                    f"crop={MASTER_WIDTH}:{MASTER_HEIGHT}:"
                    f"{crop_x}:{crop_y}"
                ),
            ]
        )
    else:
        raise MasterRenderError(f"unsupported fit mode: {mode}")

    filters.extend(
        [
            f"fps={MASTER_FPS}",
            "setsar=1",
            "format=yuv420p",
        ]
    )
    return ",".join(filters)


def _codec_args(codec: str) -> list[str]:
    if codec == "h264_nvenc":
        return [
            "-c:v",
            "h264_nvenc",
            "-preset",
            "p5",
            "-cq",
            "18",
            "-b:v",
            "0",
        ]
    if codec == "libx264":
        return [
            "-c:v",
            "libx264",
            "-preset",
            "fast",
            "-crf",
            "18",
        ]
    raise MasterRenderError(f"unsupported codec: {codec}")


def _nvenc_probe(ffmpeg: Path) -> bool:
    result = subprocess.run(
        [
            str(ffmpeg),
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            (
                f"color=c=black:s={MASTER_WIDTH}x{MASTER_HEIGHT}:"
                f"r={MASTER_FPS}"
            ),
            "-frames:v",
            "2",
            "-an",
            *_codec_args("h264_nvenc"),
            "-pix_fmt",
            "yuv420p",
            "-f",
            "null",
            "-",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=60,
        check=False,
    )
    return result.returncode == 0


def _render_segment(
    ffmpeg: Path,
    scene,
    output: Path,
    codec: str,
) -> None:
    if scene.render_action == VideoBaseRenderAction.PLACEHOLDER:
        raise MasterRenderError(
            "CLEAN_BASE master refuses placeholder scenes"
        )
    if not scene.source_path:
        raise MasterRenderError("scene source_path is missing")

    command = [
        str(ffmpeg),
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
    ]
    if scene.render_action == VideoBaseRenderAction.IMAGE:
        command.extend(
            [
                "-loop",
                "1",
                "-framerate",
                str(MASTER_FPS),
                "-i",
                str(scene.source_path),
            ]
        )
    elif scene.render_action == VideoBaseRenderAction.VIDEO:
        command.extend(
            [
                "-ss",
                f"{scene.source_start_s:.6f}",
                "-noautorotate",
                "-i",
                str(scene.source_path),
            ]
        )
    else:
        raise MasterRenderError(
            f"unsupported render action: {scene.render_action}"
        )

    command.extend(
        [
            "-t",
            f"{scene.duration_seconds:.6f}",
            "-vf",
            _filters(scene),
            "-an",
            *_codec_args(codec),
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            str(output),
        ]
    )
    _run(command)
    if not output.is_file() or output.stat().st_size <= 0:
        raise MasterRenderError("master segment is empty")


def _concat(
    ffmpeg: Path,
    segments: list[Path],
    output: Path,
    work: Path,
    codec: str,
) -> str:
    concat_file = work / "concat.txt"
    concat_file.write_text(
        "".join(
            "file '"
            + str(path.resolve()).replace("\\", "/").replace("'", "'\\''")
            + "'\n"
            for path in segments
        ),
        encoding="utf-8",
        newline="\n",
    )
    copy = subprocess.run(
        [
            str(ffmpeg),
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat_file),
            "-c",
            "copy",
            "-movflags",
            "+faststart",
            str(output),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=600,
        check=False,
    )
    if copy.returncode == 0 and output.is_file() and output.stat().st_size > 0:
        return "copy"

    output.unlink(missing_ok=True)
    _run(
        [
            str(ffmpeg),
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat_file),
            "-an",
            *_codec_args(codec),
            "-pix_fmt",
            "yuv420p",
            "-r",
            str(MASTER_FPS),
            "-movflags",
            "+faststart",
            str(output),
        ]
    )
    return "reencode"


def render_master(
    plan: VideoBasePlan,
    *,
    task_id: str,
) -> MasterRenderResult:
    if not plan.clean_base_eligible:
        raise MasterRenderError("master requires CLEAN_BASE eligible plan")

    ffmpeg = _ffmpeg()
    ffprobe = _ffprobe(ffmpeg)
    output_dir = Path(utils.task_dir(task_id)) / "r7-master"
    segments_dir = output_dir / "segments"
    output_dir.mkdir(parents=True, exist_ok=True)
    segments_dir.mkdir(parents=True, exist_ok=True)
    output = output_dir / "master-2160x3840.mp4"

    nvenc_ok = _nvenc_probe(ffmpeg)
    codec = "h264_nvenc" if nvenc_ok else "libx264"
    fallback = not nvenc_ok

    def render_all(selected_codec: str) -> list[Path]:
        shutil.rmtree(segments_dir, ignore_errors=True)
        segments_dir.mkdir(parents=True, exist_ok=True)
        result: list[Path] = []
        for scene in plan.scenes:
            segment = (
                segments_dir
                / f"segment-{scene.scene_number:03d}.mp4"
            )
            _render_segment(
                ffmpeg,
                scene,
                segment,
                selected_codec,
            )
            result.append(segment)
        return result

    try:
        segments = render_all(codec)
    except MasterRenderError:
        if codec == "libx264":
            raise
        codec = "libx264"
        fallback = True
        segments = render_all(codec)

    concat_mode = _concat(
        ffmpeg,
        segments,
        output,
        output_dir,
        codec,
    )
    summary = _probe(output, ffprobe)
    expected = sum(scene.duration_seconds for scene in plan.scenes)
    tolerance = max(0.35, len(plan.scenes) / MASTER_FPS + 0.15)

    if (
        summary["width"] != MASTER_WIDTH
        or summary["height"] != MASTER_HEIGHT
        or abs(summary["fps"] - MASTER_FPS) > 0.02
        or summary["pix_fmt"] != "yuv420p"
        or summary["audio_streams"] != 0
        or abs(summary["duration"] - expected) > tolerance
    ):
        raise MasterRenderError(
            "master validation failed: "
            + json.dumps(summary, ensure_ascii=False)
        )

    sha = _sha256(output)
    manifest = {
        "profile_id": "MASTER_VERTICAL_2160X3840",
        "width": MASTER_WIDTH,
        "height": MASTER_HEIGHT,
        "fps": MASTER_FPS,
        "requested_codec": "h264_nvenc",
        "effective_codec": codec,
        "codec_fallback": fallback,
        "nvenc_probe_success": nvenc_ok,
        "concat_mode": concat_mode,
        "duration_seconds": summary["duration"],
        "sha256": sha,
        "audio_streams": summary["audio_streams"],
        "source_mode": "DIRECT_FROM_SELECTED_SOURCE_MEDIA",
        "derived_from_social": False,
    }
    (output_dir / "master-render-manifest.json").write_text(
        json.dumps(
            manifest,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )
    shutil.rmtree(segments_dir, ignore_errors=True)

    return MasterRenderResult(
        video_path=str(output),
        width=MASTER_WIDTH,
        height=MASTER_HEIGHT,
        fps=summary["fps"],
        duration_seconds=summary["duration"],
        codec=codec,
        codec_fallback=fallback,
        nvenc_probe_success=nvenc_ok,
        sha256=sha,
        manifest=manifest,
    )
