from __future__ import annotations

import logging
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import streamlit as st

from app.services.centinela.orchestration import JobStatus, ProjectState

from . import mobile_pages, pages, ui, visual_generation


LOGGER = logging.getLogger(__name__)
_NAVIGATION: dict[str, Any] = {}


def configure_product_navigation(**pages_by_name: Any) -> None:
    _NAVIGATION.update(pages_by_name)


def _nav_page(name: str) -> Any | None:
    return _NAVIGATION.get(name)


def _recent_projects(service):
    return list(service.projects())


def _agenda_preview() -> tuple[Any, ...]:
    state = st.session_state.get(pages.AGENDA_SESSION_KEY)
    if not isinstance(state, dict):
        return ()
    return tuple(state.get("events") or ())


def _event_time_label(event: Any) -> str:
    try:
        official = event.canonical_quantity.provenance.get("official_madrid_time") or {}
        iso = str(official.get("iso8601") or "")
        if iso:
            return iso.replace("T", " ")[:16]
    except Exception:
        pass
    return "Hora pendiente de consulta"


def _artifact_count(project: Any, *tokens: str) -> int:
    total = 0
    for artifact_type, count in project.artifact_type_counts.items():
        lower = artifact_type.lower()
        if any(token in lower for token in tokens):
            total += int(count)
    return total


def _render_project_content(project: Any) -> None:
    ui.render_section_heading(
        "Contenido",
        "Entregables materializados del proyecto. Solo se muestran estados derivados de datos reales.",
        eyebrow="PRODUCCIÓN",
    )
    rows = (
        ("Vídeo", _artifact_count(project, "video", "render")),
        ("Audio narración", _artifact_count(project, "audio", "voice", "tts")),
        ("Subtítulos", _artifact_count(project, "subtitle", "srt")),
        ("Miniatura", _artifact_count(project, "thumbnail")),
    )
    any_materialized = any(count > 0 for _, count in rows)
    if not any_materialized:
        ui.render_empty_state(
            "El contenido final aún no está materializado",
            "Los entregables aparecerán aquí a medida que avance el pipeline.",
        )
        return
    with st.container(
        key="centinela-project-content-grid",
        horizontal=True,
        horizontal_alignment="left",
        gap="medium",
    ):
        for label, count in rows:
            if count <= 0:
                continue
            with st.container(border=True):
                st.caption(label.upper())
                st.markdown(f"### {count}")
                st.caption("artefacto" if count == 1 else "artefactos")


def _render_next_action(project: Any) -> None:
    review_page = _nav_page("review")
    publication_page = _nav_page("publication")
    if project.state == ProjectState.READY_FOR_HUMAN_REVIEW and review_page is not None:
        st.page_link(
            review_page,
            label="Continuar revisión",
            icon=":material/fact_check:",
            width="stretch",
        )
    elif project.state == ProjectState.FINAL_APPROVED and publication_page is not None:
        st.page_link(
            publication_page,
            label="Preparar publicación manual",
            icon=":material/inventory_2:",
            width="stretch",
        )
    else:
        st.caption(project.next_action)


def home_page() -> None:
    service = pages._service()
    projects = _recent_projects(service)
    events = _agenda_preview()

    ui.render_brand_manifesto()
    ui.render_brand_hero(
        "Bienvenido al observatorio.",
        "Todo listo para crear historias del Universo.",
        eyebrow="INICIO · TU CENTRO DE MANDO",
        action_hint="CIENCIA RIGUROSA · PRODUCCIÓN AUDIOVISUAL · PUBLICACIÓN MANUAL",
    )

    with st.container(
        key="centinela-hero-actions",
        horizontal=True,
        horizontal_alignment="left",
        vertical_alignment="center",
        gap="small",
    ):
        st.page_link(
            CREATE_PAGE,
            label="＋ Crear una historia",
            icon=":material/add_circle:",
            width="stretch",
        )
        sky_page = _nav_page("sky")
        if sky_page is not None:
            st.page_link(
                sky_page,
                label="Explorar el cielo",
                icon=":material/dark_mode:",
                width="stretch",
            )

    ui.render_section_heading(
        "Centro de mando",
        "Lo importante ahora, sin exponer complejidad técnica innecesaria.",
    )
    with st.container(
        key="centinela-home-grid",
        horizontal=True,
        horizontal_alignment="left",
        vertical_alignment="top",
        gap="medium",
    ):
        with st.container(border=True):
            st.caption("PRODUCCIÓN EN CURSO")
            if not projects:
                ui.render_empty_state(
                    "Sin producción activa",
                    "Crea una historia astronómica para iniciar el primer proyecto.",
                )
            else:
                current = projects[0]
                st.markdown(f"### {current.title}")
                ui.render_state_badge(current.state)
                ui.render_project_timeline(current)
                _render_next_action(current)

        with st.container(border=True):
            st.caption("PRÓXIMO EVENTO")
            if not events:
                ui.render_empty_state(
                    "Agenda aún no calculada",
                    "Calcula la Agenda futura para mostrar aquí una efeméride real.",
                )
                sky_page = _nav_page("sky")
                if sky_page is not None:
                    st.page_link(
                        sky_page,
                        label="Ver agenda",
                        icon=":material/calendar_month:",
                        width="stretch",
                    )
            else:
                event = events[0]
                st.markdown(f"### {getattr(event, 'label_es', 'Evento astronómico')}")
                st.caption(_event_time_label(event))
                body = str(getattr(event, "body", "") or "").strip()
                if body:
                    st.write(body)
                sky_page = _nav_page("sky")
                if sky_page is not None:
                    st.page_link(
                        sky_page,
                        label="Ver en agenda",
                        icon=":material/calendar_month:",
                        width="stretch",
                    )

        with st.container(border=True):
            st.caption("PRODUCCIONES RECIENTES")
            recent = projects[1:4]
            if not recent:
                ui.render_empty_state(
                    "Sin historial reciente",
                    "Las últimas producciones aparecerán aquí cuando existan.",
                )
            else:
                for project in recent:
                    st.markdown(f"**{project.title}**")
                    st.caption(f"{ui.state_display(project.state)} · {project.updated_at}")
            st.page_link(
                PROJECTS_PAGE,
                label="Ver todos los proyectos",
                icon=":material/movie:",
                width="stretch",
            )


def create_video_page() -> None:
    service = pages._service()

    ui.render_brand_hero(
        "¿Qué quieres contar?",
        "Elige cómo quieres empezar. El Fact Lock protege los datos científicos antes de producir.",
        eyebrow="CREAR",
        action_hint="REEL / TIKTOK / SHORT · 9:16 · 30 FPS",
    )

    start_mode = st.radio(
        "¿Cómo quieres empezar?",
        options=("Agenda futura", "Idea propia", "Proyecto existente"),
        index=1,
        horizontal=True,
        key="create-start-mode",
    )

    if start_mode == "Agenda futura":
        ui.render_empty_state(
            "Empieza desde una efeméride real",
            "Abre Cielo, calcula la Agenda futura para tu ubicación y selecciona el fenómeno que quieras convertir en historia.",
        )
        sky_page = _nav_page("sky")
        if sky_page is not None:
            st.page_link(
                sky_page,
                label="Abrir Agenda futura",
                icon=":material/calendar_month:",
                width="stretch",
            )
        return

    if start_mode == "Proyecto existente":
        ui.render_empty_state(
            "Continúa una producción",
            "Abre Proyectos para retomar la siguiente acción pendiente de una historia existente.",
        )
        st.page_link(
            PROJECTS_PAGE,
            label="Abrir Proyectos",
            icon=":material/movie:",
            width="stretch",
        )
        return

    ui.render_format_chips(("Reel / TikTok / Short", "9:16", "30 fps"))

    with st.form("create-video-v2", clear_on_submit=False):
        title = st.text_area(
            "Idea o tema",
            placeholder=(
                "Ej.: La Luna llena saliendo detrás del horizonte de Valladolid esta noche."
            ),
            max_chars=512,
            height=132,
        )

        with st.expander("Opciones avanzadas", expanded=False):
            st.caption(
                "Añade contexto de observación solo cuando la historia dependa de lugar, hora o visibilidad."
            )
            use_observation_context = st.checkbox(
                "Esta historia depende de lugar y/o momento",
                value=False,
                key="studio-use-observation-context",
            )

            latitude_text = ""
            longitude_text = ""
            elevation_text = "0"
            timezone_name = "Europe/Madrid"
            observation_date = datetime.now().date()
            observation_time = datetime.now().time().replace(
                second=0,
                microsecond=0,
            )

            if use_observation_context:
                latitude_text = st.text_input(
                    "Latitud",
                    placeholder="41.65",
                    help="Grados, entre -90 y 90.",
                )
                longitude_text = st.text_input(
                    "Longitud",
                    placeholder="-4.72",
                    help="Grados, entre -180 y 180.",
                )
                elevation_text = st.text_input("Elevación (m)", value="0")
                timezone_name = st.text_input(
                    "Zona horaria",
                    value="Europe/Madrid",
                    help="Identificador IANA completo, por ejemplo Europe/Madrid.",
                )
                observation_date = st.date_input(
                    "Fecha local",
                    value=observation_date,
                )
                observation_time = st.time_input(
                    "Hora local",
                    value=observation_time,
                )

        submitted = st.form_submit_button(
            "✦ Generar investigación y guion",
            type="primary",
            use_container_width=True,
        )

    if not submitted:
        st.caption(
            "Nada se publica automáticamente. Fact Lock y la revisión humana siguen siendo obligatorios."
        )
        return

    observation_context = {}
    if use_observation_context:
        try:
            latitude = float(latitude_text.strip())
            longitude = float(longitude_text.strip())
            elevation = float(elevation_text.strip())
            if not -90.0 <= latitude <= 90.0:
                raise ValueError("La latitud debe estar entre -90 y 90.")
            if not -180.0 <= longitude <= 180.0:
                raise ValueError("La longitud debe estar entre -180 y 180.")
            timezone_info = ZoneInfo(timezone_name.strip())
            moment = datetime.combine(
                observation_date,
                observation_time,
                tzinfo=timezone_info,
            )
        except (ValueError, ZoneInfoNotFoundError) as exc:
            ui.render_error_state(
                "El contexto de observación no es válido.",
                action="Revisa coordenadas, elevación y zona horaria.",
                technical_detail=exc,
            )
            return

        observation_context = {
            "astronomy": {
                "observer": {
                    "latitude_deg": latitude,
                    "longitude_deg": longitude,
                    "elevation_m": elevation,
                    "timezone": timezone_name.strip(),
                },
                "moment": moment.isoformat(),
                "include_eclipses": True,
            }
        }

    try:
        with st.spinner("Creando proyecto e iniciando investigación…", show_time=True):
            project, started = service.create_project(
                title,
                observation_context=observation_context,
                auto_start=True,
            )
    except ValueError as exc:
        ui.render_error_state(str(exc))
        return
    except Exception as exc:
        LOGGER.exception("Create project failed")
        ui.render_error_state(
            "No se pudo crear el proyecto.",
            action="Puedes reintentarlo. El diagnóstico queda disponible en Ingeniería.",
            technical_detail=exc,
        )
        return

    st.session_state["centinela_project_id"] = project.project_id
    st.success(f"Proyecto creado: {project.title}")
    if started is not None:
        st.progress(0.0, text="Preparando investigación y producción…")
    st.page_link(PROJECTS_PAGE, label="Abrir proyecto", width="stretch")
    st.caption(
        "La publicación automática permanece desactivada y la revisión humana es obligatoria."
    )


def projects_page() -> None:
    service = pages._service()

    ui.render_brand_hero(
        "Tus historias del Universo",
        "Consulta el estado real de cada producción, sus entregables y sus visuales por escena.",
        eyebrow="PROYECTOS",
    )

    project = pages._project_selector(service, "studio-projects-selector")
    if project is None:
        ui.render_empty_state(
            "Todavía no hay proyectos",
            "Crea una historia para comenzar el primer recorrido de producción.",
            action="Ve a Crear para iniciar una historia.",
        )
        st.page_link(CREATE_PAGE, label="✦ Crear una historia", width="stretch")
        return

    with st.container(border=True):
        st.html('<div class="centinela-project-orb" aria-hidden="true"></div>')
        st.markdown(f"## {project.title}")
        ui.render_state_badge(project.state)
        st.caption(f"Actualizado: {project.updated_at}")
        ui.render_project_timeline(project)

        st.markdown("### Etapa actual")
        st.write(project.next_action)

        if project.capability_pending:
            st.warning(
                "La producción está detenida de forma segura hasta que esta capacidad esté disponible."
            )
        _render_next_action(project)

    _render_project_content(project)

    with st.container(
        key="centinela-project-kpis",
        horizontal=True,
        horizontal_alignment="left",
        gap="medium",
    ):
        active_jobs = [
            job
            for job in project.latest_jobs
            if job.status
            in {
                JobStatus.QUEUED,
                JobStatus.RUNNING,
                JobStatus.CANCEL_REQUESTED,
            }
        ]
        ui.render_kpi_card(
            "Archivos y evidencias",
            project.artifact_count,
            detail="Materializados para este proyecto.",
        )
        ui.render_kpi_card(
            "Procesos activos",
            len(active_jobs),
            detail="Trabajos en cola o ejecución.",
        )

    visual_generation.render_visual_generation_workspace(service, project)

    with st.expander("Detalles técnicos y trazabilidad"):
        st.markdown("#### Artefactos")
        if project.artifact_type_counts:
            for key, value in project.artifact_type_counts.items():
                ui.render_key_value_card(key, value)
        else:
            st.caption("Todavía no hay artefactos materializados.")

        st.markdown("#### Historial de procesos")
        if project.latest_jobs:
            for job in reversed(project.latest_jobs):
                with st.container(border=True):
                    st.markdown(f"**{pages._job_status_text(job.status)}**")
                    st.write(job.message or job.job_type)
                    st.caption(f"{job.progress}% · {job.updated_at}")
        else:
            st.caption("No hay procesos registrados todavía.")


HOME_PAGE = st.Page(
    home_page,
    title="Inicio",
    default=True,
)
CREATE_PAGE = st.Page(
    create_video_page,
    title="Crear",
    url_path="crear",
)
SKY_PAGE = st.Page(
    mobile_pages.ephemerides_page,
    title="Agenda y efemérides",
    url_path="cielo",
)
PROJECTS_PAGE = st.Page(
    projects_page,
    title="Proyectos",
    url_path="proyectos",
)
