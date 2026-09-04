from __future__ import annotations

import logging
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import streamlit as st

from app.services.centinela.orchestration import JobStatus, ProjectState

from . import pages, ui


LOGGER = logging.getLogger(__name__)


def _recent_projects(service):
    return list(service.projects())


def home_page() -> None:
    service = pages._service()
    projects = _recent_projects(service)

    ui.render_brand_hero(
        "Observa. Comprende. Cuenta el cielo.",
        "Tu centro de control para transformar fenómenos reales del Universo en historias "
        "visuales con rigor científico, producción audiovisual y revisión humana.",
        action_hint="CIENCIA · PRODUCCIÓN AUDIOVISUAL · PUBLICACIÓN MANUAL",
    )

    st.page_link(CREATE_PAGE, label="✦ Crear una historia", width="stretch")

    ui.render_section_heading(
        "Tu siguiente acción",
        "El Centinela prioriza la decisión que necesita de ti ahora.",
        eyebrow="CENTRO DE CONTROL",
    )
    if not projects:
        ui.render_empty_state(
            "El observatorio está preparado",
            "Crea tu primera historia astronómica para iniciar investigación, guion y producción.",
            action="Empieza desde Crear.",
        )
        return

    current = projects[0]
    with st.container(border=True):
        st.markdown(f"## {current.title}")
        ui.render_state_badge(current.state)
        st.markdown("### Siguiente paso")
        st.write(current.next_action)
        ui.render_project_timeline(current)

        if current.capability_pending:
            st.warning(
                "La producción está detenida de forma segura hasta que la capacidad pendiente "
                "esté disponible."
            )
        elif current.state == ProjectState.READY_FOR_HUMAN_REVIEW:
            st.info("Este proyecto necesita tu revisión humana. Abre **Más → Revisión**.")
        elif current.state == ProjectState.FINAL_APPROVED:
            st.info(
                "El proyecto está aprobado. Abre **Más → Publicación** para preparar el paquete."
            )

        st.page_link(PROJECTS_PAGE, label="Abrir proyecto", width="stretch")

    if len(projects) > 1:
        ui.render_section_heading("Historias recientes", "Tus últimas producciones.")
        for project in projects[1:4]:
            with st.container(border=True):
                st.markdown(f"### {project.title}")
                ui.render_state_badge(project.state)
                st.caption(project.next_action)


def create_video_page() -> None:
    service = pages._service()

    ui.render_brand_hero(
        "¿Qué quieres contar?",
        "Describe el fenómeno, objeto o historia astronómica. El Centinela investigará y hará "
        "avanzar la producción hasta la siguiente decisión que necesite de ti.",
        eyebrow="CREAR",
        action_hint="EL FACT LOCK PROTEGE LOS DATOS CIENTÍFICOS ANTES DE PRODUCIR",
    )

    with st.form("create-video-v2", clear_on_submit=False):
        title = st.text_area(
            "Idea o tema",
            placeholder=(
                "Ej.: La Luna llena saliendo detrás del horizonte de Valladolid esta noche."
            ),
            max_chars=512,
            height=118,
        )

        st.caption("Formato: vídeo social vertical · 9:16 · revisión humana obligatoria.")

        with st.expander("Contexto de observación · opcional", expanded=False):
            st.caption(
                "Úsalo cuando la historia dependa de visibilidad, conjunciones, eclipses o "
                "paisaje celeste desde un lugar y momento concretos."
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
            "✦ Investigar y crear guion",
            type="primary",
            use_container_width=True,
        )

    if not submitted:
        st.caption(
            "Nada se publica automáticamente. Fact Lock y la revisión humana siguen siendo "
            "obligatorios."
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
        "Consulta el estado real de cada producción y continúa desde la siguiente decisión útil.",
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
        st.markdown(f"## {project.title}")
        ui.render_state_badge(project.state)
        st.caption(f"Actualizado: {project.updated_at}")

        st.markdown("### Siguiente acción")
        st.write(project.next_action)
        ui.render_project_timeline(project)

        if project.capability_pending:
            st.warning(
                "La producción está detenida de forma segura hasta que esta capacidad "
                "esté disponible."
            )
        elif project.state == ProjectState.READY_FOR_HUMAN_REVIEW:
            st.info("Siguiente decisión: **Más → Revisión**.")
        elif project.state == ProjectState.FINAL_APPROVED:
            st.info("Siguiente decisión: **Más → Publicación**.")

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

    with st.expander("Detalles avanzados y trazabilidad"):
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
PROJECTS_PAGE = st.Page(
    projects_page,
    title="Proyectos",
    url_path="proyectos",
)
