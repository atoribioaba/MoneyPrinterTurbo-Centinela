from __future__ import annotations

import json

import streamlit as st

from app.models.astronomy_director import AstronomyVideoPlan
from app.models.sound_design import SoundDesignPlan
from app.models.voice_studio import VoiceStudioRequest
from app.services.voice_studio import VoiceStudioError, build_voice_studio


st.set_page_config(page_title="F23 · El Centinela", layout="wide")
st.title("F23 · Voice Studio")
st.caption(
    "Planifica narración y requisitos de voz a partir de F3 + F22. "
    "F23 no sintetiza audio ni selecciona una voz real."
)

st.info(
    "**Frontera de runtime:** la voz real y el TTS siguen pendientes de ejecución "
    "local. El contrato prioriza español de España, voz masculina y timestamps "
    "nativos del TTS, con selección humana explícita."
)

plan_file = st.file_uploader(
    "F3 · AstronomyVideoPlan JSON",
    type=["json"],
    key="f23-plan",
)
sound_file = st.file_uploader(
    "F22 · SoundDesignPlan JSON",
    type=["json"],
    key="f23-sound",
)


def _load(uploaded, model, label: str):
    if uploaded is None:
        raise VoiceStudioError(f"falta {label}")
    payload = json.loads(uploaded.getvalue().decode("utf-8"))
    return model.model_validate(payload)


def _render(plan) -> None:
    st.success("Plan de voz construido. No se ha sintetizado audio.")

    st.metric("Escenas", plan.scene_count)
    st.metric(
        "Selecciones de voz pendientes",
        plan.voice_selection_required_count,
    )
    st.write(f"Backend contractual: {plan.backend_family}")
    st.write(f"Candidato preferido: {plan.preferred_candidate}")
    st.caption(
        "El candidato preferido no equivale a una voz seleccionada ni a runtime "
        "TTS certificado."
    )

    st.subheader("Narración por escena")
    for utterance in plan.utterances:
        with st.container(border=True):
            st.markdown(f"### Escena {utterance.scene_number}")
            st.write(utterance.narration)
            st.write(f"Locale: {utterance.locale}")
            st.write(f"Género preferido: {utterance.preferred_gender}")
            st.write(f"Estado: {utterance.status.value}")
            st.write(
                "Voz exacta seleccionada: "
                + (utterance.exact_voice_id or "ninguna")
            )
            st.write(
                "Selección humana requerida: "
                + ("sí" if utterance.voice_selection_required else "no")
            )
            st.write(f"Política de timestamps: {utterance.timestamp_policy.value}")
            if utterance.astronomy_terms:
                st.write(
                    "Términos astronómicos: "
                    + ", ".join(utterance.astronomy_terms)
                )

    st.warning(
        "VOICE_SELECTION_REQUIRED · El plan no genera audio y no fija "
        "exact_voice_id. REAL_TTS permanece PENDING_PC / NOT_EXECUTED."
    )

    with st.expander("Trazabilidad y guardrails", expanded=False):
        st.write(f"Hash F23: {plan.voice_studio_hash}")
        st.write(f"Generado UTC: {plan.generated_at_utc.isoformat()}")
        st.write(f"Planning only: {plan.planning_only}")
        st.write(f"Resource class: {plan.resource_class}")
        st.write(f"Uses LLM: {plan.uses_llm}")
        st.write(f"GPU required: {plan.gpu_required}")
        st.write(f"Generates audio: {plan.generates_audio}")
        st.write(f"TTS invocations: {plan.tts_invocations}")
        st.write(f"Network calls: {plan.network_calls}")
        st.write(f"Downloads models: {plan.downloads_models}")
        st.write(f"Auto publication: {plan.auto_publication}")


if st.button("Construir plan de voz", type="primary"):
    try:
        request = VoiceStudioRequest(
            plan=_load(plan_file, AstronomyVideoPlan, "F3 AstronomyVideoPlan"),
            sound_design=_load(
                sound_file,
                SoundDesignPlan,
                "F22 SoundDesignPlan",
            ),
        )
        _render(build_voice_studio(request))
    except Exception as exc:
        st.error(
            "No se ha podido construir el plan F23. "
            "No se ha seleccionado voz ni generado audio."
        )
        with st.expander("Detalles técnicos", expanded=False):
            st.code(f"{type(exc).__name__}: {exc}", language=None)
