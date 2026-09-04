from __future__ import annotations

import logging
import re
from datetime import UTC, datetime
from html import escape
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import streamlit as st

from app.models.astronomy import ObserverContext
from app.services.astronomy_core import get_astronomy_health
from app.services.centinela.event_calendar import MADRID_TIMEZONE, EventCalendarService

from . import pages, ui


LOGGER = logging.getLogger(__name__)

_BODY_LABELS_ES = {
    "sun": "Sol",
    "moon": "Luna",
    "mercury": "Mercurio",
    "venus": "Venus",
    "mars": "Marte",
    "jupiter": "Júpiter",
    "saturn": "Saturno",
    "uranus": "Urano",
    "neptune": "Neptuno",
    "pluto": "Plutón",
}
_BODY_TOKEN_RE = re.compile(
    r"\b(" + "|".join(re.escape(item) for item in _BODY_LABELS_ES) + r")\b",
    flags=re.IGNORECASE,
)
_MONTHS_ES = (
    "enero",
    "febrero",
    "marzo",
    "abril",
    "mayo",
    "junio",
    "julio",
    "agosto",
    "septiembre",
    "octubre",
    "noviembre",
    "diciembre",
)


def body_label_es(value: object) -> str:
    raw = str(getattr(value, "value", value) or "").strip()
    if not raw:
        return ""
    return _BODY_LABELS_ES.get(raw.lower(), raw)


def _localize_body_tokens(value: object) -> str:
    text = str(value or "")
    return _BODY_TOKEN_RE.sub(
        lambda match: _BODY_LABELS_ES[match.group(0).lower()],
        text,
    )


def event_title_es(event: object) -> str:
    event_type = str(getattr(event, "event_type", "") or "")
    details = getattr(event, "details", {}) or {}
    pair = details.get("body_pair") if isinstance(details, dict) else None
    if event_type == "apparent_conjunction" and isinstance(pair, (list, tuple)) and len(pair) == 2:
        left_raw = str(pair[0]).lower()
        left = body_label_es(pair[0])
        right = body_label_es(pair[1])
        left_phrase = f"la {left}" if left_raw == "moon" else left
        return f"Conjunción aparente de {left_phrase} y {right}"
    return _localize_body_tokens(getattr(event, "label_es", "Evento astronómico"))


def event_time_es(event: object) -> str:
    provenance = getattr(getattr(event, "canonical_quantity", None), "provenance", {}) or {}
    official = provenance.get("official_madrid_time") or {}
    iso = str(official.get("iso8601") or "").strip()
    moment: datetime | None = None
    if iso:
        try:
            moment = datetime.fromisoformat(iso)
        except ValueError:
            moment = None
    if moment is None:
        fallback = getattr(event, "time_local", None)
        if isinstance(fallback, datetime):
            moment = fallback
    if moment is None:
        return "Hora pendiente de consulta"
    abbreviation = str(official.get("abbreviation") or moment.tzname() or "").strip()
    month = _MONTHS_ES[moment.month - 1]
    suffix = f" {abbreviation}" if abbreviation else ""
    return f"{moment.day} de {month} de {moment.year} · {moment:%H:%M}{suffix}"


def _agenda_now_utc(calendar: EventCalendarService) -> datetime:
    now_local = calendar._local_moment()
    if now_local.tzinfo is None or now_local.utcoffset() is None:
        raise ValueError("Agenda future authority must be timezone-aware")
    return now_local.astimezone(UTC)


def _future_only_events(events, now: datetime):
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("future agenda cutoff must be timezone-aware")
    cutoff = now.astimezone(UTC)
    future = []
    for event in events:
        event_time = getattr(event, "time_utc", None)
        if not isinstance(event_time, datetime):
            continue
        if event_time.tzinfo is None or event_time.utcoffset() is None:
            raise ValueError("future agenda event time must be timezone-aware")
        if event_time.astimezone(UTC) >= cutoff:
            future.append(event)
    return tuple(future)


def _future_agenda_events(calendar: EventCalendarService, selected_filter: str):
    candidates = pages._agenda_events(calendar, selected_filter)
    return _future_only_events(candidates, _agenda_now_utc(calendar))


def _decimal_es(value: object, digits: int, *, show_plus: bool = False) -> str:
    number = float(value)
    if show_plus:
        rendered = f"{number:+.{digits}f}"
    else:
        rendered = f"{number:.{digits}f}"
    return rendered.replace("-", "−", 1).replace(".", ",")


def _ra_hm(value: object) -> str:
    total_minutes = int(round(float(value) * 60.0)) % (24 * 60)
    hours, minutes = divmod(total_minutes, 60)
    return f"{hours} h {minutes:02d} min"


def _dec_dm(value: object) -> str:
    degrees_value = float(value)
    sign = "+" if degrees_value >= 0 else "−"
    total_minutes = int(round(abs(degrees_value) * 60.0))
    degrees, minutes = divmod(total_minutes, 60)
    return f"{sign}{degrees}° {minutes:02d}′"


def _visibility_presentation(event: object) -> dict[str, object]:
    provenance = getattr(getattr(event, "canonical_quantity", None), "provenance", {}) or {}
    local = provenance.get("local_circumstances") or {}
    if not local or local.get("status") == "not_available":
        return {
            "label": "VISIBILIDAD NO DISPONIBLE",
            "detail": "No hay circunstancias locales disponibles para este evento.",
            "tone": "neutral",
            "altitude": None,
            "azimuth": None,
        }
    above = bool(local.get("above_horizon"))
    return {
        "label": "VISIBLE DESDE TU UBICACIÓN" if above else "NO VISIBLE DESDE TU UBICACIÓN",
        "detail": "Sobre el horizonte" if above else "Bajo el horizonte",
        "tone": "visible" if above else "warning",
        "altitude": local.get("altitude_deg"),
        "azimuth": local.get("azimuth_deg"),
    }


def _scientific_detail_rows(event: object) -> tuple[tuple[str, str], ...]:
    provenance = getattr(getattr(event, "canonical_quantity", None), "provenance", {}) or {}
    local = provenance.get("local_circumstances") or {}
    global_maximum = provenance.get("global_maximum") or {}
    celestial = provenance.get("celestial_region") or {}
    rows: list[tuple[str, str]] = []

    if local and local.get("status") != "not_available":
        if local.get("altitude_deg") is not None:
            rows.append(("Altitud", f"{_decimal_es(local['altitude_deg'], 2)}°"))
        if local.get("azimuth_deg") is not None:
            rows.append(("Azimut", f"{_decimal_es(local['azimuth_deg'], 2)}°"))
        rows.append(
            (
                "Visibilidad",
                "Sobre el horizonte" if local.get("above_horizon") else "Bajo el horizonte",
            )
        )
    else:
        rows.append(("Visibilidad", "No disponible"))

    if celestial and celestial.get("status") != "not_available":
        if celestial.get("right_ascension_hours") is not None:
            rows.append(("Ascensión recta", _ra_hm(celestial["right_ascension_hours"])))
        if celestial.get("declination_deg") is not None:
            rows.append(("Declinación", _dec_dm(celestial["declination_deg"])))

    maximum_status = global_maximum.get("status")
    if maximum_status == "available":
        latitude = global_maximum.get("latitude_deg")
        longitude = global_maximum.get("longitude_deg")
        if latitude is not None and longitude is not None:
            rows.append(
                (
                    "Máximo terrestre",
                    f"{_decimal_es(latitude, 2, show_plus=True)}°, "
                    f"{_decimal_es(longitude, 2, show_plus=True)}°",
                )
            )
        else:
            rows.append(("Máximo terrestre", "Disponible"))
    elif maximum_status == "not_applicable":
        rows.append(("Máximo terrestre", "No aplica a este tipo de fenómeno."))
    elif maximum_status is not None:
        rows.append(("Máximo terrestre", "No disponible"))

    return tuple(rows)


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


def _render_event_card(event, *, index: int) -> None:
    title = event_title_es(event)
    body = body_label_es(getattr(event, "body", None))
    human_time = event_time_es(event)
    visibility = _visibility_presentation(event)

    with st.container(border=True, key=f"centinela-ephemeris-card-{index}"):
        body_markup = f"<p>{escape(body)}</p>" if body else ""
        st.html(
            '<div class="centinela-event-heading">'
            '<div class="centinela-event-heading__eyebrow">EFEMÉRIDE</div>'
            f"<h3>{escape(title)}</h3>"
            f"{body_markup}"
            "</div>"
        )
        st.html(f'<div class="centinela-event-time">{escape(human_time)}</div>')

        visibility_class = (
            " centinela-event-visibility--visible"
            if visibility["tone"] == "visible"
            else ""
        )
        st.html(
            f'<div class="centinela-event-visibility{visibility_class}">'
            f"<strong>{escape(str(visibility['label']))}</strong>"
            f"<span>{escape(str(visibility['detail']))}</span>"
            "</div>"
        )

        altitude = visibility.get("altitude")
        azimuth = visibility.get("azimuth")
        if altitude is not None and azimuth is not None:
            st.caption(
                f"Altitud {_decimal_es(altitude, 1)}° · "
                f"Azimut {_decimal_es(azimuth, 1)}°"
            )

        rows = _scientific_detail_rows(event)
        with st.expander("Detalles científicos"):
            markup = "".join(
                '<div class="centinela-science-row">'
                f"<span>{escape(label)}</span><strong>{escape(value)}</strong>"
                "</div>"
                for label, value in rows
            )
            st.html(f'<div class="centinela-science-rows">{markup}</div>')
            st.caption(
                "La evidencia original y su precisión completa se conservan en la "
                "trazabilidad científica del evento."
            )


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
    calendar = EventCalendarService(observer)
    if refresh:
        try:
            with st.spinner("Calculando efemérides…", show_time=True):
                events = _future_agenda_events(calendar, selected_filter)
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

    stored_events = tuple(state.get("events") or ())
    events = _future_only_events(stored_events, _agenda_now_utc(calendar))
    if events != stored_events:
        state = dict(state)
        state["events"] = events
        st.session_state[pages.AGENDA_SESSION_KEY] = state

    st.caption(f"Intervalo calculado: {state.get('filter', selected_filter)}")
    if not events:
        ui.render_empty_state(
            "No hay eventos futuros en este intervalo",
            "Los fenómenos que ya han pasado se excluyen de Agenda futura.",
            action="Prueba otro intervalo temporal.",
        )
        return

    for index, event in enumerate(events):
        _render_event_card(event, index=index)


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
