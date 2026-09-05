from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.models.analytics_brain import AnalyticsBrainPlan  # noqa: E402
from app.models.metric_normalizer import (  # noqa: E402
    MetricNormalizerRequest,
    NormalizationStatus,
)
from app.services.metric_normalizer import build_metric_normalizer  # noqa: E402


UI_PREVIEW_LIMIT = 20

st.set_page_config(page_title="F32 · El Centinela", layout="wide")
st.title("F32 · Metric Normalizer")
st.caption(
    "Aplica únicamente los mapeos canónicos verificados por el backend. "
    "Las métricas desconocidas permanecen NATIVE_ONLY y nunca se asume "
    "equivalencia entre plataformas."
)

uploaded = st.file_uploader(
    "AnalyticsBrainPlan de F31 (JSON)",
    type=["json"],
    help="Carga un AnalyticsBrainPlan real. F32 no reconstruye ni reinterpreta F31.",
)


def _render_failure(exc: Exception) -> None:
    st.error(
        "No se ha podido preparar la normalización. "
        "Comprueba que el archivo corresponde a un AnalyticsBrainPlan válido."
    )
    with st.expander("Detalles técnicos", expanded=False):
        st.caption(
            "No se crea ningún mapping alternativo, no se promocionan métricas "
            "desconocidas y no se ejecutan fases posteriores."
        )
        st.code(f"{type(exc).__name__}: {exc}", language=None)


if st.button("Preparar normalización", type="primary"):
    try:
        if uploaded is None:
            raise ValueError("selecciona un AnalyticsBrainPlan JSON de F31")

        analytics_plan = AnalyticsBrainPlan.model_validate_json(uploaded.getvalue())
        result = build_metric_normalizer(
            MetricNormalizerRequest(analytics=analytics_plan)
        )

        st.subheader("Fuente")
        st.write("Fuente: F31 · Analytics Brain")
        st.write(f"Hash F31: {result.source_analytics_hash}")
        st.write(f"Observaciones recibidas: {result.observation_count}")

        if not result.observations:
            st.warning(
                "No hay métricas para normalizar. "
                "F32 permanece en espera y no fabrica equivalencias."
            )
        else:
            st.success("MetricNormalizerPlan preparado con el contrato real de F32.")

        st.metric("Estado", result.status)
        st.metric("Normalizadas", result.normalized_count)
        st.metric("Sólo nativas", result.native_only_count)

        if result.native_only_count:
            st.warning(
                "Hay métricas sin mapping verificado. "
                "Se conservan como NATIVE_ONLY con canonical_metric=None."
            )

        st.subheader("Métricas detectadas")
        visible = result.observations[:UI_PREVIEW_LIMIT]
        if result.observation_count > UI_PREVIEW_LIMIT:
            st.caption(
                f"Mostrando {UI_PREVIEW_LIMIT} de {result.observation_count}. "
                "El plan conserva el conjunto completo."
            )

        for index, item in enumerate(visible, 1):
            source = item.source
            canonical = (
                item.canonical_metric.value
                if item.canonical_metric is not None
                else "None"
            )
            with st.expander(
                f"Métrica {index} · {source.platform.value} · "
                f"{source.native_metric_name}",
                expanded=False,
            ):
                st.write(f"Estado: {item.normalization_status.value}")
                st.write(f"Métrica canónica: {canonical}")
                st.write(f"Base de mapping: {item.mapping_basis}")
                st.write(
                    "Equivalencia cross-platform asumida: "
                    f"{item.cross_platform_equivalence_assumed}"
                )
                if item.normalization_status == NormalizationStatus.NATIVE_ONLY:
                    st.caption(
                        "Sin mapping verificado: se conserva la semántica nativa."
                    )

        st.info(
            "F32 no crea rankings globales ni ejecuta F33/F34 automáticamente."
        )

        with st.expander("Detalles técnicos", expanded=False):
            st.write(f"Hash F32: {result.metric_normalizer_hash}")
            st.write(f"Generado UTC: {result.generated_at_utc.isoformat()}")
            st.write(f"Planning only: {result.planning_only}")
            st.write(
                "Cross-platform equivalence: "
                f"{result.cross_platform_equivalence_assumed}"
            )
            st.write(f"API calls: {result.api_calls}")
            st.write(f"Network calls: {result.network_calls}")
            st.write(f"Auto publication: {result.auto_publication}")

    except Exception as exc:
        _render_failure(exc)
