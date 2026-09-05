from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import TypeVar

import streamlit as st
from pydantic import BaseModel


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.models.human_policy_approval import (  # noqa: E402
    HumanDecision,
    HumanPolicyApprovalPlan,
    HumanPolicyApprovalRequest,
    PolicyHumanDecision,
)
from app.models.policy_candidate import PolicyCandidatePlan  # noqa: E402
from app.models.policy_comparator import PolicyComparatorPlan  # noqa: E402
from app.models.policy_simulator import PolicySimulatorPlan  # noqa: E402
from app.services.human_policy_approval import (  # noqa: E402
    HumanPolicyApprovalError,
    build_human_policy_approval,
)


ModelT = TypeVar("ModelT", bound=BaseModel)

st.set_page_config(page_title="F44 · El Centinela", layout="wide")
st.title("F44 · Human Policy Approval")
st.caption(
    "Revisión humana explícita de candidatos de política a partir de evidencia real "
    "F41 → F42 → F43. Aprobar o rechazar sólo registra la decisión en el plan F44; "
    "no activa, no promueve y no publica ninguna política."
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


def _render_failure(exc: Exception, candidate_id: str | None = None) -> None:
    st.error(
        "No se ha podido completar la revisión humana de forma segura. "
        "Revisa la evidencia, la trazabilidad y los campos obligatorios."
    )
    with st.expander("Detalles técnicos", expanded=False):
        st.caption(
            "Evidencia diagnóstica preservada. No se ha activado ni promovido ninguna "
            "política, no se ha escrito en el registro y no se ha ejecutado F45."
        )
        if candidate_id:
            st.write(f"Candidate ID: {candidate_id}")
        st.code(f"{type(exc).__name__}: {exc}", language=None)


def _format_scalar(value: bool | float) -> str:
    if isinstance(value, bool):
        return "sí" if value else "no"
    return f"{value:g}"


def _render_result(result: HumanPolicyApprovalPlan, candidate_id: str) -> None:
    record = next(
        (item for item in result.records if item.policy_candidate_id == candidate_id),
        None,
    )
    if record is None:
        st.warning("F44 no devolvió un registro para el candidato seleccionado.")
        return

    st.success(f"Decisión humana registrada: {record.decision.value}")
    st.info(
        "La decisión queda representada únicamente en HumanPolicyApprovalPlan. "
        "No activa la política, no la promueve, no modifica runtime y no ejecuta F45."
    )
    st.write(f"Revisor: {record.reviewer_ref}")
    st.write(f"Motivo: {record.rationale}")
    st.write(f"Decidido: {record.decided_at_utc.strftime('%d/%m/%Y · %H:%M:%S UTC')}")

    with st.expander("Detalles técnicos", expanded=False):
        st.write(f"Estado F44: {result.status.value}")
        st.write(f"Hash F44: {result.human_policy_approval_hash}")
        st.write(f"Hash F43 fuente: {result.source_policy_comparator_hash}")
        st.write(f"Generado UTC: {result.generated_at_utc.isoformat()}")
        st.write(f"Auto approval: {result.auto_approval}")
        st.write(f"Activates policy: {result.activates_policy}")
        st.write(f"Edits project: {result.edits_project}")
        st.write(f"Network calls: {result.network_calls}")
        st.write(f"Auto publication: {result.auto_publication}")


st.subheader("Evidencia F41 → F42 → F43")
st.caption(
    "Carga los tres planes JSON reales de la misma lineage. Los archivos se validan "
    "en memoria mediante sus modelos Pydantic; no se aceptan rutas del servidor."
)

f41_upload = st.file_uploader(
    "F41 · PolicyCandidatePlan",
    type=["json"],
    key="f44_f41",
)
f42_upload = st.file_uploader(
    "F42 · PolicySimulatorPlan",
    type=["json"],
    key="f44_f42",
)
f43_upload = st.file_uploader(
    "F43 · PolicyComparatorPlan",
    type=["json"],
    key="f44_f43",
)

if f41_upload is None or f42_upload is None or f43_upload is None:
    st.warning(
        "EVIDENCE INCOMPLETE · Se necesitan F41, F42 y F43 para habilitar una "
        "decisión humana. No se ha creado ninguna decisión."
    )
else:
    try:
        f41 = _load_json_model(f41_upload, PolicyCandidatePlan, "F41")
        f42 = _load_json_model(f42_upload, PolicySimulatorPlan, "F42")
        f43 = _load_json_model(f43_upload, PolicyComparatorPlan, "F43")

        lineage_41_42 = f42.source_policy_candidate_hash == f41.policy_candidate_hash
        lineage_42_43 = f43.source_policy_simulator_hash == f42.policy_simulator_hash
        lineage_ok = lineage_41_42 and lineage_42_43

        st.subheader("Trazabilidad")
        st.write(
            "F41 → F42: "
            + ("PASS" if lineage_41_42 else "FAIL")
        )
        st.write(
            "F42 → F43: "
            + ("PASS" if lineage_42_43 else "FAIL")
        )

        if not lineage_ok:
            st.error(
                "La trazabilidad de este candidato no coincide. "
                "No se puede tomar una decisión humana de forma segura."
            )

        candidates_by_id = {
            item.policy_candidate_id: item for item in f41.candidates
        }
        simulations_by_id: dict[str, list] = {}
        for item in f42.results:
            simulations_by_id.setdefault(item.policy_candidate_id, []).append(item)
        comparisons_by_id = {
            item.policy_candidate_id: item for item in f43.comparisons
        }

        candidate_ids = list(comparisons_by_id)
        if not candidate_ids:
            st.warning(
                "F43 no contiene candidatos comparados. No hay ninguna decisión "
                "humana disponible."
            )
        else:
            selected_id = st.selectbox(
                "Candidato a revisar",
                options=candidate_ids,
                format_func=lambda candidate_id: (
                    f"{candidate_id} · "
                    + (
                        "SAFE FOR HUMAN REVIEW"
                        if comparisons_by_id[candidate_id].safe_for_human_review
                        else "BLOCKED"
                    )
                ),
            )

            selected_candidate = candidates_by_id.get(selected_id)
            selected_simulations = simulations_by_id.get(selected_id, [])
            selected_comparison = comparisons_by_id[selected_id]
            context_complete = (
                selected_candidate is not None and bool(selected_simulations)
            )

            st.subheader("Candidato")
            if selected_candidate is None:
                st.error(
                    "El candidato comparado por F43 no existe en F41. "
                    "La decisión queda bloqueada."
                )
            else:
                st.write(f"Candidate ID: {selected_candidate.policy_candidate_id}")
                st.write(f"Componente: {selected_candidate.target_component.value}")
                st.write(f"Parámetro: {selected_candidate.parameter}")
                st.write(
                    "Baseline: "
                    f"{_format_scalar(selected_candidate.baseline_value)}"
                )
                st.write(
                    "Candidate: "
                    f"{_format_scalar(selected_candidate.candidate_value)}"
                )
                st.write(f"Evidencia: {selected_candidate.evidence_class}")

            st.subheader("Resultado de simulación")
            if not selected_simulations:
                st.error(
                    "No existe resultado F42 para el candidato seleccionado. "
                    "La decisión queda bloqueada."
                )
            else:
                for simulation in selected_simulations:
                    with st.expander(
                        f"Caso {simulation.case_id} · {simulation.parameter}",
                        expanded=False,
                    ):
                        st.write(
                            "Cambio de comportamiento: "
                            + ("sí" if simulation.behavior_changed else "no")
                        )
                        st.write(
                            "Checks estructurales baseline: "
                            + (
                                "PASS"
                                if simulation.baseline_structural_checks_pass
                                else "FAIL"
                            )
                        )
                        st.write(
                            "Checks estructurales candidate: "
                            + (
                                "PASS"
                                if simulation.candidate_structural_checks_pass
                                else "FAIL"
                            )
                        )
                        st.write(
                            "Placeholders preservados: "
                            + ("sí" if simulation.placeholders_preserved else "no")
                        )
                        st.write(
                            f"Clímax baseline: escena {simulation.baseline_climax_scene}"
                        )
                        st.write(
                            f"Clímax candidate: escena {simulation.candidate_climax_scene}"
                        )
                        st.caption(
                            f"Direction hash baseline: {simulation.baseline_direction_hash}"
                        )
                        st.caption(
                            f"Direction hash candidate: {simulation.candidate_direction_hash}"
                        )

            st.subheader("Resultado del comparator")
            st.write(
                f"Simulaciones: {selected_comparison.simulation_count}"
            )
            st.write(
                f"Cambios de comportamiento: {selected_comparison.behavior_change_count}"
            )
            st.write(
                "Regresiones estructurales: "
                f"{selected_comparison.structural_regression_count}"
            )
            st.write(
                "Regresiones de placeholders: "
                f"{selected_comparison.placeholder_regression_count}"
            )

            if selected_comparison.safe_for_human_review:
                st.success("SAFE FOR HUMAN REVIEW")
            else:
                st.warning(
                    "BLOCKED · F43 no autoriza revisión humana para este candidato. "
                    "No existe bypass desde F44."
                )

            st.subheader("Decisión humana")
            reviewer_ref = st.text_input(
                "Reviewer ref",
                value="",
                placeholder="Identificador explícito del revisor",
            )
            rationale = st.text_area(
                "Rationale",
                value="",
                placeholder="Explica por qué apruebas o rechazas este candidato.",
            )

            required_fields_ok = bool(reviewer_ref.strip() and rationale.strip())
            decision_enabled = (
                lineage_ok
                and context_complete
                and selected_comparison.safe_for_human_review
                and required_fields_ok
            )

            if not required_fields_ok:
                st.caption(
                    "Reviewer ref y rationale son obligatorios antes de registrar "
                    "APPROVE o REJECT."
                )

            reject_clicked = st.button(
                "Rechazar",
                disabled=not decision_enabled,
            )
            approve_clicked = st.button(
                "Aprobar",
                type="primary",
                disabled=not decision_enabled,
            )

            if reject_clicked or approve_clicked:
                decision_kind = (
                    HumanDecision.REJECT if reject_clicked else HumanDecision.APPROVE
                )
                try:
                    decision = PolicyHumanDecision(
                        policy_candidate_id=selected_id,
                        decision=decision_kind,
                        reviewer_ref=reviewer_ref.strip(),
                        rationale=rationale.strip(),
                        decided_at_utc=datetime.now(timezone.utc),
                    )
                    result = build_human_policy_approval(
                        HumanPolicyApprovalRequest(
                            comparator=f43,
                            decisions=[decision],
                        )
                    )
                    _render_result(result, selected_id)
                except HumanPolicyApprovalError as exc:
                    _render_failure(exc, selected_id)
                except Exception as exc:
                    _render_failure(exc, selected_id)

        with st.expander("Detalles técnicos", expanded=False):
            st.caption(
                "Hashes y metadatos de los planes cargados. Esta vista no repara "
                "lineage ni recalcula safe_for_human_review."
            )
            st.write(f"F41 hash: {f41.policy_candidate_hash}")
            st.write(f"F42 source F41 hash: {f42.source_policy_candidate_hash}")
            st.write(f"F42 hash: {f42.policy_simulator_hash}")
            st.write(f"F43 source F42 hash: {f43.source_policy_simulator_hash}")
            st.write(f"F43 hash: {f43.policy_comparator_hash}")
            st.write(f"F43 safe candidates: {f43.safe_candidate_count}")
            st.write(f"F43 status: {f43.status.value}")

    except Exception as exc:
        _render_failure(exc)
