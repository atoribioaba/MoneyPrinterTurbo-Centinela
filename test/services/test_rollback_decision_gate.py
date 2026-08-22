from datetime import datetime, timezone

from app.models.canary_monitor import CanaryMonitorPlan, CanaryMonitorStatus, CanaryMonitorThresholds, CanaryPolicyMonitoringSummary
from app.models.policy_candidate import PolicyTargetComponent
from app.models.policy_registry import PolicyRegistryEntry, PolicyRegistryPlan, PolicyRegistryStatus
from app.models.rollback_decision_gate import RollbackDecision, RollbackDecisionRequest, RollbackGateStatus
from app.services.rollback_decision_gate import build_rollback_decision_plan

NOW = datetime(2026, 8, 22, tzinfo=timezone.utc)


def registry():
    entry = PolicyRegistryEntry(
        policy_version="v1",
        policy_candidate_id="c1",
        approval_record_hash="a1",
        target_component=PolicyTargetComponent.CINEMATIC_DIRECTOR_REQUEST,
        parameter="intensity_bias",
        baseline_value=0.0,
        candidate_value=0.05,
        previous_policy_version=None,
        rollback_target_policy_version=None,
    )
    return PolicyRegistryPlan(
        source_policy_candidate_hash="c",
        source_human_policy_approval_hash="h",
        rollback_metadata_generated=True,
        status=PolicyRegistryStatus.VERSIONED_POLICIES_REGISTERED,
        entry_count=1,
        entries=[entry],
        policy_registry_hash="registry",
        generated_at_utc=NOW,
    )


def monitor(breach):
    summaries = [
        CanaryPolicyMonitoringSummary(
            policy_version="v1",
            observation_count=1,
            total_sample_size=25,
            max_runtime_error_rate=0.01 if breach else 0.0,
            max_quality_gate_failure_rate=0.0,
            scientific_guardrail_violations=0,
            publication_guardrail_violations=0,
            runtime_error_breach=breach,
            quality_gate_breach=False,
            scientific_guardrail_breach=False,
            publication_guardrail_breach=False,
            any_breach=breach,
        )
    ]
    return CanaryMonitorPlan(
        source_canary_policy_hash="canary",
        thresholds=CanaryMonitorThresholds(),
        status=CanaryMonitorStatus.MONITORING_EVIDENCE_READY,
        observation_count=1,
        monitored_policy_count=1,
        breached_policy_count=1 if breach else 0,
        summaries=summaries,
        canary_monitor_hash="monitor",
        generated_at_utc=NOW,
    )


def empty_monitor():
    return CanaryMonitorPlan(
        source_canary_policy_hash="canary",
        thresholds=CanaryMonitorThresholds(),
        status=CanaryMonitorStatus.WAITING_FOR_CANARY_OBSERVATIONS,
        observation_count=0,
        monitored_policy_count=0,
        breached_policy_count=0,
        summaries=[],
        canary_monitor_hash="monitor",
        generated_at_utc=NOW,
    )


def test_waits_without_monitoring_evidence():
    result = build_rollback_decision_plan(
        RollbackDecisionRequest(registry=registry(), monitor=empty_monitor())
    )
    assert result.status == RollbackGateStatus.WAITING_FOR_MONITORING_EVIDENCE


def test_breach_requires_rollback_but_does_not_execute_it():
    result = build_rollback_decision_plan(
        RollbackDecisionRequest(registry=registry(), monitor=monitor(True))
    )
    assert result.decisions[0].decision == RollbackDecision.ROLLBACK_REQUIRED
    assert result.decisions[0].rollback_to_baseline_default is True
    assert result.executes_rollback is False


def test_clean_canary_is_only_eligible_for_promotion_review():
    result = build_rollback_decision_plan(
        RollbackDecisionRequest(registry=registry(), monitor=monitor(False))
    )
    assert result.decisions[0].decision == RollbackDecision.ELIGIBLE_FOR_PROMOTION_REVIEW
    assert result.promotes_policy is False
    assert result.activates_policy is False
