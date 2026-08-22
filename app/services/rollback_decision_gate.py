from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from app.models.rollback_decision_gate import (
    ROLLBACK_DECISION_GATE_VERSION,
    PolicyRollbackDecision,
    RollbackDecision,
    RollbackDecisionPlan,
    RollbackDecisionRequest,
    RollbackGateStatus,
)


class RollbackDecisionGateError(RuntimeError):
    pass


def _hash(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest().upper()


def build_rollback_decision_plan(
    request: RollbackDecisionRequest,
) -> RollbackDecisionPlan:
    registry = {item.policy_version: item for item in request.registry.entries}
    decisions = []

    for summary in request.monitor.summaries:
        entry = registry.get(summary.policy_version)
        if entry is None:
            raise RollbackDecisionGateError(
                f"monitor references unknown registry policy: {summary.policy_version}"
            )

        decision = (
            RollbackDecision.ROLLBACK_REQUIRED
            if summary.any_breach
            else RollbackDecision.ELIGIBLE_FOR_PROMOTION_REVIEW
        )

        decisions.append(
            PolicyRollbackDecision(
                policy_version=entry.policy_version,
                decision=decision,
                breach_detected=summary.any_breach,
                rollback_target_policy_version=entry.rollback_target_policy_version,
                rollback_to_baseline_default=entry.rollback_target_policy_version is None,
                baseline_parameter=entry.parameter,
                baseline_value=entry.baseline_value,
            )
        )

    decisions.sort(key=lambda item: item.policy_version)
    stable = {
        "version": ROLLBACK_DECISION_GATE_VERSION,
        "registry_hash": request.registry.policy_registry_hash,
        "monitor_hash": request.monitor.canary_monitor_hash,
        "decisions": [item.model_dump(mode="json") for item in decisions],
    }

    return RollbackDecisionPlan(
        source_policy_registry_hash=request.registry.policy_registry_hash,
        source_canary_monitor_hash=request.monitor.canary_monitor_hash,
        status=(
            RollbackGateStatus.DECISIONS_READY
            if decisions
            else RollbackGateStatus.WAITING_FOR_MONITORING_EVIDENCE
        ),
        decision_count=len(decisions),
        rollback_required_count=sum(
            item.decision == RollbackDecision.ROLLBACK_REQUIRED for item in decisions
        ),
        promotion_review_count=sum(
            item.decision == RollbackDecision.ELIGIBLE_FOR_PROMOTION_REVIEW
            for item in decisions
        ),
        decisions=decisions,
        rollback_decision_hash=_hash(stable),
        generated_at_utc=datetime.now(timezone.utc),
    )
