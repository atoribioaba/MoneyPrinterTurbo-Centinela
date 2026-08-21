from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from app.models.quality_gates import (
    QUALITY_GATES_VERSION,
    QualityGateCheck,
    QualityGatesPlan,
    QualityGatesRequest,
    QualityGateStatus,
)


class QualityGatesError(RuntimeError):
    pass


def _hash(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest().upper()


def build_quality_gates(request: QualityGatesRequest) -> QualityGatesPlan:
    comparator = request.comparator
    sound = request.sound_design
    voice = request.voice_studio
    mastering = request.audio_mastering
    subtitles = request.subtitles

    contexts = {
        comparator.source_plan_context_hash,
        sound.source_plan_context_hash,
        voice.source_plan_context_hash,
        mastering.source_plan_context_hash,
        subtitles.source_plan_context_hash,
    }
    if len(contexts) != 1:
        raise QualityGatesError("F28/F22/F23/F24/F25 context mismatch")

    checks = [
        QualityGateCheck(
            check_id="visual_media_resolved",
            passed=(
                comparator.placeholder_count == 0
                and comparator.failed_count == 0
            ),
            detail=(
                f"placeholders={comparator.placeholder_count}; "
                f"failed={comparator.failed_count}"
            ),
        ),
        QualityGateCheck(
            check_id="enhancement_reviews_resolved",
            passed=comparator.ab_required_count == 0,
            detail=f"ab_required={comparator.ab_required_count}",
        ),
        QualityGateCheck(
            check_id="sound_assets_selected_and_licensed",
            passed=(
                sound.cue_count == 0
                or (
                    sound.asset_count == sound.cue_count
                    and all(cue.publication_eligible for cue in sound.cues)
                )
            ),
            detail=f"cues={sound.cue_count}; assets={sound.asset_count}",
        ),
        QualityGateCheck(
            check_id="voice_selection_complete",
            passed=voice.voice_selection_required_count == 0,
            detail=f"voice_selection_required={voice.voice_selection_required_count}",
        ),
        QualityGateCheck(
            check_id="audio_mastering_ready",
            passed=mastering.mastering_ready,
            detail=f"mastering_ready={mastering.mastering_ready}",
        ),
        QualityGateCheck(
            check_id="subtitle_timing_ready",
            passed=(
                subtitles.waiting_count == 0
                and subtitles.native_ready_count == subtitles.scene_count
            ),
            detail=(
                f"native_ready={subtitles.native_ready_count}; "
                f"waiting={subtitles.waiting_count}"
            ),
        ),
    ]

    ready = all(check.passed for check in checks if check.blocking)
    stable = {
        "version": QUALITY_GATES_VERSION,
        "comparator_hash": comparator.quality_comparator_hash,
        "sound_hash": sound.sound_design_hash,
        "voice_hash": voice.voice_studio_hash,
        "mastering_hash": mastering.audio_mastering_hash,
        "subtitles_hash": subtitles.subtitle_intelligence_hash,
        "checks": [check.model_dump(mode="json") for check in checks],
    }

    return QualityGatesPlan(
        subject=comparator.subject,
        source_plan_context_hash=comparator.source_plan_context_hash,
        source_comparator_hash=comparator.quality_comparator_hash,
        source_sound_design_hash=sound.sound_design_hash,
        source_voice_studio_hash=voice.voice_studio_hash,
        source_audio_mastering_hash=mastering.audio_mastering_hash,
        source_subtitles_hash=subtitles.subtitle_intelligence_hash,
        status=(
            QualityGateStatus.READY_FOR_HUMAN_REVIEW
            if ready
            else QualityGateStatus.BLOCKED
        ),
        check_count=len(checks),
        passed_count=sum(check.passed for check in checks),
        failed_count=sum(not check.passed for check in checks),
        technical_ready=ready,
        publication_eligible_after_human_approval=ready,
        checks=checks,
        quality_gates_hash=_hash(stable),
        generated_at_utc=datetime.now(timezone.utc),
    )
