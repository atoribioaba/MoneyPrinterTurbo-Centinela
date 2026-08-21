from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from app.models.cinematic_director import TransitionIntent
from app.models.shot_matching import ShotMatchStatus
from app.models.transition_director import (
    TRANSITION_DIRECTOR_VERSION,
    TransitionDirectorPlan,
    TransitionDirectorRequest,
    TransitionSpec,
    TransitionStatus,
    TransitionType,
)


class TransitionDirectorError(RuntimeError):
    pass


def _hash(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest().upper()


_TRANSITIONS = {
    TransitionIntent.OPEN: (TransitionType.CUT, 0.0),
    TransitionIntent.MOTIVATED_CUT: (TransitionType.CUT, 0.0),
    TransitionIntent.SOFT_CUT: (TransitionType.SOFT_DISSOLVE, 0.18),
    TransitionIntent.EMPHASIS_CUT: (TransitionType.CUT, 0.0),
    TransitionIntent.BREATHING_CUT: (TransitionType.SOFT_DISSOLVE, 0.24),
    TransitionIntent.FADE_OUT_INTENT: (TransitionType.FADE_TO_BLACK, 0.35),
}


def build_transition_director(
    request: TransitionDirectorRequest,
) -> TransitionDirectorPlan:
    graph = request.story_graph
    matching = request.shot_matching

    if graph.source_plan_context_hash != matching.source_plan_context_hash:
        raise TransitionDirectorError("F8/F20 context mismatch")
    if graph.graph_hash != matching.source_story_graph_hash:
        raise TransitionDirectorError("F8/F20 graph hash mismatch")
    if graph.edge_count != matching.edge_count:
        raise TransitionDirectorError("F8/F20 edge count mismatch")

    match_by_id = {item.edge_id: item for item in matching.edges}
    transitions: list[TransitionSpec] = []

    for edge in graph.edges:
        if edge.edge_id not in match_by_id:
            raise TransitionDirectorError("F20 missing edge")
        transition_type, duration = _TRANSITIONS[edge.source_transition_intent]
        placeholder = (
            match_by_id[edge.edge_id].status
            == ShotMatchStatus.PLACEHOLDER_PAIR_NOT_APPLICABLE
        )
        transitions.append(
            TransitionSpec(
                edge_id=edge.edge_id,
                source_scene_number=edge.source_scene_number,
                target_scene_number=edge.target_scene_number,
                status=(
                    TransitionStatus.PLACEHOLDER_PENDING_MEDIA
                    if placeholder
                    else TransitionStatus.TRANSITION_PLAN_READY
                ),
                transition_type=transition_type,
                duration_seconds=duration,
                execution_ready=not placeholder,
                warnings=["MEDIA_PENDING"] if placeholder else [],
            )
        )

    stable = {
        "version": TRANSITION_DIRECTOR_VERSION,
        "graph_hash": graph.graph_hash,
        "matching_hash": matching.shot_matching_hash,
        "transitions": [item.model_dump(mode="json") for item in transitions],
    }
    pending = sum(
        item.status == TransitionStatus.PLACEHOLDER_PENDING_MEDIA
        for item in transitions
    )
    return TransitionDirectorPlan(
        subject=graph.subject,
        source_plan_context_hash=graph.source_plan_context_hash,
        source_story_graph_hash=graph.graph_hash,
        source_shot_matching_hash=matching.shot_matching_hash,
        transition_count=len(transitions),
        placeholder_pending_count=pending,
        ready_count=len(transitions) - pending,
        transitions=transitions,
        transition_director_hash=_hash(stable),
        generated_at_utc=datetime.now(timezone.utc),
    )
