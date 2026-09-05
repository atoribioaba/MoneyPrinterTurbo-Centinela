from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.models.association_analyzer import (  # noqa: E402
    AssociationAnalyzerRequest,
    AssociationAnalyzerStatus,
)
from app.models.outcome_linker import OutcomeLinkerPlan  # noqa: E402
from app.services.association_analyzer import build_association_analyzer  # noqa: E402


UI_PREVIEW_LIMIT = 30

st.set_page_config(page_title="F38 · El Centinela", layout="wide")
st.title("F38 · Association Analyzer")
st.caption(
    "Calcula asociaciones descriptivas Spearman por plataforma. "
    "No agrupa plataformas, no calcula p-values y correlación no implica causalidad."
)

uploaded = st.file_uploader(
    "OutcomeLinkerPlan de F37 (JSON)",
    type=["json"],
)
minimum_sample_size_text = st.text_input(
    "Muestra mínima por asociación",
    value="5",
    help=(
        "El valor pasa por el contrato Pydantic real de F38 "
        "(rango contractual 5–1000); no se corrige silenciosamente."
    ),
)


def _render_failure(exc: Exception) -> None:
    st.error(
        "No se ha podido preparar el análisis de asociaciones. "
        "Comprueba el OutcomeLinkerPlan y la muestra mínima indicada."
    )
    with st.expander("Detalles técnicos", expanded=False):
        st.caption(
            "F38 falla cerrado: no inventa asociaciones, p-values, "
            "significancia estadística ni causalidad."
        )
        st.code(f"{type(exc).__name__}: {exc}", language=None)


if st.button("Analizar asociaciones", type="primary"):
    try:
        if uploaded is None:
            raise ValueError("selecciona un OutcomeLinkerPlan JSON de F37")

        joined = OutcomeLinkerPlan.model_validate_json(uploaded.getvalue())
        minimum_sample_size = int(minimum_sample_size_text.strip())
        request = AssociationAnalyzerRequest(
            joined=joined,
            minimum_sample_size=minimum_sample_size,
        )
        result = build_association_analyzer(request)

        st.subheader("Linaje de entrada")
        st.write(f"Hash F37: {result.source_outcome_linker_hash}")
        st.write(f"Método: {result.method}")
        st.write(f"Muestra mínima aplicada: {request.minimum_sample_size}")

        if result.status == AssociationAnalyzerStatus.WAITING_FOR_JOINED_DATA:
            st.warning(
                "F37 no contiene datos unidos. "
                "F38 permanece en espera y no fabrica asociaciones."
            )
        elif result.status == AssociationAnalyzerStatus.INSUFFICIENT_SAMPLE:
            st.warning(
                "Hay pares candidatos, pero ninguno alcanza la muestra mínima "
                "para una asociación descriptiva."
            )
        else:
            st.success("Asociaciones Spearman descriptivas preparadas.")

        st.metric("Estado", result.status.value)
        st.metric("Pares candidatos", result.candidate_pair_count)
        st.metric("Asociaciones", result.association_count)

        st.subheader("Asociaciones descriptivas")
        visible = result.associations[:UI_PREVIEW_LIMIT]
        for index, association in enumerate(visible, 1):
            with st.expander(
                f"Asociación {index} · {association.platform.value} · "
                f"{association.feature_name}",
                expanded=False,
            ):
                st.write(f"Métrica: {association.canonical_metric.value}")
                st.write(f"Muestra: {association.sample_size}")
                st.write(f"Spearman ρ: {association.spearman_rho:g}")
                st.write(f"p-value: {association.p_value}")
                st.write(
                    "Significancia estadística afirmada: "
                    f"{association.statistical_significance_claimed}"
                )
                st.write(f"Causalidad afirmada: {association.causal_claim}")
                st.caption("Correlación descriptiva ≠ causalidad.")

        if result.association_count > UI_PREVIEW_LIMIT:
            st.caption(
                f"Mostrando {UI_PREVIEW_LIMIT} de "
                f"{result.association_count} asociaciones."
            )

        st.info(
            "F38 termina en AssociationAnalyzerPlan. "
            "No crea hipótesis experimentales, recomendaciones ni policy candidates."
        )

        with st.expander("Detalles técnicos", expanded=False):
            st.write(f"Hash F38: {result.association_analyzer_hash}")
            st.write(f"Generado UTC: {result.generated_at_utc.isoformat()}")
            st.write(f"Planning only: {result.planning_only}")
            st.write(f"Cross-platform pooling: {result.cross_platform_pooling}")
            st.write(f"P-values calculated: {result.p_values_calculated}")
            st.write(
                "Statistical significance claimed: "
                f"{result.statistical_significance_claimed}"
            )
            st.write(f"Causal claims: {result.causal_claims}")
            st.write(f"Uses LLM: {result.uses_llm}")
            st.write(f"Network calls: {result.network_calls}")
            st.write(f"Auto publication: {result.auto_publication}")

    except Exception as exc:
        _render_failure(exc)
