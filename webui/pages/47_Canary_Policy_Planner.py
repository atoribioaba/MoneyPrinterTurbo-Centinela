from __future__ import annotations

import sys
from pathlib import Path
from typing import TypeVar

import streamlit as st
from pydantic import BaseModel


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.models.canary_policy_planner import (  # noqa: E402
    CanaryPolicyPlan,
    CanaryPolicyRequest,
)
from app.models.shadow_policy_evaluator import ShadowPolicyPlan  # noqa: E402
from app.services.canary_policy_planner import build_canary_policy_plan  # noqa: E402


ModelT = TypeVar("ModelT", bound=BaseModel)

st.set_page_config(page_title="F47 · El Centinela", layout="wide")
st.title("F47 · Canary Policy Planner")
st.caption(
    "Prepara candidatos canary desde evidencia F46. La exposición contractual es "
    "0.01–0.10 y la valida el modelo real. F47 no lanza el canary, no activa policy "
    "y no escribe runtime config."
)
st.info(
    "HUMAN LAUNCH REQUIRED · Un CanaryPolicyPlan listo sigue siendo planificación. "
    "Cada candidate mantiene requires_human_launch = TRUE y launched = FALSE."
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


def _render_failure(exc: Exception) -> None:
    st.error(
        "No se ha podido preparar el plan canary. El valor de exposición y la "
        "evidencia shadow se validan fail-closed mediante los modelos reales. "
        "No se ha lanzado ningún canary."
    )
    with st.expander("Detalles técnicos", expanded=False):
        st.caption(
            "F47 no normaliza silenciosamente la exposición, no crea observaciones "
            "y no avanza a F48."
        )
        st.code(f"{type(exc).__name__}: {exc}", language=None)


def _render_result(plan: CanaryPolicyPlan) -> None:
    if plan.status.value == "CANARY_PLANS_READY":
        st.success(
            f"CANARY_PLANS_READY · {plan.canary_candidate_count} candidate(s) elegibles."
        )
    elif plan.status.value == "NO_CANARY_ELIGIBLE":
        st.warning(
            "NO_CANARY_ELIGIBLE · Existe evidencia shadow, pero no cumple "
            "la eligibility contractual."
        )
    else:
        st.warning(
            "WAITING_FOR_SHADOW_EVIDENCE · No existe evidencia shadow suficiente."
        )

    st.subheader("Canary candidate(s)")
    if not plan.candidates:
        st.caption("No hay candidates canary para mostrar.")
    for candidate in plan.candidates:
        with st.container(border=True):
            st.markdown(f"### {candidate.policy_candidate_id}")
            st.write(f"Policy version: {candidate.policy_version}")
            st.write(f"Parámetro: {candidate.parameter}")
            st.write(
                f"Requested exposure fraction: {candidate.requested_exposure_fraction:.3f}"
            )
            st.write(f"Shadow cases: {candidate.shadow_case_count}")
            st.write(f"Shadow safe: {candidate.shadow_safe_count}")
            st.write(
                "Shadow behavior changes: "
                f"{candidate.shadow_behavior_change_count}"
            )
            st.write(
                "HUMAN LAUNCH REQUIRED: "
                + ("TRUE" if candidate.requires_human_launch else "FALSE")
            )
            st.write("LAUNCHED = " + ("TRUE" if candidate.launched else "FALSE"))

    st.subheader("Frontera de ejecución")
    with st.container(border=True):
        st.write("Execution = **NOT PERFORMED**")
        st.write(f"Max exposure fraction: {plan.max_exposure_fraction}")
        st.write(f"Executes canary: {plan.executes_canary}")
        st.write(f"Writes runtime config: {plan.writes_runtime_config}")
        st.write(f"Activates policy: {plan.activates_policy}")
        st.write(f"Auto rollback: {plan.auto_rollback}")
        st.write(f"Network calls: {plan.network_calls}")
        st.write(f"Auto publication: {plan.auto_publication}")

    with st.expander("Detalles técnicos", expanded=False):
        st.write(f"Estado F47: {plan.status.value}")
        st.write(f"Hash F47: {plan.canary_policy_hash}")
        st.write(f"Source shadow hash: {plan.source_shadow_policy_hash}")
        st.write(f"Evaluated policies: {plan.evaluated_policy_count}")
        st.write(f"Canary candidates: {plan.canary_candidate_count}")
        st.write(f"Generated UTC: {plan.generated_at_utc.isoformat()}")
        st.write(f"Planning only: {plan.planning_only}")

    st.caption(
        "F47 termina en CanaryPolicyPlan. No llama F48 automáticamente, no crea "
        "CanaryObservation y no confirma ningún lanzamiento humano."
    )


st.subheader("Shadow evidence")
shadow_upload = st.file_uploader(
    "F46 · ShadowPolicyPlan JSON",
    type=["json"],
    key="f47-shadow",
)
requested_exposure_fraction = st.number_input(
    "Requested exposure fraction",
    value=0.05,
    step=0.01,
    format="%.3f",
    key="f47-exposure",
    help=(
        "Contrato permitido: 0.01–0.10. No se aplica clamp en la UI; "
        "CanaryPolicyRequest valida el valor real."
    ),
)

if shadow_upload is None:
    st.warning(
        "UPSTREAM INCOMPLETE · Se necesita un ShadowPolicyPlan real. "
        "F47 no inventa evidencia shadow."
    )
else:
    try:
        shadow = _load_json_model(shadow_upload, ShadowPolicyPlan, "F46")

        st.subheader("Eligibility evidence")
        with st.container(border=True):
            st.write(f"Shadow policy hash: {shadow.shadow_policy_hash}")
            st.write(f"Evaluations: {shadow.evaluation_count}")
            st.write(f"Structural safe: {shadow.safe_evaluation_count}")
            st.write(f"Behavior changes: {shadow.behavior_change_count}")
            st.caption(
                "La eligibility se calcula exclusivamente en build_canary_policy_plan(): "
                "todas las rows de una policy deben ser structural_safe y al menos una "
                "debe tener behavior_changed."
            )

        if st.button("Preparar plan canary", type="primary"):
            request = CanaryPolicyRequest(
                shadow=shadow,
                requested_exposure_fraction=float(requested_exposure_fraction),
            )
            _render_result(build_canary_policy_plan(request))
    except Exception as exc:
        _render_failure(exc)
