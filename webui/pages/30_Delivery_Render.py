from __future__ import annotations

import json

import streamlit as st

from app.models.delivery_render import (
    DeliveryRenderPlan,
    DeliveryRenderRequest,
    DeliveryRenderStatus,
    FFmpegCapabilityHint,
)
from app.models.quality_gates import QualityGatesPlan
from app.services.delivery_render import build_delivery_render


st.set_page_config(page_title="F30 · El Centinela", layout="wide")
st.title("F30 · Delivery Render")
st.caption(
    "Prepara el plan contractual de entrega desde F29 y evidencia de capacidad FFmpeg. "
    "F30 no ejecuta FFmpeg, no renderiza vídeo y no certifica físicamente codecs ni GPU."
)

st.info(
    "MASTER y SOCIAL se planifican siempre desde las fuentes originales. "
    "READY_FOR_EXPLICIT_RENDER_APPROVAL significa que el plan puede pasar a una "
    "aprobación humana explícita; no significa que el vídeo esté renderizado."
)

quality_file = st.file_uploader(
    "F29 · QualityGatesPlan JSON",
    type=["json"],
    key="f30-quality-gates",
)

st.subheader("Evidencia de capacidad FFmpeg")
st.caption(
    "Introduce únicamente evidencia ya observada fuera de F30. "
    "Esta página no ejecuta probes, comandos shell ni detección de hardware."
)

ffmpeg_present = st.checkbox(
    "FFmpeg indicado como presente",
    value=False,
    key="f30-ffmpeg-present",
)
ffmpeg_version = st.text_input(
    "Versión FFmpeg observada (opcional)",
    value="",
    key="f30-ffmpeg-version",
)
h264_nvenc_listed = st.checkbox(
    "h264_nvenc indicado como listado",
    value=False,
    key="f30-nvenc-listed",
)
libx264_listed = st.checkbox(
    "libx264 indicado como listado",
    value=False,
    key="f30-libx264-listed",
)

_probe_options = {
    "Sin evidencia": None,
    "Probe indicado como PASS": True,
    "Probe indicado como FAIL": False,
}
nvenc_master_probe_label = st.selectbox(
    "NVENC MASTER · evidencia de probe",
    options=list(_probe_options),
    index=0,
    key="f30-nvenc-master-probe",
)
nvenc_social_probe_label = st.selectbox(
    "NVENC SOCIAL · evidencia de probe",
    options=list(_probe_options),
    index=0,
    key="f30-nvenc-social-probe",
)
capability_probe_invocations = st.number_input(
    "Número de probes declarados en la evidencia",
    min_value=0,
    step=1,
    value=0,
    key="f30-capability-probe-invocations",
    help="Dato descriptivo aportado al capability hint; F30 no ejecuta estos probes.",
)


def _load_quality_gates() -> QualityGatesPlan:
    if quality_file is None:
        raise ValueError("falta F29 QualityGatesPlan")
    payload = json.loads(quality_file.getvalue().decode("utf-8"))
    return QualityGatesPlan.model_validate(payload)


def _status_copy(status: DeliveryRenderStatus) -> tuple[str, str]:
    mapping = {
        DeliveryRenderStatus.BLOCKED_BY_QUALITY_GATES: (
            "BLOCKED",
            "F29 o la evidencia mínima de FFmpeg todavía no permiten preparar "
            "una aprobación explícita de render.",
        ),
        DeliveryRenderStatus.READY_FOR_EXPLICIT_RENDER_APPROVAL: (
            "READY FOR EXPLICIT RENDER APPROVAL",
            "El plan contractual está preparado para una aprobación humana explícita. "
            "No se ha renderizado ningún archivo.",
        ),
    }
    return mapping[status]


def _render_profile(profile) -> None:
    with st.container(border=True):
        st.markdown(f"### {profile.profile_id}")
        st.write(f"Resolución: {profile.width} × {profile.height}")
        st.write(f"FPS: {profile.fps}")
        st.write(f"Estrategia de fuente: {profile.source_strategy}")
        st.write(f"Codec solicitado: {profile.requested_codec}")
        st.write(f"Codec candidato efectivo: {profile.effective_codec_candidate}")
        st.write(f"Fallback contractual: {profile.fallback_codec}")
        st.write(f"Pixel format: {profile.pixel_format}")
        st.write(f"Execution ready: {profile.execution_ready}")
        st.caption(
            "El codec mostrado es un candidato contractual calculado por el backend. "
            "No constituye certificación física del encoder."
        )


def _render_result(plan: DeliveryRenderPlan) -> None:
    label, detail = _status_copy(plan.status)
    if plan.status == DeliveryRenderStatus.BLOCKED_BY_QUALITY_GATES:
        st.warning(f"{label} · {detail}")
    elif plan.status == DeliveryRenderStatus.READY_FOR_EXPLICIT_RENDER_APPROVAL:
        st.success(f"{label} · {detail}")
    else:
        st.error(f"Estado F30 no soportado: {plan.status}")
        return

    st.subheader("Perfiles de salida")
    for profile in plan.profiles:
        _render_profile(profile)

    st.subheader("Frontera de ejecución")
    with st.container(border=True):
        st.write("Render real: **NO EJECUTADO**")
        st.write(
            "Aprobación humana de render: "
            + ("**REQUERIDA**" if plan.human_render_approval_required else "**NO**")
        )
        st.write(f"Project render invocations: {plan.project_render_invocations}")
        st.write(f"Renders project video: {plan.renders_project_video}")
        st.write(f"Upscales social to master: {plan.upscales_social_to_master}")
        st.write(
            "Certificación física FFmpeg/NVENC/libx264: **PENDIENTE_PC**"
        )

    st.subheader("Evidencia consumida")
    with st.container(border=True):
        st.write(f"FFmpeg presente según hint: {plan.ffmpeg_present}")
        st.write(f"Versión declarada: {plan.ffmpeg_version or 'sin evidencia'}")
        st.write(f"h264_nvenc listado según hint: {plan.h264_nvenc_listed}")
        st.write(f"libx264 listado según hint: {plan.libx264_listed}")
        st.write(f"NVENC MASTER probe: {plan.nvenc_master_probe_success}")
        st.write(f"NVENC SOCIAL probe: {plan.nvenc_social_probe_success}")
        st.write(f"Probes declarados: {plan.capability_probe_invocations}")

    with st.expander("Detalles técnicos", expanded=False):
        st.write(f"Estado backend: {plan.status.value}")
        st.write(f"Hash F30: {plan.delivery_render_hash}")
        st.write(f"Hash F29 origen: {plan.source_quality_gates_hash}")
        st.write(f"Context hash: {plan.source_plan_context_hash}")
        st.write(f"Generated UTC: {plan.generated_at_utc.isoformat()}")
        st.write(f"Planning only: {plan.planning_only}")
        st.write(f"Resource class: {plan.resource_class}")
        st.write(f"Uses LLM: {plan.uses_llm}")
        st.write(f"Downloads dependencies: {plan.downloads_dependencies}")
        st.write(f"Auto publication: {plan.auto_publication}")
        st.write(
            f"Human render approval required: {plan.human_render_approval_required}"
        )

    st.caption(
        "F30 termina en DeliveryRenderPlan. No llama F51 automáticamente, no crea "
        "estados downstream y no autoriza publicación."
    )


if st.button("Preparar plan de render", type="primary"):
    try:
        request = DeliveryRenderRequest(
            quality_gates=_load_quality_gates(),
            ffmpeg=FFmpegCapabilityHint(
                ffmpeg_present=ffmpeg_present,
                ffmpeg_version=ffmpeg_version.strip() or None,
                h264_nvenc_listed=h264_nvenc_listed,
                libx264_listed=libx264_listed,
                nvenc_social_probe_success=_probe_options[nvenc_social_probe_label],
                nvenc_master_probe_success=_probe_options[nvenc_master_probe_label],
                capability_probe_invocations=int(capability_probe_invocations),
            ),
        )
        _render_result(build_delivery_render(request))
    except Exception as exc:
        st.error(
            "No se ha podido preparar el plan F30. El flujo permanece fail-closed: "
            "no se ha ejecutado render, no se ha certificado ningún encoder y no se "
            "ha avanzado a F51."
        )
        with st.expander("Detalles técnicos", expanded=False):
            st.code(f"{type(exc).__name__}: {exc}", language=None)
