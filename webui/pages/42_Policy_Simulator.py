from __future__ import annotations

import json
import sys
from pathlib import Path

import streamlit as st


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.models.policy_candidate import PolicyCandidatePlan  # noqa: E402
from app.models.policy_simulator import (  # noqa: E402
    PolicySimulationCase,
    PolicySimulatorPlan,
    PolicySimulatorRequest,
    PolicySimulatorStatus,
)
from app.services.policy_simulator import (  # noqa: E402
    PolicySimulatorError,
    build_policy_simulator,
)


st.set_page_config(page_title="F42 · El Centinela", layout="wide")
st.title("F42 · Policy Simulator")
st.caption(
    "Simula baseline vs candidate usando el CinematicDirector real. "
    "No renderiza vídeo, no usa GPU y no escribe runtime config."
)
st.info(
    "F42 verifica que el baseline declarado por F41 coincida con el "
    "CinematicDirectorRequest real antes de aplicar el candidate_value."
)


def _load_cases(uploaded) -> list[PolicySimulationCase]:
    if uploaded is None:
        return []
    try:
        payload = json.loads(uploaded.getvalue().decode("utf-8"))
    except UnicodeDecodeError as exc:
        raise ValueError("PolicySimulationCase[] debe estar en UTF-8") from exc
    except json.JSONDecodeError as exc:
        raise ValueError("PolicySimulationCase[] contiene JSON inválido") from exc
    if not isinstance(payload, list):
        raise ValueError("PolicySimulationCase[] debe ser una lista JSON")
    return [PolicySimulationCase.model_validate(item) for item in payload]


def _render_failure(exc: Exception) -> None:
    st.error(
        "F42 ha fallado cerrado. No se ha renderizado vídeo, no se ha usado "
        "GPU, no se ha escrito runtime config y no se ha avanzado a F43."
    )
    with st.expander("Detalles técnicos", expanded=False):
        st.code(f"{type(exc).__name__}: {exc}", language=None)


def _render_result(plan: PolicySimulatorPlan) -> None:
    if plan.status == PolicySimulatorStatus.SIMULATIONS_READY:
        st.success(
            f"{plan.simulation_count} simulación(es) de planificación listas."
        )
    else:
        st.warning(
            "WAITING_FOR_CANDIDATE_POLICY_AND_CASES · F42 necesita "
            "candidatos y casos para producir resultados."
        )

    st.subheader("Resultados")
    if not plan.results:
        st.caption("No existen simulaciones para comparar.")
    for result in plan.results:
        with st.container(border=True):
            st.markdown(
                f"### {result.policy_candidate_id} · {result.case_id}"
            )
            st.write(f"Parámetro: {result.parameter}")
            st.write(f"Behavior changed: {result.behavior_changed}")
            st.write(
                "Baseline structural checks pass: "
                f"{result.baseline_structural_checks_pass}"
            )
            st.write(
                "Candidate structural checks pass: "
                f"{result.candidate_structural_checks_pass}"
            )
            st.write(
                f"Placeholders preserved: {result.placeholders_preserved}"
            )
            st.write(
                "Climax baseline → candidate: "
                f"{result.baseline_climax_scene} → "
                f"{result.candidate_climax_scene}"
            )

    st.subheader("Frontera de ejecución")
    with st.container(border=True):
        st.write(
            f"Uses real CinematicDirector: {plan.uses_real_cinematic_director}"
        )
        st.write(f"Renders video: {plan.renders_video}")
        st.write(f"GPU required: {plan.gpu_required}")
        st.write(f"Writes runtime config: {plan.writes_runtime_config}")
        st.write(f"Activates policy: {plan.activates_policy}")
        st.write(f"Network calls: {plan.network_calls}")
        st.write(f"Auto publication: {plan.auto_publication}")

    with st.expander("Detalles técnicos", expanded=False):
        st.write(f"Estado F42: {plan.status.value}")
        st.write(f"Hash F42: {plan.policy_simulator_hash}")
        st.write(
            f"Source policy candidate hash: {plan.source_policy_candidate_hash}"
        )
        st.write(f"Case count: {plan.case_count}")
        st.write(f"Simulation count: {plan.simulation_count}")
        st.write(f"Behavior changes: {plan.behavior_change_count}")
        st.write(f"Generated UTC: {plan.generated_at_utc.isoformat()}")

    st.caption(
        "STOP F42 · Simulation significa evaluación determinista de la "
        "lógica del director. No existe render, GPU ni activación."
    )


candidates_upload = st.file_uploader(
    "F41 · PolicyCandidatePlan JSON",
    type=["json"],
    key="f42-candidates",
)
cases_upload = st.file_uploader(
    "PolicySimulationCase[] JSON · opcional",
    type=["json"],
    key="f42-cases",
    help=(
        "Cada caso contiene case_id + AstronomyVideoPlan + VideoBasePlan. "
        "Sin casos, F42 permanece en WAITING."
    ),
)

if candidates_upload is None:
    st.warning(
        "UPSTREAM INCOMPLETE · Carga un PolicyCandidatePlan real de F41. "
        "F42 no fabrica candidatos."
    )
else:
    try:
        candidates = PolicyCandidatePlan.model_validate_json(
            candidates_upload.getvalue().decode("utf-8")
        )
        cases = _load_cases(cases_upload)

        st.subheader("Lineage F41 → F42")
        with st.container(border=True):
            st.write(
                f"Policy candidate hash: {candidates.policy_candidate_hash}"
            )
            st.write(f"Candidatos: {candidates.candidate_count}")
            st.write(f"Casos cargados: {len(cases)}")
            st.caption(
                "El servicio real volverá a validar target, parámetro, tipo, "
                "rango y baseline antes de ejecutar la simulación lógica."
            )

        if st.button("Simular candidatos", type="primary"):
            request = PolicySimulatorRequest(
                candidates=candidates,
                cases=cases,
            )
            _render_result(build_policy_simulator(request))
    except PolicySimulatorError as exc:
        _render_failure(exc)
    except Exception as exc:
        _render_failure(exc)
