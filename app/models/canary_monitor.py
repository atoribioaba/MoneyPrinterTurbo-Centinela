from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.canary_policy_planner import CanaryPolicyPlan


CANARY_MONITOR_VERSION = "canary-monitor-v0.1"


class StrictCanaryMonitorModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class CanaryMonitorStatus(str, Enum):
    WAITING_FOR_CANARY_OBSERVATIONS = "WAITING_FOR_CANARY_OBSERVATIONS"
    MONITORING_EVIDENCE_READY = "MONITORING_EVIDENCE_READY"


class CanaryMonitorThresholds(StrictCanaryMonitorModel):
    max_runtime_error_rate: float = Field(default=0.0, ge=0.0, le=1.0)
    max_quality_gate_failure_rate: float = Field(default=0.0, ge=0.0, le=1.0)
    max_scientific_guardrail_violations: int = Field(default=0, ge=0)
    max_publication_guardrail_violations: int = Field(default=0, ge=0)


class CanaryObservation(StrictCanaryMonitorModel):
    observation_id: str = Field(min_length=1, max_length=128)
    policy_version: str = Field(min_length=1, max_length=128)
    human_launch_confirmed: bool = True

    sample_size: int = Field(ge=1)
    runtime_error_rate: float = Field(ge=0.0, le=1.0)
    quality_gate_failure_rate: float = Field(ge=0.0, le=1.0)
    scientific_guardrail_violations: int = Field(ge=0)
    publication_guardrail_violations: int = Field(ge=0)

    observed_at_utc: datetime

    @model_validator(mode="after")
    def validate_observation(self):
        if not self.human_launch_confirmed:
            raise ValueError("F48 observations require confirmed human canary launch")
        return self


class CanaryMonitorRequest(StrictCanaryMonitorModel):
    canary: CanaryPolicyPlan
    thresholds: CanaryMonitorThresholds = Field(default_factory=CanaryMonitorThresholds)
    observations: list[CanaryObservation] = Field(default_factory=list)


class CanaryPolicyMonitoringSummary(StrictCanaryMonitorModel):
    policy_version: str
    observation_count: int = Field(ge=1)
    total_sample_size: int = Field(ge=1)

    max_runtime_error_rate: float = Field(ge=0.0, le=1.0)
    max_quality_gate_failure_rate: float = Field(ge=0.0, le=1.0)
    scientific_guardrail_violations: int = Field(ge=0)
    publication_guardrail_violations: int = Field(ge=0)

    runtime_error_breach: bool
    quality_gate_breach: bool
    scientific_guardrail_breach: bool
    publication_guardrail_breach: bool
    any_breach: bool

    quality_improvement_claimed: bool = False
    causal_claim: bool = False


class CanaryMonitorPlan(StrictCanaryMonitorModel):
    version: str = CANARY_MONITOR_VERSION
    source_canary_policy_hash: str

    deterministic: bool = True
    descriptive_only: bool = True
    resource_class: str = "LIGHT"

    launches_canary: bool = False
    executes_rollback: bool = False
    activates_policy: bool = False
    writes_runtime_config: bool = False
    quality_improvement_claims: bool = False
    causal_claims: bool = False
    uses_llm: bool = False
    network_calls: int = 0
    database_writes: int = 0
    auto_publication: bool = False

    thresholds: CanaryMonitorThresholds
    status: CanaryMonitorStatus
    observation_count: int = Field(ge=0)
    monitored_policy_count: int = Field(ge=0)
    breached_policy_count: int = Field(ge=0)
    summaries: list[CanaryPolicyMonitoringSummary]

    canary_monitor_hash: str
    generated_at_utc: datetime

    @model_validator(mode="after")
    def validate_plan(self):
        if self.observation_count < len(self.summaries):
            raise ValueError("observation_count invalid")
        if self.monitored_policy_count != len(self.summaries):
            raise ValueError("monitored_policy_count mismatch")
        if self.breached_policy_count != sum(item.any_breach for item in self.summaries):
            raise ValueError("breached_policy_count mismatch")

        expected = (
            CanaryMonitorStatus.MONITORING_EVIDENCE_READY
            if self.summaries
            else CanaryMonitorStatus.WAITING_FOR_CANARY_OBSERVATIONS
        )
        if self.status != expected:
            raise ValueError("status mismatch")

        if (
            not self.descriptive_only
            or self.launches_canary
            or self.executes_rollback
            or self.activates_policy
            or self.writes_runtime_config
            or self.quality_improvement_claims
            or self.causal_claims
            or self.uses_llm
            or self.network_calls != 0
            or self.database_writes != 0
            or self.auto_publication
        ):
            raise ValueError("F48 guardrail violation")
        return self
