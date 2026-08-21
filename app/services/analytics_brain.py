from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from app.models.analytics_brain import (
    ANALYTICS_BRAIN_VERSION,
    AnalyticsBrainPlan,
    AnalyticsBrainRequest,
)


def _hash(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest().upper()


def build_analytics_brain(request: AnalyticsBrainRequest) -> AnalyticsBrainPlan:
    observations = sorted(
        request.observations,
        key=lambda item: (
            item.platform.value,
            item.content_id,
            item.observed_at_utc.isoformat(),
            item.native_metric_name,
            -1.0 if item.position_ratio is None else item.position_ratio,
        ),
    )

    stable = {
        "version": ANALYTICS_BRAIN_VERSION,
        "observations": [item.model_dump(mode="json") for item in observations],
    }

    return AnalyticsBrainPlan(
        observation_count=len(observations),
        platform_count=len({item.platform for item in observations}),
        content_count=len({(item.platform, item.content_id) for item in observations}),
        observations=observations,
        status="READY_FOR_NORMALIZATION" if observations else "WAITING_FOR_ANALYTICS_DATA",
        analytics_brain_hash=_hash(stable),
        generated_at_utc=datetime.now(timezone.utc),
    )
