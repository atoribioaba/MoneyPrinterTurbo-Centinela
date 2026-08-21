from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


from app.models.astronomy_director import AstronomyVideoPlan  # noqa: E402
from app.models.material_selection import MaterialSelectionPlan  # noqa: E402
from app.models.schema import VideoFitMode  # noqa: E402
from app.models.video_base import (  # noqa: E402
    VideoBasePlanRequest,
    VideoBaseRenderMode,
)
from app.services.video_base_planner import (  # noqa: E402
    VideoBasePlanBlockedError,
    VideoBasePlanError,
    VideoBasePlanner,
)
from app.services.video_base_renderer import (  # noqa: E402
    FFmpegSceneRenderer,
    VideoBaseRenderError,
)


st.set_page_config(page_title="Video Base · El Centinela", layout="wide")
st.title("Video Base V1 · El Centinela del Universo")
st.caption(
    "Fase 6 · AstronomyVideoPlan + MaterialSelectionPlan → FFmpeg determinista"
)

plan_path = st.text_input(
    "AstronomyVideoPlan JSON",
    r"E:\IA\MPT-Phase3-Evidence\20260821-142904\real-astronomy-video-plan.json",
)
materials_path = st.text_input(
    "MaterialSelectionPlan JSON",
    r"E:\IA\MPT-Phase5-Evidence\20260821-183036\real-material-selection-plan.json",
)

c1, c2, c3 = st.columns(3)
render_mode = c1.selectbox(
    "Modo",
    [mode.value for mode in VideoBaseRenderMode],
    index=0,
)
fit_mode = c2.selectbox(
    "Fit",
    [mode.value for mode in VideoFitMode],
    index=0,
)
codec = c3.selectbox("Codec preferido", ["h264_nvenc", "libx264"], index=0)

f1, f2 = st.columns(2)
focal_x = f1.slider("Focal X", 0.0, 1.0, 0.5, 0.01)
focal_y = f2.slider("Focal Y", 0.0, 1.0, 0.5, 0.01)
keep_segments = st.checkbox("Conservar segmentos normalizados", True)


def load_request():
    plan = AstronomyVideoPlan.model_validate_json(
        Path(plan_path).read_text(encoding="utf-8")
    )
    materials = MaterialSelectionPlan.model_validate_json(
        Path(materials_path).read_text(encoding="utf-8")
    )
    return VideoBasePlanRequest(
        plan=plan,
        materials=materials,
        render_mode=VideoBaseRenderMode(render_mode),
        default_fit_mode=VideoFitMode(fit_mode),
        focal_x=focal_x,
        focal_y=focal_y,
        requested_codec=codec,
    )


if st.button("Planificar F6", type="secondary"):
    try:
        result = VideoBasePlanner().build(load_request())
        a, b, c = st.columns(3)
        a.metric("Escenas", result.scene_count)
        b.metric("Placeholders", result.placeholder_count)
        c.metric("CLEAN_BASE elegible", str(result.clean_base_eligible))
        st.json(result.model_dump(mode="json"))
    except (OSError, ValueError, VideoBasePlanError) as exc:
        st.error(str(exc))


if st.button("Renderizar Video Base", type="primary"):
    try:
        with st.spinner("Renderizando F6..."):
            planned = VideoBasePlanner().build(load_request())
            result = FFmpegSceneRenderer().render(
                planned,
                keep_segments=keep_segments,
            )
        st.success("Video Base generado y validado")
        st.video(result.video_path)
        st.json(result.model_dump(mode="json"))
    except (
        OSError,
        ValueError,
        VideoBasePlanBlockedError,
        VideoBasePlanError,
        VideoBaseRenderError,
    ) as exc:
        st.error(str(exc))
