from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.models.content_feature_registry import (  # noqa: E402
    ContentFeatureRegistryPlan,
)
from app.models.metric_normalizer import MetricNormalizerPlan  # noqa: E402
from app.models.outcome_linker import (  # noqa: E402
    OutcomeLinkerRequest,
    OutcomeLinkerStatus,
)
from app.services.outcome_linker import build_outcome_linker  # noqa: E402


UI_PREVIEW_LIMIT = 20

st.set_page_config(page_title="F37 · El Centinela", layout="wide")
st.title("F37 · Outcome Linker")
st.caption(
    "Une features y outcomes sólo por platform + content_id exactos. "
    "Ignora métricas NATIVE_ONLY, no cruza plataformas y no interpola observaciones."
)

uploaded_features = st.file_uploader(
    "ContentFeatureRegistryPlan de F36 (JSON)",
    type=["json"],
    key="f37_features",
)
uploaded_metrics = st.file_uploader(
    "MetricNormalizerPlan de F32 (JSON)",
    type=["json"],
    key="f37_metrics",
)


def _render_failure(exc: Exception) -> None:
    st.error(
        "No se ha podido enlazar features y outcomes. "
        "Comprueba que los archivos corresponden a F36 y F32 y conservan sus contratos."
    )
    with st.expander("Detalles técnicos", expanded=False):
        st.caption(
            "F37 no fuerza bindings, no promociona NATIVE_ONLY, "
            "no hace joins cross-platform y no ejecuta F38."
        )
        st.code(f"{type(exc).__name__}: {exc}", language=None)


if st.button("Preparar enlace de outcomes", type="primary"):
    try:
        if uploaded_features is None:
            raise ValueError("selecciona un ContentFeatureRegistryPlan JSON de F36")
        if uploaded_metrics is None:
            raise ValueError("selecciona un MetricNormalizerPlan JSON de F32")

        features = ContentFeatureRegistryPlan.model_validate_json(
            uploaded_features.getvalue()
        )
        metrics = MetricNormalizerPlan.model_validate_json(
            uploaded_metrics.getvalue()
        )
        result = build_outcome_linker(
            OutcomeLinkerRequest(
                features=features,
                metrics=metrics,
            )
        )

        st.subheader("Linaje de entrada")
        st.write(f"Hash F36: {result.source_content_feature_registry_hash}")
        st.write(f"Hash F32: {result.source_metric_normalizer_hash}")

        if result.status == OutcomeLinkerStatus.WAITING_FOR_BOUND_CONTENT_ANALYTICS:
            st.warning(
                "No hay pares elegibles con binding real y métrica normalizada "
                "verificada. "
                "F37 permanece en espera y no fabrica outcomes."
            )
        else:
            st.success(
                "OutcomeLinkerPlan preparado con joins exactos por plataforma + "
                "content_id."
            )

        st.metric("Estado", result.status.value)
        st.metric("Registros unidos", result.record_count)
        st.metric("Outcomes unidos", result.joined_outcome_count)

        st.subheader("Registros feature → outcome")
        visible = result.records[:UI_PREVIEW_LIMIT]
        for index, record in enumerate(visible, 1):
            with st.expander(
                f"Registro {index} · {record.platform.value} · {record.content_id}",
                expanded=False,
            ):
                st.write(f"Snapshot ID: {record.snapshot_id}")
                st.write(f"Features: {len(record.features)}")
                st.write(f"Outcomes: {record.outcome_count}")
                for outcome in record.outcomes:
                    st.write(f"{outcome.canonical_metric.value}: {outcome.value:g}")
                    st.caption(
                        f"Observado UTC: {outcome.observed_at_utc.isoformat()} · "
                        f"nativa: {outcome.source_native_metric_name}"
                    )

        if result.record_count > UI_PREVIEW_LIMIT:
            st.caption(
                f"Mostrando {UI_PREVIEW_LIMIT} de {result.record_count} registros."
            )

        st.info(
            "F37 termina en OutcomeLinkerPlan. "
            "No ejecuta F38 automáticamente."
        )

        with st.expander("Detalles técnicos", expanded=False):
            st.write(f"Hash F37: {result.outcome_linker_hash}")
            st.write(f"Generado UTC: {result.generated_at_utc.isoformat()}")
            st.write(f"Planning only: {result.planning_only}")
            st.write(f"Joins native-only metrics: {result.joins_native_only_metrics}")
            st.write(f"Cross-platform join: {result.cross_platform_join}")
            st.write(f"Interpolates observations: {result.interpolates_observations}")
            st.write(f"Uses LLM: {result.uses_llm}")
            st.write(f"Network calls: {result.network_calls}")
            st.write(f"Database writes: {result.database_writes}")
            st.write(f"Auto publication: {result.auto_publication}")

    except Exception as exc:
        _render_failure(exc)
