from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from app.models.cinematic_director import CinematicDirectorRequest
from app.models.policy_candidate import PolicyTargetComponent
from app.models.shadow_policy_evaluator import (
    SHADOW_POLICY_EVALUATOR_VERSION,
    ShadowPolicyPlan,
    ShadowPolicyRequest,
    ShadowPolicyResult,
    ShadowPolicyStatus,
)
from app.services.cinematic_director import CinematicDirector


class ShadowPolicyEvaluatorError(RuntimeError):
    pass


SUPPORTED_PARAMETERS = {
    "intensity_bias": ("float", -0.20, 0.20),
    "prefer_observation_over_motion": ("bool", None, None),
    "preserve_source_transition_intent": ("bool", None, None),
}


def _hash(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest().upper()


def _checks_pass(direction) -> bool:
    checks = direction.structural_checks
    return all(
        (
            checks.act_order_valid,
            checks.climax_present,
            checks.epilogue_present,
            checks.scene_number_alignment,
            checks.duration_alignment,
            checks.placeholders_preserved,
        )
    )


def _validate_entry(entry) -> None:
    if entry.target_component != PolicyTargetComponent.CINEMATIC_DIRECTOR_REQUEST:
        raise ShadowPolicyEvaluatorError("unsupported target component")

    spec = SUPPORTED_PARAMETERS.get(entry.parameter)
    if spec is None:
        raise ShadowPolicyEvaluatorError(f"unsupported policy parameter: {entry.parameter}")

    kind, lower, upper = spec
    values = (entry.baseline_value, entry.candidate_value)
    if kind == "bool":
        if any(type(value) is not bool for value in values):
            raise ShadowPolicyEvaluatorError(f"{entry.parameter} requires boolean values")
        return

    for value in values:
        if type(value) is bool or not isinstance(value, float):
            raise ShadowPolicyEvaluatorError(f"{entry.parameter} requires strict float values")
        if not lower <= value <= upper:
            raise ShadowPolicyEvaluatorError(
                f"{entry.parameter} outside allowed range [{lower}, {upper}]"
            )


def build_shadow_policy_plan(request: ShadowPolicyRequest) -> ShadowPolicyPlan:
    director = CinematicDirector()
    results = []

    for entry in request.registry.entries:
        _validate_entry(entry)

        for case in request.cases:
            baseline_request = CinematicDirectorRequest(
                plan=case.plan,
                video_base=case.video_base,
            )
            actual_baseline = getattr(baseline_request, entry.parameter)
            if actual_baseline != entry.baseline_value:
                raise ShadowPolicyEvaluatorError(
                    f"baseline mismatch for {entry.parameter}: "
                    f"request={actual_baseline!r} registry={entry.baseline_value!r}"
                )

            payload = baseline_request.model_dump(mode="python")
            payload[entry.parameter] = entry.candidate_value
            candidate_request = CinematicDirectorRequest.model_validate(payload)

            baseline = director.build(baseline_request)
            candidate = director.build(candidate_request)

            baseline_ok = _checks_pass(baseline)
            candidate_ok = _checks_pass(candidate)
            placeholders_preserved = (
                baseline.placeholder_count == candidate.placeholder_count
                and all(
                    before.placeholder == after.placeholder
                    for before, after in zip(baseline.scenes, candidate.scenes)
                )
            )

            results.append(
                ShadowPolicyResult(
                    policy_version=entry.policy_version,
                    policy_candidate_id=entry.policy_candidate_id,
                    case_id=case.case_id,
                    parameter=entry.parameter,
                    baseline_direction_hash=baseline.direction_hash,
                    candidate_direction_hash=candidate.direction_hash,
                    behavior_changed=baseline.direction_hash != candidate.direction_hash,
                    baseline_structural_checks_pass=baseline_ok,
                    candidate_structural_checks_pass=candidate_ok,
                    placeholders_preserved=placeholders_preserved,
                    structural_safe=baseline_ok and candidate_ok and placeholders_preserved,
                )
            )

    results.sort(key=lambda item: (item.policy_version, item.case_id))
    stable = {
        "version": SHADOW_POLICY_EVALUATOR_VERSION,
        "registry_hash": request.registry.policy_registry_hash,
        "results": [item.model_dump(mode="json") for item in results],
    }

    return ShadowPolicyPlan(
        source_policy_registry_hash=request.registry.policy_registry_hash,
        status=(
            ShadowPolicyStatus.SHADOW_RESULTS_READY
            if results
            else ShadowPolicyStatus.WAITING_FOR_REGISTERED_POLICY_AND_CASES
        ),
        registered_policy_count=request.registry.entry_count,
        case_count=len(request.cases),
        evaluation_count=len(results),
        safe_evaluation_count=sum(item.structural_safe for item in results),
        behavior_change_count=sum(item.behavior_changed for item in results),
        results=results,
        shadow_policy_hash=_hash(stable),
        generated_at_utc=datetime.now(timezone.utc),
    )
