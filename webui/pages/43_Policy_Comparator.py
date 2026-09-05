from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.models.policy_comparator import (  # noqa: E402
    PolicyComparatorPlan,
    PolicyComparatorRequest,
    PolicyComparatorStatus,
)
from app.models.policy_simulator import PolicySimulatorPlan  # noqa: E402
from app.services.policy_comparator import (  # noqa: E402
    build_policy_comparator,
)


st.set_page_config(page_title="F43 · El Centinela", layout="wide")
st.title("F43 · Policy Comparator")
st.caption(
    "Evalúa regresiones estructurales antes de revisión humana. "
    "Safe for human review no significa mejor, causal ni aprobado."
)
st.info(
    "F43 sólo determina seguridad estructural para revisión. "
    "La decisión APPROVE/REJECT pertenece exclusivamente a F44."
)


def _render_failure(exc: Exception) -> None:
    st.error(
        "No se ha podido completar F43 de forma segura. No se ha aprobado "
        "ninguna política y no se ha creado ninguna decisión F44."
    )
    with st.expander("Detalles técnicos", expanded=False):
        st.code(f"{type(exc).__name__}: {exc}", language=None)


def _render_result(plan: PolicyComparatorPlan) -> None:
    if plan.status == PolicyComparatorStatus.SAFE_CANDIDATES_READY:
        st.success(
            f"{plan.safe_candidate_count} candidato(s) sin regresiones "
            "estructurales detectadas, aptos para revisión humana."
        )
    elif plan.status == PolicyComparatorStatus.NO_SAFE_CANDIDATES:
        st.error(
            "NO_SAFE_CANDIDATES · Las simulaciones presentan regresiones "
            "estructurales o de placeholders."
        )
    else:
        st.warning(
            "WAITING_FOR_SIMULATIONS · No existen simulaciones que comparar."
        )

    st.subheader("Comparaciones")
    if not plan.comparisons:
        st.caption("No hay candidatos comparables.")
    for comparison in plan.comparisons:
        with st.container(border=True):
            label = (
                "SEGURO PARA REVISIÓN HUMANA"
                if comparison.safe_for_human_review
                else "NO SEGURO PARA REVISIÓN HUMANA"
            )
            st.markdown(f"### {comparison.policy_candidate_id}")
            st.write(label)
            st.write(f"Simulaciones: {comparison.simulation_count}")
            st.write(
                f"Behavior changes: {comparison.behavior_change_count}"
            )
            st.write(
                "Structural regressions: "
                f"{comparison.structural_regression_count}"
            )
            st.write(
                "Placeholder regressions: "
                f"{comparison.placeholder_regression_count}"
            )
            st.write(
                "Quality improvement claimed: "
                f"{comparison.quality_improvement_claimed}"
            )
            st.write(f"Causal claim: {comparison.causal_claim}")

    st.warning(
        "SAFE_FOR_HUMAN_REVIEW ≠ mejora demostrada ≠ efecto causal "
        "≠ política aprobada. El criterio F43 sólo exige cero regresiones "
        "estructurales y cero regresiones de placeholders."
    )

    st.subheader("Frontera de ejecución")
    with st.container(border=True):
        st.write(f"Quality improvement claims: {plan.quality_improvement_claims}")
        st.write(f"Causal claims: {plan.causal_claims}")
        st.write(f"Activates policy: {plan.activates_policy}")
        st.write(f"Edits project: {plan.edits_project}")
        st.write(f"Network calls: {plan.network_calls}")
        st.write(f"Auto publication: {plan.auto_publication}")

    with st.expander("Detalles técnicos", expanded=False):
        st.write(f"Estado F43: {plan.status.value}")
        st.write(f"Hash F43: {plan.policy_comparator_hash}")
        st.write(
            f"Source simulator hash: {plan.source_policy_simulator_hash}"
        )
        st.write(f"Candidates: {plan.candidate_count}")
        st.write(f"Safe candidates: {plan.safe_candidate_count}")
        st.write(f"Generated UTC: {plan.generated_at_utc.isoformat()}")

    st.caption(
        "STOP F43 · F44 Human Policy Approval es un gate separado. "
        "Esta página no contiene controles APPROVE/REJECT."
    )


simulations_upload = st.file_uploader(
    "F42 · PolicySimulatorPlan JSON",
    type=["json"],
    key="f43-simulations",
)

if simulations_upload is None:
    st.warning(
        "UPSTREAM INCOMPLETE · Carga un PolicySimulatorPlan real de F42. "
        "F43 no fabrica simulaciones."
    )
else:
    try:
        simulations = PolicySimulatorPlan.model_validate_json(
            simulations_upload.getvalue().decode("utf-8")
        )

        st.subheader("Lineage F42 → F43")
        with st.container(border=True):
            st.write(
                f"Policy simulator hash: {simulations.policy_simulator_hash}"
            )
            st.write(f"Simulaciones: {simulations.simulation_count}")
            st.write(
                f"Behavior changes: {simulations.behavior_change_count}"
            )

        if st.button("Comparar seguridad estructural", type="primary"):
            request = PolicyComparatorRequest(simulations=simulations)
            _render_result(build_policy_comparator(request))
    except Exception as exc:
        _render_failure(exc)
