from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.models.experiment_planner import (  # noqa: E402
    ExperimentHypothesis,
    ExperimentPlannerRequest,
    ExperimentPlannerStatus,
)
from app.models.performance_signals import PerformanceSignalsPlan  # noqa: E402
from app.models.retention_intelligence import RetentionIntelligencePlan  # noqa: E402
from app.services.experiment_planner import build_experiment_planner  # noqa: E402


UI_PREVIEW_LIMIT = 20

st.set_page_config(page_title="F35 · El Centinela", layout="wide")
st.title("F35 · Experiment Planner")
st.caption(
    "Prepara una hipótesis escrita por una persona usando evidencia F33/F34. "
    "No ejecuta experimentos, no demuestra causalidad y no publica contenido."
)

st.subheader("Evidence inputs")
performance_upload = st.file_uploader(
    "PerformanceSignalsPlan de F33 (JSON)",
    type=["json"],
    key="f35_performance_plan",
    help="Carga un PerformanceSignalsPlan real generado por F33.",
)
retention_upload = st.file_uploader(
    "RetentionIntelligencePlan de F34 (JSON)",
    type=["json"],
    key="f35_retention_plan",
    help="Carga un RetentionIntelligencePlan real generado por F34.",
)

st.subheader("Hipótesis humana")
hypothesis_id = st.text_input("hypothesis_id")
variable = st.text_input("variable")
rationale = st.text_area("rationale")
evidence_refs_text = st.text_area(
    "evidence_refs",
    help="Una referencia de evidencia por línea. Debe existir al menos una.",
)
control_definition = st.text_area("control_definition")
variant_definition = st.text_area("variant_definition")
success_metric = st.text_input("success_metric")

st.caption(
    "Contrato F35: una sola variable por hipótesis. "
    "La hipótesis no se genera ni completa automáticamente."
)


def _render_failure(exc: Exception) -> None:
    st.error(
        "No se ha podido preparar la hipótesis candidata. "
        "Comprueba los planes F33/F34 y todos los campos de la hipótesis."
    )
    with st.expander("Detalles técnicos", expanded=False):
        st.caption(
            "F35 falla cerrado: no corrige payloads, no ejecuta experimentos "
            "y no crea evidencia posterior."
        )
        st.code(f"{type(exc).__name__}: {exc}", language=None)


if st.button("Preparar hipótesis candidata", type="primary"):
    try:
        if performance_upload is None:
            raise ValueError("selecciona un PerformanceSignalsPlan JSON de F33")
        if retention_upload is None:
            raise ValueError("selecciona un RetentionIntelligencePlan JSON de F34")

        performance = PerformanceSignalsPlan.model_validate_json(
            performance_upload.getvalue()
        )
        retention = RetentionIntelligencePlan.model_validate_json(
            retention_upload.getvalue()
        )

        evidence_refs = [
            line.strip()
            for line in evidence_refs_text.splitlines()
            if line.strip()
        ]
        hypothesis = ExperimentHypothesis(
            hypothesis_id=hypothesis_id,
            variable=variable,
            rationale=rationale,
            evidence_refs=evidence_refs,
            control_definition=control_definition,
            variant_definition=variant_definition,
            success_metric=success_metric,
            changes_one_variable_only=True,
            auto_apply=False,
            auto_publish=False,
        )
        request = ExperimentPlannerRequest(
            performance=performance,
            retention=retention,
            candidate_hypotheses=[hypothesis],
        )
        result = build_experiment_planner(request)

        st.subheader("Planner status")
        st.metric("Estado", result.status.value)
        st.metric("Hipótesis liberadas", result.hypothesis_count)

        if result.status == ExperimentPlannerStatus.WAITING_FOR_EVIDENCE:
            st.warning(
                "No existe evidencia F33/F34 suficiente. "
                "La hipótesis candidata no ha sido liberada. "
                "No se ejecuta ningún experimento."
            )
            st.info(
                "Hipótesis enviada: NO LIBERADA / SUPRIMIDA POR EL GATE DE EVIDENCIA."
            )
        else:
            st.success(
                "Hipótesis candidata preparada para revisión y ejecución humana. "
                "Esto no significa que el experimento esté aprobado, ejecutado "
                "ni validado."
            )

        st.subheader("Hipótesis liberadas")
        visible = result.hypotheses[:UI_PREVIEW_LIMIT]
        if result.hypothesis_count > UI_PREVIEW_LIMIT:
            st.caption(
                f"Mostrando {UI_PREVIEW_LIMIT} de {result.hypothesis_count}. "
                "El plan conserva el conjunto completo."
            )

        for index, item in enumerate(visible, 1):
            with st.expander(
                f"Hipótesis {index} · {item.hypothesis_id}",
                expanded=False,
            ):
                st.write(f"Variable: {item.variable}")
                st.write(f"Rationale: {item.rationale}")
                st.write(f"Evidence refs: {', '.join(item.evidence_refs)}")
                st.write(f"Control: {item.control_definition}")
                st.write(f"Variante: {item.variant_definition}")
                st.write(f"Success metric: {item.success_metric}")
                st.write(
                    "Changes one variable only: "
                    f"{item.changes_one_variable_only}"
                )
                st.caption(
                    "Candidata para revisión/ejecución humana; no es un resultado "
                    "experimental ni una prueba causal."
                )

        st.info(
            "F35 termina en ExperimentPlannerPlan. "
            "No asigna grupos, no recopila mediciones y no registra resultados."
        )

        with st.expander("Detalles técnicos", expanded=False):
            st.write(f"Hash F33: {result.source_performance_hash}")
            st.write(f"Hash F34: {result.source_retention_hash}")
            st.write(f"Hash F35: {result.experiment_planner_hash}")
            st.write(f"Generado UTC: {result.generated_at_utc.isoformat()}")
            st.write(f"Evidence sufficient: {result.evidence_sufficient}")
            st.write(f"Planning only: {result.planning_only}")
            st.write(f"Runs experiments: {result.runs_experiments}")
            st.write(f"Edits project: {result.edits_project}")
            st.write(f"Publishes content: {result.publishes_content}")
            st.write(f"Causal claims: {result.causal_claims}")
            st.write(f"Uses LLM: {result.uses_llm}")
            st.write(f"Network calls: {result.network_calls}")

    except Exception as exc:
        _render_failure(exc)
