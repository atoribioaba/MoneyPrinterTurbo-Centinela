from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import TypeVar

import streamlit as st
from pydantic import BaseModel


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.models.human_policy_approval import HumanPolicyApprovalPlan  # noqa: E402
from app.models.policy_candidate import PolicyCandidatePlan  # noqa: E402
from app.models.policy_registry import (  # noqa: E402
    PolicyRegistryPlan,
    PolicyRegistryRequest,
    PreviousPolicyReference,
)
from app.services.policy_registry import (  # noqa: E402
    PolicyRegistryError,
    build_policy_registry,
)


ModelT = TypeVar("ModelT", bound=BaseModel)

st.set_page_config(page_title="F45 · El Centinela", layout="wide")
st.title("F45 · Policy Registry")
st.caption(
    "Registra únicamente políticas que ya llegan aprobadas desde F44. "
    "F45 conserva versionado y rollback metadata, pero no activa políticas, "
    "no escribe runtime config y no persiste un registry real."
)
st.info(
    "HUMAN APPROVAL UPSTREAM · F45 consume un HumanPolicyApprovalPlan existente. "
    "No ofrece una vía alternativa para aprobar o rechazar políticas."
)


def _load_json_model(uploaded, model_type: type[ModelT], label: str) -> ModelT:
    try:
        payload = uploaded.getvalue().decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(f"{label}: el archivo debe estar codificado en UTF-8") from exc
    try:
        return model_type.model_validate_json(payload)
    except Exception as exc:
        raise ValueError(f"{label}: JSON o modelo inválido ({exc})") from exc


def _load_previous_versions(uploaded) -> list[PreviousPolicyReference]:
    if uploaded is None:
        return []
    try:
        raw = uploaded.getvalue().decode("utf-8")
        payload = json.loads(raw)
    except UnicodeDecodeError as exc:
        raise ValueError("PreviousPolicyReference: el archivo debe ser UTF-8") from exc
    except json.JSONDecodeError as exc:
        raise ValueError("PreviousPolicyReference: JSON inválido") from exc
    if not isinstance(payload, list):
        raise ValueError("PreviousPolicyReference: se esperaba una lista JSON")
    return [PreviousPolicyReference.model_validate(item) for item in payload]


def _render_failure(exc: Exception) -> None:
    st.error(
        "No se ha podido preparar el registro F45 de forma segura. "
        "No se ha creado ninguna activación, no se ha escrito runtime config "
        "y no se ha avanzado a F46."
    )
    with st.expander("Detalles técnicos", expanded=False):
        st.caption(
            "La entrada permanece fail-closed. F45 no repara IDs, no fabrica "
            "aprobaciones y no recalcula criptográficamente la procedencia F44."
        )
        st.code(f"{type(exc).__name__}: {exc}", language=None)


def _render_result(plan: PolicyRegistryPlan) -> None:
    if plan.entries:
        st.success(
            f"{plan.entry_count} política(s) aprobada(s) preparada(s) en el registro contractual."
        )
    else:
        st.warning(
            "WAITING_FOR_APPROVED_POLICY · No existe ninguna aprobación F44 válida "
            "que produzca una entrada de registry."
        )

    st.subheader("Registry entries")
    if not plan.entries:
        st.caption("No se ha creado ninguna registry entry.")
    for entry in plan.entries:
        with st.container(border=True):
            st.markdown(f"### {entry.policy_candidate_id}")
            st.write(f"Policy version: {entry.policy_version}")
            st.write(f"Componente: {entry.target_component.value}")
            st.write(f"Parámetro: {entry.parameter}")
            st.write(f"Baseline: {entry.baseline_value}")
            st.write(f"Candidate: {entry.candidate_value}")
            st.write(
                f"Previous policy version: {entry.previous_policy_version or 'sin referencia'}"
            )
            st.write(
                "Rollback target: "
                f"{entry.rollback_target_policy_version or 'sin referencia'}"
            )
            st.write(f"Immutable entry: {entry.immutable_entry}")
            st.write(
                "Eligible for shadow evaluation: "
                f"{entry.eligible_for_shadow_evaluation}"
            )
            st.write(f"ACTIVE = {entry.active}")
            st.caption(f"Approval record hash: {entry.approval_record_hash}")

    st.subheader("Frontera de ejecución")
    with st.container(border=True):
        st.write("Policy activation: **NOT PERFORMED**")
        st.write(f"Active policy changed: {plan.active_policy_changed}")
        st.write(f"Writes runtime config: {plan.writes_runtime_config}")
        st.write(f"Database writes: {plan.database_writes}")
        st.write(f"Network calls: {plan.network_calls}")
        st.write(f"Auto publication: {plan.auto_publication}")

    with st.expander("Detalles técnicos", expanded=False):
        st.write(f"Estado F45: {plan.status.value}")
        st.write(f"Hash F45: {plan.policy_registry_hash}")
        st.write(f"Source candidate hash: {plan.source_policy_candidate_hash}")
        st.write(
            "Source human approval hash: "
            f"{plan.source_human_policy_approval_hash}"
        )
        st.write(f"Generated UTC: {plan.generated_at_utc.isoformat()}")
        st.write(f"Planning only: {plan.planning_only}")
        st.write(f"Immutable registry: {plan.immutable_registry}")
        st.write(f"Activates policy: {plan.activates_policy}")
        st.write(f"Rollback metadata generated: {plan.rollback_metadata_generated}")

    st.caption(
        "PROVENANCE · HASHES PROPAGATED; NOT CRYPTOGRAPHICALLY RECOMPUTED BY F45. "
        "F45 termina en PolicyRegistryPlan y no activa policy."
    )


st.subheader("Human approval evidence")
candidates_upload = st.file_uploader(
    "F41 · PolicyCandidatePlan JSON",
    type=["json"],
    key="f45-candidates",
)
approvals_upload = st.file_uploader(
    "F44 · HumanPolicyApprovalPlan JSON",
    type=["json"],
    key="f45-approvals",
)
previous_upload = st.file_uploader(
    "PreviousPolicyReference[] JSON · opcional",
    type=["json"],
    key="f45-previous",
)

if candidates_upload is None or approvals_upload is None:
    st.warning(
        "UPSTREAM INCOMPLETE · Se necesitan PolicyCandidatePlan y "
        "HumanPolicyApprovalPlan reales. F45 no crea aprobaciones alternativas."
    )
else:
    try:
        candidates = _load_json_model(candidates_upload, PolicyCandidatePlan, "F41")
        approvals = _load_json_model(
            approvals_upload,
            HumanPolicyApprovalPlan,
            "F44",
        )
        previous_versions = _load_previous_versions(previous_upload)

        st.subheader("Lineage")
        with st.container(border=True):
            st.write(f"Policy candidate hash: {candidates.policy_candidate_hash}")
            st.write(
                "Human policy approval hash: "
                f"{approvals.human_policy_approval_hash}"
            )
            st.write(
                "Comparator source hash carried by F44: "
                f"{approvals.source_policy_comparator_hash}"
            )
            st.write(f"Human decisions recorded: {approvals.decision_count}")
            st.write(f"APPROVE records: {approvals.approved_count}")
            st.write(f"REJECT records: {approvals.rejected_count}")
            st.caption(
                "F45 consume el plan F44 validado y deja al servicio real decidir "
                "qué APPROVE produce registry entry. Los hashes se presentan como "
                "lineage propagada, no como atestado criptográfico recalculado."
            )

        if st.button("Preparar registro de política", type="primary"):
            request = PolicyRegistryRequest(
                candidates=candidates,
                approvals=approvals,
                previous_versions=previous_versions,
            )
            _render_result(build_policy_registry(request))
    except PolicyRegistryError as exc:
        _render_failure(exc)
    except Exception as exc:
        _render_failure(exc)
