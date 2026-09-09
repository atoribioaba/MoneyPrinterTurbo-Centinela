from __future__ import annotations

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import streamlit as st

from app.models.astronomy import ObserverContext, ScientificStatus
from app.models.observation import (
    EvidenceKind,
    ObservationObjectClass,
    ObservabilityRequest,
    SkyQualityContext,
)
from app.models.sky_planning import (
    FixedSkyTarget,
    FixedSkyTargetKind,
    LandscapeWindowRequest,
)
from app.services.centinela.observation_dashboard import build_observation_dashboard
from app.services.centinela.observation_intelligence import evaluate_observability
from app.services.centinela.open_meteo_observation import fetch_open_meteo_snapshot
from app.services.centinela.seven_timer_astro import fetch_7timer_astro_snapshots
from app.services.centinela.sky_window_planner import plan_landscape_window


PLANNER_STATE_KEY = "centinela-product-observation-planner-result-v1"

_TARGET_KIND_LABELS = {
    "Cielo profundo": FixedSkyTargetKind.DEEP_SKY,
    "Campo de Vía Láctea": FixedSkyTargetKind.MILKY_WAY_FIELD,
    "Centro galáctico": FixedSkyTargetKind.GALACTIC_CENTER,
    "Estrella / campo estelar": FixedSkyTargetKind.STAR,
    "Otro objetivo fijo": FixedSkyTargetKind.OTHER,
}

_OBJECT_CLASS_BY_KIND = {
    FixedSkyTargetKind.DEEP_SKY: ObservationObjectClass.DEEP_SKY,
    FixedSkyTargetKind.MILKY_WAY_FIELD: ObservationObjectClass.MILKY_WAY,
    FixedSkyTargetKind.GALACTIC_CENTER: ObservationObjectClass.MILKY_WAY,
    FixedSkyTargetKind.STAR: ObservationObjectClass.GENERAL,
    FixedSkyTargetKind.OTHER: ObservationObjectClass.GENERAL,
}


def _local_start(observer: ObserverContext, date_value, time_value) -> datetime:
    zone = ZoneInfo(observer.timezone)
    return datetime.combine(date_value, time_value, tzinfo=zone)


def _nearest_conditions(snapshots, target_time: datetime):
    if not snapshots:
        return None
    nearest = min(
        snapshots,
        key=lambda item: abs(item.valid_at - target_time.astimezone(UTC)),
    )
    distance_hours = abs(
        (nearest.valid_at - target_time.astimezone(UTC)).total_seconds()
    ) / 3600.0
    return nearest if distance_hours <= 3.1 else None


def _sky_quality_controls() -> SkyQualityContext | None:
    enabled = st.checkbox(
        "Añadir calidad de cielo (opcional)",
        value=False,
        key="observation-planner-sky-quality-enabled",
    )
    if not enabled:
        return None

    mode = st.selectbox(
        "Origen de calidad de cielo",
        options=("SQM medido", "Bortle de mapa", "Bortle estimado"),
        key="observation-planner-sky-quality-mode",
    )
    source_id = st.text_input(
        "Identificador de fuente",
        value="user-supplied-sky-quality",
        key="observation-planner-sky-quality-source",
        help="Ej.: sqm-2026-09-09-campo o nombre/version del mapa consultado.",
    ).strip()
    if not source_id:
        st.warning("La calidad de cielo no se usará sin un identificador de fuente.")
        return None

    if mode == "SQM medido":
        sqm = st.number_input(
            "SQM (mag/arcsec²)",
            min_value=10.0,
            max_value=30.0,
            value=20.5,
            step=0.1,
            key="observation-planner-sqm",
        )
        return SkyQualityContext(
            source_id=source_id,
            evidence_kind=EvidenceKind.MEASURED,
            sqm_mag_arcsec2=float(sqm),
        )

    bortle = st.number_input(
        "Clase Bortle",
        min_value=1,
        max_value=9,
        value=5,
        step=1,
        key="observation-planner-bortle",
    )
    evidence = (
        EvidenceKind.MAP_DERIVED if mode == "Bortle de mapa" else EvidenceKind.INFERRED
    )
    return SkyQualityContext(
        source_id=source_id,
        evidence_kind=evidence,
        bortle_class=int(bortle),
    )


def _render_result(state: dict, observer: ObserverContext) -> None:
    plan = state["plan"]
    dashboard = state["dashboard"]
    best = plan.best_sample

    if best is None:
        st.warning(
            "No hay una muestra que cumpla simultáneamente los umbrales geométricos "
            "de esta ventana. Amplía el intervalo o revisa altitud/oscuridad."
        )
        return

    local_time = best.observed_at.astimezone(ZoneInfo(observer.timezone))
    st.success(f"Mejor ventana geométrica: {local_time:%d/%m/%Y · %H:%M}")
    kpi = st.columns(3)
    with kpi[0]:
        st.metric("Observabilidad", dashboard.score_text)
    with kpi[1]:
        st.metric("Grado", dashboard.grade)
    with kpi[2]:
        st.metric("Completitud", dashboard.completeness_text)

    st.caption(
        f"Altitud {best.target_position.altitude_apparent_deg:.1f}° · "
        f"azimut {best.target_position.azimuth_deg:.1f}° · "
        f"Sol {best.sun_altitude_deg:.1f}° · "
        f"Luna {best.moon_altitude_deg:.1f}° · "
        f"separación lunar {best.moon_target_separation_deg:.1f}°."
    )

    if dashboard.attention_required:
        st.warning("Atención: " + ", ".join(dashboard.attention_reasons))

    for metric in dashboard.metrics:
        with st.container(border=True):
            st.markdown(f"**{metric.label} · {metric.value_text}**")
            st.caption(f"{metric.state_text} · {metric.rationale}")
            if metric.source_ids:
                st.caption("Fuentes: " + ", ".join(metric.source_ids))

    with st.expander("Evidencia y trazabilidad"):
        for item in dashboard.evidence:
            valid = item.valid_at.isoformat() if item.valid_at else "no disponible"
            retrieved = (
                item.retrieved_at.isoformat() if item.retrieved_at else "no disponible"
            )
            st.write(
                f"{item.source_id} · {item.evidence_kind} · válido={valid} · "
                f"recuperado={retrieved} · stale={item.stale}"
            )
        st.caption(f"Etiqueta científica del resultado: {dashboard.scientific_label}")

    st.info(
        "La puntuación es INFERENCIA. No garantiza visibilidad ni calidad fotográfica. "
        "El horizonte real, nubes locales, contaminación lumínica no aportada y otros "
        "factores de campo pueden cambiar el resultado."
    )


def render_observation_planner(observer: ObserverContext) -> None:
    st.divider()
    st.subheader("Planificador de observación")
    st.caption(
        "Calcula una ventana local para un objetivo fijo J2000. Las coordenadas "
        "introducidas manualmente se tratan como NO VERIFICADO hasta asociarlas a "
        "un catálogo o fuente científica."
    )

    now_local = datetime.now(ZoneInfo(observer.timezone)).replace(second=0, microsecond=0)
    with st.form("centinela-observation-planner-form", clear_on_submit=False):
        target_name = st.text_input(
            "Objetivo",
            value="Objetivo J2000",
            key="observation-planner-target-name",
        )
        kind_label = st.selectbox(
            "Tipo de objetivo",
            options=tuple(_TARGET_KIND_LABELS),
            key="observation-planner-target-kind",
        )
        ra_hours = st.number_input(
            "Ascensión recta J2000 (horas)",
            min_value=0.0,
            max_value=23.999999,
            value=17.75,
            format="%.6f",
            key="observation-planner-ra",
        )
        dec_deg = st.number_input(
            "Declinación J2000 (grados)",
            min_value=-90.0,
            max_value=90.0,
            value=-29.0,
            format="%.6f",
            key="observation-planner-dec",
        )
        start_date = st.date_input(
            "Fecha local de inicio",
            value=now_local.date(),
            key="observation-planner-start-date",
        )
        start_time = st.time_input(
            "Hora local de inicio",
            value=now_local.time(),
            key="observation-planner-start-time",
        )
        duration_hours = st.slider(
            "Duración de búsqueda (h)",
            min_value=1,
            max_value=12,
            value=6,
            key="observation-planner-duration",
        )
        minimum_altitude = st.slider(
            "Altitud mínima del objetivo (°)",
            min_value=0,
            max_value=60,
            value=15,
            key="observation-planner-min-altitude",
        )
        maximum_sun_altitude = st.slider(
            "Altitud máxima del Sol (°)",
            min_value=-24,
            max_value=0,
            value=-12,
            key="observation-planner-max-sun",
        )
        use_forecasts = st.checkbox(
            "Consultar Open-Meteo + 7Timer al calcular",
            value=True,
            key="observation-planner-use-forecasts",
            help="Sólo realiza las dos peticiones al pulsar Calcular.",
        )
        sky_quality = _sky_quality_controls()
        submitted = st.form_submit_button(
            "Calcular ventana",
            type="primary",
            use_container_width=True,
        )

    if submitted:
        try:
            kind = _TARGET_KIND_LABELS[kind_label]
            target = FixedSkyTarget(
                target_id="product-user-fixed-target",
                name=target_name.strip() or "Objetivo J2000",
                kind=kind,
                right_ascension_hours_j2000=float(ra_hours),
                declination_deg_j2000=float(dec_deg),
                source_ids=["product-user-supplied-j2000"],
                scientific_status=ScientificStatus.NO_VERIFICADO,
            )
            start_local = _local_start(observer, start_date, start_time)
            start_utc = start_local.astimezone(UTC)
            plan = plan_landscape_window(
                LandscapeWindowRequest(
                    target=target,
                    observer=observer,
                    start_utc=start_utc,
                    end_utc=start_utc + timedelta(hours=int(duration_hours)),
                    step_minutes=15,
                    minimum_target_altitude_deg=float(minimum_altitude),
                    maximum_sun_altitude_deg=float(maximum_sun_altitude),
                )
            )
            best = plan.best_sample
            if best is None:
                st.session_state[PLANNER_STATE_KEY] = {"plan": plan, "dashboard": None}
            else:
                weather = None
                astronomy_conditions = None
                forecast_errors: list[str] = []
                if use_forecasts:
                    try:
                        weather = fetch_open_meteo_snapshot(
                            latitude_deg=observer.latitude_deg,
                            longitude_deg=observer.longitude_deg,
                            requested_at=best.observed_at,
                            retrieved_at=datetime.now(UTC),
                            timeout_seconds=10.0,
                        )
                    except Exception as exc:
                        forecast_errors.append(f"Open-Meteo: {exc}")
                    try:
                        conditions = fetch_7timer_astro_snapshots(
                            latitude=observer.latitude_deg,
                            longitude=observer.longitude_deg,
                            retrieved_at=datetime.now(UTC),
                            timeout_seconds=10.0,
                        )
                        astronomy_conditions = _nearest_conditions(
                            conditions,
                            best.observed_at,
                        )
                        if astronomy_conditions is None:
                            forecast_errors.append(
                                "7Timer: no hay una muestra a ±3,1 h de la mejor ventana"
                            )
                    except Exception as exc:
                        forecast_errors.append(f"7Timer: {exc}")

                request = ObservabilityRequest(
                    object_class=_OBJECT_CLASS_BY_KIND[kind],
                    target_altitude_deg=best.target_position.altitude_apparent_deg,
                    sun_altitude_deg=best.sun_altitude_deg,
                    moon_altitude_deg=best.moon_altitude_deg,
                    moon_target_separation_deg=best.moon_target_separation_deg,
                    moon_illumination_fraction=best.moon_illumination_fraction,
                    weather=weather,
                    astronomy_conditions=astronomy_conditions,
                    sky_quality=sky_quality,
                )
                result = evaluate_observability(request)
                dashboard = build_observation_dashboard(
                    title=target.name,
                    request=request,
                    result=result,
                    now=datetime.now(UTC),
                )
                st.session_state[PLANNER_STATE_KEY] = {
                    "plan": plan,
                    "dashboard": dashboard,
                    "forecast_errors": forecast_errors,
                }
        except Exception as exc:
            st.error("No se pudo calcular la ventana de observación.")
            with st.expander("Detalle técnico"):
                st.exception(exc)

    state = st.session_state.get(PLANNER_STATE_KEY)
    if not state:
        st.info("Configura el objetivo y pulsa **Calcular ventana**.")
        return
    if state.get("dashboard") is None:
        _render_result({"plan": state["plan"], "dashboard": None}, observer)
        return
    for error in state.get("forecast_errors", []):
        st.warning(error)
    _render_result(state, observer)
