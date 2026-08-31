from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.models.finalization_e2e import (
    HumanFinalReviewDecision,
    HumanFinalReviewRecord,
)
from app.services.centinela.orchestration import ProjectState
from app.services.centinela.project_foundation import ArtifactRef

from .models import PRODUCTION_SPINE_VERSION, SpineStage
from .spine import ProductionSpine as _LegacyProductionSpine
from .spine import StageStateError

STRUCTURED_HUMAN_REVIEW_ARTIFACT_TYPE = "human_final_review_record"


class ProductionSpine(_LegacyProductionSpine):
    """Fail-closed review gate layered over the legacy production spine.

    A transition to FINAL_APPROVED requires a durable HumanFinalReviewRecord whose
    decision is APPROVE and whose seven canonical human-review gates all pass.
    Legacy boolean approval is intentionally rejected. Legacy boolean rejection is
    retained only as a compatibility path and is normalized to CHANGES_REQUESTED.
    """

    @staticmethod
    def _normalize_review(
        *,
        review: HumanFinalReviewRecord | dict[str, Any] | None,
        approved: bool | None,
        reviewer: str | None,
        notes: str | None,
    ) -> HumanFinalReviewRecord:
        if review is None:
            if approved is not False:
                raise StageStateError(
                    "legacy boolean approval is forbidden; "
                    "a structured HumanFinalReviewRecord is required"
                )
            reviewer_ref = str(reviewer or "").strip()
            rationale = str(notes or "").strip()
            if not reviewer_ref or not rationale:
                raise ValueError("reviewer and notes are required")
            return HumanFinalReviewRecord(
                decision=HumanFinalReviewDecision.CHANGES_REQUESTED,
                reviewer_ref=reviewer_ref,
                rationale=rationale,
                decided_at_utc=datetime.now(timezone.utc),
            )

        if approved is not None or reviewer is not None or notes is not None:
            raise TypeError(
                "structured review cannot be combined with legacy approved/reviewer/notes fields"
            )
        if isinstance(review, HumanFinalReviewRecord):
            payload = review.model_dump(mode="json")
        elif isinstance(review, dict):
            payload = dict(review)
        else:
            raise TypeError("review must be HumanFinalReviewRecord or dict")
        return HumanFinalReviewRecord.model_validate(payload)

    def _prepare_human_review_state(self, project_id: str) -> None:
        current = self.state_machine.current_state(project_id)
        if current == ProjectState.NEEDS_INPUT and self._latest_side_stage(project_id) is None:
            history = self.state_machine.history(project_id)
            if history and history[-1].metadata.get("human_review"):
                self.state_machine.transition(
                    project_id,
                    ProjectState.READY_FOR_HUMAN_REVIEW,
                    reason="resume human review",
                    actor="centinela.production_spine",
                    metadata={"human_review": True, "resume": True},
                    expected_state=ProjectState.NEEDS_INPUT,
                )
                current = ProjectState.READY_FOR_HUMAN_REVIEW
        if current != ProjectState.READY_FOR_HUMAN_REVIEW:
            raise StageStateError("human review requires READY_FOR_HUMAN_REVIEW")

    def _validated_structured_review(self, project_id: str, ref: ArtifactRef) -> HumanFinalReviewRecord:
        if ref.artifact_type != STRUCTURED_HUMAN_REVIEW_ARTIFACT_TYPE:
            raise StageStateError("unexpected human review artifact type")
        payload = self.store.read_json(
            project_id,
            ref.artifact_id,
            verify_integrity=True,
        )
        return HumanFinalReviewRecord.model_validate(payload)

    def _previous_receipt(self, project_id: str, stage: SpineStage) -> ArtifactRef | None:
        if stage != SpineStage.PUBLICATION_PACKAGE:
            return super()._previous_receipt(project_id, stage)

        reviews = self.store.list_artifacts(
            project_id,
            artifact_type=STRUCTURED_HUMAN_REVIEW_ARTIFACT_TYPE,
        )
        for ref in reversed(reviews):
            try:
                record = self._validated_structured_review(project_id, ref)
            except Exception:
                continue
            if (
                record.decision == HumanFinalReviewDecision.APPROVE
                and record.all_required_gates_passed
            ):
                return ref
        return None

    def schedule_stage(
        self,
        project_id: str,
        stage: SpineStage | str,
        **kwargs: Any,
    ):
        normalized = SpineStage(stage)
        if (
            normalized == SpineStage.PUBLICATION_PACKAGE
            and self.state_machine.current_state(project_id) == ProjectState.FINAL_APPROVED
            and self._previous_receipt(project_id, normalized) is None
        ):
            raise StageStateError(
                "PUBLICATION_PACKAGE requires integrity-verified structured human approval"
            )
        return super().schedule_stage(project_id, normalized, **kwargs)

    def record_human_review(
        self,
        project_id: str,
        *,
        review: HumanFinalReviewRecord | dict[str, Any] | None = None,
        approved: bool | None = None,
        reviewer: str | None = None,
        notes: str | None = None,
    ) -> ArtifactRef:
        normalized = self._normalize_review(
            review=review,
            approved=approved,
            reviewer=reviewer,
            notes=notes,
        )
        self._prepare_human_review_state(project_id)

        if (
            normalized.decision == HumanFinalReviewDecision.APPROVE
            and not normalized.all_required_gates_passed
        ):
            raise StageStateError(
                "APPROVE requires all seven canonical human-review gates to pass"
            )

        review_receipts = [
            item
            for item in self.store.list_artifacts(
                project_id,
                artifact_type="spine_stage_receipt",
            )
            if item.metadata.get("spine_stage") == SpineStage.REVIEW_PREP.value
        ]
        previous = review_receipts[-1] if review_receipts else None
        inputs = () if previous is None else (previous.artifact_id,)

        ref = self.store.put_json(
            project_id,
            STRUCTURED_HUMAN_REVIEW_ARTIFACT_TYPE,
            normalized.model_dump(mode="json"),
            producer="centinela.human_review.structured",
            producer_version=PRODUCTION_SPINE_VERSION,
            input_artifact_ids=inputs,
            provenance={
                "explicit_human_decision": True,
                "structured_review": True,
            },
            metadata={
                "decision": normalized.decision.value,
                "all_required_gates_passed": normalized.all_required_gates_passed,
            },
        )

        persisted = self._validated_structured_review(project_id, ref)
        approved_result = persisted.decision == HumanFinalReviewDecision.APPROVE
        if approved_result and not persisted.all_required_gates_passed:
            raise StageStateError(
                "persisted APPROVE evidence does not satisfy all seven human-review gates"
            )

        target = ProjectState.FINAL_APPROVED if approved_result else ProjectState.NEEDS_INPUT
        reason_by_decision = {
            HumanFinalReviewDecision.APPROVE: "structured human review approved",
            HumanFinalReviewDecision.CHANGES_REQUESTED: "structured human review requested changes",
            HumanFinalReviewDecision.REJECT: "structured human review rejected",
        }
        self.state_machine.transition(
            project_id,
            target,
            reason=reason_by_decision[persisted.decision],
            actor=persisted.reviewer_ref,
            metadata={
                "human_review": True,
                "structured_review": True,
                "decision_artifact_id": ref.artifact_id,
                "decision": persisted.decision.value,
                "approved": approved_result,
            },
            expected_state=ProjectState.READY_FOR_HUMAN_REVIEW,
        )
        return ref
