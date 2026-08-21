from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from app.models.audio_mastering import (
    AUDIO_MASTERING_VERSION,
    AudioMasteringPlan,
    AudioMasteringRequest,
)


class AudioMasteringError(RuntimeError):
    pass


def _hash(value: Any) -> str:
    raw = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest().upper()


def build_audio_mastering(request: AudioMasteringRequest) -> AudioMasteringPlan:
    voice = request.voice_studio
    sound = request.sound_design

    if voice.source_plan_context_hash != sound.source_plan_context_hash:
        raise AudioMasteringError("F23/F22 context mismatch")
    if voice.subject != sound.subject:
        raise AudioMasteringError("F23/F22 subject mismatch")
    if voice.scene_count != sound.scene_count:
        raise AudioMasteringError("F23/F22 scene count mismatch")

    stable = {
        "version": AUDIO_MASTERING_VERSION,
        "voice_hash": voice.voice_studio_hash,
        "sound_hash": sound.sound_design_hash,
        "profile": "VOICE_LED_SOCIAL_PROJECT_TARGET",
        "target_i_lufs": -16.0,
        "target_lra_lu": 7.0,
        "target_tp_dbtp": -1.0,
    }

    return AudioMasteringPlan(
        subject=voice.subject,
        source_plan_context_hash=voice.source_plan_context_hash,
        source_voice_studio_hash=voice.voice_studio_hash,
        source_sound_design_hash=sound.sound_design_hash,
        audio_mastering_hash=_hash(stable),
        generated_at_utc=datetime.now(timezone.utc),
    )
