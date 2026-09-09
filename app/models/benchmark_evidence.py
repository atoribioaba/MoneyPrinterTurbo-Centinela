from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictBenchmarkModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class BenchmarkOutcome(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    OOM = "OOM"
    NOT_RUN = "NOT_RUN"


class RuntimeMetrics(StrictBenchmarkModel):
    elapsed_seconds: float = Field(gt=0.0)
    peak_ram_mb: float | None = Field(default=None, ge=0.0)
    peak_vram_mb: float | None = Field(default=None, ge=0.0)
    gpu_name: str | None = None
    realtime_factor: float | None = Field(default=None, gt=0.0)
    tokens_per_second: float | None = Field(default=None, gt=0.0)


class ModelIdentity(StrictBenchmarkModel):
    provider: str = Field(min_length=1)
    runtime: str = Field(min_length=1)
    model_id: str = Field(min_length=1)
    model_sha256: str | None = Field(default=None, pattern=r"^[0-9a-fA-F]{64}$")
    quantization: str | None = None
    license_classification: str = Field(min_length=1)
    license_ref: str = Field(min_length=1)


class TTSBenchmarkEvidence(StrictBenchmarkModel):
    benchmark_id: str
    model: ModelIdentity
    voice_id: str
    corpus_sha256: str = Field(pattern=r"^[0-9a-fA-F]{64}$")
    audio_sha256: str | None = Field(default=None, pattern=r"^[0-9a-fA-F]{64}$")
    audio_duration_seconds: float | None = Field(default=None, gt=0.0)
    timestamps_source: str
    metrics: RuntimeMetrics | None = None
    outcome: BenchmarkOutcome
    naturalness_score: float | None = Field(default=None, ge=0.0, le=10.0)
    es_es_accent_score: float | None = Field(default=None, ge=0.0, le=10.0)
    astronomy_pronunciation_score: float | None = Field(default=None, ge=0.0, le=10.0)
    cinematic_prosody_score: float | None = Field(default=None, ge=0.0, le=10.0)
    human_reviewer: str | None = None

    @model_validator(mode="after")
    def passing_audio_requires_artifact_and_human_scores(self):
        if self.outcome == BenchmarkOutcome.PASS:
            if self.audio_sha256 is None or self.metrics is None:
                raise ValueError("PASS TTS benchmark requires audio hash and metrics")
            required = (
                self.naturalness_score,
                self.es_es_accent_score,
                self.astronomy_pronunciation_score,
                self.cinematic_prosody_score,
                self.human_reviewer,
            )
            if any(value is None for value in required):
                raise ValueError("PASS TTS benchmark requires human quality review")
        return self


class LLMBenchmarkEvidence(StrictBenchmarkModel):
    benchmark_id: str
    model: ModelIdentity
    prompt_set_sha256: str = Field(pattern=r"^[0-9a-fA-F]{64}$")
    output_sha256: str | None = Field(default=None, pattern=r"^[0-9a-fA-F]{64}$")
    metrics: RuntimeMetrics | None = None
    outcome: BenchmarkOutcome
    astronomy_questions_total: int = Field(ge=0)
    astronomy_questions_correct: int = Field(ge=0)
    unsupported_claims: int = Field(ge=0)
    factlock_violations: int = Field(ge=0)

    @model_validator(mode="after")
    def counts_must_be_consistent(self):
        if self.astronomy_questions_correct > self.astronomy_questions_total:
            raise ValueError("correct questions cannot exceed total")
        if self.outcome == BenchmarkOutcome.PASS and (
            self.output_sha256 is None or self.metrics is None
        ):
            raise ValueError("PASS LLM benchmark requires output hash and metrics")
        return self


class AIVisualBenchmarkEvidence(StrictBenchmarkModel):
    benchmark_id: str
    model: ModelIdentity
    mode: str
    factlock_sha256: str = Field(pattern=r"^[0-9a-fA-F]{64}$")
    prompt_sha256: str = Field(pattern=r"^[0-9a-fA-F]{64}$")
    output_sha256: str | None = Field(default=None, pattern=r"^[0-9a-fA-F]{64}$")
    metrics: RuntimeMetrics | None = None
    outcome: BenchmarkOutcome
    scientific_label: str = "RECREACION_VISUAL"
    human_fidelity_score: float | None = Field(default=None, ge=0.0, le=10.0)
    artifact_free_score: float | None = Field(default=None, ge=0.0, le=10.0)
    human_reviewer: str | None = None

    @model_validator(mode="after")
    def visual_pass_requires_safe_label_and_review(self):
        if self.scientific_label != "RECREACION_VISUAL":
            raise ValueError("AI visual evidence must remain RECREACION_VISUAL")
        if self.outcome == BenchmarkOutcome.PASS:
            if self.output_sha256 is None or self.metrics is None:
                raise ValueError("PASS AI visual benchmark requires output hash and metrics")
            if (
                self.human_fidelity_score is None
                or self.artifact_free_score is None
                or self.human_reviewer is None
            ):
                raise ValueError("PASS AI visual benchmark requires human review")
        return self
