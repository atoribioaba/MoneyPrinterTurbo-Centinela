from datetime import datetime, timezone

import pytest

from app.models.canary_monitor import CanaryMonitorRequest, CanaryMonitorStatus, CanaryObservation
from app.models.canary_policy_planner import CanaryPolicyCandidate, CanaryPolicyPlan, CanaryPolicyStatus
from app.services.canary_monitor import build_canary_monitor

NOW = datetime(2026, 8, 22, tzinfo=timezone.utc)


def canary():
    candidate = CanaryPolicyCandidate(
        policy_version="v1",
        policy_candidate_id="c1",
        parameter="intensity_bias",
        requested_exposure_fraction=0.05,
        shadow_case_count=2,
        shadow_safe_count=2,
        shadow_behavior_change_count=2,
    )
    return CanaryPolicyPlan(
        source_shadow_policy_hash="shadow",
        status=CanaryPolicyStatus.CANARY_PLANS_READY,
        evaluated_policy_count=1,
        canary_candidate_count=1,
        candidates=[candidate],
        canary_policy_hash="canary",
        generated_at_utc=NOW,
    )


def observation(**updates):
    values = dict(
        observation_id="obs-1",
        policy_version="v1",
        human_launch_confirmed=True,
        sample_size=25,
        runtime_error_rate=0.0,
        quality_gate_failure_rate=0.0,
        scientific_guardrail_violations=0,
        publication_guardrail_violations=0,
        observed_at_utc=NOW,
    )
    values.update(updates)
    return CanaryObservation(**values)


def test_waits_without_observations():
    result = build_canary_monitor(CanaryMonitorRequest(canary=canary()))
    assert result.status == CanaryMonitorStatus.WAITING_FOR_CANARY_OBSERVATIONS


def test_clean_observation_has_no_breach():
    result = build_canary_monitor(
        CanaryMonitorRequest(canary=canary(), observations=[observation()])
    )
    assert result.status == CanaryMonitorStatus.MONITORING_EVIDENCE_READY
    assert result.breached_policy_count == 0


def test_runtime_error_is_detected_with_zero_tolerance_default():
    result = build_canary_monitor(
        CanaryMonitorRequest(
            canary=canary(),
            observations=[observation(runtime_error_rate=0.01)],
        )
    )
    assert result.breached_policy_count == 1
    assert result.summaries[0].runtime_error_breach is True


def test_unknown_policy_observation_rejected():
    with pytest.raises(RuntimeError):
        build_canary_monitor(
            CanaryMonitorRequest(
                canary=canary(),
                observations=[observation(policy_version="unknown")],
            )
        )


def test_no_quality_or_causal_claim():
    result = build_canary_monitor(
        CanaryMonitorRequest(canary=canary(), observations=[observation()])
    )
    assert result.quality_improvement_claims is False
    assert result.causal_claims is False
    assert result.executes_rollback is False
