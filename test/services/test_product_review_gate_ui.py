from __future__ import annotations

import inspect
from pathlib import Path

import pytest

from app.models.finalization_e2e import (
    HumanFinalReviewDecision,
    HumanFinalReviewRecord,
)
from app.services.centinela.control_center import CentinelaControlCenter
from app.services.centinela.orchestration import JobStatus, ProjectState
from app.services.centinela.production_spine import (
    STAGE_DESCRIPTORS,
    SpineStage,
    StageArtifact,
    StageBinding,
    StageResult,
    StageStateError,
)
from app.services.centinela.project_foundation import ArtifactStore
from app.services.centinela.research_adapters.integration import C3ResearchControlCenter
from webui.product.review import _build_review


class _FakeCatalog:
    def list_items(self, active_only=True):
        del active_only
        return []


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _binding(stage: SpineStage) -> StageBinding:
    descriptor = STAGE_DESCRIPTORS[stage]

    def handler(context, payload):
        del context, payload
        return StageResult.complete(
            *(
                StageArtifact(
                    artifact_type=artifact_type,
                    payload={"stage": stage.value, "ok": True},
                )
                for artifact_type in descriptor.required_artifact_types
            ),
            message=f"{stage.value} complete",
        )

    return StageBinding(
        adapter_id=f"review_integration_{stage.value.lower()}",
        handler=handler,
        resource_class=descriptor.minimum_resource_class,
    )


def _make_service(tmp_path) -> CentinelaControlCenter:
    return CentinelaControlCenter(
        store=ArtifactStore(tmp_path / "centinela"),
        catalog=_FakeCatalog(),
        register_default_media=False,
        max_workers=2,
    )


def _advance_to_review(service: CentinelaControlCenter, project_id: str) -> None:
    for stage in (
        SpineStage.RESEARCH,
        SpineStage.SCRIPT,
        SpineStage.SCENES,
        SpineStage.MEDIA,
        SpineStage.AUDIO,
        SpineStage.VIDEO_BASE,
        SpineStage.REVIEW_PREP,
    ):
        service.register_stage(stage, _binding(stage))
        scheduled = service.spine.schedule_stage(project_id, stage)
        record = service.spine.wait(scheduled.job_id, timeout=10)
        assert record.status == JobStatus.SUCCEEDED
    assert service.project(project_id).state == ProjectState.READY_FOR_HUMAN_REVIEW


def _ui_review(*, all_gates: bool = True) -> HumanFinalReviewRecord:
    return _build_review(
        decision=HumanFinalReviewDecision.APPROVE,
        reviewer="human-reviewer",
        notes="explicit product review",
        science_passed=all_gates,
        visual_passed=all_gates,
        audio_passed=all_gates,
        subtitles_passed=all_gates,
        rights_passed=all_gates,
        thumbnail_passed=all_gates,
        copy_passed=all_gates,
    )


def test_product_navigation_routes_to_structured_review_page():
    text = (_repo_root() / "webui" / "Centinela.py").read_text(encoding="utf-8")
    compile(text, "webui/Centinela.py", "exec")
    assert "from webui.product import pages, review" in text
    assert 'st.Page(review.review_page, title="Revisión")' in text
    assert 'st.Page(pages.review_page, title="Revisión")' not in text


def test_structured_review_ui_exposes_all_seven_canonical_gates():
    text = (_repo_root() / "webui" / "product" / "review.py").read_text(encoding="utf-8")
    compile(text, "webui/product/review.py", "exec")
    for field in (
        "science_passed",
        "visual_passed",
        "audio_passed",
        "subtitles_passed",
        "rights_passed",
        "thumbnail_passed",
        "copy_passed",
    ):
        assert field in text
    assert "review.all_required_gates_passed" in text
    assert "HumanFinalReviewDecision.APPROVE" in text
    assert "HumanFinalReviewDecision.CHANGES_REQUESTED" in text
    assert "approved=True" not in text
    assert "approved=False" not in text


def test_structured_review_ui_preserves_manual_publication_boundary():
    text = (_repo_root() / "webui" / "product" / "review.py").read_text(encoding="utf-8")
    assert "No autoriza ni ejecuta publicación automática" in text


def test_public_control_center_exposes_only_structured_review_contract():
    parameters = inspect.signature(CentinelaControlCenter.review).parameters
    assert "review" in parameters
    assert "approved" not in parameters
    assert "reviewer" not in parameters
    assert "notes" not in parameters
    assert C3ResearchControlCenter.review is CentinelaControlCenter.review


@pytest.mark.parametrize(
    ("reviewer", "notes"),
    [
        ("", "review notes"),
        ("human-reviewer", ""),
    ],
)
def test_review_ui_builder_requires_human_identity_and_rationale(reviewer, notes):
    with pytest.raises(ValueError):
        _build_review(
            decision=HumanFinalReviewDecision.APPROVE,
            reviewer=reviewer,
            notes=notes,
            science_passed=True,
            visual_passed=True,
            audio_passed=True,
            subtitles_passed=True,
            rights_passed=True,
            thumbnail_passed=True,
            copy_passed=True,
        )


def test_product_review_7_of_7_reaches_final_approved(tmp_path):
    service = _make_service(tmp_path)
    try:
        project, _ = service.create_project("Review happy path", auto_start=False)
        _advance_to_review(service, project.project_id)

        review = _ui_review(all_gates=True)
        assert review.all_required_gates_passed is True

        service.review(project.project_id, review=review)

        approved = service.project(project.project_id)
        assert approved.state == ProjectState.FINAL_APPROVED
        assert approved.auto_publication is False
        assert service.store.load_project(project.project_id).metadata["auto_publication"] is False
    finally:
        service.shutdown()


@pytest.mark.parametrize("failed_gate", ["rights", "science"])
def test_product_review_missing_critical_gate_is_fail_closed(tmp_path, failed_gate):
    service = _make_service(tmp_path)
    try:
        project, _ = service.create_project("Review fail closed", auto_start=False)
        _advance_to_review(service, project.project_id)
        review = _ui_review(all_gates=True).model_copy(
            update={f"{failed_gate}_passed": False}
        )

        with pytest.raises(StageStateError, match="all seven"):
            service.review(project.project_id, review=review)

        assert service.project(project.project_id).state == ProjectState.READY_FOR_HUMAN_REVIEW
    finally:
        service.shutdown()


def test_product_review_legacy_boolean_approval_is_not_public_api(tmp_path):
    service = _make_service(tmp_path)
    try:
        project, _ = service.create_project("Legacy approval", auto_start=False)
        _advance_to_review(service, project.project_id)

        with pytest.raises(TypeError):
            service.review(
                project.project_id,
                approved=True,
                reviewer="legacy",
                notes="legacy approval",
            )

        assert service.project(project.project_id).state == ProjectState.READY_FOR_HUMAN_REVIEW
    finally:
        service.shutdown()


def test_product_review_rejects_non_record_payload(tmp_path):
    service = _make_service(tmp_path)
    try:
        project, _ = service.create_project("Invalid review", auto_start=False)
        _advance_to_review(service, project.project_id)

        with pytest.raises(TypeError, match="HumanFinalReviewRecord"):
            service.review(
                project.project_id,
                review={"decision": "APPROVE"},
            )

        assert service.project(project.project_id).state == ProjectState.READY_FOR_HUMAN_REVIEW
    finally:
        service.shutdown()


def test_product_review_wrong_state_is_fail_closed(tmp_path):
    service = _make_service(tmp_path)
    try:
        project, _ = service.create_project("Wrong state", auto_start=False)
        review = _ui_review(all_gates=True)

        with pytest.raises(StageStateError, match="READY_FOR_HUMAN_REVIEW"):
            service.review(project.project_id, review=review)

        assert service.project(project.project_id).state == ProjectState.DRAFT
    finally:
        service.shutdown()
