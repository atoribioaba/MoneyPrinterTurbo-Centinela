from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from app.models.canary_policy_planner import (
    CANARY_POLICY_PLANNER_VERSION,
    CanaryPolicyCandidate,
    CanaryPolicyPlan,
    CanaryPolicyRequest,
    CanaryPolicyStatus,
)


def _hash(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest().upper()


def build_canary_policy_plan(request: CanaryPolicyRequest) -> CanaryPolicyPlan:
    grouped = defaultdict(list)
    for result in request.shadow.results:
        grouped[result.policy_version].append(result)

    candidates = []
    for policy_version in sorted(grouped):
        rows = grouped[policy_version]
        safe_count = sum(item.structural_safe for item in rows)
        behavior_count = sum(item.behavior_changed for item in rows)

        if safe_count != len(rows) or behavior_count == 0:
            continue

        first = rows[0]
        candidates.append(
            CanaryPolicyCandidate(
                policy_version=policy_version,
                policy_candidate_id=first.policy_candidate_id,
                parameter=first.parameter,
                requested_exposure_fraction=request.requested_exposure_fraction,
                shadow_case_count=len(rows),
                shadow_safe_count=safe_count,
                shadow_behavior_change_count=behavior_count,
            )
        )

    if not grouped:
        status = CanaryPolicyStatus.WAITING_FOR_SHADOW_EVIDENCE
    elif candidates:
        status = CanaryPolicyStatus.CANARY_PLANS_READY
    else:
        status = CanaryPolicyStatus.NO_CANARY_ELIGIBLE

    stable = {
        "version": CANARY_POLICY_PLANNER_VERSION,
        "shadow_hash": request.shadow.shadow_policy_hash,
        "requested_exposure_fraction": request.requested_exposure_fraction,
        "candidates": [item.model_dump(mode="json") for item in candidates],
    }

    return CanaryPolicyPlan(
        source_shadow_policy_hash=request.shadow.shadow_policy_hash,
        status=status,
        evaluated_policy_count=len(grouped),
        canary_candidate_count=len(candidates),
        candidates=candidates,
        canary_policy_hash=_hash(stable),
        generated_at_utc=datetime.now(timezone.utc),
    )
