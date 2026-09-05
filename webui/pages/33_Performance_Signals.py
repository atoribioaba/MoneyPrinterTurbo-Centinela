from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.models.metric_normalizer import MetricNormalizerPlan  # noqa: E402
from app.models.performance_signals import (  # noqa: E402
    PerformanceSignalStatus,
    PerformanceSignalsRequest,
)
from app.services.performance_signals import build_performance_signals  # noqa: E402


UI_PREVIEW_LIMIT = 20

st.set_page_config(page_title="F33 · El Centinela", layout="wide")
st.title("F33 · Content Performance Signals")
st.caption(
    "Calcula señales relativas dentro de cohortes de la misma plataforma. "
    "No crea score universal, no mezcla rankings cross-platform y no afirma causalidad."
)

uploaded = st.file_uploader(
    "MetricNormalizerPlan de F32 (JSON)",
    type=["json"],
    help="Carga un MetricNormalizerPlan real. F33 sólo usa métricas normalizadas verificadas.",
)

minimum_cohort_size = st.number_input(
    "Tamaño mínimo de cohorte",
    value=5,
    step=1,
    help=(
        "El valor se valida por PerformanceSignalsRequest. "
        "La UI no corrige ni clampa silenciosamente valores inválidos."
    ),
)


def _render_failure(exc: Exception) -> None:
    st.error(
        "No se han podido preparar las señales de rendimiento. "
        "Revisa el MetricNormalizerPlan y el tamaño mínimo de cohorte."
    )
    with st.expander("Detalles técnicos", expanded=False):
        st.caption(
            "No se fabrica ningún score, ranking global ni conclusión causal."
        )
        st.code(f"{type(exc).__name__}: {exc}", language=None)


if st.button("Preparar señales de rendimiento", type="primary"):
    try:
        if uploaded is None:
            raise ValueError("selecciona un MetricNormalizerPlan JSON de F32")

        metrics_plan = MetricNormalizerPlan.model_validate_json(uploaded.getvalue())
        request = PerformanceSignalsRequest(
            metrics=metrics_plan,
            minimum_cohort_size=minimum_cohort_size,
        )
        result = build_performance_signals(request)

        st.subheader("Fuente y cohorte")
        st.write("Fuente: F32 · Metric Normalizer")
        st.write(f"Hash F32: {result.source_metric_normalizer_hash}")
        st.write(f"Cohorte mínima: {request.minimum_cohort_size}")

        if result.status == PerformanceSignalStatus.WAITING_FOR_ANALYTICS_DATA:
            st.warning(
                "No hay métricas normalizadas suficientes para construir señales."
            )
        elif result.status == PerformanceSignalStatus.INSUFFICIENT_COHORT:
            st.warning(
                "INSUFFICIENT_COHORT: la cohorte es demasiado pequeña. "
                "No se ha fabricado ningún percentile ni score."
            )
        else:
            st.success(
                "Señales de rendimiento preparadas dentro de sus cohortes de plataforma."
            )

        st.metric("Estado", result.status.value)
        st.metric("Contenidos", result.content_count)
        st.metric("Señales listas", result.ready_signal_count)

        st.subheader("Performance signals")
        visible = result.signals[:UI_PREVIEW_LIMIT]
        if result.content_count > UI_PREVIEW_LIMIT:
            st.caption(
                f"Mostrando {UI_PREVIEW_LIMIT} de {result.content_count}. "
                "El plan conserva el conjunto completo."
            )

        for index, signal in enumerate(visible, 1):
            with st.expander(
                f"Señal {index} · {signal.platform.value} · {signal.content_id}",
                expanded=False,
            ):
                st.write(f"Tamaño de cohorte: {signal.cohort_size}")
                st.write(f"Views: {signal.view_count}")
                st.write(f"Interacciones: {signal.interaction_count}")
                st.write(
                    "Ratio de interacción por view: "
                    f"{signal.interaction_rate_per_view}"
                )
                st.write(
                    "Percentil de views dentro de cohorte: "
                    f"{signal.view_percentile_within_cohort}"
                )
                st.write(
                    "Percentil de interacción dentro de cohorte: "
                    f"{signal.interaction_rate_percentile_within_cohort}"
                )
                st.caption(
                    "Señal descriptiva dentro de plataforma; no implica causalidad."
                )

        st.info(
            "F33 termina en PerformanceSignalsPlan. "
            "No ejecuta F35 automáticamente."
        )

        with st.expander("Detalles técnicos", expanded=False):
            st.write(f"Hash F33: {result.performance_signals_hash}")
            st.write(f"Generado UTC: {result.generated_at_utc.isoformat()}")
            st.write(f"Planning only: {result.planning_only}")
            st.write(f"Cross-platform ranking: {result.cross_platform_ranking}")
            st.write(f"Composite score enabled: {result.composite_score_enabled}")
            st.write(f"Causal claims: {result.causal_claims}")
            st.write(f"Network calls: {result.network_calls}")
            st.write(f"Auto publication: {result.auto_publication}")

    except Exception as exc:
        _render_failure(exc)
