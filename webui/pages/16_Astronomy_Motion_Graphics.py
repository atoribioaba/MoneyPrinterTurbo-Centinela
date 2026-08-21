from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.models.astronomy_director import AstronomyVideoPlan  # noqa: E402
from app.models.visual_story_graph import VisualStoryGraph  # noqa: E402
from app.services.astronomy_motion_graphics import (  # noqa: E402
    build_motion_graphics,
)


st.set_page_config(
    page_title="Astronomy Motion Graphics · El Centinela",
    layout="wide",
)
st.title("Astronomy Motion Graphics · El Centinela del Universo")
st.caption(
    "F16 · Planifica overlays sólo desde objetos explícitos y claims del plan. "
    "No inventa coordenadas ni cifras."
)

plan_path = st.text_input(
    "AstronomyVideoPlan F3",
    r"E:\IA\MPT-Phase3-Evidence\20260821-142904\real-astronomy-video-plan.json",
)
graph_path = st.text_input(
    "VisualStoryGraph F8",
    r"E:\IA\MPT-Phase8-Evidence\20260821-214354\real-visual-story-graph.json",
)

if st.button("Planificar motion graphics", type="primary"):
    plan = AstronomyVideoPlan.model_validate_json(
        Path(plan_path).read_text(encoding="utf-8")
    )
    graph = VisualStoryGraph.model_validate_json(
        Path(graph_path).read_text(encoding="utf-8")
    )
    result = build_motion_graphics(plan, graph)

    a, b, c = st.columns(3)
    a.metric("Cues", result.cue_count)
    b.metric("Object labels", result.object_label_count)
    c.metric("Claim callouts", result.claim_callout_count)

    st.dataframe(
        [
            {
                "scene": cue.scene_number,
                "kind": cue.kind.value,
                "text": cue.text,
                "status": cue.scientific_status.value,
                "review": cue.review_required,
                "anchor": cue.anchor.value,
            }
            for scene in result.scenes
            for cue in scene.cues
        ],
        use_container_width=True,
    )
    st.code(result.motion_graphics_hash)
