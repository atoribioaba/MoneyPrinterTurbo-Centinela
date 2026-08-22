from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.analytics_brain import AnalyticsPlatform
from app.models.experiment_planner import ExperimentPlannerPlan


EXPERIMENT_EVIDENCE_LEDGER_VERSION = "experiment-evidence-ledger-v0.1"


class StrictExperimentEvidenceModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class ExperimentEvidenceStatus(str, Enum):
    WAITING_FOR_EXPERIMENT_RESULTS = "WAITING_FOR_EXPERIMENT_RESULTS"
    RESULTS_RECORDED = "RESULTS_RECORDED"


class ExperimentResultInput(StrictExperimentEvidenceModel):
    experiment_id: str = Field(min_length=1, max_length=128)
    hypothesis_id: str = Field(min_length=1, max_length=128)
    platform: AnalyticsPlatform
    success_metric: str = Field(min_length=1, max_length=128)

    control_n: int = Field(ge=1)
    variant_n: int = Field(ge=1)
    control_metric_mean: float
    variant_metric_mean: float
    higher_is_better: bool = True

    randomized_assignment_confirmed: bool = False
    same_measurement_window_confirmed: bool = False
    human_reviewed: bool = False
    notes: str | None = Field(default=None, max_length=1500)


class ExperimentEvidenceLedgerRequest(StrictExperimentEvidenceModel):
    planner: ExperimentPlannerPlan
    results: list[ExperimentResultInput] = Field(default_factory=list)


class ExperimentEvidenceRecord(StrictExperimentEvidenceModel):
    experiment_id: str
    hypothesis_id: str
    platform: AnalyticsPlatform
    variable: str
    control_definition: str
    variant_definition: str
    success_metric: str

    control_n: int
    variant_n: int
    control_metric_mean: float
    variant_metric_mean: float
    observed_delta: float
    observed_relative_delta: float | None = None
    higher_is_better: bool

    randomized_assignment_confirmed: bool
    same_measurement_window_confirmed: bool
    human_reviewed: bool

    eligible_for_recommendation_review: bool
    causal_claim: bool = False
    statistical_significance_claimed: bool = False

    @model_validator(mode="after")
    def validate_record(self):
        if self.causal_claim:
            raise ValueError("F39 does not make automatic causal claims")
        if self.statistical_significance_claimed:
            raise ValueError("F39 V0.1 does not claim statistical significance")
        expected = (
            self.randomized_assignment_confirmed
            and self.same_measurement_window_confirmed
            and self.human_reviewed
        )
        if self.eligible_for_recommendation_review != expected:
            raise ValueError("recommendation eligibility mismatch")
        return self


class ExperimentEvidenceLedgerPlan(StrictExperimentEvidenceModel):
    version: str = EXPERIMENT_EVIDENCE_LEDGER_VERSION
    source_experiment_planner_hash: str

    deterministic: bool = True
    planning_only: bool = True
    resource_class: str = "LIGHT"

    runs_experiments: bool = False
    calculates_p_values: bool = False
    causal_claims: bool = False
    database_writes: int = 0
    network_calls: int = 0
    auto_apply: bool = False
    auto_publication: bool = False

    status: ExperimentEvidenceStatus
    result_count: int = Field(ge=0)
    eligible_result_count: int = Field(ge=0)
    records: list[ExperimentEvidenceRecord]

    experiment_evidence_ledger_hash: str
    generated_at_utc: datetime

    @model_validator(mode="after")
    def validate_plan(self):
        if self.result_count != len(self.records):
            raise ValueError("result_count mismatch")
        if self.eligible_result_count != sum(
            item.eligible_for_recommendation_review for item in self.records
        ):
            raise ValueError("eligible_result_count mismatch")

        expected = (
            ExperimentEvidenceStatus.RESULTS_RECORDED
            if self.records
            else ExperimentEvidenceStatus.WAITING_FOR_EXPERIMENT_RESULTS
        )
        if self.status != expected:
            raise ValueError("status mismatch")

        if (
            not self.planning_only
            or self.runs_experiments
            or self.calculates_p_values
            or self.causal_claims
            or self.database_writes != 0
            or self.network_calls != 0
            or self.auto_apply
            or self.auto_publication
        ):
            raise ValueError("F39 guardrail violation")
        return self
