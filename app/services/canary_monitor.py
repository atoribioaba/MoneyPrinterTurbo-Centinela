from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from app.models.canary_monitor import (
    CANARY_MONITOR_VERSION,
    CanaryMonitorPlan,
    CanaryMonitorRequest,
    CanaryMonitorStatus,
    CanaryPolicyMonitoringSummary,
)


class CanaryMonitorError(RuntimeError):
    pass


def _hash(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest().upper()


def build_canary_monitor(request: CanaryMonitorRequest) -> CanaryMonitorPlan:
    eligible = {item.policy_version for item in request.canary.candidates}
    grouped = defaultdict(list)
    seen = set()

    for observation in request.observations:
        if observation.observation_id in seen:
            raise CanaryMonitorError("duplicate observation_id")
        seen.add(observation.observation_id)

        if observation.policy_version not in eligible:
            raise CanaryMonitorError(
                f"observation targets unknown canary policy: {observation.policy_version}"
            )
        grouped[observation.policy_version].append(observation)

    summaries = []
    t = request.thresholds

    for policy_version in sorted(grouped):
        rows = grouped[policy_version]
        runtime_max = max(item.runtime_error_rate for item in rows)
        quality_max = max(item.quality_gate_failure_rate for item in rows)
        scientific = sum(item.scientific_guardrail_violations for item in rows)
        publication = sum(item.publication_guardrail_violations for item in rows)

        runtime_breach = runtime_max > t.max_runtime_error_rate
        quality_breach = quality_max > t.max_quality_gate_failure_rate
        scientific_breach = scientific > t.max_scientific_guardrail_violations
        publication_breach = publication > t.max_publication_guardrail_violations

        summaries.append(
            CanaryPolicyMonitoringSummary(
                policy_version=policy_version,
                observation_count=len(rows),
                total_sample_size=sum(item.sample_size for item in rows),
                max_runtime_error_rate=runtime_max,
                max_quality_gate_failure_rate=quality_max,
                scientific_guardrail_violations=scientific,
                publication_guardrail_violations=publication,
                runtime_error_breach=runtime_breach,
                quality_gate_breach=quality_breach,
                scientific_guardrail_breach=scientific_breach,
                publication_guardrail_breach=publication_breach,
                any_breach=(
                    runtime_breach
                    or quality_breach
                    or scientific_breach
                    or publication_breach
                ),
            )
        )

    stable = {
        "version": CANARY_MONITOR_VERSION,
        "canary_hash": request.canary.canary_policy_hash,
        "thresholds": request.thresholds.model_dump(mode="json"),
        "summaries": [item.model_dump(mode="json") for item in summaries],
    }

    return CanaryMonitorPlan(
        source_canary_policy_hash=request.canary.canary_policy_hash,
        thresholds=request.thresholds,
        status=(
            CanaryMonitorStatus.MONITORING_EVIDENCE_READY
            if summaries
            else CanaryMonitorStatus.WAITING_FOR_CANARY_OBSERVATIONS
        ),
        observation_count=len(request.observations),
        monitored_policy_count=len(summaries),
        breached_policy_count=sum(item.any_breach for item in summaries),
        summaries=summaries,
        canary_monitor_hash=_hash(stable),
        generated_at_utc=datetime.now(timezone.utc),
    )
