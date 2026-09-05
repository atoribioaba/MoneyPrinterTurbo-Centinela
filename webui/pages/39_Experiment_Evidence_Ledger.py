from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.models.analytics_brain import AnalyticsPlatform  # noqa: E402
from app.models.experiment_evidence_ledger import (  # noqa: E402
    ExperimentEvidenceLedgerRequest,
    ExperimentEvidenceStatus,
    ExperimentResultInput,
)
from app.models.experiment_planner import ExperimentPlannerPlan  # noqa: E402
from app.services.experiment_evidence_ledger import (  # noqa: E402
    build_experiment_evidence_ledger,
)


UI_PREVIEW_LIMIT = 20

st.set_page_config(page_title="F39 · El Centinela", layout="wide")
st.title("F39 · Experiment Evidence Ledger")
st.caption(
    "Registra resultados introducidos explícitamente por una persona. "
    "No ejecuta experimentos, no calcula p-values y no demuestra causalidad."
)

planner_upload = st.file_uploader(
    "ExperimentPlannerPlan de F35 (JSON)",
    type=["json"],
    key="f39_experiment_planner",
    help="Carga un ExperimentPlannerPlan real generado por F35.",
)

st.subheader("Resultado experimental")
add_result = st.checkbox(
    "Registrar un resultado experimental en este ledger",
    value=False,
    help=(
        "Desactivado = results=[]. F39 permanecerá esperando resultados y "
        "no fabricará evidencia."
    ),
)

if add_result:
    experiment_id = st.text_input("experiment_id")
    hypothesis_id = st.text_input("hypothesis_id")
    platform_value = st.selectbox(
        "platform",
        options=[item.value for item in AnalyticsPlatform],
    )
    success_metric = st.text_input("success_metric")
    control_n = st.number_input(
        "control_n",
        min_value=1,
        step=1,
        value=1,
    )
    variant_n = st.number_input(
        "variant_n",
        min_value=1,
        step=1,
        value=1,
    )
    control_metric_mean = st.number_input(
        "control_metric_mean",
        value=0.0,
        format="%.6f",
    )
    variant_metric_mean = st.number_input(
        "variant_metric_mean",
        value=0.0,
        format="%.6f",
    )
    higher_is_better = st.checkbox(
        "higher_is_better",
        value=True,
    )

    st.caption(
        "Las tres confirmaciones siguientes son atestaciones humanas. "
        "F39 las registra; no las verifica empíricamente."
    )
    randomized_assignment_confirmed = st.checkbox(
        "randomized_assignment_confirmed",
        value=False,
    )
    same_measurement_window_confirmed = st.checkbox(
        "same_measurement_window_confirmed",
        value=False,
    )
    human_reviewed = st.checkbox(
        "human_reviewed",
        value=False,
    )
    notes = st.text_area("notes (opcional)")
else:
    experiment_id = ""
    hypothesis_id = ""
    platform_value = AnalyticsPlatform.YOUTUBE.value
    success_metric = ""
    control_n = 1
    variant_n = 1
    control_metric_mean = 0.0
    variant_metric_mean = 0.0
    higher_is_better = True
    randomized_assignment_confirmed = False
    same_measurement_window_confirmed = False
    human_reviewed = False
    notes = ""


def _render_failure(exc: Exception) -> None:
    st.error(
        "No se ha podido construir el ledger F39. "
        "Comprueba el plan F35 y los datos experimentales introducidos."
    )
    with st.expander("Detalles técnicos", expanded=False):
        st.caption(
            "F39 falla cerrado: no corrige resultados, no inventa "
            "confirmaciones y no genera recomendaciones posteriores."
        )
        st.code(f"{type(exc).__name__}: {exc}", language=None)


if st.button("Construir ledger F39", type="primary"):
    try:
        if planner_upload is None:
            raise ValueError("selecciona un ExperimentPlannerPlan JSON de F35")

        planner = ExperimentPlannerPlan.model_validate_json(
            planner_upload.getvalue()
        )

        results = []
        if add_result:
            result_input = ExperimentResultInput(
                experiment_id=experiment_id,
                hypothesis_id=hypothesis_id,
                platform=AnalyticsPlatform(platform_value),
                success_metric=success_metric,
                control_n=int(control_n),
                variant_n=int(variant_n),
                control_metric_mean=float(control_metric_mean),
                variant_metric_mean=float(variant_metric_mean),
                higher_is_better=higher_is_better,
                randomized_assignment_confirmed=(
                    randomized_assignment_confirmed
                ),
                same_measurement_window_confirmed=(
                    same_measurement_window_confirmed
                ),
                human_reviewed=human_reviewed,
                notes=notes or None,
            )
            results.append(result_input)

        request = ExperimentEvidenceLedgerRequest(
            planner=planner,
            results=results,
        )
        result = build_experiment_evidence_ledger(request)

        st.subheader("Ledger status")
        st.metric("Estado", result.status.value)
        st.metric("Resultados registrados", result.result_count)
        st.metric(
            "Elegibles para revisión de recomendación",
            result.eligible_result_count,
        )

        if result.status == ExperimentEvidenceStatus.WAITING_FOR_EXPERIMENT_RESULTS:
            st.warning(
                "No existen resultados experimentales registrados. "
                "No se ha fabricado evidencia."
            )
        else:
            st.info(
                "RESULTS_RECORDED sólo significa que el ledger contiene "
                "registros. No implica significancia estadística, causalidad "
                "ni validación experimental."
            )

        for index, item in enumerate(
            result.records[:UI_PREVIEW_LIMIT],
            1,
        ):
            with st.expander(
                f"Resultado {index} · {item.experiment_id}",
                expanded=False,
            ):
                st.write(f"Hipótesis: {item.hypothesis_id}")
                st.write(f"Plataforma: {item.platform.value}")
                st.write(f"Métrica: {item.success_metric}")
                st.write(f"Control n: {item.control_n}")
                st.write(f"Variante n: {item.variant_n}")
                st.write(f"Media control: {item.control_metric_mean}")
                st.write(f"Media variante: {item.variant_metric_mean}")
                st.write(f"Delta observado: {item.observed_delta}")
                st.write(
                    "Asignación aleatoria confirmada: "
                    f"{item.randomized_assignment_confirmed}"
                )
                st.write(
                    "Misma ventana de medida confirmada: "
                    f"{item.same_measurement_window_confirmed}"
                )
                st.write(f"Revisión humana: {item.human_reviewed}")
                st.write(
                    "Elegible para revisión de recomendación: "
                    f"{item.eligible_for_recommendation_review}"
                )
                st.caption(
                    "Estas confirmaciones son datos declarados por una persona; "
                    "F39 no las verifica de forma independiente."
                )

        st.info(
            "F39 termina en ExperimentEvidenceLedgerPlan. "
            "No llama F40 automáticamente y no actualiza ninguna política."
        )

        with st.expander("Detalles técnicos", expanded=False):
            st.write(
                "Hash F35: "
                f"{result.source_experiment_planner_hash}"
            )
            st.write(f"Hash F39: {result.experiment_evidence_ledger_hash}")
            st.write(f"Generado UTC: {result.generated_at_utc.isoformat()}")
            st.write(f"Planning only: {result.planning_only}")
            st.write(f"Runs experiments: {result.runs_experiments}")
            st.write(f"Calculates p-values: {result.calculates_p_values}")
            st.write(f"Causal claims: {result.causal_claims}")
            st.write(f"Database writes: {result.database_writes}")
            st.write(f"Network calls: {result.network_calls}")
            st.write(f"Auto apply: {result.auto_apply}")
            st.write(f"Auto publication: {result.auto_publication}")

    except Exception as exc:
        _render_failure(exc)
