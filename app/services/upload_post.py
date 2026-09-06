"""Optional Upload-Post fallback for EL CENTINELA DEL UNIVERSO.

Upload-Post is a third-party freemium aggregation service. It is not the
canonical publication path: direct official YouTube, TikTok and Instagram
adapters live in ``app.services.social_publication``.

Safety invariant:
    GENERAR -> REVISAR -> APROBAR -> PUBLICAR
    AUTO_PUBLICATION = False

Every operation that can upload content requires explicit ``approved=True``.
Configuration alone is never publication approval.
"""

import os
from typing import Optional

import requests
from loguru import logger

from app.config import config


AUTO_PUBLICATION = False
_ALLOWED_YOUTUBE_PRIVACY = frozenset({"private", "unlisted", "public"})
_APPROVAL_ERROR = "Upload-Post fallback requires explicit human approval"


class UploadPostService:
    API_BASE = "https://api.upload-post.com"

    def __init__(self):
        self.api_key = str(config.app.get("upload_post_api_key", "") or "").strip()
        self.username = str(config.app.get("upload_post_username", "") or "").strip()
        self.enabled = bool(config.app.get("upload_post_enabled", False))
        self.platforms = list(
            config.app.get("upload_post_platforms", ["tiktok", "instagram"]) or []
        )

        # Permanent Centinela invariant. Deliberately ignore historical
        # ``upload_post_auto_upload`` configuration values.
        self.auto_upload = AUTO_PUBLICATION

        configured_privacy = str(
            config.app.get("upload_post_youtube_privacy_status", "private") or "private"
        ).strip().lower()
        self.youtube_privacy_status = (
            configured_privacy
            if configured_privacy in _ALLOWED_YOUTUBE_PRIVACY
            else "private"
        )

    def is_configured(self) -> bool:
        return bool(self.api_key and self.username and self.enabled)

    def _safe_error(self, error: object) -> str:
        """Prevent the configured Upload-Post API key from reaching task/UI logs."""
        message = str(error)
        if self.api_key:
            message = message.replace(self.api_key, "***")
        return message

    @staticmethod
    def _require_approval(approved: bool) -> dict | None:
        if AUTO_PUBLICATION:
            raise RuntimeError("AUTO_PUBLICATION invariant was modified")
        if approved is True:
            return None
        logger.warning("Upload-Post publication blocked: explicit human approval is missing")
        return {"success": False, "error": _APPROVAL_ERROR}

    def upload_video(
        self,
        video_path: str,
        title: str,
        platforms: Optional[list] = None,
        privacy_level: str = "PUBLIC_TO_EVERYONE",
        youtube_extra: Optional[dict] = None,
        *,
        approved: bool = False,
    ) -> dict:
        approval_failure = self._require_approval(approved)
        if approval_failure is not None:
            return approval_failure

        if not self.is_configured():
            logger.warning("Upload-Post is not configured. Skipping fallback publication.")
            return {"success": False, "error": "Upload-Post not configured"}

        if platforms is None:
            platforms = self.platforms

        if not os.path.exists(video_path):
            logger.error(f"Video file not found: {video_path}")
            return {"success": False, "error": f"Video file not found: {video_path}"}

        logger.info(
            "Manual Upload-Post fallback approved; publishing to "
            f"{', '.join(platforms)}"
        )

        try:
            with open(video_path, "rb") as video_file:
                files = {"video": video_file}

                data = [
                    ("user", self.username),
                    ("title", title[:2200]),
                    ("privacy_level", privacy_level),
                ]

                for platform in platforms:
                    data.append(("platform[]", platform))

                if youtube_extra and any(p.startswith("youtube") for p in platforms):
                    if "youtube_title" in youtube_extra:
                        data.append(("youtube_title", youtube_extra["youtube_title"][:100]))
                    if "youtube_description" in youtube_extra:
                        data.append(
                            ("youtube_description", youtube_extra["youtube_description"])
                        )
                    for tag in youtube_extra.get("tags", []):
                        data.append(("tags[]", tag))
                    privacy_status = str(
                        youtube_extra.get(
                            "privacyStatus", self.youtube_privacy_status
                        )
                        or self.youtube_privacy_status
                    ).strip().lower()
                    if privacy_status not in _ALLOWED_YOUTUBE_PRIVACY:
                        privacy_status = "private"
                    data.append(("privacyStatus", privacy_status))
                    data.append(("containsSyntheticMedia", "true"))

                headers = {"Authorization": f"Apikey {self.api_key}"}

                response = requests.post(
                    f"{self.API_BASE}/api/upload",
                    headers=headers,
                    data=data,
                    files=files,
                    timeout=300,
                )

                response.raise_for_status()
                result = response.json()

                if result.get("success"):
                    logger.info(
                        "Upload-Post fallback completed successfully; "
                        f"request_id={result.get('request_id')}"
                    )
                else:
                    logger.warning(
                        "Upload-Post fallback failed: "
                        f"{self._safe_error(result.get('message', 'Unknown error'))}"
                    )

                return result

        except requests.exceptions.RequestException as exc:
            safe_error = self._safe_error(exc)
            logger.error(f"Upload-Post fallback request failed: {safe_error}")
            return {"success": False, "error": safe_error}

    def check_status(self, request_id: str) -> dict:
        """Check a previously approved Upload-Post fallback request."""
        try:
            headers = {"Authorization": f"Apikey {self.api_key}"}

            response = requests.get(
                f"{self.API_BASE}/api/uploadposts/status",
                params={"request_id": request_id},
                headers=headers,
                timeout=30,
            )

            response.raise_for_status()
            return response.json()

        except requests.exceptions.RequestException as exc:
            safe_error = self._safe_error(exc)
            logger.error(f"Failed to check Upload-Post status: {safe_error}")
            return {"success": False, "error": safe_error}


upload_post_service = UploadPostService()


def cross_post_video(
    video_path: str,
    title: str,
    platforms: Optional[list] = None,
    youtube_extra: Optional[dict] = None,
    *,
    approved: bool = False,
) -> dict:
    return upload_post_service.upload_video(
        video_path,
        title,
        platforms,
        youtube_extra=youtube_extra,
        approved=approved,
    )
