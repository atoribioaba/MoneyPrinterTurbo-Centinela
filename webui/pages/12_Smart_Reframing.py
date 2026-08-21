from __future__ import annotations

import json
import sys
from pathlib import Path

import streamlit as st


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


from app.models.astronomy_director import AstronomyVideoPlan  # noqa: E402
from app.models.astronomical_tracker import AstronomicalTrackingPlan  # noqa: E402
from app.models.best_moment import BestMomentPlan  # noqa: E402
from app.models.material_selection import MaterialSelectionPlan  # noqa: E402
from app.models.shot_quality import ShotQualityPlan  # noqa: E402
from app.models.smart_reframing import (  # noqa: E402
    SmartFocalHint,
    SmartReframingRequest,
)
from app.models.video_base import VideoBasePlanRequest, VideoBaseRenderMode  # noqa: E402
from app.models.visual_story_graph import VisualStoryGraph  # noqa: E402
from app.services.smart_reframing import (  # noqa: E402
    SmartReframingError,
    SmartReframingPlanner,
)
from app.services.video_base_planner import VideoBasePlanner  # noqa: E402


st.set_page_config(
    page_title="Smart Reframing 2.0 · El Centinela",
    layout="wide",
)
st.title("Smart Reframing 2.0 · El Centinela del Universo")
st.caption(
    "Fase 12 · F11 tracking → SmartFocal V0.1 → focal F6. "
    "Genera un plan de crop 9:16; todavía no renderiza."
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
tracking_path = st.text_input(
    "AstronomicalTrackingPlan F11",
    r"E:\IA\MPT-Phase11-Evidence\20260821-221324\real-astronomical-tracking-plan.json",
)

st.markdown(
    "Opcional: pega decisiones ya producidas por SmartFocal V0.1. "
    'Ejemplo: `[{"scene_number":1,"focal_x":0.8,"focal_y":0.5,'
    '"confidence":0.995,"method":"numpy_temporal_median_cover"}]`'
)
hints_json = st.text_area(
    "SmartFocal hints JSON",
    "[]",
    height=130,
)
save_path = st.text_input("Guardar SmartReframingPlan (opcional)", "")


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
    tracking = AstronomicalTrackingPlan.model_validate_json(
        Path(tracking_path).read_text(encoding="utf-8")
    )

    video_base = VideoBasePlanner().build(
        VideoBasePlanRequest(
            plan=plan,
            materials=materials,
            render_mode=VideoBaseRenderMode.REVIEW_PARTIAL,
            requested_codec="h264_nvenc",
        )
    )

    hints = [
        SmartFocalHint.model_validate(item)
        for item in json.loads(hints_json)
    ]

    return SmartReframingRequest(
        video_base=video_base,
        story_graph=graph,
        shot_quality=quality,
        best_moment=moment,
        tracking=tracking,
        smartfocal_hints=hints,
    )


if st.button("Planificar reencuadre", type="primary"):
    try:
        result = SmartReframingPlanner().build(load_request())

        a, b, c, d = st.columns(4)
        a.metric("Dinámicos F11", result.dynamic_tracking_count)
        b.metric("SmartFocal", result.static_smartfocal_count)
        c.metric("Fallback F6", result.static_f6_focal_count)
        d.metric("Keyframes", result.keyframe_count)

        st.dataframe(
            [
                {
                    "scene": scene.scene_number,
                    "status": scene.status.value,
                    "source": scene.focal_source.value,
                    "ready": scene.execution_ready,
                    "review": scene.review_required,
                    "keyframes": len(scene.keyframes),
                    "warnings": ", ".join(scene.warnings),
                }
                for scene in result.scenes
            ],
            use_container_width=True,
        )

        st.code(result.reframing_hash)

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
        SmartReframingError,
    ) as exc:
        st.error(str(exc))
