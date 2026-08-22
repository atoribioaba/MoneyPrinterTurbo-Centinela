from __future__ import annotations

import hashlib
import json
import math
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from app.models.association_analyzer import (
    ASSOCIATION_ANALYZER_VERSION,
    AssociationAnalyzerPlan,
    AssociationAnalyzerRequest,
    AssociationAnalyzerStatus,
    FeatureOutcomeAssociation,
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


def _average_ranks(values: list[float]) -> list[float]:
    order = sorted(range(len(values)), key=lambda index: values[index])
    ranks = [0.0] * len(values)

    position = 0
    while position < len(order):
        end = position + 1
        while end < len(order) and values[order[end]] == values[order[position]]:
            end += 1

        # Ranks are 1-based; ties receive the average rank.
        average = ((position + 1) + end) / 2.0
        for cursor in range(position, end):
            ranks[order[cursor]] = average
        position = end

    return ranks


def _pearson(x: list[float], y: list[float]) -> float | None:
    if len(x) != len(y) or len(x) < 2:
        return None

    mean_x = sum(x) / len(x)
    mean_y = sum(y) / len(y)
    dx = [item - mean_x for item in x]
    dy = [item - mean_y for item in y]
    sum_x2 = sum(item * item for item in dx)
    sum_y2 = sum(item * item for item in dy)

    if sum_x2 == 0 or sum_y2 == 0:
        return None

    numerator = sum(a * b for a, b in zip(dx, dy))
    return numerator / math.sqrt(sum_x2 * sum_y2)


def _spearman(x: list[float], y: list[float]) -> float | None:
    return _pearson(_average_ranks(x), _average_ranks(y))


def build_association_analyzer(
    request: AssociationAnalyzerRequest,
) -> AssociationAnalyzerPlan:
    # platform + feature + metric -> list[(content_id, feature, outcome)]
    pairs = defaultdict(list)

    for record in request.joined.records:
        for feature_name, feature_value in record.features.items():
            for outcome in record.outcomes:
                key = (
                    record.platform,
                    feature_name,
                    outcome.canonical_metric,
                )
                pairs[key].append(
                    (record.content_id, float(feature_value), float(outcome.value))
                )

    associations = []
    for key in sorted(
        pairs,
        key=lambda item: (item[0].value, item[1], item[2].value),
    ):
        rows = pairs[key]
        # One row per content is guaranteed by F37 record structure.
        if len(rows) < request.minimum_sample_size:
            continue

        x = [row[1] for row in rows]
        y = [row[2] for row in rows]
        rho = _spearman(x, y)
        if rho is None:
            continue

        associations.append(
            FeatureOutcomeAssociation(
                platform=key[0],
                feature_name=key[1],
                canonical_metric=key[2],
                sample_size=len(rows),
                spearman_rho=round(rho, 6),
            )
        )

    if not request.joined.records:
        status = AssociationAnalyzerStatus.WAITING_FOR_JOINED_DATA
    elif associations:
        status = AssociationAnalyzerStatus.ASSOCIATIONS_READY
    else:
        status = AssociationAnalyzerStatus.INSUFFICIENT_SAMPLE

    stable = {
        "version": ASSOCIATION_ANALYZER_VERSION,
        "joined_hash": request.joined.outcome_linker_hash,
        "minimum_sample_size": request.minimum_sample_size,
        "associations": [item.model_dump(mode="json") for item in associations],
    }

    return AssociationAnalyzerPlan(
        source_outcome_linker_hash=request.joined.outcome_linker_hash,
        status=status,
        candidate_pair_count=len(pairs),
        association_count=len(associations),
        associations=associations,
        association_analyzer_hash=_hash(stable),
        generated_at_utc=datetime.now(timezone.utc),
    )
