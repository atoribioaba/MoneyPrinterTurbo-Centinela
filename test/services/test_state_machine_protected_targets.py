from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.models.finalization_e2e import HumanFinalReviewDecision, HumanFinalReviewRecord
from app.services.centinela.orchestration import (
    InvalidTransitionError,
    ProjectState,
    ProjectStateMachine,
)
from app.services.centinela.orchestration.state_machine import (
    ProjectStateMachine as RawProjectStateMachine,
)
from app.services.centinela.project_foundation import ArtifactStore

_FORWARD_GATES = (
    (ProjectState.DRAFT, ProjectState.RESEARCH_READY, "RESEARCH"),
    (ProjectState.RESEARCH_READY, ProjectState.SCRIPT_READY, "SCRIPT"),
    (ProjectState.SCRIPT_READY, ProjectState.SCENES_READY, "SCENES"),
    (ProjectState.SCENES_READY, ProjectState.MEDIA_READY, "MEDIA"),
    (ProjectState.MEDIA_READY, ProjectState.AUDIO_READY, "AUDIO"),
    (ProjectState.AUDIO_READY, ProjectState.VIDEO_BASE_READY, "VIDEO_BASE"),
    (
        ProjectState.VIDEO_BASE_READY,
        ProjectState.READY_FOR_HUMAN_REVIEW,
        "REVIEW_PREP",
    ),
)


def _raw_advance_to(store, project_id: str, target_state: ProjectState) -> None:
    machine = RawProjectStateMachine(store)
    if machine.current_state(project_id) == target_state:
        return
    ordered = (
        ProjectState.RESEARCH_READY,
        ProjectState.SCRIPT_READY,
        ProjectState.SCENES_READY,
        ProjectState.MEDIA_READY,
        ProjectState.AUDIO_READY,
        ProjectState.VIDEO_BASE_READY,
        ProjectState.READY_FOR_HUMAN_REVIEW,
    )
    for target in ordered:
        if machine.current_state(project_id) == target_state:
            return
        current = machine.current_state(project_id)
        machine.transition(
            project_id,
            target,
            reason=f"raw test setup to {target.value}",
            actor="test.raw.setup",
            expected_state=current,
        )
        if target == target_state:
            return
    raise AssertionError(f"unable to raw-advance to {target_state.value}")


def _canonical_stage_receipt(
    store,
    *,
    stage: str,
    source: ProjectState,
    target: ProjectState,
    output_type: str,
    adapter_id: str,
):
    fingerprint = (stage.lower().encode("utf-8").hex() * 64)[:64]
    provenance = {
        "production_spine_version": "1",
        "spine_stage": stage,
        "spine_fingerprint": fingerprint,
        "spine_job_id": f"job-{stage.lower()}",
        "adapter_id": adapter_id,
        "stage_disposition": "COMPLETE",
    }
    metadata = {
        "spine_stage": stage,
        "spine_fingerprint": fingerprint,
    }
    output = store.put_json(
        "p1",
        output_type,
        {"stage": stage, "test_fixture": True},
        producer=f"centinela.production_spine.{adapter_id}",
        provenance=provenance,
        metadata=metadata,
    )
    return store.put_json(
        "p1",
        "spine_stage_receipt",
        {
            "version": "1",
            "stage": stage,
            "fingerprint": fingerprint,
            "adapter_id": adapter_id,
            "source_state": source.value,
            "target_state": target.value,
            "required_artifact_types": [output_type],
            "output_artifact_ids": [output.artifact_id],
            "output_sha256": {output.artifact_id: output.sha256},
            "details": {},
        },
        producer="centinela.production_spine",
        input_artifact_ids=(output.artifact_id,),
        provenance={
            "spine_stage": stage,
            "spine_fingerprint": fingerprint,
            "spine_job_id": f"job-{stage.lower()}",
            "adapter_id": adapter_id,
        },
        metadata=metadata,
    )


def _advance_to_review(store, project_id="p1"):
    store.create_project("Protected target audit", project_id=project_id)
    _raw_advance_to(store, project_id, ProjectState.VIDEO_BASE_READY)
    receipt = _canonical_stage_receipt(
        store,
        stage="REVIEW_PREP",
        source=ProjectState.VIDEO_BASE_READY,
        target=ProjectState.READY_FOR_HUMAN_REVIEW,
        output_type="review_packet",
        adapter_id="test_review_prep_adapter",
    )
    raw = RawProjectStateMachine(store)
    raw.transition(
        project_id,
        ProjectState.READY_FOR_HUMAN_REVIEW,
        reason="raw test setup with REVIEW_PREP lineage",
        actor="test.raw.setup",
        metadata={
            "spine_stage": "REVIEW_PREP",
            "receipt_artifact_id": receipt.artifact_id,
        },
        expected_state=ProjectState.VIDEO_BASE_READY,
    )
    return receipt


def _review(
    *,
    decision: HumanFinalReviewDecision = HumanFinalReviewDecision.APPROVE,
    all_gates: bool = True,
):
    return HumanFinalReviewRecord(
        decision=decision,
        reviewer_ref="reviewer",
        rationale="protected target test review",
        decided_at_utc=datetime(2026, 8, 31, tzinfo=timezone.utc),
        science_passed=all_gates,
        visual_passed=all_gates,
        audio_passed=all_gates,
        subtitles_passed=all_gates,
        rights_passed=all_gates,
        thumbnail_passed=all_gates,
        copy_passed=all_gates,
    )


def _persist_review(store, review, *, producer="centinela.human_review.structured"):
    review_receipts = [
        item
        for item in store.list_artifacts("p1", artifact_type="spine_stage_receipt")
        if item.metadata.get("spine_stage") == "REVIEW_PREP"
    ]
    assert review_receipts
    return store.put_json(
        "p1",
        "human_final_review_record",
        review.model_dump(mode="json"),
        producer=producer,
        input_artifact_ids=(review_receipts[-1].artifact_id,),
        provenance={
            "explicit_human_decision": True,
            "structured_review": True,
        },
        metadata={
            "decision": review.decision.value,
            "all_required_gates_passed": review.all_required_gates_passed,
        },
    )


def _approve(store, machine):
    review = _review()
    ref = _persist_review(store, review)
    machine.transition(
        "p1",
        ProjectState.FINAL_APPROVED,
        reason="structured review approved",
        actor=review.reviewer_ref,
        metadata={
            "human_review": True,
            "structured_review": True,
            "decision_artifact_id": ref.artifact_id,
            "decision": "APPROVE",
            "approved": True,
        },
        expected_state=ProjectState.READY_FOR_HUMAN_REVIEW,
    )
    return ref


def _publication_receipt(store, *, valid_output=True, canonical_lineage=True):
    fingerprint = "a" * 64
    adapter_id = "test_publication_adapter"
    output_id = "missing-output"
    inputs = ()

    if valid_output:
        output_kwargs = {}
        if canonical_lineage:
            output_kwargs = {
                "provenance": {
                    "production_spine_version": "1",
                    "spine_stage": "PUBLICATION_PACKAGE",
                    "spine_fingerprint": fingerprint,
                    "spine_job_id": "job-1",
                    "adapter_id": adapter_id,
                    "stage_disposition": "COMPLETE",
                },
                "metadata": {
                    "spine_stage": "PUBLICATION_PACKAGE",
                    "spine_fingerprint": fingerprint,
                },
            }
        output = store.put_json(
            "p1",
            "publication_package_manifest",
            {"manual_publication_only": True, "auto_publication": False},
            producer=(
                f"centinela.production_spine.{adapter_id}"
                if canonical_lineage
                else "test.publication_package"
            ),
            **output_kwargs,
        )
        output_id = output.artifact_id
        inputs = (output_id,)

    receipt_kwargs = {}
    if canonical_lineage:
        receipt_kwargs = {
            "provenance": {
                "spine_stage": "PUBLICATION_PACKAGE",
                "spine_fingerprint": fingerprint,
                "spine_job_id": "job-1",
                "adapter_id": adapter_id,
            },
            "metadata": {
                "spine_stage": "PUBLICATION_PACKAGE",
                "spine_fingerprint": fingerprint,
            },
        }

    return store.put_json(
        "p1",
        "spine_stage_receipt",
        {
            "version": "1",
            "stage": "PUBLICATION_PACKAGE",
            "fingerprint": fingerprint,
            "adapter_id": adapter_id,
            "source_state": "FINAL_APPROVED",
            "target_state": "PUBLICATION_PACKAGE_READY",
            "required_artifact_types": ["publication_package_manifest"],
            "output_artifact_ids": [output_id],
            "output_sha256": {},
            "details": {},
        },
        producer=("centinela.production_spine" if canonical_lineage else "direct-caller"),
        input_artifact_ids=inputs,
        **receipt_kwargs,
    )


def _publication_transition(machine, receipt):
    machine.transition(
        "p1",
        ProjectState.PUBLICATION_PACKAGE_READY,
        reason="publication package complete",
        actor="centinela.production_spine",
        metadata={
            "spine_stage": "PUBLICATION_PACKAGE",
            "receipt_artifact_id": receipt.artifact_id,
        },
        expected_state=ProjectState.FINAL_APPROVED,
    )


@pytest.mark.parametrize("source,target,stage", _FORWARD_GATES)
def test_every_automated_forward_gate_rejects_missing_spine_evidence(
    tmp_path,
    source,
    target,
    stage,
):
    store = ArtifactStore(tmp_path / "store")
    store.create_project("Forward gate audit", project_id="p1")
    _raw_advance_to(store, "p1", source)
    machine = ProjectStateMachine(store)
    with pytest.raises(InvalidTransitionError, match=f"ProductionSpine {stage} evidence"):
        machine.transition(
            "p1",
            target,
            reason="attempt gate skip",
            actor="direct-caller",
            expected_state=source,
        )


def test_direct_final_approved_without_review_evidence_is_blocked(tmp_path):
    store = ArtifactStore(tmp_path / "store")
    _advance_to_review(store)
    machine = ProjectStateMachine(store)
    with pytest.raises(InvalidTransitionError, match="structured human-review authority"):
        machine.transition(
            "p1",
            ProjectState.FINAL_APPROVED,
            reason="direct approval without evidence",
            actor="direct-caller",
            expected_state=ProjectState.READY_FOR_HUMAN_REVIEW,
        )


def test_failed_review_gate_blocks_final_approved(tmp_path):
    store = ArtifactStore(tmp_path / "store")
    _advance_to_review(store)
    machine = ProjectStateMachine(store)
    review = _review().model_copy(update={"rights_passed": False})
    ref = _persist_review(store, review)
    with pytest.raises(InvalidTransitionError, match="review metadata"):
        machine.transition(
            "p1",
            ProjectState.FINAL_APPROVED,
            reason="incomplete approval",
            actor="reviewer",
            metadata={
                "structured_review": True,
                "approved": True,
                "decision": "APPROVE",
                "decision_artifact_id": ref.artifact_id,
            },
            expected_state=ProjectState.READY_FOR_HUMAN_REVIEW,
        )


def test_review_with_untrusted_producer_is_blocked(tmp_path):
    store = ArtifactStore(tmp_path / "store")
    _advance_to_review(store)
    machine = ProjectStateMachine(store)
    review = _review()
    ref = _persist_review(store, review, producer="direct-caller")
    with pytest.raises(InvalidTransitionError, match="canonical structured-review provenance"):
        machine.transition(
            "p1",
            ProjectState.FINAL_APPROVED,
            reason="forged approval artifact",
            actor="direct-caller",
            metadata={
                "structured_review": True,
                "approved": True,
                "decision": "APPROVE",
                "decision_artifact_id": ref.artifact_id,
            },
            expected_state=ProjectState.READY_FOR_HUMAN_REVIEW,
        )


def test_stale_review_approval_is_blocked_after_newer_review(tmp_path):
    store = ArtifactStore(tmp_path / "store")
    _advance_to_review(store)
    machine = ProjectStateMachine(store)
    approval = _persist_review(store, _review())
    _persist_review(
        store,
        _review(
            decision=HumanFinalReviewDecision.CHANGES_REQUESTED,
            all_gates=False,
        ),
    )
    with pytest.raises(InvalidTransitionError, match="latest structured"):
        machine.transition(
            "p1",
            ProjectState.FINAL_APPROVED,
            reason="reuse stale approval",
            actor="direct-caller",
            metadata={
                "structured_review": True,
                "approved": True,
                "decision": "APPROVE",
                "decision_artifact_id": approval.artifact_id,
            },
            expected_state=ProjectState.READY_FOR_HUMAN_REVIEW,
        )


def test_review_not_bound_to_latest_review_prep_is_blocked(tmp_path):
    store = ArtifactStore(tmp_path / "store")
    _advance_to_review(store)
    machine = ProjectStateMachine(store)
    review = _review()
    ref = store.put_json(
        "p1",
        "human_final_review_record",
        review.model_dump(mode="json"),
        producer="centinela.human_review.structured",
        provenance={
            "explicit_human_decision": True,
            "structured_review": True,
        },
        metadata={
            "decision": "APPROVE",
            "all_required_gates_passed": True,
        },
    )
    with pytest.raises(InvalidTransitionError, match="latest REVIEW_PREP receipt"):
        machine.transition(
            "p1",
            ProjectState.FINAL_APPROVED,
            reason="unbound review",
            actor="direct-caller",
            metadata={
                "structured_review": True,
                "approved": True,
                "decision": "APPROVE",
                "decision_artifact_id": ref.artifact_id,
            },
            expected_state=ProjectState.READY_FOR_HUMAN_REVIEW,
        )


def test_valid_review_unlocks_final_approved(tmp_path):
    store = ArtifactStore(tmp_path / "store")
    _advance_to_review(store)
    machine = ProjectStateMachine(store)
    _approve(store, machine)
    assert machine.current_state("p1") == ProjectState.FINAL_APPROVED


def test_publication_ready_without_spine_receipt_is_blocked(tmp_path):
    store = ArtifactStore(tmp_path / "store")
    _advance_to_review(store)
    machine = ProjectStateMachine(store)
    _approve(store, machine)
    with pytest.raises(
        InvalidTransitionError,
        match="ProductionSpine PUBLICATION_PACKAGE evidence",
    ):
        machine.transition(
            "p1",
            ProjectState.PUBLICATION_PACKAGE_READY,
            reason="direct publication readiness",
            actor="direct-caller",
            expected_state=ProjectState.FINAL_APPROVED,
        )


def test_minimal_forged_publication_receipt_is_blocked(tmp_path):
    store = ArtifactStore(tmp_path / "store")
    _advance_to_review(store)
    machine = ProjectStateMachine(store)
    _approve(store, machine)
    receipt = _publication_receipt(store, canonical_lineage=False)
    with pytest.raises(InvalidTransitionError, match="non-canonical producer"):
        _publication_transition(machine, receipt)


def test_publication_receipt_with_missing_output_is_blocked(tmp_path):
    store = ArtifactStore(tmp_path / "store")
    _advance_to_review(store)
    machine = ProjectStateMachine(store)
    _approve(store, machine)
    receipt = _publication_receipt(store, valid_output=False)
    with pytest.raises(InvalidTransitionError, match="lineage does not match"):
        _publication_transition(machine, receipt)


def test_valid_publication_receipt_unlocks_ready(tmp_path):
    store = ArtifactStore(tmp_path / "store")
    _advance_to_review(store)
    machine = ProjectStateMachine(store)
    _approve(store, machine)
    receipt = _publication_receipt(store, valid_output=True)
    _publication_transition(machine, receipt)
    assert machine.current_state("p1") == ProjectState.PUBLICATION_PACKAGE_READY
