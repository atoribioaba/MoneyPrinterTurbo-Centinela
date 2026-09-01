from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.models.finalization_e2e import (
    HumanFinalReviewDecision,
    HumanFinalReviewRecord,
)
from app.services.centinela.orchestration import (
    JobStatus,
    ProjectState,
    ResourceClass,
)
from app.services.centinela.project_foundation import ArtifactStore
from app.services.centinela.production_spine import (
    LegacyArtifactIngestAdapter,
    PydanticServiceAdapter,
    ProductionSpine,
    ProductionSpineDB,
    ScheduleDisposition,
    SpineStage,
    StageArtifact,
    StageBinding,
    StageConflictError,
    StageDisposition,
    StageResult,
    StageStateError,
    STAGE_DESCRIPTORS,
)


class LeaseRecorder:
    def __init__(self):
        self.calls = []
        self.active = 0
        self.max_active = 0

    @contextmanager
    def acquire(self, component, resource_class, timeout_seconds):
        self.calls.append((component, resource_class, timeout_seconds))
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        try:
            yield
        finally:
            self.active -= 1


@pytest.fixture
def store(tmp_path: Path) -> ArtifactStore:
    return ArtifactStore(tmp_path / "centinela")


@pytest.fixture
def spine(store: ArtifactStore):
    service = ProductionSpine(store, resource_lease=LeaseRecorder(), max_workers=2)
    yield service
    service.shutdown()


def create_project(store: ArtifactStore, pid="p1"):
    return store.create_project("Project", project_id=pid)


def approved_review(*, reviewer="human", rationale="approved") -> HumanFinalReviewRecord:
    return HumanFinalReviewRecord(
        decision=HumanFinalReviewDecision.APPROVE,
        reviewer_ref=reviewer,
        rationale=rationale,
        decided_at_utc=datetime(2026, 8, 31, tzinfo=timezone.utc),
        science_passed=True,
        visual_passed=True,
        audio_passed=True,
        subtitles_passed=True,
        rights_passed=True,
        thumbnail_passed=True,
        copy_passed=True,
    )


def binding_for(stage: SpineStage, *, disposition=StageDisposition.COMPLETE):
    descriptor = STAGE_DESCRIPTORS[stage]

    def handler(context, payload):
        if disposition == StageDisposition.NEEDS_INPUT:
            return StageResult.needs_input("input required", details={"field": "x"})
        if disposition == StageDisposition.BLOCKED:
            return StageResult.blocked("blocked", details={"reason": "quality"})
        artifacts = [
            StageArtifact(
                artifact_type=artifact_type,
                payload={"stage": stage.value, "request": payload},
            )
            for artifact_type in descriptor.required_artifact_types
        ]
        return StageResult.complete(*artifacts, message=f"{stage.value} complete")

    return StageBinding(
        adapter_id=f"test_{stage.value.lower()}",
        handler=handler,
        resource_class=descriptor.minimum_resource_class,
    )


def run_stage(spine: ProductionSpine, project_id: str, stage: SpineStage, request=None):
    schedule = spine.schedule_stage(project_id, stage, request=request or {})
    assert schedule.job_id
    record = spine.wait(schedule.job_id, timeout=10)
    assert record.status == JobStatus.SUCCEEDED
    return record


def test_descriptors_cover_eight_automated_transitions():
    assert set(STAGE_DESCRIPTORS) == set(SpineStage)
    assert len(STAGE_DESCRIPTORS) == 8


def test_stage_progression_matches_r2_states():
    pairs = [(d.source_state, d.target_state) for d in STAGE_DESCRIPTORS.values()]
    assert pairs[0] == (ProjectState.DRAFT, ProjectState.RESEARCH_READY)
    assert pairs[-1] == (ProjectState.FINAL_APPROVED, ProjectState.PUBLICATION_PACKAGE_READY)


def test_each_stage_requires_real_artifact_type():
    assert STAGE_DESCRIPTORS[SpineStage.RESEARCH].required_artifact_types == ("fact_lock",)
    assert STAGE_DESCRIPTORS[SpineStage.MEDIA].required_artifact_types == ("material_selection",)
    assert STAGE_DESCRIPTORS[SpineStage.VIDEO_BASE].required_artifact_types == ("video_base_manifest",)


def test_missing_adapter_moves_project_to_needs_input(spine, store):
    create_project(store)
    result = spine.schedule_stage("p1", SpineStage.RESEARCH)
    assert result.disposition == ScheduleDisposition.NEEDS_INPUT
    assert spine.state_machine.current_state("p1") == ProjectState.NEEDS_INPUT


def test_missing_adapter_status_names_future_owner(spine, store):
    create_project(store)
    spine.schedule_stage("p1", SpineStage.RESEARCH)
    status = spine.project_status("p1")
    assert status.next_stage == SpineStage.RESEARCH
    assert "Register RESEARCH adapter" in status.next_action


def test_registering_adapter_resumes_needs_input_and_runs(spine, store):
    create_project(store)
    spine.schedule_stage("p1", SpineStage.RESEARCH)
    spine.register_adapter(SpineStage.RESEARCH, binding_for(SpineStage.RESEARCH))
    record = run_stage(spine, "p1", SpineStage.RESEARCH)
    assert record.result["state"] == ProjectState.RESEARCH_READY.value
    assert spine.state_machine.current_state("p1") == ProjectState.RESEARCH_READY


def test_complete_stage_persists_required_output_and_receipt(spine, store):
    create_project(store)
    spine.register_adapter(SpineStage.RESEARCH, binding_for(SpineStage.RESEARCH))
    record = run_stage(spine, "p1", SpineStage.RESEARCH)
    outputs = record.result["output_artifact_ids"]
    assert len(outputs) == 1
    assert store.get_artifact("p1", outputs[0]).artifact_type == "fact_lock"
    receipt = store.get_artifact("p1", record.result["receipt_artifact_id"])
    assert receipt.artifact_type == "spine_stage_receipt"


def test_receipt_contains_output_sha256(spine, store):
    create_project(store)
    spine.register_adapter(SpineStage.RESEARCH, binding_for(SpineStage.RESEARCH))
    record = run_stage(spine, "p1", SpineStage.RESEARCH)
    receipt = store.read_json("p1", record.result["receipt_artifact_id"])
    output_id = record.result["output_artifact_ids"][0]
    assert receipt["output_sha256"][output_id] == store.get_artifact("p1", output_id).sha256


def test_state_advances_only_after_artifact_persistence(spine, store, monkeypatch):
    create_project(store)
    spine.register_adapter(SpineStage.RESEARCH, binding_for(SpineStage.RESEARCH))
    original = store.put_json

    def fail(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(store, "put_json", fail)
    schedule = spine.schedule_stage("p1", SpineStage.RESEARCH)
    record = spine.wait(schedule.job_id, timeout=10)
    assert record.status == JobStatus.FAILED
    assert spine.state_machine.current_state("p1") == ProjectState.DRAFT
    monkeypatch.setattr(store, "put_json", original)


def test_missing_required_output_fails_without_state_advance(spine, store):
    create_project(store)

    def bad(context, payload):
        return StageResult.complete(StageArtifact("wrong_type", payload={"x": 1}))

    spine.register_adapter(
        SpineStage.RESEARCH,
        StageBinding("bad", bad, ResourceClass.LIGHT),
    )
    schedule = spine.schedule_stage("p1", SpineStage.RESEARCH)
    record = spine.wait(schedule.job_id, timeout=10)
    assert record.status == JobStatus.FAILED
    assert record.error_type == "StageOutputError"
    assert spine.state_machine.current_state("p1") == ProjectState.DRAFT


def test_needs_input_result_is_successful_job_but_side_state(spine, store):
    create_project(store)
    spine.register_adapter(
        SpineStage.RESEARCH,
        binding_for(SpineStage.RESEARCH, disposition=StageDisposition.NEEDS_INPUT),
    )
    schedule = spine.schedule_stage("p1", SpineStage.RESEARCH)
    record = spine.wait(schedule.job_id, timeout=10)
    assert record.status == JobStatus.SUCCEEDED
    assert record.result["disposition"] == "NEEDS_INPUT"
    assert spine.state_machine.current_state("p1") == ProjectState.NEEDS_INPUT


def test_blocked_result_moves_to_blocked(spine, store):
    create_project(store)
    spine.register_adapter(
        SpineStage.RESEARCH,
        binding_for(SpineStage.RESEARCH, disposition=StageDisposition.BLOCKED),
    )
    schedule = spine.schedule_stage("p1", SpineStage.RESEARCH)
    record = spine.wait(schedule.job_id, timeout=10)
    assert record.status == JobStatus.SUCCEEDED
    assert spine.state_machine.current_state("p1") == ProjectState.BLOCKED


def test_complete_pipeline_through_publication_package(spine, store):
    create_project(store)
    stages_before_review = [
        SpineStage.RESEARCH,
        SpineStage.SCRIPT,
        SpineStage.SCENES,
        SpineStage.MEDIA,
        SpineStage.AUDIO,
        SpineStage.VIDEO_BASE,
        SpineStage.REVIEW_PREP,
    ]
    for stage in stages_before_review:
        spine.register_adapter(stage, binding_for(stage))
        run_stage(spine, "p1", stage)
    assert spine.state_machine.current_state("p1") == ProjectState.READY_FOR_HUMAN_REVIEW
    decision = spine.record_human_review("p1", review=approved_review())
    assert decision.metadata["decision"] == HumanFinalReviewDecision.APPROVE.value
    assert decision.metadata["all_required_gates_passed"] is True
    assert spine.state_machine.current_state("p1") == ProjectState.FINAL_APPROVED
    spine.register_adapter(SpineStage.PUBLICATION_PACKAGE, binding_for(SpineStage.PUBLICATION_PACKAGE))
    run_stage(spine, "p1", SpineStage.PUBLICATION_PACKAGE)
    assert spine.state_machine.current_state("p1") == ProjectState.PUBLICATION_PACKAGE_READY


def test_publication_package_depends_on_approved_human_decision(spine, store):
    create_project(store)
    for stage in [
        SpineStage.RESEARCH, SpineStage.SCRIPT, SpineStage.SCENES, SpineStage.MEDIA,
        SpineStage.AUDIO, SpineStage.VIDEO_BASE, SpineStage.REVIEW_PREP,
    ]:
        spine.register_adapter(stage, binding_for(stage))
        run_stage(spine, "p1", stage)
    decision = spine.record_human_review("p1", review=approved_review())
    spine.register_adapter(SpineStage.PUBLICATION_PACKAGE, binding_for(SpineStage.PUBLICATION_PACKAGE))
    record = run_stage(spine, "p1", SpineStage.PUBLICATION_PACKAGE)
    output = store.get_artifact("p1", record.result["output_artifact_ids"][0])
    assert decision.artifact_id in output.input_artifact_ids


def test_rejected_human_review_needs_input(spine, store):
    create_project(store)
    for stage in [
        SpineStage.RESEARCH, SpineStage.SCRIPT, SpineStage.SCENES, SpineStage.MEDIA,
        SpineStage.AUDIO, SpineStage.VIDEO_BASE, SpineStage.REVIEW_PREP,
    ]:
        spine.register_adapter(stage, binding_for(stage))
        run_stage(spine, "p1", stage)
    spine.record_human_review("p1", approved=False, reviewer="human", notes="revise")
    assert spine.state_machine.current_state("p1") == ProjectState.NEEDS_INPUT


def test_rejected_review_can_be_explicitly_reviewed_again(spine, store):
    create_project(store)
    for stage in [
        SpineStage.RESEARCH, SpineStage.SCRIPT, SpineStage.SCENES, SpineStage.MEDIA,
        SpineStage.AUDIO, SpineStage.VIDEO_BASE, SpineStage.REVIEW_PREP,
    ]:
        spine.register_adapter(stage, binding_for(stage))
        run_stage(spine, "p1", stage)
    spine.record_human_review("p1", approved=False, reviewer="human", notes="revise")
    spine.record_human_review("p1", review=approved_review(rationale="now approved"))
    assert spine.state_machine.current_state("p1") == ProjectState.FINAL_APPROVED


def test_publication_is_never_automatic(spine, store):
    create_project(store)
    status = spine.project_status("p1")
    assert status.auto_publication is False


def test_binding_with_auto_publication_is_rejected(spine):
    with pytest.raises(ValueError, match="automatic publication"):
        spine.register_adapter(
            SpineStage.RESEARCH,
            StageBinding("unsafe", lambda c, p: StageResult.needs_input("x"), ResourceClass.LIGHT, auto_publication=True),
        )


def test_network_adapter_requires_explicit_opt_in(spine):
    with pytest.raises(ValueError, match="network adapters"):
        spine.register_adapter(
            SpineStage.RESEARCH,
            StageBinding("network", lambda c, p: StageResult.needs_input("x"), ResourceClass.LIGHT, invokes_network=True),
        )


def test_exclusive_adapter_requires_explicit_opt_in(spine):
    with pytest.raises(ValueError, match="EXCLUSIVE adapters"):
        spine.register_adapter(
            SpineStage.RESEARCH,
            StageBinding("exclusive", lambda c, p: StageResult.needs_input("x"), ResourceClass.EXCLUSIVE),
        )


def test_stage_cannot_underdeclare_resource_class(spine):
    with pytest.raises(ValueError, match="requires at least MEDIUM"):
        spine.register_adapter(
            SpineStage.SCRIPT,
            StageBinding("too_light", lambda c, p: StageResult.needs_input("x"), ResourceClass.LIGHT),
        )


def test_resource_lease_is_used(spine, store):
    create_project(store)
    spine.register_adapter(SpineStage.RESEARCH, binding_for(SpineStage.RESEARCH))
    run_stage(spine, "p1", SpineStage.RESEARCH)
    assert spine.resource_lease.calls
    assert spine.resource_lease.calls[0][1] == ResourceClass.LIGHT


def test_same_active_job_is_idempotently_returned(store):
    create_project(store)
    lease = LeaseRecorder()
    service = ProductionSpine(store, resource_lease=lease, max_workers=1)
    gate = threading.Event()

    def slow(context, payload):
        gate.wait(5)
        return StageResult.complete(StageArtifact("fact_lock", payload={"ok": True}))

    service.register_adapter(SpineStage.RESEARCH, StageBinding("slow", slow, ResourceClass.LIGHT))
    first = service.schedule_stage("p1", SpineStage.RESEARCH)
    second = service.schedule_stage("p1", SpineStage.RESEARCH)
    assert second.disposition == ScheduleDisposition.EXISTING_JOB
    assert second.job_id == first.job_id
    gate.set()
    assert service.wait(first.job_id, timeout=10).status == JobStatus.SUCCEEDED
    service.shutdown()


def test_different_inputs_conflict_while_stage_active(store):
    create_project(store)
    service = ProductionSpine(store, resource_lease=LeaseRecorder(), max_workers=1)
    gate = threading.Event()

    def slow(context, payload):
        gate.wait(5)
        return StageResult.complete(StageArtifact("fact_lock", payload={"ok": True}))

    service.register_adapter(SpineStage.RESEARCH, StageBinding("slow", slow, ResourceClass.LIGHT))
    first = service.schedule_stage("p1", SpineStage.RESEARCH, request={"v": 1})
    with pytest.raises(StageConflictError):
        service.schedule_stage("p1", SpineStage.RESEARCH, request={"v": 2})
    gate.set()
    service.wait(first.job_id, timeout=10)
    service.shutdown()


def test_partial_unique_index_blocks_cross_process_duplicate(store):
    create_project(store)
    ProductionSpineDB(store)
    with sqlite3.connect(store.db_path) as connection:
        columns = (
            "job_id,project_id,job_type,status,progress,message,resource_class,payload_json,"
            "result_json,error_type,error_message,created_at,started_at,finished_at,updated_at,"
            "owner_id,retry_of_job_id,attempt"
        )
        values = (
            "j1", "p1", "centinela.spine.research", "QUEUED", 0, None, "LIGHT", "{}",
            None, None, None, "2026-01-01T00:00:00Z", None, None, "2026-01-01T00:00:00Z",
            None, None, 1,
        )
        connection.execute(f"INSERT INTO jobs({columns}) VALUES ({','.join('?' for _ in values)})", values)
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(f"INSERT INTO jobs({columns}) VALUES ({','.join('?' for _ in values)})", ("j2", *values[1:]))


def test_stage_wrong_state_is_rejected(spine, store):
    create_project(store)
    spine.register_adapter(SpineStage.SCRIPT, binding_for(SpineStage.SCRIPT))
    with pytest.raises(StageStateError):
        spine.schedule_stage("p1", SpineStage.SCRIPT)


def test_input_artifact_lineage_is_preserved(spine, store):
    create_project(store)
    seed = store.put_json("p1", "seed", {"x": 1}, producer="test")
    spine.register_adapter(SpineStage.RESEARCH, binding_for(SpineStage.RESEARCH))
    schedule = spine.schedule_stage("p1", SpineStage.RESEARCH, input_artifact_ids=(seed.artifact_id,))
    completed = spine.wait(schedule.job_id, timeout=10)
    output = store.get_artifact("p1", completed.result["output_artifact_ids"][0])
    assert seed.artifact_id in output.input_artifact_ids


def test_next_stage_output_depends_on_previous_receipt(spine, store):
    create_project(store)
    spine.register_adapter(SpineStage.RESEARCH, binding_for(SpineStage.RESEARCH))
    research = run_stage(spine, "p1", SpineStage.RESEARCH)
    research_receipt = research.result["receipt_artifact_id"]
    spine.register_adapter(SpineStage.SCRIPT, binding_for(SpineStage.SCRIPT))
    script = run_stage(spine, "p1", SpineStage.SCRIPT)
    output = store.get_artifact("p1", script.result["output_artifact_ids"][0])
    assert research_receipt in output.input_artifact_ids


def test_receipt_reuse_after_transition_failure_avoids_second_adapter_run(spine, store, monkeypatch):
    create_project(store)
    calls = {"count": 0}

    def handler(context, payload):
        calls["count"] += 1
        return StageResult.complete(StageArtifact("fact_lock", payload={"n": calls["count"]}))

    spine.register_adapter(SpineStage.RESEARCH, StageBinding("once", handler, ResourceClass.LIGHT))
    original = spine.state_machine.transition
    failed = {"done": False}

    def transition(*args, **kwargs):
        target = args[1] if len(args) > 1 else None
        if target == ProjectState.RESEARCH_READY and not failed["done"]:
            failed["done"] = True
            raise RuntimeError("simulated state-write failure")
        return original(*args, **kwargs)

    monkeypatch.setattr(spine.state_machine, "transition", transition)
    first = spine.schedule_stage("p1", SpineStage.RESEARCH)
    assert spine.wait(first.job_id, timeout=10).status == JobStatus.FAILED
    assert spine.state_machine.current_state("p1") == ProjectState.DRAFT
    monkeypatch.setattr(spine.state_machine, "transition", original)
    second = spine.schedule_stage("p1", SpineStage.RESEARCH)
    result = spine.wait(second.job_id, timeout=10)
    assert result.status == JobStatus.SUCCEEDED
    assert result.result["disposition"] == "REUSED"
    assert calls["count"] == 1


def test_corrupt_receipt_is_not_reused(spine, store):
    create_project(store)
    spine.register_adapter(SpineStage.RESEARCH, binding_for(SpineStage.RESEARCH))
    fingerprint = spine._fingerprint("p1", SpineStage.RESEARCH, {}, ())
    store.put_json(
        "p1", "spine_stage_receipt",
        {"output_artifact_ids": ["missing"]},
        producer="test",
        metadata={"spine_stage": "RESEARCH", "spine_fingerprint": fingerprint},
    )
    assert spine._matching_receipt("p1", SpineStage.RESEARCH, fingerprint) is None


def test_stage_request_rejects_secret_like_keys(spine, store):
    create_project(store)
    spine.register_adapter(SpineStage.RESEARCH, binding_for(SpineStage.RESEARCH))
    with pytest.raises(ValueError, match="secret-like key"):
        spine.schedule_stage("p1", SpineStage.RESEARCH, request={"api_key": "x"})


def test_legacy_ingest_adapter_copies_real_file(tmp_path, spine, store):
    create_project(store)
    source = tmp_path / "fact.json"
    source.write_text('{"fact":1}', encoding="utf-8")
    adapter = LegacyArtifactIngestAdapter(required_types=("fact_lock",))
    spine.register_adapter(
        SpineStage.RESEARCH,
        StageBinding("legacy", adapter, ResourceClass.LIGHT),
    )
    schedule = spine.schedule_stage("p1", SpineStage.RESEARCH, request={"files": {"fact_lock": str(source)}})
    record = spine.wait(schedule.job_id, timeout=10)
    output = store.get_artifact("p1", record.result["output_artifact_ids"][0])
    assert store.read_bytes("p1", output.artifact_id) == source.read_bytes()
    assert source.is_file()


def test_legacy_ingest_adapter_needs_input_when_file_missing(spine, store):
    create_project(store)
    adapter = LegacyArtifactIngestAdapter(required_types=("fact_lock",))
    spine.register_adapter(SpineStage.RESEARCH, StageBinding("legacy", adapter, ResourceClass.LIGHT))
    schedule = spine.schedule_stage("p1", SpineStage.RESEARCH, request={"files": {}})
    record = spine.wait(schedule.job_id, timeout=10)
    assert record.result["disposition"] == "NEEDS_INPUT"


def test_pydantic_service_adapter_serializes_model():
    class Request:
        @classmethod
        def model_validate(cls, raw):
            return raw

    class Result:
        def model_dump(self, mode="json"):
            return {"ok": True}

    adapter = PydanticServiceAdapter(request_model=Request, service=lambda req: Result(), artifact_type="fact_lock")
    result = adapter(None, {"request": {"x": 1}})
    assert result.artifacts[0].payload == {"ok": True}


def test_pydantic_service_adapter_needs_request():
    class Request:
        pass
    adapter = PydanticServiceAdapter(request_model=Request, service=lambda req: {}, artifact_type="fact_lock")
    assert adapter(None, {}).disposition == StageDisposition.NEEDS_INPUT


def test_project_status_reports_explicit_human_review(spine, store):
    create_project(store)
    manifest = store.load_project("p1")
    manifest.status = ProjectState.READY_FOR_HUMAN_REVIEW.value
    store.save_project(manifest)
    # Initialize R2 head from manifest state.
    status = spine.project_status("p1")
    assert status.next_action == "Explicit human review required"
    assert status.auto_publication is False


def test_production_spine_sqlite_integrity(spine):
    assert spine.db.integrity_check() == "ok"


def test_spine_meta_schema_version_is_one(store):
    ProductionSpineDB(store)
    with sqlite3.connect(store.db_path) as connection:
        value = connection.execute("SELECT value FROM production_spine_meta WHERE key='schema_version'").fetchone()[0]
    assert value == "1"


def test_no_wangp_adapter_is_registered_by_default(spine):
    assert all(binding.adapter_id.casefold().find("wangp") < 0 for binding in spine._bindings.values())


def test_no_adapter_is_registered_by_default(spine):
    assert spine._bindings == {}


def test_recover_keeps_queued_stage_job_resumeable(store):
    create_project(store)
    service = ProductionSpine(store, resource_lease=LeaseRecorder(), max_workers=1)
    service.register_adapter(SpineStage.RESEARCH, binding_for(SpineStage.RESEARCH))
    schedule = service.schedule_stage("p1", SpineStage.RESEARCH, auto_start=False)
    assert service.jobs.get_job(schedule.job_id).status == JobStatus.QUEUED
    recovered = service.recover(project_id="p1")
    assert schedule.job_id in recovered["resumed_queued_job_ids"]
    assert service.wait(schedule.job_id, timeout=10).status == JobStatus.SUCCEEDED
    service.shutdown()


def test_job_failure_persists_structured_error_not_traceback(spine, store):
    create_project(store)

    def boom(context, payload):
        raise RuntimeError("controlled failure")

    spine.register_adapter(SpineStage.RESEARCH, StageBinding("boom", boom, ResourceClass.LIGHT))
    schedule = spine.schedule_stage("p1", SpineStage.RESEARCH)
    record = spine.wait(schedule.job_id, timeout=10)
    assert record.status == JobStatus.FAILED
    assert record.error_type == "RuntimeError"
    assert record.error_message == "controlled failure"
    assert "Traceback" not in record.error_message


def test_terminal_publication_ready_status_is_manual(spine, store):
    create_project(store)
    manifest = store.load_project("p1")
    manifest.status = ProjectState.PUBLICATION_PACKAGE_READY.value
    store.save_project(manifest)
    status = spine.project_status("p1")
    assert "Manual publication" in status.next_action
    assert status.auto_publication is False
