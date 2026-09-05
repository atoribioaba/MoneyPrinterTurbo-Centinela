from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.models.evidence_recommendation_gate import (  # noqa: E402
    EvidenceRecommendationGatePlan,
)
from app.models.policy_candidate import (  # noqa: E402
    PolicyBinding,
    PolicyCandidatePlan,
    PolicyCandidateRequest,
    PolicyCandidateStatus,
    PolicyTargetComponent,
)
from app.services.policy_candidate import (  # noqa: E402
    PolicyCandidateError,
    build_policy_candidate,
)


st.set_page_config(page_title="F41 · El Centinela", layout="wide")
st.title("F41 · Policy Candidate")
st.caption(
    "Convierte una recomendación F40 en candidato de política únicamente "
    "cuando una persona confirma explícitamente el mapping al parámetro."
)
st.info(
    "F41 no infiere bindings, no activa políticas y no modifica runtime. "
    "Cada candidato requiere simulación posterior en F42."
)


def _render_failure(exc: Exception) -> None:
    st.error(
        "No se ha podido preparar F41 de forma segura. No se ha inferido "
        "ningún binding, no se ha activado policy y no se ha avanzado a F42."
    )
    with st.expander("Detalles técnicos", expanded=False):
        st.code(f"{type(exc).__name__}: {exc}", language=None)


def _render_result(plan: PolicyCandidatePlan) -> None:
    if plan.status == PolicyCandidateStatus.CANDIDATE_POLICIES_READY:
        st.success(
            f"{plan.candidate_count} candidato(s) preparados para simulación."
        )
    else:
        st.warning(
            "WAITING_FOR_EXPLICIT_POLICY_BINDINGS · No existe ningún binding "
            "humano confirmado que produzca un candidato."
        )

    st.subheader("Candidatos")
    if not plan.candidates:
        st.caption("No se ha creado ningún candidato de policy.")
    for candidate in plan.candidates:
        with st.container(border=True):
            st.markdown(f"### {candidate.policy_candidate_id}")
            st.write(f"Recommendation: {candidate.recommendation_id}")
            st.write(f"Parámetro: {candidate.parameter}")
            st.write(f"Baseline: {candidate.baseline_value}")
            st.write(f"Candidate: {candidate.candidate_value}")
            st.write(
                f"Human mapping confirmed: {candidate.human_mapping_confirmed}"
            )
            st.write(f"Requires simulation: {candidate.requires_simulation}")
            st.write(
                f"Approved for activation: {candidate.approved_for_activation}"
            )

    st.subheader("Frontera de ejecución")
    with st.container(border=True):
        st.write(f"Inferred bindings: {plan.inferred_bindings}")
        st.write(f"Edits project: {plan.edits_project}")
        st.write(f"Updates director policy: {plan.updates_director_policy}")
        st.write(f"Activates policy: {plan.activates_policy}")
        st.write(f"Network calls: {plan.network_calls}")
        st.write(f"Database writes: {plan.database_writes}")
        st.write(f"Auto publication: {plan.auto_publication}")

    with st.expander("Detalles técnicos", expanded=False):
        st.write(f"Estado F41: {plan.status.value}")
        st.write(f"Hash F41: {plan.policy_candidate_hash}")
        st.write(
            "Source recommendation gate hash: "
            f"{plan.source_recommendation_gate_hash}"
        )
        st.write(f"Bindings recibidos: {plan.binding_count}")
        st.write(f"Candidatos: {plan.candidate_count}")
        st.write(f"Generated UTC: {plan.generated_at_utc.isoformat()}")
        st.write(f"Planning only: {plan.planning_only}")

    st.caption(
        "STOP F41 · Un candidato no está aprobado ni activo. "
        "Debe pasar por F42 y F43 antes de cualquier decisión humana F44."
    )


recommendations_upload = st.file_uploader(
    "F40 · EvidenceRecommendationGatePlan JSON",
    type=["json"],
    key="f41-recommendations",
)

st.subheader("Binding humano explícito")
add_binding = st.checkbox(
    "Añadir un PolicyBinding",
    value=False,
    help=(
        "Desactivado = bindings=[]. F41 permanecerá esperando mapping humano."
    ),
)

bindings: list[PolicyBinding] = []

if add_binding:
    recommendation_id = st.text_input("recommendation_id")
    parameter = st.selectbox(
        "parameter",
        options=[
            "intensity_bias",
            "prefer_observation_over_motion",
            "preserve_source_transition_intent",
        ],
    )

    if parameter == "intensity_bias":
        baseline_value = st.number_input(
            "baseline_value",
            value=0.0,
            format="%.4f",
        )
        candidate_value = st.number_input(
            "candidate_value",
            value=0.05,
            format="%.4f",
        )
    else:
        baseline_value = st.checkbox(
            "baseline_value",
            value=False,
            key="f41-baseline-bool",
        )
        candidate_value = st.checkbox(
            "candidate_value",
            value=True,
            key="f41-candidate-bool",
        )

    human_mapping_confirmed = st.checkbox(
        "Confirmo manualmente este mapping recomendación → parámetro",
        value=False,
    )

    try:
        bindings.append(
            PolicyBinding(
                recommendation_id=recommendation_id,
                target_component=(
                    PolicyTargetComponent.CINEMATIC_DIRECTOR_REQUEST
                ),
                parameter=parameter,
                baseline_value=baseline_value,
                candidate_value=candidate_value,
                human_mapping_confirmed=human_mapping_confirmed,
            )
        )
    except Exception as exc:
        _render_failure(exc)
        bindings = []

if recommendations_upload is None:
    st.warning(
        "UPSTREAM INCOMPLETE · Carga un EvidenceRecommendationGatePlan real "
        "de F40. F41 no fabrica recomendaciones ni bindings."
    )
else:
    try:
        recommendations = EvidenceRecommendationGatePlan.model_validate_json(
            recommendations_upload.getvalue().decode("utf-8")
        )

        st.subheader("Lineage F40 → F41")
        with st.container(border=True):
            st.write(
                "Evidence recommendation gate hash: "
                f"{recommendations.evidence_recommendation_gate_hash}"
            )
            st.write(
                f"Recomendaciones F40: {recommendations.recommendation_count}"
            )
            st.write(
                "Todas las asociaciones de parámetro deben confirmarse "
                "manualmente; F41 no las infiere."
            )

        if st.button("Preparar candidatos de política", type="primary"):
            request = PolicyCandidateRequest(
                recommendations=recommendations,
                bindings=bindings,
            )
            _render_result(build_policy_candidate(request))
    except PolicyCandidateError as exc:
        _render_failure(exc)
    except Exception as exc:
        _render_failure(exc)
