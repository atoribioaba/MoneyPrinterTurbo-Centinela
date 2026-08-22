from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from app.models.evidence_recommendation_gate import (
    EVIDENCE_RECOMMENDATION_GATE_VERSION,
    CandidateRecommendation,
    EvidenceRecommendationGatePlan,
    EvidenceRecommendationGateRequest,
    EvidenceRecommendationStatus,
)


def _hash(value: Any) -> str:
    raw = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest().upper()


def build_evidence_recommendation_gate(
    request: EvidenceRecommendationGateRequest,
) -> EvidenceRecommendationGatePlan:
    recommendations = []

    for record in request.ledger.records:
        if not record.eligible_for_recommendation_review:
            continue

        improved = (
            record.variant_metric_mean > record.control_metric_mean
            if record.higher_is_better
            else record.variant_metric_mean < record.control_metric_mean
        )
        if not improved:
            continue

        recommendation_id = _hash(
            {
                "experiment_id": record.experiment_id,
                "hypothesis_id": record.hypothesis_id,
                "variable": record.variable,
                "variant": record.variant_definition,
            }
        )

        recommendations.append(
            CandidateRecommendation(
                recommendation_id=recommendation_id,
                experiment_id=record.experiment_id,
                hypothesis_id=record.hypothesis_id,
                platform=record.platform,
                variable=record.variable,
                recommended_definition=record.variant_definition,
                success_metric=record.success_metric,
                observed_delta=record.observed_delta,
                observed_relative_delta=record.observed_relative_delta,
            )
        )

    recommendations.sort(key=lambda item: item.recommendation_id)

    stable = {
        "version": EVIDENCE_RECOMMENDATION_GATE_VERSION,
        "ledger_hash": request.ledger.experiment_evidence_ledger_hash,
        "recommendations": [
            item.model_dump(mode="json") for item in recommendations
        ],
    }

    return EvidenceRecommendationGatePlan(
        source_experiment_evidence_ledger_hash=request.ledger.experiment_evidence_ledger_hash,
        status=(
            EvidenceRecommendationStatus.CANDIDATE_RECOMMENDATIONS_READY
            if recommendations
            else EvidenceRecommendationStatus.WAITING_FOR_CONFIRMED_EXPERIMENT_RESULTS
        ),
        recommendation_count=len(recommendations),
        recommendations=recommendations,
        evidence_recommendation_gate_hash=_hash(stable),
        generated_at_utc=datetime.now(timezone.utc),
    )
