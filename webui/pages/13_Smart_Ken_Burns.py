from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


from app.models.astronomy_director import AstronomyVideoPlan  # noqa: E402
from app.models.material_selection import MaterialSelectionPlan  # noqa: E402
from app.models.smart_ken_burns import SmartKenBurnsRequest  # noqa: E402
from app.models.smart_reframing import SmartReframingPlan  # noqa: E402
from app.models.video_base import VideoBasePlanRequest, VideoBaseRenderMode  # noqa: E402
from app.models.visual_story_graph import VisualStoryGraph  # noqa: E402
from app.services.smart_ken_burns import (  # noqa: E402
    SmartKenBurnsError,
    SmartKenBurnsPlanner,
)
from app.services.video_base_planner import VideoBasePlanner  # noqa: E402


st.set_page_config(
    page_title="Smart Ken Burns · El Centinela",
    layout="wide",
)
st.title("Smart Ken Burns · El Centinela del Universo")
st.caption(
    "Fase 13 · Diseña movimiento cinematográfico sólo para imágenes "
    "estáticas a partir del encuadre F12. No renderiza."
)

plan_path = st.text_input(
    "AstronomyVideoPlan F3",
    r"E:\IA\MPT-Phase3-Evidence\20260821-142904\real-astronomy-video-plan.json",
)
materials_path = st.text_input(
    "MaterialSelectionPlan F5",
    r"E:\IA\MPT-Phase5-Evidence\20260821-183036\real-material-selection-plan.json",
)
graph_path = st.text_input(
    "VisualStoryGraph F8",
    r"E:\IA\MPT-Phase8-Evidence\20260821-214354\real-visual-story-graph.json",
)
reframing_path = st.text_input(
    "SmartReframingPlan F12",
    r"E:\IA\MPT-Phase12-Evidence\20260821-223654\real-smart-reframing-plan.json",
)
save_path = st.text_input("Guardar SmartKenBurnsPlan (opcional)", "")


if st.button("Planificar Smart Ken Burns", type="primary"):
    try:
        plan = AstronomyVideoPlan.model_validate_json(
            Path(plan_path).read_text(encoding="utf-8")
        )
        materials = MaterialSelectionPlan.model_validate_json(
            Path(materials_path).read_text(encoding="utf-8")
        )
        graph = VisualStoryGraph.model_validate_json(
            Path(graph_path).read_text(encoding="utf-8")
        )
        reframing = SmartReframingPlan.model_validate_json(
            Path(reframing_path).read_text(encoding="utf-8")
        )

        video_base = VideoBasePlanner().build(
            VideoBasePlanRequest(
                plan=plan,
                materials=materials,
                render_mode=VideoBaseRenderMode.REVIEW_PARTIAL,
                requested_codec="h264_nvenc",
            )
        )

        result = SmartKenBurnsPlanner().build(
            SmartKenBurnsRequest(
                video_base=video_base,
                story_graph=graph,
                reframing=reframing,
            )
        )

        a, b, c, d = st.columns(4)
        a.metric("Movimiento", result.motion_scene_count)
        b.metric("Push-in", result.push_in_count)
        c.metric("Pull-back", result.pull_back_count)
        d.metric("Reveal", result.controlled_reveal_count)

        st.dataframe(
            [
                {
                    "scene": scene.scene_number,
                    "status": scene.status.value,
                    "motion": scene.motion_type.value,
                    "pace": scene.pace.value,
                    "intensity": scene.intensity,
                    "zoom_delta": scene.zoom_delta,
                    "ready": scene.execution_ready,
                    "review": scene.review_required,
                    "keyframes": len(scene.keyframes),
                }
                for scene in result.scenes
            ],
            use_container_width=True,
        )

        st.code(result.ken_burns_hash)

        if save_path.strip():
            target = Path(save_path.strip())
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(
                result.model_dump_json(indent=2),
                encoding="utf-8",
            )
            st.success(f"Plan guardado: {target}")

        st.json(result.model_dump(mode="json"))

    except (OSError, ValueError, SmartKenBurnsError) as exc:
        st.error(str(exc))
