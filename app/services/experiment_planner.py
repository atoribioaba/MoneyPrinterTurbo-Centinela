from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from app.models.experiment_planner import (
    EXPERIMENT_PLANNER_VERSION,
    ExperimentPlannerPlan,
    ExperimentPlannerRequest,
    ExperimentPlannerStatus,
)
from app.models.performance_signals import PerformanceSignalStatus
from app.models.retention_intelligence import RetentionStatus


def _hash(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest().upper()


def build_experiment_planner(request: ExperimentPlannerRequest) -> ExperimentPlannerPlan:
    evidence_sufficient = (
        request.performance.status == PerformanceSignalStatus.COHORT_SIGNALS_READY
        or request.retention.status == RetentionStatus.RETENTION_CURVES_READY
    )

    hypotheses = list(request.candidate_hypotheses) if evidence_sufficient else []
    status = (
        ExperimentPlannerStatus.CANDIDATE_EXPERIMENTS_READY
        if hypotheses
        else ExperimentPlannerStatus.WAITING_FOR_EVIDENCE
    )

    stable = {
        "version": EXPERIMENT_PLANNER_VERSION,
        "performance_hash": request.performance.performance_signals_hash,
        "retention_hash": request.retention.retention_intelligence_hash,
        "evidence_sufficient": evidence_sufficient,
        "hypotheses": [item.model_dump(mode="json") for item in hypotheses],
    }

    return ExperimentPlannerPlan(
        source_performance_hash=request.performance.performance_signals_hash,
        source_retention_hash=request.retention.retention_intelligence_hash,
        status=status,
        evidence_sufficient=evidence_sufficient,
        hypothesis_count=len(hypotheses),
        hypotheses=hypotheses,
        experiment_planner_hash=_hash(stable),
        generated_at_utc=datetime.now(timezone.utc),
    )
