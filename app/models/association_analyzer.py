from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.analytics_brain import AnalyticsPlatform
from app.models.metric_normalizer import CanonicalMetric
from app.models.outcome_linker import OutcomeLinkerPlan


ASSOCIATION_ANALYZER_VERSION = "association-analyzer-v0.1"


class StrictAssociationModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class AssociationAnalyzerStatus(str, Enum):
    WAITING_FOR_JOINED_DATA = "WAITING_FOR_JOINED_DATA"
    INSUFFICIENT_SAMPLE = "INSUFFICIENT_SAMPLE"
    ASSOCIATIONS_READY = "ASSOCIATIONS_READY"


class AssociationAnalyzerRequest(StrictAssociationModel):
    joined: OutcomeLinkerPlan
    minimum_sample_size: int = Field(default=5, ge=5, le=1000)


class FeatureOutcomeAssociation(StrictAssociationModel):
    platform: AnalyticsPlatform
    feature_name: str
    canonical_metric: CanonicalMetric
    sample_size: int = Field(ge=5)
    spearman_rho: float = Field(ge=-1.0, le=1.0)
    p_value: float | None = None
    statistical_significance_claimed: bool = False
    causal_claim: bool = False

    @model_validator(mode="after")
    def validate_association(self):
        if self.p_value is not None:
            raise ValueError("F38 V0.1 does not calculate p-values")
        if self.statistical_significance_claimed:
            raise ValueError("F38 V0.1 does not claim significance")
        if self.causal_claim:
            raise ValueError("correlation cannot be promoted to causality")
        return self


class AssociationAnalyzerPlan(StrictAssociationModel):
    version: str = ASSOCIATION_ANALYZER_VERSION
    source_outcome_linker_hash: str

    deterministic: bool = True
    planning_only: bool = True
    resource_class: str = "LIGHT"

    method: str = "SPEARMAN_RANK_CORRELATION"
    cross_platform_pooling: bool = False
    p_values_calculated: bool = False
    statistical_significance_claimed: bool = False
    causal_claims: bool = False
    uses_llm: bool = False
    network_calls: int = 0
    auto_publication: bool = False

    status: AssociationAnalyzerStatus
    candidate_pair_count: int = Field(ge=0)
    association_count: int = Field(ge=0)
    associations: list[FeatureOutcomeAssociation]

    association_analyzer_hash: str
    generated_at_utc: datetime

    @model_validator(mode="after")
    def validate_plan(self):
        if self.association_count != len(self.associations):
            raise ValueError("association_count mismatch")
        if self.status == AssociationAnalyzerStatus.ASSOCIATIONS_READY:
            if not self.associations:
                raise ValueError("ready status requires associations")
        if (
            not self.planning_only
            or self.cross_platform_pooling
            or self.p_values_calculated
            or self.statistical_significance_claimed
            or self.causal_claims
            or self.uses_llm
            or self.network_calls != 0
            or self.auto_publication
        ):
            raise ValueError("F38 guardrail violation")
        return self
