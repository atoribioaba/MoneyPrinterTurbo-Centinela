from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from app.models.astronomy import ScientificStatus
from app.models.astronomy_director import AstronomyVideoPlan
from app.models.astronomy_motion_graphics import (
    ASTRONOMY_MOTION_GRAPHICS_VERSION,
    AstronomyMotionGraphicsPlan,
    MotionGraphicAnchor,
    MotionGraphicAnimation,
    MotionGraphicCue,
    MotionGraphicKind,
    MotionGraphicsScene,
    MotionGraphicsStructuralChecks,
)
from app.models.visual_story_graph import VisualStoryGraph


class AstronomyMotionGraphicsError(RuntimeError):
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


def _validate_alignment(
    plan: AstronomyVideoPlan,
    graph: VisualStoryGraph,
) -> None:
    if plan.context_hash != graph.source_plan_context_hash:
        raise AstronomyMotionGraphicsError(
            "F3/F8 context hash mismatch"
        )
    if len(plan.scenes) != graph.node_count:
        raise AstronomyMotionGraphicsError(
            "F3/F8 scene count mismatch"
        )
    if [
        scene.scene_number for scene in plan.scenes
    ] != [
        node.scene_number for node in graph.nodes
    ]:
        raise AstronomyMotionGraphicsError(
            "F3/F8 scene order mismatch"
        )


def _review_required(status: ScientificStatus) -> bool:
    return status not in {
        ScientificStatus.HECHO_VERIFICADO,
        ScientificStatus.APROXIMACION_DIVULGATIVA,
    }


def build_motion_graphics(
    plan: AstronomyVideoPlan,
    graph: VisualStoryGraph,
) -> AstronomyMotionGraphicsPlan:
    _validate_alignment(plan, graph)

    graph_by_number = {
        node.scene_number: node for node in graph.nodes
    }
    result_scenes: list[MotionGraphicsScene] = []

    anchors = [
        MotionGraphicAnchor.TOP_SAFE,
        MotionGraphicAnchor.LOWER_THIRD,
        MotionGraphicAnchor.SIDE_CARD,
    ]

    for scene in plan.scenes:
        node = graph_by_number[scene.scene_number]
        cues: list[MotionGraphicCue] = []
        cue_index = 0

        seen_objects = set()
        for obj in scene.astronomy_objects:
            key = obj.strip().casefold()
            if not key or key in seen_objects:
                continue
            seen_objects.add(key)

            anchor = anchors[cue_index % len(anchors)]
            cues.append(
                MotionGraphicCue(
                    cue_id=f"scene:{scene.scene_number}:object:{cue_index + 1}",
                    scene_number=scene.scene_number,
                    kind=MotionGraphicKind.OBJECT_LABEL,
                    text=obj.strip(),
                    scientific_status=scene.scientific_status,
                    fact_ids=[],
                    anchor=anchor,
                    animation=(
                        MotionGraphicAnimation.FADE_IN_HOLD_FADE_OUT
                    ),
                    normalized_start=0.08,
                    normalized_end=0.42,
                    review_required=_review_required(
                        scene.scientific_status
                    ),
                )
            )
            cue_index += 1

        for claim_index, claim in enumerate(scene.claims, start=1):
            anchor = anchors[cue_index % len(anchors)]
            cues.append(
                MotionGraphicCue(
                    cue_id=(
                        f"scene:{scene.scene_number}:claim:{claim_index}"
                    ),
                    scene_number=scene.scene_number,
                    kind=(
                        MotionGraphicKind.SCIENTIFIC_CLAIM_CALLOUT
                    ),
                    text=claim.statement,
                    scientific_status=claim.scientific_status,
                    fact_ids=list(claim.fact_ids),
                    anchor=anchor,
                    animation=(
                        MotionGraphicAnimation.GENTLE_SLIDE_IN_HOLD_FADE_OUT
                    ),
                    normalized_start=0.48,
                    normalized_end=0.88,
                    review_required=_review_required(
                        claim.scientific_status
                    ),
                )
            )
            cue_index += 1

        result_scenes.append(
            MotionGraphicsScene(
                scene_number=scene.scene_number,
                node_id=node.node_id,
                cue_count=len(cues),
                cues=cues,
                review_required=any(
                    cue.review_required for cue in cues
                ),
            )
        )

    all_cues = [
        cue
        for scene in result_scenes
        for cue in scene.cues
    ]

    stable = {
        "version": ASTRONOMY_MOTION_GRAPHICS_VERSION,
        "subject": plan.subject,
        "source_plan_context_hash": plan.context_hash,
        "source_story_graph_hash": graph.graph_hash,
        "scenes": [
            scene.model_dump(mode="json")
            for scene in result_scenes
        ],
    }

    return AstronomyMotionGraphicsPlan(
        subject=plan.subject,
        source_plan_context_hash=plan.context_hash,
        source_story_graph_version=graph.version,
        source_story_graph_hash=graph.graph_hash,
        scene_count=len(result_scenes),
        cue_count=len(all_cues),
        object_label_count=sum(
            cue.kind == MotionGraphicKind.OBJECT_LABEL
            for cue in all_cues
        ),
        claim_callout_count=sum(
            cue.kind == MotionGraphicKind.SCIENTIFIC_CLAIM_CALLOUT
            for cue in all_cues
        ),
        review_required_count=sum(
            scene.review_required for scene in result_scenes
        ),
        scenes=result_scenes,
        structural_checks=MotionGraphicsStructuralChecks(
            plan_graph_alignment=True,
            explicit_objects_only=True,
            plan_claims_only=True,
            verified_claim_fact_ids_preserved=True,
            no_invented_coordinates=True,
            no_invented_trajectories=True,
            no_invented_numeric_values=True,
            scientific_status_preserved=True,
        ),
        motion_graphics_hash=_hash_json(stable),
        generated_at_utc=datetime.now(timezone.utc),
    )
