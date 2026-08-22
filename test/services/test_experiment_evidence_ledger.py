from datetime import datetime, timezone

import pytest

from app.models.analytics_brain import AnalyticsPlatform
from app.models.experiment_evidence_ledger import (
    ExperimentEvidenceLedgerRequest,
    ExperimentEvidenceStatus,
    ExperimentResultInput,
)
from app.models.experiment_planner import (
    ExperimentHypothesis,
    ExperimentPlannerPlan,
    ExperimentPlannerStatus,
)
from app.services.experiment_evidence_ledger import (
    build_experiment_evidence_ledger,
)


NOW = datetime(2026, 8, 22, tzinfo=timezone.utc)


def hypothesis():
    return ExperimentHypothesis(
        hypothesis_id="hook-v1",
        variable="hook_duration_seconds",
        rationale="Controlled test candidate.",
        evidence_refs=["association:hook"],
        control_definition="5 seconds",
        variant_definition="3 seconds",
        success_metric="AUDIENCE_WATCH_RATIO",
    )


def planner(with_hypothesis=True):
    hypotheses = [hypothesis()] if with_hypothesis else []
    return ExperimentPlannerPlan(
        source_performance_hash="p",
        source_retention_hash="r",
        status=(
            ExperimentPlannerStatus.CANDIDATE_EXPERIMENTS_READY
            if hypotheses
            else ExperimentPlannerStatus.WAITING_FOR_EVIDENCE
        ),
        evidence_sufficient=bool(hypotheses),
        hypothesis_count=len(hypotheses),
        hypotheses=hypotheses,
        experiment_planner_hash="planner",
        generated_at_utc=NOW,
    )


def result(**overrides):
    values = dict(
        experiment_id="exp-1",
        hypothesis_id="hook-v1",
        platform=AnalyticsPlatform.YOUTUBE,
        success_metric="AUDIENCE_WATCH_RATIO",
        control_n=10,
        variant_n=10,
        control_metric_mean=0.60,
        variant_metric_mean=0.66,
        higher_is_better=True,
        randomized_assignment_confirmed=True,
        same_measurement_window_confirmed=True,
        human_reviewed=True,
    )
    values.update(overrides)
    return ExperimentResultInput(**values)


def test_empty_waits():
    output = build_experiment_evidence_ledger(
        ExperimentEvidenceLedgerRequest(
            planner=planner(False),
            results=[],
        )
    )
    assert output.status == ExperimentEvidenceStatus.WAITING_FOR_EXPERIMENT_RESULTS


def test_reviewed_randomized_result_is_eligible():
    output = build_experiment_evidence_ledger(
        ExperimentEvidenceLedgerRequest(
            planner=planner(True),
            results=[result()],
        )
    )
    record = output.records[0]
    assert output.eligible_result_count == 1
    assert record.eligible_for_recommendation_review is True
    assert round(record.observed_delta, 2) == 0.06


def test_unreviewed_result_is_not_eligible():
    output = build_experiment_evidence_ledger(
        ExperimentEvidenceLedgerRequest(
            planner=planner(True),
            results=[result(human_reviewed=False)],
        )
    )
    assert output.eligible_result_count == 0


def test_unknown_hypothesis_is_rejected():
    with pytest.raises(RuntimeError):
        build_experiment_evidence_ledger(
            ExperimentEvidenceLedgerRequest(
                planner=planner(True),
                results=[result(hypothesis_id="missing")],
            )
        )


def test_no_significance_or_causal_claim():
    output = build_experiment_evidence_ledger(
        ExperimentEvidenceLedgerRequest(
            planner=planner(True),
            results=[result()],
        )
    )
    assert output.calculates_p_values is False
    assert output.causal_claims is False
    assert output.records[0].statistical_significance_claimed is False
