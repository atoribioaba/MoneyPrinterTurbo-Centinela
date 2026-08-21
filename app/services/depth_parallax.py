from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from app.models.astromedia import MediaType
from app.models.depth_parallax import (
    DEPTH_PARALLAX_VERSION,
    DepthParallaxPlan,
    DepthParallaxRequest,
    DepthParallaxScene,
    DepthParallaxStatus,
    DepthParallaxStructuralChecks,
)


class DepthParallaxError(RuntimeError):
    pass


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _hash_json(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest().upper()


def _validate(request: DepthParallaxRequest) -> None:
    graph = request.story_graph
    ken = request.ken_burns

    if graph.source_plan_context_hash != ken.source_plan_context_hash:
        raise DepthParallaxError("F8/F13 context hash mismatch")
    if graph.graph_hash != ken.source_story_graph_hash:
        raise DepthParallaxError("F8 graph hash mismatch against F13")
    if graph.node_count != ken.scene_count:
        raise DepthParallaxError("F8/F13 scene count mismatch")

    graph_numbers = [node.scene_number for node in graph.nodes]
    ken_numbers = [scene.scene_number for scene in ken.scenes]
    if graph_numbers != ken_numbers:
        raise DepthParallaxError("F8/F13 scene order mismatch")


def build_depth_parallax(request: DepthParallaxRequest) -> DepthParallaxPlan:
    _validate(request)

    graph = request.story_graph
    ken = request.ken_burns
    hints = {item.scene_number: item for item in request.depth_maps}
    scenes: list[DepthParallaxScene] = []

    for node, ken_scene in zip(graph.nodes, ken.scenes):
        common = dict(
            scene_number=node.scene_number,
            node_id=node.node_id,
            selected_media_id=ken_scene.selected_media_id,
            media_type=ken_scene.media_type,
        )

        if node.placeholder:
            scenes.append(
                DepthParallaxScene(
                    **common,
                    status=DepthParallaxStatus.PLACEHOLDER_NOT_APPLICABLE,
                    execution_ready=False,
                    review_required=False,
                    warnings=["NO_SELECTED_MEDIA"],
                )
            )
            continue

        if ken_scene.media_type == MediaType.VIDEO:
            scenes.append(
                DepthParallaxScene(
                    **common,
                    status=DepthParallaxStatus.VIDEO_NOT_APPLICABLE,
                    execution_ready=False,
                    review_required=False,
                    warnings=["F18_V01_DEPTH_PARALLAX_IS_STATIC_IMAGE_ONLY"],
                )
            )
            continue

        if ken_scene.review_required:
            scenes.append(
                DepthParallaxScene(
                    **common,
                    status=DepthParallaxStatus.REVIEW_REQUIRED,
                    execution_ready=False,
                    review_required=True,
                    warnings=["F13_REVIEW_MUST_BE_RESOLVED_FIRST"],
                )
            )
            continue

        hint = hints.get(node.scene_number)
        if hint is None:
            scenes.append(
                DepthParallaxScene(
                    **common,
                    status=DepthParallaxStatus.DEPTH_MAP_REQUIRED,
                    execution_ready=False,
                    review_required=False,
                    warnings=[
                        "EXPLICIT_DEPTH_MAP_REQUIRED",
                        "F18_DOES_NOT_RUN_DEPTH_ESTIMATION",
                    ],
                )
            )
            continue

        if hint.source_media_id != ken_scene.selected_media_id:
            raise DepthParallaxError(
                f"depth map media mismatch scene {node.scene_number}"
            )

        if not hint.source_match_verified:
            scenes.append(
                DepthParallaxScene(
                    **common,
                    status=DepthParallaxStatus.REVIEW_REQUIRED,
                    execution_ready=False,
                    review_required=True,
                    warnings=["DEPTH_MAP_SOURCE_MATCH_NOT_VERIFIED"],
                )
            )
            continue

        shift = round(min(0.025, 0.008 + 0.014 * float(node.intensity)), 4)
        scenes.append(
            DepthParallaxScene(
                **common,
                status=DepthParallaxStatus.DEPTH_MAP_READY,
                depth_map_path=hint.depth_map_path,
                execution_ready=True,
                review_required=False,
                layer_count=3,
                max_parallax_shift_fraction=shift,
            )
        )

    stable = {
        "version": DEPTH_PARALLAX_VERSION,
        "graph_hash": graph.graph_hash,
        "ken_hash": ken.ken_burns_hash,
        "depth_maps": [item.model_dump(mode="json") for item in request.depth_maps],
        "scenes": [scene.model_dump(mode="json") for scene in scenes],
    }

    def count(status):
        return sum(scene.status == status for scene in scenes)

    return DepthParallaxPlan(
        subject=graph.subject,
        source_plan_context_hash=graph.source_plan_context_hash,
        source_story_graph_version=graph.version,
        source_story_graph_hash=graph.graph_hash,
        source_ken_burns_version=ken.version,
        source_ken_burns_hash=ken.ken_burns_hash,
        scene_count=len(scenes),
        placeholder_count=count(DepthParallaxStatus.PLACEHOLDER_NOT_APPLICABLE),
        video_not_applicable_count=count(DepthParallaxStatus.VIDEO_NOT_APPLICABLE),
        depth_map_required_count=count(DepthParallaxStatus.DEPTH_MAP_REQUIRED),
        depth_map_ready_count=count(DepthParallaxStatus.DEPTH_MAP_READY),
        review_required_count=count(DepthParallaxStatus.REVIEW_REQUIRED),
        scenes=scenes,
        structural_checks=DepthParallaxStructuralChecks(
            source_alignment=True,
            graph_hash_preserved=True,
            ken_burns_hash_preserved=True,
            image_only_depth=True,
            explicit_depth_map_only=True,
            no_depth_inference=True,
            no_model_download=True,
            no_render=True,
        ),
        depth_parallax_hash=_hash_json(stable),
        generated_at_utc=datetime.now(timezone.utc),
    )
