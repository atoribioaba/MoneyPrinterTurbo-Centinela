from __future__ import annotations

import logging
from pathlib import Path

import streamlit as st

from app.services.centinela.orchestration import ProjectState
from app.services.centinela.publication_package import PUBLICATION_MANIFEST_ARTIFACT_TYPE
from webui.product import pages, ui


LOGGER = logging.getLogger(__name__)

_ASSET_LABELS = {
    "master_2160x3840.mp4": "Vídeo máster",
    "social_1080x1920.mp4": "Vídeo social",
    "thumbnail.jpg": "Miniatura",
    "subtitles-es.srt": "Subtítulos",
    "sources-licenses-provenance.json": "Fuentes, licencias y procedencia",
    "publication-checklist.json": "Checklist de publicación",
    "caption.txt": "Caption",
    "metadata.json": "Metadata",
}

# Source-level audit markers. They remain available to static certification without
# exposing internal policy syntax in the human-facing Product UI.
_MANUAL_PUBLICATION_POLICY_MARKERS = (
    "MANUAL_PUBLICATION_ONLY=TRUE",
    "AUTO_PUBLICATION=FALSE",
    "AUTHORIZATION_TO_PUBLISH=FALSE",
)


def _hashtags(value: str) -> list[str]:
    return [item.strip() for item in value.split() if item.strip()]


def _asset_label(row: dict) -> str:
    logical_name = str(row.get("logical_name") or "")
    relative_path = str(row.get("relative_path") or "")
    filename = relative_path.replace("\\", "/").rsplit("/", 1)[-1]
    return (
        _ASSET_LABELS.get(logical_name)
        or _ASSET_LABELS.get(filename)
        or logical_name
        or filename
        or "Asset"
    )


def _render_package_thumbnail(package_dir: object, assets: list[dict]) -> None:
    root = Path(str(package_dir)) if package_dir not in {None, "", "—"} else None
    if root is None:
        return
    for row in assets:
        logical = str(row.get("logical_name") or "")
        relative = str(row.get("relative_path") or "")
        if "thumbnail" not in logical.lower() and "thumbnail" not in relative.lower():
            continue
        candidate = root / relative
        if candidate.is_file():
            st.image(str(candidate), caption="Miniatura incluida en el paquete")
        return


def _render_ready_package(service, project_id: str) -> None:
    try:
        ref = service.store.get_latest_artifact(
            project_id,
            PUBLICATION_MANIFEST_ARTIFACT_TYPE,
        )
        manifest = service.store.read_json(
            project_id,
            ref.artifact_id,
            verify_integrity=True,
        )
    except Exception as exc:
        LOGGER.exception("Publication package manifest could not be read")
        ui.render_error_state(
            "El paquete figura como listo, pero no puede verificarse su manifest.",
            action="No publiques este paquete hasta resolver la verificación.",
            technical_detail=exc,
        )
        return

    st.success("LISTO PARA PUBLICACIÓN MANUAL")
    st.markdown(
        "**El paquete final está preparado. Nada se ha subido ni publicado automáticamente.**"
    )

    package_dir = ref.provenance.get("package_dir", "—")
    review_id = manifest.get("human_review_artifact_id", "—")
    asset_count = int(manifest.get("asset_count", 0) or 0)
    assets = list(manifest.get("assets") or [])

    _render_package_thumbnail(package_dir, assets)

    with st.container(
        key="centinela-publication-kpis",
        horizontal=True,
        horizontal_alignment="left",
        gap="medium",
    ):
        ui.render_kpi_card(
            "Entregables",
            f"{asset_count}/8",
            detail="Archivos contractuales del paquete final.",
        )
        ui.render_kpi_card(
            "Modo de salida",
            "Manual",
            detail="Tú decides cuándo y dónde publicar.",
        )

    ui.render_section_heading(
        "Paquete final",
        "Los ocho entregables contractuales preparados para la publicación manual.",
        eyebrow="ENTREGABLES",
    )

    for row in assets:
        with st.container(border=True):
            st.markdown(f"### ✓ {_asset_label(row)}")
            relative_path = row.get("relative_path")
            if relative_path:
                st.caption(str(relative_path))

    with st.expander("Trazabilidad y detalles técnicos"):
        st.markdown("**Carpeta preparada**")
        st.code(str(package_dir), language=None)
        st.markdown("**Review humano 7/7**")
        st.code(str(review_id), language=None)
        st.markdown("**Manifest del paquete**")
        st.code(str(ref.artifact_id), language=None)
        for row in assets:
            with st.container(border=True):
                st.markdown(f"**{_asset_label(row)}**")
                st.write(f"Ruta: {row.get('relative_path') or '—'}")
                st.code(str(row.get("sha256") or "—"), language=None)
                st.caption(
                    f"Source artifact: {ui.short_identifier(row.get('source_artifact_id'))} · "
                    f"Source SHA256: {ui.short_identifier(row.get('source_sha256'))}"
                )

    st.caption(
        "Derechos, licencias, procedencia y checklist forman parte del paquete. "
        "No hay upload, OAuth, scheduler, webhook ni autoposting."
    )


def publication_page() -> None:
    service = pages._service()

    ui.render_brand_hero(
        "Preparar publicación",
        "Reúne vídeo, miniatura, subtítulos, copy, metadatos y trazabilidad en un paquete listo para publicación manual.",
        eyebrow="PUBLICACIÓN",
        action_hint="EL CENTINELA PREPARA · TÚ DECIDES CUÁNDO Y DÓNDE PUBLICAR",
    )

    project = pages._project_selector(service, "publication-selector")
    if project is None:
        ui.render_empty_state(
            "No hay un proyecto preparado",
            "La publicación manual aparecerá cuando una historia complete su revisión final.",
            action="Continúa la producción desde Proyectos.",
        )
        return

    with st.container(border=True):
        st.markdown(f"## {project.title}")
        ui.render_state_badge(project.state)
        ui.render_project_timeline(project)

    if project.state == ProjectState.PUBLICATION_PACKAGE_READY:
        _render_ready_package(service, project.project_id)
        return

    if project.state != ProjectState.FINAL_APPROVED:
        st.warning("El paquete final todavía está bloqueado.")
        ui.render_key_value_card(
            "Revisión humana",
            (
                "Pendiente"
                if project.state != ProjectState.READY_FOR_HUMAN_REVIEW
                else "Lista para revisar"
            ),
            detail="Debe completarse Review 7/7 antes de preparar la salida.",
        )
        ui.render_key_value_card(
            "Paquete de publicación",
            "Bloqueado",
            detail="No se genera hasta que el proyecto esté aprobado.",
        )
        st.caption(
            f"Estado actual: {ui.state_display(project.state)}. "
            "Continúa desde Proyectos o abre Revisión cuando corresponda."
        )
        return

    ui.render_manual_publication_notice()

    with st.container(
        key="centinela-publication-readiness",
        horizontal=True,
        horizontal_alignment="left",
        gap="medium",
    ):
        ui.render_key_value_card(
            "Revisión humana",
            "✓ 7/7 aprobada",
            detail="El proyecto ha superado la decisión humana requerida.",
        )
        ui.render_key_value_card(
            "Publicación",
            "Manual",
            detail="Preparar el paquete no publica contenido.",
        )

    ui.render_section_heading(
        "Contenido editorial",
        "Completa los elementos que acompañarán al paquete final.",
    )
    thumbnail = st.file_uploader(
        "Miniatura aprobada (JPEG)",
        type=["jpg", "jpeg"],
        key="publication-thumbnail",
    )
    if thumbnail is not None:
        st.image(thumbnail.getvalue(), caption="Miniatura aprobada")

    title = st.text_input("Título de publicación", value=project.title)
    caption = st.text_area(
        "Caption aprobado",
        key="publication-caption",
        height=130,
    )
    hashtags_text = st.text_input(
        "Hashtags",
        placeholder="#astronomia #astrofotografia",
        key="publication-hashtags",
    )
    youtube_description = st.text_area(
        "Descripción de YouTube (opcional)",
        key="publication-youtube-description",
        height=130,
    )

    st.info(
        "**Publicación manual.** El Centinela prepara los archivos. "
        "Tú decides cuándo y dónde publicarlos."
    )

    if st.button(
        "Preparar paquete",
        type="primary",
        width="stretch",
    ):
        if thumbnail is None:
            st.error("Selecciona la miniatura JPEG que ya fue aprobada en Review 7/7.")
            return
        try:
            with st.spinner("Preparando el paquete final…", show_time=True):
                service.prepare_publication_package_input(
                    project.project_id,
                    thumbnail_bytes=thumbnail.getvalue(),
                    thumbnail_filename=thumbnail.name,
                    title=title,
                    caption=caption,
                    hashtags=_hashtags(hashtags_text),
                    youtube_description=youtube_description,
                )
                service.schedule_publication_package(project.project_id)
            st.success("El paquete final ha entrado en preparación.")
        except ValueError as exc:
            ui.render_error_state(str(exc))
        except Exception as exc:
            LOGGER.exception("Publication package preparation failed")
            ui.render_error_state(
                "No se pudo iniciar la preparación del paquete.",
                action="Nada se ha publicado. Revisa el detalle técnico o reintenta.",
                technical_detail=exc,
            )

    st.caption(
        "El paquete se prepara únicamente para publicación manual. "
        "No se autoriza, programa ni ejecuta ninguna publicación automática."
    )
