from __future__ import annotations

from typing import Any

from app.models.finalization_e2e import HumanFinalReviewRecord

from .service import CentinelaControlCenter as _LegacyCentinelaControlCenter


class CentinelaControlCenter(_LegacyCentinelaControlCenter):
    """Control Center facade with the structured human-review contract."""

    def review(
        self,
        project_id: str,
        *,
        review: HumanFinalReviewRecord | dict[str, Any] | None = None,
        approved: bool | None = None,
        reviewer: str | None = None,
        notes: str | None = None,
    ):
        return self.spine.record_human_review(
            project_id,
            review=review,
            approved=approved,
            reviewer=reviewer,
            notes=notes,
        )
