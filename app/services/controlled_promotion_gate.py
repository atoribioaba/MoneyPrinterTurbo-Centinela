from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from app.models.controlled_promotion_gate import (
    CONTROLLED_PROMOTION_GATE_VERSION,
    ControlledPromotionPlan,
    ControlledPromotionRequest,
    ControlledPromotionStatus,
    PromotionAuthorization,
    PromotionDecision,
)
from app.models.rollback_decision_gate import RollbackDecision


class ControlledPromotionGateError(RuntimeError):
    pass


def _hash(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest().upper()


def build_controlled_promotion_plan(
    request: ControlledPromotionRequest,
) -> ControlledPromotionPlan:
    eligible = {
        item.policy_version: item
        for item in request.rollback_gate.decisions
        if item.decision == RollbackDecision.ELIGIBLE_FOR_PROMOTION_REVIEW
    }

    seen = set()
    records = []

    for decision in request.decisions:
        if decision.policy_version in seen:
            raise ControlledPromotionGateError("duplicate promotion decision")
        seen.add(decision.policy_version)

        if decision.policy_version not in eligible:
            raise ControlledPromotionGateError(
                "promotion decision targets policy not eligible for promotion review"
            )

        stable = decision.model_dump(mode="json")
        records.append(
            PromotionAuthorization(
                policy_version=decision.policy_version,
                decision=decision.decision,
                reviewer_ref=decision.reviewer_ref,
                rationale=decision.rationale,
                decided_at_utc=decision.decided_at_utc,
                authorized_for_future_activation=(
                    decision.decision == PromotionDecision.APPROVE
                ),
                promotion_record_hash=_hash(stable),
            )
        )

    records.sort(key=lambda item: item.policy_version)
    authorization_count = sum(item.authorized_for_future_activation for item in records)

    if authorization_count:
        status = ControlledPromotionStatus.PROMOTION_AUTHORIZATIONS_READY
    elif records:
        status = ControlledPromotionStatus.PROMOTION_DECISIONS_RECORDED
    else:
        status = ControlledPromotionStatus.WAITING_FOR_PROMOTION_EVIDENCE

    stable = {
        "version": CONTROLLED_PROMOTION_GATE_VERSION,
        "rollback_hash": request.rollback_gate.rollback_decision_hash,
        "records": [item.model_dump(mode="json") for item in records],
    }

    return ControlledPromotionPlan(
        source_rollback_decision_hash=request.rollback_gate.rollback_decision_hash,
        status=status,
        eligible_policy_count=len(eligible),
        decision_count=len(records),
        authorization_count=authorization_count,
        rejection_count=sum(item.decision == PromotionDecision.REJECT for item in records),
        records=records,
        controlled_promotion_hash=_hash(stable),
        generated_at_utc=datetime.now(timezone.utc),
    )
