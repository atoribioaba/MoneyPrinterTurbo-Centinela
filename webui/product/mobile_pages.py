from __future__ import annotations

import logging
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import streamlit as st

from app.models.astronomy import ObserverContext
from app.services.astronomy_core import get_astronomy_health
from app.services.centinela.event_calendar import MADRID_TIMEZONE, EventCalendarService

from . import pages, ui


LOGGER = logging.getLogger(__name__)


def _observer_controls() -> ObserverContext | None:
    with st.expander("Ubicación y contexto", expanded=True):
        place = st.text_input(
            "Lugar",
            value="Valladolid",
            key="mobile-agenda-observer-name",
        )
        latitude = st.number_input(
            "Latitud (°)",
            min_value=-90.0,
            max_value=90.0,
            value=41.6523,
            format="%.6f",
            key="mobile-agenda-latitude",
        )
        longitude = st.number_input(
            "Longitud (°)",
            min_value=-180.0,
            max_value=180.0,
            value=-4.7245,
            format="%.6f",
            key="mobile-agenda-longitude",
        )
        elevation = st.number_input(
            "Elevación (m)",
            min_value=-500.0,
            max_value=100000.0,
            value=698.0,
            format="%.1f",
            key="mobile-agenda-elevation",
        )
        timezone_name = st.text_input(
            "Zona horaria",
            value=MADRID_TIMEZONE,
            key="mobile-agenda-timezone",
            help="Identificador IANA completo.",
        )

    try:
        ZoneInfo(timezone_name.strip())
        observer = ObserverContext(
            latitude_deg=float(latitude),
            longitude_deg=float(longitude),
            elevation_m=float(elevation),
            timezone=timezone_name.strip(),
            name=place.strip() or None,
        )
    except (ValueError, ZoneInfoNotFoundError) as exc:
        ui.render_error_state(
            "La ubicación no es válida.",
            action="Revisa coordenadas, elevación y zona horaria.",
            technical_detail=exc,
        )
        return None

    st.caption(
        f"{observer.name or 'Observador'} · {observer.latitude_deg:.4f}° · "
        f"{observer.longitude_deg:.4f}° · {observer.elevation_m:.0f} m · "
        f"{observer.timezone}"
    )
    return observer


def _render_event_card(event) -> None:
    provenance = event.canonical_quantity.provenance
    official = provenance.get("official_madrid_time") or {}
    iso = str(official.get("iso8601") or "Hora no disponible")
    abbreviation = str(official.get("abbreviation") or "")
    offset = str(official.get("utc_offset") or "")
    local = provenance.get("local_circumstances") or {}

    with st.container(border=True):
        st.markdown(f"### {event.label_es}")
        if event.body:
            st.caption(str(event.body))
        st.write(f"**{iso.replace('T', ' ')}**")
        if abbreviation or offset:
            st.caption(" · ".join(part for part in (abbreviation, offset) if part))

        if local.get("status") != "not_available" and local:
            altitude = local.get("altitude_deg")
            azimuth = local.get("azimuth_deg")
            above = local.get("above_horizon")
            if altitude is not None and azimuth is not None:
                visibility = "sobre el horizonte" if above else "bajo el horizonte"
                st.write(
                    f"**Desde tu ubicación:** Alt {float(altitude):.1f}° · "
                    f"Az {float(azimuth):.1f}° · {visibility}"
                )

        with st.expander("Detalles científicos"):
            st.write(pages._visibility_and_maximum(event))


def ephemerides_page() -> None:
    ui.render_brand_hero(
        "Agenda del cielo",
        "Calcula efemérides locales y descubre qué fenómenos merecen convertirse en una historia.",
        eyebrow="CIELO",
        action_hint="ASTRONOMY ENGINE · HORA LOCAL · CONTEXTO DEL OBSERVADOR",
    )

    health = get_astronomy_health()
    st.success(f"Observatorio operativo · {health.engine} {health.engine_version}")

    observer = _observer_controls()
    if observer is None:
        return

    ui.render_section_heading(
        "Agenda futura",
        "Elige el horizonte temporal. Los cálculos se realizan para tu ubicación.",
    )
    selected_filter = st.radio(
        "Intervalo",
        options=pages.AGENDA_FILTERS,
        horizontal=True,
        key="mobile-agenda-filter",
    )
    refresh = st.button(
        "Actualizar Agenda Futura",
        type="primary",
        width="stretch",
        key="mobile-agenda-refresh",
    )

    observer_key = pages._observer_summary(observer)
    state = st.session_state.get(pages.AGENDA_SESSION_KEY)
    if refresh:
        try:
            with st.spinner("Calculando efemérides…", show_time=True):
                calendar = EventCalendarService(observer)
                events = pages._agenda_events(calendar, selected_filter)
            state = {
                "filter": selected_filter,
                "observer": observer_key,
                "events": events,
            }
            st.session_state[pages.AGENDA_SESSION_KEY] = state
        except Exception as exc:
            LOGGER.exception("Agenda Futura calculation failed")
            ui.render_error_state(
                "No se pudo calcular la Agenda Futura.",
                action="La ubicación y el intervalo se conservan para que puedas reintentarlo.",
                technical_detail=exc,
            )
            return

    if not state:
        ui.render_empty_state(
            "Todavía no hay resultados",
            "Elige un intervalo y actualiza la Agenda Futura.",
            action="Los resultados aparecerán aquí como eventos legibles en móvil.",
        )
        return

    if state.get("observer") != observer_key:
        st.info("La ubicación ha cambiado. Actualiza la Agenda Futura para recalcular.")
        return

    events = tuple(state.get("events") or ())
    st.caption(f"Intervalo calculado: {state.get('filter', selected_filter)}")
    if not events:
        ui.render_empty_state(
            "No hay eventos en este intervalo",
            "No se han encontrado fenómenos astronómicos para los filtros actuales.",
            action="Prueba otro intervalo temporal.",
        )
        return

    for event in events:
        _render_event_card(event)


def observatory_page() -> None:
    ui.render_brand_hero(
        "Observatorio",
        "Estado de la capacidad astronómica local que sostiene efemérides y planificación.",
        eyebrow="CIELO",
    )
    health = get_astronomy_health()
    ui.render_kpi_card(
        "Estado",
        "Operativo",
        detail="Núcleo astronómico disponible localmente.",
    )
    ui.render_key_value_card("Motor astronómico", health.engine)
    ui.render_key_value_card("Versión", health.engine_version)
    ui.render_key_value_card("Runtime", "Local / CPU")
    st.info(
        "Las efemérides se calculan localmente. La actualidad, misiones y descubrimientos "
        "destinados a publicación siguen requiriendo corroboración con fuentes primarias."
    )


def library_page() -> None:
    service = pages._service()
    ui.render_brand_hero(
        "Biblioteca",
        "Inventario de material propio y verificado que puede alimentar tus producciones.",
        eyebrow="MEDIOS",
    )
    library = service.library()

    ui.render_kpi_card("Material activo", library.active_items)
    ui.render_kpi_card("Publicable", library.publication_eligible_items)
    ui.render_kpi_card(
        "Catálogo",
        "Pendiente" if library.refresh.refresh_catalog else "Al día",
    )

    if library.active_items == 0:
        ui.render_empty_state(
            "Todavía no hay material en la biblioteca",
            "El material propio o verificado aparecerá aquí cuando se incorpore al catálogo.",
            action="El pipeline gestionará el indexado cuando corresponda.",
        )
    elif library.refresh.refresh_catalog:
        st.info(
            "Se han detectado cambios. El catálogo se actualizará cuando la producción "
            "alcance la etapa de Materiales."
        )
    else:
        st.success("La biblioteca no necesita reindexado.")

    with st.expander("Detalles avanzados"):
        st.write(f"Archivos soportados detectados: {library.refresh.supported_file_count}")
        st.write(f"Motivo técnico: {library.refresh.reason}")
        st.caption(
            "Indexado, SemanticMatcher y SmartFocal son responsabilidades del pipeline, "
            "no pasos manuales del flujo normal."
        )


def sources_page() -> None:
    service = pages._service()
    ui.render_brand_hero(
        "Fuentes y derechos",
        "Procedencia, proveedores y estado de derechos del material activo.",
        eyebrow="MEDIOS",
    )
    library = service.library()

    ui.render_section_heading("Proveedores")
    if library.provider_counts:
        for provider, count in library.provider_counts.items():
            ui.render_key_value_card(provider, count, detail="elementos en el catálogo")
    else:
        ui.render_empty_state(
            "Aún no hay proveedores activos",
            "Las fuentes verificadas aparecerán cuando exista material incorporado al catálogo.",
        )

    ui.render_section_heading("Derechos")
    if library.rights_counts:
        for status, count in library.rights_counts.items():
            ui.render_key_value_card(status, count, detail="elementos")
    else:
        ui.render_empty_state(
            "Aún no hay material que clasificar",
            "Los estados de derechos aparecerán cuando el catálogo contenga medios activos.",
        )


def analytics_page() -> None:
    ui.render_brand_hero(
        "Analítica",
        "Métricas editoriales basadas únicamente en datos reales y trazables.",
        eyebrow="RESULTADOS",
    )
    ui.render_empty_state(
        "Todavía no hay datos suficientes",
        "Las métricas aparecerán cuando existan resultados reales importados y trazables.",
        action="No se generan métricas ficticias para rellenar esta vista.",
    )


def system_status_page() -> None:
    service = pages._service()
    ui.render_brand_hero(
        "Estado del sistema",
        "Salud del Control Center y capacidades conectadas al flujo de producción.",
        eyebrow="SISTEMA",
    )

    integrity = service.storage_integrity()
    ui.render_kpi_card(
        "Almacenamiento de proyectos",
        "OK" if integrity == "ok" else integrity.upper(),
    )
    ui.render_kpi_card(
        "Publicación automática",
        "Desactivada",
        detail="La salida sigue siendo manual.",
    )

    ui.render_section_heading(
        "Capacidades",
        "En móvil cada etapa se presenta como una tarjeta legible en lugar de una "
        "tabla comprimida.",
    )
    for item in service.capabilities():
        ui.render_capability_card(
            item.label,
            connected=bool(item.connected),
            backend=str(item.backend_status),
            resource=str(item.resource_class.value),
        )


def settings_page() -> None:
    ui.render_brand_hero(
        "Configuración",
        "Preferencias y versión del producto sin exponer credenciales ni secretos.",
        eyebrow="SISTEMA",
    )

    ui.render_key_value_card("Centinela Edition", pages.CENTINELA_EDITION_LABEL)
    ui.render_key_value_card("Control Center", pages.CONTROL_CENTER_VERSION)
    ui.render_key_value_card(
        "Publicación",
        "Manual",
        detail="La publicación automática permanece desactivada.",
    )

    with st.expander("Detalles del sistema"):
        ui.render_key_value_card("MoneyPrinterTurbo Core", pages._core_version())
        ui.render_key_value_card("Architecture freeze", "No autorizado")
        st.caption("Las API keys, tokens y secretos no se muestran en esta interfaz.")

    st.info(
        "Las herramientas de desarrollador están separadas del flujo normal. "
        "Puedes abrirlas desde **Más → Herramientas de desarrollador** cuando "
        "necesites diagnóstico."
    )
