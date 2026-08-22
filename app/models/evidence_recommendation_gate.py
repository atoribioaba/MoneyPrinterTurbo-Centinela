from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.analytics_brain import AnalyticsPlatform
from app.models.experiment_evidence_ledger import ExperimentEvidenceLedgerPlan


EVIDENCE_RECOMMENDATION_GATE_VERSION = "evidence-recommendation-gate-v0.1"


class StrictEvidenceRecommendationModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class EvidenceRecommendationStatus(str, Enum):
    WAITING_FOR_CONFIRMED_EXPERIMENT_RESULTS = "WAITING_FOR_CONFIRMED_EXPERIMENT_RESULTS"
    CANDIDATE_RECOMMENDATIONS_READY = "CANDIDATE_RECOMMENDATIONS_READY"


class EvidenceRecommendationGateRequest(StrictEvidenceRecommendationModel):
    ledger: ExperimentEvidenceLedgerPlan


class CandidateRecommendation(StrictEvidenceRecommendationModel):
    recommendation_id: str
    experiment_id: str
    hypothesis_id: str
    platform: AnalyticsPlatform
    variable: str
    recommended_definition: str
    success_metric: str
    observed_delta: float
    observed_relative_delta: float | None = None
    evidence_class: str = "CONTROLLED_EXPERIMENT_RESULT"
    requires_human_approval: bool = True
    auto_apply: bool = False
    auto_publish: bool = False

    @model_validator(mode="after")
    def validate_recommendation(self):
        if not self.requires_human_approval:
            raise ValueError("recommendations require human approval")
        if self.auto_apply or self.auto_publish:
            raise ValueError("F40 cannot auto-apply or publish")
        return self


class EvidenceRecommendationGatePlan(StrictEvidenceRecommendationModel):
    version: str = EVIDENCE_RECOMMENDATION_GATE_VERSION
    source_experiment_evidence_ledger_hash: str

    deterministic: bool = True
    planning_only: bool = True
    resource_class: str = "LIGHT"

    association_only_recommendations: bool = False
    causal_claims: bool = False
    edits_project: bool = False
    updates_director_policy: bool = False
    auto_apply: bool = False
    auto_publication: bool = False
    uses_llm: bool = False
    network_calls: int = 0

    status: EvidenceRecommendationStatus
    recommendation_count: int = Field(ge=0)
    recommendations: list[CandidateRecommendation]

    evidence_recommendation_gate_hash: str
    generated_at_utc: datetime

    @model_validator(mode="after")
    def validate_plan(self):
        if self.recommendation_count != len(self.recommendations):
            raise ValueError("recommendation_count mismatch")

        expected = (
            EvidenceRecommendationStatus.CANDIDATE_RECOMMENDATIONS_READY
            if self.recommendations
            else EvidenceRecommendationStatus.WAITING_FOR_CONFIRMED_EXPERIMENT_RESULTS
        )
        if self.status != expected:
            raise ValueError("status mismatch")

        if (
            not self.planning_only
            or self.association_only_recommendations
            or self.causal_claims
            or self.edits_project
            or self.updates_director_policy
            or self.auto_apply
            or self.auto_publication
            or self.uses_llm
            or self.network_calls != 0
        ):
            raise ValueError("F40 guardrail violation")
        return self
