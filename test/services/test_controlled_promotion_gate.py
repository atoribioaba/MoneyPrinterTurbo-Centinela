from datetime import datetime, timezone

import pytest

from app.models.controlled_promotion_gate import (
    ControlledPromotionRequest,
    ControlledPromotionStatus,
    HumanPromotionDecision,
    PromotionDecision,
)
from app.models.rollback_decision_gate import (
    PolicyRollbackDecision,
    RollbackDecision,
    RollbackDecisionPlan,
    RollbackGateStatus,
)
from app.services.controlled_promotion_gate import build_controlled_promotion_plan

NOW = datetime(2026, 8, 22, tzinfo=timezone.utc)


def rollback_gate(decision=RollbackDecision.ELIGIBLE_FOR_PROMOTION_REVIEW):
    item = PolicyRollbackDecision(
        policy_version="v1",
        decision=decision,
        breach_detected=(decision == RollbackDecision.ROLLBACK_REQUIRED),
        rollback_target_policy_version=None,
        rollback_to_baseline_default=True,
        baseline_parameter="intensity_bias",
        baseline_value=0.0,
    )
    return RollbackDecisionPlan(
        source_policy_registry_hash="registry",
        source_canary_monitor_hash="monitor",
        status=RollbackGateStatus.DECISIONS_READY,
        decision_count=1,
        rollback_required_count=1 if decision == RollbackDecision.ROLLBACK_REQUIRED else 0,
        promotion_review_count=1 if decision == RollbackDecision.ELIGIBLE_FOR_PROMOTION_REVIEW else 0,
        decisions=[item],
        rollback_decision_hash="rollback",
        generated_at_utc=NOW,
    )


def human(kind=PromotionDecision.APPROVE):
    return HumanPromotionDecision(
        policy_version="v1",
        decision=kind,
        reviewer_ref="human-reviewer",
        rationale="Canary evidence reviewed.",
        decided_at_utc=NOW,
    )


def test_waits_without_second_human_decision():
    result = build_controlled_promotion_plan(
        ControlledPromotionRequest(rollback_gate=rollback_gate())
    )
    assert result.status == ControlledPromotionStatus.WAITING_FOR_PROMOTION_EVIDENCE


def test_explicit_approval_only_authorizes_future_activation():
    result = build_controlled_promotion_plan(
        ControlledPromotionRequest(
            rollback_gate=rollback_gate(),
            decisions=[human()],
        )
    )
    assert result.status == ControlledPromotionStatus.PROMOTION_AUTHORIZATIONS_READY
    assert result.authorization_count == 1
    assert result.records[0].authorized_for_future_activation is True
    assert result.records[0].activation_executed is False
    assert result.activates_policy is False


def test_explicit_rejection_records_no_authorization():
    result = build_controlled_promotion_plan(
        ControlledPromotionRequest(
            rollback_gate=rollback_gate(),
            decisions=[human(PromotionDecision.REJECT)],
        )
    )
    assert result.status == ControlledPromotionStatus.PROMOTION_DECISIONS_RECORDED
    assert result.authorization_count == 0
    assert result.rejection_count == 1


def test_rollback_required_policy_cannot_be_promoted():
    with pytest.raises(RuntimeError):
        build_controlled_promotion_plan(
            ControlledPromotionRequest(
                rollback_gate=rollback_gate(RollbackDecision.ROLLBACK_REQUIRED),
                decisions=[human()],
            )
        )


def test_f50_never_writes_or_activates():
    result = build_controlled_promotion_plan(
        ControlledPromotionRequest(
            rollback_gate=rollback_gate(),
            decisions=[human()],
        )
    )
    assert result.writes_runtime_config is False
    assert result.auto_apply is False
    assert result.executes_rollback is False
    assert result.auto_publication is False
