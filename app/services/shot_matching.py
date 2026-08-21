from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, timezone
from typing import Any

from app.models.color_science import ColorScienceStatus
from app.models.shot_matching import (
    SHOT_MATCHING_VERSION,
    ShotMatchEdge,
    ShotMatchStatus,
    ShotMatchingPlan,
    ShotMatchingRequest,
)
from app.models.shot_quality import ShotQualityStatus


class ShotMatchingError(RuntimeError):
    pass


def _hash(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest().upper()


def _exposure_delta(source_y: float, target_y: float) -> float:
    source = max(source_y, 1.0)
    target = max(target_y, 1.0)
    raw = math.log2(target / source)
    return round(max(-0.75, min(0.75, raw)), 3)


def build_shot_matching(request: ShotMatchingRequest) -> ShotMatchingPlan:
    graph = request.story_graph
    quality = request.shot_quality
    color = request.color_science

    if not (
        graph.source_plan_context_hash
        == quality.source_plan_context_hash
        == color.source_plan_context_hash
    ):
        raise ShotMatchingError("F8/F9/F19 context mismatch")
    if graph.graph_hash != quality.source_story_graph_hash:
        raise ShotMatchingError("F8/F9 graph hash mismatch")
    if graph.graph_hash != color.source_story_graph_hash:
        raise ShotMatchingError("F8/F19 graph hash mismatch")

    q = {scene.scene_number: scene for scene in quality.scenes}
    c = {scene.scene_number: scene for scene in color.scenes}
    n = {node.scene_number: node for node in graph.nodes}

    edges: list[ShotMatchEdge] = []
    for edge in graph.edges:
        s = edge.source_scene_number
        t = edge.target_scene_number
        if s not in q or t not in q or s not in c or t not in c:
            raise ShotMatchingError("missing F9/F19 scene for F20 edge")

        if n[s].placeholder or n[t].placeholder:
            edges.append(
                ShotMatchEdge(
                    edge_id=edge.edge_id,
                    source_scene_number=s,
                    target_scene_number=t,
                    status=ShotMatchStatus.PLACEHOLDER_PAIR_NOT_APPLICABLE,
                    execution_ready=False,
                    review_required=False,
                    warnings=["PLACEHOLDER_PAIR"],
                )
            )
            continue

        if (
            q[s].status == ShotQualityStatus.ANALYSIS_FAILED
            or q[t].status == ShotQualityStatus.ANALYSIS_FAILED
        ):
            edges.append(
                ShotMatchEdge(
                    edge_id=edge.edge_id,
                    source_scene_number=s,
                    target_scene_number=t,
                    status=ShotMatchStatus.REVIEW_REQUIRED,
                    execution_ready=False,
                    review_required=True,
                    warnings=["F9_ANALYSIS_FAILED"],
                )
            )
            continue

        if (
            q[s].status != ShotQualityStatus.SCORED
            or q[t].status != ShotQualityStatus.SCORED
            or c[s].status != ColorScienceStatus.GRADE_PLAN_READY
            or c[t].status != ColorScienceStatus.GRADE_PLAN_READY
        ):
            edges.append(
                ShotMatchEdge(
                    edge_id=edge.edge_id,
                    source_scene_number=s,
                    target_scene_number=t,
                    status=ShotMatchStatus.METRICS_UNAVAILABLE,
                    execution_ready=False,
                    review_required=False,
                    warnings=["MEASURED_LUMA_OR_COLOR_PLAN_UNAVAILABLE"],
                )
            )
            continue

        sy = float(q[s].frame_metrics.y_avg)
        ty = float(q[t].frame_metrics.y_avg)
        continuity = (
            "SAME_PROFILE"
            if c[s].profile == c[t].profile
            else f"{c[s].profile.value}->{c[t].profile.value}"
        )
        edges.append(
            ShotMatchEdge(
                edge_id=edge.edge_id,
                source_scene_number=s,
                target_scene_number=t,
                status=ShotMatchStatus.MATCH_PLAN_READY,
                source_y_avg=sy,
                target_y_avg=ty,
                exposure_offset_ev=_exposure_delta(sy, ty),
                color_profile_continuity=continuity,
                execution_ready=True,
                review_required=False,
            )
        )

    stable = {
        "version": SHOT_MATCHING_VERSION,
        "graph_hash": graph.graph_hash,
        "quality_hash": quality.quality_hash,
        "color_hash": color.color_science_hash,
        "edges": [edge.model_dump(mode="json") for edge in edges],
    }

    def count(status):
        return sum(edge.status == status for edge in edges)

    return ShotMatchingPlan(
        subject=graph.subject,
        source_plan_context_hash=graph.source_plan_context_hash,
        source_story_graph_hash=graph.graph_hash,
        source_quality_hash=quality.quality_hash,
        source_color_science_hash=color.color_science_hash,
        edge_count=len(edges),
        placeholder_pair_count=count(ShotMatchStatus.PLACEHOLDER_PAIR_NOT_APPLICABLE),
        metrics_unavailable_count=count(ShotMatchStatus.METRICS_UNAVAILABLE),
        match_ready_count=count(ShotMatchStatus.MATCH_PLAN_READY),
        review_required_count=count(ShotMatchStatus.REVIEW_REQUIRED),
        edges=edges,
        shot_matching_hash=_hash(stable),
        generated_at_utc=datetime.now(timezone.utc),
    )
