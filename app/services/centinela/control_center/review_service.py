from __future__ import annotations

from app.models.finalization_e2e import HumanFinalReviewRecord

from .service import CentinelaControlCenter as _BaseCentinelaControlCenter


class CentinelaControlCenter(_BaseCentinelaControlCenter):
    """Public Control Center facade exposing only structured human review."""

    def review(
        self,
        project_id: str,
        *,
        review: HumanFinalReviewRecord,
    ):
        if not isinstance(review, HumanFinalReviewRecord):
            raise TypeError("review must be a HumanFinalReviewRecord")
        return self.spine.record_human_review(
            project_id,
            review=review,
        )
