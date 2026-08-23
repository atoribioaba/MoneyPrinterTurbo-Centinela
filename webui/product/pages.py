from __future__ import annotations

import logging
import tomllib
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import streamlit as st

from app.services.astronomy_core import get_astronomy_health
from app.services.centinela.control_center import (
    CENTINELA_EDITION_LABEL,
    CONTROL_CENTER_VERSION,
    CentinelaControlCenter,
)
from app.services.centinela.orchestration import JobStatus, ProjectState

LOGGER = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parents[2]


@st.cache_resource(show_spinner=False)
def get_control_center() -> CentinelaControlCenter:
    service = CentinelaControlCenter(register_default_writer_room=True)
    service.recover_runtime()
    return service


def _service() -> CentinelaControlCenter:
    try:
        return get_control_center()
    except Exception:
        LOGGER.exception("Control Center initialization failed")
        st.error(
            "El Control Center no ha podido iniciar. "
            "Consulta Avanzado · Ingeniería para el diagnóstico técnico."
        )
        st.stop()


def _core_version() -> str:
    try:
        with (ROOT / "pyproject.toml").open("rb") as handle:
            return str(tomllib.load(handle)["project"]["version"])
    except Exception:
        return "no verificado"


def _header(title: str, caption: str | None = None) -> None:
    st.title(title)
    if caption:
        st.caption(caption)


def _project_selector(service: CentinelaControlCenter, key: str):
    projects = service.projects()
    if not projects:
        st.info("Todavía no hay proyectos de producción.")
        return None

    mapping = {item.project_id: item for item in projects}
    preferred = st.session_state.get("centinela_project_id")
    index = 0
    if preferred in mapping:
        index = list(mapping).index(preferred)

    selected = st.selectbox(
        "Proyecto",
        options=list(mapping),
        index=index,
        format_func=lambda value: f"{mapping[value].title} · {mapping[value].state_label}",
        key=key,
    )
    st.session_state["centinela_project_id"] = selected
    return service.project(selected)


def _job_status_text(status: JobStatus) -> str:
    labels = {
        JobStatus.QUEUED: "En cola",
        JobStatus.RUNNING: "En ejecución",
        JobStatus.CANCEL_REQUESTED: "Cancelación solicitada",
        JobStatus.SUCCEEDED: "Completado",
        JobStatus.FAILED: "Fallido",
        JobStatus.CANCELLED: "Cancelado",
        JobStatus.INTERRUPTED: "Interrumpido",
    }
    return labels[status]


def _render_project_status(project) -> None:
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Estado", project.state_label)
    c2.metric("Artefactos", project.artifact_count)
    c3.metric("Siguiente etapa", project.next_stage.value if project.next_stage else "—")
    c4.metric("Publicación automática", "DESACTIVADA")

    if project.capability_pending:
        st.warning(project.next_action)
        st.caption(
            "La automatización se detiene de forma segura en esta capacidad. "
            "No necesitas abrir módulos internos ni fabricar resultados manualmente."
        )
    elif project.state == ProjectState.NEEDS_INPUT:
        st.warning(project.next_action)
    elif project.state == ProjectState.BLOCKED:
        st.error(project.next_action)
    elif project.state == ProjectState.READY_FOR_HUMAN_REVIEW:
        st.success(project.next_action)
    else:
        st.info(project.next_action)

    active = [
        item
        for item in project.latest_jobs
        if item.status in {JobStatus.QUEUED, JobStatus.RUNNING, JobStatus.CANCEL_REQUESTED}
    ]
    if active:
        st.subheader("Trabajo en curso")
        for job in active:
            st.write(f"**{_job_status_text(job.status)}** · {job.message or job.job_type}")
            st.progress(job.progress / 100.0, text=f"{job.progress}%")


def home_page() -> None:
    service = _service()
    _header(
        "Inicio",
        "Control Center de producción · El Centinela del Universo",
    )

    projects = service.projects()
    jobs = service.jobs.list_jobs()
    active_jobs = sum(
        item.status in {JobStatus.QUEUED, JobStatus.RUNNING, JobStatus.CANCEL_REQUESTED}
        for item in jobs
    )
    waiting_review = sum(
        item.state == ProjectState.READY_FOR_HUMAN_REVIEW
        for item in projects
    )

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Proyectos", len(projects))
    c2.metric("Trabajos activos", active_jobs)
    c3.metric("Pendientes de revisión", waiting_review)
    c4.metric("Auto publicación", "NO")

    st.subheader("Producción reciente")
    if not projects:
        st.write("Crea el primer vídeo desde **Crear vídeo**.")
        return

    for project in projects[:6]:
        with st.container(border=True):
            st.markdown(f"### {project.title}")
            st.write(f"**{project.state_label}** · {project.next_action}")
            st.caption(f"Actualizado: {project.updated_at}")


def create_video_page() -> None:
    service = _service()
    _header(
        "Crear vídeo",
        "Una entrada de producto; la maquinaria técnica se ejecuta por debajo.",
    )

    st.write(
        "Introduce el tema. El Control Center crea el proyecto y lanza la producción "
        "automática hasta la siguiente capacidad realmente disponible."
    )

    with st.form("create-video", clear_on_submit=False):
        title = st.text_input(
            "Tema o título",
            placeholder="Ej.: La Luna y Júpiter esta noche",
            max_chars=512,
        )
        use_observation_context = st.checkbox(
            "El tema depende de un lugar y/o momento de observación",
            value=False,
            help=(
                "Úsalo para visibilidad, conjunciones, eclipses o "
                "contenidos del cielo desde un lugar concreto."
            ),
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
            with st.container(border=True):
                st.caption(
                    "R6 no inventa ubicación ni fecha. Estos datos quedan "
                    "fijados en el Fact Lock astronómico."
                )
                c1, c2 = st.columns(2)
                latitude_text = c1.text_input(
                    "Latitud (grados)",
                    placeholder="Ej.: 41.65",
                )
                longitude_text = c2.text_input(
                    "Longitud (grados)",
                    placeholder="Ej.: -4.72",
                )
                c3, c4 = st.columns(2)
                elevation_text = c3.text_input(
                    "Elevación (m)",
                    value="0",
                )
                timezone_name = c4.text_input(
                    "Zona horaria IANA",
                    value="Europe/Madrid",
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

        submitted = st.form_submit_button(
            "Generar borrador",
            type="primary",
            use_container_width=True,
        )

    if not submitted:
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
            "No se pudo crear el proyecto. El detalle técnico queda reservado para Ingeniería."
        )
        return


    st.session_state["centinela_project_id"] = project.project_id
    st.success(f"Proyecto creado: {project.title}")
    if started is not None:
        st.write("Producción automática iniciada.")
        st.progress(0.0, text="Preparando pipeline…")
    st.caption(
        "No se publicará nada automáticamente. La revisión y aprobación humana siguen siendo obligatorias."
    )


def projects_page() -> None:
    service = _service()
    _header("Proyectos", "Estado, siguiente acción, jobs y artefactos del proyecto.")
    project = _project_selector(service, "projects-selector")
    if project is None:
        return

    _render_project_status(project)

    st.subheader("Artefactos")
    if not project.artifact_type_counts:
        st.write("Todavía no hay artefactos materializados.")
    else:
        rows = [
            {"Tipo": key, "Cantidad": value}
            for key, value in project.artifact_type_counts.items()
        ]
        st.dataframe(rows, use_container_width=True, hide_index=True)

    st.subheader("Historial reciente de trabajos")
    if not project.latest_jobs:
        st.write("No hay trabajos registrados todavía.")
    else:
        rows = [
            {
                "Estado": _job_status_text(job.status),
                "Progreso": f"{job.progress}%",
                "Trabajo": job.message or job.job_type,
                "Recurso": job.resource_class.value,
                "Actualizado": job.updated_at,
            }
            for job in reversed(project.latest_jobs)
        ]
        st.dataframe(rows, use_container_width=True, hide_index=True)


def review_page() -> None:
    service = _service()
    _header(
        "Revisión",
        "La aprobación humana es una frontera deliberada del pipeline.",
    )
    project = _project_selector(service, "review-selector")
    if project is None:
        return

    if project.state != ProjectState.READY_FOR_HUMAN_REVIEW:
        st.info(
            f"Este proyecto está en **{project.state_label}**. "
            "La revisión se habilitará cuando exista un vídeo preparado para revisión humana."
        )
        return

    st.warning("Revisa el vídeo y sus evidencias antes de aprobar.")
    reviewer = st.text_input("Revisor", value="Revisión humana")
    notes = st.text_area("Notas de revisión", placeholder="Motivo de aprobación o cambios requeridos")
    c1, c2 = st.columns(2)

    if c1.button("Aprobar", type="primary", use_container_width=True):
        try:
            service.review(
                project.project_id,
                approved=True,
                reviewer=reviewer,
                notes=notes,
            )
            st.success("Proyecto aprobado explícitamente.")
        except Exception as exc:
            st.error(str(exc))

    if c2.button("Solicitar cambios", use_container_width=True):
        try:
            service.review(
                project.project_id,
                approved=False,
                reviewer=reviewer,
                notes=notes,
            )
            st.warning("El proyecto vuelve a necesitar intervención antes de continuar.")
        except Exception as exc:
            st.error(str(exc))


def observatory_page() -> None:
    _header("Observatorio", "Capacidad astronómica local y determinista.")
    health = get_astronomy_health()
    c1, c2, c3 = st.columns(3)
    c1.metric("Motor", health.engine)
    c2.metric("Versión", health.engine_version)
    c3.metric("Runtime", "LOCAL / CPU")
    st.write(
        "El núcleo de efemérides está disponible sin red. La capa de producto para "
        "planificación observacional se ampliará sin duplicar este motor."
    )
    st.caption(
        "Los datos destinados a publicación sobre actualidad, misiones, eclipses o descubrimientos "
        "seguirán requiriendo corroboración con fuentes primarias actuales."
    )


def ephemerides_page() -> None:
    _header("Efemérides", "Vista de producto en construcción sobre Astronomy Engine.")
    health = get_astronomy_health()
    st.success(f"Motor disponible: {health.engine} {health.engine_version}")
    st.write(
        "R5 no crea un segundo calculador. Esta sección queda preparada para consumir el núcleo "
        "astronómico existente con contexto de observación del proyecto."
    )


def library_page() -> None:
    service = _service()
    _header(
        "Biblioteca",
        "AstroMedia en modo de producto: inventario y automatización, sin botones técnicos.",
    )
    library = service.library()
    c1, c2, c3 = st.columns(3)
    c1.metric("Items activos", library.active_items)
    c2.metric("Publicables", library.publication_eligible_items)
    c3.metric("Actualización", "PENDIENTE" if library.refresh.refresh_catalog else "AL DÍA")

    if library.refresh.refresh_catalog:
        st.info(
            "Se han detectado cambios en la biblioteca. R4 la actualizará automáticamente "
            "cuando una producción llegue a la etapa MEDIA."
        )
    else:
        st.success("El preflight de biblioteca no detecta cambios que requieran reindexado.")

    st.caption(
        f"Archivos soportados detectados: {library.refresh.supported_file_count} · "
        f"Motivo: {library.refresh.reason}"
    )
    st.write(
        "El flujo normal no requiere **Indexar**, **Buscar**, ejecutar SemanticMatcher ni lanzar "
        "SmartFocal manualmente. Esas operaciones son responsabilidad del pipeline."
    )


def sources_page() -> None:
    service = _service()
    _header("Fuentes", "Proveedores y estado de derechos del catálogo activo.")
    library = service.library()

    st.subheader("Proveedores")
    if library.provider_counts:
        st.dataframe(
            [{"Proveedor": key, "Items": value} for key, value in library.provider_counts.items()],
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.write("No hay proveedores activos en el catálogo.")

    st.subheader("Derechos")
    if library.rights_counts:
        st.dataframe(
            [{"Estado": key, "Items": value} for key, value in library.rights_counts.items()],
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.write("No hay material activo para clasificar.")


def publication_page() -> None:
    service = _service()
    _header("Publicación", "Salida controlada; nunca autopublicación.")
    projects = service.projects()
    ready = [item for item in projects if item.state == ProjectState.PUBLICATION_PACKAGE_READY]
    approved = [item for item in projects if item.state == ProjectState.FINAL_APPROVED]

    c1, c2 = st.columns(2)
    c1.metric("Paquetes listos", len(ready))
    c2.metric("Aprobados pendientes de paquete", len(approved))
    st.info(
        "R8 materializará el Publication Package completo. Incluso entonces, publicar seguirá "
        "requiriendo una acción humana explícita."
    )


def analytics_page() -> None:
    _header("Analítica", "Capa de producto reservada para datos reales posteriores.")
    st.info(
        "Los contratos de analítica existentes se preservan. R5 no los presenta como aprendizaje "
        "operativo hasta disponer de datos reales importados y suficientemente trazables."
    )


def system_status_page() -> None:
    service = _service()
    _header("Estado", "Salud del Control Center y capacidades conectadas al Production Spine.")

    integrity = service.storage_integrity()
    c1, c2, c3 = st.columns(3)
    c1.metric("Project Store", "OK" if integrity == "ok" else integrity.upper())
    c2.metric("Architecture freeze", "NO")
    c3.metric("Auto publicación", "NO")

    rows = [
        {
            "Etapa": item.label,
            "Conectado": "Sí" if item.connected else "No",
            "Recurso": item.resource_class.value,
            "Backend": item.backend_status,
        }
        for item in service.capabilities()
    ]
    st.dataframe(rows, use_container_width=True, hide_index=True)


def settings_page() -> None:
    _header("Configuración", "Resumen seguro; las credenciales no se muestran en esta interfaz.")
    rows = [
        {"Componente": "Centinela Edition", "Valor": CENTINELA_EDITION_LABEL},
        {"Componente": "Control Center", "Valor": CONTROL_CENTER_VERSION},
        {"Componente": "MoneyPrinterTurbo Core", "Valor": _core_version()},
        {"Componente": "Publicación automática", "Valor": "Desactivada"},
        {"Componente": "Architecture freeze", "Valor": "No autorizado"},
    ]
    st.dataframe(rows, use_container_width=True, hide_index=True)
    st.caption("Las API keys, tokens y secretos no se vuelcan ni se renderizan aquí.")


def engineering_page() -> None:
    _header(
        "Ingeniería",
        "Herramientas históricas y diagnósticas F3–F58 preservadas fuera del flujo normal.",
    )
    st.warning(
        "Estas pantallas pueden exponer controles internos como indexado, pruebas de motores o "
        "artefactos técnicos. No forman parte del flujo normal de crear un vídeo."
    )
    st.write(
        "Utiliza las entradas adicionales de este grupo sólo para diagnóstico, validación o A/B técnico."
    )
