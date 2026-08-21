from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


from app.models.astronomy_director import AstronomyVideoPlan  # noqa: E402
from app.models.material_selection import MaterialSelectionPlan  # noqa: E402
from app.models.master_image_i2v import MasterImageI2VRequest  # noqa: E402
from app.models.smart_ken_burns import SmartKenBurnsPlan  # noqa: E402
from app.models.video_base import VideoBasePlanRequest, VideoBaseRenderMode  # noqa: E402
from app.models.visual_story_graph import VisualStoryGraph  # noqa: E402
from app.services.master_image_i2v import (  # noqa: E402
    MasterImageI2VError,
    MasterImageI2VPlanner,
)
from app.services.video_base_planner import VideoBasePlanner  # noqa: E402


st.set_page_config(
    page_title="Master Image → I2V · El Centinela",
    layout="wide",
)
st.title("Master Image → I2V · El Centinela del Universo")
st.caption(
    "Fase 14 · Prepara jobs I2V auditables. No invoca WanGP, no descarga "
    "modelos y exige aprobación explícita por escena."
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
ken_path = st.text_input(
    "SmartKenBurnsPlan F13",
    r"E:\IA\MPT-Phase13-Evidence\20260821-224621\real-smart-ken-burns-plan.json",
)

approved_text = st.text_input(
    "Escenas con aprobación explícita para IA (ej. 2,4)",
    "",
)
save_path = st.text_input("Guardar MasterImageI2VPlan (opcional)", "")


def parse_approved(value: str) -> list[int]:
    if not value.strip():
        return []
    return [
        int(item.strip())
        for item in value.split(",")
        if item.strip()
    ]


if st.button("Preparar jobs I2V", type="primary"):
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
        ken = SmartKenBurnsPlan.model_validate_json(
            Path(ken_path).read_text(encoding="utf-8")
        )

        video_base = VideoBasePlanner().build(
            VideoBasePlanRequest(
                plan=plan,
                materials=materials,
                render_mode=VideoBaseRenderMode.REVIEW_PARTIAL,
                requested_codec="h264_nvenc",
            )
        )

        result = MasterImageI2VPlanner().build(
            MasterImageI2VRequest(
                video_base=video_base,
                story_graph=graph,
                ken_burns=ken,
                approved_scene_numbers=parse_approved(approved_text),
            )
        )

        a, b, c, d = st.columns(4)
        a.metric("Master faltante", result.master_image_required_count)
        b.metric("Pendientes aprobación", result.approval_pending_count)
        c.metric("Jobs listos", result.job_ready_count)
        d.metric("Bloqueados derechos", result.rights_blocked_count)

        st.warning(
            "F14 no genera vídeo. Un job I2V listo sólo autoriza el handoff "
            "a F15. Todo resultado futuro debe etiquetarse como "
            "RECREACION_VISUAL."
        )

        st.dataframe(
            [
                {
                    "scene": scene.scene_number,
                    "status": scene.status.value,
                    "media_type": (
                        scene.media_type.value
                        if scene.media_type is not None
                        else None
                    ),
                    "approved": scene.approved,
                    "handoff_ready": scene.handoff_ready,
                    "review": scene.review_required,
                    "job": scene.job is not None,
                    "warnings": ", ".join(scene.warnings),
                }
                for scene in result.scenes
            ],
            use_container_width=True,
        )

        st.code(result.i2v_plan_hash)

        if save_path.strip():
            target = Path(save_path.strip())
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(
                result.model_dump_json(indent=2),
                encoding="utf-8",
            )
            st.success(f"Plan guardado: {target}")

        st.json(result.model_dump(mode="json"))

    except (OSError, ValueError, MasterImageI2VError) as exc:
        st.error(str(exc))
