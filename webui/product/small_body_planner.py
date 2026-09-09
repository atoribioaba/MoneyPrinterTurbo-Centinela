from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import streamlit as st

from app.models.astronomy import ObserverContext
from app.models.small_body import SmallBodyObserverRequest
from app.services.centinela.jpl_horizons import fetch_horizons_observer_result


SMALL_BODY_STATE_KEY = "centinela-product-small-body-horizons-result-v1"


def _local_observed_at(observer: ObserverContext, date_value, time_value) -> datetime:
    return datetime.combine(
        date_value,
        time_value,
        tzinfo=ZoneInfo(observer.timezone),
    )


def _render_result(state: dict) -> None:
    result = state["result"]
    provenance = result.provenance

    st.success(f"JPL Horizons · {result.target_name}")
    st.caption(
        "Respuesta topocéntrica para el observador y el instante solicitados. "
        "Las etiquetas/unidades de las columnas se muestran tal como las devuelve Horizons."
    )

    for label, value in result.columns.items():
        with st.container(border=True):
            st.caption(label)
            st.write(value if value else "—")

    with st.expander("Provenance y evidencia"):
        st.write(f"Fuente: {result.api_source}")
        st.write(f"Versión API revisada: {provenance.api_version or 'no disponible'}")
        st.write(f"Target command: {provenance.target_command}")
        st.write(f"Instante consultado UTC: {provenance.query_time_utc.isoformat()}")
        st.write(f"Recuperado UTC: {provenance.retrieved_at_utc.isoformat()}")
        st.code(provenance.result_sha256, language=None)
        st.caption(f"Etiqueta científica: {result.scientific_status.value}")

    st.info(
        "Horizons aporta la efeméride, no una recomendación editorial ni una garantía "
        "de observación. Las afirmaciones destinadas a publicación siguen pasando por "
        "FactLock, fuentes primarias vigentes y revisión humana."
    )


def render_small_body_planner(observer: ObserverContext) -> None:
    st.divider()
    st.subheader("Cometas y asteroides · JPL Horizons")
    st.caption(
        "Consulta manual de una efeméride topocéntrica. Usa un identificador/COMMAND "
        "de Horizons explícito; Centinela no propaga órbitas localmente ni hace polling."
    )

    now_local = datetime.now(ZoneInfo(observer.timezone)).replace(second=0, microsecond=0)
    with st.form("centinela-small-body-horizons-form", clear_on_submit=False):
        target_command = st.text_input(
            "Target command de JPL Horizons",
            placeholder="Ej.: 99942 o DES=2023 A3;",
            max_chars=256,
            key="small-body-target-command",
            help=(
                "Debe ser un selector válido de Horizons. Si el identificador es ambiguo, "
                "el servicio devolverá error y Centinela fallará cerrado."
            ),
        )
        observed_date = st.date_input(
            "Fecha local",
            value=now_local.date(),
            key="small-body-observed-date",
        )
        observed_time = st.time_input(
            "Hora local",
            value=now_local.time(),
            key="small-body-observed-time",
        )
        submitted = st.form_submit_button(
            "Consultar JPL Horizons",
            type="primary",
            use_container_width=True,
        )

    if submitted:
        try:
            command = target_command.strip()
            if not command:
                raise ValueError("Introduce un target command de JPL Horizons.")
            observed_at = _local_observed_at(
                observer,
                observed_date,
                observed_time,
            )
            request = SmallBodyObserverRequest(
                target_command=command,
                observer=observer,
                observed_at=observed_at,
            )
            with st.spinner("Consultando JPL Horizons…", show_time=True):
                result = fetch_horizons_observer_result(
                    request,
                    retrieved_at_utc=datetime.now(UTC),
                    timeout_seconds=20.0,
                )
            st.session_state[SMALL_BODY_STATE_KEY] = {
                "result": result,
                "observer": observer.model_dump(mode="json"),
            }
        except Exception as exc:
            st.error("No se pudo obtener una efeméride válida de JPL Horizons.")
            st.caption(
                "Revisa el identificador, la conectividad o vuelve a intentarlo más tarde. "
                "No se reutiliza una respuesta parcial como si fuera válida."
            )
            with st.expander("Detalle técnico"):
                st.exception(exc)

    state = st.session_state.get(SMALL_BODY_STATE_KEY)
    if not isinstance(state, dict) or "result" not in state:
        st.info("La consulta sólo se realiza cuando pulsas **Consultar JPL Horizons**.")
        return

    if state.get("observer") != observer.model_dump(mode="json"):
        st.warning(
            "La ubicación del observador ha cambiado. Realiza una nueva consulta para "
            "evitar reutilizar una efeméride topocéntrica de otra ubicación."
        )
        return

    _render_result(state)
