"""Verified manual publication bridge for EL CENTINELA DEL UNIVERSO.

This module is intentionally outside the automatic production spine. It accepts
only a project whose certified publication package already reached
``PUBLICATION_PACKAGE_READY`` and requires a fresh explicit human approval for
every network operation.

Safety policy:
    GENERAR -> REVISAR -> APROBAR -> PUBLICAR
    AUTO_PUBLICATION = False
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from app.models.publication_package import PublicationMetadata
from app.services.centinela.orchestration import ProjectState, ProjectStateMachine
from app.services.centinela.project_foundation import (
    ArtifactNotFoundError,
    ArtifactStore,
    IntegrityError,
)
from app.services.centinela.publication_package import (
    PUBLICATION_MANIFEST_ARTIFACT_TYPE,
    TARGETS,
)
from app.services.error_control import CentinelaError, ErrorCategory, boundary_error
from app.services.social_publication import SocialResult, TikTokAdapter, YouTubeAdapter

AUTO_PUBLICATION = False
MANUAL_PUBLICATION_BRIDGE_VERSION = "c05-c6-manual-publication-v0.1"


class ManualPublicationPlatform(StrEnum):
    YOUTUBE = "youtube"
    TIKTOK = "tiktok"
    INSTAGRAM = "instagram"


@dataclass(frozen=True, slots=True)
class VerifiedPublicationPackage:
    project_id: str
    manifest_artifact_id: str
    publication_package_hash: str
    human_review_artifact_id: str
    package_dir: Path
    social_video_path: Path
    social_video_sha256: str
    metadata: PublicationMetadata


def _blocked(
    code: str,
    message: str,
    *,
    component: str = "manual_publication",
    cause: BaseException | None = None,
    details: dict[str, Any] | None = None,
) -> CentinelaError:
    return boundary_error(
        code=code,
        category=ErrorCategory.VALIDATION,
        message=message,
        operation="manual_publication.publish_verified_package",
        component=component,
        details=details,
        cause=cause,
    )


def _validated_sha256(value: Any, *, label: str, code: str) -> str:
    normalized = str(value or "").strip().lower()
    try:
        if len(normalized) != 64:
            raise ValueError
        int(normalized, 16)
    except ValueError as exc:
        raise _blocked(
            code,
            f"El SHA-256 de {label} no es válido.",
            cause=exc,
            details={"logical_name": label},
        ) from exc
    return normalized


def _sha256_file(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


def _safe_package_file(package_dir: Path, relative_path: str, logical_name: str) -> Path:
    relative = Path(str(relative_path or "").replace("\\", "/"))
    if not relative.parts or relative.is_absolute() or ".." in relative.parts:
        raise _blocked(
            "publication_package_path_unsafe",
            f"La ruta del asset {logical_name} no es segura.",
            details={"logical_name": logical_name},
        )

    cursor = package_dir
    for part in relative.parts:
        cursor /= part
        if cursor.is_symlink():
            raise _blocked(
                "publication_package_symlink_forbidden",
                f"El asset {logical_name} contiene un enlace simbólico no permitido.",
                details={"logical_name": logical_name},
            )

    try:
        resolved = (package_dir / relative).resolve(strict=True)
        resolved.relative_to(package_dir)
    except (OSError, RuntimeError, ValueError) as exc:
        raise _blocked(
            "publication_package_asset_unavailable",
            f"No se puede verificar el asset {logical_name} del paquete.",
            cause=exc,
            details={"logical_name": logical_name},
        ) from exc
    if not resolved.is_file():
        raise _blocked(
            "publication_package_asset_not_file",
            f"El asset {logical_name} no es un archivo regular.",
            details={"logical_name": logical_name},
        )
    return resolved


def _verify_asset(package_dir: Path, row: dict[str, Any]) -> Path:
    logical_name = str(row.get("logical_name") or "")
    expected_relative = TARGETS.get(logical_name)
    if expected_relative is None or row.get("relative_path") != expected_relative:
        raise _blocked(
            "publication_package_asset_mapping_invalid",
            "El manifest contiene un mapeo de assets no canónico.",
            details={"logical_name": logical_name or "missing"},
        )

    expected_sha = _validated_sha256(
        row.get("sha256"),
        label=logical_name,
        code="publication_package_asset_sha_invalid",
    )
    size_value = row.get("size_bytes")
    if isinstance(size_value, bool) or not isinstance(size_value, int) or size_value < 0:
        raise _blocked(
            "publication_package_asset_size_invalid",
            f"El tamaño declarado de {logical_name} no es válido.",
            details={"logical_name": logical_name},
        )

    path = _safe_package_file(package_dir, expected_relative, logical_name)
    try:
        actual_sha, actual_size = _sha256_file(path)
    except OSError as exc:
        raise _blocked(
            "publication_package_asset_read_failed",
            f"No se pudo releer {logical_name} para verificar su integridad.",
            cause=exc,
            details={"logical_name": logical_name},
        ) from exc

    if actual_sha != expected_sha or actual_size != size_value:
        raise _blocked(
            "publication_package_asset_integrity_mismatch",
            f"La integridad de {logical_name} ha cambiado desde la aprobación.",
            details={"logical_name": logical_name},
        )
    if str(row.get("source_sha256") or "").lower() != expected_sha:
        raise _blocked(
            "publication_package_source_identity_mismatch",
            f"La identidad de origen de {logical_name} no coincide con el paquete aprobado.",
            details={"logical_name": logical_name},
        )
    return path


def _read_json_evidence(path: Path, *, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise _blocked(
            "publication_package_evidence_invalid",
            f"No se puede validar {label} del paquete aprobado.",
            cause=exc,
            details={"logical_name": label},
        ) from exc
    if not isinstance(payload, dict):
        raise _blocked(
            "publication_package_evidence_invalid",
            f"{label} no tiene un formato JSON válido.",
            details={"logical_name": label},
        )
    return payload


def verify_publication_package(
    store: ArtifactStore,
    project_id: str,
) -> VerifiedPublicationPackage:
    """Revalidate the certified package immediately before a manual publication."""
    if AUTO_PUBLICATION:
        raise RuntimeError("AUTO_PUBLICATION invariant was modified")

    try:
        state = ProjectStateMachine(store).current_state(project_id)
    except Exception as exc:
        raise _blocked(
            "publication_project_state_unavailable",
            "No se pudo verificar el estado del proyecto antes de publicar.",
            cause=exc,
        ) from exc
    if state != ProjectState.PUBLICATION_PACKAGE_READY:
        raise _blocked(
            "publication_package_not_ready",
            "El proyecto no está en PUBLICATION_PACKAGE_READY.",
            details={"state": state.value},
        )

    try:
        ref = store.get_latest_artifact(project_id, PUBLICATION_MANIFEST_ARTIFACT_TYPE)
        manifest = store.read_json(project_id, ref.artifact_id, verify_integrity=True)
    except (ArtifactNotFoundError, IntegrityError, OSError, ValueError) as exc:
        raise _blocked(
            "publication_package_manifest_unavailable",
            "No se puede verificar el manifest del paquete de publicación.",
            cause=exc,
        ) from exc
    if not isinstance(manifest, dict):
        raise _blocked(
            "publication_package_manifest_invalid",
            "El manifest del paquete no tiene un formato válido.",
        )

    review_id = str(manifest.get("human_review_artifact_id") or "").strip()
    package_hash = _validated_sha256(
        manifest.get("publication_package_hash"),
        label="publication_package_hash",
        code="publication_package_hash_invalid",
    )
    final_render_id = str(manifest.get("final_render_artifact_id") or "").strip()
    safe_contract = (
        manifest.get("project_id") == project_id
        and manifest.get("asset_count") == 8
        and bool(review_id)
        and bool(final_render_id)
        and manifest.get("source_artifacts_preserved") is True
        and manifest.get("post_review_content_mutation") is False
        and manifest.get("manual_publication_only") is True
        and manifest.get("auto_publication") is False
        and manifest.get("authorization_to_publish") is False
        and manifest.get("marks_published") is False
        and manifest.get("uploads_files") is False
        and manifest.get("webhook_calls") == 0
        and manifest.get("package_network_calls") == 0
        and ref.provenance.get("human_review_artifact_id") == review_id
        and ref.provenance.get("final_render_artifact_id") == final_render_id
        and ref.metadata.get("manual_publication_only") is True
        and ref.metadata.get("auto_publication") is False
        and ref.metadata.get("authorization_to_publish") is False
        and ref.metadata.get("marks_published") is False
        and ref.metadata.get("uploads_files") is False
        and ref.metadata.get("webhook_calls") == 0
        and ref.metadata.get("package_network_calls") == 0
    )
    if not safe_contract:
        raise _blocked(
            "publication_package_safety_contract_invalid",
            "El paquete no conserva el contrato de seguridad aprobado.",
        )

    raw_package_dir = Path(str(ref.provenance.get("package_dir") or ""))
    expected_parent = (store.root / "publication-packages" / project_id).resolve()
    if raw_package_dir.is_symlink():
        raise _blocked(
            "publication_package_root_symlink_forbidden",
            "La carpeta del paquete no puede ser un enlace simbólico.",
        )
    try:
        package_dir = raw_package_dir.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise _blocked(
            "publication_package_root_unavailable",
            "La carpeta materializada del paquete no está disponible.",
            cause=exc,
        ) from exc
    if not package_dir.is_dir() or package_dir.parent != expected_parent:
        raise _blocked(
            "publication_package_root_invalid",
            "La carpeta del paquete no pertenece al proyecto certificado.",
        )

    rows = manifest.get("assets")
    if not isinstance(rows, list) or len(rows) != 8:
        raise _blocked(
            "publication_package_asset_set_invalid",
            "El paquete no contiene los ocho assets contractuales.",
        )
    by_name: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            raise _blocked(
                "publication_package_asset_set_invalid",
                "El manifest contiene una entrada de asset inválida.",
            )
        name = str(row.get("logical_name") or "")
        if name in by_name:
            raise _blocked(
                "publication_package_asset_duplicate",
                "El manifest contiene assets duplicados.",
                details={"logical_name": name},
            )
        by_name[name] = row
    if set(by_name) != set(TARGETS):
        raise _blocked(
            "publication_package_asset_set_invalid",
            "El conjunto de assets no coincide con el contrato G-006.",
        )

    # Re-hash the exact asset that will leave the machine plus the small evidence
    # files that authorize its use. The 4K master is deliberately not reread here
    # because it is not the publication payload and may be very large.
    publish_boundary_assets = (
        "social",
        "thumbnail",
        "subtitles_es",
        "provenance",
        "publication_checklist",
        "caption",
        "metadata",
    )
    verified_paths = {
        name: _verify_asset(package_dir, by_name[name]) for name in publish_boundary_assets
    }

    social_source_id = str(by_name["social"].get("source_artifact_id") or "").strip()
    if not social_source_id:
        raise _blocked(
            "publication_social_source_missing",
            "El vídeo social aprobado no conserva su artifact_id de origen.",
        )
    try:
        social_source = store.get_artifact(project_id, social_source_id)
        social_source_path = store.resolve_artifact_path(project_id, social_source_id)
        if social_source_path.is_symlink() or not social_source_path.is_file():
            raise OSError("canonical social source is not a regular file")
        source_actual_sha, source_actual_size = _sha256_file(social_source_path)
    except (ArtifactNotFoundError, IntegrityError, OSError, ValueError) as exc:
        raise _blocked(
            "publication_social_source_unavailable",
            "No se puede revalidar el artefacto social canónico.",
            cause=exc,
        ) from exc
    social_sha = str(by_name["social"]["sha256"]).lower()
    if (
        social_source.sha256.lower() != social_sha
        or source_actual_sha != social_sha
        or source_actual_size != social_source.size_bytes
    ):
        raise _blocked(
            "publication_social_source_identity_mismatch",
            "El vídeo social materializado ya no coincide con su artefacto canónico.",
        )

    checklist = _read_json_evidence(
        verified_paths["publication_checklist"],
        label="publication_checklist",
    )
    review_payload = checklist.get("review")
    if (
        checklist.get("human_review_artifact_id") != review_id
        or checklist.get("review_7_of_7") is not True
        or checklist.get("auto_publication") is not False
        or not isinstance(review_payload, dict)
        or review_payload.get("rights_passed") is not True
    ):
        raise _blocked(
            "publication_review_evidence_invalid",
            "Review 7/7 y derechos deben seguir aprobados justo antes de publicar.",
        )

    provenance = _read_json_evidence(
        verified_paths["provenance"],
        label="sources-licenses-provenance",
    )
    rights_provenance = provenance.get("rights_provenance")
    if (
        provenance.get("human_review_artifact_id") != review_id
        or not isinstance(rights_provenance, dict)
        or rights_provenance.get("upstream_publication_ready") is not True
        or rights_provenance.get("human_review_rights_passed") is not True
    ):
        raise _blocked(
            "publication_rights_evidence_invalid",
            "La procedencia y los derechos del paquete ya no certifican publicación.",
        )

    try:
        metadata_payload = json.loads(verified_paths["metadata"].read_text(encoding="utf-8"))
        metadata = PublicationMetadata.model_validate(metadata_payload)
        caption = verified_paths["caption"].read_text(encoding="utf-8")
    except (
        OSError,
        UnicodeDecodeError,
        json.JSONDecodeError,
        ValidationError,
    ) as exc:
        raise _blocked(
            "publication_metadata_invalid",
            "Los metadatos aprobados no pueden validarse.",
            cause=exc,
        ) from exc
    if caption != metadata.caption:
        raise _blocked(
            "publication_caption_metadata_mismatch",
            "El caption aprobado no coincide con metadata.json.",
        )

    return VerifiedPublicationPackage(
        project_id=project_id,
        manifest_artifact_id=ref.artifact_id,
        publication_package_hash=package_hash,
        human_review_artifact_id=review_id,
        package_dir=package_dir,
        social_video_path=verified_paths["social"],
        social_video_sha256=social_sha,
        metadata=metadata,
    )


def publish_verified_package(
    store: ArtifactStore,
    project_id: str,
    platform: ManualPublicationPlatform | str,
    *,
    access_token: str,
    approved: bool = False,
    youtube_adapter: YouTubeAdapter | None = None,
    tiktok_adapter: TikTokAdapter | None = None,
) -> SocialResult:
    """Execute one explicit human-approved publication from the certified package."""
    if AUTO_PUBLICATION:
        raise RuntimeError("AUTO_PUBLICATION invariant was modified")
    if not approved:
        raise _blocked(
            "human_approval_required",
            "La publicación requiere aprobación humana explícita en esta acción.",
        )

    try:
        normalized = ManualPublicationPlatform(platform)
    except ValueError as exc:
        raise _blocked(
            "publication_platform_unsupported",
            "La plataforma solicitada no está soportada por el bridge manual.",
            cause=exc,
        ) from exc

    package = verify_publication_package(store, project_id)

    if normalized == ManualPublicationPlatform.INSTAGRAM:
        # Instagram Graph API requires a public HTTPS video URL. Accepting a URL
        # supplied ad hoc here would break package->payload identity. Keep this
        # fail-closed until a temporary hosting adapter can prove the hosted bytes
        # match ``social_video_sha256`` before container creation.
        raise _blocked(
            "instagram_verified_hosting_required",
            "Instagram queda bloqueado hasta disponer de hosting HTTPS temporal con SHA-256 verificable.",
            component="instagram",
        )

    if normalized == ManualPublicationPlatform.YOUTUBE:
        adapter = youtube_adapter or YouTubeAdapter()
        return adapter.upload_private(
            package.social_video_path,
            access_token=access_token,
            title=package.metadata.title,
            description=(package.metadata.youtube_description or package.metadata.caption),
            tags=list(package.metadata.hashtags),
            approved=True,
        )

    adapter = tiktok_adapter or TikTokAdapter()
    return adapter.upload_to_inbox(
        package.social_video_path,
        access_token=access_token,
        approved=True,
    )
