from app.models.astronomy_director import AstronomyVideoPlan, ScenePlan
from app.models.sound_design import SoundDesignPlan
from app.models.voice_studio import VoiceStudioRequest
from app.services.voice_studio import build_voice_studio


def fixture():
    scenes = [
        ScenePlan.model_construct(
            scene_number=1,
            duration_seconds=10,
            narration="La Luna emerge sobre el horizonte.",
            astronomy_objects=["Luna", "Luna"],
        ),
        ScenePlan.model_construct(
            scene_number=2,
            duration_seconds=8,
            narration="El cielo entra en el crepúsculo.",
            astronomy_objects=[],
        ),
    ]
    plan = AstronomyVideoPlan.model_construct(
        subject="Fixture",
        language="es-ES",
        context_hash="ctx",
        scenes=scenes,
    )
    sound = SoundDesignPlan.model_construct(
        subject="Fixture",
        source_plan_context_hash="ctx",
        scene_count=2,
        sound_design_hash="snd",
    )
    return VoiceStudioRequest.model_construct(plan=plan, sound_design=sound)


def test_requires_explicit_voice_selection():
    result = build_voice_studio(fixture())
    assert result.voice_selection_required_count == 2
    assert all(item.exact_voice_id is None for item in result.utterances)


def test_native_timestamps_are_first_policy():
    result = build_voice_studio(fixture())
    assert all(
        item.timestamp_policy.value == "TTS_NATIVE_BOUNDARIES_FIRST"
        for item in result.utterances
    )


def test_astronomy_terms_are_deduplicated():
    result = build_voice_studio(fixture())
    assert result.utterances[0].astronomy_terms == ["Luna"]


def test_hash_is_deterministic():
    assert (
        build_voice_studio(fixture()).voice_studio_hash
        == build_voice_studio(fixture()).voice_studio_hash
    )


def test_guardrails():
    result = build_voice_studio(fixture())
    assert result.generates_audio is False
    assert result.tts_invocations == 0
    assert result.network_calls == 0
    assert result.downloads_models is False
