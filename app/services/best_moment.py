from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, timezone
from typing import Any

from app.models.astromedia import MediaType
from app.models.best_moment import (
    BEST_MOMENT_VERSION,
    BestMomentCandidate,
    BestMomentPlan,
    BestMomentRequest,
    BestMomentSceneResult,
    BestMomentStatus,
    BestMomentStructuralChecks,
)
from app.services.shot_quality import (
    FFmpegFrameDiagnostics,
    FrameAnalysisError,
)


class BestMomentError(RuntimeError):
    pass


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


def _validate_alignment(request: BestMomentRequest) -> None:
    base = request.video_base
    graph = request.story_graph
    quality = request.shot_quality

    if base.source_plan_context_hash != graph.source_plan_context_hash:
        raise BestMomentError("F6/F8 context hash mismatch")
    if base.source_plan_context_hash != quality.source_plan_context_hash:
        raise BestMomentError("F6/F9 context hash mismatch")
    if base.version != graph.source_video_base_version:
        raise BestMomentError("F6 version mismatch against F8")
    if base.version != quality.source_video_base_version:
        raise BestMomentError("F6 version mismatch against F9")
    if graph.version != quality.source_story_graph_version:
        raise BestMomentError("F8 version mismatch against F9")
    if graph.graph_hash != quality.source_story_graph_hash:
        raise BestMomentError("F8 graph hash mismatch against F9")

    if base.scene_count != graph.node_count:
        raise BestMomentError("F6/F8 scene count mismatch")
    if base.scene_count != quality.scene_count:
        raise BestMomentError("F6/F9 scene count mismatch")

    base_numbers = [scene.scene_number for scene in base.scenes]
    graph_numbers = [node.scene_number for node in graph.nodes]
    quality_numbers = [scene.scene_number for scene in quality.scenes]

    if base_numbers != graph_numbers or base_numbers != quality_numbers:
        raise BestMomentError("scene order mismatch across F6/F8/F9")

    for base_scene, node, quality_scene in zip(
        base.scenes,
        graph.nodes,
        quality.scenes,
    ):
        if bool(base_scene.placeholder) != bool(node.placeholder):
            raise BestMomentError(
                f"placeholder mismatch F6/F8 scene {base_scene.scene_number}"
            )
        if bool(base_scene.placeholder) != bool(quality_scene.placeholder):
            raise BestMomentError(
                f"placeholder mismatch F6/F9 scene {base_scene.scene_number}"
            )
        if base_scene.selected_media_id != quality_scene.selected_media_id:
            raise BestMomentError(
                f"material identity mismatch F6/F9 scene {base_scene.scene_number}"
            )
        if base_scene.source_path != quality_scene.source_path:
            raise BestMomentError(
                f"source path mismatch F6/F9 scene {base_scene.scene_number}"
            )


def _candidate_starts(
    *,
    source_duration: float,
    requested_duration: float,
    max_candidates: int,
) -> list[float]:
    if requested_duration <= 0.0:
        raise BestMomentError("requested duration must be positive")
    if source_duration <= 0.0:
        raise BestMomentError("video source duration must be positive")

    max_start = max(0.0, source_duration - requested_duration)
    if math.isclose(max_start, 0.0, abs_tol=1e-9):
        return [0.0]

    count = min(
        max_candidates,
        max(3, int(math.ceil(max_start)) + 1),
    )

    if count <= 1:
        return [0.0]

    step = max_start / (count - 1)
    starts = [round(index * step, 6) for index in range(count)]
    starts[0] = 0.0
    starts[-1] = round(max_start, 6)
    return starts


def _relative_sharpness(raw_blur: list[float]) -> list[float]:
    if not raw_blur:
        return []

    minimum = min(raw_blur)
    maximum = max(raw_blur)

    if math.isclose(minimum, maximum, rel_tol=0.0, abs_tol=1e-12):
        return [0.5 for _ in raw_blur]

    span = maximum - minimum
    return [
        round(
            _clamp01(1.0 - ((value - minimum) / span)),
            3,
        )
        for value in raw_blur
    ]


def _luma_score(span: float) -> float:
    # Astronomy-aware: dark mean luminance is valid. Reward tonal span only.
    return round(_clamp01(float(span) / 64.0), 3)


class BestMomentDetector:
    """F10 deterministic temporal-window selector.

    The material is immutable: F10 searches only inside the exact video
    selected upstream. Each candidate window is evaluated by one frame at its
    temporal center. No tracking, reframing, LLM, GPU, rendering or publishing.
    """

    version = BEST_MOMENT_VERSION

    def __init__(self, analyzer=None):
        self.analyzer = analyzer

    def build(self, request: BestMomentRequest) -> BestMomentPlan:
        _validate_alignment(request)

        base = request.video_base
        graph = request.story_graph
        quality = request.shot_quality

        node_by_number = {
            node.scene_number: node for node in graph.nodes
        }
        quality_by_number = {
            scene.scene_number: scene for scene in quality.scenes
        }

        analyzer = self.analyzer
        results: list[BestMomentSceneResult] = []

        for scene in base.scenes:
            node = node_by_number[scene.scene_number]
            baseline = quality_by_number[scene.scene_number]
            baseline_score = baseline.score

            if scene.placeholder:
                results.append(
                    BestMomentSceneResult(
                        scene_number=scene.scene_number,
                        node_id=node.node_id,
                        selected_media_id=scene.selected_media_id,
                        media_type=scene.media_type,
                        source_path=scene.source_path,
                        status=BestMomentStatus.PLACEHOLDER_NOT_APPLICABLE,
                        source_duration_seconds=scene.source_duration_seconds,
                        requested_duration_seconds=scene.duration_seconds,
                        original_start_s=scene.source_start_s,
                        baseline_shot_quality_score=baseline_score,
                        warnings=[
                            "PLACEHOLDER_HAS_NO_TEMPORAL_SOURCE",
                            *scene.warnings,
                        ],
                    )
                )
                continue

            if scene.media_type == MediaType.IMAGE:
                results.append(
                    BestMomentSceneResult(
                        scene_number=scene.scene_number,
                        node_id=node.node_id,
                        selected_media_id=scene.selected_media_id,
                        media_type=scene.media_type,
                        source_path=scene.source_path,
                        status=BestMomentStatus.STATIC_IMAGE,
                        source_duration_seconds=scene.source_duration_seconds,
                        requested_duration_seconds=scene.duration_seconds,
                        original_start_s=scene.source_start_s,
                        baseline_shot_quality_score=baseline_score,
                        warnings=["STATIC_IMAGE_HAS_NO_BEST_MOMENT_SEARCH"],
                    )
                )
                continue

            if scene.media_type != MediaType.VIDEO:
                results.append(
                    BestMomentSceneResult(
                        scene_number=scene.scene_number,
                        node_id=node.node_id,
                        selected_media_id=scene.selected_media_id,
                        media_type=scene.media_type,
                        source_path=scene.source_path,
                        status=BestMomentStatus.ANALYSIS_FAILED,
                        source_duration_seconds=scene.source_duration_seconds,
                        requested_duration_seconds=scene.duration_seconds,
                        original_start_s=scene.source_start_s,
                        baseline_shot_quality_score=baseline_score,
                        warnings=["UNSUPPORTED_MEDIA_TYPE_FOR_F10"],
                    )
                )
                continue

            try:
                starts = _candidate_starts(
                    source_duration=float(scene.source_duration_seconds),
                    requested_duration=float(scene.duration_seconds),
                    max_candidates=request.max_candidates,
                )

                if analyzer is None:
                    analyzer = FFmpegFrameDiagnostics()

                raw = []
                for start in starts:
                    end = min(
                        float(scene.source_duration_seconds),
                        start + float(scene.duration_seconds),
                    )
                    sample_time = start + ((end - start) / 2.0)

                    proxy = scene.model_copy(
                        update={"source_start_s": sample_time}
                    )
                    metrics = analyzer.analyze(proxy)

                    raw.append(
                        {
                            "start": start,
                            "end": end,
                            "sample": sample_time,
                            "metrics": metrics,
                        }
                    )

                sharpness = _relative_sharpness(
                    [item["metrics"].blur_metric for item in raw]
                )

                candidates: list[BestMomentCandidate] = []
                for index, (item, sharpness_score) in enumerate(
                    zip(raw, sharpness),
                    start=1,
                ):
                    metrics = item["metrics"]
                    luma = _luma_score(metrics.luma_span)
                    score = round(
                        0.65 * sharpness_score
                        + 0.35 * luma,
                        3,
                    )
                    candidates.append(
                        BestMomentCandidate(
                            candidate_index=index,
                            window_start_s=item["start"],
                            window_end_s=item["end"],
                            sample_time_s=item["sample"],
                            blur_metric=metrics.blur_metric,
                            luma_span=metrics.luma_span,
                            y_min=metrics.y_min,
                            y_max=metrics.y_max,
                            y_avg=metrics.y_avg,
                            sharpness_relative=sharpness_score,
                            luma_range_score=luma,
                            temporal_score=score,
                        )
                    )

                winner = max(
                    candidates,
                    key=lambda candidate: (
                        candidate.temporal_score,
                        -candidate.window_start_s,
                    ),
                )

                results.append(
                    BestMomentSceneResult(
                        scene_number=scene.scene_number,
                        node_id=node.node_id,
                        selected_media_id=scene.selected_media_id,
                        media_type=scene.media_type,
                        source_path=scene.source_path,
                        status=BestMomentStatus.SELECTED,
                        source_duration_seconds=scene.source_duration_seconds,
                        requested_duration_seconds=scene.duration_seconds,
                        original_start_s=scene.source_start_s,
                        selected_start_s=winner.window_start_s,
                        selected_end_s=winner.window_end_s,
                        selected_sample_time_s=winner.sample_time_s,
                        selected_score=winner.temporal_score,
                        baseline_shot_quality_score=baseline_score,
                        candidates=candidates,
                    )
                )

            except (BestMomentError, FrameAnalysisError, OSError, ValueError) as exc:
                results.append(
                    BestMomentSceneResult(
                        scene_number=scene.scene_number,
                        node_id=node.node_id,
                        selected_media_id=scene.selected_media_id,
                        media_type=scene.media_type,
                        source_path=scene.source_path,
                        status=BestMomentStatus.ANALYSIS_FAILED,
                        source_duration_seconds=scene.source_duration_seconds,
                        requested_duration_seconds=scene.duration_seconds,
                        original_start_s=scene.source_start_s,
                        baseline_shot_quality_score=baseline_score,
                        warnings=[str(exc)],
                    )
                )

        selected_count = sum(
            item.status == BestMomentStatus.SELECTED
            for item in results
        )
        placeholder_count = sum(
            item.status == BestMomentStatus.PLACEHOLDER_NOT_APPLICABLE
            for item in results
        )
        static_count = sum(
            item.status == BestMomentStatus.STATIC_IMAGE
            for item in results
        )
        failed_count = sum(
            item.status == BestMomentStatus.ANALYSIS_FAILED
            for item in results
        )
        frame_count = sum(len(item.candidates) for item in results)

        stable_payload = {
            "version": self.version,
            "source_plan_context_hash": base.source_plan_context_hash,
            "source_video_base_version": base.version,
            "source_story_graph_version": graph.version,
            "source_story_graph_hash": graph.graph_hash,
            "source_shot_quality_version": quality.version,
            "source_shot_quality_hash": quality.quality_hash,
            "candidate_policy": "EQUALLY_SPACED_WINDOW_CENTERS_V01",
            "scoring_profile": "TEMPORAL_TECHNICAL_V01",
            "max_candidates": request.max_candidates,
            "scenes": [
                item.model_dump(mode="json")
                for item in results
            ],
        }

        return BestMomentPlan(
            subject=base.subject,
            source_plan_context_hash=base.source_plan_context_hash,
            source_video_base_version=base.version,
            source_story_graph_version=graph.version,
            source_story_graph_hash=graph.graph_hash,
            source_shot_quality_version=quality.version,
            source_shot_quality_hash=quality.quality_hash,
            max_candidates=request.max_candidates,
            scene_count=len(results),
            selected_count=selected_count,
            placeholder_count=placeholder_count,
            static_image_count=static_count,
            analysis_failed_count=failed_count,
            ffmpeg_frames_analyzed=frame_count,
            scenes=results,
            structural_checks=BestMomentStructuralChecks(
                source_alignment=True,
                graph_hash_preserved=True,
                quality_hash_preserved=True,
                material_identity_preserved=True,
                placeholders_preserved=(
                    placeholder_count == base.placeholder_count
                ),
                static_images_not_scanned=all(
                    not item.candidates
                    for item in results
                    if item.status == BestMomentStatus.STATIC_IMAGE
                ),
            ),
            best_moment_hash=_hash_json(stable_payload),
            generated_at_utc=datetime.now(timezone.utc),
        )
