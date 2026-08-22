from datetime import datetime, timezone

from app.models.analytics_brain import AnalyticsPlatform
from app.models.association_analyzer import (
    AssociationAnalyzerRequest,
    AssociationAnalyzerStatus,
)
from app.models.metric_normalizer import CanonicalMetric
from app.models.outcome_linker import (
    FeatureOutcomeRecord,
    LinkedOutcome,
    OutcomeLinkerPlan,
)
from app.services.association_analyzer import build_association_analyzer


NOW = datetime(2026, 8, 22, tzinfo=timezone.utc)


def record(index, feature, outcome):
    content_id = f"video-{index}"
    return FeatureOutcomeRecord(
        platform=AnalyticsPlatform.YOUTUBE,
        content_id=content_id,
        snapshot_id=f"snap-{index}",
        features={"HOOK_CHAR_COUNT": feature},
        outcome_count=1,
        outcomes=[
            LinkedOutcome(
                platform=AnalyticsPlatform.YOUTUBE,
                content_id=content_id,
                snapshot_id=f"snap-{index}",
                canonical_metric=CanonicalMetric.VIEW_COUNT,
                value=outcome,
                observed_at_utc=NOW,
                source_native_metric_name="views",
                source_metric_normalizer_hash="metrics",
            )
        ],
    )


def plan(records):
    return OutcomeLinkerPlan.model_construct(
        records=records,
        outcome_linker_hash="joined",
    )


def test_empty_waits():
    result = build_association_analyzer(
        AssociationAnalyzerRequest.model_construct(
            joined=plan([]),
            minimum_sample_size=5,
        )
    )
    assert result.status == AssociationAnalyzerStatus.WAITING_FOR_JOINED_DATA


def test_small_sample_is_insufficient():
    result = build_association_analyzer(
        AssociationAnalyzerRequest.model_construct(
            joined=plan([record(i, i, i) for i in range(1, 5)]),
            minimum_sample_size=5,
        )
    )
    assert result.status == AssociationAnalyzerStatus.INSUFFICIENT_SAMPLE


def test_monotonic_sample_has_spearman_one():
    result = build_association_analyzer(
        AssociationAnalyzerRequest.model_construct(
            joined=plan([record(i, i, i * 10) for i in range(1, 6)]),
            minimum_sample_size=5,
        )
    )
    assert result.status == AssociationAnalyzerStatus.ASSOCIATIONS_READY
    assert result.associations[0].spearman_rho == 1.0


def test_no_p_values_or_causal_claims():
    result = build_association_analyzer(
        AssociationAnalyzerRequest.model_construct(
            joined=plan([record(i, i, i * 10) for i in range(1, 6)]),
            minimum_sample_size=5,
        )
    )
    assert result.p_values_calculated is False
    assert result.statistical_significance_claimed is False
    assert result.causal_claims is False
    assert result.associations[0].p_value is None


def test_no_cross_platform_pooling():
    result = build_association_analyzer(
        AssociationAnalyzerRequest.model_construct(
            joined=plan([]),
            minimum_sample_size=5,
        )
    )
    assert result.cross_platform_pooling is False
