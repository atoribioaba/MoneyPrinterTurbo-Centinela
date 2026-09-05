from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.models.analytics_brain import AnalyticsPlatform  # noqa: E402
from app.models.analytics_import_adapter import (  # noqa: E402
    AnalyticsImportFormat,
    AnalyticsImportRequest,
    AnalyticsImportStatus,
)
from app.services.analytics_import_adapter import (  # noqa: E402
    AnalyticsImportError,
    build_analytics_import,
)


UI_PREVIEW_LIMIT = 20

st.set_page_config(page_title="F55 · El Centinela", layout="wide")
st.title("F55 · Analytics Import Adapter")
st.caption(
    "Importa y valida exportaciones CSV/JSON en memoria para preparar el contrato "
    "de Analytics Brain. No guarda datos, no usa APIs y no publica."
)

uploaded = st.file_uploader(
    "Archivo de Analytics",
    type=["csv", "json"],
    help=(
        "Formatos admitidos por F55: CSV y JSON. El archivo se procesa en memoria; "
        "no se accede a rutas del servidor."
    ),
)

platform_options = ["Sin valor por defecto", *[item.value for item in AnalyticsPlatform]]
default_platform_value = st.selectbox(
    "Plataforma por defecto (opcional)",
    options=platform_options,
    help=(
        "Se aplica sólo cuando una fila no incluye platform. No modifica la confianza "
        "semántica ni crea equivalencias entre plataformas."
    ),
)


def _render_failure(exc: Exception) -> None:
    st.error(
        "No se han podido validar los datos de Analytics. "
        "Revisa el archivo y consulta los detalles para identificar la fila o campo "
        "que necesita corrección."
    )
    with st.expander("Detalles técnicos", expanded=False):
        st.caption(
            "Evidencia diagnóstica preservada. No se ha fabricado ningún resultado, "
            "no se ha guardado el archivo y no se ha ejecutado ningún paso downstream."
        )
        st.code(f"{type(exc).__name__}: {exc}", language=None)


def _format_observed_at(value) -> str:
    return value.strftime("%d/%m/%Y · %H:%M UTC")


if st.button("Validar y preparar datos de Analytics", type="primary"):
    try:
        if uploaded is None:
            raise AnalyticsImportError("selecciona un archivo CSV o JSON")

        payload_text = uploaded.getvalue().decode("utf-8")
        filename = uploaded.name.casefold()
        if filename.endswith(".csv"):
            import_format = AnalyticsImportFormat.CSV
        elif filename.endswith(".json"):
            import_format = AnalyticsImportFormat.JSON
        else:
            raise AnalyticsImportError("formato de archivo no soportado")

        default_platform = (
            None
            if default_platform_value == "Sin valor por defecto"
            else AnalyticsPlatform(default_platform_value)
        )
        result = build_analytics_import(
            AnalyticsImportRequest(
                format=import_format,
                payload_text=payload_text,
                default_platform=default_platform,
            )
        )

        if result.status == AnalyticsImportStatus.WAITING_FOR_IMPORT_DATA:
            st.warning(
                "El archivo no contiene observaciones de Analytics. "
                "No se ha preparado ningún dato."
            )
        else:
            st.success("Datos de Analytics validados y preparados correctamente.")
            st.metric("Estado", "Preparado")
            st.metric("Formato", import_format.value)
            st.metric("Filas", result.row_count)
            st.metric("Observaciones válidas", result.observation_count)
            st.info(
                "Preparado para Analytics Brain. F55 no ejecuta F31 automáticamente "
                "y no persiste este resultado."
            )

            visible = result.observations[:UI_PREVIEW_LIMIT]
            st.subheader("Observaciones")
            if result.observation_count > UI_PREVIEW_LIMIT:
                st.caption(
                    f"Mostrando {UI_PREVIEW_LIMIT} de {result.observation_count} "
                    "observaciones. El plan conserva el conjunto completo."
                )

            for index, observation in enumerate(visible, 1):
                with st.expander(
                    f"Observación {index} · {observation.platform.value} · "
                    f"{observation.native_metric_name}",
                    expanded=False,
                ):
                    st.write(f"Contenido: {observation.content_id}")
                    st.write(
                        f"Valor: {observation.value:g} · {observation.value_type.value}"
                    )
                    st.write(f"Observado: {_format_observed_at(observation.observed_at_utc)}")
                    st.write(
                        "Confianza semántica: "
                        f"{observation.semantic_confidence.value}"
                    )
                    st.caption(f"Origen: {observation.source_type.value}")
                    if observation.source_ref:
                        st.caption(f"Referencia de origen: {observation.source_ref}")
                    if observation.position_ratio is not None:
                        st.caption(f"Posición relativa: {observation.position_ratio:g}")
                    st.caption(
                        "Estimado: " + ("sí" if observation.estimated else "no")
                    )

            with st.expander("Detalles técnicos", expanded=False):
                st.caption(
                    "Valores canónicos preservados para trazabilidad. "
                    "La presentación no modifica el AnalyticsImportPlan."
                )
                st.write(f"Estado backend: {result.status.value}")
                st.write(f"Hash F55: {result.analytics_import_hash}")
                st.write(f"Generado UTC: {result.generated_at_utc.isoformat()}")
                st.write(f"Network calls: {result.network_calls}")
                st.write(f"API calls: {result.api_calls}")
                st.write(f"Database writes: {result.database_writes}")
                st.write(f"Auto publication: {result.auto_publication}")

    except Exception as exc:
        _render_failure(exc)
