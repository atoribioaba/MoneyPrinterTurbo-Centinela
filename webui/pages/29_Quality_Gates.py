from __future__ import annotations

import json

import streamlit as st

from app.models.audio_mastering import AudioMasteringPlan
from app.models.quality_comparator import QualityComparatorPlan
from app.models.quality_gates import QualityGatesRequest, QualityGateStatus
from app.models.sound_design import SoundDesignPlan
from app.models.subtitle_intelligence import SubtitleIntelligencePlan
from app.models.voice_studio import VoiceStudioPlan
from app.services.quality_gates import QualityGatesError, build_quality_gates


st.set_page_config(page_title="F29 · El Centinela", layout="wide")
st.title("F29 · Quality Gates")
st.caption(
    "Evalúa gates técnicos de imagen, sonido, voz, mastering y subtítulos. "
    "F29 puede bloquear o permitir revisión humana; nunca aprueba contenido ni publica."
)

st.info(
    "READY_FOR_HUMAN_REVIEW significa únicamente que los checks técnicos han pasado. "
    "La aprobación humana sigue siendo obligatoria."
)

comparator_file = st.file_uploader(
    "F28 · QualityComparatorPlan JSON",
    type=["json"],
    key="f29-comparator",
)
sound_file = st.file_uploader(
    "F22 · SoundDesignPlan JSON",
    type=["json"],
    key="f29-sound",
)
voice_file = st.file_uploader(
    "F23 · VoiceStudioPlan JSON",
    type=["json"],
    key="f29-voice",
)
mastering_file = st.file_uploader(
    "F24 · AudioMasteringPlan JSON",
    type=["json"],
    key="f29-mastering",
)
subtitles_file = st.file_uploader(
    "F25 · SubtitleIntelligencePlan JSON",
    type=["json"],
    key="f29-subtitles",
)


def _load(uploaded, model, label: str):
    if uploaded is None:
        raise QualityGatesError(f"falta {label}")
    payload = json.loads(uploaded.getvalue().decode("utf-8"))
    return model.model_validate(payload)


def _render(plan) -> None:
    if plan.status == QualityGateStatus.BLOCKED:
        st.warning(
            "BLOCKED · Uno o más checks técnicos siguen pendientes. "
            "No se fabrica readiness para continuar."
        )
    elif plan.status == QualityGateStatus.READY_FOR_HUMAN_REVIEW:
        st.success(
            "READY_FOR_HUMAN_REVIEW · Gates técnicos superados. "
            "Esto NO es aprobación humana ni autorización para publicar."
        )
    else:
        st.error(f"Estado F29 no soportado: {plan.status}")

    st.metric("Checks", plan.check_count)
    st.metric("Superados", plan.passed_count)
    st.metric("Fallidos", plan.failed_count)

    st.subheader("Checks técnicos")
    for check in plan.checks:
        with st.container(border=True):
            st.markdown(f"### {'✓' if check.passed else '✗'} {check.check_id}")
            st.write("Resultado: " + ("PASS" if check.passed else "BLOCKED"))
            st.caption(check.detail)

    st.warning(
        "HUMAN_APPROVAL_REQUIRED · F29 no crea aprobación humana, no crea "
        "authorization_to_publish, no sube archivos, no usa webhooks y no marca publicado."
    )

    with st.expander("Detalles técnicos", expanded=False):
        st.write(f"Hash F29: {plan.quality_gates_hash}")
        st.write(f"Generated UTC: {plan.generated_at_utc.isoformat()}")
        st.write(f"Status: {plan.status.value}")
        st.write(f"Technical ready: {plan.technical_ready}")
        st.write(f"Human approval required: {plan.human_approval_required}")
        st.write(
            "Publication eligible after human approval: "
            f"{plan.publication_eligible_after_human_approval}"
        )
        st.write(f"Planning only: {plan.planning_only}")
        st.write(f"Renders media: {plan.renders_media}")
        st.write(f"Modifies media: {plan.modifies_media}")
        st.write(f"GPU required: {plan.gpu_required}")
        st.write(f"Auto publication: {plan.auto_publication}")
        st.write("Authorization to publish created: false")
        st.write("Uploads files: 0")
        st.write("Webhook calls: 0")
        st.write("Marks published: false")


if st.button("Evaluar gates F29", type="primary"):
    try:
        request = QualityGatesRequest(
            comparator=_load(
                comparator_file,
                QualityComparatorPlan,
                "F28 QualityComparatorPlan",
            ),
            sound_design=_load(sound_file, SoundDesignPlan, "F22 SoundDesignPlan"),
            voice_studio=_load(voice_file, VoiceStudioPlan, "F23 VoiceStudioPlan"),
            audio_mastering=_load(
                mastering_file,
                AudioMasteringPlan,
                "F24 AudioMasteringPlan",
            ),
            subtitles=_load(
                subtitles_file,
                SubtitleIntelligencePlan,
                "F25 SubtitleIntelligencePlan",
            ),
        )
        _render(build_quality_gates(request))
    except Exception as exc:
        st.error(
            "No se han podido evaluar los gates F29. "
            "El estado permanece fail-closed y no se ha creado ninguna aprobación."
        )
        with st.expander("Detalles técnicos", expanded=False):
            st.code(f"{type(exc).__name__}: {exc}", language=None)
