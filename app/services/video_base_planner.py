from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

from app.models.astromedia import MediaType
from app.models.material_selection import SelectionStatus
from app.models.video_base import (
    VideoBaseBlockCode,
    VideoBasePlan,
    VideoBasePlanRequest,
    VideoBaseRenderAction,
    VideoBaseRenderMode,
    VideoBaseScenePlan,
)
from app.services.astromedia import AstroMediaCatalog


VIDEO_DURATION_TOLERANCE_SECONDS = 0.05
_SELECTED_STATUSES = {
    SelectionStatus.SELECTED,
    SelectionStatus.MANUAL_OVERRIDE,
    SelectionStatus.SELECTED_AI_RECREATION,
}
_UNRESOLVED_STATUS_TO_CODE = {
    SelectionStatus.NO_ADEQUATE_MEDIA: VideoBaseBlockCode.NO_ADEQUATE_MEDIA,
    SelectionStatus.AI_RECREATION_REQUIRED: VideoBaseBlockCode.AI_RECREATION_REQUIRED,
}


class VideoBasePlanError(RuntimeError):
    pass


class VideoBasePlanBlockedError(VideoBasePlanError):
    def __init__(self, blockers: list[str]):
        self.blockers = list(blockers)
        super().__init__("CLEAN_BASE blocked: " + " | ".join(self.blockers))


def _same_path(left: str, right: str) -> bool:
    return os.path.normcase(os.path.abspath(os.path.normpath(left))) == os.path.normcase(
        os.path.abspath(os.path.normpath(right))
    )


def _source_fingerprint(item) -> str:
    if item.content_sha256:
        return "sha256:" + item.content_sha256
    return f"stat:{item.file_size_bytes}:{item.mtime_ns}"


class VideoBasePlanner:
    """Builds a deterministic render plan from F3 + F5 outputs.

    Critical invariant: only catalog.get(selected_media_id) is allowed. This planner never
    calls search(), list_items(), ranking, providers, SmartFocal, SemanticMatcher or WanGP.
    """

    def __init__(self, catalog=None):
        self.catalog = catalog or AstroMediaCatalog()

    @staticmethod
    def _placeholder_scene(scene, selection, reason, request, warnings=None):
        return VideoBaseScenePlan(
            scene_number=scene.scene_number,
            scene_key=selection.scene_key,
            duration_seconds=float(scene.duration_seconds),
            visual_requirement=scene.visual_requirement,
            narration=scene.narration,
            material_selection_status=selection.status,
            render_action=VideoBaseRenderAction.PLACEHOLDER,
            selected_media_id=selection.selected_media_id,
            source_path=selection.selected_local_path,
            provider=selection.selected_provider,
            rights_status=selection.selected_rights_status,
            publication_eligible=selection.selected_publication_eligible,
            fit_mode=request.default_fit_mode,
            focal_x=request.focal_x,
            focal_y=request.focal_y,
            renderable=True,
            clean_base_eligible=False,
            placeholder=True,
            placeholder_reason=reason,
            warnings=list(warnings or []),
        )

    def _selected_scene(self, scene, selection, request):
        media_id = selection.selected_media_id
        if not media_id:
            return None, VideoBaseBlockCode.MISSING_SELECTION, [
                "selected status without selected_media_id"
            ]

        item = self.catalog.get(media_id)
        if item is None:
            return None, VideoBaseBlockCode.UNKNOWN_MEDIA_ID, [
                f"catalog has no media_id={media_id}"
            ]
        if not item.active:
            return None, VideoBaseBlockCode.INACTIVE_MEDIA, ["catalog item is inactive"]
        if not item.renderable:
            return None, VideoBaseBlockCode.NON_RENDERABLE_MEDIA, [
                item.probe_error or "catalog item is non-renderable"
            ]
        if selection.selected_local_path and not _same_path(
            selection.selected_local_path, item.local_path
        ):
            return None, VideoBaseBlockCode.SOURCE_PATH_MISMATCH, [
                "F5 selected_local_path does not match AstroMedia media_id"
            ]

        source_path = Path(item.local_path)
        if not source_path.is_file():
            return None, VideoBaseBlockCode.MISSING_SOURCE, [
                f"source file missing: {source_path}"
            ]
        current_stat = source_path.stat()
        if (
            int(item.file_size_bytes or 0) != current_stat.st_size
            or int(item.mtime_ns or 0) != current_stat.st_mtime_ns
        ):
            return None, VideoBaseBlockCode.SOURCE_CHANGED, [
                "source file changed since AstroMedia indexing; re-index before rendering"
            ]
        if item.width <= 0 or item.height <= 0:
            return None, VideoBaseBlockCode.INVALID_MEDIA, [
                "source dimensions are not positive"
            ]

        duration = float(scene.duration_seconds)
        if item.media_type == MediaType.VIDEO:
            if item.duration_seconds <= 0:
                return None, VideoBaseBlockCode.INVALID_MEDIA, [
                    "video duration is not positive"
                ]
            if item.duration_seconds + VIDEO_DURATION_TOLERANCE_SECONDS < duration:
                return None, VideoBaseBlockCode.SOURCE_TOO_SHORT, [
                    f"source={item.duration_seconds:.3f}s scene={duration:.3f}s"
                ]
            action = VideoBaseRenderAction.VIDEO
        elif item.media_type == MediaType.IMAGE:
            action = VideoBaseRenderAction.IMAGE
        else:
            return None, VideoBaseBlockCode.INVALID_MEDIA, ["unsupported media_type"]

        warnings = []
        if selection.review_required:
            warnings.append("F5_REVIEW_REQUIRED")
        if selection.selected_publication_eligible is not True:
            warnings.append("NOT_PUBLICATION_ELIGIBLE")

        planned = VideoBaseScenePlan(
            scene_number=scene.scene_number,
            scene_key=selection.scene_key,
            duration_seconds=duration,
            visual_requirement=scene.visual_requirement,
            narration=scene.narration,
            material_selection_status=selection.status,
            render_action=action,
            selected_media_id=item.media_id,
            source_path=item.local_path,
            media_type=item.media_type,
            provider=item.provider,
            rights_status=item.rights_status,
            publication_eligible=item.publication_eligible,
            source_width=item.width,
            source_height=item.height,
            source_rotation_deg=item.rotation_deg,
            source_duration_seconds=item.duration_seconds,
            source_start_s=0.0,
            source_fingerprint=_source_fingerprint(item),
            fit_mode=request.default_fit_mode,
            focal_x=request.focal_x,
            focal_y=request.focal_y,
            renderable=True,
            clean_base_eligible=True,
            placeholder=False,
            warnings=warnings,
        )
        return planned, None, []

    def build(self, request: VideoBasePlanRequest) -> VideoBasePlan:
        plan = request.plan
        materials = request.materials

        if not plan.scenes:
            raise VideoBasePlanError("AstronomyVideoPlan has no scenes")
        if plan.context_hash != materials.source_plan_context_hash:
            raise VideoBasePlanError(
                "AstronomyVideoPlan context_hash does not match MaterialSelectionPlan"
            )
        if len(plan.scenes) != materials.scene_count:
            raise VideoBasePlanError("scene count mismatch between F3 and F5")

        selections = {}
        for selection in materials.selections:
            if selection.scene_number in selections:
                raise VideoBasePlanError(
                    f"duplicate material selection for scene {selection.scene_number}"
                )
            selections[selection.scene_number] = selection

        scene_numbers = [scene.scene_number for scene in plan.scenes]
        if len(scene_numbers) != len(set(scene_numbers)):
            raise VideoBasePlanError("AstronomyVideoPlan contains duplicate scene_number")

        blockers: list[str] = []
        scenes: list[VideoBaseScenePlan] = []
        unresolved_count = 0

        for scene in plan.scenes:
            selection = selections.get(scene.scene_number)
            if selection is None:
                raise VideoBasePlanError(
                    f"MaterialSelectionPlan missing scene {scene.scene_number}"
                )

            if selection.status in _UNRESOLVED_STATUS_TO_CODE:
                unresolved_count += 1
                reason = _UNRESOLVED_STATUS_TO_CODE[selection.status]
                blocker = f"scene {scene.scene_number}: {reason.value}"
                if request.render_mode == VideoBaseRenderMode.CLEAN_BASE:
                    blockers.append(blocker)
                    continue
                scenes.append(self._placeholder_scene(scene, selection, reason, request))
                continue

            if selection.status not in _SELECTED_STATUSES:
                raise VideoBasePlanError(
                    f"unsupported F5 status for scene {scene.scene_number}: {selection.status}"
                )

            planned, failure_code, warnings = self._selected_scene(
                scene, selection, request
            )
            if planned is not None:
                scenes.append(planned)
                continue

            blocker = f"scene {scene.scene_number}: {failure_code.value}"
            if request.render_mode == VideoBaseRenderMode.CLEAN_BASE:
                blockers.append(blocker)
                continue
            scenes.append(
                self._placeholder_scene(
                    scene,
                    selection,
                    failure_code,
                    request,
                    warnings=warnings,
                )
            )

        if blockers:
            # Mandatory gate: no FFmpeg path can be reached from a blocked CLEAN_BASE.
            raise VideoBasePlanBlockedError(blockers)

        placeholder_count = sum(scene.placeholder for scene in scenes)
        clean_base_eligible = len(scenes) == len(plan.scenes) and placeholder_count == 0

        return VideoBasePlan(
            subject=plan.subject,
            source_plan_context_hash=plan.context_hash,
            source_selector_version=materials.selector_version,
            render_mode=request.render_mode,
            requested_codec=request.requested_codec,
            scene_count=len(scenes),
            unresolved_count=unresolved_count,
            placeholder_count=placeholder_count,
            clean_base_eligible=clean_base_eligible,
            source_materials_publication_ready=materials.publication_ready,
            scenes=scenes,
            generated_at_utc=datetime.now(timezone.utc),
        )
