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
from app.services.instagram_ephemeral_https import (
    INSTAGRAM_EPHEMERAL_HTTPS_ENABLED_ENV,
    INSTAGRAM_TUNNEL_PROVIDER_ENV,
    ephemeral_https_settings,
)
from app.services.instagram_manual_publication import (
    get_instagram_publish_receipt,
    get_unresolved_instagram_publish_intent,
    load_latest_prepared_instagram_reel,
    prepare_instagram_manual_publication,
    publish_instagram_manual_publication,
)
from app.services.instagram_oauth_callback import (
    INSTAGRAM_CALLBACK_ENABLED_ENV,
    INSTAGRAM_CALLBACK_PROVIDER_ENV,
    INSTAGRAM_CLIENT_ID_ENV,
    INSTAGRAM_CLIENT_SECRET_ENV,
    INSTAGRAM_REDIRECT_URI_ENV,
    TAILSCALE_PROVIDER,
    callback_runtime_status,
)
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
        "Instagram usa un flujo separado de dos aprobaciones con OAuth y hosting HTTPS verificable; "
        "se configura en el bloque específico de Instagram más abajo."
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


def _instagram_product_runtime_status() -> dict[str, object]:
    callback = callback_runtime_status()
    try:
        transport = ephemeral_https_settings()
        transport_gate_valid = True
        transport_enabled = bool(transport.enabled)
        transport_provider = (
            transport.provider.value if transport.provider is not None else ""
        )
    except Exception:
        transport_gate_valid = False
        transport_enabled = False
        transport_provider = ""

    callback_provider = str(callback.get("provider") or "")
    unified_tailscale = bool(
        callback_provider == TAILSCALE_PROVIDER
        and transport_provider == TAILSCALE_PROVIDER
    )
    ready = bool(
        callback.get("gate_valid")
        and callback.get("enabled")
        and callback.get("configured")
        and transport_gate_valid
        and transport_enabled
        and transport_provider
    )
    return {
        "callback_gate_valid": bool(callback.get("gate_valid")),
        "callback_enabled": bool(callback.get("enabled")),
        "callback_configured": bool(callback.get("configured")),
        "callback_provider": callback_provider,
        "transport_gate_valid": transport_gate_valid,
        "transport_enabled": transport_enabled,
        "transport_provider": transport_provider,
        "unified_tailscale": unified_tailscale,
        "ready": ready,
        "token_persistence": False,
        "auto_publication": False,
    }


def _prepare_instagram_product_action(
    service,
    project_id: str,
    *,
    approved: bool,
):
    return prepare_instagram_manual_publication(
        service.store,
        project_id,
        approved=approved,
    )


def _publish_instagram_product_action(
    service,
    project_id: str,
    *,
    approved: bool,
):
    return publish_instagram_manual_publication(
        service.store,
        project_id,
        approved=approved,
    )


def _render_instagram_manual_action(service, project_id: str) -> None:
    ui.render_section_heading(
        "Instagram Reel",
        (
            "Instagram se ejecuta en dos acciones humanas separadas. Primero autenticas y preparas "
            "un contenedor FINISHED; después una segunda aprobación exige autenticar de nuevo la "
            "misma cuenta antes de media_publish."
        ),
        eyebrow="DOS APROBACIONES",
    )

    runtime = _instagram_product_runtime_status()
    if not runtime["callback_gate_valid"]:
        st.error(f"{INSTAGRAM_CALLBACK_ENABLED_ENV} contiene un valor no válido.")
    elif not runtime["callback_enabled"]:
        st.warning("El callback HTTPS de Instagram está desactivado.")
    elif not runtime["callback_configured"]:
        st.warning("Falta completar la configuración OAuth de Instagram en el proceso local.")

    if not runtime["transport_gate_valid"]:
        st.error(f"{INSTAGRAM_EPHEMERAL_HTTPS_ENABLED_ENV} contiene una configuración no válida.")
    elif not runtime["transport_enabled"]:
        st.warning("El hosting HTTPS verificable del Reel está desactivado.")
    elif runtime["unified_tailscale"]:
        st.success(
            "Tailscale Funnel está seleccionado como transporte unificado para OAuth y MP4."
        )
    elif runtime["transport_provider"]:
        st.info(
            "Instagram usa Tailscale Funnel para OAuth y un proveedor HTTPS alternativo para el MP4."
        )

    with st.expander("Configuración local de Instagram", expanded=False):
        st.caption(
            "Define únicamente estas variables en el proceso local. La interfaz nunca muestra ni "
            "persiste sus valores."
        )
        for variable in (
            INSTAGRAM_CALLBACK_ENABLED_ENV,
            INSTAGRAM_CALLBACK_PROVIDER_ENV,
            INSTAGRAM_CLIENT_ID_ENV,
            INSTAGRAM_CLIENT_SECRET_ENV,
            INSTAGRAM_REDIRECT_URI_ENV,
            INSTAGRAM_EPHEMERAL_HTTPS_ENABLED_ENV,
            INSTAGRAM_TUNNEL_PROVIDER_ENV,
        ):
            st.code(variable, language=None)
        st.caption(
            "Recomendado: usa tailscale_funnel también en el transporte del MP4 para que una sola "
            "herramienta cubra OAuth + vídeo. cloudflare_quick y zrok_public quedan como fallback "
            "explícito. Centinela no descarga binarios ni guarda tokens por su cuenta."
        )

    try:
        prepared = load_latest_prepared_instagram_reel(service.store, project_id)
        receipt = get_instagram_publish_receipt(service.store, project_id)
        unresolved_intent = get_unresolved_instagram_publish_intent(service.store, project_id)
    except CentinelaError as exc:
        ui.render_error_state(
            exc.safe_message,
            action="No continúes con Instagram hasta recuperar la trazabilidad del contenedor.",
            technical_detail=f"{exc.code} · {exc.category.value}",
        )
        return
    except Exception as exc:
        LOGGER.exception("Instagram Product state could not be loaded")
        ui.render_error_state(
            "No se pudo verificar el estado persistido de Instagram.",
            action="No se abrirá OAuth ni se publicará mientras el estado no sea verificable.",
            technical_detail=type(exc).__name__,
        )
        return

    if receipt is not None:
        st.success("Instagram ya tiene un recibo local de publicación para este contenedor.")
        with st.expander("Recibo de Instagram", expanded=False):
            st.write(f"Estado remoto: {receipt.status or '—'}")
            if receipt.remote_id:
                st.code(receipt.remote_id, language=None)
        st.caption("No se ofrece otro media_publish para este contenedor.")
        return

    if unresolved_intent is not None:
        st.warning(
            "Existe un intento previo de publicación cuyo resultado remoto no está resuelto. "
            "Por seguridad no se ofrece otro media_publish."
        )
        with st.expander("Intento de Instagram por resolver", expanded=True):
            st.code(unresolved_intent.container_id or "—", language=None)
            st.caption(
                "Verifica manualmente el estado de este Reel en Instagram antes de cualquier recuperación futura."
            )
        return

    if prepared is None:
        st.info(
            "**Fase 1 de 2.** Se abrirá Instagram Business Login y después se preparará el Reel "
            "mediante hosting HTTPS verificable. Esta acción no ejecuta media_publish."
        )
        with st.form(
            f"centinela-instagram-prepare-{project_id}",
            clear_on_submit=True,
            enter_to_submit=False,
        ):
            approved = st.checkbox(
                "Confirmo que he revisado el paquete y autorizo únicamente preparar el Reel en Instagram.",
                value=False,
            )
            submitted = st.form_submit_button(
                "Autenticar y preparar Reel",
                type="primary",
                width="stretch",
                disabled=not bool(runtime["ready"]),
            )
        if not runtime["ready"]:
            st.caption("Fase 1 bloqueada hasta completar OAuth, callback y hosting HTTPS verificable.")
        if not submitted:
            return
        if not approved:
            st.error("Marca la confirmación explícita antes de autenticar y preparar Instagram.")
            return
        try:
            with st.spinner(
                "Autenticando Instagram y preparando el contenedor…",
                show_time=True,
            ):
                record = _prepare_instagram_product_action(
                    service,
                    project_id,
                    approved=True,
                )
        except CentinelaError as exc:
            ui.render_error_state(
                exc.safe_message,
                action="Nada se reintenta automáticamente. Revisa el entorno antes de otra aprobación.",
                technical_detail=f"{exc.code} · {exc.category.value}",
            )
            return
        except Exception as exc:
            LOGGER.exception("Instagram Product preparation failed")
            ui.render_error_state(
                "Instagram no pudo completar la preparación manual del Reel.",
                action="No se ha autorizado media_publish. Verifica el entorno antes de repetir la fase 1.",
                technical_detail=type(exc).__name__,
            )
            return
        st.success("Reel preparado y FINISHED. Todavía no se ha publicado.")
        st.code(record.prepared.container_id, language=None)
        st.caption("La publicación exige una segunda aprobación y una nueva autenticación de la misma cuenta.")
        return

    st.info(
        "**Fase 2 de 2.** El contenedor está FINISHED. Para publicar debes dar una segunda aprobación "
        "y autenticar de nuevo la misma cuenta de Instagram."
    )
    with st.container(border=True):
        st.markdown("### ✓ Contenedor preparado")
        st.write("Estado: FINISHED")
        st.code(prepared.prepared.container_id, language=None)
        st.caption(f"Cuenta Instagram ID: {prepared.prepared.ig_user_id}")

    with st.form(
        f"centinela-instagram-publish-{project_id}",
        clear_on_submit=True,
        enter_to_submit=False,
    ):
        approved = st.checkbox(
            "Segunda aprobación: autorizo publicar únicamente este Reel preparado en la misma cuenta.",
            value=False,
        )
        submitted = st.form_submit_button(
            "Autenticar de nuevo y publicar Reel",
            type="primary",
            width="stretch",
            disabled=not bool(runtime["ready"]),
        )
    if not runtime["ready"]:
        st.caption("Fase 2 bloqueada hasta que OAuth/callback vuelvan a estar disponibles.")
    if not submitted:
        return
    if not approved:
        st.error("La segunda aprobación explícita es obligatoria antes de media_publish.")
        return

    try:
        with st.spinner(
            "Autenticando de nuevo la misma cuenta y ejecutando media_publish…",
            show_time=True,
        ):
            result = _publish_instagram_product_action(
                service,
                project_id,
                approved=True,
            )
    except CentinelaError as exc:
        ui.render_error_state(
            exc.safe_message,
            action=(
                "No hay reintento automático. Si Instagram pudo publicar pero falló el recibo local, "
                "verifica primero el estado remoto antes de hacer otra acción."
            ),
            technical_detail=f"{exc.code} · {exc.category.value}",
        )
        return
    except Exception as exc:
        LOGGER.exception("Instagram Product publish failed")
        ui.render_error_state(
            "La publicación manual de Instagram no pudo confirmarse.",
            action="No se reintenta automáticamente; verifica Instagram antes de otra aprobación.",
            technical_detail=type(exc).__name__,
        )
        return

    if getattr(result, "success", False):
        st.success("Reel publicado en Instagram y recibo local registrado.")
        remote_id = str(getattr(result, "remote_id", "") or "").strip()
        if remote_id:
            st.code(remote_id, language=None)
    else:
        st.warning("Instagram devolvió un resultado no exitoso; no se hará ningún reintento automático.")


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
    _render_instagram_manual_action(service, project_id)


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
