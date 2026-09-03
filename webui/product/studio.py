from __future__ import annotations

import logging
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import streamlit as st

from app.services.centinela.orchestration import JobStatus

from . import pages, ui


LOGGER = logging.getLogger(__name__)


def _recent_projects(service):
    return list(service.projects())


def home_page() -> None:
    service = pages._service()
    projects = _recent_projects(service)

    ui.render_brand_hero(
        "Observa. Comprende. Cuenta el cielo.",
        "Un estudio de producción astronómica para convertir fenómenos reales del Universo "
        "en historias visuales con rigor científico y revisión humana.",
        action_hint="PRODUCCIÓN AUDIOVISUAL · ASTRONOMÍA · PUBLICACIÓN MANUAL",
    )

    primary, secondary = st.columns([1.35, 1])
    with primary:
        st.page_link(CREATE_PAGE, label="✦ Crear una historia", width="stretch")
    with secondary:
        st.page_link(PROJECTS_PAGE, label="▣ Ver proyectos", width="stretch")

    ui.render_section_heading(
        "Producción en curso",
        "Continúa exactamente donde se detuvo el pipeline.",
        eyebrow="ESTUDIO",
    )
    if not projects:
        ui.render_empty_state(
            "El observatorio está preparado",
            "Crea tu primera historia astronómica para iniciar investigación, guion y producción.",
        )
        return

    current = projects[0]
    with st.container(border=True):
        title_col, state_col = st.columns([3, 1])
        with title_col:
            st.markdown(f"### {current.title}")
        with state_col:
            ui.render_state_badge(current.state)

        ui.render_project_timeline(current)
        st.markdown(f"**Siguiente paso:** {current.next_action}")
        st.page_link(PROJECTS_PAGE, label="Continuar proyecto", width="stretch")

    if len(projects) > 1:
        ui.render_section_heading("Producciones recientes")
        for project in projects[1:5]:
            with st.container(border=True):
                left, right = st.columns([4, 1])
                with left:
                    st.markdown(f"**{project.title}**")
                    st.caption(project.next_action)
                with right:
                    ui.render_state_badge(project.state)


def create_video_page() -> None:
    service = pages._service()

    ui.render_brand_hero(
        "¿Qué quieres contar?",
        "Describe el fenómeno, objeto o historia astronómica. El Centinela hará avanzar "
        "la producción hasta la siguiente decisión que necesite de ti.",
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

        with st.expander("Contexto de observación"):
            st.caption(
                "Añádelo solo si la historia depende de un lugar o momento concreto: "
                "visibilidad, conjunciones, eclipses o paisaje celeste."
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
                c1, c2 = st.columns(2)
                latitude_text = c1.text_input(
                    "Latitud",
                    placeholder="41.65",
                    help="Grados, entre -90 y 90.",
                )
                longitude_text = c2.text_input(
                    "Longitud",
                    placeholder="-4.72",
                    help="Grados, entre -180 y 180.",
                )
                c3, c4 = st.columns(2)
                elevation_text = c3.text_input("Elevación (m)", value="0")
                timezone_name = c4.text_input(
                    "Zona horaria",
                    value="Europe/Madrid",
                    help="Identificador IANA.",
                )
                c5, c6 = st.columns(2)
                observation_date = c5.date_input(
                    "Fecha local",
                    value=observation_date,
                )
                observation_time = c6.time_input(
                    "Hora local",
                    value=observation_time,
                )

        st.caption(
            "Formato de producto: vídeo social vertical. Los parámetros técnicos avanzados "
            "permanecen bajo control del pipeline."
        )
        submitted = st.form_submit_button(
            "✦ Generar investigación y guion",
            type="primary",
            use_container_width=True,
        )

    if not submitted:
        st.caption(
            "Nada se publica automáticamente. La revisión y aprobación humana siguen "
            "siendo obligatorias."
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
            st.error(f"Contexto de observación inválido: {exc}")
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
        project, started = service.create_project(
            title,
            observation_context=observation_context,
            auto_start=True,
        )
    except ValueError as exc:
        st.error(str(exc))
        return
    except Exception:
        LOGGER.exception("Create project failed")
        st.error(
            "No se pudo crear el proyecto. El diagnóstico técnico está disponible en Ingeniería."
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
        )
        st.page_link(CREATE_PAGE, label="✦ Crear una historia", width="stretch")
        return

    with st.container(border=True):
        top_left, top_right = st.columns([3, 1])
        with top_left:
            st.markdown(f"## {project.title}")
            st.caption(f"Actualizado: {project.updated_at}")
        with top_right:
            ui.render_state_badge(project.state)

        ui.render_project_timeline(project)
        st.markdown("### Siguiente paso")
        st.write(project.next_action)

        if project.capability_pending:
            st.warning(
                "La producción está detenida de forma segura hasta que esta capacidad "
                "esté disponible."
            )

    c1, c2 = st.columns(2)
    c1.metric("Archivos y evidencias", project.artifact_count)
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
    c2.metric("Procesos activos", len(active_jobs))

    with st.expander("Detalles técnicos"):
        st.markdown("#### Artefactos")
        if project.artifact_type_counts:
            st.dataframe(
                [
                    {"Tipo": key, "Cantidad": value}
                    for key, value in project.artifact_type_counts.items()
                ],
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.caption("Todavía no hay artefactos materializados.")

        st.markdown("#### Historial de procesos")
        if project.latest_jobs:
            st.dataframe(
                [
                    {
                        "Estado": pages._job_status_text(job.status),
                        "Progreso": f"{job.progress}%",
                        "Proceso": job.message or job.job_type,
                        "Actualizado": job.updated_at,
                    }
                    for job in reversed(project.latest_jobs)
                ],
                use_container_width=True,
                hide_index=True,
            )
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
