from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from datetime import timezone
from typing import Any

from app.models.content_feature_registry import ContentBindingStatus
from app.models.metric_normalizer import NormalizationStatus
from app.models.outcome_linker import (
    OUTCOME_LINKER_VERSION,
    FeatureOutcomeRecord,
    LinkedOutcome,
    OutcomeLinkerPlan,
    OutcomeLinkerRequest,
    OutcomeLinkerStatus,
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


def build_outcome_linker(request: OutcomeLinkerRequest) -> OutcomeLinkerPlan:
    snapshot_by_key = {}
    for snapshot in request.features.snapshots:
        if snapshot.binding_status != ContentBindingStatus.BOUND_TO_CONTENT:
            continue
        key = (snapshot.platform, snapshot.content_id)
        snapshot_by_key[key] = snapshot

    # One latest verified normalized observation per content/canonical metric.
    latest = {}
    for item in request.metrics.observations:
        if item.normalization_status != NormalizationStatus.NORMALIZED_VERIFIED:
            continue
        if item.canonical_metric is None:
            continue

        source = item.source
        key = (source.platform, source.content_id)
        if key not in snapshot_by_key:
            continue

        metric_key = (source.platform, source.content_id, item.canonical_metric)
        previous = latest.get(metric_key)
        if previous is None or source.observed_at_utc > previous.source.observed_at_utc:
            latest[metric_key] = item

    grouped = defaultdict(list)
    for item in latest.values():
        source = item.source
        key = (source.platform, source.content_id)
        snapshot = snapshot_by_key[key]
        grouped[key].append(
            LinkedOutcome(
                platform=source.platform,
                content_id=source.content_id,
                snapshot_id=snapshot.snapshot_id,
                canonical_metric=item.canonical_metric,
                value=source.value,
                observed_at_utc=source.observed_at_utc.astimezone(timezone.utc),
                source_native_metric_name=source.native_metric_name,
                source_metric_normalizer_hash=request.metrics.metric_normalizer_hash,
            )
        )

    records = []
    for key in sorted(grouped, key=lambda item: (item[0].value, item[1])):
        snapshot = snapshot_by_key[key]
        outcomes = sorted(
            grouped[key],
            key=lambda item: item.canonical_metric.value,
        )
        features = {
            item.feature_name: item.value
            for item in snapshot.features
        }
        records.append(
            FeatureOutcomeRecord(
                platform=key[0],
                content_id=key[1],
                snapshot_id=snapshot.snapshot_id,
                features=features,
                outcome_count=len(outcomes),
                outcomes=outcomes,
            )
        )

    stable = {
        "version": OUTCOME_LINKER_VERSION,
        "feature_hash": request.features.content_feature_registry_hash,
        "metric_hash": request.metrics.metric_normalizer_hash,
        "records": [item.model_dump(mode="json") for item in records],
    }

    return OutcomeLinkerPlan(
        source_content_feature_registry_hash=request.features.content_feature_registry_hash,
        source_metric_normalizer_hash=request.metrics.metric_normalizer_hash,
        status=(
            OutcomeLinkerStatus.JOINED_OUTCOMES_READY
            if records
            else OutcomeLinkerStatus.WAITING_FOR_BOUND_CONTENT_ANALYTICS
        ),
        record_count=len(records),
        joined_outcome_count=sum(item.outcome_count for item in records),
        records=records,
        outcome_linker_hash=_hash(stable),
        generated_at_utc=__import__("datetime").datetime.now(timezone.utc),
    )
