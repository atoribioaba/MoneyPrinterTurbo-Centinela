from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.models.analytics_import_adapter import AnalyticsImportPlan  # noqa: E402
from app.services.analytics_brain import build_analytics_brain  # noqa: E402


UI_PREVIEW_LIMIT = 20

st.set_page_config(page_title="F31 · El Centinela", layout="wide")
st.title("F31 · Analytics Brain")
st.caption(
    "Consume el contrato validado por F55 y prepara el plan analítico canónico. "
    "No reimporta CSV/JSON, no normaliza métricas y no ejecuta pasos downstream."
)

uploaded = st.file_uploader(
    "AnalyticsImportPlan de F55 (JSON)",
    type=["json"],
    help=(
        "Carga un AnalyticsImportPlan serializado por la fase F55. "
        "F31 valida el modelo real y usa exactamente su analytics_request."
    ),
)


def _render_failure(exc: Exception) -> None:
    st.error(
        "No se ha podido preparar Analytics Brain. "
        "Comprueba que el archivo corresponde a un AnalyticsImportPlan válido de F55."
    )
    with st.expander("Detalles técnicos", expanded=False):
        st.caption(
            "La evidencia diagnóstica se conserva sin fabricar observaciones, "
            "sin persistencia y sin ejecutar F32 ni fases posteriores."
        )
        st.code(f"{type(exc).__name__}: {exc}", language=None)


if st.button("Preparar plan analítico", type="primary"):
    try:
        if uploaded is None:
            raise ValueError("selecciona un AnalyticsImportPlan JSON de F55")

        import_plan = AnalyticsImportPlan.model_validate_json(uploaded.getvalue())
        analytics_request = import_plan.analytics_request
        result = build_analytics_brain(analytics_request)

        st.subheader("Linaje de entrada")
        st.write("Fuente: F55 · Analytics Import Adapter")
        st.write(f"Estado F55: {import_plan.status.value}")
        st.write(f"Hash F55: {import_plan.analytics_import_hash}")
        st.write(
            f"Observaciones recibidas sin reinterpretación: "
            f"{len(analytics_request.observations)}"
        )

        if not result.observations:
            st.warning(
                "No hay observaciones analíticas disponibles. "
                "F31 permanece en espera y no fabrica datos de ejemplo."
            )
        else:
            st.success("AnalyticsBrainPlan preparado con observaciones reales de F55.")

        st.metric("Estado", result.status)
        st.metric("Observaciones", result.observation_count)
        st.metric("Plataformas", result.platform_count)
        st.metric("Contenidos", result.content_count)

        st.subheader("Observaciones disponibles")
        visible = result.observations[:UI_PREVIEW_LIMIT]
        if result.observation_count > UI_PREVIEW_LIMIT:
            st.caption(
                f"Mostrando {UI_PREVIEW_LIMIT} de {result.observation_count}. "
                "El plan conserva el conjunto completo."
            )

        for index, observation in enumerate(visible, 1):
            with st.expander(
                f"Observación {index} · {observation.platform.value} · "
                f"{observation.native_metric_name}",
                expanded=False,
            ):
                st.write(f"Contenido: {observation.content_id}")
                st.write(
                    f"Valor nativo: {observation.value:g} · "
                    f"{observation.value_type.value}"
                )
                st.write(
                    "Confianza semántica: "
                    f"{observation.semantic_confidence.value}"
                )
                if observation.position_ratio is not None:
                    st.write(
                        f"Posición relativa observada: "
                        f"{observation.position_ratio:g}"
                    )
                st.caption(
                    "F31 preserva esta observación nativa; la normalización pertenece a F32."
                )

        st.info(
            "F31 termina en AnalyticsBrainPlan. "
            "No ejecuta F32 automáticamente."
        )

        with st.expander("Detalles técnicos", expanded=False):
            st.write(f"Hash F31: {result.analytics_brain_hash}")
            st.write(f"Generado UTC: {result.generated_at_utc.isoformat()}")
            st.write(f"Planning only: {result.planning_only}")
            st.write(f"Storage writes: {result.storage_writes}")
            st.write(f"API calls: {result.api_calls}")
            st.write(f"Network calls: {result.network_calls}")
            st.write(f"GPU required: {result.gpu_required}")
            st.write(f"Auto publication: {result.auto_publication}")

    except Exception as exc:
        _render_failure(exc)
