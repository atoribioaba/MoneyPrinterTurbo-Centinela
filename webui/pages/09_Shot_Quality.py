from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


from app.models.astronomy_director import AstronomyVideoPlan  # noqa: E402
from app.models.material_selection import MaterialSelectionPlan  # noqa: E402
from app.models.shot_quality import ShotQualityRequest  # noqa: E402
from app.models.video_base import VideoBasePlanRequest, VideoBaseRenderMode  # noqa: E402
from app.models.visual_story_graph import VisualStoryGraph  # noqa: E402
from app.services.shot_quality import ShotQualityError, ShotQualityScorer  # noqa: E402
from app.services.video_base_planner import VideoBasePlanner  # noqa: E402


st.set_page_config(
    page_title="Shot Quality Scorer · El Centinela",
    layout="wide",
)
st.title("Shot Quality Scorer · El Centinela del Universo")
st.caption(
    "Fase 9 · VideoBasePlan + VisualStoryGraph → evaluación técnica "
    "determinista de la toma seleccionada. F10 conserva la búsqueda temporal "
    "del Best Moment."
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
save_path = st.text_input(
    "Guardar ShotQualityPlan (opcional)",
    "",
)


def load_request():
    plan = AstronomyVideoPlan.model_validate_json(
        Path(plan_path).read_text(encoding="utf-8")
    )
    materials = MaterialSelectionPlan.model_validate_json(
        Path(materials_path).read_text(encoding="utf-8")
    )
    graph = VisualStoryGraph.model_validate_json(
        Path(graph_path).read_text(encoding="utf-8")
    )

    video_base = VideoBasePlanner().build(
        VideoBasePlanRequest(
            plan=plan,
            materials=materials,
            render_mode=VideoBaseRenderMode.REVIEW_PARTIAL,
            requested_codec="h264_nvenc",
        )
    )

    return ShotQualityRequest(
        video_base=video_base,
        story_graph=graph,
    )


if st.button("Evaluar calidad técnica", type="primary"):
    try:
        result = ShotQualityScorer().build(load_request())

        a, b, c, d = st.columns(4)
        a.metric("Escenas", result.scene_count)
        b.metric("Evaluadas", result.scored_count)
        c.metric("No evaluables", result.not_scorable_count)
        d.metric("Fallos análisis", result.analysis_failed_count)

        st.metric(
            "Media técnica",
            "N/A" if result.mean_score is None else f"{result.mean_score:.3f}",
        )

        st.dataframe(
            [
                {
                    "scene": scene.scene_number,
                    "node": scene.node_id,
                    "status": scene.status.value,
                    "score": scene.score,
                    "band": scene.band.value,
                    "flags": ", ".join(scene.flags),
                    "blur": (
                        scene.frame_metrics.blur_metric
                        if scene.frame_metrics
                        else None
                    ),
                    "luma_span": (
                        scene.frame_metrics.luma_span
                        if scene.frame_metrics
                        else None
                    ),
                }
                for scene in result.scenes
            ],
            use_container_width=True,
        )

        st.code(result.quality_hash)

        if save_path.strip():
            target = Path(save_path.strip())
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(
                result.model_dump_json(indent=2),
                encoding="utf-8",
            )
            st.success(f"Plan guardado: {target}")

        st.json(result.model_dump(mode="json"))

    except (OSError, ValueError, ShotQualityError) as exc:
        st.error(str(exc))
