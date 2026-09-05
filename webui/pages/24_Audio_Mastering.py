from __future__ import annotations

import json

import streamlit as st

from app.models.audio_mastering import AudioMasteringRequest
from app.models.sound_design import SoundDesignPlan
from app.models.voice_studio import VoiceStudioPlan
from app.services.audio_mastering import AudioMasteringError, build_audio_mastering


st.set_page_config(page_title="F24 · El Centinela", layout="wide")
st.title("F24 · Audio Mastering")
st.caption(
    "Construye el plan técnico de mastering a partir de F23 + F22. "
    "F24 no modifica audio ni ejecuta FFmpeg."
)

st.info(
    "Objetivo contractual del proyecto: -16 LUFS, -1 dBTP y loudnorm a dos "
    "pasadas cuando existan entradas de audio reales. Este batch sólo planifica."
)

voice_file = st.file_uploader(
    "F23 · VoiceStudioPlan JSON",
    type=["json"],
    key="f24-voice",
)
sound_file = st.file_uploader(
    "F22 · SoundDesignPlan JSON",
    type=["json"],
    key="f24-sound",
)


def _load(uploaded, model, label: str):
    if uploaded is None:
        raise AudioMasteringError(f"falta {label}")
    payload = json.loads(uploaded.getvalue().decode("utf-8"))
    return model.model_validate(payload)


def _render(plan) -> None:
    st.warning(
        f"{plan.status.value} · Plan técnico disponible; "
        "No se ha masterizado audio."
    )

    st.metric("Objetivo de loudness", f"{plan.target_i_lufs:.1f} LUFS")
    st.metric("True peak máximo", f"{plan.target_tp_dbtp:.1f} dBTP")
    st.metric("LRA objetivo", f"{plan.target_lra_lu:.1f} LU")
    st.write(f"Perfil: {plan.profile}")
    st.write(f"Método previsto: {plan.normalization_method}")
    st.caption(
        "Los objetivos son del proyecto y no constituyen una garantía de "
        "normalización idéntica en todas las plataformas."
    )

    st.subheader("Readiness de entradas")
    with st.container(border=True):
        st.write(
            "Audio de voz listo: "
            + ("sí" if plan.voice_audio_ready else "no")
        )
        st.write(
            "Assets de sonido listos: "
            + ("sí" if plan.sound_assets_ready else "no")
        )
        st.write(
            "Mastering listo: "
            + ("sí" if plan.mastering_ready else "no")
        )

    st.error(
        "MASTERING_NOT_EXECUTED · F24 no ha creado ni modificado ningún archivo "
        "de audio."
    )

    with st.expander("Trazabilidad y guardrails", expanded=False):
        st.write(f"Hash F24: {plan.audio_mastering_hash}")
        st.write(f"Generado UTC: {plan.generated_at_utc.isoformat()}")
        st.write(f"Planning only: {plan.planning_only}")
        st.write(f"Resource class: {plan.resource_class}")
        st.write(f"Platform guarantee: {plan.platform_guarantee}")
        st.write(f"Uses LLM: {plan.uses_llm}")
        st.write(f"GPU required: {plan.gpu_required}")
        st.write(f"Renders audio: {plan.renders_audio}")
        st.write(f"Modifies audio: {plan.modifies_audio}")
        st.write(f"FFmpeg invocations: {plan.ffmpeg_invocations}")
        st.write(f"Auto publication: {plan.auto_publication}")


if st.button("Construir plan de mastering", type="primary"):
    try:
        request = AudioMasteringRequest(
            voice_studio=_load(
                voice_file,
                VoiceStudioPlan,
                "F23 VoiceStudioPlan",
            ),
            sound_design=_load(
                sound_file,
                SoundDesignPlan,
                "F22 SoundDesignPlan",
            ),
        )
        _render(build_audio_mastering(request))
    except Exception as exc:
        st.error(
            "No se ha podido construir el plan F24. "
            "No se ha ejecutado FFmpeg ni modificado audio."
        )
        with st.expander("Detalles técnicos", expanded=False):
            st.code(f"{type(exc).__name__}: {exc}", language=None)
