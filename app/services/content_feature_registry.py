from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from statistics import fmean
from typing import Any

from app.models.content_feature_registry import (
    CONTENT_FEATURE_REGISTRY_VERSION,
    ContentBindingStatus,
    ContentFeatureRegistryPlan,
    ContentFeatureRegistryRequest,
    ContentFeatureSnapshot,
    ContentFeatureValue,
)


class ContentFeatureRegistryError(RuntimeError):
    pass


def _hash(value: Any) -> str:
    raw = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest().upper()


def build_content_feature_registry(
    request: ContentFeatureRegistryRequest,
) -> ContentFeatureRegistryPlan:
    plan = request.plan
    graph = request.story_graph

    if plan.context_hash != graph.source_plan_context_hash:
        raise ContentFeatureRegistryError("F3/F8 context hash mismatch")
    if len(plan.scenes) != graph.node_count:
        raise ContentFeatureRegistryError("F3/F8 scene count mismatch")

    scene_durations = [float(scene.duration_seconds) for scene in plan.scenes]
    narration_chars = sum(len(scene.narration) for scene in plan.scenes)
    claim_count = sum(len(scene.claims) for scene in plan.scenes)
    ai_recreation_count = sum(scene.ai_recreation_allowed for scene in plan.scenes)
    astronomy_objects = {
        item.strip().casefold()
        for scene in plan.scenes
        for item in scene.astronomy_objects
        if item.strip()
    }
    intensities = [float(node.intensity) for node in graph.nodes]
    climax_node = next(
        node for node in graph.nodes if node.node_id == graph.climax_node_id
    )

    features = [
        ContentFeatureValue(
            feature_name="TOTAL_DURATION_SECONDS",
            value=float(plan.total_duration_seconds),
            unit="seconds",
            provenance=["F3.total_duration_seconds"],
        ),
        ContentFeatureValue(
            feature_name="SCENE_COUNT",
            value=float(len(plan.scenes)),
            unit="count",
            provenance=["F3.scenes"],
        ),
        ContentFeatureValue(
            feature_name="AVERAGE_SCENE_DURATION_SECONDS",
            value=round(fmean(scene_durations), 6),
            unit="seconds",
            provenance=["F3.scenes.duration_seconds"],
        ),
        ContentFeatureValue(
            feature_name="HOOK_CHAR_COUNT",
            value=float(len(plan.hook)),
            unit="characters",
            provenance=["F3.hook"],
        ),
        ContentFeatureValue(
            feature_name="NARRATION_CHAR_COUNT",
            value=float(narration_chars),
            unit="characters",
            provenance=["F3.scenes.narration"],
        ),
        ContentFeatureValue(
            feature_name="SCIENTIFIC_CLAIM_COUNT",
            value=float(claim_count),
            unit="count",
            provenance=["F3.scenes.claims"],
        ),
        ContentFeatureValue(
            feature_name="AI_RECREATION_SCENE_COUNT",
            value=float(ai_recreation_count),
            unit="count",
            provenance=["F3.scenes.ai_recreation_allowed"],
        ),
        ContentFeatureValue(
            feature_name="ASTRONOMY_OBJECT_DISTINCT_COUNT",
            value=float(len(astronomy_objects)),
            unit="count",
            provenance=["F3.scenes.astronomy_objects"],
        ),
        ContentFeatureValue(
            feature_name="PLACEHOLDER_SCENE_COUNT",
            value=float(graph.placeholder_count),
            unit="count",
            provenance=["F8.placeholder_count"],
        ),
        ContentFeatureValue(
            feature_name="MEAN_STORY_INTENSITY",
            value=round(fmean(intensities), 6),
            unit="ratio",
            provenance=["F8.nodes.intensity"],
        ),
        ContentFeatureValue(
            feature_name="CLIMAX_INTENSITY",
            value=float(climax_node.intensity),
            unit="ratio",
            provenance=["F8.climax_node_id", "F8.nodes.intensity"],
        ),
        ContentFeatureValue(
            feature_name="CLIMAX_POSITION_RATIO",
            value=round(climax_node.scene_number / len(plan.scenes), 6),
            unit="ratio",
            provenance=["F8.climax_node_id", "F8.nodes.scene_number"],
        ),
    ]

    binding = request.binding
    binding_status = (
        ContentBindingStatus.BOUND_TO_CONTENT
        if binding is not None
        else ContentBindingStatus.WAITING_FOR_CONTENT_BINDING
    )

    snapshot_stable = {
        "context_hash": plan.context_hash,
        "graph_hash": graph.graph_hash,
        "platform": binding.platform.value if binding else None,
        "content_id": binding.content_id if binding else None,
        "features": [item.model_dump(mode="json") for item in features],
    }
    snapshot_id = _hash(snapshot_stable)

    snapshot = ContentFeatureSnapshot(
        snapshot_id=snapshot_id,
        source_plan_context_hash=plan.context_hash,
        source_story_graph_hash=graph.graph_hash,
        platform=binding.platform if binding else None,
        content_id=binding.content_id if binding else None,
        binding_status=binding_status,
        feature_count=len(features),
        features=features,
    )

    stable = {
        "version": CONTENT_FEATURE_REGISTRY_VERSION,
        "subject": plan.subject,
        "snapshot": snapshot.model_dump(mode="json"),
    }

    return ContentFeatureRegistryPlan(
        subject=plan.subject,
        source_plan_context_hash=plan.context_hash,
        source_story_graph_hash=graph.graph_hash,
        snapshot_count=1,
        bound_snapshot_count=1 if binding else 0,
        status=binding_status,
        snapshots=[snapshot],
        content_feature_registry_hash=_hash(stable),
        generated_at_utc=datetime.now(timezone.utc),
    )
