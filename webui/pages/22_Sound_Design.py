from __future__ import annotations

import json

import streamlit as st

from app.models.cinematic_infographics import CinematicInfographicsPlan
from app.models.sound_design import SoundDesignRequest
from app.models.transition_director import TransitionDirectorPlan
from app.models.visual_story_graph import VisualStoryGraph
from app.services.sound_design import SoundDesignError, build_sound_design


st.set_page_config(page_title="F22 · El Centinela", layout="wide")
st.title("F22 · Sound Design")
st.caption(
    "Diseña cues no diegéticos a partir de F8 + F17 + F21. "
    "No genera audio, no selecciona assets y no inventa licencias."
)

st.info(
    "**Frontera de derechos:** F22 deja cada cue sin asset y con "
    "`LICENCIA_NO_VERIFICADA` hasta que exista selección humana de material."
)

story_file = st.file_uploader(
    "F8 · VisualStoryGraph JSON",
    type=["json"],
    key="f22-story",
)
info_file = st.file_uploader(
    "F17 · CinematicInfographicsPlan JSON",
    type=["json"],
    key="f22-info",
)
transition_file = st.file_uploader(
    "F21 · TransitionDirectorPlan JSON",
    type=["json"],
    key="f22-transitions",
)


def _load(uploaded, model, label: str):
    if uploaded is None:
        raise SoundDesignError(f"falta {label}")
    payload = json.loads(uploaded.getvalue().decode("utf-8"))
    return model.model_validate(payload)


def _render(plan) -> None:
    st.success("Plan de diseño sonoro construido sin seleccionar ni generar audio.")

    with st.container(horizontal=True, gap="medium"):
        st.metric("Escenas", plan.scene_count)
        st.metric("Cues", plan.cue_count)
        st.metric("Assets seleccionados", plan.asset_count)
        st.metric("Acentos de clímax", plan.climax_accent_count)

    st.subheader("Cues")
    for cue in plan.cues:
        with st.container(border=True):
            st.markdown(f"### Escena {cue.scene_number} · {cue.cue_type.value}")
            st.write(f"Perfil: {cue.design_profile}")
            st.write(f"Intensidad: {cue.intensity:.3f}")
            st.write(f"Rol: {cue.role.value}")
            st.write(f"Asset seleccionado: {'sí' if cue.asset_selected else 'no'}")
            st.write(f"Licencia: {cue.license_status}")
            st.write(
                "Requiere selección humana: "
                + ("sí" if cue.requires_human_selection else "no")
            )
            st.write(
                "Sonido diegético en vacío: "
                + ("sí" if cue.diegetic_space_sound else "no")
            )

    with st.expander("Trazabilidad y guardrails", expanded=False):
        st.write(f"Hash F22: {plan.sound_design_hash}")
        st.write(f"Generado UTC: {plan.generated_at_utc.isoformat()}")
        st.write(f"Planning only: {plan.planning_only}")
        st.write(f"Resource class: {plan.resource_class}")
        st.write(f"Uses LLM: {plan.uses_llm}")
        st.write(f"GPU required: {plan.gpu_required}")
        st.write(f"Renders audio: {plan.renders_audio}")
        st.write(f"Generates audio: {plan.generates_audio}")
        st.write(f"Downloads audio: {plan.downloads_audio}")
        st.write(f"Searches audio: {plan.searches_audio}")
        st.write(f"Selects assets: {plan.selects_assets}")
        st.write(
            f"Verifies external licenses: {plan.verifies_external_licenses}"
        )
        st.write(f"Auto publication: {plan.auto_publication}")

    st.caption(
        "F22 es planificación de intención sonora. La elección de assets, licencia y mezcla "
        "pertenecen a fases posteriores con revisión humana."
    )


if st.button("Construir diseño sonoro", type="primary"):
    try:
        request = SoundDesignRequest(
            story_graph=_load(story_file, VisualStoryGraph, "F8 VisualStoryGraph"),
            infographics=_load(
                info_file,
                CinematicInfographicsPlan,
                "F17 CinematicInfographicsPlan",
            ),
            transitions=_load(
                transition_file,
                TransitionDirectorPlan,
                "F21 TransitionDirectorPlan",
            ),
        )
        _render(build_sound_design(request))
    except Exception as exc:
        st.error(
            "No se ha podido construir el plan F22. "
            "No se ha generado, descargado ni seleccionado audio."
        )
        with st.expander("Detalles técnicos", expanded=False):
            st.code(f"{type(exc).__name__}: {exc}", language=None)
