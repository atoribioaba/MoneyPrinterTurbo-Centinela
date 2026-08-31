from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from app.models.astronomical_tracker import (
    TrackingSceneStatus,
)
from app.models.best_moment import BestMomentStatus
from app.models.cinematic_director import (
    CinematicPace,
    CompositionIntent,
)
from app.models.schema import VideoFitMode
from app.models.smart_reframing import (
    SMART_REFRAMING_VERSION,
    CropGeometry,
    FocalSource,
    ReframeKeyframe,
    ReframingScenePlan,
    ReframingSceneStatus,
    ReframingStructuralChecks,
    SmartFocalHint,
    SmartReframingPlan,
    SmartReframingRequest,
)
from app.services.smart_focal import (
    FocalDecision,
    fallback_focal_decision,
)


class SmartReframingError(RuntimeError):
    pass


_SMARTFOCAL_FALLBACK_METHOD = fallback_focal_decision().method


def _smartfocal_decision_is_informative(
    decision: FocalDecision,
) -> bool:
    """Respect SmartFocal V0.1's real fallback contract.

    SmartFocal V0.1 explicitly states that `confidence` is not yet a
    calibrated production threshold. F12 therefore must not invent one.
    The canonical no-information signal is method == "fallback_center".
    """
    return decision.method != _SMARTFOCAL_FALLBACK_METHOD


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


def smartfocal_hint_from_decision(
    *,
    scene_number: int,
    decision: FocalDecision,
) -> SmartFocalHint:
    """Bridge the canonical SmartFocal V0.1 decision into F12."""
    return SmartFocalHint(
        scene_number=scene_number,
        focal_x=decision.focal_x,
        focal_y=decision.focal_y,
        confidence=decision.confidence,
        method=decision.method,
    )


def _validate_alignment(request: SmartReframingRequest) -> None:
    base = request.video_base
    graph = request.story_graph
    quality = request.shot_quality
    moment = request.best_moment
    tracking = request.tracking

    context_hashes = {
        base.source_plan_context_hash,
        graph.source_plan_context_hash,
        quality.source_plan_context_hash,
        moment.source_plan_context_hash,
        tracking.source_plan_context_hash,
    }
    if len(context_hashes) != 1:
        raise SmartReframingError(
            "context hash mismatch across F6/F8/F9/F10/F11"
        )

    if base.version != graph.source_video_base_version:
        raise SmartReframingError("F6 version mismatch against F8")
    if base.version != quality.source_video_base_version:
        raise SmartReframingError("F6 version mismatch against F9")
    if base.version != moment.source_video_base_version:
        raise SmartReframingError("F6 version mismatch against F10")
    if base.version != tracking.source_video_base_version:
        raise SmartReframingError("F6 version mismatch against F11")

    if graph.version != quality.source_story_graph_version:
        raise SmartReframingError("F8 version mismatch against F9")
    if graph.version != moment.source_story_graph_version:
        raise SmartReframingError("F8 version mismatch against F10")
    if graph.version != tracking.source_story_graph_version:
        raise SmartReframingError("F8 version mismatch against F11")

    if graph.graph_hash != quality.source_story_graph_hash:
        raise SmartReframingError("F8 graph hash mismatch against F9")
    if graph.graph_hash != moment.source_story_graph_hash:
        raise SmartReframingError("F8 graph hash mismatch against F10")
    if graph.graph_hash != tracking.source_story_graph_hash:
        raise SmartReframingError("F8 graph hash mismatch against F11")

    if quality.version != moment.source_shot_quality_version:
        raise SmartReframingError("F9 version mismatch against F10")
    if quality.version != tracking.source_shot_quality_version:
        raise SmartReframingError("F9 version mismatch against F11")
    if quality.quality_hash != moment.source_shot_quality_hash:
        raise SmartReframingError("F9 quality hash mismatch against F10")
    if quality.quality_hash != tracking.source_shot_quality_hash:
        raise SmartReframingError("F9 quality hash mismatch against F11")

    if moment.version != tracking.source_best_moment_version:
        raise SmartReframingError("F10 version mismatch against F11")
    if moment.best_moment_hash != tracking.source_best_moment_hash:
        raise SmartReframingError("F10 Best Moment hash mismatch against F11")

    if not (
        base.scene_count
        == graph.node_count
        == quality.scene_count
        == moment.scene_count
        == tracking.scene_count
    ):
        raise SmartReframingError(
            "scene count mismatch across F6/F8/F9/F10/F11"
        )

    numbers = (
        [scene.scene_number for scene in base.scenes],
        [scene.scene_number for scene in graph.nodes],
        [scene.scene_number for scene in quality.scenes],
        [scene.scene_number for scene in moment.scenes],
        [scene.scene_number for scene in tracking.scenes],
    )
    if not all(values == numbers[0] for values in numbers[1:]):
        raise SmartReframingError(
            "scene order mismatch across F6/F8/F9/F10/F11"
        )

    for base_scene, quality_scene, moment_scene, tracking_scene in zip(
        base.scenes,
        quality.scenes,
        moment.scenes,
        tracking.scenes,
    ):
        number = base_scene.scene_number

        if base_scene.selected_media_id != quality_scene.selected_media_id:
            raise SmartReframingError(
                f"material identity mismatch F6/F9 scene {number}"
            )
        if base_scene.selected_media_id != moment_scene.selected_media_id:
            raise SmartReframingError(
                f"material identity mismatch F6/F10 scene {number}"
            )
        if base_scene.selected_media_id != tracking_scene.selected_media_id:
            raise SmartReframingError(
                f"material identity mismatch F6/F11 scene {number}"
            )

        if base_scene.source_path != quality_scene.source_path:
            raise SmartReframingError(
                f"source path mismatch F6/F9 scene {number}"
            )
        if base_scene.source_path != moment_scene.source_path:
            raise SmartReframingError(
                f"source path mismatch F6/F10 scene {number}"
            )
        if base_scene.source_path != tracking_scene.source_path:
            raise SmartReframingError(
                f"source path mismatch F6/F11 scene {number}"
            )


def _effective_dimensions(scene) -> tuple[int, int]:
    width = int(scene.source_width)
    height = int(scene.source_height)

    if width <= 0 or height <= 0:
        raise SmartReframingError(
            f"scene {scene.scene_number} has invalid source dimensions"
        )

    if int(scene.source_rotation_deg) % 180:
        width, height = height, width

    return width, height


def _cover_geometry(
    *,
    source_width: int,
    source_height: int,
    target_width: int,
    target_height: int,
) -> CropGeometry:
    source_aspect = source_width / source_height
    target_aspect = target_width / target_height

    if source_aspect > target_aspect:
        crop_height = 1.0
        crop_width = target_aspect / source_aspect
    elif source_aspect < target_aspect:
        crop_width = 1.0
        crop_height = source_aspect / target_aspect
    else:
        crop_width = 1.0
        crop_height = 1.0

    return CropGeometry(
        crop_width_norm=round(crop_width, 9),
        crop_height_norm=round(crop_height, 9),
        target_aspect_ratio=round(target_aspect, 9),
    )


def _composition_target(
    composition: CompositionIntent,
) -> tuple[float, float]:
    # Output-frame target for the tracked subject center.
    # Vertical bias leaves useful room for landscape/context and social UI.
    targets = {
        CompositionIntent.LAYERED_WIDE: (0.50, 0.38),
        CompositionIntent.BALANCED_OBSERVATION: (0.50, 0.45),
        CompositionIntent.SUBJECT_DOMINANT: (0.50, 0.50),
        CompositionIntent.GUIDED_FOLLOW: (0.50, 0.45),
        CompositionIntent.INFORMATIONAL_CLEAN: (0.50, 0.42),
    }
    return targets[composition]


def _clamp_focal(
    focal_x: float,
    focal_y: float,
    geometry: CropGeometry,
) -> tuple[float, float]:
    half_w = geometry.crop_width_norm / 2.0
    half_h = geometry.crop_height_norm / 2.0

    min_x = half_w
    max_x = 1.0 - half_w
    min_y = half_h
    max_y = 1.0 - half_h

    return (
        round(max(min_x, min(max_x, focal_x)), 9),
        round(max(min_y, min(max_y, focal_y)), 9),
    )


def _subject_to_focal(
    *,
    subject_x: float,
    subject_y: float,
    geometry: CropGeometry,
    composition: CompositionIntent,
) -> tuple[float, float]:
    target_x, target_y = _composition_target(composition)

    focal_x = (
        subject_x
        - (target_x - 0.5) * geometry.crop_width_norm
    )
    focal_y = (
        subject_y
        - (target_y - 0.5) * geometry.crop_height_norm
    )

    return _clamp_focal(
        focal_x,
        focal_y,
        geometry,
    )


def _crop_origin(
    *,
    focal_x: float,
    focal_y: float,
    geometry: CropGeometry,
) -> tuple[float, float]:
    x = focal_x - geometry.crop_width_norm / 2.0
    y = focal_y - geometry.crop_height_norm / 2.0

    max_x = 1.0 - geometry.crop_width_norm
    max_y = 1.0 - geometry.crop_height_norm

    return (
        round(max(0.0, min(max_x, x)), 9),
        round(max(0.0, min(max_y, y)), 9),
    )


def _pace_alpha(pace: CinematicPace) -> float:
    return {
        CinematicPace.MEDITATIVE: 0.20,
        CinematicPace.MEASURED: 0.30,
        CinematicPace.ACCELERATING: 0.42,
        CinematicPace.PEAK: 0.52,
        CinematicPace.RELEASE: 0.30,
        CinematicPace.CONTEMPLATIVE: 0.20,
    }[pace]


def _bounded_step(
    previous: float,
    desired: float,
    max_delta: float,
) -> float:
    delta = desired - previous
    if delta > max_delta:
        return previous + max_delta
    if delta < -max_delta:
        return previous - max_delta
    return desired


def _dynamic_keyframes(
    *,
    tracking_scene,
    graph_node,
    geometry: CropGeometry,
    dead_zone_fraction: float,
    max_pan_speed_per_s: float,
) -> list[ReframeKeyframe]:
    points = list(tracking_scene.points)
    if not points:
        raise SmartReframingError(
            f"scene {tracking_scene.scene_number} has no tracking points"
        )

    timestamps = [float(point.timestamp_s) for point in points]
    if timestamps != sorted(timestamps):
        raise SmartReframingError("F11 tracking timestamps must be sorted")
    if len(timestamps) != len(set(timestamps)):
        raise SmartReframingError("F11 tracking timestamps must be unique")

    alpha = _pace_alpha(graph_node.pace)
    dead_x = geometry.crop_width_norm * dead_zone_fraction
    dead_y = geometry.crop_height_norm * dead_zone_fraction

    result: list[ReframeKeyframe] = []
    previous_x = None
    previous_y = None
    previous_t = None

    for point in points:
        raw_x, raw_y = _subject_to_focal(
            subject_x=float(point.center_x),
            subject_y=float(point.center_y),
            geometry=geometry,
            composition=graph_node.composition_intent,
        )

        timestamp = float(point.timestamp_s)

        if previous_x is None:
            focal_x, focal_y = raw_x, raw_y
        else:
            if (
                abs(raw_x - previous_x) <= dead_x
                and abs(raw_y - previous_y) <= dead_y
            ):
                smoothed_x = previous_x
                smoothed_y = previous_y
            else:
                smoothed_x = previous_x + alpha * (raw_x - previous_x)
                smoothed_y = previous_y + alpha * (raw_y - previous_y)

            dt = max(0.0, timestamp - float(previous_t))
            max_delta = max_pan_speed_per_s * dt

            focal_x = _bounded_step(
                previous_x,
                smoothed_x,
                max_delta,
            )
            focal_y = _bounded_step(
                previous_y,
                smoothed_y,
                max_delta,
            )

            focal_x, focal_y = _clamp_focal(
                focal_x,
                focal_y,
                geometry,
            )

        crop_x, crop_y = _crop_origin(
            focal_x=focal_x,
            focal_y=focal_y,
            geometry=geometry,
        )

        result.append(
            ReframeKeyframe(
                timestamp_s=round(timestamp, 6),
                subject_x=round(float(point.center_x), 6),
                subject_y=round(float(point.center_y), 6),
                focal_x=round(float(focal_x), 9),
                focal_y=round(float(focal_y), 9),
                crop_x=crop_x,
                crop_y=crop_y,
                crop_width=geometry.crop_width_norm,
                crop_height=geometry.crop_height_norm,
                focal_source=FocalSource.F11_TRACKING,
            )
        )

        previous_x = float(focal_x)
        previous_y = float(focal_y)
        previous_t = timestamp

    return result


def _static_keyframe(
    *,
    timestamp_s: float,
    focal_x: float,
    focal_y: float,
    geometry: CropGeometry,
    source: FocalSource,
) -> ReframeKeyframe:
    focal_x, focal_y = _clamp_focal(
        focal_x,
        focal_y,
        geometry,
    )
    crop_x, crop_y = _crop_origin(
        focal_x=focal_x,
        focal_y=focal_y,
        geometry=geometry,
    )

    return ReframeKeyframe(
        timestamp_s=round(max(0.0, timestamp_s), 6),
        focal_x=focal_x,
        focal_y=focal_y,
        crop_x=crop_x,
        crop_y=crop_y,
        crop_width=geometry.crop_width_norm,
        crop_height=geometry.crop_height_norm,
        focal_source=source,
    )


class SmartReframingPlanner:
    """F12 deterministic Smart Reframing planner.

    Priority:
      1. F11 object trajectory.
      2. SmartFocal V0.1 decision, respecting its canonical fallback contract.
      3. F6 focal coordinates.

    F12 creates crop/keyframe decisions only. It does not render.
    """

    version = SMART_REFRAMING_VERSION

    def build(
        self,
        request: SmartReframingRequest,
    ) -> SmartReframingPlan:
        _validate_alignment(request)

        if request.target_width != 1080 or request.target_height != 1920:
            raise SmartReframingError(
                "F12 V0.1 only supports canonical 1080x1920"
            )

        base = request.video_base
        graph = request.story_graph
        quality = request.shot_quality
        moment = request.best_moment
        tracking = request.tracking

        graph_by_number = {
            node.scene_number: node for node in graph.nodes
        }
        moment_by_number = {
            scene.scene_number: scene for scene in moment.scenes
        }
        tracking_by_number = {
            scene.scene_number: scene for scene in tracking.scenes
        }
        hints = {
            hint.scene_number: hint
            for hint in request.smartfocal_hints
        }

        known_numbers = {scene.scene_number for scene in base.scenes}
        unknown_hints = sorted(set(hints) - known_numbers)
        if unknown_hints:
            raise SmartReframingError(
                "SmartFocal hint references unknown scene(s): "
                + ", ".join(str(value) for value in unknown_hints)
            )

        scenes: list[ReframingScenePlan] = []
        accepted = 0
        rejected = 0

        for scene in base.scenes:
            number = scene.scene_number
            node = graph_by_number[number]
            moment_scene = moment_by_number[number]
            tracking_scene = tracking_by_number[number]
            hint = hints.get(number)

            common = dict(
                scene_number=number,
                node_id=node.node_id,
                selected_media_id=scene.selected_media_id,
                media_type=scene.media_type,
                source_path=scene.source_path,
                fit_mode=scene.fit_mode,
                composition_intent=node.composition_intent,
                motion_intent=node.motion_intent,
                source_width=scene.source_width,
                source_height=scene.source_height,
                source_rotation_deg=scene.source_rotation_deg,
            )

            if scene.placeholder:
                if hint is not None:
                    raise SmartReframingError(
                        f"placeholder scene {number} cannot accept SmartFocal hint"
                    )
                scenes.append(
                    ReframingScenePlan(
                        **common,
                        status=ReframingSceneStatus.PLACEHOLDER_NOT_APPLICABLE,
                        focal_source=FocalSource.NONE,
                        execution_ready=False,
                        review_required=False,
                        warnings=["PLACEHOLDER_HAS_NO_REFRAMABLE_SOURCE"],
                    )
                )
                continue

            if scene.fit_mode == VideoFitMode.fit:
                scenes.append(
                    ReframingScenePlan(
                        **common,
                        status=ReframingSceneStatus.FIT_PASSTHROUGH,
                        focal_source=FocalSource.NONE,
                        execution_ready=True,
                        review_required=False,
                        warnings=["FIT_MODE_PRESERVED_NO_CROP_REQUIRED"],
                    )
                )
                continue

            source_width, source_height = _effective_dimensions(scene)
            geometry = _cover_geometry(
                source_width=source_width,
                source_height=source_height,
                target_width=request.target_width,
                target_height=request.target_height,
            )

            rotation_warning = (
                ["SOURCE_ROTATION_REQUIRES_RENDERER_REVIEW"]
                if int(scene.source_rotation_deg) % 360 != 0
                else []
            )

            if tracking_scene.status in {
                TrackingSceneStatus.TRACKED,
                TrackingSceneStatus.TRACKED_PARTIAL,
            }:
                if moment_scene.status != BestMomentStatus.SELECTED:
                    raise SmartReframingError(
                        f"tracked scene {number} lacks selected F10 window"
                    )
                if (
                    tracking_scene.window_start_s
                    != moment_scene.selected_start_s
                    or tracking_scene.window_end_s
                    != moment_scene.selected_end_s
                ):
                    raise SmartReframingError(
                        f"F11/F10 window mismatch at scene {number}"
                    )

                keyframes = _dynamic_keyframes(
                    tracking_scene=tracking_scene,
                    graph_node=node,
                    geometry=geometry,
                    dead_zone_fraction=request.dead_zone_fraction,
                    max_pan_speed_per_s=request.max_pan_speed_per_s,
                )

                partial = (
                    tracking_scene.status
                    == TrackingSceneStatus.TRACKED_PARTIAL
                )
                review = partial or bool(rotation_warning)

                warnings = list(rotation_warning)
                if hint is not None:
                    warnings.append(
                        "SMARTFOCAL_HINT_SUPERSEDED_BY_F11_TRACKING"
                    )
                if partial:
                    warnings.append(
                        "PARTIAL_TRACK_NOT_EXECUTION_READY"
                    )

                scenes.append(
                    ReframingScenePlan(
                        **common,
                        status=(
                            ReframingSceneStatus.DYNAMIC_TRACKING_PARTIAL
                            if partial
                            else ReframingSceneStatus.DYNAMIC_TRACKING
                        ),
                        focal_source=FocalSource.F11_TRACKING,
                        execution_ready=not review,
                        review_required=review,
                        window_start_s=moment_scene.selected_start_s,
                        window_end_s=moment_scene.selected_end_s,
                        crop_geometry=geometry,
                        keyframes=keyframes,
                        warnings=warnings,
                    )
                )
                continue

            if hint is not None:
                decision = FocalDecision(
                    focal_x=hint.focal_x,
                    focal_y=hint.focal_y,
                    confidence=hint.confidence,
                    method=hint.method,
                )
                apply_smart = _smartfocal_decision_is_informative(decision)

                if apply_smart:
                    accepted += 1
                    focal_x = hint.focal_x
                    focal_y = hint.focal_y
                    status = ReframingSceneStatus.STATIC_SMARTFOCAL
                    source = FocalSource.SMARTFOCAL_V01
                    warnings = list(rotation_warning)
                else:
                    rejected += 1
                    focal_x = 0.5
                    focal_y = 0.5
                    status = ReframingSceneStatus.STATIC_SAFE_CENTER
                    source = FocalSource.SMARTFOCAL_SAFE_CENTER
                    warnings = [
                        *rotation_warning,
                        "SMARTFOCAL_SAFETY_GATE_REJECTED_DECISION",
                    ]

                timestamp = (
                    float(moment_scene.selected_start_s)
                    if moment_scene.status == BestMomentStatus.SELECTED
                    and moment_scene.selected_start_s is not None
                    else float(scene.source_start_s)
                )

                review = bool(rotation_warning)

                scenes.append(
                    ReframingScenePlan(
                        **common,
                        status=status,
                        focal_source=source,
                        execution_ready=not review,
                        review_required=review,
                        window_start_s=(
                            moment_scene.selected_start_s
                            if moment_scene.status == BestMomentStatus.SELECTED
                            else None
                        ),
                        window_end_s=(
                            moment_scene.selected_end_s
                            if moment_scene.status == BestMomentStatus.SELECTED
                            else None
                        ),
                        smartfocal_confidence=hint.confidence,
                        smartfocal_method=hint.method,
                        crop_geometry=geometry,
                        keyframes=[
                            _static_keyframe(
                                timestamp_s=timestamp,
                                focal_x=focal_x,
                                focal_y=focal_y,
                                geometry=geometry,
                                source=source,
                            )
                        ],
                        warnings=warnings,
                    )
                )
                continue

            timestamp = (
                float(moment_scene.selected_start_s)
                if moment_scene.status == BestMomentStatus.SELECTED
                and moment_scene.selected_start_s is not None
                else float(scene.source_start_s)
            )

            review = bool(rotation_warning)

            scenes.append(
                ReframingScenePlan(
                    **common,
                    status=ReframingSceneStatus.STATIC_F6_FOCAL,
                    focal_source=FocalSource.F6_FOCAL,
                    execution_ready=not review,
                    review_required=review,
                    window_start_s=(
                        moment_scene.selected_start_s
                        if moment_scene.status == BestMomentStatus.SELECTED
                        else None
                    ),
                    window_end_s=(
                        moment_scene.selected_end_s
                        if moment_scene.status == BestMomentStatus.SELECTED
                        else None
                    ),
                    crop_geometry=geometry,
                    keyframes=[
                        _static_keyframe(
                            timestamp_s=timestamp,
                            focal_x=scene.focal_x,
                            focal_y=scene.focal_y,
                            geometry=geometry,
                            source=FocalSource.F6_FOCAL,
                        )
                    ],
                    warnings=[
                        *rotation_warning,
                        "NO_F11_TRACK_OR_SMARTFOCAL_HINT_USING_F6_FOCAL",
                    ],
                )
            )

        def count(status):
            return sum(scene.status == status for scene in scenes)

        stable_payload = {
            "version": self.version,
            "source_plan_context_hash": base.source_plan_context_hash,
            "source_story_graph_hash": graph.graph_hash,
            "source_shot_quality_hash": quality.quality_hash,
            "source_best_moment_hash": moment.best_moment_hash,
            "source_tracking_hash": tracking.tracking_hash,
            "target_width": request.target_width,
            "target_height": request.target_height,
            "dead_zone_fraction": request.dead_zone_fraction,
            "max_pan_speed_per_s": request.max_pan_speed_per_s,
            "smartfocal_hints": [
                hint.model_dump(mode="json")
                for hint in request.smartfocal_hints
            ],
            "scenes": [
                scene.model_dump(mode="json")
                for scene in scenes
            ],
        }

        return SmartReframingPlan(
            subject=base.subject,
            source_plan_context_hash=base.source_plan_context_hash,
            source_video_base_version=base.version,
            source_story_graph_version=graph.version,
            source_story_graph_hash=graph.graph_hash,
            source_shot_quality_version=quality.version,
            source_shot_quality_hash=quality.quality_hash,
            source_best_moment_version=moment.version,
            source_best_moment_hash=moment.best_moment_hash,
            source_tracking_version=tracking.version,
            source_tracking_hash=tracking.tracking_hash,
            scene_count=len(scenes),
            placeholder_count=count(
                ReframingSceneStatus.PLACEHOLDER_NOT_APPLICABLE
            ),
            fit_passthrough_count=count(
                ReframingSceneStatus.FIT_PASSTHROUGH
            ),
            dynamic_tracking_count=count(
                ReframingSceneStatus.DYNAMIC_TRACKING
            ),
            dynamic_partial_count=count(
                ReframingSceneStatus.DYNAMIC_TRACKING_PARTIAL
            ),
            static_smartfocal_count=count(
                ReframingSceneStatus.STATIC_SMARTFOCAL
            ),
            static_safe_center_count=count(
                ReframingSceneStatus.STATIC_SAFE_CENTER
            ),
            static_f6_focal_count=count(
                ReframingSceneStatus.STATIC_F6_FOCAL
            ),
            smartfocal_hint_count=len(request.smartfocal_hints),
            smartfocal_accepted_count=accepted,
            smartfocal_rejected_count=rejected,
            execution_ready_count=sum(
                scene.execution_ready for scene in scenes
            ),
            review_required_count=sum(
                scene.review_required for scene in scenes
            ),
            keyframe_count=sum(len(scene.keyframes) for scene in scenes),
            scenes=scenes,
            structural_checks=ReframingStructuralChecks(
                source_alignment=True,
                graph_hash_preserved=True,
                quality_hash_preserved=True,
                best_moment_hash_preserved=True,
                tracking_hash_preserved=True,
                material_identity_preserved=True,
                fit_mode_preserved=True,
                best_moment_window_preserved=True,
                smartfocal_fallback_contract_used=True,
                no_tracking_reexecution=True,
            ),
            reframing_hash=_hash_json(stable_payload),
            generated_at_utc=datetime.now(timezone.utc),
        )
