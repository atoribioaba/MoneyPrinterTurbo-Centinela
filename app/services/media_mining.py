from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from app.models.astromedia import MediaType
from app.models.media_mining import (
    MEDIA_MINING_VERSION,
    MediaMiningPlan,
    MediaMiningRequest,
    MediaMiningScene,
    MediaMiningStatus,
)
from app.models.shot_quality import ShotQualityStatus


def _hash(value: Any) -> str:
    raw = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest().upper()


def build_media_mining(request: MediaMiningRequest) -> MediaMiningPlan:
    quality = request.shot_quality
    scenes: list[MediaMiningScene] = []

    for source in quality.scenes:
        if source.placeholder or source.status == ShotQualityStatus.NOT_SCORABLE:
            scenes.append(
                MediaMiningScene(
                    scene_number=source.scene_number,
                    source_path=source.source_path,
                    media_type=source.media_type,
                    placeholder=True,
                    status=MediaMiningStatus.PLACEHOLDER_NOT_APPLICABLE,
                    warnings=["PLACEHOLDER"],
                )
            )
            continue

        if source.status == ShotQualityStatus.ANALYSIS_FAILED:
            scenes.append(
                MediaMiningScene(
                    scene_number=source.scene_number,
                    source_path=source.source_path,
                    media_type=source.media_type,
                    placeholder=False,
                    status=MediaMiningStatus.SOURCE_ANALYSIS_FAILED,
                    warnings=["F9_ANALYSIS_FAILED"],
                )
            )
            continue

        if source.media_type == MediaType.IMAGE:
            scenes.append(
                MediaMiningScene(
                    scene_number=source.scene_number,
                    source_path=source.source_path,
                    media_type=source.media_type,
                    placeholder=False,
                    status=MediaMiningStatus.IMAGE_SINGLE_SHOT,
                )
            )
            continue

        if source.media_type == MediaType.VIDEO:
            scenes.append(
                MediaMiningScene(
                    scene_number=source.scene_number,
                    source_path=source.source_path,
                    media_type=source.media_type,
                    placeholder=False,
                    status=MediaMiningStatus.VIDEO_DETECTION_REQUIRED,
                    detector="AdaptiveDetector",
                    scene_detection_required=True,
                    warnings=["PYSCENEDETECT_LOCAL_BENCHMARK_REQUIRED"],
                )
            )
            continue

        scenes.append(
            MediaMiningScene(
                scene_number=source.scene_number,
                source_path=source.source_path,
                media_type=source.media_type,
                placeholder=False,
                status=MediaMiningStatus.SOURCE_ANALYSIS_FAILED,
                warnings=["UNSUPPORTED_MEDIA_TYPE"],
            )
        )

    def count(status):
        return sum(scene.status == status for scene in scenes)

    stable = {
        "version": MEDIA_MINING_VERSION,
        "quality_hash": quality.quality_hash,
        "scenes": [scene.model_dump(mode="json") for scene in scenes],
    }

    return MediaMiningPlan(
        subject=quality.subject,
        source_plan_context_hash=quality.source_plan_context_hash,
        source_quality_hash=quality.quality_hash,
        scene_count=len(scenes),
        placeholder_count=count(MediaMiningStatus.PLACEHOLDER_NOT_APPLICABLE),
        image_single_shot_count=count(MediaMiningStatus.IMAGE_SINGLE_SHOT),
        video_detection_required_count=count(MediaMiningStatus.VIDEO_DETECTION_REQUIRED),
        analysis_failed_count=count(MediaMiningStatus.SOURCE_ANALYSIS_FAILED),
        scenes=scenes,
        media_mining_hash=_hash(stable),
        generated_at_utc=datetime.now(timezone.utc),
    )
