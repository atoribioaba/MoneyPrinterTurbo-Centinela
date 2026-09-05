from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.models.metric_normalizer import MetricNormalizerPlan  # noqa: E402
from app.models.retention_intelligence import (  # noqa: E402
    RetentionIntelligenceRequest,
    RetentionStatus,
)
from app.services.retention_intelligence import (  # noqa: E402
    build_retention_intelligence,
)


UI_PREVIEW_LIMIT = 20

st.set_page_config(page_title="F34 · El Centinela", layout="wide")
st.title("F34 · Retention Intelligence")
st.caption(
    "Describe curvas de retención observadas. "
    "No interpola puntos ausentes, no prescribe cambios y no atribuye causalidad."
)

uploaded = st.file_uploader(
    "MetricNormalizerPlan de F32 (JSON)",
    type=["json"],
    help=(
        "Carga un MetricNormalizerPlan real. "
        "F34 sólo describe observaciones AUDIENCE_WATCH_RATIO disponibles."
    ),
)


def _render_failure(exc: Exception) -> None:
    st.error(
        "No se ha podido preparar el análisis de retención. "
        "Comprueba que el archivo corresponde a un MetricNormalizerPlan válido."
    )
    with st.expander("Detalles técnicos", expanded=False):
        st.caption(
            "No se interpolan huecos, no se generan recomendaciones "
            "y no se ejecuta F35."
        )
        st.code(f"{type(exc).__name__}: {exc}", language=None)


if st.button("Preparar análisis de retención", type="primary"):
    try:
        if uploaded is None:
            raise ValueError("selecciona un MetricNormalizerPlan JSON de F32")

        metrics_plan = MetricNormalizerPlan.model_validate_json(uploaded.getvalue())
        result = build_retention_intelligence(
            RetentionIntelligenceRequest(metrics=metrics_plan)
        )

        st.subheader("Fuente")
        st.write("Fuente: F32 · Metric Normalizer")
        st.write(f"Hash F32: {result.source_metric_normalizer_hash}")

        if result.status == RetentionStatus.WAITING_FOR_RETENTION_DATA:
            st.warning(
                "No hay una curva de retención suficiente. "
                "No se han interpolado puntos ni generado recomendaciones."
            )
        else:
            st.success("Curvas de retención observadas preparadas de forma descriptiva.")

        st.metric("Estado", result.status.value)
        st.metric("Curvas observadas", result.curve_count)

        st.subheader("Retention observations")
        visible = result.insights[:UI_PREVIEW_LIMIT]
        if result.curve_count > UI_PREVIEW_LIMIT:
            st.caption(
                f"Mostrando {UI_PREVIEW_LIMIT} de {result.curve_count}. "
                "El plan conserva el conjunto completo."
            )

        for index, insight in enumerate(visible, 1):
            with st.expander(
                f"Curva {index} · {insight.platform.value} · {insight.content_id}",
                expanded=False,
            ):
                st.write(f"Puntos observados: {insight.point_count}")
                st.write(
                    f"Media primeros 10 %: {insight.first_10_percent_mean}"
                )
                st.write(f"Retención cerca del midpoint: {insight.midpoint_ratio}")
                st.write(f"Retención final observada: {insight.final_ratio}")
                st.write(
                    "Mayor caída observada en posición relativa: "
                    f"{insight.largest_drop_position_ratio}"
                )
                st.write(
                    "Magnitud de mayor caída observada: "
                    f"{insight.largest_drop_magnitude}"
                )
                st.caption(
                    "Descripción de observaciones; no identifica la causa de la caída."
                )

        st.info(
            "F34 termina en RetentionIntelligencePlan. "
            "No interpola, no recomienda cambios y no ejecuta F35."
        )

        with st.expander("Detalles técnicos", expanded=False):
            st.write(f"Hash F34: {result.retention_intelligence_hash}")
            st.write(f"Generado UTC: {result.generated_at_utc.isoformat()}")
            st.write(f"Planning only: {result.planning_only}")
            st.write(
                "Interpolates missing points: "
                f"{result.interpolates_missing_points}"
            )
            st.write(f"Causal claims: {result.causal_claims}")
            st.write(
                "Recommendations generated: "
                f"{result.recommendations_generated}"
            )
            st.write(f"Network calls: {result.network_calls}")
            st.write(f"Auto publication: {result.auto_publication}")

    except Exception as exc:
        _render_failure(exc)
