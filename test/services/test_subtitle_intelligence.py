from datetime import datetime, timezone

import pytest

from app.models.subtitle_intelligence import (
    NativeTimingCue,
    SubtitleIntelligenceRequest,
    SubtitleSceneStatus,
)
from app.models.voice_studio import VoiceStudioPlan, VoiceUtterance
from app.services.subtitle_intelligence import build_subtitle_intelligence


def voice_fixture():
    utterances = [
        VoiceUtterance(
            scene_number=1,
            duration_seconds=10.0,
            narration="La Luna aparece.",
            locale="es-ES",
        ),
        VoiceUtterance(
            scene_number=2,
            duration_seconds=8.0,
            narration="Comienza el crepúsculo.",
            locale="es-ES",
        ),
    ]
    return VoiceStudioPlan(
        subject="Fixture",
        source_plan_context_hash="ctx",
        source_sound_design_hash="snd",
        scene_count=2,
        voice_selection_required_count=2,
        utterances=utterances,
        voice_studio_hash="voice",
        generated_at_utc=datetime.now(timezone.utc),
    )


def test_waits_for_native_timestamps_before_whisper():
    request = SubtitleIntelligenceRequest.model_construct(
        voice_studio=voice_fixture(),
        native_timing_cues=[],
    )
    result = build_subtitle_intelligence(request)
    assert result.waiting_count == 2
    assert result.whisper_triggered is False
    assert result.downloads_models is False


def test_native_timestamps_are_preserved():
    cues = [
        NativeTimingCue(
            scene_number=1,
            start_s=0.0,
            end_s=1.2,
            text="La Luna",
        ),
        NativeTimingCue(
            scene_number=1,
            start_s=1.2,
            end_s=2.0,
            text="aparece.",
        ),
    ]
    request = SubtitleIntelligenceRequest(
        voice_studio=voice_fixture(),
        native_timing_cues=cues,
    )
    result = build_subtitle_intelligence(request)
    assert result.native_ready_count == 1
    scene = result.scenes[0]
    assert scene.status == SubtitleSceneStatus.NATIVE_TIMING_READY
    assert [cue.text for cue in scene.cues] == ["La Luna", "aparece."]


def test_overlapping_native_cues_are_rejected():
    cues = [
        NativeTimingCue(scene_number=1, start_s=0.0, end_s=1.5, text="A"),
        NativeTimingCue(scene_number=1, start_s=1.0, end_s=2.0, text="B"),
    ]
    request = SubtitleIntelligenceRequest(
        voice_studio=voice_fixture(),
        native_timing_cues=cues,
    )
    with pytest.raises(RuntimeError):
        build_subtitle_intelligence(request)


def test_hash_is_deterministic():
    request = SubtitleIntelligenceRequest.model_construct(
        voice_studio=voice_fixture(),
        native_timing_cues=[],
    )
    assert (
        build_subtitle_intelligence(request).subtitle_intelligence_hash
        == build_subtitle_intelligence(request).subtitle_intelligence_hash
    )


def test_guardrails():
    request = SubtitleIntelligenceRequest.model_construct(
        voice_studio=voice_fixture(),
        native_timing_cues=[],
    )
    result = build_subtitle_intelligence(request)
    assert result.whisper_triggered is False
    assert result.transcribes_audio is False
    assert result.gpu_required is False
