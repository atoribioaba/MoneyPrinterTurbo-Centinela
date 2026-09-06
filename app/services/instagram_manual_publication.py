"""Persisted, token-free manual Instagram publication workflow for Product UI.

C13 composes the certified C10/C11/C12 boundaries without persisting OAuth
credentials. Phase 1 authenticates once, prepares a FINISHED Instagram Reel
container, and stores only non-secret container/package evidence. Phase 2
requires a fresh human approval and a fresh OAuth session, proves the same
Instagram user_id, publishes once, and stores a non-secret receipt.

Canonical policy:
    GENERAR -> REVISAR -> APROBAR -> PUBLICAR
    AUTO_PUBLICATION = False
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from app.services.centinela.manual_publication import verify_publication_package
from app.services.centinela.project_foundation import (
    ArtifactNotFoundError,
    ArtifactRef,
    ArtifactStore,
)
from app.services.error_control import ErrorCategory, boundary_error
from app.services.instagram_ephemeral_https import (
    InstagramTunnelProvider,
    PreparedInstagramReel,
    TransportEvidence,
    prepare_instagram_reel,
    publish_prepared_instagram_reel,
)
from app.services.instagram_oauth_callback import (
    InstagramCallbackSessionResult,
    authorize_instagram_via_stable_https,
)
from app.services.social_publication import SocialResult

AUTO_PUBLICATION = False
INSTAGRAM_PREPARED_REEL_ARTIFACT_TYPE = "instagram_prepared_reel"
INSTAGRAM_PUBLISH_RECEIPT_ARTIFACT_TYPE = "instagram_publish_receipt"
_SCHEMA_VERSION = 1
_PRODUCER = "centinela.instagram_manual_publication"
_SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")

InstagramAuthorize = Callable[..., InstagramCallbackSessionResult]
InstagramPrepare = Callable[..., PreparedInstagramReel]
InstagramPublish = Callable[..., SocialResult]


@dataclass(frozen=True, slots=True)
class PersistedPreparedInstagramReel:
    artifact_id: str
    prepared: PreparedInstagramReel


@dataclass(frozen=True, slots=True)
class InstagramPublishReceipt:
    artifact_id: str
    prepared_artifact_id: str
    remote_id: str
    status: str


def _error(
    code: str,
    category: ErrorCategory,
    message: str,
    *,
    operation: str,
    details: dict[str, Any] | None = None,
    cause: BaseException | None = None,
):
    return boundary_error(
        code=code,
        category=category,
        message=message,
        operation=operation,
        component="instagram_manual_publication",
        details=details,
        cause=cause,
    )


def _required_text(payload: dict[str, Any], key: str) -> str:
    value = str(payload.get(key) or "").strip()
    if not value:
        raise _error(
            "instagram_prepared_artifact_invalid",
            ErrorCategory.VALIDATION,
            "El artefacto de preparación de Instagram está incompleto.",
            operation="instagram_manual_publication.load_prepared",
            details={"field": key},
        )
    return value


def _required_sha256(payload: dict[str, Any], key: str) -> str:
    value = _required_text(payload, key).lower()
    if _SHA256_RE.fullmatch(value) is None:
        raise _error(
            "instagram_prepared_artifact_invalid",
            ErrorCategory.VALIDATION,
            "El artefacto de preparación contiene un SHA-256 no válido.",
            operation="instagram_manual_publication.load_prepared",
            details={"field": key},
        )
    return value


def _transport_payload(evidence: TransportEvidence) -> dict[str, Any]:
    return evidence.as_dict()


def _prepared_payload(prepared: PreparedInstagramReel) -> dict[str, Any]:
    return {
        "schema_version": _SCHEMA_VERSION,
        "project_id": prepared.project_id,
        "manifest_artifact_id": prepared.manifest_artifact_id,
        "publication_package_hash": prepared.publication_package_hash,
        "human_review_artifact_id": prepared.human_review_artifact_id,
        "social_video_sha256": prepared.social_video_sha256,
        "ig_user_id": prepared.ig_user_id,
        "container_id": prepared.container_id,
        "status": prepared.status,
        "tunnel_provider": prepared.tunnel_provider.value,
        "transport_evidence": _transport_payload(prepared.transport_evidence),
        "contains_credentials": False,
        "auto_publication": False,
    }


def _prepared_from_payload(payload: Any) -> PreparedInstagramReel:
    if not isinstance(payload, dict) or payload.get("schema_version") != _SCHEMA_VERSION:
        raise _error(
            "instagram_prepared_artifact_invalid",
            ErrorCategory.VALIDATION,
            "El artefacto de preparación de Instagram no tiene un esquema compatible.",
            operation="instagram_manual_publication.load_prepared",
        )
    if payload.get("contains_credentials") is not False or payload.get("auto_publication") is not False:
        raise _error(
            "instagram_prepared_artifact_policy_violation",
            ErrorCategory.VALIDATION,
            "El artefacto de preparación de Instagram viola la política de seguridad.",
            operation="instagram_manual_publication.load_prepared",
        )

    transport = payload.get("transport_evidence")
    if not isinstance(transport, dict):
        raise _error(
            "instagram_prepared_artifact_invalid",
            ErrorCategory.VALIDATION,
            "Falta la evidencia de transporte del Reel preparado.",
            operation="instagram_manual_publication.load_prepared",
        )
    try:
        provider = InstagramTunnelProvider(_required_text(payload, "tunnel_provider"))
        evidence_provider = InstagramTunnelProvider(_required_text(transport, "provider"))
        size_bytes = int(transport.get("size_bytes"))
        head_status = int(transport.get("head_status"))
        get_status = int(transport.get("get_status"))
        range_status = int(transport.get("range_status"))
    except (TypeError, ValueError) as exc:
        raise _error(
            "instagram_prepared_artifact_invalid",
            ErrorCategory.VALIDATION,
            "La evidencia del Reel preparado contiene tipos no válidos.",
            operation="instagram_manual_publication.load_prepared",
            cause=exc,
        ) from exc
    if provider != evidence_provider or size_bytes <= 0:
        raise _error(
            "instagram_prepared_artifact_invalid",
            ErrorCategory.VALIDATION,
            "La evidencia del Reel preparado no es coherente.",
            operation="instagram_manual_publication.load_prepared",
        )

    evidence = TransportEvidence(
        provider=evidence_provider,
        public_origin=_required_text(transport, "public_origin"),
        public_path_sha256=_required_sha256(transport, "public_path_sha256"),
        local_media_sha256=_required_sha256(transport, "local_media_sha256"),
        remote_media_sha256=_required_sha256(transport, "remote_media_sha256"),
        size_bytes=size_bytes,
        content_type=_required_text(transport, "content_type"),
        head_status=head_status,
        get_status=get_status,
        range_status=range_status,
    )
    prepared = PreparedInstagramReel(
        project_id=_required_text(payload, "project_id"),
        manifest_artifact_id=_required_text(payload, "manifest_artifact_id"),
        publication_package_hash=_required_sha256(payload, "publication_package_hash"),
        human_review_artifact_id=_required_text(payload, "human_review_artifact_id"),
        social_video_sha256=_required_sha256(payload, "social_video_sha256"),
        ig_user_id=_required_text(payload, "ig_user_id"),
        container_id=_required_text(payload, "container_id"),
        status=_required_text(payload, "status"),
        tunnel_provider=provider,
        transport_evidence=evidence,
    )
    if prepared.status != "FINISHED":
        raise _error(
            "instagram_prepared_artifact_not_finished",
            ErrorCategory.VALIDATION,
            "El contenedor persistido de Instagram no está FINISHED.",
            operation="instagram_manual_publication.load_prepared",
        )
    return prepared


def persist_prepared_instagram_reel(
    store: ArtifactStore,
    prepared: PreparedInstagramReel,
) -> ArtifactRef:
    if AUTO_PUBLICATION:
        raise RuntimeError("AUTO_PUBLICATION invariant was modified")
    if prepared.status != "FINISHED":
        raise _error(
            "instagram_prepared_container_not_finished",
            ErrorCategory.VALIDATION,
            "Solo se puede persistir un contenedor Instagram FINISHED.",
            operation="instagram_manual_publication.persist_prepared",
        )
    return store.put_json(
        prepared.project_id,
        INSTAGRAM_PREPARED_REEL_ARTIFACT_TYPE,
        _prepared_payload(prepared),
        producer=_PRODUCER,
        input_artifact_ids=(prepared.manifest_artifact_id,),
        metadata={
            "container_id": prepared.container_id,
            "ig_user_id": prepared.ig_user_id,
            "contains_credentials": False,
        },
    )


def load_latest_prepared_instagram_reel(
    store: ArtifactStore,
    project_id: str,
) -> PersistedPreparedInstagramReel | None:
    try:
        ref = store.get_latest_artifact(project_id, INSTAGRAM_PREPARED_REEL_ARTIFACT_TYPE)
    except ArtifactNotFoundError:
        return None
    payload = store.read_json(project_id, ref.artifact_id, verify_integrity=True)
    prepared = _prepared_from_payload(payload)
    if prepared.project_id != project_id:
        raise _error(
            "instagram_prepared_project_mismatch",
            ErrorCategory.VALIDATION,
            "El contenedor preparado no pertenece al proyecto seleccionado.",
            operation="instagram_manual_publication.load_prepared",
        )
    return PersistedPreparedInstagramReel(artifact_id=ref.artifact_id, prepared=prepared)


def _receipt_for_prepared(
    store: ArtifactStore,
    project_id: str,
    prepared_artifact_id: str,
) -> InstagramPublishReceipt | None:
    refs = store.list_artifacts(project_id, artifact_type=INSTAGRAM_PUBLISH_RECEIPT_ARTIFACT_TYPE)
    for ref in reversed(refs):
        payload = store.read_json(project_id, ref.artifact_id, verify_integrity=True)
        if not isinstance(payload, dict):
            continue
        if str(payload.get("prepared_artifact_id") or "") != prepared_artifact_id:
            continue
        if payload.get("schema_version") != _SCHEMA_VERSION or payload.get("success") is not True:
            continue
        return InstagramPublishReceipt(
            artifact_id=ref.artifact_id,
            prepared_artifact_id=prepared_artifact_id,
            remote_id=str(payload.get("remote_id") or "").strip(),
            status=str(payload.get("status") or "").strip(),
        )
    return None


def get_instagram_publish_receipt(
    store: ArtifactStore,
    project_id: str,
) -> InstagramPublishReceipt | None:
    prepared = load_latest_prepared_instagram_reel(store, project_id)
    if prepared is None:
        return None
    return _receipt_for_prepared(store, project_id, prepared.artifact_id)


def _package_matches_prepared(store: ArtifactStore, prepared: PreparedInstagramReel) -> None:
    package = verify_publication_package(store, prepared.project_id)
    if not (
        package.manifest_artifact_id == prepared.manifest_artifact_id
        and package.publication_package_hash == prepared.publication_package_hash
        and package.human_review_artifact_id == prepared.human_review_artifact_id
        and package.social_video_sha256 == prepared.social_video_sha256
    ):
        raise _error(
            "instagram_prepared_package_stale",
            ErrorCategory.VALIDATION,
            "El contenedor preparado ya no pertenece al paquete aprobado vigente.",
            operation="instagram_manual_publication.verify_prepared",
        )


def prepare_instagram_manual_publication(
    store: ArtifactStore,
    project_id: str,
    *,
    approved: bool = False,
    oauth_authorize: InstagramAuthorize = authorize_instagram_via_stable_https,
    prepare: InstagramPrepare = prepare_instagram_reel,
) -> PersistedPreparedInstagramReel:
    """Fresh approval -> OAuth -> C10 prepare -> token-free persisted preparation."""
    if AUTO_PUBLICATION:
        raise RuntimeError("AUTO_PUBLICATION invariant was modified")
    if not approved:
        raise _error(
            "human_approval_required",
            ErrorCategory.VALIDATION,
            "Preparar Instagram requiere una confirmación humana explícita.",
            operation="instagram_manual_publication.prepare",
        )

    # Reject stale/tampered packages before opening the vendor login.
    verify_publication_package(store, project_id)
    oauth_result = oauth_authorize()
    token = oauth_result.token
    access_token = str(token.access_token or "").strip()
    user_id = str(token.user_id or "").strip()
    try:
        if not access_token or not user_id:
            raise _error(
                "instagram_oauth_identity_missing",
                ErrorCategory.AUTH,
                "Instagram OAuth no devolvió token e identidad de cuenta verificables.",
                operation="instagram_manual_publication.prepare",
            )
        prepared = prepare(
            store,
            project_id,
            ig_user_id=user_id,
            access_token=access_token,
            approved=True,
        )
    finally:
        access_token = ""
        token = None
        oauth_result = None

    try:
        ref = persist_prepared_instagram_reel(store, prepared)
    except Exception as exc:
        raise _error(
            "instagram_prepared_persistence_failed",
            ErrorCategory.FILESYSTEM,
            (
                "Instagram terminó de preparar el contenedor, pero no se pudo guardar "
                "su evidencia local. No se ha ejecutado media_publish."
            ),
            operation="instagram_manual_publication.prepare",
            details={"container_id": prepared.container_id},
            cause=exc,
        ) from exc
    return PersistedPreparedInstagramReel(artifact_id=ref.artifact_id, prepared=prepared)


def publish_instagram_manual_publication(
    store: ArtifactStore,
    project_id: str,
    *,
    approved: bool = False,
    oauth_authorize: InstagramAuthorize = authorize_instagram_via_stable_https,
    publish: InstagramPublish = publish_prepared_instagram_reel,
) -> SocialResult:
    """Fresh second approval + fresh OAuth + same-account proof -> media_publish once."""
    if AUTO_PUBLICATION:
        raise RuntimeError("AUTO_PUBLICATION invariant was modified")
    if not approved:
        raise _error(
            "human_approval_required",
            ErrorCategory.VALIDATION,
            "Publicar el Reel preparado requiere una segunda confirmación humana explícita.",
            operation="instagram_manual_publication.publish",
        )

    record = load_latest_prepared_instagram_reel(store, project_id)
    if record is None:
        raise _error(
            "instagram_prepared_container_missing",
            ErrorCategory.VALIDATION,
            "No existe un contenedor Instagram preparado para este proyecto.",
            operation="instagram_manual_publication.publish",
        )
    if _receipt_for_prepared(store, project_id, record.artifact_id) is not None:
        raise _error(
            "instagram_prepared_container_already_published",
            ErrorCategory.VALIDATION,
            "Este contenedor Instagram ya tiene un recibo de publicación y no se repetirá.",
            operation="instagram_manual_publication.publish",
        )

    _package_matches_prepared(store, record.prepared)
    oauth_result = oauth_authorize()
    token = oauth_result.token
    access_token = str(token.access_token or "").strip()
    user_id = str(token.user_id or "").strip()
    try:
        if not access_token or not user_id:
            raise _error(
                "instagram_oauth_identity_missing",
                ErrorCategory.AUTH,
                "Instagram OAuth no devolvió token e identidad de cuenta verificables.",
                operation="instagram_manual_publication.publish",
            )
        if user_id != record.prepared.ig_user_id:
            raise _error(
                "instagram_publish_account_mismatch",
                ErrorCategory.AUTH,
                "La segunda autenticación pertenece a otra cuenta de Instagram.",
                operation="instagram_manual_publication.publish",
            )
        result = publish(
            store,
            record.prepared,
            access_token=access_token,
            approved=True,
        )
    finally:
        access_token = ""
        token = None
        oauth_result = None

    if not result.success:
        return result

    receipt_payload = {
        "schema_version": _SCHEMA_VERSION,
        "prepared_artifact_id": record.artifact_id,
        "manifest_artifact_id": record.prepared.manifest_artifact_id,
        "publication_package_hash": record.prepared.publication_package_hash,
        "ig_user_id": record.prepared.ig_user_id,
        "container_id": record.prepared.container_id,
        "remote_id": str(result.remote_id or "").strip(),
        "status": str(result.status or "").strip(),
        "success": True,
        "contains_credentials": False,
        "auto_publication": False,
    }
    try:
        store.put_json(
            project_id,
            INSTAGRAM_PUBLISH_RECEIPT_ARTIFACT_TYPE,
            receipt_payload,
            producer=_PRODUCER,
            input_artifact_ids=(record.artifact_id,),
            metadata={
                "remote_id": receipt_payload["remote_id"],
                "container_id": record.prepared.container_id,
                "contains_credentials": False,
            },
        )
    except Exception as exc:
        raise _error(
            "instagram_publish_receipt_persistence_failed",
            ErrorCategory.FILESYSTEM,
            (
                "Instagram indicó éxito remoto, pero no se pudo guardar el recibo local. "
                "No reintentes automáticamente: verifica primero el estado en Instagram."
            ),
            operation="instagram_manual_publication.publish",
            details={
                "remote_id": receipt_payload["remote_id"],
                "container_id": record.prepared.container_id,
            },
            cause=exc,
        ) from exc
    return result
