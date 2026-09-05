from __future__ import annotations

import json

import streamlit as st

from app.models.subtitle_intelligence import (
    NativeTimingCue,
    SubtitleIntelligenceRequest,
    SubtitleSceneStatus,
)
from app.models.voice_studio import VoiceStudioPlan
from app.services.subtitle_intelligence import (
    SubtitleIntelligenceError,
    build_subtitle_intelligence,
)


st.set_page_config(page_title="F25 · El Centinela", layout="wide")
st.title("F25 · Subtitle Intelligence")
st.caption(
    "Evalúa timestamps nativos del TTS antes que cualquier fallback. "
    "F25 no ejecuta Whisper ni descarga modelos."
)

st.info(
    "**Prioridad canónica:** NATIVE_TTS_BOUNDARIES_FIRST. Si faltan timestamps "
    "válidos, la escena espera; no se fabrican timings ni SRT."
)

voice_file = st.file_uploader(
    "F23 · VoiceStudioPlan JSON",
    type=["json"],
    key="f25-voice",
)
timing_file = st.file_uploader(
    "Timestamps nativos TTS JSON (lista opcional de NativeTimingCue)",
    type=["json"],
    key="f25-timings",
)


def _load_voice(uploaded):
    if uploaded is None:
        raise SubtitleIntelligenceError("falta F23 VoiceStudioPlan")
    payload = json.loads(uploaded.getvalue().decode("utf-8"))
    return VoiceStudioPlan.model_validate(payload)


def _load_cues(uploaded) -> list[NativeTimingCue]:
    if uploaded is None:
        return []
    payload = json.loads(uploaded.getvalue().decode("utf-8"))
    if not isinstance(payload, list):
        raise SubtitleIntelligenceError(
            "los timestamps nativos deben ser una lista JSON"
        )
    return [NativeTimingCue.model_validate(item) for item in payload]


def _render(plan) -> None:
    if plan.waiting_count:
        st.warning(
            "TIMESTAMPS_PENDING · Hay escenas en "
            "WAITING_NATIVE_TTS_TIMESTAMPS. F25 no ejecuta Whisper."
        )
    else:
        st.success("NATIVE_TIMING_READY · Todas las escenas tienen timing nativo.")

    st.metric("Escenas", plan.scene_count)
    st.metric("Timing nativo listo", plan.native_ready_count)
    st.metric("Esperando timestamps", plan.waiting_count)
    st.metric("Cues nativos", plan.cue_count)

    st.write(f"Prioridad: {plan.timestamp_priority}")
    st.write(f"Fallback candidato: {plan.fallback_candidate}")
    st.caption(
        "El fallback es sólo una referencia contractual. "
        "whisper_triggered permanece FALSE en F25 V0.1."
    )

    st.subheader("Estado por escena")
    for scene in plan.scenes:
        with st.container(border=True):
            st.markdown(f"### Escena {scene.scene_number}")
            st.write(f"Estado: {scene.status.value}")
            st.write(f"Cues: {scene.cue_count}")
            st.write(
                "Fallback Whisper requerido: "
                + ("sí" if scene.whisper_fallback_required else "no")
            )
            if scene.status == SubtitleSceneStatus.NATIVE_TIMING_READY:
                for cue in scene.cues:
                    st.write(
                        f"{cue.start_s:.3f}s → {cue.end_s:.3f}s · {cue.text}"
                    )
            else:
                st.caption(
                    "Sin timestamps nativos válidos: se mantiene la espera."
                )

    with st.expander("Trazabilidad y guardrails", expanded=False):
        st.write(f"Hash F25: {plan.subtitle_intelligence_hash}")
        st.write(f"Generado UTC: {plan.generated_at_utc.isoformat()}")
        st.write(f"Planning only: {plan.planning_only}")
        st.write(f"Resource class: {plan.resource_class}")
        st.write(f"Timestamp priority: {plan.timestamp_priority}")
        st.write(f"Whisper triggered: {plan.whisper_triggered}")
        st.write(f"Downloads models: {plan.downloads_models}")
        st.write(f"Transcribes audio: {plan.transcribes_audio}")
        st.write(f"GPU required: {plan.gpu_required}")
        st.write(f"Auto publication: {plan.auto_publication}")


if st.button("Evaluar timestamps nativos", type="primary"):
    try:
        request = SubtitleIntelligenceRequest(
            voice_studio=_load_voice(voice_file),
            native_timing_cues=_load_cues(timing_file),
        )
        _render(build_subtitle_intelligence(request))
    except Exception as exc:
        st.error(
            "No se ha podido evaluar F25. "
            "No se ha ejecutado Whisper ni fabricado ningún timestamp."
        )
        with st.expander("Detalles técnicos", expanded=False):
            st.code(f"{type(exc).__name__}: {exc}", language=None)
