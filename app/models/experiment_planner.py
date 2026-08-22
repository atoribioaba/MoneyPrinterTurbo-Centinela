from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.performance_signals import PerformanceSignalsPlan
from app.models.retention_intelligence import RetentionIntelligencePlan


EXPERIMENT_PLANNER_VERSION = "experiment-planner-v0.1"


class StrictExperimentModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class ExperimentPlannerStatus(str, Enum):
    WAITING_FOR_EVIDENCE = "WAITING_FOR_EVIDENCE"
    CANDIDATE_EXPERIMENTS_READY = "CANDIDATE_EXPERIMENTS_READY"


class ExperimentHypothesis(StrictExperimentModel):
    hypothesis_id: str = Field(min_length=1, max_length=128)
    variable: str = Field(min_length=1, max_length=128)
    rationale: str = Field(min_length=1, max_length=1024)
    evidence_refs: list[str] = Field(min_length=1, max_length=20)
    control_definition: str = Field(min_length=1, max_length=1024)
    variant_definition: str = Field(min_length=1, max_length=1024)
    success_metric: str = Field(min_length=1, max_length=128)
    changes_one_variable_only: bool = True
    auto_apply: bool = False
    auto_publish: bool = False

    @model_validator(mode="after")
    def validate_hypothesis(self):
        if not self.changes_one_variable_only:
            raise ValueError("experiment must isolate one variable")
        if self.auto_apply or self.auto_publish:
            raise ValueError("experiments require explicit human execution")
        return self


class ExperimentPlannerRequest(StrictExperimentModel):
    performance: PerformanceSignalsPlan
    retention: RetentionIntelligencePlan
    candidate_hypotheses: list[ExperimentHypothesis] = Field(default_factory=list)


class ExperimentPlannerPlan(StrictExperimentModel):
    version: str = EXPERIMENT_PLANNER_VERSION
    source_performance_hash: str
    source_retention_hash: str
    deterministic: bool = True
    planning_only: bool = True
    resource_class: str = "LIGHT"

    causal_claims: bool = False
    edits_project: bool = False
    runs_experiments: bool = False
    publishes_content: bool = False
    uses_llm: bool = False
    network_calls: int = 0

    status: ExperimentPlannerStatus
    evidence_sufficient: bool
    hypothesis_count: int = Field(ge=0)
    hypotheses: list[ExperimentHypothesis]

    experiment_planner_hash: str
    generated_at_utc: datetime

    @model_validator(mode="after")
    def validate_plan(self):
        if self.hypothesis_count != len(self.hypotheses):
            raise ValueError("hypothesis_count mismatch")
        if self.status == ExperimentPlannerStatus.CANDIDATE_EXPERIMENTS_READY:
            if not self.evidence_sufficient or not self.hypotheses:
                raise ValueError("ready experiments require evidence and hypotheses")
        if self.status == ExperimentPlannerStatus.WAITING_FOR_EVIDENCE and self.hypotheses:
            raise ValueError("waiting plan cannot expose executable hypotheses")
        if (
            not self.planning_only
            or self.causal_claims
            or self.edits_project
            or self.runs_experiments
            or self.publishes_content
            or self.uses_llm
            or self.network_calls != 0
        ):
            raise ValueError("F35 guardrail violation")
        return self
