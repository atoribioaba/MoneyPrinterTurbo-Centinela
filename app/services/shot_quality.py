from __future__ import annotations

import hashlib
import json
import math
import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.models.schema import VideoFitMode
from app.models.shot_quality import (
    SHOT_QUALITY_VERSION,
    RepresentativeFrameMetrics,
    ShotQualityBand,
    ShotQualityComponents,
    ShotQualityPlan,
    ShotQualityRequest,
    ShotQualitySceneScore,
    ShotQualityStatus,
    ShotQualityStructuralChecks,
)


class ShotQualityError(RuntimeError):
    pass


class FrameAnalysisError(ShotQualityError):
    pass


_FLOAT_RE = r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?"


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _hash_json(value: Any) -> str:
    return hashlib.sha256(
        _canonical_json(value).encode("utf-8")
    ).hexdigest().upper()


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _effective_dimensions(scene) -> tuple[int, int]:
    width = int(scene.source_width)
    height = int(scene.source_height)
    rotation = int(scene.source_rotation_deg) % 360

    if rotation in {90, 270}:
        width, height = height, width

    return width, height


def _geometry_components(scene, output_width: int, output_height: int):
    source_width, source_height = _effective_dimensions(scene)
    if source_width <= 0 or source_height <= 0:
        raise FrameAnalysisError("source dimensions are not positive")

    if output_width <= 0 or output_height <= 0:
        raise FrameAnalysisError("output dimensions are not positive")

    fit_mode = scene.fit_mode

    if fit_mode == VideoFitMode.fit:
        scale = min(
            output_width / source_width,
            output_height / source_height,
        )
        projected_width = source_width * scale
        projected_height = source_height * scale
        framing_efficiency = (
            projected_width * projected_height
        ) / (output_width * output_height)

    elif fit_mode == VideoFitMode.cover:
        scale = max(
            output_width / source_width,
            output_height / source_height,
        )
        scaled_width = source_width * scale
        scaled_height = source_height * scale
        framing_efficiency = (
            output_width * output_height
        ) / (scaled_width * scaled_height)

    else:
        raise FrameAnalysisError(f"unsupported fit mode: {fit_mode}")

    upsample_factor = max(1.0, scale)
    resolution_adequacy = 1.0 / upsample_factor

    return (
        round(_clamp01(resolution_adequacy), 3),
        round(_clamp01(framing_efficiency), 3),
        float(scale),
    )


class FFmpegFrameDiagnostics:
    """Analyze exactly one deterministic frame from an F6-selected source.

    No temporal search is permitted here. For video, the sample timestamp is
    exactly `source_start_s`; F10 owns Best Moment temporal search.
    """

    REQUIRED_KEYS = (
        "lavfi.blur",
        "lavfi.signalstats.YMIN",
        "lavfi.signalstats.YMAX",
        "lavfi.signalstats.YAVG",
        "lavfi.signalstats.SATAVG",
    )

    def __init__(self, ffmpeg_binary: str | None = None):
        binary = ffmpeg_binary or shutil.which("ffmpeg")
        if not binary:
            raise FrameAnalysisError("ffmpeg binary not found on PATH")
        self.ffmpeg_binary = str(binary)
        self.calls = 0

    @staticmethod
    def _parse_metadata(text: str) -> dict[str, float]:
        result: dict[str, float] = {}

        for key in FFmpegFrameDiagnostics.REQUIRED_KEYS:
            match = re.search(
                re.escape(key) + r"\s*=\s*(" + _FLOAT_RE + r")",
                text,
            )
            if match:
                result[key] = float(match.group(1))

        return result

    def analyze(self, scene) -> RepresentativeFrameMetrics:
        source_path = Path(str(scene.source_path or ""))
        if not source_path.is_file():
            raise FrameAnalysisError(
                f"source file missing: {source_path}"
            )

        sample_time = float(scene.source_start_s or 0.0)
        command = [
            self.ffmpeg_binary,
            "-hide_banner",
            "-nostdin",
            "-loglevel",
            "info",
        ]

        if sample_time > 0.0:
            command.extend(["-ss", f"{sample_time:.6f}"])

        command.extend(
            [
                "-i",
                str(source_path),
                "-map",
                "0:v:0",
                "-frames:v",
                "1",
                "-vf",
                (
                    "format=yuv420p,"
                    "blurdetect,"
                    "signalstats,"
                    "metadata=mode=print"
                ),
                "-an",
                "-sn",
                "-f",
                "null",
                "-",
            ]
        )

        self.calls += 1

        result = subprocess.run(
            command,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
        )

        combined = (result.stdout or "") + "\n" + (result.stderr or "")
        if result.returncode != 0:
            tail = "\n".join(combined.splitlines()[-12:])
            raise FrameAnalysisError(
                "ffmpeg representative-frame analysis failed: " + tail
            )

        values = self._parse_metadata(combined)
        missing = [
            key for key in self.REQUIRED_KEYS if key not in values
        ]
        if missing:
            raise FrameAnalysisError(
                "ffmpeg metadata missing keys: " + ", ".join(missing)
            )

        y_min = values["lavfi.signalstats.YMIN"]
        y_max = values["lavfi.signalstats.YMAX"]
        if y_max < y_min:
            raise FrameAnalysisError("signalstats returned YMAX < YMIN")

        return RepresentativeFrameMetrics(
            sample_time_s=sample_time,
            blur_metric=max(0.0, values["lavfi.blur"]),
            y_min=y_min,
            y_max=y_max,
            y_avg=values["lavfi.signalstats.YAVG"],
            sat_avg=max(0.0, values["lavfi.signalstats.SATAVG"]),
            luma_span=y_max - y_min,
            ffmpeg_binary=self.ffmpeg_binary,
        )


def _validate_alignment(request: ShotQualityRequest) -> None:
    base = request.video_base
    graph = request.story_graph

    if base.source_plan_context_hash != graph.source_plan_context_hash:
        raise ShotQualityError(
            "VideoBasePlan context hash does not match VisualStoryGraph"
        )
    if base.version != graph.source_video_base_version:
        raise ShotQualityError(
            "VideoBasePlan version does not match VisualStoryGraph source"
        )
    if base.source_selector_version != graph.source_selector_version:
        raise ShotQualityError(
            "selector version mismatch between VideoBasePlan and VisualStoryGraph"
        )
    if base.scene_count != graph.node_count:
        raise ShotQualityError(
            "scene/node count mismatch between F6 and F8"
        )

    base_numbers = [scene.scene_number for scene in base.scenes]
    graph_numbers = [node.scene_number for node in graph.nodes]
    if base_numbers != graph_numbers:
        raise ShotQualityError(
            "scene order mismatch between F6 and F8"
        )

    for scene, node in zip(base.scenes, graph.nodes):
        if bool(scene.placeholder) != bool(node.placeholder):
            raise ShotQualityError(
                f"placeholder mismatch at scene {scene.scene_number}"
            )
        if abs(float(scene.duration_seconds) - float(node.duration_seconds)) > 0.01:
            raise ShotQualityError(
                f"duration mismatch at scene {scene.scene_number}"
            )


def _sharpness_relative(raw_metrics: dict[int, RepresentativeFrameMetrics]):
    if not raw_metrics:
        return {}

    values = {
        scene_number: metrics.blur_metric
        for scene_number, metrics in raw_metrics.items()
    }

    minimum = min(values.values())
    maximum = max(values.values())

    if math.isclose(minimum, maximum, rel_tol=0.0, abs_tol=1e-12):
        return {
            scene_number: 0.5
            for scene_number in values
        }

    span = maximum - minimum
    return {
        scene_number: round(
            _clamp01(
                1.0 - ((blur - minimum) / span)
            ),
            3,
        )
        for scene_number, blur in values.items()
    }


def _luma_range_score(metrics: RepresentativeFrameMetrics) -> float:
    # Astronomy-aware conservative heuristic:
    # do not punish a low average luminance (night sky is expected).
    # Only reward usable tonal span, saturating at 64 code values.
    return round(_clamp01(metrics.luma_span / 64.0), 3)


def _quality_band(score: float) -> ShotQualityBand:
    if score >= 0.85:
        return ShotQualityBand.EXCELLENT
    if score >= 0.70:
        return ShotQualityBand.GOOD
    if score >= 0.50:
        return ShotQualityBand.USABLE
    return ShotQualityBand.WEAK


def _quality_flags(
    *,
    scene,
    resolution_score: float,
    framing_score: float,
    sharpness_score: float,
    metrics: RepresentativeFrameMetrics,
    scale: float,
) -> list[str]:
    flags = []

    if scale > 1.0001:
        flags.append("UPSCALE_REQUIRED")

    if scene.fit_mode == VideoFitMode.fit and framing_score < 0.45:
        flags.append("LOW_FRAME_OCCUPANCY")

    if scene.fit_mode == VideoFitMode.cover and framing_score < 0.45:
        flags.append("HEAVY_CROP")

    if resolution_score < 0.70:
        flags.append("LOW_RESOLUTION_FOR_OUTPUT")

    if sharpness_score < 0.35:
        flags.append("RELATIVE_BLUR_RISK")

    if metrics.luma_span < 32.0:
        flags.append("LOW_LUMA_RANGE")

    if metrics.y_max < 24.0:
        flags.append("NEAR_BLACK_FRAME")

    if metrics.y_min > 231.0:
        flags.append("NEAR_WHITE_FRAME")

    return flags


class ShotQualityScorer:
    """F9 deterministic technical shot-quality scorer.

    F9 never replaces F5 material selection and never searches the timeline.
    One frame per renderable scene is inspected at F6 `source_start_s`.
    """

    version = SHOT_QUALITY_VERSION

    def __init__(self, analyzer=None):
        self.analyzer = analyzer

    def build(self, request: ShotQualityRequest) -> ShotQualityPlan:
        _validate_alignment(request)

        base = request.video_base
        graph = request.story_graph

        node_by_number = {
            node.scene_number: node for node in graph.nodes
        }

        geometry: dict[int, tuple[float, float, float]] = {}
        raw_metrics: dict[int, RepresentativeFrameMetrics] = {}
        failures: dict[int, str] = {}

        analyzer = self.analyzer

        for scene in base.scenes:
            if scene.placeholder:
                continue

            try:
                geometry[scene.scene_number] = _geometry_components(
                    scene,
                    base.output_width,
                    base.output_height,
                )

                if analyzer is None:
                    analyzer = FFmpegFrameDiagnostics()

                raw_metrics[scene.scene_number] = analyzer.analyze(scene)

            except (FrameAnalysisError, OSError, ValueError) as exc:
                failures[scene.scene_number] = str(exc)

        sharpness = _sharpness_relative(raw_metrics)

        scene_scores: list[ShotQualitySceneScore] = []

        for scene in base.scenes:
            node = node_by_number[scene.scene_number]

            if scene.placeholder:
                flags = ["PLACEHOLDER_NOT_SCORABLE"]
                if scene.placeholder_reason is not None:
                    flags.append(
                        "F6:" + scene.placeholder_reason.value
                    )

                scene_scores.append(
                    ShotQualitySceneScore(
                        scene_number=scene.scene_number,
                        node_id=node.node_id,
                        selected_media_id=scene.selected_media_id,
                        media_type=scene.media_type,
                        source_path=scene.source_path,
                        placeholder=True,
                        status=ShotQualityStatus.NOT_SCORABLE,
                        score=None,
                        band=ShotQualityBand.NOT_SCORABLE,
                        flags=flags,
                        warnings=list(scene.warnings),
                    )
                )
                continue

            if scene.scene_number in failures:
                scene_scores.append(
                    ShotQualitySceneScore(
                        scene_number=scene.scene_number,
                        node_id=node.node_id,
                        selected_media_id=scene.selected_media_id,
                        media_type=scene.media_type,
                        source_path=scene.source_path,
                        placeholder=False,
                        status=ShotQualityStatus.ANALYSIS_FAILED,
                        score=None,
                        band=ShotQualityBand.ANALYSIS_FAILED,
                        flags=["REPRESENTATIVE_FRAME_ANALYSIS_FAILED"],
                        warnings=[
                            *scene.warnings,
                            failures[scene.scene_number],
                        ],
                    )
                )
                continue

            resolution_score, framing_score, scale = geometry[
                scene.scene_number
            ]
            frame = raw_metrics[scene.scene_number]
            sharpness_score = sharpness[scene.scene_number]
            luma_score = _luma_range_score(frame)

            components = ShotQualityComponents(
                resolution_adequacy=resolution_score,
                framing_efficiency=framing_score,
                sharpness_relative=sharpness_score,
                luma_range=luma_score,
            )

            score = round(
                0.40 * components.resolution_adequacy
                + 0.25 * components.framing_efficiency
                + 0.20 * components.sharpness_relative
                + 0.15 * components.luma_range,
                3,
            )

            scene_scores.append(
                ShotQualitySceneScore(
                    scene_number=scene.scene_number,
                    node_id=node.node_id,
                    selected_media_id=scene.selected_media_id,
                    media_type=scene.media_type,
                    source_path=scene.source_path,
                    placeholder=False,
                    status=ShotQualityStatus.SCORED,
                    score=score,
                    band=_quality_band(score),
                    components=components,
                    frame_metrics=frame,
                    flags=_quality_flags(
                        scene=scene,
                        resolution_score=resolution_score,
                        framing_score=framing_score,
                        sharpness_score=sharpness_score,
                        metrics=frame,
                        scale=scale,
                    ),
                    warnings=list(scene.warnings),
                )
            )

        scored_values = [
            item.score
            for item in scene_scores
            if item.status == ShotQualityStatus.SCORED
            and item.score is not None
        ]

        stable_payload = {
            "version": self.version,
            "source_plan_context_hash": base.source_plan_context_hash,
            "source_video_base_version": base.version,
            "source_story_graph_version": graph.version,
            "source_story_graph_hash": graph.graph_hash,
            "representative_frame_policy": "F6_SOURCE_START_SINGLE_FRAME",
            "heuristic_profile": "TECHNICAL_V01",
            "scenes": [
                item.model_dump(mode="json")
                for item in scene_scores
            ],
        }

        scored_count = sum(
            item.status == ShotQualityStatus.SCORED
            for item in scene_scores
        )
        not_scorable_count = sum(
            item.status == ShotQualityStatus.NOT_SCORABLE
            for item in scene_scores
        )
        failed_count = sum(
            item.status == ShotQualityStatus.ANALYSIS_FAILED
            for item in scene_scores
        )

        return ShotQualityPlan(
            subject=base.subject,
            source_plan_context_hash=base.source_plan_context_hash,
            source_video_base_version=base.version,
            source_story_graph_version=graph.version,
            source_story_graph_hash=graph.graph_hash,
            scene_count=len(scene_scores),
            scored_count=scored_count,
            not_scorable_count=not_scorable_count,
            analysis_failed_count=failed_count,
            ffmpeg_frames_analyzed=scored_count,
            mean_score=(
                round(sum(scored_values) / len(scored_values), 3)
                if scored_values
                else None
            ),
            scenes=scene_scores,
            structural_checks=ShotQualityStructuralChecks(
                source_alignment=True,
                graph_hash_preserved=True,
                placeholders_preserved=(
                    not_scorable_count == base.placeholder_count
                ),
                no_best_moment_search=True,
                no_material_search=True,
            ),
            quality_hash=_hash_json(stable_payload),
            generated_at_utc=datetime.now(timezone.utc),
        )
