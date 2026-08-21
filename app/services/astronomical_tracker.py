from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.models.astromedia import MediaType
from app.models.astronomical_tracker import (
    ASTRONOMICAL_TRACKER_VERSION,
    AstronomicalTrackingPlan,
    AstronomicalTrackingRequest,
    NormalizedBoundingBox,
    TrackingPoint,
    TrackingSceneResult,
    TrackingSceneStatus,
    TrackingStructuralChecks,
)
from app.models.best_moment import BestMomentStatus


class AstronomicalTrackingError(RuntimeError):
    pass


class TrackingBackendUnavailable(AstronomicalTrackingError):
    pass


class TrackingBackendError(AstronomicalTrackingError):
    pass


@dataclass(frozen=True)
class BackendTrackResult:
    points: list[TrackingPoint]
    complete: bool
    warnings: list[str]


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


def _validate_alignment(request: AstronomicalTrackingRequest) -> None:
    base = request.video_base
    graph = request.story_graph
    quality = request.shot_quality
    moment = request.best_moment

    if base.source_plan_context_hash != graph.source_plan_context_hash:
        raise AstronomicalTrackingError("F6/F8 context hash mismatch")
    if base.source_plan_context_hash != quality.source_plan_context_hash:
        raise AstronomicalTrackingError("F6/F9 context hash mismatch")
    if base.source_plan_context_hash != moment.source_plan_context_hash:
        raise AstronomicalTrackingError("F6/F10 context hash mismatch")

    if base.version != graph.source_video_base_version:
        raise AstronomicalTrackingError("F6 version mismatch against F8")
    if base.version != quality.source_video_base_version:
        raise AstronomicalTrackingError("F6 version mismatch against F9")
    if base.version != moment.source_video_base_version:
        raise AstronomicalTrackingError("F6 version mismatch against F10")

    if graph.version != quality.source_story_graph_version:
        raise AstronomicalTrackingError("F8 version mismatch against F9")
    if graph.version != moment.source_story_graph_version:
        raise AstronomicalTrackingError("F8 version mismatch against F10")
    if graph.graph_hash != quality.source_story_graph_hash:
        raise AstronomicalTrackingError("F8 graph hash mismatch against F9")
    if graph.graph_hash != moment.source_story_graph_hash:
        raise AstronomicalTrackingError("F8 graph hash mismatch against F10")

    if quality.version != moment.source_shot_quality_version:
        raise AstronomicalTrackingError("F9 version mismatch against F10")
    if quality.quality_hash != moment.source_shot_quality_hash:
        raise AstronomicalTrackingError("F9 quality hash mismatch against F10")

    if not (
        base.scene_count
        == graph.node_count
        == quality.scene_count
        == moment.scene_count
    ):
        raise AstronomicalTrackingError("scene count mismatch across F6/F8/F9/F10")

    base_numbers = [scene.scene_number for scene in base.scenes]
    graph_numbers = [scene.scene_number for scene in graph.nodes]
    quality_numbers = [scene.scene_number for scene in quality.scenes]
    moment_numbers = [scene.scene_number for scene in moment.scenes]

    if not (
        base_numbers
        == graph_numbers
        == quality_numbers
        == moment_numbers
    ):
        raise AstronomicalTrackingError(
            "scene order mismatch across F6/F8/F9/F10"
        )

    for base_scene, graph_scene, quality_scene, moment_scene in zip(
        base.scenes,
        graph.nodes,
        quality.scenes,
        moment.scenes,
    ):
        number = base_scene.scene_number

        if bool(base_scene.placeholder) != bool(graph_scene.placeholder):
            raise AstronomicalTrackingError(
                f"placeholder mismatch F6/F8 scene {number}"
            )
        if bool(base_scene.placeholder) != bool(quality_scene.placeholder):
            raise AstronomicalTrackingError(
                f"placeholder mismatch F6/F9 scene {number}"
            )

        if base_scene.selected_media_id != quality_scene.selected_media_id:
            raise AstronomicalTrackingError(
                f"material identity mismatch F6/F9 scene {number}"
            )
        if base_scene.selected_media_id != moment_scene.selected_media_id:
            raise AstronomicalTrackingError(
                f"material identity mismatch F6/F10 scene {number}"
            )

        if base_scene.source_path != quality_scene.source_path:
            raise AstronomicalTrackingError(
                f"source path mismatch F6/F9 scene {number}"
            )
        if base_scene.source_path != moment_scene.source_path:
            raise AstronomicalTrackingError(
                f"source path mismatch F6/F10 scene {number}"
            )


def _normalized_bbox(
    x: float,
    y: float,
    width: float,
    height: float,
    frame_width: float,
    frame_height: float,
) -> NormalizedBoundingBox:
    if frame_width <= 0 or frame_height <= 0:
        raise TrackingBackendError("frame dimensions must be positive")

    nx = max(0.0, min(1.0, x / frame_width))
    ny = max(0.0, min(1.0, y / frame_height))
    nw = max(1e-9, min(1.0 - nx, width / frame_width))
    nh = max(1e-9, min(1.0 - ny, height / frame_height))

    return NormalizedBoundingBox(
        x=round(nx, 6),
        y=round(ny, 6),
        width=round(nw, 6),
        height=round(nh, 6),
    )


class OpenCVCSRTBackend:
    """CPU single-object tracker loaded lazily.

    OpenCV is intentionally not added to the main project dependencies by F11.
    If an existing environment provides CSRT, it can be used. Otherwise F11
    returns BACKEND_UNAVAILABLE instead of mutating dependencies.
    """

    name = "opencv_csrt"

    @staticmethod
    def _load_cv2():
        try:
            import cv2  # type: ignore
        except Exception as exc:
            raise TrackingBackendUnavailable(
                "OpenCV is not installed in the active environment"
            ) from exc
        return cv2

    @staticmethod
    def _tracker_factory(cv2):
        factory = getattr(cv2, "TrackerCSRT_create", None)
        if callable(factory):
            return factory

        legacy = getattr(cv2, "legacy", None)
        if legacy is not None:
            factory = getattr(legacy, "TrackerCSRT_create", None)
            if callable(factory):
                return factory

        raise TrackingBackendUnavailable(
            "OpenCV CSRT tracker is unavailable; opencv-contrib build may be required"
        )

    def track(
        self,
        *,
        source_path: str,
        start_s: float,
        end_s: float,
        seed_bbox: NormalizedBoundingBox,
        sample_rate_hz: float,
    ) -> BackendTrackResult:
        source = Path(source_path)
        if not source.is_file():
            raise TrackingBackendError(f"source video missing: {source}")

        cv2 = self._load_cv2()
        factory = self._tracker_factory(cv2)

        capture = cv2.VideoCapture(str(source))
        if not capture.isOpened():
            capture.release()
            raise TrackingBackendError("OpenCV could not open source video")

        try:
            capture.set(cv2.CAP_PROP_POS_MSEC, float(start_s) * 1000.0)
            ok, frame = capture.read()
            if not ok or frame is None:
                raise TrackingBackendError(
                    "could not decode first frame at Best Moment start"
                )

            frame_height, frame_width = frame.shape[:2]
            if frame_width <= 0 or frame_height <= 0:
                raise TrackingBackendError("invalid decoded frame dimensions")

            tracker = factory()

            bbox_px = (
                float(seed_bbox.x * frame_width),
                float(seed_bbox.y * frame_height),
                float(seed_bbox.width * frame_width),
                float(seed_bbox.height * frame_height),
            )

            init_result = tracker.init(frame, bbox_px)
            if init_result is False:
                raise TrackingBackendError("CSRT tracker initialization failed")

            interval = 1.0 / float(sample_rate_hz)
            next_record_s = float(start_s)

            points = [
                TrackingPoint(
                    timestamp_s=round(float(start_s), 6),
                    bbox=seed_bbox,
                    center_x=round(seed_bbox.x + seed_bbox.width / 2.0, 6),
                    center_y=round(seed_bbox.y + seed_bbox.height / 2.0, 6),
                    tracking_ok=True,
                )
            ]
            next_record_s += interval

            complete = True
            warnings: list[str] = []

            while True:
                ok, frame = capture.read()
                if not ok or frame is None:
                    break

                timestamp_s = float(capture.get(cv2.CAP_PROP_POS_MSEC)) / 1000.0
                if timestamp_s > float(end_s) + 1e-6:
                    break

                tracked_ok, bbox = tracker.update(frame)
                if not tracked_ok:
                    complete = False
                    warnings.append(
                        f"TRACK_LOST_AT={timestamp_s:.6f}"
                    )
                    break

                if timestamp_s + 1e-6 < next_record_s:
                    continue

                x, y, width, height = [float(value) for value in bbox]
                normalized = _normalized_bbox(
                    x,
                    y,
                    width,
                    height,
                    frame_width,
                    frame_height,
                )

                points.append(
                    TrackingPoint(
                        timestamp_s=round(timestamp_s, 6),
                        bbox=normalized,
                        center_x=round(
                            normalized.x + normalized.width / 2.0,
                            6,
                        ),
                        center_y=round(
                            normalized.y + normalized.height / 2.0,
                            6,
                        ),
                        tracking_ok=True,
                    )
                )
                next_record_s += interval

            if not points:
                raise TrackingBackendError("tracker returned no points")

            return BackendTrackResult(
                points=points,
                complete=complete,
                warnings=warnings,
            )

        finally:
            capture.release()


class AstronomicalObjectTracker:
    version = ASTRONOMICAL_TRACKER_VERSION

    def __init__(self, backend=None):
        self.backend = backend
        self.backend_invocations = 0

    def _get_backend(self, name: str):
        if self.backend is not None:
            return self.backend

        if name == "opencv_csrt":
            self.backend = OpenCVCSRTBackend()
            return self.backend

        raise TrackingBackendUnavailable(
            f"unsupported tracking backend: {name}"
        )

    def build(
        self,
        request: AstronomicalTrackingRequest,
    ) -> AstronomicalTrackingPlan:
        _validate_alignment(request)

        base = request.video_base
        graph = request.story_graph
        quality = request.shot_quality
        moment = request.best_moment

        scene_numbers = {scene.scene_number for scene in base.scenes}
        for seed in request.seeds:
            if seed.scene_number not in scene_numbers:
                raise AstronomicalTrackingError(
                    f"tracking seed references unknown scene {seed.scene_number}"
                )

        seeds = {
            seed.scene_number: seed
            for seed in request.seeds
        }
        graph_by_number = {
            node.scene_number: node for node in graph.nodes
        }
        moment_by_number = {
            scene.scene_number: scene for scene in moment.scenes
        }

        results: list[TrackingSceneResult] = []

        for scene in base.scenes:
            number = scene.scene_number
            node = graph_by_number[number]
            moment_scene = moment_by_number[number]
            seed = seeds.get(number)

            common = dict(
                scene_number=number,
                node_id=node.node_id,
                selected_media_id=scene.selected_media_id,
                media_type=scene.media_type,
                source_path=scene.source_path,
            )

            if scene.placeholder:
                if seed is not None:
                    raise AstronomicalTrackingError(
                        f"placeholder scene {number} cannot accept tracking seed"
                    )
                results.append(
                    TrackingSceneResult(
                        **common,
                        status=TrackingSceneStatus.PLACEHOLDER_NOT_APPLICABLE,
                        warnings=["PLACEHOLDER_HAS_NO_TRACKABLE_SOURCE"],
                    )
                )
                continue

            if scene.media_type == MediaType.IMAGE:
                if seed is not None:
                    raise AstronomicalTrackingError(
                        f"static image scene {number} cannot accept tracking seed"
                    )
                results.append(
                    TrackingSceneResult(
                        **common,
                        status=TrackingSceneStatus.STATIC_IMAGE_NOT_APPLICABLE,
                        warnings=["STATIC_IMAGE_HAS_NO_TEMPORAL_TRACK"],
                    )
                )
                continue

            if scene.media_type != MediaType.VIDEO:
                results.append(
                    TrackingSceneResult(
                        **common,
                        status=TrackingSceneStatus.TRACKING_FAILED,
                        warnings=["UNSUPPORTED_MEDIA_TYPE"],
                    )
                )
                continue

            if moment_scene.status != BestMomentStatus.SELECTED:
                results.append(
                    TrackingSceneResult(
                        **common,
                        status=TrackingSceneStatus.BEST_MOMENT_UNAVAILABLE,
                        warnings=[
                            "VIDEO_REQUIRES_SELECTED_F10_WINDOW_BEFORE_TRACKING"
                        ],
                    )
                )
                continue

            if seed is None:
                results.append(
                    TrackingSceneResult(
                        **common,
                        status=TrackingSceneStatus.SEED_REQUIRED,
                        window_start_s=moment_scene.selected_start_s,
                        window_end_s=moment_scene.selected_end_s,
                        warnings=[
                            "EXPLICIT_OBJECT_SEED_REQUIRED",
                            "F11_DOES_NOT_INFER_OBJECT_FROM_FREE_TEXT",
                        ],
                    )
                )
                continue

            try:
                self.backend_invocations += 1
                backend = self._get_backend(request.backend)

                tracked = backend.track(
                    source_path=str(scene.source_path),
                    start_s=float(moment_scene.selected_start_s),
                    end_s=float(moment_scene.selected_end_s),
                    seed_bbox=seed.bbox,
                    sample_rate_hz=request.sample_rate_hz,
                )

                status = (
                    TrackingSceneStatus.TRACKED
                    if tracked.complete
                    else TrackingSceneStatus.TRACKED_PARTIAL
                )

                results.append(
                    TrackingSceneResult(
                        **common,
                        status=status,
                        subject_label=seed.subject_label,
                        seed_source=seed.source,
                        seed_bbox=seed.bbox,
                        window_start_s=moment_scene.selected_start_s,
                        window_end_s=moment_scene.selected_end_s,
                        backend=request.backend,
                        complete_track=tracked.complete,
                        points=tracked.points,
                        warnings=tracked.warnings,
                    )
                )

            except TrackingBackendUnavailable as exc:
                results.append(
                    TrackingSceneResult(
                        **common,
                        status=TrackingSceneStatus.BACKEND_UNAVAILABLE,
                        subject_label=seed.subject_label,
                        seed_source=seed.source,
                        seed_bbox=seed.bbox,
                        window_start_s=moment_scene.selected_start_s,
                        window_end_s=moment_scene.selected_end_s,
                        backend=request.backend,
                        warnings=[str(exc)],
                    )
                )

            except (TrackingBackendError, OSError, ValueError) as exc:
                results.append(
                    TrackingSceneResult(
                        **common,
                        status=TrackingSceneStatus.TRACKING_FAILED,
                        subject_label=seed.subject_label,
                        seed_source=seed.source,
                        seed_bbox=seed.bbox,
                        window_start_s=moment_scene.selected_start_s,
                        window_end_s=moment_scene.selected_end_s,
                        backend=request.backend,
                        warnings=[str(exc)],
                    )
                )

        tracked_count = sum(
            scene.status == TrackingSceneStatus.TRACKED
            for scene in results
        )
        partial_count = sum(
            scene.status == TrackingSceneStatus.TRACKED_PARTIAL
            for scene in results
        )
        placeholder_count = sum(
            scene.status == TrackingSceneStatus.PLACEHOLDER_NOT_APPLICABLE
            for scene in results
        )
        static_count = sum(
            scene.status == TrackingSceneStatus.STATIC_IMAGE_NOT_APPLICABLE
            for scene in results
        )
        seed_required_count = sum(
            scene.status == TrackingSceneStatus.SEED_REQUIRED
            for scene in results
        )
        backend_unavailable_count = sum(
            scene.status == TrackingSceneStatus.BACKEND_UNAVAILABLE
            for scene in results
        )
        failed_count = sum(
            scene.status
            in {
                TrackingSceneStatus.TRACKING_FAILED,
                TrackingSceneStatus.BEST_MOMENT_UNAVAILABLE,
            }
            for scene in results
        )
        point_count = sum(len(scene.points) for scene in results)

        stable_payload = {
            "version": self.version,
            "source_plan_context_hash": base.source_plan_context_hash,
            "source_story_graph_hash": graph.graph_hash,
            "source_shot_quality_hash": quality.quality_hash,
            "source_best_moment_hash": moment.best_moment_hash,
            "backend": request.backend,
            "sample_rate_hz": request.sample_rate_hz,
            "seeds": [
                seed.model_dump(mode="json")
                for seed in request.seeds
            ],
            "scenes": [
                scene.model_dump(mode="json")
                for scene in results
            ],
        }

        return AstronomicalTrackingPlan(
            subject=base.subject,
            source_plan_context_hash=base.source_plan_context_hash,
            source_video_base_version=base.version,
            source_story_graph_version=graph.version,
            source_story_graph_hash=graph.graph_hash,
            source_shot_quality_version=quality.version,
            source_shot_quality_hash=quality.quality_hash,
            source_best_moment_version=moment.version,
            source_best_moment_hash=moment.best_moment_hash,
            scene_count=len(results),
            tracked_count=tracked_count,
            partial_count=partial_count,
            placeholder_count=placeholder_count,
            static_image_count=static_count,
            seed_required_count=seed_required_count,
            backend_unavailable_count=backend_unavailable_count,
            tracking_failed_count=failed_count,
            backend_invocations=self.backend_invocations,
            tracking_point_count=point_count,
            scenes=results,
            structural_checks=TrackingStructuralChecks(
                source_alignment=True,
                graph_hash_preserved=True,
                quality_hash_preserved=True,
                best_moment_hash_preserved=True,
                material_identity_preserved=True,
                best_moment_window_preserved=True,
                no_reframing=True,
            ),
            tracking_hash=_hash_json(stable_payload),
            generated_at_utc=datetime.now(timezone.utc),
        )
