from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from app.models.voice_studio import (
    VOICE_STUDIO_VERSION,
    VoiceStudioPlan,
    VoiceStudioRequest,
    VoiceUtterance,
)


class VoiceStudioError(RuntimeError):
    pass


def _hash(value: Any) -> str:
    raw = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest().upper()


def build_voice_studio(request: VoiceStudioRequest) -> VoiceStudioPlan:
    plan = request.plan
    sound = request.sound_design

    if plan.context_hash != sound.source_plan_context_hash:
        raise VoiceStudioError("F3/F22 context mismatch")
    if plan.subject != sound.subject:
        raise VoiceStudioError("F3/F22 subject mismatch")
    if len(plan.scenes) != sound.scene_count:
        raise VoiceStudioError("F3/F22 scene count mismatch")

    utterances: list[VoiceUtterance] = []
    for scene in plan.scenes:
        terms = []
        seen = set()
        for item in scene.astronomy_objects:
            text = str(item).strip()
            key = text.casefold()
            if text and key not in seen:
                seen.add(key)
                terms.append(text)

        utterances.append(
            VoiceUtterance(
                scene_number=scene.scene_number,
                duration_seconds=float(scene.duration_seconds),
                narration=scene.narration,
                locale=plan.language,
                astronomy_terms=terms,
            )
        )

    stable = {
        "version": VOICE_STUDIO_VERSION,
        "context_hash": plan.context_hash,
        "sound_design_hash": sound.sound_design_hash,
        "utterances": [
            item.model_dump(mode="json")
            for item in utterances
        ],
    }

    return VoiceStudioPlan(
        subject=plan.subject,
        source_plan_context_hash=plan.context_hash,
        source_sound_design_hash=sound.sound_design_hash,
        scene_count=len(utterances),
        voice_selection_required_count=len(utterances),
        utterances=utterances,
        voice_studio_hash=_hash(stable),
        generated_at_utc=datetime.now(timezone.utc),
    )
