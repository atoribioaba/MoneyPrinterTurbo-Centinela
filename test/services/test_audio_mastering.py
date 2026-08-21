from app.models.audio_mastering import AudioMasteringRequest
from app.models.sound_design import SoundDesignPlan
from app.models.voice_studio import VoiceStudioPlan
from app.services.audio_mastering import build_audio_mastering


def fixture():
    voice = VoiceStudioPlan.model_construct(
        subject="Fixture",
        source_plan_context_hash="ctx",
        source_sound_design_hash="snd",
        scene_count=2,
        voice_studio_hash="voice",
    )
    sound = SoundDesignPlan.model_construct(
        subject="Fixture",
        source_plan_context_hash="ctx",
        scene_count=2,
        sound_design_hash="snd",
    )
    return AudioMasteringRequest.model_construct(
        voice_studio=voice,
        sound_design=sound,
    )


def test_inputs_are_required():
    result = build_audio_mastering(fixture())
    assert result.mastering_ready is False
    assert result.voice_audio_ready is False
    assert result.sound_assets_ready is False


def test_project_target_is_explicit_not_platform_guarantee():
    result = build_audio_mastering(fixture())
    assert result.target_i_lufs == -16.0
    assert result.target_tp_dbtp == -1.0
    assert result.platform_guarantee is False


def test_two_pass_loudnorm_is_planned():
    result = build_audio_mastering(fixture())
    assert "LOUDNORM_TWO_PASS" in result.normalization_method


def test_hash_is_deterministic():
    assert (
        build_audio_mastering(fixture()).audio_mastering_hash
        == build_audio_mastering(fixture()).audio_mastering_hash
    )


def test_guardrails():
    result = build_audio_mastering(fixture())
    assert result.renders_audio is False
    assert result.modifies_audio is False
    assert result.ffmpeg_invocations == 0
