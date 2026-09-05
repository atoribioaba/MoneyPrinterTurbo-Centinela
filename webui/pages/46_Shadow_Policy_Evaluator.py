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

from app.models.policy_registry import PolicyRegistryPlan  # noqa: E402
from app.models.policy_simulator import PolicySimulationCase  # noqa: E402
from app.models.shadow_policy_evaluator import (  # noqa: E402
    ShadowPolicyPlan,
    ShadowPolicyRequest,
)
from app.services.shadow_policy_evaluator import (  # noqa: E402
    ShadowPolicyEvaluatorError,
    build_shadow_policy_plan,
)


ModelT = TypeVar("ModelT", bound=BaseModel)

st.set_page_config(page_title="F46 · El Centinela", layout="wide")
st.title("F46 · Shadow Policy Evaluator")
st.caption(
    "Evalúa policies registradas contra casos reales mediante el CinematicDirector "
    "existente. El resultado es shadow-only: no modifica runtime, no renderiza vídeo "
    "y no activa ninguna policy."
)
st.info(
    "SHADOW ONLY · F46 consume PolicyRegistryPlan + PolicySimulationCase[]. "
    "No requiere PolicySimulatorPlan y no crea casos sintéticos."
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


def _load_cases(uploaded) -> list[PolicySimulationCase]:
    try:
        raw = uploaded.getvalue().decode("utf-8")
        payload = json.loads(raw)
    except UnicodeDecodeError as exc:
        raise ValueError("PolicySimulationCase[]: el archivo debe ser UTF-8") from exc
    except json.JSONDecodeError as exc:
        raise ValueError("PolicySimulationCase[]: JSON inválido") from exc
    if not isinstance(payload, list):
        raise ValueError("PolicySimulationCase[]: se esperaba una lista JSON")
    return [PolicySimulationCase.model_validate(item) for item in payload]


def _render_failure(exc: Exception) -> None:
    st.error(
        "No se ha podido preparar la evaluación shadow de forma segura. "
        "El baseline no se corrige silenciosamente y F46 no produce efectos sobre runtime."
    )
    with st.expander("Detalles técnicos", expanded=False):
        st.caption(
            "Un baseline mismatch, un case inválido o una policy no soportada "
            "permanece bloqueada. No se activa policy y no se ejecuta render."
        )
        st.code(f"{type(exc).__name__}: {exc}", language=None)


def _render_result(plan: ShadowPolicyPlan) -> None:
    if plan.results:
        st.success(
            f"SHADOW_RESULTS_READY · {plan.evaluation_count} evaluación(es) preparadas."
        )
    else:
        st.warning(
            "WAITING_FOR_REGISTERED_POLICY_AND_CASES · No existen resultados shadow."
        )

    st.subheader("Shadow evidence")
    if not plan.results:
        st.caption("No hay evaluaciones para mostrar.")
    for result in plan.results:
        with st.container(border=True):
            st.markdown(f"### {result.policy_candidate_id} · {result.case_id}")
            st.write(f"Policy version: {result.policy_version}")
            st.write(f"Parámetro: {result.parameter}")
            st.write(
                "Behavior changed: "
                + ("sí" if result.behavior_changed else "no")
            )
            st.write(
                "Baseline structural checks: "
                + ("PASS" if result.baseline_structural_checks_pass else "FAIL")
            )
            st.write(
                "Candidate structural checks: "
                + ("PASS" if result.candidate_structural_checks_pass else "FAIL")
            )
            st.write(
                "Placeholders preserved: "
                + ("sí" if result.placeholders_preserved else "no")
            )
            st.write(
                "Structural safe: "
                + ("PASS" if result.structural_safe else "BLOCKED")
            )
            with st.expander("Hashes de dirección", expanded=False):
                st.caption(f"Baseline: {result.baseline_direction_hash}")
                st.caption(f"Candidate: {result.candidate_direction_hash}")

    st.subheader("Frontera de ejecución")
    with st.container(border=True):
        st.write(f"Shadow only: {plan.shadow_only}")
        st.write(f"Uses real CinematicDirector: {plan.uses_real_cinematic_director}")
        st.write(f"Runtime effect: {plan.runtime_effect}")
        st.write(f"Writes runtime config: {plan.writes_runtime_config}")
        st.write(f"Activates policy: {plan.activates_policy}")
        st.write(f"Renders video: {plan.renders_video}")
        st.write(f"GPU required: {plan.gpu_required}")
        st.write(f"Network calls: {plan.network_calls}")
        st.write(f"Auto publication: {plan.auto_publication}")

    with st.expander("Detalles técnicos", expanded=False):
        st.write(f"Estado F46: {plan.status.value}")
        st.write(f"Hash F46: {plan.shadow_policy_hash}")
        st.write(f"Source registry hash: {plan.source_policy_registry_hash}")
        st.write(f"Registered policies: {plan.registered_policy_count}")
        st.write(f"Cases: {plan.case_count}")
        st.write(f"Safe evaluations: {plan.safe_evaluation_count}")
        st.write(f"Behavior changes: {plan.behavior_change_count}")
        st.write(f"Generated UTC: {plan.generated_at_utc.isoformat()}")
        st.write(f"Planning only: {plan.planning_only}")

    st.caption(
        "F46 termina en ShadowPolicyPlan. No aplica cambios al runtime y no avanza "
        "automáticamente hacia un lanzamiento canary."
    )


st.subheader("Policy registry")
registry_upload = st.file_uploader(
    "F45 · PolicyRegistryPlan JSON",
    type=["json"],
    key="f46-registry",
)
cases_upload = st.file_uploader(
    "PolicySimulationCase[] JSON",
    type=["json"],
    key="f46-cases",
)

if registry_upload is None or cases_upload is None:
    st.warning(
        "UPSTREAM INCOMPLETE · Se necesita un PolicyRegistryPlan real y una lista "
        "explícita PolicySimulationCase[]. No se fabrican casos desde F46."
    )
else:
    try:
        registry = _load_json_model(registry_upload, PolicyRegistryPlan, "F45")
        cases = _load_cases(cases_upload)

        st.subheader("Lineage")
        with st.container(border=True):
            st.write(f"Policy registry hash: {registry.policy_registry_hash}")
            st.write(f"Registered policies: {registry.entry_count}")
            st.write(f"Simulation cases supplied: {len(cases)}")
            for case in cases:
                st.caption(
                    f"{case.case_id} · context {case.plan.context_hash} · "
                    f"video base scenes {case.video_base.scene_count}"
                )

        if st.button("Preparar evaluación shadow", type="primary"):
            request = ShadowPolicyRequest(registry=registry, cases=cases)
            _render_result(build_shadow_policy_plan(request))
    except ShadowPolicyEvaluatorError as exc:
        _render_failure(exc)
    except Exception as exc:
        _render_failure(exc)
