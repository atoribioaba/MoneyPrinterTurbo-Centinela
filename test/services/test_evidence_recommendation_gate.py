from datetime import datetime, timezone

from app.models.analytics_brain import AnalyticsPlatform
from app.models.evidence_recommendation_gate import (
    EvidenceRecommendationGateRequest,
    EvidenceRecommendationStatus,
)
from app.models.experiment_evidence_ledger import (
    ExperimentEvidenceLedgerPlan,
    ExperimentEvidenceRecord,
    ExperimentEvidenceStatus,
)
from app.services.evidence_recommendation_gate import (
    build_evidence_recommendation_gate,
)


NOW = datetime(2026, 8, 22, tzinfo=timezone.utc)


def record(eligible=True, improved=True):
    control = 0.60
    variant = 0.66 if improved else 0.55
    return ExperimentEvidenceRecord(
        experiment_id="exp-1",
        hypothesis_id="hook-v1",
        platform=AnalyticsPlatform.YOUTUBE,
        variable="hook_duration_seconds",
        control_definition="5 seconds",
        variant_definition="3 seconds",
        success_metric="AUDIENCE_WATCH_RATIO",
        control_n=10,
        variant_n=10,
        control_metric_mean=control,
        variant_metric_mean=variant,
        observed_delta=variant - control,
        observed_relative_delta=(variant - control) / control,
        higher_is_better=True,
        randomized_assignment_confirmed=eligible,
        same_measurement_window_confirmed=eligible,
        human_reviewed=eligible,
        eligible_for_recommendation_review=eligible,
    )


def ledger(records):
    return ExperimentEvidenceLedgerPlan(
        source_experiment_planner_hash="planner",
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
        experiment_evidence_ledger_hash="ledger",
        generated_at_utc=NOW,
    )


def test_empty_waits():
    output = build_evidence_recommendation_gate(
        EvidenceRecommendationGateRequest(ledger=ledger([]))
    )
    assert output.status == EvidenceRecommendationStatus.WAITING_FOR_CONFIRMED_EXPERIMENT_RESULTS


def test_eligible_improvement_creates_candidate():
    output = build_evidence_recommendation_gate(
        EvidenceRecommendationGateRequest(ledger=ledger([record(True, True)]))
    )
    assert output.status == EvidenceRecommendationStatus.CANDIDATE_RECOMMENDATIONS_READY
    assert output.recommendation_count == 1
    assert output.recommendations[0].recommended_definition == "3 seconds"


def test_non_improving_variant_is_not_recommended():
    output = build_evidence_recommendation_gate(
        EvidenceRecommendationGateRequest(ledger=ledger([record(True, False)]))
    )
    assert output.recommendation_count == 0


def test_ineligible_result_is_not_recommended():
    output = build_evidence_recommendation_gate(
        EvidenceRecommendationGateRequest(ledger=ledger([record(False, True)]))
    )
    assert output.recommendation_count == 0


def test_no_auto_apply_or_policy_update():
    output = build_evidence_recommendation_gate(
        EvidenceRecommendationGateRequest(ledger=ledger([record(True, True)]))
    )
    assert output.association_only_recommendations is False
    assert output.updates_director_policy is False
    assert output.edits_project is False
    assert output.auto_apply is False
    assert output.auto_publication is False
