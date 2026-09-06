"""Official social-platform publication adapters for EL CENTINELA DEL UNIVERSO.

The adapters use the platforms' public HTTP APIs directly and add no paid SaaS
runtime dependency. They never infer approval: every network operation that can
create an upload/publication task requires ``approved=True`` from the caller.

Safety policy:
    GENERAR -> REVISAR -> APROBAR -> PUBLICAR
    AUTO_PUBLICATION = False

Live OAuth/app-review setup is intentionally external to this module. Tokens are
passed at runtime and are never persisted or logged here.
"""

from __future__ import annotations

import math
import mimetypes
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any

import requests

from app.services.error_control import (
    CentinelaError,
    ErrorCategory,
    boundary_error,
    is_retryable_http_status,
    redact_secrets,
    validate_local_media_file,
)

AUTO_PUBLICATION = False
_DEFAULT_TIMEOUT = (15, 120)
_VIDEO_EXTENSIONS = frozenset({".mp4", ".mov", ".webm"})


class SocialPlatform(StrEnum):
    YOUTUBE = "youtube"
    TIKTOK = "tiktok"
    INSTAGRAM = "instagram"


class PublicationMode(StrEnum):
    YOUTUBE_PRIVATE = "youtube_private"
    TIKTOK_INBOX = "tiktok_inbox"
    INSTAGRAM_REEL = "instagram_reel"


@dataclass(slots=True)
class SocialResult:
    success: bool
    platform: SocialPlatform
    mode: PublicationMode
    remote_id: str = ""
    status: str = ""
    requires_user_action: bool = False
    details: dict[str, Any] = field(default_factory=dict)
    error: dict[str, Any] | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "platform": self.platform.value,
            "mode": self.mode.value,
            "remote_id": self.remote_id,
            "status": self.status,
            "requires_user_action": self.requires_user_action,
            "details": self.details,
            "error": self.error,
        }


def _require_approval(*, operation: str, platform: SocialPlatform) -> None:
    if AUTO_PUBLICATION:
        raise RuntimeError("AUTO_PUBLICATION invariant was modified")
    raise boundary_error(
        code="human_approval_required",
        category=ErrorCategory.VALIDATION,
        message="La publicación requiere aprobación humana explícita.",
        operation=operation,
        component=platform.value,
    )


def _require_token(token: str, *, operation: str, platform: SocialPlatform) -> str:
    normalized = str(token or "").strip()
    if not normalized:
        raise boundary_error(
            code="access_token_missing",
            category=ErrorCategory.AUTH,
            message=f"Falta el access token de {platform.value}.",
            operation=operation,
            component=platform.value,
        )
    return normalized


def _request_json(
    session: requests.Session,
    method: str,
    url: str,
    *,
    operation: str,
    platform: SocialPlatform,
    expected_statuses: set[int],
    timeout: tuple[int, int] = _DEFAULT_TIMEOUT,
    **kwargs: Any,
) -> tuple[requests.Response, dict[str, Any]]:
    try:
        response = session.request(method, url, timeout=timeout, **kwargs)
    except (requests.Timeout, requests.ConnectionError) as exc:
        raise boundary_error(
            code="social_network_failure",
            category=ErrorCategory.NETWORK,
            message=f"No se pudo conectar con {platform.value}.",
            operation=operation,
            component=platform.value,
            retryable=True,
            cause=exc,
        ) from exc
    except requests.RequestException as exc:
        raise boundary_error(
            code="social_request_failure",
            category=ErrorCategory.NETWORK,
            message=f"La petición a {platform.value} falló antes de completarse.",
            operation=operation,
            component=platform.value,
            retryable=False,
            cause=exc,
        ) from exc

    try:
        payload = response.json() if response.content else {}
    except ValueError:
        payload = {}

    if response.status_code not in expected_statuses:
        category = ErrorCategory.RATE_LIMIT if response.status_code == 429 else ErrorCategory.UPSTREAM
        if response.status_code in {401, 403}:
            category = ErrorCategory.AUTH
        remote_message = ""
        if isinstance(payload, dict):
            remote_message = str(
                payload.get("message")
                or payload.get("error_description")
                or payload.get("error")
                or ""
            )
        raise boundary_error(
            code=f"{platform.value}_http_{response.status_code}",
            category=category,
            message=(
                f"{platform.value} rechazó la petición con HTTP {response.status_code}. "
                f"{redact_secrets(remote_message)}"
            ).strip(),
            operation=operation,
            component=platform.value,
            retryable=is_retryable_http_status(response.status_code),
            details={"status_code": response.status_code},
        )
    return response, payload if isinstance(payload, dict) else {}


class YouTubeAdapter:
    """YouTube Data API v3 resumable upload using only ``requests``."""

    INIT_URL = "https://www.googleapis.com/upload/youtube/v3/videos"
    MAX_FILE_BYTES = 256 * 1024**3

    def __init__(self, *, session: requests.Session | None = None) -> None:
        self.session = session or requests.Session()

    def upload_private(
        self,
        video_path: str | Path,
        *,
        access_token: str,
        title: str,
        description: str = "",
        tags: list[str] | None = None,
        category_id: str = "28",
        approved: bool = False,
    ) -> SocialResult:
        operation = "youtube.upload_private"
        if not approved:
            _require_approval(operation=operation, platform=SocialPlatform.YOUTUBE)
        token = _require_token(access_token, operation=operation, platform=SocialPlatform.YOUTUBE)
        path = validate_local_media_file(
            video_path,
            operation=operation,
            allowed_extensions=_VIDEO_EXTENSIONS,
            max_size_bytes=self.MAX_FILE_BYTES,
        )
        size = path.stat().st_size
        mime_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        metadata = {
            "snippet": {
                "title": str(title or "").strip()[:100],
                "description": str(description or ""),
                "tags": [str(tag)[:500] for tag in (tags or []) if str(tag).strip()],
                "categoryId": str(category_id),
            },
            # Private is the canonical safe default. Changing visibility is a
            # separate human-controlled action in YouTube Studio/API tooling.
            "status": {"privacyStatus": "private"},
        }
        if not metadata["snippet"]["title"]:
            raise boundary_error(
                code="youtube_title_missing",
                category=ErrorCategory.VALIDATION,
                message="YouTube requiere un título no vacío.",
                operation=operation,
                component="youtube",
            )

        response, _ = _request_json(
            self.session,
            "POST",
            self.INIT_URL,
            operation=f"{operation}.init",
            platform=SocialPlatform.YOUTUBE,
            expected_statuses={200},
            params={"uploadType": "resumable", "part": "snippet,status"},
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json; charset=UTF-8",
                "X-Upload-Content-Length": str(size),
                "X-Upload-Content-Type": mime_type,
            },
            json=metadata,
        )
        upload_url = str(response.headers.get("Location") or "").strip()
        if not upload_url:
            raise boundary_error(
                code="youtube_upload_session_missing",
                category=ErrorCategory.UPSTREAM,
                message="YouTube no devolvió la URL de la sesión resumable.",
                operation=f"{operation}.init",
                component="youtube",
            )

        recoverable_statuses = {500, 502, 503, 504}
        max_resume_attempts = 5

        def confirmed_offset(response: requests.Response) -> int:
            range_header = str(response.headers.get("Range") or "").strip().lower()
            if not range_header:
                return 0
            prefix = "bytes=0-"
            if not range_header.startswith(prefix):
                raise boundary_error(
                    code="youtube_resume_range_invalid",
                    category=ErrorCategory.UPSTREAM,
                    message="YouTube devolvió un Range inválido al reanudar la subida.",
                    operation=f"{operation}.resume",
                    component="youtube",
                )
            try:
                last_byte = int(range_header[len(prefix):])
            except ValueError as exc:
                raise boundary_error(
                    code="youtube_resume_range_invalid",
                    category=ErrorCategory.UPSTREAM,
                    message="YouTube devolvió un Range no numérico al reanudar la subida.",
                    operation=f"{operation}.resume",
                    component="youtube",
                    cause=exc,
                ) from exc
            if last_byte < 0 or last_byte >= size:
                raise boundary_error(
                    code="youtube_resume_range_out_of_bounds",
                    category=ErrorCategory.UPSTREAM,
                    message="YouTube devolvió progreso de subida fuera del tamaño del vídeo.",
                    operation=f"{operation}.resume",
                    component="youtube",
                )
            return last_byte + 1

        def probe_progress() -> requests.Response:
            last_network_error = None
            for probe_attempt in range(max_resume_attempts):
                try:
                    probe = self.session.put(
                        upload_url,
                        headers={
                            "Authorization": f"Bearer {token}",
                            "Content-Length": "0",
                            "Content-Range": f"bytes */{size}",
                        },
                        data=b"",
                        timeout=(15, 120),
                    )
                except (requests.Timeout, requests.ConnectionError) as exc:
                    last_network_error = exc
                    if probe_attempt + 1 < max_resume_attempts:
                        continue
                    raise boundary_error(
                        code="youtube_resume_probe_network_failed",
                        category=ErrorCategory.NETWORK,
                        message="No se pudo consultar el progreso de la subida resumable de YouTube.",
                        operation=f"{operation}.resume_probe",
                        component="youtube",
                        retryable=True,
                        cause=exc,
                    ) from exc
                except requests.RequestException as exc:
                    raise boundary_error(
                        code="youtube_resume_probe_failed",
                        category=ErrorCategory.NETWORK,
                        message="Falló la consulta del progreso de subida de YouTube.",
                        operation=f"{operation}.resume_probe",
                        component="youtube",
                        cause=exc,
                    ) from exc

                if probe.status_code in {200, 201, 308}:
                    return probe
                if probe.status_code in recoverable_statuses and probe_attempt + 1 < max_resume_attempts:
                    continue
                raise boundary_error(
                    code=f"youtube_resume_probe_http_{probe.status_code}",
                    category=ErrorCategory.UPSTREAM,
                    message=f"YouTube devolvió HTTP {probe.status_code} al consultar el progreso.",
                    operation=f"{operation}.resume_probe",
                    component="youtube",
                    retryable=probe.status_code in recoverable_statuses,
                )

            raise boundary_error(
                code="youtube_resume_probe_exhausted",
                category=ErrorCategory.NETWORK,
                message="Se agotaron los intentos de consultar el progreso de YouTube.",
                operation=f"{operation}.resume_probe",
                component="youtube",
                retryable=True,
                cause=last_network_error,
            )

        offset = 0
        payload: dict[str, Any] = {}
        completed = False
        for attempt in range(max_resume_attempts):
            transfer_response = None
            try:
                with path.open("rb") as file_handle:
                    file_handle.seek(offset)
                    remaining = size - offset
                    transfer_headers = {
                        "Authorization": f"Bearer {token}",
                        "Content-Length": str(remaining),
                        "Content-Type": mime_type,
                    }
                    if offset:
                        transfer_headers["Content-Range"] = (
                            f"bytes {offset}-{size - 1}/{size}"
                        )
                    transfer_response = self.session.put(
                        upload_url,
                        headers=transfer_headers,
                        data=file_handle,
                        timeout=(15, 600),
                    )
            except (requests.Timeout, requests.ConnectionError):
                transfer_response = probe_progress()
            except requests.RequestException as exc:
                raise boundary_error(
                    code="youtube_upload_transfer_failed",
                    category=ErrorCategory.NETWORK,
                    message="La transferencia del vídeo a YouTube falló.",
                    operation=f"{operation}.transfer",
                    component="youtube",
                    cause=exc,
                ) from exc
            except OSError as exc:
                raise boundary_error(
                    code="youtube_upload_file_failed",
                    category=ErrorCategory.FILESYSTEM,
                    message="No se pudo leer el vídeo durante la subida a YouTube.",
                    operation=f"{operation}.transfer",
                    component="youtube",
                    cause=exc,
                ) from exc

            if transfer_response.status_code in recoverable_statuses:
                transfer_response = probe_progress()

            if transfer_response.status_code in {200, 201}:
                try:
                    candidate = transfer_response.json() if transfer_response.content else {}
                except ValueError:
                    candidate = {}
                payload = candidate if isinstance(candidate, dict) else {}
                completed = True
                break

            if transfer_response.status_code == 308:
                next_offset = confirmed_offset(transfer_response)
                if next_offset < offset:
                    raise boundary_error(
                        code="youtube_resume_progress_reversed",
                        category=ErrorCategory.UPSTREAM,
                        message="YouTube informó un progreso menor que el ya confirmado.",
                        operation=f"{operation}.resume",
                        component="youtube",
                    )
                offset = next_offset
                continue

            raise boundary_error(
                code=f"youtube_upload_http_{transfer_response.status_code}",
                category=ErrorCategory.UPSTREAM,
                message=f"YouTube devolvió HTTP {transfer_response.status_code} durante la subida.",
                operation=f"{operation}.transfer",
                component="youtube",
                retryable=is_retryable_http_status(transfer_response.status_code),
            )

        if not completed:
            raise boundary_error(
                code="youtube_resume_exhausted",
                category=ErrorCategory.NETWORK,
                message="Se agotaron los intentos de reanudar la subida a YouTube.",
                operation=f"{operation}.resume",
                component="youtube",
                retryable=True,
            )

        video_id = str(payload.get("id") or "") if isinstance(payload, dict) else ""
        return SocialResult(
            success=True,
            platform=SocialPlatform.YOUTUBE,
            mode=PublicationMode.YOUTUBE_PRIVATE,
            remote_id=video_id,
            status="uploaded_private",
            requires_user_action=True,
            details={"privacy_status": "private"},
        )


class TikTokAdapter:
    """TikTok Content Posting API upload-to-inbox flow (scope ``video.upload``)."""

    INIT_URL = "https://open.tiktokapis.com/v2/post/publish/inbox/video/init/"
    MAX_FILE_BYTES = 4 * 1024**3
    MIN_CHUNK_BYTES = 5 * 1024**2
    MAX_CHUNK_BYTES = 64 * 1024**2
    TARGET_CHUNK_BYTES = 32 * 1024**2

    def __init__(self, *, session: requests.Session | None = None) -> None:
        self.session = session or requests.Session()

    @classmethod
    def _chunk_plan(cls, size: int) -> tuple[int, int]:
        if size < cls.MIN_CHUNK_BYTES:
            return size, 1
        if size <= cls.MAX_CHUNK_BYTES:
            return size, 1
        chunk_size = cls.TARGET_CHUNK_BYTES
        chunk_count = size // chunk_size
        if chunk_count < 1:
            chunk_count = 1
        # TikTok defines total_chunk_count as floor(video_size / chunk_size),
        # with trailing bytes merged into the final chunk.
        if chunk_count > 1000:
            chunk_size = math.ceil(size / 1000)
            chunk_size = min(cls.MAX_CHUNK_BYTES, max(cls.MIN_CHUNK_BYTES, chunk_size))
            chunk_count = size // chunk_size
        if not 1 <= chunk_count <= 1000:
            raise ValueError("TikTok chunk plan exceeds platform limits")
        return chunk_size, chunk_count

    def upload_to_inbox(
        self,
        video_path: str | Path,
        *,
        access_token: str,
        approved: bool = False,
    ) -> SocialResult:
        operation = "tiktok.upload_to_inbox"
        if not approved:
            _require_approval(operation=operation, platform=SocialPlatform.TIKTOK)
        token = _require_token(access_token, operation=operation, platform=SocialPlatform.TIKTOK)
        path = validate_local_media_file(
            video_path,
            operation=operation,
            allowed_extensions=_VIDEO_EXTENSIONS,
            max_size_bytes=self.MAX_FILE_BYTES,
        )
        size = path.stat().st_size
        chunk_size, chunk_count = self._chunk_plan(size)
        _, payload = _request_json(
            self.session,
            "POST",
            self.INIT_URL,
            operation=f"{operation}.init",
            platform=SocialPlatform.TIKTOK,
            expected_statuses={200},
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json; charset=UTF-8",
            },
            json={
                "source_info": {
                    "source": "FILE_UPLOAD",
                    "video_size": size,
                    "chunk_size": chunk_size,
                    "total_chunk_count": chunk_count,
                }
            },
        )
        remote_error = payload.get("error") or {}
        if isinstance(remote_error, dict) and remote_error.get("code") not in {None, "", "ok"}:
            raise boundary_error(
                code=f"tiktok_{remote_error.get('code')}",
                category=ErrorCategory.UPSTREAM,
                message=f"TikTok rechazó la inicialización: {remote_error.get('message', '')}",
                operation=f"{operation}.init",
                component="tiktok",
            )
        data = payload.get("data") or {}
        upload_url = str(data.get("upload_url") or "")
        publish_id = str(data.get("publish_id") or "")
        if not upload_url or not publish_id:
            raise boundary_error(
                code="tiktok_upload_session_missing",
                category=ErrorCategory.UPSTREAM,
                message="TikTok no devolvió publish_id/upload_url.",
                operation=f"{operation}.init",
                component="tiktok",
            )

        mime_type = mimetypes.guess_type(path.name)[0] or "video/mp4"
        if mime_type not in {"video/mp4", "video/quicktime", "video/webm"}:
            mime_type = "video/mp4"
        try:
            with path.open("rb") as file_handle:
                first_byte = 0
                for index in range(chunk_count):
                    is_last = index == chunk_count - 1
                    length = size - first_byte if is_last else chunk_size
                    body = file_handle.read(length)
                    if len(body) != length:
                        raise OSError("unexpected EOF while reading TikTok upload chunk")
                    last_byte = first_byte + length - 1
                    response = self.session.put(
                        upload_url,
                        headers={
                            "Content-Type": mime_type,
                            "Content-Length": str(length),
                            "Content-Range": f"bytes {first_byte}-{last_byte}/{size}",
                        },
                        data=body,
                        timeout=(15, 300),
                    )
                    expected = {201} if is_last else {206}
                    if response.status_code not in expected:
                        raise boundary_error(
                            code=f"tiktok_transfer_http_{response.status_code}",
                            category=ErrorCategory.UPSTREAM,
                            message=(
                                "TikTok rechazó un chunk de vídeo con HTTP "
                                f"{response.status_code}."
                            ),
                            operation=f"{operation}.transfer",
                            component="tiktok",
                            retryable=is_retryable_http_status(response.status_code),
                            details={"chunk_index": index, "chunk_count": chunk_count},
                        )
                    first_byte = last_byte + 1
        except CentinelaError:
            raise
        except (OSError, requests.RequestException) as exc:
            raise boundary_error(
                code="tiktok_upload_transfer_failed",
                category=(
                    ErrorCategory.FILESYSTEM
                    if isinstance(exc, OSError)
                    else ErrorCategory.NETWORK
                ),
                message="La transferencia del vídeo a TikTok no se completó.",
                operation=f"{operation}.transfer",
                component="tiktok",
                retryable=isinstance(exc, (requests.Timeout, requests.ConnectionError)),
                cause=exc,
            ) from exc

        return SocialResult(
            success=True,
            platform=SocialPlatform.TIKTOK,
            mode=PublicationMode.TIKTOK_INBOX,
            remote_id=publish_id,
            status="uploaded_to_inbox",
            requires_user_action=True,
            details={
                "instruction": "Abrir la notificación de TikTok para editar y completar el post.",
                "chunk_count": chunk_count,
            },
        )


class InstagramAdapter:
    """Instagram professional-account Reels publishing from a public HTTPS URL."""

    def __init__(
        self,
        *,
        api_version: str = "v26.0",
        host: str = "https://graph.instagram.com",
        session: requests.Session | None = None,
    ) -> None:
        self.api_version = api_version.strip("/")
        self.host = host.rstrip("/")
        self.session = session or requests.Session()

    def create_reel_container(
        self,
        *,
        ig_user_id: str,
        access_token: str,
        video_url: str,
        caption: str = "",
        approved: bool = False,
    ) -> SocialResult:
        operation = "instagram.create_reel_container"
        if not approved:
            _require_approval(operation=operation, platform=SocialPlatform.INSTAGRAM)
        token = _require_token(access_token, operation=operation, platform=SocialPlatform.INSTAGRAM)
        user_id = str(ig_user_id or "").strip()
        url = str(video_url or "").strip()
        if not user_id:
            raise boundary_error(
                code="instagram_user_id_missing",
                category=ErrorCategory.CONFIG,
                message="Falta el ID de la cuenta profesional de Instagram.",
                operation=operation,
                component="instagram",
            )
        if not url.startswith("https://"):
            raise boundary_error(
                code="instagram_public_https_url_required",
                category=ErrorCategory.VALIDATION,
                message="Instagram requiere un video_url HTTPS accesible públicamente.",
                operation=operation,
                component="instagram",
            )
        _, payload = _request_json(
            self.session,
            "POST",
            f"{self.host}/{self.api_version}/{user_id}/media",
            operation=operation,
            platform=SocialPlatform.INSTAGRAM,
            expected_statuses={200},
            headers={"Authorization": f"Bearer {token}"},
            data={
                "media_type": "REELS",
                "video_url": url,
                "caption": str(caption or "")[:2200],
            },
        )
        container_id = str(payload.get("id") or "")
        if not container_id:
            raise boundary_error(
                code="instagram_container_missing",
                category=ErrorCategory.UPSTREAM,
                message="Instagram no devolvió el ID del contenedor del Reel.",
                operation=operation,
                component="instagram",
            )
        return SocialResult(
            success=True,
            platform=SocialPlatform.INSTAGRAM,
            mode=PublicationMode.INSTAGRAM_REEL,
            remote_id=container_id,
            status="container_created",
            requires_user_action=True,
            details={"next_step": "Comprobar FINISHED y aprobar media_publish manualmente."},
        )

    def get_container_status(
        self,
        container_id: str,
        *,
        access_token: str,
    ) -> SocialResult:
        operation = "instagram.get_container_status"
        token = _require_token(access_token, operation=operation, platform=SocialPlatform.INSTAGRAM)
        normalized_id = str(container_id or "").strip()
        if not normalized_id:
            raise boundary_error(
                code="instagram_container_id_missing",
                category=ErrorCategory.VALIDATION,
                message="Falta el ID del contenedor de Instagram.",
                operation=operation,
                component="instagram",
            )
        _, payload = _request_json(
            self.session,
            "GET",
            f"{self.host}/{self.api_version}/{normalized_id}",
            operation=operation,
            platform=SocialPlatform.INSTAGRAM,
            expected_statuses={200},
            headers={"Authorization": f"Bearer {token}"},
            params={"fields": "status_code,status"},
        )
        return SocialResult(
            success=True,
            platform=SocialPlatform.INSTAGRAM,
            mode=PublicationMode.INSTAGRAM_REEL,
            remote_id=normalized_id,
            status=str(payload.get("status_code") or "UNKNOWN"),
            requires_user_action=True,
            details={"remote_status": str(payload.get("status") or "")},
        )

    def publish_reel(
        self,
        *,
        ig_user_id: str,
        container_id: str,
        access_token: str,
        approved: bool = False,
    ) -> SocialResult:
        operation = "instagram.publish_reel"
        if not approved:
            _require_approval(operation=operation, platform=SocialPlatform.INSTAGRAM)
        token = _require_token(access_token, operation=operation, platform=SocialPlatform.INSTAGRAM)
        user_id = str(ig_user_id or "").strip()
        creation_id = str(container_id or "").strip()
        if not user_id or not creation_id:
            raise boundary_error(
                code="instagram_publish_ids_missing",
                category=ErrorCategory.VALIDATION,
                message="Faltan ig_user_id o creation_id para publicar el Reel.",
                operation=operation,
                component="instagram",
            )
        status = self.get_container_status(creation_id, access_token=token)
        if status.status != "FINISHED":
            raise boundary_error(
                code="instagram_container_not_ready",
                category=ErrorCategory.UPSTREAM,
                message=f"El contenedor de Instagram no está listo: {status.status}.",
                operation=operation,
                component="instagram",
                retryable=status.status in {"IN_PROGRESS", "PUBLISHED"},
            )
        _, payload = _request_json(
            self.session,
            "POST",
            f"{self.host}/{self.api_version}/{user_id}/media_publish",
            operation=operation,
            platform=SocialPlatform.INSTAGRAM,
            expected_statuses={200},
            headers={"Authorization": f"Bearer {token}"},
            data={"creation_id": creation_id},
        )
        media_id = str(payload.get("id") or "")
        return SocialResult(
            success=bool(media_id),
            platform=SocialPlatform.INSTAGRAM,
            mode=PublicationMode.INSTAGRAM_REEL,
            remote_id=media_id,
            status="published" if media_id else "unknown",
            requires_user_action=False,
        )


def platform_capabilities() -> list[dict[str, Any]]:
    """Return UI-friendly capability/cost truth without credentials."""
    return [
        {
            "platform": "YouTube",
            "canonical_mode": PublicationMode.YOUTUBE_PRIVATE.value,
            "cost": "0 € de API bajo cuota; requiere proyecto OAuth de Google",
            "default_safety": "Subida privada; publicación/visibilidad se decide después",
            "local_file": True,
        },
        {
            "platform": "TikTok",
            "canonical_mode": PublicationMode.TIKTOK_INBOX.value,
            "cost": "0 € de API; requiere app y scope video.upload",
            "default_safety": "Sube a Inbox; el usuario termina el post en TikTok",
            "local_file": True,
        },
        {
            "platform": "Instagram",
            "canonical_mode": PublicationMode.INSTAGRAM_REEL.value,
            "cost": "0 € de API; requiere cuenta profesional/app Meta",
            "default_safety": "Contenedor + aprobación explícita antes de media_publish",
            "local_file": False,
            "limitation": "video_url HTTPS público (o implementar rupload por separado)",
        },
    ]
