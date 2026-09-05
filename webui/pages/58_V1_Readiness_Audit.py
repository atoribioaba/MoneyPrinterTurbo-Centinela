from __future__ import annotations

import json

import streamlit as st

from app.models.analytics_import_adapter import AnalyticsImportPlan
from app.models.golden_e2e_certification import GoldenE2ECertificationPlan
from app.models.operational_hardening import OperationalHardeningPlan
from app.models.production_orchestrator import ProductionOrchestratorPlan
from app.models.publication_package import PublicationPackagePlan
from app.models.v1_readiness_audit import (
    OSSAuditEntry,
    V1ReadinessRequest,
    V1ReadinessStatus,
)
from app.services.v1_readiness_audit import build_v1_readiness_audit


st.set_page_config(page_title="F58 · El Centinela", layout="wide")
st.title("F58 · V1 Readiness Audit")
st.caption(
    "Auditoría final fail-closed de los contratos V1. F58 puede autorizar un freeze "
    "tras aprobación humana explícita, pero nunca lo ejecuta."
)

st.warning(
    "**F57 sigue siendo evidencia real obligatoria.** Un Golden sintético no es aceptable. "
    "Si el plan F57 no está en CERTIFICATION_PASS, F58 debe permanecer NOT READY."
)


def _load_json(uploaded, model, label: str):
    if uploaded is None:
        raise ValueError(f"falta {label}")
    payload = json.loads(uploaded.getvalue().decode("utf-8"))
    return model.model_validate(payload)


orchestrator_file = st.file_uploader(
    "F51 · ProductionOrchestratorPlan JSON", type=["json"], key="f58-orchestrator"
)
publication_file = st.file_uploader(
    "F54 · PublicationPackagePlan JSON", type=["json"], key="f58-publication"
)
analytics_file = st.file_uploader(
    "F55 · AnalyticsImportPlan JSON", type=["json"], key="f58-analytics"
)
hardening_file = st.file_uploader(
    "F56 · OperationalHardeningPlan JSON", type=["json"], key="f58-hardening"
)
golden_file = st.file_uploader(
    "F57 · GoldenE2ECertificationPlan JSON", type=["json"], key="f58-golden"
)
oss_file = st.file_uploader(
    "Auditoría OSS JSON (lista de OSSAuditEntry)", type=["json"], key="f58-oss"
)

st.subheader("Aprobación humana de freeze")
st.caption(
    "Por defecto no existe autorización. La aprobación sólo se transmite al backend "
    "si se marca la casilla y se escribe exactamente la frase de confirmación."
)
human_approval_checked = st.checkbox(
    "Autorizo explícitamente el freeze de arquitectura V1",
    value=False,
    key="f58-human-freeze-check",
)
confirmation = st.text_input(
    "Confirmación",
    value="",
    placeholder="AUTORIZAR FREEZE V1",
    key="f58-human-freeze-text",
)
human_freeze_approval = bool(
    human_approval_checked and confirmation.strip() == "AUTORIZAR FREEZE V1"
)


def _load_oss():
    if oss_file is None:
        raise ValueError("falta auditoría OSS")
    payload = json.loads(oss_file.getvalue().decode("utf-8"))
    if not isinstance(payload, list):
        raise ValueError("la auditoría OSS debe ser una lista JSON")
    return [OSSAuditEntry.model_validate(item) for item in payload]


def _render_result(plan) -> None:
    if plan.status == V1ReadinessStatus.NOT_READY_FOR_ARCHITECTURE_FREEZE:
        st.error("NOT READY · Hay gates técnicos bloqueantes pendientes.")
    elif plan.status == V1ReadinessStatus.READY_FOR_HUMAN_FREEZE_APPROVAL:
        st.warning(
            "READY FOR HUMAN FREEZE APPROVAL · Los gates técnicos pasan; falta aprobación humana."
        )
    else:
        st.success(
            "ARCHITECTURE FREEZE AUTHORIZED · Autorizado, pero F58 NO ejecuta el freeze."
        )

    with st.container(horizontal=True, gap="medium"):
        st.metric("Checks", plan.check_count)
        st.metric("PASS", plan.passed_count)
        st.metric("FAIL", plan.failed_count)
        st.metric(
            "OSS verificado",
            f"{plan.oss_audit_verified_count}/{plan.oss_audit_count}",
        )

    st.subheader("Gates")
    for check in plan.checks:
        with st.container(border=True):
            st.markdown(f"### {'✓' if check.passed else '✗'} {check.check_id}")
            st.write(check.detail)
            st.caption(f"Blocking: {'sí' if check.blocking else 'no'}")

    st.subheader("Auditoría OSS")
    for entry in plan.oss_audit:
        with st.container(border=True):
            st.markdown(f"### {entry.function}")
            st.write(f"Actual: {entry.current_component}")
            st.write(f"Clasificación: {entry.classification}")
            st.write(f"Licencia: {entry.license}")
            st.write(f"Decisión: {entry.decision}")
            st.caption(f"Verificado: {'sí' if entry.verified else 'no'}")

    with st.expander("Trazabilidad y guardrails", expanded=False):
        st.write(f"Estado backend: {plan.status.value}")
        st.write(f"Hash F58: {plan.v1_readiness_hash}")
        st.write(f"Generado UTC: {plan.generated_at_utc.isoformat()}")
        st.write(f"Audit only: {plan.audit_only}")
        st.write(f"Final phase: {plan.final_phase}")
        st.write(f"Freeze autorizado: {plan.freeze_authorized}")
        st.write(f"Arquitectura V1 congelada: {plan.architecture_v1_frozen}")
        st.write(f"Freeze ejecutado: {plan.freeze_executed}")
        st.write(f"Auto publication: {plan.auto_publication}")
        st.write(f"Auto activation: {plan.auto_activation}")
        st.write(f"Writes runtime config: {plan.writes_runtime_config}")

    st.info(
        "Un resultado ARCHITECTURE_FREEZE_AUTHORIZED es una autorización registrada en el plan; "
        "no modifica la arquitectura, no escribe configuración y no ejecuta ningún freeze."
    )


if st.button("Ejecutar auditoría V1", type="primary"):
    try:
        request = V1ReadinessRequest(
            orchestrator=_load_json(
                orchestrator_file,
                ProductionOrchestratorPlan,
                "F51 ProductionOrchestratorPlan",
            ),
            publication=_load_json(
                publication_file,
                PublicationPackagePlan,
                "F54 PublicationPackagePlan",
            ),
            analytics_import=_load_json(
                analytics_file,
                AnalyticsImportPlan,
                "F55 AnalyticsImportPlan",
            ),
            hardening=_load_json(
                hardening_file,
                OperationalHardeningPlan,
                "F56 OperationalHardeningPlan",
            ),
            golden=_load_json(
                golden_file,
                GoldenE2ECertificationPlan,
                "F57 GoldenE2ECertificationPlan",
            ),
            oss_audit=_load_oss(),
            human_freeze_approval=human_freeze_approval,
        )
        plan = build_v1_readiness_audit(request)
        _render_result(plan)
    except Exception as exc:
        st.error(
            "No se ha podido completar la auditoría V1. "
            "No se ha autorizado ni ejecutado ningún freeze."
        )
        with st.expander("Detalles técnicos", expanded=False):
            st.code(f"{type(exc).__name__}: {exc}", language=None)
