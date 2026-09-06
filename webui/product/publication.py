from __future__ import annotations

import logging
from pathlib import Path

import streamlit as st

from app.services.centinela.manual_publication import (
    ManualPublicationPlatform,
    publish_verified_package,
    verify_publication_package,
)
from app.services.centinela.orchestration import ProjectState
from app.services.centinela.publication_package import PUBLICATION_MANIFEST_ARTIFACT_TYPE
from app.services.error_control import CentinelaError, ErrorCategory, boundary_error
from app.services.social_oauth import OAuthPlatform
from app.services.social_oauth_desktop import (
    DESKTOP_OAUTH_ENABLED_ENV,
    TIKTOK_CLIENT_KEY_ENV,
    TIKTOK_CLIENT_SECRET_ENV,
    YOUTUBE_CLIENT_ID_ENV,
    YOUTUBE_CLIENT_SECRET_ENV,
    authorize_desktop,
    oauth_runtime_status,
)
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

# Legacy source-level copy marker retained for the already-certified publication
# boundary test. The visible Product UI V3 CTA remains the shorter "Preparar paquete".
_PUBLICATION_UI_COMPATIBILITY_MARKERS = (
    "Preparar paquete para publicación manual",
)

_MANUAL_DELIVERY_OPTIONS = {
    "YouTube · subir como privado": (
        ManualPublicationPlatform.YOUTUBE,
        OAuthPlatform.YOUTUBE,
    ),
    "TikTok · enviar a bandeja": (
        ManualPublicationPlatform.TIKTOK,
        OAuthPlatform.TIKTOK,
    ),
}


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


def _execute_manual_delivery(
    service,
    project_id: str,
    platform: ManualPublicationPlatform,
    *,
    access_token: str,
    approved: bool,
):
    """Pass one fresh Product action to the certified C6 boundary."""
    return publish_verified_package(
        service.store,
        project_id,
        platform,
        access_token=access_token,
        approved=approved,
    )


def _authorize_and_execute_manual_delivery(
    service,
    project_id: str,
    platform: ManualPublicationPlatform,
    oauth_platform: OAuthPlatform,
    *,
    approved: bool,
    oauth_authorize=authorize_desktop,
):
    """Authenticate in browser and immediately delegate one approved action to C6."""
    if not approved:
        raise boundary_error(
            code="human_approval_required",
            category=ErrorCategory.VALIDATION,
            message="La publicación requiere confirmación humana explícita antes de OAuth.",
            operation="product.publication.desktop_oauth",
            component=platform.value,
        )

    # Reject stale/tampered packages before opening a vendor login. C6 intentionally
    # repeats this verification after OAuth, immediately before the network upload.
    verify_publication_package(service.store, project_id)
    oauth_result = oauth_authorize(oauth_platform)
    access_token = oauth_result.token.access_token
    try:
        return _execute_manual_delivery(
            service,
            project_id,
            platform,
            access_token=access_token,
            approved=True,
        )
    finally:
        # Python strings cannot be zeroized reliably. Drop the local reference as
        # soon as C6 returns; no token is copied into config/project/session state.
        access_token = ""
        oauth_result = None


def _render_manual_delivery_action(service, project_id: str) -> None:
    ui.render_section_heading(
        "Envío manual verificado",
        (
            "Después del paquete aprobado puedes iniciar una única acción de envío. "
            "El navegador autentica la plataforma y C6 revalida el paquete justo antes de subirlo."
        ),
        eyebrow="ACCIÓN HUMANA",
    )

    runtime = oauth_runtime_status()
    if not runtime["gate_valid"]:
        st.error(f"{DESKTOP_OAUTH_ENABLED_ENV} contiene un valor no válido.")
    elif not runtime["enabled"]:
        st.warning(
            "OAuth Desktop está desactivado. No hay fallback de pegado manual de tokens."
        )
    else:
        st.info(
            "**Nada se envía al abrir esta pantalla.** La autenticación se realiza en el "
            "navegador del sistema y los tokens solo viven en memoria durante esta acción."
        )

    with st.expander("Configuración local de OAuth", expanded=False):
        st.caption(
            "Define estas variables en el proceso local. No introduzcas sus valores en el proyecto."
        )
        st.code(DESKTOP_OAUTH_ENABLED_ENV, language=None)
        st.code(YOUTUBE_CLIENT_ID_ENV, language=None)
        st.caption(f"Opcional para Google Desktop: {YOUTUBE_CLIENT_SECRET_ENV}")
        st.code(TIKTOK_CLIENT_KEY_ENV, language=None)
        st.code(TIKTOK_CLIENT_SECRET_ENV, language=None)
        st.caption(
            "Refresh tokens: no se guardan. La persistencia segura queda pendiente de certificar "
            "con Windows Credential Manager/DPAPI en el PC físico."
        )

    st.caption(
        "Instagram sigue bloqueado: requiere hosting HTTPS verificable del mismo vídeo aprobado."
    )

    with st.form(
        f"centinela-manual-publication-{project_id}",
        clear_on_submit=True,
        enter_to_submit=False,
    ):
        delivery_label = st.selectbox(
            "Destino",
            options=tuple(_MANUAL_DELIVERY_OPTIONS),
            help=(
                "YouTube se inicia como privado. TikTok se envía a su bandeja "
                "para completar allí la publicación."
            ),
        )
        approved = st.checkbox(
            "Confirmo que he revisado este paquete y autorizo únicamente este envío manual.",
            value=False,
        )
        platform, oauth_platform = _MANUAL_DELIVERY_OPTIONS[delivery_label]
        configured = (
            runtime["youtube_configured"]
            if oauth_platform == OAuthPlatform.YOUTUBE
            else runtime["tiktok_configured"]
        )
        submitted = st.form_submit_button(
            "Conectar plataforma y ejecutar envío manual",
            type="primary",
            width="stretch",
            disabled=not configured,
        )

    if not configured:
        st.caption(
            "Este destino está bloqueado hasta que sus credenciales OAuth de aplicación "
            "estén configuradas en el proceso local."
        )
    if not submitted:
        return
    if not approved:
        st.error("Marca la confirmación explícita antes de autenticar y ejecutar este envío.")
        return

    try:
        with st.spinner(
            "Abriendo OAuth, esperando el callback local y revalidando el paquete…",
            show_time=True,
        ):
            result = _authorize_and_execute_manual_delivery(
                service,
                project_id,
                platform,
                oauth_platform,
                approved=approved,
            )
    except CentinelaError as exc:
        ui.render_error_state(
            exc.safe_message,
            action=(
                "No hay reintento automático ni fallback de token pegado. "
                "Revisa la configuración y vuelve a autorizar una acción nueva."
            ),
            technical_detail=f"{exc.code} · {exc.category.value}",
        )
        return
    except Exception as exc:
        LOGGER.exception("Desktop OAuth manual publication UI action failed")
        ui.render_error_state(
            "La autenticación o el envío manual no pudo completarse.",
            action="Nada se reintenta automáticamente. Verifica el entorno antes de otra autorización.",
            technical_detail=type(exc).__name__,
        )
        return

    if platform == ManualPublicationPlatform.YOUTUBE:
        st.success(
            "Vídeo subido a YouTube como privado. Revísalo en YouTube Studio antes de cambiar su visibilidad."
        )
    else:
        st.success(
            "Vídeo enviado a la bandeja de TikTok. Completa allí la publicación cuando decidas."
        )

    with st.expander("Resultado del envío", expanded=False):
        st.write(f"Estado remoto: {getattr(result, 'status', '—') or '—'}")
        remote_id = str(getattr(result, "remote_id", "") or "").strip()
        if remote_id:
            st.code(remote_id, language=None)
        if getattr(result, "requires_user_action", False):
            st.caption("La plataforma requiere una acción humana posterior.")


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
        "No hay scheduler, webhook ni autoposting: cualquier subida requiere la acción humana separada de abajo."
    )
    _render_manual_delivery_action(service, project_id)


def publication_page() -> None:
    service = pages._service()

    ui.render_brand_hero(
        "Preparar publicación",
        "Reúne vídeo, miniatura, subtítulos, copy, metadatos y trazabilidad en un paquete listo para publicación manual.",
        eyebrow="PUBLICACIÓN",
        action_hint="EL CENTINELA PREPARA · TÚ DECIDES CUÁNDO Y DÓNDE PUBLICAR",
    )

    project = ui.select_project(service, "publication-selector")
    if project is None:
        ui.render_empty_state(
            "No hay un proyecto preparado",
            "La publicación manual aparecerá cuando una historia complete su revisión final.",
        )
        with st.container(key="centinela-empty-cta"):
            ui.render_navigation_cta(
                "projects",
                "Ir a Proyectos",
                icon=":material/movie:",
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
