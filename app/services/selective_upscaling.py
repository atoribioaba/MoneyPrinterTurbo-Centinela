from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from app.models.selective_upscaling import (
    SELECTIVE_UPSCALING_VERSION,
    SelectiveUpscalingPlan,
    SelectiveUpscalingRequest,
    UpscaleScene,
    UpscaleSceneStatus,
)
from app.models.shot_quality import ShotQualityStatus


class SelectiveUpscalingError(RuntimeError):
    pass


def _hash(value: Any) -> str:
    raw = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest().upper()


def build_selective_upscaling(
    request: SelectiveUpscalingRequest,
) -> SelectiveUpscalingPlan:
    video = request.video_base
    quality = request.shot_quality

    if video.source_plan_context_hash != quality.source_plan_context_hash:
        raise SelectiveUpscalingError("F6/F9 context mismatch")
    if video.scene_count != quality.scene_count:
        raise SelectiveUpscalingError("F6/F9 scene count mismatch")

    quality_by_number = {
        scene.scene_number: scene
        for scene in quality.scenes
    }

    scenes: list[UpscaleScene] = []
    for scene in video.scenes:
        q = quality_by_number.get(scene.scene_number)
        if q is None:
            raise SelectiveUpscalingError("F9 missing F6 scene")

        if scene.placeholder:
            scenes.append(
                UpscaleScene(
                    scene_number=scene.scene_number,
                    status=UpscaleSceneStatus.PLACEHOLDER_NOT_APPLICABLE,
                    source_width=scene.source_width,
                    source_height=scene.source_height,
                    target_width=video.output_width,
                    target_height=video.output_height,
                    warnings=["PLACEHOLDER"],
                )
            )
            continue

        enough = (
            scene.source_width >= video.output_width
            and scene.source_height >= video.output_height
        )
        if enough:
            scenes.append(
                UpscaleScene(
                    scene_number=scene.scene_number,
                    status=UpscaleSceneStatus.NOT_REQUIRED,
                    source_width=scene.source_width,
                    source_height=scene.source_height,
                    target_width=video.output_width,
                    target_height=video.output_height,
                )
            )
            continue

        warnings = [
            "LOWER_THAN_F6_TARGET",
            "A_B_COMPARE_REQUIRED",
            "DO_NOT_INVENT_STARS_OR_FINE_ASTRONOMY_DETAIL",
        ]
        if q.status == ShotQualityStatus.ANALYSIS_FAILED:
            warnings.append("F9_ANALYSIS_FAILED")
        scenes.append(
            UpscaleScene(
                scene_number=scene.scene_number,
                status=UpscaleSceneStatus.A_B_REVIEW_REQUIRED,
                source_width=scene.source_width,
                source_height=scene.source_height,
                target_width=video.output_width,
                target_height=video.output_height,
                candidate_engine="Real-ESRGAN-ncnn-vulkan",
                astronomy_fidelity_review_required=True,
                warnings=warnings,
            )
        )

    stable = {
        "version": SELECTIVE_UPSCALING_VERSION,
        "video_version": video.version,
        "quality_hash": quality.quality_hash,
        "scenes": [
            scene.model_dump(mode="json")
            for scene in scenes
        ],
    }

    def count(status):
        return sum(scene.status == status for scene in scenes)

    return SelectiveUpscalingPlan(
        subject=video.subject,
        source_plan_context_hash=video.source_plan_context_hash,
        source_video_base_version=video.version,
        source_quality_hash=quality.quality_hash,
        scene_count=len(scenes),
        placeholder_count=count(UpscaleSceneStatus.PLACEHOLDER_NOT_APPLICABLE),
        not_required_count=count(UpscaleSceneStatus.NOT_REQUIRED),
        candidate_count=count(UpscaleSceneStatus.A_B_REVIEW_REQUIRED),
        scenes=scenes,
        selective_upscaling_hash=_hash(stable),
        generated_at_utc=datetime.now(timezone.utc),
    )
