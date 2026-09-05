from __future__ import annotations

import json

import streamlit as st

from app.models.delivery_render import DeliveryRenderPlan
from app.models.production_orchestrator import (
    HumanReviewState,
    ProductionOrchestratorRequest,
    ProductionOrchestratorStatus,
)
from app.models.quality_gates import QualityGatesPlan
from app.models.video_base import VideoBaseRenderManifest
from app.services.production_orchestrator import build_production_orchestrator


st.set_page_config(page_title="F51 · El Centinela", layout="wide")
st.title("F51 · Production Orchestrator")
st.caption(
    "Orquestación contractual sobre F29/F30/F6. F51 reutiliza resultados existentes: "
    "no renderiza, no aprueba revisión humana y no publica."
)

st.info(
    "**Autoridad limitada:** F51 decide qué etapa existente corresponde ejecutar después. "
    "No ejecuta F6, F52 ni F53, no fabrica estados downstream y no convierte una aprobación "
    "declarativa en autorización."
)

quality_file = st.file_uploader(
    "F29 · QualityGatesPlan JSON",
    type=["json"],
    key="f51-quality",
)
delivery_file = st.file_uploader(
    "F30 · DeliveryRenderPlan JSON",
    type=["json"],
    key="f51-delivery",
)
video_file = st.file_uploader(
    "F6 · VideoBaseRenderManifest JSON (opcional)",
    type=["json"],
    key="f51-video-base",
    help="Déjalo vacío cuando todavía no exista Video Base.",
)

human_review_value = st.selectbox(
    "Estado humano conocido",
    options=[
        HumanReviewState.PENDING.value,
        HumanReviewState.REJECTED.value,
    ],
    index=0,
    help=(
        "F51 no acepta APPROVED como declaración. La aprobación autoritativa pertenece "
        "a Finalization E2E con HumanFinalReviewRecord."
    ),
)


def _load_required(uploaded, model, label: str):
    if uploaded is None:
        raise ValueError(f"falta {label}")
    payload = json.loads(uploaded.getvalue().decode("utf-8"))
    return model.model_validate(payload)


def _load_optional_video():
    if video_file is None:
        return None
    payload = json.loads(video_file.getvalue().decode("utf-8"))
    return VideoBaseRenderManifest.model_validate(payload)


def _status_copy(status: ProductionOrchestratorStatus) -> tuple[str, str]:
    mapping = {
        ProductionOrchestratorStatus.BLOCKED_BY_QUALITY_OR_DELIVERY: (
            "BLOCKED",
            "Resuelve primero los gates F29/F30 existentes.",
        ),
        ProductionOrchestratorStatus.READY_FOR_VIDEO_BASE: (
            "READY FOR VIDEO BASE",
            "La siguiente autoridad es el renderer F6 existente.",
        ),
        ProductionOrchestratorStatus.HUMAN_REVIEW_REJECTED: (
            "HUMAN REVIEW REJECTED",
            "Vuelve al pipeline creativo existente.",
        ),
        ProductionOrchestratorStatus.WAITING_FOR_HUMAN_REVIEW: (
            "WAITING FOR HUMAN REVIEW",
            "Continúa por F52 y después F53; F51 no decide la aprobación.",
        ),
    }
    return mapping[status]


def _render_result(plan) -> None:
    label, detail = _status_copy(plan.status)
    if plan.status == ProductionOrchestratorStatus.BLOCKED_BY_QUALITY_OR_DELIVERY:
        st.error(f"{label} · {detail}")
    elif plan.status == ProductionOrchestratorStatus.HUMAN_REVIEW_REJECTED:
        st.warning(f"{label} · {detail}")
    else:
        st.success(f"{label} · {detail}")

    with st.container(horizontal=True, gap="medium"):
        st.metric("Quality ready", "sí" if plan.quality_ready else "no")
        st.metric("Delivery ready", "sí" if plan.delivery_ready else "no")
        st.metric("Video Base presente", "sí" if plan.video_base_present else "no")
        st.metric("Review state", plan.human_review_state.value)

    st.subheader("Siguiente acción contractual")
    st.code(plan.next_action, language=None)

    with st.expander("Trazabilidad y guardrails", expanded=False):
        st.write(f"Estado backend: {plan.status.value}")
        st.write(f"Hash F51: {plan.production_orchestrator_hash}")
        st.write(f"Generado UTC: {plan.generated_at_utc.isoformat()}")
        st.write(f"Orchestration only: {plan.orchestration_only}")
        st.write(f"Resource class: {plan.resource_class}")
        st.write(f"Invoca render: {plan.invokes_render}")
        st.write(f"Invoca LLM: {plan.invokes_llm}")
        st.write(f"Invoca red: {plan.invokes_network}")
        st.write(f"Writes runtime config: {plan.writes_runtime_config}")
        st.write(f"Auto publication: {plan.auto_publication}")
        st.write(f"Authorization to publish: {plan.authorization_to_publish}")
        st.write(f"Uploads files: {plan.uploads_files}")
        st.write(f"Webhook calls: {plan.webhook_calls}")
        st.write(f"Marks published: {plan.marks_published}")
        st.write(f"Finalization complete: {plan.finalization_complete}")
        st.write(
            f"Publication package complete: {plan.publication_package_complete}"
        )

    st.caption(
        "F51 sólo orquesta contratos ya existentes. La revisión humana autoritativa, "
        "la finalización y el paquete de publicación pertenecen a sus fases downstream."
    )


if st.button("Evaluar orquestación", type="primary"):
    try:
        request = ProductionOrchestratorRequest(
            quality_gates=_load_required(
                quality_file,
                QualityGatesPlan,
                "F29 QualityGatesPlan",
            ),
            delivery=_load_required(
                delivery_file,
                DeliveryRenderPlan,
                "F30 DeliveryRenderPlan",
            ),
            video_base_manifest=_load_optional_video(),
            human_review_state=HumanReviewState(human_review_value),
        )
        plan = build_production_orchestrator(request)
        _render_result(plan)
    except Exception as exc:
        st.error(
            "No se ha podido evaluar la orquestación. "
            "No se ha ejecutado render, revisión, finalización ni publicación."
        )
        with st.expander("Detalles técnicos", expanded=False):
            st.code(f"{type(exc).__name__}: {exc}", language=None)
