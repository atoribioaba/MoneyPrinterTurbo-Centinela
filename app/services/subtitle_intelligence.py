from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from app.models.subtitle_intelligence import (
    SUBTITLE_INTELLIGENCE_VERSION,
    NativeTimingCue,
    SubtitleIntelligencePlan,
    SubtitleIntelligenceRequest,
    SubtitleScene,
    SubtitleSceneStatus,
)


class SubtitleIntelligenceError(RuntimeError):
    pass


def _hash(value: Any) -> str:
    raw = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest().upper()


def build_subtitle_intelligence(
    request: SubtitleIntelligenceRequest,
) -> SubtitleIntelligencePlan:
    voice = request.voice_studio
    scene_numbers = {item.scene_number for item in voice.utterances}

    grouped: dict[int, list[NativeTimingCue]] = {
        number: [] for number in scene_numbers
    }

    for cue in request.native_timing_cues:
        if cue.scene_number not in scene_numbers:
            raise SubtitleIntelligenceError("native timing cue references unknown scene")
        grouped[cue.scene_number].append(cue)

    scenes: list[SubtitleScene] = []
    for utterance in voice.utterances:
        cues = sorted(
            grouped[utterance.scene_number],
            key=lambda item: (item.start_s, item.end_s),
        )
        for previous, current in zip(cues, cues[1:]):
            if current.start_s < previous.end_s:
                raise SubtitleIntelligenceError("overlapping native TTS cues")

        if cues:
            scenes.append(
                SubtitleScene(
                    scene_number=utterance.scene_number,
                    status=SubtitleSceneStatus.NATIVE_TIMING_READY,
                    cue_count=len(cues),
                    cues=cues,
                    whisper_fallback_required=False,
                )
            )
        else:
            scenes.append(
                SubtitleScene(
                    scene_number=utterance.scene_number,
                    status=SubtitleSceneStatus.WAITING_NATIVE_TTS_TIMESTAMPS,
                    cue_count=0,
                    cues=[],
                    whisper_fallback_required=False,
                )
            )

    stable = {
        "version": SUBTITLE_INTELLIGENCE_VERSION,
        "voice_hash": voice.voice_studio_hash,
        "scenes": [
            scene.model_dump(mode="json")
            for scene in scenes
        ],
    }
    native_ready = sum(
        scene.status == SubtitleSceneStatus.NATIVE_TIMING_READY
        for scene in scenes
    )

    return SubtitleIntelligencePlan(
        subject=voice.subject,
        source_plan_context_hash=voice.source_plan_context_hash,
        source_voice_studio_hash=voice.voice_studio_hash,
        scene_count=len(scenes),
        native_ready_count=native_ready,
        waiting_count=len(scenes) - native_ready,
        cue_count=sum(scene.cue_count for scene in scenes),
        scenes=scenes,
        subtitle_intelligence_hash=_hash(stable),
        generated_at_utc=datetime.now(timezone.utc),
    )
