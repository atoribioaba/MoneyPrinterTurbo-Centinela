from datetime import datetime, timezone

from app.models.canary_policy_planner import CanaryPolicyRequest, CanaryPolicyStatus
from app.models.shadow_policy_evaluator import ShadowPolicyPlan, ShadowPolicyResult, ShadowPolicyStatus
from app.services.canary_policy_planner import build_canary_policy_plan

NOW = datetime(2026, 8, 22, tzinfo=timezone.utc)


def shadow(rows):
    return ShadowPolicyPlan(
        source_policy_registry_hash="registry",
        status=ShadowPolicyStatus.SHADOW_RESULTS_READY if rows else ShadowPolicyStatus.WAITING_FOR_REGISTERED_POLICY_AND_CASES,
        registered_policy_count=1 if rows else 0,
        case_count=len(rows),
        evaluation_count=len(rows),
        safe_evaluation_count=sum(x.structural_safe for x in rows),
        behavior_change_count=sum(x.behavior_changed for x in rows),
        results=rows,
        shadow_policy_hash="shadow",
        generated_at_utc=NOW,
    )


def row(safe=True, changed=True):
    return ShadowPolicyResult(
        policy_version="v1",
        policy_candidate_id="c1",
        case_id="case-1",
        parameter="intensity_bias",
        baseline_direction_hash="a",
        candidate_direction_hash="b" if changed else "a",
        behavior_changed=changed,
        baseline_structural_checks_pass=True,
        candidate_structural_checks_pass=safe,
        placeholders_preserved=safe,
        structural_safe=safe,
    )


def test_waits_without_shadow_results():
    result = build_canary_policy_plan(CanaryPolicyRequest(shadow=shadow([])))
    assert result.status == CanaryPolicyStatus.WAITING_FOR_SHADOW_EVIDENCE


def test_safe_changed_shadow_becomes_canary_candidate():
    result = build_canary_policy_plan(CanaryPolicyRequest(shadow=shadow([row()])))
    assert result.status == CanaryPolicyStatus.CANARY_PLANS_READY
    assert result.canary_candidate_count == 1
    assert result.candidates[0].requires_human_launch is True
    assert result.candidates[0].launched is False


def test_unsafe_shadow_is_not_canary_eligible():
    result = build_canary_policy_plan(CanaryPolicyRequest(shadow=shadow([row(safe=False)])))
    assert result.status == CanaryPolicyStatus.NO_CANARY_ELIGIBLE


def test_canary_never_executes_or_activates():
    result = build_canary_policy_plan(CanaryPolicyRequest(shadow=shadow([row()])))
    assert result.executes_canary is False
    assert result.activates_policy is False
    assert result.writes_runtime_config is False
