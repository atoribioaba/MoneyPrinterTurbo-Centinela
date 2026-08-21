from app.models.audio_mastering import AudioMasteringPlan
from app.models.quality_comparator import QualityComparatorPlan
from app.models.quality_gates import QualityGatesRequest, QualityGateStatus
from app.models.sound_design import SoundDesignPlan
from app.models.subtitle_intelligence import SubtitleIntelligencePlan
from app.models.voice_studio import VoiceStudioPlan
from app.services.quality_gates import build_quality_gates


def fixture(blocked=True):
    comparator = QualityComparatorPlan.model_construct(
        subject="Fixture",
        source_plan_context_hash="ctx",
        placeholder_count=1 if blocked else 0,
        failed_count=0,
        ab_required_count=0,
        quality_comparator_hash="cmp",
    )
    sound = SoundDesignPlan.model_construct(
        source_plan_context_hash="ctx",
        cue_count=0,
        asset_count=0,
        cues=[],
        sound_design_hash="snd",
    )
    voice = VoiceStudioPlan.model_construct(
        source_plan_context_hash="ctx",
        voice_selection_required_count=1 if blocked else 0,
        voice_studio_hash="voice",
    )
    mastering = AudioMasteringPlan.model_construct(
        source_plan_context_hash="ctx",
        mastering_ready=not blocked,
        audio_mastering_hash="master",
    )
    subtitles = SubtitleIntelligencePlan.model_construct(
        source_plan_context_hash="ctx",
        scene_count=1,
        native_ready_count=0 if blocked else 1,
        waiting_count=1 if blocked else 0,
        subtitle_intelligence_hash="sub",
    )
    return QualityGatesRequest.model_construct(
        comparator=comparator,
        sound_design=sound,
        voice_studio=voice,
        audio_mastering=mastering,
        subtitles=subtitles,
    )


def test_blocked_state():
    result = build_quality_gates(fixture(True))
    assert result.status == QualityGateStatus.BLOCKED
    assert result.technical_ready is False


def test_ready_still_requires_human_approval():
    result = build_quality_gates(fixture(False))
    assert result.status == QualityGateStatus.READY_FOR_HUMAN_REVIEW
    assert result.technical_ready is True
    assert result.human_approval_required is True
    assert result.auto_publication is False


def test_hash_deterministic():
    assert (
        build_quality_gates(fixture(True)).quality_gates_hash
        == build_quality_gates(fixture(True)).quality_gates_hash
    )


def test_guardrails():
    result = build_quality_gates(fixture(True))
    assert result.renders_media is False
    assert result.modifies_media is False
    assert result.auto_publication is False
