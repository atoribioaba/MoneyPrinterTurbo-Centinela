from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from app.models.cinematic_director import CinematicMood
from app.models.sound_design import (
    SOUND_DESIGN_VERSION,
    SoundCue,
    SoundCueType,
    SoundDesignPlan,
    SoundDesignRequest,
)


class SoundDesignError(RuntimeError):
    pass


def _hash(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest().upper()


_PROFILE = {
    CinematicMood.MYSTERIOUS: "LOW_ATMOSPHERIC_BED",
    CinematicMood.CONTEMPLATIVE: "SPARSE_AMBIENT_BED",
    CinematicMood.DISCOVERY: "SUBTLE_TONAL_BED",
    CinematicMood.AWE: "WIDE_CINEMATIC_BED",
    CinematicMood.RELEASE: "GENTLE_RELEASE_BED",
    CinematicMood.AFTERGLOW: "WARM_AFTERGLOW_BED",
}


def build_sound_design(request: SoundDesignRequest) -> SoundDesignPlan:
    graph = request.story_graph
    info = request.infographics
    transitions = request.transitions

    if not (
        graph.source_plan_context_hash
        == info.source_plan_context_hash
        == transitions.source_plan_context_hash
    ):
        raise SoundDesignError("F8/F17/F21 context mismatch")
    if graph.graph_hash != transitions.source_story_graph_hash:
        raise SoundDesignError("F8/F21 graph hash mismatch")
    if graph.node_count != info.scene_count:
        raise SoundDesignError("F8/F17 scene count mismatch")

    cues: list[SoundCue] = []
    for node in graph.nodes:
        cues.append(
            SoundCue(
                cue_id=f"scene:{node.scene_number}:bed",
                scene_number=node.scene_number,
                cue_type=SoundCueType.ATMOSPHERIC_BED,
                design_profile=_PROFILE[node.mood],
                intensity=round(min(0.75, 0.20 + 0.55 * float(node.intensity)), 3),
            )
        )

    climax = max(graph.nodes, key=lambda node: node.intensity)
    if climax.intensity >= 0.80:
        cues.append(
            SoundCue(
                cue_id=f"scene:{climax.scene_number}:climax-accent",
                scene_number=climax.scene_number,
                cue_type=SoundCueType.CLIMAX_ACCENT,
                design_profile="SUBTLE_CINEMATIC_IMPACT_NON_DIEGETIC",
                intensity=round(min(0.90, float(climax.intensity)), 3),
            )
        )

    stable = {
        "version": SOUND_DESIGN_VERSION,
        "graph_hash": graph.graph_hash,
        "infographics_hash": info.infographics_hash,
        "transition_hash": transitions.transition_director_hash,
        "cues": [cue.model_dump(mode="json") for cue in cues],
    }

    return SoundDesignPlan(
        subject=graph.subject,
        source_plan_context_hash=graph.source_plan_context_hash,
        source_story_graph_hash=graph.graph_hash,
        source_infographics_hash=info.infographics_hash,
        source_transition_director_hash=transitions.transition_director_hash,
        scene_count=graph.node_count,
        cue_count=len(cues),
        asset_count=0,
        climax_accent_count=sum(
            cue.cue_type == SoundCueType.CLIMAX_ACCENT for cue in cues
        ),
        cues=cues,
        sound_design_hash=_hash(stable),
        generated_at_utc=datetime.now(timezone.utc),
    )
