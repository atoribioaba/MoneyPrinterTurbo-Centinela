from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from app.models.quality_comparator import (
    QUALITY_COMPARATOR_VERSION,
    QualityComparatorPlan,
    QualityComparatorRequest,
    QualityComparisonScene,
    QualityComparisonStatus,
)
from app.models.selective_upscaling import UpscaleSceneStatus
from app.models.shot_quality import ShotQualityStatus


class QualityComparatorError(RuntimeError):
    pass


def _hash(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest().upper()


def build_quality_comparator(request: QualityComparatorRequest) -> QualityComparatorPlan:
    quality = request.shot_quality
    upscaling = request.upscaling
    mining = request.media_mining

    hashes = {
        quality.source_plan_context_hash,
        upscaling.source_plan_context_hash,
        mining.source_plan_context_hash,
    }
    if len(hashes) != 1:
        raise QualityComparatorError("F9/F26/F27 context mismatch")
    if len({quality.scene_count, upscaling.scene_count, mining.scene_count}) != 1:
        raise QualityComparatorError("F9/F26/F27 scene count mismatch")

    up_by = {item.scene_number: item for item in upscaling.scenes}
    mining_by = {item.scene_number: item for item in mining.scenes}
    scenes: list[QualityComparisonScene] = []

    for q in quality.scenes:
        up = up_by.get(q.scene_number)
        mine = mining_by.get(q.scene_number)
        if up is None or mine is None:
            raise QualityComparatorError("scene lineage mismatch")

        if q.placeholder or q.status == ShotQualityStatus.NOT_SCORABLE:
            scenes.append(
                QualityComparisonScene(
                    scene_number=q.scene_number,
                    status=QualityComparisonStatus.PLACEHOLDER_NOT_COMPARABLE,
                    warnings=["PLACEHOLDER"],
                )
            )
            continue

        if q.status == ShotQualityStatus.ANALYSIS_FAILED:
            scenes.append(
                QualityComparisonScene(
                    scene_number=q.scene_number,
                    status=QualityComparisonStatus.SOURCE_ANALYSIS_FAILED,
                    warnings=["F9_ANALYSIS_FAILED"],
                )
            )
            continue

        if up.status == UpscaleSceneStatus.A_B_REVIEW_REQUIRED:
            scenes.append(
                QualityComparisonScene(
                    scene_number=q.scene_number,
                    status=QualityComparisonStatus.A_B_COMPARISON_REQUIRED,
                    baseline_score=q.score,
                    candidate_name=up.candidate_engine,
                    human_review_required=True,
                    astronomy_fidelity_required=True,
                    warnings=["NO_WINNER_WITHOUT_A_B_EVIDENCE"],
                )
            )
            continue

        scenes.append(
            QualityComparisonScene(
                scene_number=q.scene_number,
                status=QualityComparisonStatus.BASELINE_ACCEPTED,
                baseline_score=q.score,
            )
        )

    def count(status):
        return sum(scene.status == status for scene in scenes)

    stable = {
        "version": QUALITY_COMPARATOR_VERSION,
        "quality_hash": quality.quality_hash,
        "upscaling_hash": upscaling.selective_upscaling_hash,
        "mining_hash": mining.media_mining_hash,
        "scenes": [scene.model_dump(mode="json") for scene in scenes],
    }

    return QualityComparatorPlan(
        subject=quality.subject,
        source_plan_context_hash=quality.source_plan_context_hash,
        source_quality_hash=quality.quality_hash,
        source_upscaling_hash=upscaling.selective_upscaling_hash,
        source_media_mining_hash=mining.media_mining_hash,
        scene_count=len(scenes),
        placeholder_count=count(QualityComparisonStatus.PLACEHOLDER_NOT_COMPARABLE),
        baseline_accepted_count=count(QualityComparisonStatus.BASELINE_ACCEPTED),
        ab_required_count=count(QualityComparisonStatus.A_B_COMPARISON_REQUIRED),
        failed_count=count(QualityComparisonStatus.SOURCE_ANALYSIS_FAILED),
        scenes=scenes,
        quality_comparator_hash=_hash(stable),
        generated_at_utc=datetime.now(timezone.utc),
    )
