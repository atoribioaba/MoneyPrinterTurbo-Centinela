from __future__ import annotations

import streamlit as st

from app.services.centinela.orchestration import ProjectState
from app.services.centinela.publication_package import PUBLICATION_MANIFEST_ARTIFACT_TYPE
from webui.product import pages


def _hashtags(value: str) -> list[str]:
    return [item.strip() for item in value.split() if item.strip()]


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
        st.error(f"El paquete está marcado como listo pero su manifest no es legible: {exc}")
        return

    st.success("LISTO PARA PUBLICACIÓN MANUAL")
    st.write(f"**Ruta del paquete:** `{ref.provenance.get('package_dir', '—')}`")
    st.write(f"**Review 7/7:** `{manifest.get('human_review_artifact_id', '—')}`")
    st.write(f"**Assets contractuales:** `{manifest.get('asset_count', 0)}/8`")
    assets = manifest.get("assets") or []
    st.dataframe(
        [
            {
                "Asset": row.get("logical_name"),
                "Ruta": row.get("relative_path"),
                "SHA256": row.get("sha256"),
                "Source artifact": row.get("source_artifact_id"),
                "Source SHA256": row.get("source_sha256"),
            }
            for row in assets
        ],
        use_container_width=True,
        hide_index=True,
    )
    st.caption(
        "Derechos/provenance y checklist forman parte de los ocho assets. "
        "La publicación sigue siendo manual: no hay upload, OAuth, scheduler, webhook ni autoposting."
    )


def publication_page() -> None:
    service = pages._service()
    pages._header(
        "Publicación",
        "Preparación física del paquete final; la publicación continúa siendo manual.",
    )
    project = pages._project_selector(service, "publication-selector")
    if project is None:
        return

    if project.state == ProjectState.PUBLICATION_PACKAGE_READY:
        _render_ready_package(service, project.project_id)
        return

    if project.state != ProjectState.FINAL_APPROVED:
        st.info(
            f"Este proyecto está en **{project.state_label}**. "
            "La preparación se habilita únicamente después de Review 7/7 y FINAL_APPROVED."
        )
        return

    st.warning(
        "Esta acción prepara archivos locales para publicación manual. "
        "No autoriza ni ejecuta ninguna publicación automática."
    )
    thumbnail = st.file_uploader(
        "Miniatura aprobada (JPEG)",
        type=["jpg", "jpeg"],
        key="publication-thumbnail",
    )
    title = st.text_input("Título de publicación", value=project.title)
    caption = st.text_area("Caption aprobado", key="publication-caption")
    hashtags_text = st.text_input(
        "Hashtags",
        placeholder="#astronomia #astrofotografia",
        key="publication-hashtags",
    )
    youtube_description = st.text_area(
        "Descripción de YouTube (opcional)",
        key="publication-youtube-description",
    )

    if st.button(
        "Preparar paquete para publicación manual",
        type="primary",
        use_container_width=True,
    ):
        if thumbnail is None:
            st.error("Selecciona la miniatura JPEG que ya fue aprobada en Review 7/7.")
            return
        try:
            service.prepare_publication_package_input(
                project.project_id,
                thumbnail_bytes=thumbnail.getvalue(),
                thumbnail_filename=thumbnail.name,
                title=title,
                caption=caption,
                hashtags=_hashtags(hashtags_text),
                youtube_description=youtube_description,
            )
            schedule = service.schedule_publication_package(project.project_id)
            st.success(
                "Paquete en preparación mediante PUBLICATION_PACKAGE con request={}. "
                f"Job: {schedule.job_id or 'reutilizado'}."
            )
        except Exception as exc:
            st.error(str(exc))

    st.caption(
        "MANUAL_PUBLICATION_ONLY=TRUE · AUTO_PUBLICATION=FALSE · "
        "AUTHORIZATION_TO_PUBLISH=FALSE"
    )
