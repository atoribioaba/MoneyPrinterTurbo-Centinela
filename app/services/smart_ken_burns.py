from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from app.models.astromedia import MediaType
from app.models.cinematic_director import (
    CinematicPace,
    CompositionIntent,
    MotionIntent,
)
from app.models.schema import VideoFitMode
from app.models.smart_ken_burns import (
    SMART_KEN_BURNS_VERSION,
    KenBurnsKeyframe,
    KenBurnsMotionType,
    KenBurnsScenePlan,
    KenBurnsSceneStatus,
    KenBurnsStructuralChecks,
    SmartKenBurnsPlan,
    SmartKenBurnsRequest,
)
from app.models.smart_reframing import (
    ReframingSceneStatus,
)


class SmartKenBurnsError(RuntimeError):
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


def _validate_alignment(request: SmartKenBurnsRequest) -> None:
    base = request.video_base
    graph = request.story_graph
    reframing = request.reframing

    if not (
        base.source_plan_context_hash
        == graph.source_plan_context_hash
        == reframing.source_plan_context_hash
    ):
        raise SmartKenBurnsError(
            "context hash mismatch across F6/F8/F12"
        )

    if base.version != graph.source_video_base_version:
        raise SmartKenBurnsError("F6 version mismatch against F8")
    if base.version != reframing.source_video_base_version:
        raise SmartKenBurnsError("F6 version mismatch against F12")

    if graph.version != reframing.source_story_graph_version:
        raise SmartKenBurnsError("F8 version mismatch against F12")
    if graph.graph_hash != reframing.source_story_graph_hash:
        raise SmartKenBurnsError("F8 graph hash mismatch against F12")

    if (
        base.output_width != reframing.target_width
        or base.output_height != reframing.target_height
    ):
        raise SmartKenBurnsError(
            "F6/F12 target geometry mismatch"
        )

    if not (
        base.scene_count
        == graph.node_count
        == reframing.scene_count
    ):
        raise SmartKenBurnsError(
            "scene count mismatch across F6/F8/F12"
        )

    base_numbers = [scene.scene_number for scene in base.scenes]
    graph_numbers = [scene.scene_number for scene in graph.nodes]
    reframing_numbers = [
        scene.scene_number for scene in reframing.scenes
    ]

    if not (
        base_numbers
        == graph_numbers
        == reframing_numbers
    ):
        raise SmartKenBurnsError(
            "scene order mismatch across F6/F8/F12"
        )

    for base_scene, reframe_scene in zip(
        base.scenes,
        reframing.scenes,
    ):
        number = base_scene.scene_number

        if (
            base_scene.selected_media_id
            != reframe_scene.selected_media_id
        ):
            raise SmartKenBurnsError(
                f"material identity mismatch F6/F12 scene {number}"
            )

        if base_scene.source_path != reframe_scene.source_path:
            raise SmartKenBurnsError(
                f"source path mismatch F6/F12 scene {number}"
            )

        if base_scene.fit_mode != reframe_scene.fit_mode:
            raise SmartKenBurnsError(
                f"fit mode mismatch F6/F12 scene {number}"
            )


def _pace_zoom_base(pace: CinematicPace) -> float:
    return {
        CinematicPace.MEDITATIVE: 0.030,
        CinematicPace.MEASURED: 0.040,
        CinematicPace.ACCELERATING: 0.055,
        CinematicPace.PEAK: 0.070,
        CinematicPace.RELEASE: 0.040,
        CinematicPace.CONTEMPLATIVE: 0.028,
    }[pace]


def _zoom_delta(
    *,
    pace: CinematicPace,
    intensity: float,
    maximum: float,
) -> float:
    value = _pace_zoom_base(pace) + 0.015 * float(intensity)
    return round(min(maximum, value), 6)


def _clamp_center(
    *,
    focal_x: float,
    focal_y: float,
    crop_width: float,
    crop_height: float,
) -> tuple[float, float]:
    half_w = crop_width / 2.0
    half_h = crop_height / 2.0

    return (
        max(half_w, min(1.0 - half_w, focal_x)),
        max(half_h, min(1.0 - half_h, focal_y)),
    )


def _crop_from_center(
    *,
    focal_x: float,
    focal_y: float,
    crop_width: float,
    crop_height: float,
) -> tuple[float, float, float, float]:
    focal_x, focal_y = _clamp_center(
        focal_x=focal_x,
        focal_y=focal_y,
        crop_width=crop_width,
        crop_height=crop_height,
    )

    crop_x = focal_x - crop_width / 2.0
    crop_y = focal_y - crop_height / 2.0

    return (
        round(max(0.0, min(1.0 - crop_width, crop_x)), 9),
        round(max(0.0, min(1.0 - crop_height, crop_y)), 9),
        round(focal_x, 9),
        round(focal_y, 9),
    )


def _zoomed_geometry(
    *,
    base_width: float,
    base_height: float,
    zoom_factor: float,
) -> tuple[float, float]:
    return (
        round(base_width / zoom_factor, 9),
        round(base_height / zoom_factor, 9),
    )


def _keyframe(
    *,
    timestamp_s: float,
    focal_x: float,
    focal_y: float,
    crop_width: float,
    crop_height: float,
    base_width: float,
) -> KenBurnsKeyframe:
    crop_x, crop_y, focal_x, focal_y = _crop_from_center(
        focal_x=focal_x,
        focal_y=focal_y,
        crop_width=crop_width,
        crop_height=crop_height,
    )

    zoom_factor = round(base_width / crop_width, 9)

    return KenBurnsKeyframe(
        timestamp_s=round(timestamp_s, 6),
        crop_x=crop_x,
        crop_y=crop_y,
        crop_width=round(crop_width, 9),
        crop_height=round(crop_height, 9),
        focal_x=focal_x,
        focal_y=focal_y,
        zoom_factor=zoom_factor,
    )


def _hold_keyframes(
    *,
    duration: float,
    focal_x: float,
    focal_y: float,
    crop_width: float,
    crop_height: float,
) -> list[KenBurnsKeyframe]:
    start = _keyframe(
        timestamp_s=0.0,
        focal_x=focal_x,
        focal_y=focal_y,
        crop_width=crop_width,
        crop_height=crop_height,
        base_width=crop_width,
    )
    end = start.model_copy(
        update={"timestamp_s": round(duration, 6)}
    )
    return [start, end]


def _push_in_keyframes(
    *,
    duration: float,
    focal_x: float,
    focal_y: float,
    crop_width: float,
    crop_height: float,
    zoom_delta: float,
) -> list[KenBurnsKeyframe]:
    zoom_factor = 1.0 + zoom_delta
    end_w, end_h = _zoomed_geometry(
        base_width=crop_width,
        base_height=crop_height,
        zoom_factor=zoom_factor,
    )

    return [
        _keyframe(
            timestamp_s=0.0,
            focal_x=focal_x,
            focal_y=focal_y,
            crop_width=crop_width,
            crop_height=crop_height,
            base_width=crop_width,
        ),
        _keyframe(
            timestamp_s=duration,
            focal_x=focal_x,
            focal_y=focal_y,
            crop_width=end_w,
            crop_height=end_h,
            base_width=crop_width,
        ),
    ]


def _pull_back_keyframes(
    *,
    duration: float,
    focal_x: float,
    focal_y: float,
    crop_width: float,
    crop_height: float,
    zoom_delta: float,
) -> list[KenBurnsKeyframe]:
    zoom_factor = 1.0 + zoom_delta
    start_w, start_h = _zoomed_geometry(
        base_width=crop_width,
        base_height=crop_height,
        zoom_factor=zoom_factor,
    )

    return [
        _keyframe(
            timestamp_s=0.0,
            focal_x=focal_x,
            focal_y=focal_y,
            crop_width=start_w,
            crop_height=start_h,
            base_width=crop_width,
        ),
        _keyframe(
            timestamp_s=duration,
            focal_x=focal_x,
            focal_y=focal_y,
            crop_width=crop_width,
            crop_height=crop_height,
            base_width=crop_width,
        ),
    ]


def _reveal_start_focal(
    *,
    focal_x: float,
    focal_y: float,
    composition: CompositionIntent,
    pan_fraction: float,
) -> tuple[float, float]:
    # Start with additional context opposite the final focal point.
    # If the focal is centered, use composition to choose a vertical reveal.
    if abs(focal_x - 0.5) > 0.04:
        direction = -1.0 if focal_x > 0.5 else 1.0
        return focal_x + direction * pan_fraction, focal_y

    if composition == CompositionIntent.LAYERED_WIDE:
        return focal_x, focal_y + pan_fraction

    if composition == CompositionIntent.SUBJECT_DOMINANT:
        return focal_x, focal_y - pan_fraction

    if focal_y < 0.5:
        return focal_x, focal_y + pan_fraction

    return focal_x, focal_y - pan_fraction


def _controlled_reveal_keyframes(
    *,
    duration: float,
    focal_x: float,
    focal_y: float,
    crop_width: float,
    crop_height: float,
    zoom_delta: float,
    composition: CompositionIntent,
    pan_fraction: float,
) -> list[KenBurnsKeyframe]:
    start_x, start_y = _reveal_start_focal(
        focal_x=focal_x,
        focal_y=focal_y,
        composition=composition,
        pan_fraction=pan_fraction,
    )

    start_zoom = 1.0 + zoom_delta * 0.65
    start_w, start_h = _zoomed_geometry(
        base_width=crop_width,
        base_height=crop_height,
        zoom_factor=start_zoom,
    )

    return [
        _keyframe(
            timestamp_s=0.0,
            focal_x=start_x,
            focal_y=start_y,
            crop_width=start_w,
            crop_height=start_h,
            base_width=crop_width,
        ),
        _keyframe(
            timestamp_s=duration,
            focal_x=focal_x,
            focal_y=focal_y,
            crop_width=crop_width,
            crop_height=crop_height,
            base_width=crop_width,
        ),
    ]


def _status_for_motion(
    motion: MotionIntent,
) -> tuple[KenBurnsSceneStatus, KenBurnsMotionType]:
    if motion == MotionIntent.VERY_SLOW_PUSH:
        return (
            KenBurnsSceneStatus.PUSH_IN_PLANNED,
            KenBurnsMotionType.PUSH_IN,
        )

    if motion == MotionIntent.GENTLE_PULL_BACK:
        return (
            KenBurnsSceneStatus.PULL_BACK_PLANNED,
            KenBurnsMotionType.PULL_BACK,
        )

    if motion == MotionIntent.CONTROLLED_REVEAL:
        return (
            KenBurnsSceneStatus.CONTROLLED_REVEAL_PLANNED,
            KenBurnsMotionType.CONTROLLED_REVEAL,
        )

    return (
        KenBurnsSceneStatus.STATIC_HOLD,
        KenBurnsMotionType.HOLD,
    )


class SmartKenBurnsPlanner:
    version = SMART_KEN_BURNS_VERSION

    def build(
        self,
        request: SmartKenBurnsRequest,
    ) -> SmartKenBurnsPlan:
        _validate_alignment(request)

        base = request.video_base
        graph = request.story_graph
        reframing = request.reframing

        graph_by_number = {
            node.scene_number: node for node in graph.nodes
        }
        reframe_by_number = {
            scene.scene_number: scene for scene in reframing.scenes
        }

        scenes: list[KenBurnsScenePlan] = []

        for base_scene in base.scenes:
            number = base_scene.scene_number
            node = graph_by_number[number]
            reframe = reframe_by_number[number]

            common = dict(
                scene_number=number,
                node_id=node.node_id,
                selected_media_id=base_scene.selected_media_id,
                media_type=base_scene.media_type,
                source_path=base_scene.source_path,
                duration_seconds=base_scene.duration_seconds,
                fit_mode=base_scene.fit_mode,
                pace=node.pace,
                intensity=node.intensity,
                composition_intent=node.composition_intent,
                motion_intent=node.motion_intent,
            )

            if base_scene.placeholder:
                scenes.append(
                    KenBurnsScenePlan(
                        **common,
                        status=(
                            KenBurnsSceneStatus.PLACEHOLDER_NOT_APPLICABLE
                        ),
                        motion_type=KenBurnsMotionType.HOLD,
                        execution_ready=False,
                        review_required=False,
                        warnings=["PLACEHOLDER_HAS_NO_STATIC_IMAGE"],
                    )
                )
                continue

            if base_scene.media_type == MediaType.VIDEO:
                scenes.append(
                    KenBurnsScenePlan(
                        **common,
                        status=KenBurnsSceneStatus.VIDEO_NOT_APPLICABLE,
                        motion_type=KenBurnsMotionType.HOLD,
                        execution_ready=True,
                        review_required=False,
                        warnings=[
                            "F13_DOES_NOT_ANIMATE_VIDEO",
                            "VIDEO_MOTION_OWNED_BY_SOURCE_F11_F12",
                        ],
                    )
                )
                continue

            if base_scene.media_type != MediaType.IMAGE:
                raise SmartKenBurnsError(
                    f"unsupported media type scene {number}: "
                    f"{base_scene.media_type}"
                )

            if reframe.review_required:
                scenes.append(
                    KenBurnsScenePlan(
                        **common,
                        status=(
                            KenBurnsSceneStatus.REFRAMING_REVIEW_REQUIRED
                        ),
                        motion_type=KenBurnsMotionType.HOLD,
                        execution_ready=False,
                        review_required=True,
                        warnings=[
                            "F12_REFRAMING_REQUIRES_REVIEW_BEFORE_F13"
                        ],
                    )
                )
                continue

            if base_scene.fit_mode == VideoFitMode.fit:
                if (
                    reframe.status
                    != ReframingSceneStatus.FIT_PASSTHROUGH
                ):
                    raise SmartKenBurnsError(
                        f"FIT scene {number} must remain F12 passthrough"
                    )

                scenes.append(
                    KenBurnsScenePlan(
                        **common,
                        status=KenBurnsSceneStatus.FIT_STATIC_HOLD,
                        motion_type=KenBurnsMotionType.HOLD,
                        execution_ready=True,
                        review_required=False,
                        warnings=[
                            "FIT_MODE_PRESERVED",
                            "F13_WILL_NOT_CREATE_CROP_TO_FORCE_KEN_BURNS",
                        ],
                    )
                )
                continue

            if base_scene.fit_mode != VideoFitMode.cover:
                raise SmartKenBurnsError(
                    f"unsupported fit mode scene {number}: "
                    f"{base_scene.fit_mode}"
                )

            allowed_static = {
                ReframingSceneStatus.STATIC_SMARTFOCAL,
                ReframingSceneStatus.STATIC_SAFE_CENTER,
                ReframingSceneStatus.STATIC_F6_FOCAL,
            }
            if reframe.status not in allowed_static:
                raise SmartKenBurnsError(
                    f"image COVER scene {number} requires static F12 crop, "
                    f"got {reframe.status}"
                )

            if len(reframe.keyframes) != 1:
                raise SmartKenBurnsError(
                    f"image static F12 scene {number} must have one keyframe"
                )

            base_key = reframe.keyframes[0]
            crop_w = float(base_key.crop_width)
            crop_h = float(base_key.crop_height)
            focal_x = float(base_key.focal_x)
            focal_y = float(base_key.focal_y)

            status, motion_type = _status_for_motion(
                node.motion_intent
            )

            if motion_type == KenBurnsMotionType.HOLD:
                keyframes = _hold_keyframes(
                    duration=base_scene.duration_seconds,
                    focal_x=focal_x,
                    focal_y=focal_y,
                    crop_width=crop_w,
                    crop_height=crop_h,
                )
                zoom_delta = 0.0
                warnings = []

                if node.motion_intent == MotionIntent.NATURAL_MOTION_ONLY:
                    warnings.append(
                        "STATIC_IMAGE_HAS_NO_NATURAL_MOTION_HOLD_PRESERVED"
                    )
                elif node.motion_intent == MotionIntent.OBSERVE_LOCKED:
                    warnings.append("OBSERVE_LOCKED_HOLD_PRESERVED")

            else:
                zoom_delta = _zoom_delta(
                    pace=node.pace,
                    intensity=node.intensity,
                    maximum=request.max_zoom_delta,
                )

                if motion_type == KenBurnsMotionType.PUSH_IN:
                    keyframes = _push_in_keyframes(
                        duration=base_scene.duration_seconds,
                        focal_x=focal_x,
                        focal_y=focal_y,
                        crop_width=crop_w,
                        crop_height=crop_h,
                        zoom_delta=zoom_delta,
                    )
                elif motion_type == KenBurnsMotionType.PULL_BACK:
                    keyframes = _pull_back_keyframes(
                        duration=base_scene.duration_seconds,
                        focal_x=focal_x,
                        focal_y=focal_y,
                        crop_width=crop_w,
                        crop_height=crop_h,
                        zoom_delta=zoom_delta,
                    )
                else:
                    keyframes = _controlled_reveal_keyframes(
                        duration=base_scene.duration_seconds,
                        focal_x=focal_x,
                        focal_y=focal_y,
                        crop_width=crop_w,
                        crop_height=crop_h,
                        zoom_delta=zoom_delta,
                        composition=node.composition_intent,
                        pan_fraction=request.reveal_pan_fraction,
                    )

                warnings = []

            scenes.append(
                KenBurnsScenePlan(
                    **common,
                    status=status,
                    motion_type=motion_type,
                    execution_ready=True,
                    review_required=False,
                    zoom_delta=zoom_delta,
                    keyframes=keyframes,
                    warnings=warnings,
                )
            )

        def count(status):
            return sum(scene.status == status for scene in scenes)

        stable_payload = {
            "version": self.version,
            "source_plan_context_hash": base.source_plan_context_hash,
            "source_story_graph_hash": graph.graph_hash,
            "source_reframing_hash": reframing.reframing_hash,
            "target_width": reframing.target_width,
            "target_height": reframing.target_height,
            "target_aspect": reframing.target_aspect,
            "max_zoom_delta": request.max_zoom_delta,
            "reveal_pan_fraction": request.reveal_pan_fraction,
            "scenes": [
                scene.model_dump(mode="json")
                for scene in scenes
            ],
        }

        push_count = count(KenBurnsSceneStatus.PUSH_IN_PLANNED)
        pull_count = count(KenBurnsSceneStatus.PULL_BACK_PLANNED)
        reveal_count = count(
            KenBurnsSceneStatus.CONTROLLED_REVEAL_PLANNED
        )

        return SmartKenBurnsPlan(
            subject=base.subject,
            source_plan_context_hash=base.source_plan_context_hash,
            source_video_base_version=base.version,
            source_story_graph_version=graph.version,
            source_story_graph_hash=graph.graph_hash,
            source_reframing_version=reframing.version,
            source_reframing_hash=reframing.reframing_hash,
            target_width=reframing.target_width,
            target_height=reframing.target_height,
            target_aspect=reframing.target_aspect,
            scene_count=len(scenes),
            placeholder_count=count(
                KenBurnsSceneStatus.PLACEHOLDER_NOT_APPLICABLE
            ),
            video_not_applicable_count=count(
                KenBurnsSceneStatus.VIDEO_NOT_APPLICABLE
            ),
            fit_static_hold_count=count(
                KenBurnsSceneStatus.FIT_STATIC_HOLD
            ),
            static_hold_count=count(
                KenBurnsSceneStatus.STATIC_HOLD
            ),
            push_in_count=push_count,
            pull_back_count=pull_count,
            controlled_reveal_count=reveal_count,
            review_required_count=count(
                KenBurnsSceneStatus.REFRAMING_REVIEW_REQUIRED
            ),
            motion_scene_count=(
                push_count + pull_count + reveal_count
            ),
            execution_ready_count=sum(
                scene.execution_ready for scene in scenes
            ),
            keyframe_count=sum(
                len(scene.keyframes) for scene in scenes
            ),
            scenes=scenes,
            structural_checks=KenBurnsStructuralChecks(
                source_alignment=True,
                reframing_hash_preserved=True,
                material_identity_preserved=True,
                fit_mode_preserved=True,
                target_geometry_preserved=True,
                image_only_motion=True,
                no_reframing_reexecution=True,
                no_tracking_reexecution=True,
                no_smartfocal_reexecution=True,
            ),
            ken_burns_hash=_hash_json(stable_payload),
            generated_at_utc=datetime.now(timezone.utc),
        )
