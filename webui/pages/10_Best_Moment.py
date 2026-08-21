from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


from app.models.astronomy_director import AstronomyVideoPlan  # noqa: E402
from app.models.best_moment import BestMomentRequest  # noqa: E402
from app.models.material_selection import MaterialSelectionPlan  # noqa: E402
from app.models.shot_quality import ShotQualityPlan  # noqa: E402
from app.models.video_base import VideoBasePlanRequest, VideoBaseRenderMode  # noqa: E402
from app.models.visual_story_graph import VisualStoryGraph  # noqa: E402
from app.services.best_moment import BestMomentDetector, BestMomentError  # noqa: E402
from app.services.video_base_planner import VideoBasePlanner  # noqa: E402


st.set_page_config(
    page_title="Best Moment Detector · El Centinela",
    layout="wide",
)
st.title("Best Moment Detector · El Centinela del Universo")
st.caption(
    "Fase 10 · Busca una ventana temporal mejor sólo dentro del vídeo "
    "seleccionado por F5/F6. No cambia material, no hace tracking y no reencuadra."
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
quality_path = st.text_input(
    "ShotQualityPlan F9",
    r"E:\IA\MPT-Phase9-Evidence\20260821-215420\real-shot-quality-plan.json",
)
max_candidates = st.slider(
    "Máximo de ventanas candidatas por vídeo",
    min_value=3,
    max_value=21,
    value=9,
    step=2,
)
save_path = st.text_input("Guardar BestMomentPlan (opcional)", "")


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
    quality = ShotQualityPlan.model_validate_json(
        Path(quality_path).read_text(encoding="utf-8")
    )

    video_base = VideoBasePlanner().build(
        VideoBasePlanRequest(
            plan=plan,
            materials=materials,
            render_mode=VideoBaseRenderMode.REVIEW_PARTIAL,
            requested_codec="h264_nvenc",
        )
    )

    return BestMomentRequest(
        video_base=video_base,
        story_graph=graph,
        shot_quality=quality,
        max_candidates=max_candidates,
    )


if st.button("Detectar Best Moment", type="primary"):
    try:
        result = BestMomentDetector().build(load_request())

        a, b, c, d = st.columns(4)
        a.metric("Escenas", result.scene_count)
        b.metric("Vídeos seleccionados", result.selected_count)
        c.metric("Placeholders", result.placeholder_count)
        d.metric("Frames analizados", result.ffmpeg_frames_analyzed)

        st.dataframe(
            [
                {
                    "scene": scene.scene_number,
                    "status": scene.status.value,
                    "original_start": scene.original_start_s,
                    "selected_start": scene.selected_start_s,
                    "selected_score": scene.selected_score,
                    "candidates": len(scene.candidates),
                    "media": scene.selected_media_id,
                }
                for scene in result.scenes
            ],
            use_container_width=True,
        )

        st.code(result.best_moment_hash)

        if save_path.strip():
            target = Path(save_path.strip())
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(
                result.model_dump_json(indent=2),
                encoding="utf-8",
            )
            st.success(f"Plan guardado: {target}")

        st.json(result.model_dump(mode="json"))

    except (OSError, ValueError, BestMomentError) as exc:
        st.error(str(exc))
