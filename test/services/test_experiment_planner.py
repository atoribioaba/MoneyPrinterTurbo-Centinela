from datetime import datetime, timezone

from app.models.analytics_brain import AnalyticsPlatform
from app.models.experiment_planner import (
    ExperimentHypothesis,
    ExperimentPlannerRequest,
    ExperimentPlannerStatus,
)
from app.models.performance_signals import (
    ContentPerformanceSignal,
    PerformanceSignalsPlan,
    PerformanceSignalStatus,
)
from app.models.retention_intelligence import (
    RetentionInsight,
    RetentionIntelligencePlan,
    RetentionStatus,
)
from app.services.experiment_planner import build_experiment_planner


NOW = datetime(2026, 8, 22, tzinfo=timezone.utc)


def perf(status):
    signals = []
    if status == PerformanceSignalStatus.COHORT_SIGNALS_READY:
        signals = [
            ContentPerformanceSignal(
                platform=AnalyticsPlatform.YOUTUBE,
                content_id="fixture-video",
                cohort_size=5,
                view_count=100.0,
                view_percentile_within_cohort=0.8,
            )
        ]

    return PerformanceSignalsPlan(
        source_metric_normalizer_hash="norm",
        status=status,
        content_count=len(signals),
        ready_signal_count=sum(
            signal.view_percentile_within_cohort is not None
            or signal.interaction_rate_percentile_within_cohort is not None
            for signal in signals
        ),
        signals=signals,
        performance_signals_hash="p",
        generated_at_utc=NOW,
    )


def retention(status):
    insights = []
    if status == RetentionStatus.RETENTION_CURVES_READY:
        insights = [
            RetentionInsight(
                platform=AnalyticsPlatform.YOUTUBE,
                content_id="fixture-video",
                point_count=2,
                first_10_percent_mean=1.0,
                midpoint_ratio=0.7,
                final_ratio=0.5,
                largest_drop_position_ratio=0.5,
                largest_drop_magnitude=0.3,
            )
        ]

    return RetentionIntelligencePlan(
        source_metric_normalizer_hash="norm",
        status=status,
        curve_count=len(insights),
        insights=insights,
        retention_intelligence_hash="r",
        generated_at_utc=NOW,
    )


def hypothesis():
    return ExperimentHypothesis(
        hypothesis_id="hook-v1",
        variable="hook_duration_seconds",
        rationale="Evidence-linked candidate, not a causal claim.",
        evidence_refs=["retention:video:largest_drop"],
        control_definition="Current approved hook duration.",
        variant_definition="One alternate approved hook duration.",
        success_metric="retention_first_10_percent",
    )


def test_current_empty_state_waits():
    result = build_experiment_planner(
        ExperimentPlannerRequest(
            performance=perf(
                PerformanceSignalStatus.WAITING_FOR_ANALYTICS_DATA
            ),
            retention=retention(
                RetentionStatus.WAITING_FOR_RETENTION_DATA
            ),
            candidate_hypotheses=[],
        )
    )
    assert result.status == ExperimentPlannerStatus.WAITING_FOR_EVIDENCE
    assert result.hypothesis_count == 0


def test_hypothesis_is_suppressed_without_evidence():
    result = build_experiment_planner(
        ExperimentPlannerRequest(
            performance=perf(
                PerformanceSignalStatus.INSUFFICIENT_COHORT
            ),
            retention=retention(
                RetentionStatus.WAITING_FOR_RETENTION_DATA
            ),
            candidate_hypotheses=[hypothesis()],
        )
    )
    assert result.status == ExperimentPlannerStatus.WAITING_FOR_EVIDENCE
    assert result.hypotheses == []


def test_evidence_can_release_user_supplied_hypothesis():
    result = build_experiment_planner(
        ExperimentPlannerRequest(
            performance=perf(
                PerformanceSignalStatus.COHORT_SIGNALS_READY
            ),
            retention=retention(
                RetentionStatus.WAITING_FOR_RETENTION_DATA
            ),
            candidate_hypotheses=[hypothesis()],
        )
    )
    assert result.status == ExperimentPlannerStatus.CANDIDATE_EXPERIMENTS_READY
    assert result.hypothesis_count == 1


def test_no_auto_edit_or_publish():
    result = build_experiment_planner(
        ExperimentPlannerRequest(
            performance=perf(
                PerformanceSignalStatus.WAITING_FOR_ANALYTICS_DATA
            ),
            retention=retention(
                RetentionStatus.WAITING_FOR_RETENTION_DATA
            ),
        )
    )
    assert result.edits_project is False
    assert result.runs_experiments is False
    assert result.publishes_content is False
    assert result.causal_claims is False
