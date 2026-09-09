import pytest

from app.models.benchmark_evidence import (
    AIVisualBenchmarkEvidence,
    BenchmarkOutcome,
    LLMBenchmarkEvidence,
    ModelIdentity,
    RuntimeMetrics,
    TTSBenchmarkEvidence,
)


_SHA = "a" * 64


def _model():
    return ModelIdentity(
        provider="fixture",
        runtime="fixture-runtime",
        model_id="fixture-model",
        model_sha256=_SHA,
        license_classification="OPEN_SOURCE + 100 % GRATUITA",
        license_ref="fixture-license",
    )


def _metrics():
    return RuntimeMetrics(
        elapsed_seconds=1.0,
        peak_ram_mb=512,
        peak_vram_mb=1024,
        gpu_name="fixture-gpu",
    )


def test_tts_pass_requires_hashed_audio_metrics_and_human_review():
    with pytest.raises(ValueError, match="audio hash and metrics"):
        TTSBenchmarkEvidence(
            benchmark_id="tts",
            model=_model(),
            voice_id="voice",
            corpus_sha256=_SHA,
            timestamps_source="tts-native",
            outcome=BenchmarkOutcome.PASS,
        )

    result = TTSBenchmarkEvidence(
        benchmark_id="tts",
        model=_model(),
        voice_id="voice",
        corpus_sha256=_SHA,
        audio_sha256=_SHA,
        audio_duration_seconds=12.0,
        timestamps_source="tts-native",
        metrics=_metrics(),
        outcome=BenchmarkOutcome.PASS,
        naturalness_score=9.0,
        es_es_accent_score=9.5,
        astronomy_pronunciation_score=9.5,
        cinematic_prosody_score=9.0,
        human_reviewer="reviewer",
    )
    assert result.outcome == BenchmarkOutcome.PASS


def test_llm_counts_and_pass_evidence_are_fail_closed():
    with pytest.raises(ValueError, match="cannot exceed"):
        LLMBenchmarkEvidence(
            benchmark_id="llm",
            model=_model(),
            prompt_set_sha256=_SHA,
            outcome=BenchmarkOutcome.FAIL,
            astronomy_questions_total=10,
            astronomy_questions_correct=11,
            unsupported_claims=0,
            factlock_violations=0,
        )

    with pytest.raises(ValueError, match="output hash and metrics"):
        LLMBenchmarkEvidence(
            benchmark_id="llm",
            model=_model(),
            prompt_set_sha256=_SHA,
            outcome=BenchmarkOutcome.PASS,
            astronomy_questions_total=10,
            astronomy_questions_correct=10,
            unsupported_claims=0,
            factlock_violations=0,
        )


def test_ai_visual_cannot_upgrade_scientific_label():
    with pytest.raises(ValueError, match="RECREACION_VISUAL"):
        AIVisualBenchmarkEvidence(
            benchmark_id="visual",
            model=_model(),
            mode="text_to_image",
            factlock_sha256=_SHA,
            prompt_sha256=_SHA,
            outcome=BenchmarkOutcome.NOT_RUN,
            scientific_label="HECHO_VERIFICADO",
        )


def test_ai_visual_pass_requires_hash_metrics_and_human_review():
    result = AIVisualBenchmarkEvidence(
        benchmark_id="visual",
        model=_model(),
        mode="image_to_video",
        factlock_sha256=_SHA,
        prompt_sha256=_SHA,
        output_sha256=_SHA,
        metrics=_metrics(),
        outcome=BenchmarkOutcome.PASS,
        scientific_label="RECREACION_VISUAL",
        human_fidelity_score=9.5,
        artifact_free_score=9.0,
        human_reviewer="reviewer",
    )
    assert result.scientific_label == "RECREACION_VISUAL"
