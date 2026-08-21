from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from app.models.astronomy import ScientificStatus
from app.models.astromedia import MediaType, Origin, Provider, Rights
from app.models.cinematic_director import MotionIntent
from app.models.master_image_i2v import (
    MASTER_IMAGE_I2V_VERSION,
    I2VJobSpec,
    I2VMotionProfile,
    I2VScenePlan,
    I2VSceneStatus,
    I2VStructuralChecks,
    MasterImageDescriptor,
    MasterImageI2VPlan,
    MasterImageI2VRequest,
)


class MasterImageI2VError(RuntimeError):
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


def _validate_alignment(request: MasterImageI2VRequest) -> None:
    base = request.video_base
    graph = request.story_graph
    ken = request.ken_burns

    if not (
        base.source_plan_context_hash
        == graph.source_plan_context_hash
        == ken.source_plan_context_hash
    ):
        raise MasterImageI2VError(
            "context hash mismatch across F6/F8/F13"
        )

    if base.version != graph.source_video_base_version:
        raise MasterImageI2VError("F6 version mismatch against F8")
    if base.version != ken.source_video_base_version:
        raise MasterImageI2VError("F6 version mismatch against F13")

    if graph.version != ken.source_story_graph_version:
        raise MasterImageI2VError("F8 version mismatch against F13")
    if graph.graph_hash != ken.source_story_graph_hash:
        raise MasterImageI2VError("F8 graph hash mismatch against F13")

    if (
        base.output_width != ken.target_width
        or base.output_height != ken.target_height
    ):
        raise MasterImageI2VError(
            "F6/F13 delivery geometry mismatch"
        )

    if not (
        base.scene_count
        == graph.node_count
        == ken.scene_count
    ):
        raise MasterImageI2VError(
            "scene count mismatch across F6/F8/F13"
        )

    base_numbers = [scene.scene_number for scene in base.scenes]
    graph_numbers = [node.scene_number for node in graph.nodes]
    ken_numbers = [scene.scene_number for scene in ken.scenes]

    if not (base_numbers == graph_numbers == ken_numbers):
        raise MasterImageI2VError(
            "scene order mismatch across F6/F8/F13"
        )

    for base_scene, ken_scene in zip(base.scenes, ken.scenes):
        number = base_scene.scene_number

        if base_scene.selected_media_id != ken_scene.selected_media_id:
            raise MasterImageI2VError(
                f"material identity mismatch F6/F13 scene {number}"
            )
        if base_scene.source_path != ken_scene.source_path:
            raise MasterImageI2VError(
                f"source path mismatch F6/F13 scene {number}"
            )
        if base_scene.fit_mode != ken_scene.fit_mode:
            raise MasterImageI2VError(
                f"fit mode mismatch F6/F13 scene {number}"
            )


def _origin_hint(provider: Provider) -> Origin:
    if provider == Provider.AI_GENERATED:
        return Origin.AI_GENERATED
    if provider == Provider.OWN_MEDIA:
        return Origin.REAL_OWN
    return Origin.UNKNOWN


def _motion_profile(intent: MotionIntent) -> I2VMotionProfile:
    return {
        MotionIntent.OBSERVE_LOCKED:
            I2VMotionProfile.LOCKED_MICRO_MOTION,
        MotionIntent.NATURAL_MOTION_ONLY:
            I2VMotionProfile.NATURAL_MICRO_MOTION,
        MotionIntent.VERY_SLOW_PUSH:
            I2VMotionProfile.VERY_SLOW_PUSH,
        MotionIntent.CONTROLLED_REVEAL:
            I2VMotionProfile.CONTROLLED_REVEAL,
        MotionIntent.GENTLE_PULL_BACK:
            I2VMotionProfile.GENTLE_PULL_BACK,
    }[intent]


def _motion_directive(intent: MotionIntent) -> str:
    return {
        MotionIntent.OBSERVE_LOCKED:
            (
                "Keep the camera essentially locked. Add only extremely "
                "subtle physically plausible micro-motion or light/atmospheric "
                "variation already implied by the source."
            ),
        MotionIntent.NATURAL_MOTION_ONLY:
            (
                "Use only subtle physically plausible natural motion present "
                "in the scene. Do not invent camera movement."
            ),
        MotionIntent.VERY_SLOW_PUSH:
            (
                "Use a very slow cinematic push-in with minimal amplitude. "
                "Preserve the master image composition and celestial geometry."
            ),
        MotionIntent.CONTROLLED_REVEAL:
            (
                "Use a restrained controlled reveal with gentle motion. "
                "Do not introduce new visual elements."
            ),
        MotionIntent.GENTLE_PULL_BACK:
            (
                "Use a gentle slow pull-back that reveals slightly more "
                "context while preserving the master image."
            ),
    }[intent]


_PRESERVATION_RULES = [
    "Treat the supplied master image as the canonical visual reference.",
    "Preserve celestial-body identity, shape, phase, rings and relative position.",
    "Do not add, remove, duplicate or transform astronomical objects.",
    "Do not invent stars, moons, planets, eclipses or deep-sky structures.",
    "Preserve horizon, landscape silhouettes and major composition anchors.",
    "Avoid morphing, temporal warping, sudden cuts and camera shake.",
    "No text, captions, logos or watermarks inside the generated imagery.",
    "Prefer subtle micro-animation over dramatic synthetic motion.",
]


_NEGATIVE_PROMPT = (
    "extra moon, duplicated moon, extra sun, duplicated planet, altered lunar "
    "phase, deformed planet, distorted rings, invented eclipse, hallucinated "
    "star field, new constellation, added galaxy, morphing celestial body, "
    "melting landscape, warped horizon, fast camera motion, camera shake, "
    "jump cut, aggressive zoom, flicker, temporal instability, text, logo, "
    "watermark"
)


def _positive_prompt(node) -> str:
    objects = ", ".join(node.astronomy_objects)
    object_clause = (
        f"Explicit astronomical subjects: {objects}. "
        if objects
        else ""
    )

    return (
        "Create a restrained cinematic image-to-video micro-animation from "
        "the supplied master image. "
        f"Visual requirement: {node.visual_requirement}. "
        f"{object_clause}"
        f"{_motion_directive(node.motion_intent)} "
        "Preserve scientific-looking visual consistency with the source. "
        "The master image is authoritative: preserve its composition, "
        "celestial geometry, landscape geometry, lighting logic and identity. "
        "Do not create new astronomical features. No scene cut."
    )


def _master_descriptor(scene) -> MasterImageDescriptor:
    if (
        scene.selected_media_id is None
        or scene.source_path is None
        or scene.provider is None
        or scene.rights_status is None
    ):
        raise MasterImageI2VError(
            f"scene {scene.scene_number} lacks master-image metadata"
        )

    if scene.source_width <= 0 or scene.source_height <= 0:
        raise MasterImageI2VError(
            f"scene {scene.scene_number} has invalid master dimensions"
        )

    return MasterImageDescriptor(
        scene_number=scene.scene_number,
        media_id=scene.selected_media_id,
        source_path=scene.source_path,
        source_fingerprint=scene.source_fingerprint,
        width=scene.source_width,
        height=scene.source_height,
        rotation_deg=scene.source_rotation_deg,
        provider=scene.provider,
        rights_status=scene.rights_status,
        publication_eligible=bool(scene.publication_eligible),
        source_origin_hint=_origin_hint(scene.provider),
    )


class MasterImageI2VPlanner:
    version = MASTER_IMAGE_I2V_VERSION

    def build(
        self,
        request: MasterImageI2VRequest,
    ) -> MasterImageI2VPlan:
        _validate_alignment(request)

        base = request.video_base
        graph = request.story_graph
        ken = request.ken_burns

        graph_by_number = {
            node.scene_number: node for node in graph.nodes
        }
        ken_by_number = {
            scene.scene_number: scene for scene in ken.scenes
        }

        known_numbers = {scene.scene_number for scene in base.scenes}
        approved = set(request.approved_scene_numbers)
        unknown_approvals = sorted(approved - known_numbers)

        if unknown_approvals:
            raise MasterImageI2VError(
                "AI approval references unknown scene(s): "
                + ", ".join(str(value) for value in unknown_approvals)
            )

        scenes: list[I2VScenePlan] = []

        for base_scene in base.scenes:
            number = base_scene.scene_number
            node = graph_by_number[number]
            ken_scene = ken_by_number[number]

            common = dict(
                scene_number=number,
                node_id=node.node_id,
                selected_media_id=base_scene.selected_media_id,
                media_type=base_scene.media_type,
                source_path=base_scene.source_path,
                motion_intent=node.motion_intent,
            )

            if base_scene.placeholder:
                if number in approved:
                    raise MasterImageI2VError(
                        f"scene {number} cannot be approved without master image"
                    )

                scenes.append(
                    I2VScenePlan(
                        **common,
                        status=I2VSceneStatus.MASTER_IMAGE_REQUIRED,
                        approval_required=True,
                        approved=False,
                        handoff_ready=False,
                        review_required=False,
                        warnings=[
                            "NO_SELECTED_MASTER_IMAGE",
                            "F14_DOES_NOT_GENERATE_MASTER_IMAGES",
                        ],
                    )
                )
                continue

            if base_scene.media_type == MediaType.VIDEO:
                if number in approved:
                    raise MasterImageI2VError(
                        f"video scene {number} cannot be approved for F14 I2V"
                    )

                scenes.append(
                    I2VScenePlan(
                        **common,
                        status=I2VSceneStatus.VIDEO_NOT_APPLICABLE,
                        approval_required=False,
                        approved=False,
                        handoff_ready=False,
                        review_required=False,
                        warnings=[
                            "F14_IMAGE_TO_VIDEO_REQUIRES_STATIC_MASTER_IMAGE"
                        ],
                    )
                )
                continue

            if base_scene.media_type != MediaType.IMAGE:
                raise MasterImageI2VError(
                    f"unsupported media type scene {number}: "
                    f"{base_scene.media_type}"
                )

            if ken_scene.review_required:
                if number in approved:
                    raise MasterImageI2VError(
                        f"scene {number} cannot be approved before F13 review"
                    )

                scenes.append(
                    I2VScenePlan(
                        **common,
                        status=I2VSceneStatus.F13_REVIEW_REQUIRED,
                        approval_required=True,
                        approved=False,
                        handoff_ready=False,
                        review_required=True,
                        warnings=[
                            "F13_REVIEW_MUST_BE_RESOLVED_BEFORE_I2V"
                        ],
                    )
                )
                continue

            master = _master_descriptor(base_scene)

            rights_ok = (
                master.publication_eligible
                and master.rights_status
                in {
                    Rights.CONFIRMED_OWNED,
                    Rights.VERIFIED_LICENSE,
                }
            )

            if not rights_ok:
                if number in approved:
                    raise MasterImageI2VError(
                        f"scene {number} cannot be approved with blocked rights"
                    )

                scenes.append(
                    I2VScenePlan(
                        **common,
                        status=I2VSceneStatus.SOURCE_RIGHTS_BLOCKED,
                        master_image=master,
                        approval_required=True,
                        approved=False,
                        handoff_ready=False,
                        review_required=True,
                        warnings=[
                            "MASTER_IMAGE_RIGHTS_NOT_VERIFIED_FOR_DERIVATIVE_USE"
                        ],
                    )
                )
                continue

            is_approved = number in approved
            status = (
                I2VSceneStatus.I2V_JOB_READY
                if is_approved
                else I2VSceneStatus.AWAITING_AI_APPROVAL
            )

            job = I2VJobSpec(
                scene_number=number,
                master_image=master,
                requested_duration_seconds=base_scene.duration_seconds,
                delivery_width=base.output_width,
                delivery_height=base.output_height,
                delivery_fps=base.fps,
                motion_profile=_motion_profile(node.motion_intent),
                motion_intensity=node.intensity,
                positive_prompt=_positive_prompt(node),
                negative_prompt=_NEGATIVE_PROMPT,
                preservation_rules=list(_PRESERVATION_RULES),
                output_visual_origin=Origin.AI_GENERATED,
                output_scientific_status=ScientificStatus.RECREACION_VISUAL,
                disclosure_required=True,
                execution_authorized=is_approved,
                requires_f15_backend=True,
                ken_burns_is_fallback=True,
                stack_ken_burns_with_i2v=False,
            )

            scenes.append(
                I2VScenePlan(
                    **common,
                    status=status,
                    master_image=master,
                    job=job,
                    approval_required=True,
                    approved=is_approved,
                    handoff_ready=is_approved,
                    review_required=False,
                    warnings=(
                        []
                        if is_approved
                        else [
                            "EXPLICIT_AI_GENERATION_APPROVAL_REQUIRED"
                        ]
                    ),
                )
            )

        def count(status):
            return sum(scene.status == status for scene in scenes)

        stable_payload = {
            "version": self.version,
            "source_plan_context_hash": base.source_plan_context_hash,
            "source_story_graph_hash": graph.graph_hash,
            "source_ken_burns_hash": ken.ken_burns_hash,
            "delivery_width": base.output_width,
            "delivery_height": base.output_height,
            "delivery_fps": base.fps,
            "approved_scene_numbers": sorted(request.approved_scene_numbers),
            "scenes": [
                scene.model_dump(mode="json")
                for scene in scenes
            ],
        }

        return MasterImageI2VPlan(
            subject=base.subject,
            source_plan_context_hash=base.source_plan_context_hash,
            source_video_base_version=base.version,
            source_story_graph_version=graph.version,
            source_story_graph_hash=graph.graph_hash,
            source_ken_burns_version=ken.version,
            source_ken_burns_hash=ken.ken_burns_hash,
            delivery_width=base.output_width,
            delivery_height=base.output_height,
            delivery_fps=base.fps,
            scene_count=len(scenes),
            master_image_required_count=count(
                I2VSceneStatus.MASTER_IMAGE_REQUIRED
            ),
            video_not_applicable_count=count(
                I2VSceneStatus.VIDEO_NOT_APPLICABLE
            ),
            f13_review_required_count=count(
                I2VSceneStatus.F13_REVIEW_REQUIRED
            ),
            rights_blocked_count=count(
                I2VSceneStatus.SOURCE_RIGHTS_BLOCKED
            ),
            approval_pending_count=count(
                I2VSceneStatus.AWAITING_AI_APPROVAL
            ),
            job_ready_count=count(
                I2VSceneStatus.I2V_JOB_READY
            ),
            job_spec_count=sum(scene.job is not None for scene in scenes),
            approved_scene_numbers=sorted(request.approved_scene_numbers),
            scenes=scenes,
            structural_checks=I2VStructuralChecks(
                source_alignment=True,
                story_graph_hash_preserved=True,
                ken_burns_hash_preserved=True,
                material_identity_preserved=True,
                image_only_generation=True,
                rights_gate_enforced=True,
                explicit_ai_approval_enforced=True,
                generated_origin_labeled=True,
                scientific_recreation_labeled=True,
                ken_burns_fallback_preserved=True,
                no_motion_stacking=True,
            ),
            i2v_plan_hash=_hash_json(stable_payload),
            generated_at_utc=datetime.now(timezone.utc),
        )
