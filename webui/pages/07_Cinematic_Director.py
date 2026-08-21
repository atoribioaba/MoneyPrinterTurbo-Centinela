from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


from app.models.astronomy_director import AstronomyVideoPlan  # noqa: E402
from app.models.cinematic_director import (  # noqa: E402
    CinematicDirectorRequest,
    CinematicStyleProfile,
)
from app.models.material_selection import MaterialSelectionPlan  # noqa: E402
from app.models.video_base import VideoBasePlanRequest, VideoBaseRenderMode  # noqa: E402
from app.services.cinematic_director import (  # noqa: E402
    CinematicDirector,
    CinematicDirectorError,
)
from app.services.video_base_planner import (  # noqa: E402
    VideoBasePlanError,
    VideoBasePlanner,
)


st.set_page_config(
    page_title="Cinematic Director 2.0 · El Centinela",
    layout="wide",
)
st.title("Cinematic Director 2.0 · El Centinela del Universo")
st.caption(
    "Fase 7 · F3 AstronomyVideoPlan + F6 VideoBasePlan → "
    "dirección cinematográfica determinista. No renderiza vídeo."
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

profile = c1.selectbox(
    "Perfil cinematográfico",
    [profile.value for profile in CinematicStyleProfile],
    index=0,
)
intensity_bias = c2.slider(
    "Sesgo de intensidad",
    -0.20,
    0.20,
    0.00,
    0.01,
)
prefer_observation = c3.checkbox(
    "Priorizar observación sobre movimiento",
    True,
)

preserve_transition = st.checkbox(
    "Conservar transición F3 como referencia semántica",
    True,
)

save_path = st.text_input(
    "Guardar plan F7 (opcional)",
    "",
)


def build_request():
    plan = AstronomyVideoPlan.model_validate_json(
        Path(plan_path).read_text(encoding="utf-8")
    )
    materials = MaterialSelectionPlan.model_validate_json(
        Path(materials_path).read_text(encoding="utf-8")
    )

    video_base = VideoBasePlanner().build(
        VideoBasePlanRequest(
            plan=plan,
            materials=materials,
            render_mode=VideoBaseRenderMode.REVIEW_PARTIAL,
        )
    )

    return CinematicDirectorRequest(
        plan=plan,
        video_base=video_base,
        style_profile=CinematicStyleProfile(profile),
        intensity_bias=intensity_bias,
        prefer_observation_over_motion=prefer_observation,
        preserve_source_transition_intent=preserve_transition,
    )


if st.button("Planificar F7", type="primary"):
    try:
        result = CinematicDirector().build(build_request())

        a, b, c, d = st.columns(4)
        a.metric("Escenas", result.scene_count)
        b.metric("Placeholders", result.placeholder_count)
        c.metric("Clímax", result.climax_scene_number)
        d.metric("Perfil", result.style_profile.value)

        st.subheader("Curva de intensidad")
        st.line_chart(
            {
                "intensity": result.tension_curve,
            }
        )

        st.subheader("Dirección por escena")
        st.dataframe(
            [
                {
                    "scene": scene.scene_number,
                    "act": scene.act.value,
                    "role": scene.narrative_role.value,
                    "pace": scene.pace.value,
                    "intensity": scene.intensity,
                    "composition": scene.composition_intent.value,
                    "motion": scene.motion_intent.value,
                    "transition_out": scene.transition_out_intent.value,
                    "placeholder": scene.placeholder,
                }
                for scene in result.scenes
            ],
            use_container_width=True,
        )

        st.code(result.direction_hash)

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
        CinematicDirectorError,
        VideoBasePlanError,
    ) as exc:
        st.error(str(exc))
