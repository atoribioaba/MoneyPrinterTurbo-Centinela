from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone

import pytest

from app.models.finalization_e2e import (
    HumanFinalReviewDecision,
    HumanFinalReviewRecord,
)
from app.services.centinela.orchestration import JobStatus, ProjectState
from app.services.centinela.project_foundation import ArtifactStore
from app.services.centinela.production_spine import (
    STRUCTURED_HUMAN_REVIEW_ARTIFACT_TYPE,
    STAGE_DESCRIPTORS,
    ProductionSpine,
    SpineStage,
    StageArtifact,
    StageBinding,
    StageResult,
    StageStateError,
)


@contextmanager
def _spine(store: ArtifactStore):
    service = ProductionSpine(store, max_workers=2)
    try:
        yield service
    finally:
        service.shutdown()


def _binding(stage: SpineStage) -> StageBinding:
    descriptor = STAGE_DESCRIPTORS[stage]

    def handler(context, payload):
        return StageResult.complete(
            *(
                StageArtifact(
                    artifact_type=artifact_type,
                    payload={"stage": stage.value},
                )
                for artifact_type in descriptor.required_artifact_types
            ),
            message=f"{stage.value} complete",
        )

    return StageBinding(
        adapter_id=f"adversarial_{stage.value.lower()}",
        handler=handler,
        resource_class=descriptor.minimum_resource_class,
    )


def _run_stage(spine: ProductionSpine, project_id: str, stage: SpineStage) -> None:
    spine.register_adapter(stage, _binding(stage))
    scheduled = spine.schedule_stage(project_id, stage)
    record = spine.wait(scheduled.job_id, timeout=10)
    assert record.status == JobStatus.SUCCEEDED


def _advance_to_review(spine: ProductionSpine, store: ArtifactStore, project_id="p1") -> None:
    store.create_project("Review gate", project_id=project_id)
    for stage in (
        SpineStage.RESEARCH,
        SpineStage.SCRIPT,
        SpineStage.SCENES,
        SpineStage.MEDIA,
        SpineStage.AUDIO,
        SpineStage.VIDEO_BASE,
        SpineStage.REVIEW_PREP,
    ):
        _run_stage(spine, project_id, stage)
    assert spine.state_machine.current_state(project_id) == ProjectState.READY_FOR_HUMAN_REVIEW


def _review(
    decision: HumanFinalReviewDecision,
    *,
    all_gates: bool,
) -> HumanFinalReviewRecord:
    return HumanFinalReviewRecord(
        decision=decision,
        reviewer_ref="human-reviewer",
        rationale="explicit adversarial review decision",
        decided_at_utc=datetime(2026, 8, 31, tzinfo=timezone.utc),
        science_passed=all_gates,
        visual_passed=all_gates,
        audio_passed=all_gates,
        subtitles_passed=all_gates,
        rights_passed=all_gates,
        thumbnail_passed=all_gates,
        copy_passed=all_gates,
    )


def test_legacy_boolean_approval_cannot_reach_final_approved(tmp_path):
    store = ArtifactStore(tmp_path / "store")
    with _spine(store) as spine:
        _advance_to_review(spine, store)
        with pytest.raises(StageStateError, match="structured HumanFinalReviewRecord"):
            spine.record_human_review(
                "p1",
                approved=True,
                reviewer="human",
                notes="legacy approve",
            )
        assert spine.state_machine.current_state("p1") == ProjectState.READY_FOR_HUMAN_REVIEW
        assert store.list_artifacts(
            "p1",
            artifact_type=STRUCTURED_HUMAN_REVIEW_ARTIFACT_TYPE,
        ) == []


def test_approve_with_one_failed_gate_is_fail_closed(tmp_path):
    store = ArtifactStore(tmp_path / "store")
    with _spine(store) as spine:
        _advance_to_review(spine, store)
        review = _review(HumanFinalReviewDecision.APPROVE, all_gates=True).model_copy(
            update={"rights_passed": False}
        )
        with pytest.raises(StageStateError, match="all seven"):
            spine.record_human_review("p1", review=review)
        assert spine.state_machine.current_state("p1") == ProjectState.READY_FOR_HUMAN_REVIEW


def test_valid_structured_approval_is_durable_and_integrity_verified(tmp_path):
    store = ArtifactStore(tmp_path / "store")
    with _spine(store) as spine:
        _advance_to_review(spine, store)
        ref = spine.record_human_review(
            "p1",
            review=_review(HumanFinalReviewDecision.APPROVE, all_gates=True),
        )
        assert ref.artifact_type == STRUCTURED_HUMAN_REVIEW_ARTIFACT_TYPE
        payload = store.read_json("p1", ref.artifact_id, verify_integrity=True)
        persisted = HumanFinalReviewRecord.model_validate(payload)
        assert persisted.decision == HumanFinalReviewDecision.APPROVE
        assert persisted.all_required_gates_passed is True
        assert spine.state_machine.current_state("p1") == ProjectState.FINAL_APPROVED


def test_tampered_structured_approval_cannot_unlock_publication_package(tmp_path):
    store = ArtifactStore(tmp_path / "store")
    with _spine(store) as spine:
        _advance_to_review(spine, store)
        ref = spine.record_human_review(
            "p1",
            review=_review(HumanFinalReviewDecision.APPROVE, all_gates=True),
        )
        path = store.resolve_artifact_path("p1", ref.artifact_id)
        path.write_text('{"decision":"APPROVE"}\n', encoding="utf-8")
        spine.register_adapter(SpineStage.PUBLICATION_PACKAGE, _binding(SpineStage.PUBLICATION_PACKAGE))
        with pytest.raises(StageStateError, match="integrity-verified structured human approval"):
            spine.schedule_stage("p1", SpineStage.PUBLICATION_PACKAGE)
        assert spine.state_machine.current_state("p1") == ProjectState.FINAL_APPROVED


def test_legacy_approved_metadata_is_not_publication_authority(tmp_path):
    store = ArtifactStore(tmp_path / "store")
    store.create_project("Legacy final approved", project_id="p1")
    manifest = store.load_project("p1")
    manifest.status = ProjectState.FINAL_APPROVED.value
    store.save_project(manifest)
    store.put_json(
        "p1",
        "human_review_decision",
        {"approved": True, "reviewer": "legacy", "notes": "legacy"},
        producer="legacy-test",
        metadata={"approved": True},
    )
    with _spine(store) as spine:
        spine.register_adapter(SpineStage.PUBLICATION_PACKAGE, _binding(SpineStage.PUBLICATION_PACKAGE))
        with pytest.raises(StageStateError, match="structured human approval"):
            spine.schedule_stage("p1", SpineStage.PUBLICATION_PACKAGE)


def test_forged_structured_approval_without_transition_is_not_publication_authority(tmp_path):
    store = ArtifactStore(tmp_path / "store")
    store.create_project("Forged final approved", project_id="p1")
    manifest = store.load_project("p1")
    manifest.status = ProjectState.FINAL_APPROVED.value
    store.save_project(manifest)
    forged = _review(HumanFinalReviewDecision.APPROVE, all_gates=True)
    store.put_json(
        "p1",
        STRUCTURED_HUMAN_REVIEW_ARTIFACT_TYPE,
        forged.model_dump(mode="json"),
        producer="centinela.human_review.structured",
        producer_version="adversarial-v1",
        provenance={
            "explicit_human_decision": True,
            "structured_review": True,
        },
        metadata={
            "decision": HumanFinalReviewDecision.APPROVE.value,
            "all_required_gates_passed": True,
        },
    )
    with _spine(store) as spine:
        spine.register_adapter(SpineStage.PUBLICATION_PACKAGE, _binding(SpineStage.PUBLICATION_PACKAGE))
        with pytest.raises(StageStateError, match="structured human approval"):
            spine.schedule_stage("p1", SpineStage.PUBLICATION_PACKAGE)


def test_newer_structured_reject_revokes_prior_publication_authority(tmp_path):
    store = ArtifactStore(tmp_path / "store")
    with _spine(store) as spine:
        _advance_to_review(spine, store)
        spine.record_human_review(
            "p1",
            review=_review(HumanFinalReviewDecision.APPROVE, all_gates=True),
        )
        rejection = _review(HumanFinalReviewDecision.REJECT, all_gates=False)
        store.put_json(
            "p1",
            STRUCTURED_HUMAN_REVIEW_ARTIFACT_TYPE,
            rejection.model_dump(mode="json"),
            producer="centinela.human_review.structured",
            producer_version="adversarial-v1",
            provenance={
                "explicit_human_decision": True,
                "structured_review": True,
            },
            metadata={
                "decision": HumanFinalReviewDecision.REJECT.value,
                "all_required_gates_passed": False,
            },
        )
        spine.register_adapter(SpineStage.PUBLICATION_PACKAGE, _binding(SpineStage.PUBLICATION_PACKAGE))
        with pytest.raises(StageStateError, match="structured human approval"):
            spine.schedule_stage("p1", SpineStage.PUBLICATION_PACKAGE)


def test_legacy_rejection_remains_compatible_and_structured(tmp_path):
    store = ArtifactStore(tmp_path / "store")
    with _spine(store) as spine:
        _advance_to_review(spine, store)
        ref = spine.record_human_review(
            "p1",
            approved=False,
            reviewer="human",
            notes="changes required",
        )
        payload = store.read_json("p1", ref.artifact_id, verify_integrity=True)
        persisted = HumanFinalReviewRecord.model_validate(payload)
        assert persisted.decision == HumanFinalReviewDecision.CHANGES_REQUESTED
        assert persisted.all_required_gates_passed is False
        assert spine.state_machine.current_state("p1") == ProjectState.NEEDS_INPUT


def test_structured_reject_does_not_require_passing_gates(tmp_path):
    store = ArtifactStore(tmp_path / "store")
    with _spine(store) as spine:
        _advance_to_review(spine, store)
        ref = spine.record_human_review(
            "p1",
            review=_review(HumanFinalReviewDecision.REJECT, all_gates=False),
        )
        payload = store.read_json("p1", ref.artifact_id, verify_integrity=True)
        assert payload["decision"] == HumanFinalReviewDecision.REJECT.value
        assert spine.state_machine.current_state("p1") == ProjectState.NEEDS_INPUT


def test_rejected_review_can_resume_then_receive_valid_structured_approval(tmp_path):
    store = ArtifactStore(tmp_path / "store")
    with _spine(store) as spine:
        _advance_to_review(spine, store)
        spine.record_human_review(
            "p1",
            approved=False,
            reviewer="human",
            notes="revise",
        )
        assert spine.state_machine.current_state("p1") == ProjectState.NEEDS_INPUT
        spine.record_human_review(
            "p1",
            review=_review(HumanFinalReviewDecision.APPROVE, all_gates=True),
        )
        assert spine.state_machine.current_state("p1") == ProjectState.FINAL_APPROVED
