from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from app.models.experiment_evidence_ledger import (
    EXPERIMENT_EVIDENCE_LEDGER_VERSION,
    ExperimentEvidenceLedgerPlan,
    ExperimentEvidenceLedgerRequest,
    ExperimentEvidenceRecord,
    ExperimentEvidenceStatus,
)


class ExperimentEvidenceLedgerError(RuntimeError):
    pass


def _hash(value: Any) -> str:
    raw = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest().upper()


def build_experiment_evidence_ledger(
    request: ExperimentEvidenceLedgerRequest,
) -> ExperimentEvidenceLedgerPlan:
    hypotheses = {
        item.hypothesis_id: item
        for item in request.planner.hypotheses
    }

    seen_experiments = set()
    records = []

    for result in request.results:
        if result.experiment_id in seen_experiments:
            raise ExperimentEvidenceLedgerError("duplicate experiment_id")
        seen_experiments.add(result.experiment_id)

        hypothesis = hypotheses.get(result.hypothesis_id)
        if hypothesis is None:
            raise ExperimentEvidenceLedgerError(
                f"unknown hypothesis_id: {result.hypothesis_id}"
            )
        if result.success_metric != hypothesis.success_metric:
            raise ExperimentEvidenceLedgerError(
                "experiment success_metric does not match hypothesis"
            )

        delta = result.variant_metric_mean - result.control_metric_mean
        relative = (
            delta / abs(result.control_metric_mean)
            if result.control_metric_mean != 0
            else None
        )
        eligible = (
            result.randomized_assignment_confirmed
            and result.same_measurement_window_confirmed
            and result.human_reviewed
        )

        records.append(
            ExperimentEvidenceRecord(
                experiment_id=result.experiment_id,
                hypothesis_id=result.hypothesis_id,
                platform=result.platform,
                variable=hypothesis.variable,
                control_definition=hypothesis.control_definition,
                variant_definition=hypothesis.variant_definition,
                success_metric=result.success_metric,
                control_n=result.control_n,
                variant_n=result.variant_n,
                control_metric_mean=result.control_metric_mean,
                variant_metric_mean=result.variant_metric_mean,
                observed_delta=delta,
                observed_relative_delta=relative,
                higher_is_better=result.higher_is_better,
                randomized_assignment_confirmed=result.randomized_assignment_confirmed,
                same_measurement_window_confirmed=result.same_measurement_window_confirmed,
                human_reviewed=result.human_reviewed,
                eligible_for_recommendation_review=eligible,
            )
        )

    records.sort(key=lambda item: item.experiment_id)

    stable = {
        "version": EXPERIMENT_EVIDENCE_LEDGER_VERSION,
        "planner_hash": request.planner.experiment_planner_hash,
        "records": [item.model_dump(mode="json") for item in records],
    }

    return ExperimentEvidenceLedgerPlan(
        source_experiment_planner_hash=request.planner.experiment_planner_hash,
        status=(
            ExperimentEvidenceStatus.RESULTS_RECORDED
            if records
            else ExperimentEvidenceStatus.WAITING_FOR_EXPERIMENT_RESULTS
        ),
        result_count=len(records),
        eligible_result_count=sum(
            item.eligible_for_recommendation_review for item in records
        ),
        records=records,
        experiment_evidence_ledger_hash=_hash(stable),
        generated_at_utc=datetime.now(timezone.utc),
    )
