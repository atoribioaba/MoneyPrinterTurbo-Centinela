from __future__ import annotations

import json
import sys
from pathlib import Path

import streamlit as st


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


from app.models.astronomy_director import AstronomyVideoPlan  # noqa: E402
from app.models.astronomical_tracker import (  # noqa: E402
    AstronomicalTrackingRequest,
    TrackingSeed,
)
from app.models.best_moment import BestMomentPlan  # noqa: E402
from app.models.material_selection import MaterialSelectionPlan  # noqa: E402
from app.models.shot_quality import ShotQualityPlan  # noqa: E402
from app.models.video_base import VideoBasePlanRequest, VideoBaseRenderMode  # noqa: E402
from app.models.visual_story_graph import VisualStoryGraph  # noqa: E402
from app.services.astronomical_tracker import (  # noqa: E402
    AstronomicalObjectTracker,
    AstronomicalTrackingError,
)
from app.services.video_base_planner import VideoBasePlanner  # noqa: E402


st.set_page_config(
    page_title="Astronomical Object Tracker · El Centinela",
    layout="wide",
)
st.title("Astronomical Object Tracker · El Centinela del Universo")
st.caption(
    "Fase 11 · Tracking temporal dentro de la ventana F10. "
    "No reencuadra y no infiere el objeto desde texto libre."
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
moment_path = st.text_input(
    "BestMomentPlan F10",
    r"E:\IA\MPT-Phase10-Evidence\20260821-220245\real-best-moment-plan.json",
)

st.markdown(
    "Semillas normalizadas. Ejemplo: "
    '`[{"scene_number":1,"subject_label":"Luna",'
    '"bbox":{"x":0.4,"y":0.3,"width":0.2,"height":0.2},'
    '"source":"MANUAL"}]`'
)

seeds_json = st.text_area("Tracking seeds JSON", "[]", height=130)
sample_rate = st.slider(
    "Puntos de trayectoria por segundo",
    min_value=0.5,
    max_value=5.0,
    value=2.0,
    step=0.5,
)
save_path = st.text_input("Guardar TrackingPlan (opcional)", "")


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
    moment = BestMomentPlan.model_validate_json(
        Path(moment_path).read_text(encoding="utf-8")
    )

    video_base = VideoBasePlanner().build(
        VideoBasePlanRequest(
            plan=plan,
            materials=materials,
            render_mode=VideoBaseRenderMode.REVIEW_PARTIAL,
            requested_codec="h264_nvenc",
        )
    )

    raw_seeds = json.loads(seeds_json)
    seeds = [TrackingSeed.model_validate(item) for item in raw_seeds]

    return AstronomicalTrackingRequest(
        video_base=video_base,
        story_graph=graph,
        shot_quality=quality,
        best_moment=moment,
        seeds=seeds,
        sample_rate_hz=sample_rate,
    )


if st.button("Trackear objeto", type="primary"):
    try:
        result = AstronomicalObjectTracker().build(load_request())

        a, b, c, d = st.columns(4)
        a.metric("Track completo", result.tracked_count)
        b.metric("Track parcial", result.partial_count)
        c.metric("Semilla requerida", result.seed_required_count)
        d.metric("Puntos", result.tracking_point_count)

        st.dataframe(
            [
                {
                    "scene": scene.scene_number,
                    "status": scene.status.value,
                    "subject": scene.subject_label,
                    "points": len(scene.points),
                    "backend": scene.backend,
                    "warnings": ", ".join(scene.warnings),
                }
                for scene in result.scenes
            ],
            use_container_width=True,
        )

        st.code(result.tracking_hash)

        if save_path.strip():
            target = Path(save_path.strip())
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(
                result.model_dump_json(indent=2),
                encoding="utf-8",
            )
            st.success(f"Plan guardado: {target}")

        st.json(result.model_dump(mode="json"))

    except (
        OSError,
        ValueError,
        json.JSONDecodeError,
        AstronomicalTrackingError,
    ) as exc:
        st.error(str(exc))
