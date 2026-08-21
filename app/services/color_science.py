from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from app.models.cinematic_director import CinematicMood
from app.models.color_science import (
    COLOR_SCIENCE_VERSION,
    ColorProfile,
    ColorSciencePlan,
    ColorScienceRequest,
    ColorScienceScene,
    ColorScienceStatus,
)


class ColorScienceError(RuntimeError):
    pass


def _hash(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest().upper()


_PROFILE = {
    CinematicMood.MYSTERIOUS: (
        ColorProfile.MYSTERIOUS_NEUTRAL_COOL, 0.92, 1.06, 0.14, -0.01, "COOL_GENTLE"
    ),
    CinematicMood.CONTEMPLATIVE: (
        ColorProfile.CONTEMPLATIVE_NATURAL, 0.94, 0.98, 0.12, 0.00, "NEUTRAL"
    ),
    CinematicMood.DISCOVERY: (
        ColorProfile.DISCOVERY_CLEAN, 0.98, 1.02, 0.10, 0.00, "NEUTRAL"
    ),
    CinematicMood.AWE: (
        ColorProfile.AWE_CONTROLLED_CONTRAST, 1.00, 1.08, 0.18, -0.01, "NEUTRAL"
    ),
    CinematicMood.RELEASE: (
        ColorProfile.RELEASE_WARM_NEUTRAL, 0.96, 0.98, 0.15, 0.01, "WARM_GENTLE"
    ),
    CinematicMood.AFTERGLOW: (
        ColorProfile.AFTERGLOW_GENTLE, 0.94, 0.95, 0.18, 0.015, "WARM_GENTLE"
    ),
}


def build_color_science(request: ColorScienceRequest) -> ColorSciencePlan:
    graph = request.story_graph
    depth = request.depth_parallax

    if graph.source_plan_context_hash != depth.source_plan_context_hash:
        raise ColorScienceError("F8/F18 context hash mismatch")
    if graph.graph_hash != depth.source_story_graph_hash:
        raise ColorScienceError("F8 graph hash mismatch against F18")
    if graph.node_count != depth.scene_count:
        raise ColorScienceError("F8/F18 scene count mismatch")

    depth_by_number = {scene.scene_number: scene for scene in depth.scenes}
    scenes: list[ColorScienceScene] = []

    for node in graph.nodes:
        if node.scene_number not in depth_by_number:
            raise ColorScienceError("F18 missing scene")
        if node.placeholder:
            scenes.append(
                ColorScienceScene(
                    scene_number=node.scene_number,
                    node_id=node.node_id,
                    mood=node.mood,
                    status=ColorScienceStatus.PLACEHOLDER_NOT_APPLICABLE,
                )
            )
            continue

        profile, sat, contrast, rolloff, shadow, wb = _PROFILE[node.mood]
        scenes.append(
            ColorScienceScene(
                scene_number=node.scene_number,
                node_id=node.node_id,
                mood=node.mood,
                status=ColorScienceStatus.GRADE_PLAN_READY,
                profile=profile,
                saturation_scale=sat,
                contrast_scale=contrast,
                highlight_rolloff=rolloff,
                shadow_lift=shadow,
                white_balance_bias=wb,
            )
        )

    stable = {
        "version": COLOR_SCIENCE_VERSION,
        "graph_hash": graph.graph_hash,
        "depth_hash": depth.depth_parallax_hash,
        "scenes": [scene.model_dump(mode="json") for scene in scenes],
    }

    placeholder = sum(
        scene.status == ColorScienceStatus.PLACEHOLDER_NOT_APPLICABLE
        for scene in scenes
    )
    return ColorSciencePlan(
        subject=graph.subject,
        source_plan_context_hash=graph.source_plan_context_hash,
        source_story_graph_hash=graph.graph_hash,
        source_depth_parallax_hash=depth.depth_parallax_hash,
        scene_count=len(scenes),
        placeholder_count=placeholder,
        grade_ready_count=len(scenes) - placeholder,
        scenes=scenes,
        color_science_hash=_hash(stable),
        generated_at_utc=datetime.now(timezone.utc),
    )
