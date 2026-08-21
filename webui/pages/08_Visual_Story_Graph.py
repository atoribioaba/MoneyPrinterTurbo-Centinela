from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


from app.models.astronomy_director import AstronomyVideoPlan  # noqa: E402
from app.models.cinematic_director import CinematicDirectionPlan  # noqa: E402
from app.models.material_selection import MaterialSelectionPlan  # noqa: E402
from app.models.video_base import VideoBasePlanRequest, VideoBaseRenderMode  # noqa: E402
from app.models.visual_story_graph import VisualStoryGraphRequest  # noqa: E402
from app.services.video_base_planner import VideoBasePlanner  # noqa: E402
from app.services.visual_story_graph import (  # noqa: E402
    VisualStoryGraphBuilder,
    VisualStoryGraphError,
)


st.set_page_config(
    page_title="Visual Story Graph · El Centinela",
    layout="wide",
)
st.title("Visual Story Graph · El Centinela del Universo")
st.caption(
    "Fase 8 · F3 + F6 + F7 → grafo determinista de continuidad narrativa y visual. "
    "No renderiza, no puntúa calidad y no ejecuta tracking."
)

plan_path = st.text_input(
    "AstronomyVideoPlan F3",
    r"E:\IA\MPT-Phase3-Evidence\20260821-142904\real-astronomy-video-plan.json",
)
materials_path = st.text_input(
    "MaterialSelectionPlan F5",
    r"E:\IA\MPT-Phase5-Evidence\20260821-183036\real-material-selection-plan.json",
)
direction_path = st.text_input(
    "CinematicDirectionPlan F7",
    r"E:\IA\MPT-Phase7-Evidence\20260821-212543\real-cinematic-direction-plan.json",
)
save_path = st.text_input(
    "Guardar grafo F8 (opcional)",
    "",
)


def load_request():
    plan = AstronomyVideoPlan.model_validate_json(
        Path(plan_path).read_text(encoding="utf-8")
    )
    materials = MaterialSelectionPlan.model_validate_json(
        Path(materials_path).read_text(encoding="utf-8")
    )
    direction = CinematicDirectionPlan.model_validate_json(
        Path(direction_path).read_text(encoding="utf-8")
    )

    video_base = VideoBasePlanner().build(
        VideoBasePlanRequest(
            plan=plan,
            materials=materials,
            render_mode=VideoBaseRenderMode.REVIEW_PARTIAL,
            requested_codec="h264_nvenc",
        )
    )

    return VisualStoryGraphRequest(
        plan=plan,
        video_base=video_base,
        cinematic_direction=direction,
    )


if st.button("Construir Visual Story Graph", type="primary"):
    try:
        graph = VisualStoryGraphBuilder().build(load_request())

        a, b, c, d = st.columns(4)
        a.metric("Nodos", graph.node_count)
        b.metric("Aristas", graph.edge_count)
        c.metric("Threads", len(graph.subject_threads))
        d.metric("Clímax", graph.climax_node_id)

        st.subheader("Nodos")
        st.dataframe(
            [
                {
                    "node": node.node_id,
                    "act": node.act.value,
                    "role": node.narrative_role.value,
                    "intensity": node.intensity,
                    "mood": node.mood.value,
                    "composition": node.composition_intent.value,
                    "motion": node.motion_intent.value,
                    "subjects": ", ".join(node.astronomy_objects),
                    "placeholder": node.placeholder,
                }
                for node in graph.nodes
            ],
            use_container_width=True,
        )

        st.subheader("Aristas")
        st.dataframe(
            [
                {
                    "edge": edge.edge_id,
                    "narrative": edge.narrative_link.value,
                    "subject": edge.subject_link.value,
                    "composition": edge.composition_link.value,
                    "delta": edge.intensity_delta,
                    "shared": ", ".join(edge.shared_subject_keys),
                    "flags": ", ".join(edge.continuity_flags),
                }
                for edge in graph.edges
            ],
            use_container_width=True,
        )

        st.subheader("Threads astronómicos")
        st.json(
            [
                thread.model_dump(mode="json")
                for thread in graph.subject_threads
            ]
        )

        st.code(graph.graph_hash)

        if save_path.strip():
            target = Path(save_path.strip())
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(
                graph.model_dump_json(indent=2),
                encoding="utf-8",
            )
            st.success(f"Grafo guardado: {target}")

        st.json(graph.model_dump(mode="json"))

    except (OSError, ValueError, VisualStoryGraphError) as exc:
        st.error(str(exc))
