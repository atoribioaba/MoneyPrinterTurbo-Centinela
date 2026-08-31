from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path

import pytest

from app.services.centinela.orchestration import (
    JobManager,
    JobNotFoundError,
    JobStateError,
    JobStatus,
    OrchestrationDB,
    OrchestrationPersistenceError,
    ProjectState,
    ProjectStateMachine,
    ResourceClass,
    StateConflictError,
    StateIntegrityError,
    TransitionRecoveryRequired,
    InvalidTransitionError,
)
from app.services.centinela.orchestration.state_machine import (
    ProjectStateMachine as RawProjectStateMachine,
)
from app.services.centinela.project_foundation import ArtifactStore


@pytest.fixture()
def store(tmp_path: Path) -> ArtifactStore:
    return ArtifactStore(tmp_path / "centinela")


@pytest.fixture()
def project(store: ArtifactStore):
    return store.create_project(
        "Project",
        project_id="project-1",
    )


def test_orchestration_schema_bootstraps(store, project):
    db = OrchestrationDB(store)
    assert db.integrity_check() == "ok"
    with db.connect() as connection:
        version = connection.execute(
            "SELECT value FROM orchestration_meta WHERE key='schema_version'"
        ).fetchone()[0]
    assert version == "1"


def test_orchestration_schema_is_idempotent(store, project):
    OrchestrationDB(store)
    db = OrchestrationDB(store)
    assert db.integrity_check() == "ok"


def test_unversioned_partial_orchestration_schema_is_refused(store, project):
    with sqlite3.connect(store.db_path) as connection:
        connection.execute("CREATE TABLE jobs(job_id TEXT PRIMARY KEY)")
    with pytest.raises(OrchestrationPersistenceError, match="unversioned"):
        OrchestrationDB(store)


def test_state_machine_initial_state_is_draft(store, project):
    machine = ProjectStateMachine(store)
    assert machine.current_state(project.project_id) == ProjectState.DRAFT


def test_linear_state_progression(store, project):
    machine = RawProjectStateMachine(store)
    expected = [
        ProjectState.RESEARCH_READY,
        ProjectState.SCRIPT_READY,
        ProjectState.SCENES_READY,
        ProjectState.MEDIA_READY,
        ProjectState.AUDIO_READY,
        ProjectState.VIDEO_BASE_READY,
        ProjectState.READY_FOR_HUMAN_REVIEW,
        ProjectState.FINAL_APPROVED,
        ProjectState.PUBLICATION_PACKAGE_READY,
    ]
    for target in expected:
        transition = machine.transition(
            project.project_id,
            target,
            reason=f"reach {target.value}",
            actor="test",
        )
        assert transition.to_state == target
    assert machine.current_state(project.project_id) == ProjectState.PUBLICATION_PACKAGE_READY
    assert [item.revision for item in machine.history(project.project_id)] == list(
        range(1, 10)
    )


def test_skip_forward_transition_is_rejected(store, project):
    machine = ProjectStateMachine(store)
    with pytest.raises(InvalidTransitionError):
        machine.transition(
            project.project_id,
            ProjectState.SCRIPT_READY,
            reason="skip",
            actor="test",
        )


def test_backward_transition_is_rejected(store, project):
    machine = ProjectStateMachine(store)
    machine.transition(
        project.project_id,
        ProjectState.RESEARCH_READY,
        reason="research",
        actor="test",
    )
    with pytest.raises(InvalidTransitionError):
        machine.transition(
            project.project_id,
            ProjectState.DRAFT,
            reason="back",
            actor="test",
        )


def test_expected_state_conflict_is_rejected(store, project):
    machine = ProjectStateMachine(store)
    with pytest.raises(StateConflictError):
        machine.transition(
            project.project_id,
            ProjectState.RESEARCH_READY,
            reason="research",
            actor="test",
            expected_state=ProjectState.SCRIPT_READY,
        )


@pytest.mark.parametrize(
    "side_state",
    [
        ProjectState.BLOCKED,
        ProjectState.NEEDS_INPUT,
        ProjectState.FAILED,
        ProjectState.CANCELLED,
    ],
)
def test_side_states_are_reachable_from_progression(store, project, side_state):
    machine = ProjectStateMachine(store)
    transition = machine.transition(
        project.project_id,
        side_state,
        reason="side",
        actor="test",
    )
    assert transition.to_state == side_state


@pytest.mark.parametrize(
    "side_state",
    [ProjectState.BLOCKED, ProjectState.NEEDS_INPUT],
)
def test_recoverable_side_state_resumes_only_to_previous_state(store, project, side_state):
    machine = ProjectStateMachine(store)
    machine.transition(
        project.project_id,
        ProjectState.RESEARCH_READY,
        reason="research",
        actor="test",
    )
    machine.transition(
        project.project_id,
        side_state,
        reason="pause",
        actor="test",
    )
    with pytest.raises(InvalidTransitionError):
        machine.transition(
            project.project_id,
            ProjectState.SCRIPT_READY,
            reason="wrong resume",
            actor="test",
        )
    machine.transition(
        project.project_id,
        ProjectState.RESEARCH_READY,
        reason="resume",
        actor="test",
    )
    assert machine.current_state(project.project_id) == ProjectState.RESEARCH_READY


@pytest.mark.parametrize(
    "terminal",
    [
        ProjectState.FAILED,
        ProjectState.CANCELLED,
    ],
)
def test_terminal_side_states_cannot_transition(store, project, terminal):
    machine = ProjectStateMachine(store)
    machine.transition(
        project.project_id,
        terminal,
        reason="terminal",
        actor="test",
    )
    with pytest.raises(InvalidTransitionError):
        machine.transition(
            project.project_id,
            ProjectState.DRAFT,
            reason="no",
            actor="test",
        )


def test_publication_package_ready_is_terminal(store, project):
    machine = RawProjectStateMachine(store)
    for target in (
        ProjectState.RESEARCH_READY,
        ProjectState.SCRIPT_READY,
        ProjectState.SCENES_READY,
        ProjectState.MEDIA_READY,
        ProjectState.AUDIO_READY,
        ProjectState.VIDEO_BASE_READY,
        ProjectState.READY_FOR_HUMAN_REVIEW,
        ProjectState.FINAL_APPROVED,
        ProjectState.PUBLICATION_PACKAGE_READY,
    ):
        machine.transition(
            project.project_id,
            target,
            reason="advance",
            actor="test",
        )
    with pytest.raises(InvalidTransitionError):
        machine.transition(
            project.project_id,
            ProjectState.BLOCKED,
            reason="too late",
            actor="test",
        )


def test_transition_guard_can_block(store, project):
    def guard(manifest, current, target, metadata):
        raise ValueError("missing fact lock")

    machine = ProjectStateMachine(
        store,
        guards={ProjectState.RESEARCH_READY: [guard]},
    )
    with pytest.raises(ValueError, match="fact lock"):
        machine.transition(
            project.project_id,
            ProjectState.RESEARCH_READY,
            reason="research",
            actor="test",
        )
    assert machine.current_state(project.project_id) == ProjectState.DRAFT


def test_transition_history_persists_across_instances(store, project):
    first = ProjectStateMachine(store)
    first.transition(
        project.project_id,
        ProjectState.RESEARCH_READY,
        reason="research",
        actor="test",
        metadata={"source": "test"},
    )
    second = ProjectStateMachine(store)
    history = second.history(project.project_id)
    assert len(history) == 1
    assert history[0].metadata == {"source": "test"}


def test_transition_metadata_rejects_secret_keys(store, project):
    machine = ProjectStateMachine(store)
    with pytest.raises(ValueError, match="secret-like"):
        machine.transition(
            project.project_id,
            ProjectState.RESEARCH_READY,
            reason="research",
            actor="test",
            metadata={"api_key": "do-not-store"},
        )


def test_pending_transition_recovery_finalizes_manifest_target(store, project):
    machine = ProjectStateMachine(store)
    machine._ensure_head(project.project_id)
    transition_id = "pending-finalize"
    now = "2026-08-23T00:00:00Z"
    with machine.db.immediate() as connection:
        connection.execute(
            """
            INSERT INTO project_transition_intents(
                transition_id, project_id, from_state, to_state,
                reason, actor, metadata_json, created_at, status, resolved_at
            ) VALUES (?, ?, 'DRAFT', 'RESEARCH_READY', 'recover', 'test', '{}', ?, 'PENDING', NULL)
            """,
            (transition_id, project.project_id, now),
        )
        connection.execute(
            "UPDATE project_state_heads SET pending_transition_id=? WHERE project_id=?",
            (transition_id, project.project_id),
        )
    manifest = store.load_project(project.project_id)
    manifest.status = "RESEARCH_READY"
    store.save_project(manifest)
    outcome = machine.recover_pending_transitions(project.project_id)
    assert outcome[0]["outcome"] == "FINALIZED"
    assert machine.current_state(project.project_id) == ProjectState.RESEARCH_READY
    assert machine.history(project.project_id)[0].transition_id == transition_id


def test_pending_transition_recovery_aborts_if_manifest_unchanged(store, project):
    machine = ProjectStateMachine(store)
    machine._ensure_head(project.project_id)
    transition_id = "pending-abort"
    now = "2026-08-23T00:00:00Z"
    with machine.db.immediate() as connection:
        connection.execute(
            """
            INSERT INTO project_transition_intents(
                transition_id, project_id, from_state, to_state,
                reason, actor, metadata_json, created_at, status, resolved_at
            ) VALUES (?, ?, 'DRAFT', 'RESEARCH_READY', 'recover', 'test', '{}', ?, 'PENDING', NULL)
            """,
            (transition_id, project.project_id, now),
        )
        connection.execute(
            "UPDATE project_state_heads SET pending_transition_id=? WHERE project_id=?",
            (transition_id, project.project_id),
        )
    outcome = machine.recover_pending_transitions(project.project_id)
    assert outcome[0]["outcome"] == "ABORTED"
    assert machine.current_state(project.project_id) == ProjectState.DRAFT
    assert machine.history(project.project_id) == []


def test_pending_transition_conflicting_manifest_is_integrity_error(store, project):
    machine = ProjectStateMachine(store)
    machine._ensure_head(project.project_id)
    transition_id = "pending-conflict"
    now = "2026-08-23T00:00:00Z"
    with machine.db.immediate() as connection:
        connection.execute(
            """
            INSERT INTO project_transition_intents(
                transition_id, project_id, from_state, to_state,
                reason, actor, metadata_json, created_at, status, resolved_at
            ) VALUES (?, ?, 'DRAFT', 'RESEARCH_READY', 'recover', 'test', '{}', ?, 'PENDING', NULL)
            """,
            (transition_id, project.project_id, now),
        )
        connection.execute(
            "UPDATE project_state_heads SET pending_transition_id=? WHERE project_id=?",
            (transition_id, project.project_id),
        )
    manifest = store.load_project(project.project_id)
    manifest.status = "SCRIPT_READY"
    store.save_project(manifest)
    with pytest.raises(StateIntegrityError):
        machine.recover_pending_transitions(project.project_id)


def test_current_state_refuses_pending_transition(store, project):
    machine = ProjectStateMachine(store)
    machine._ensure_head(project.project_id)
    with machine.db.immediate() as connection:
        connection.execute(
            """
            INSERT INTO project_transition_intents(
                transition_id, project_id, from_state, to_state,
                reason, actor, metadata_json, created_at, status, resolved_at
            ) VALUES ('pending', ?, 'DRAFT', 'RESEARCH_READY', 'x', 'test', '{}',
                      '2026-08-23T00:00:00Z', 'PENDING', NULL)
            """,
            (project.project_id,),
        )
        connection.execute(
            "UPDATE project_state_heads SET pending_transition_id='pending' WHERE project_id=?",
            (project.project_id,),
        )
    with pytest.raises(TransitionRecoveryRequired):
        machine.current_state(project.project_id)


def test_job_without_handler_stays_queued(store, project):
    with JobManager(store, max_workers=1) as manager:
        job = manager.enqueue(
            project.project_id,
            "research",
            auto_start=True,
        )
        assert job.status == JobStatus.QUEUED
        assert manager.resume_queued() == []


def test_register_handler_then_resume_queued(store, project):
    with JobManager(store, max_workers=1) as manager:
        job = manager.enqueue(
            project.project_id,
            "research",
            auto_start=False,
        )
        manager.register_handler(
            "research",
            lambda context, payload: {"ok": True},
        )
        assert manager.resume_queued() == [job.job_id]
        done = manager.wait(job.job_id, timeout=5)
        assert done.status == JobStatus.SUCCEEDED


def test_successful_job_persists_progress_result_and_events(store, project):
    with JobManager(store, max_workers=1) as manager:
        def handler(context, payload):
            context.report_progress(25, "quarter")
            context.report_progress(75, "three quarters")
            return {"value": payload["value"] + 1}

        manager.register_handler("compute", handler)
        job = manager.enqueue(
            project.project_id,
            "compute",
            payload={"value": 4},
        )
        done = manager.wait(job.job_id, timeout=5)
        assert done.status == JobStatus.SUCCEEDED
        assert done.progress == 100
        assert done.result == {"value": 5}
        assert [event.status for event in manager.events(job.job_id)] == [
            JobStatus.QUEUED,
            JobStatus.RUNNING,
            JobStatus.RUNNING,
            JobStatus.RUNNING,
            JobStatus.SUCCEEDED,
        ]


def test_job_progress_cannot_decrease(store, project):
    with JobManager(store, max_workers=1) as manager:
        def handler(context, payload):
            context.report_progress(50)
            context.report_progress(40)

        manager.register_handler("bad-progress", handler)
        job = manager.enqueue(project.project_id, "bad-progress")
        done = manager.wait(job.job_id, timeout=5)
        assert done.status == JobStatus.FAILED
        assert done.error_type == "JobStateError"


def test_job_progress_100_reserved_for_success(store, project):
    with JobManager(store, max_workers=1) as manager:
        def handler(context, payload):
            context.report_progress(100)

        manager.register_handler("bad-100", handler)
        job = manager.enqueue(project.project_id, "bad-100")
        done = manager.wait(job.job_id, timeout=5)
        assert done.status == JobStatus.FAILED
        assert done.error_type == "ValueError"


def test_job_failure_is_structured_without_traceback(store, project):
    with JobManager(store, max_workers=1) as manager:
        def handler(context, payload):
            raise RuntimeError("boom")

        manager.register_handler("failure", handler)
        job = manager.enqueue(project.project_id, "failure")
        done = manager.wait(job.job_id, timeout=5)
        assert done.status == JobStatus.FAILED
        assert done.error_type == "RuntimeError"
        assert done.error_message == "boom"
        assert "Traceback" not in json.dumps(done.to_dict())


def test_job_payload_rejects_secret_keys(store, project):
    with JobManager(store, max_workers=1) as manager:
        with pytest.raises(ValueError, match="secret-like"):
            manager.enqueue(
                project.project_id,
                "research",
                payload={"api_token": "secret"},
            )


def test_job_result_rejects_secret_keys_and_fails_job(store, project):
    with JobManager(store, max_workers=1) as manager:
        manager.register_handler(
            "bad-result",
            lambda context, payload: {"password": "secret"},
        )
        job = manager.enqueue(project.project_id, "bad-result")
        done = manager.wait(job.job_id, timeout=5)
        assert done.status == JobStatus.FAILED
        assert done.error_type == "ValueError"


def test_queued_job_can_be_cancelled(store, project):
    with JobManager(store, max_workers=1) as manager:
        job = manager.enqueue(
            project.project_id,
            "queued",
            auto_start=False,
        )
        assert manager.request_cancel(job.job_id) is True
        assert manager.get_job(job.job_id).status == JobStatus.CANCELLED
        assert manager.request_cancel(job.job_id) is False


def test_running_job_cancels_cooperatively(store, project):
    entered = threading.Event()
    release = threading.Event()

    with JobManager(store, max_workers=1) as manager:
        def handler(context, payload):
            entered.set()
            assert release.wait(5)
            context.check_cancelled()
            return {"should": "not happen"}

        manager.register_handler("cancel", handler)
        job = manager.enqueue(project.project_id, "cancel")
        assert entered.wait(5)
        assert manager.request_cancel(job.job_id) is True
        assert manager.get_job(job.job_id).status == JobStatus.CANCEL_REQUESTED
        release.set()
        done = manager.wait(job.job_id, timeout=5)
        assert done.status == JobStatus.CANCELLED


def test_retry_creates_new_immutable_job(store, project):
    with JobManager(store, max_workers=1) as manager:
        manager.register_handler(
            "failure",
            lambda context, payload: (_ for _ in ()).throw(RuntimeError("boom")),
        )
        original = manager.enqueue(project.project_id, "failure")
        failed = manager.wait(original.job_id, timeout=5)
        assert failed.status == JobStatus.FAILED

        manager.register_handler(
            "failure",
            lambda context, payload: {"ok": True},
        )
        retry = manager.retry(failed.job_id)
        done = manager.wait(retry.job_id, timeout=5)

        assert retry.job_id != failed.job_id
        assert done.status == JobStatus.SUCCEEDED
        assert done.retry_of_job_id == failed.job_id
        assert done.attempt == failed.attempt + 1
        assert manager.get_job(failed.job_id).status == JobStatus.FAILED


def test_nonterminal_job_cannot_be_retried(store, project):
    with JobManager(store, max_workers=1) as manager:
        job = manager.enqueue(
            project.project_id,
            "queued",
            auto_start=False,
        )
        with pytest.raises(JobStateError):
            manager.retry(job.job_id)


def test_list_jobs_filters_project_and_status(store, project):
    other = store.create_project("Other", project_id="project-2")
    with JobManager(store, max_workers=1) as manager:
        first = manager.enqueue(
            project.project_id,
            "queued",
            auto_start=False,
        )
        manager.enqueue(
            other.project_id,
            "queued",
            auto_start=False,
        )
        assert [job.job_id for job in manager.list_jobs(project_id=project.project_id)] == [
            first.job_id
        ]
        assert [job.job_id for job in manager.list_jobs(status=JobStatus.QUEUED)]


def test_unknown_job_raises(store, project):
    with JobManager(store, max_workers=1) as manager:
        with pytest.raises(JobNotFoundError):
            manager.get_job("missing")


def test_resource_class_is_persisted(store, project):
    with JobManager(store, max_workers=1) as manager:
        job = manager.enqueue(
            project.project_id,
            "heavy",
            resource_class=ResourceClass.HEAVY,
            auto_start=False,
        )
        assert manager.get_job(job.job_id).resource_class == ResourceClass.HEAVY


def test_recovery_marks_dead_owned_running_job_interrupted(store, project):
    with JobManager(store, max_workers=1) as manager:
        job = manager.enqueue(
            project.project_id,
            "orphan",
            auto_start=False,
        )
        with manager.db.immediate() as connection:
            connection.execute(
                """
                UPDATE jobs
                SET status='RUNNING', owner_id='host:999999:dead'
                WHERE job_id=?
                """,
                (job.job_id,),
            )
        recovered = manager.recover_interrupted_jobs(
            owner_alive=lambda owner: False
        )
        assert recovered == [job.job_id]
        assert manager.get_job(job.job_id).status == JobStatus.INTERRUPTED


def test_recovery_is_conservative_for_live_owner(store, project):
    with JobManager(store, max_workers=1) as manager:
        job = manager.enqueue(
            project.project_id,
            "live",
            auto_start=False,
        )
        with manager.db.immediate() as connection:
            connection.execute(
                """
                UPDATE jobs
                SET status='RUNNING', owner_id='host:123:live'
                WHERE job_id=?
                """,
                (job.job_id,),
            )
        recovered = manager.recover_interrupted_jobs(
            owner_alive=lambda owner: True
        )
        assert recovered == []
        assert manager.get_job(job.job_id).status == JobStatus.RUNNING


def test_recovery_leaves_queued_jobs_queued(store, project):
    with JobManager(store, max_workers=1) as manager:
        job = manager.enqueue(
            project.project_id,
            "queued",
            auto_start=False,
        )
        assert manager.recover_interrupted_jobs(
            owner_alive=lambda owner: False
        ) == []
        assert manager.get_job(job.job_id).status == JobStatus.QUEUED


def test_job_events_persist_across_manager_instances(store, project):
    first = JobManager(store, max_workers=1)
    job = first.enqueue(
        project.project_id,
        "queued",
        auto_start=False,
    )
    first.shutdown()

    second = JobManager(store, max_workers=1)
    try:
        events = second.events(job.job_id)
        assert len(events) == 1
        assert events[0].status == JobStatus.QUEUED
    finally:
        second.shutdown()


def test_job_manager_shutdown_refuses_new_work(store, project):
    manager = JobManager(store, max_workers=1)
    manager.shutdown()
    with pytest.raises(Exception, match="shut down"):
        manager.enqueue(project.project_id, "x")


def test_orchestration_db_windows_style_context_releases_connection(store, project):
    db = OrchestrationDB(store)
    with db.connect() as connection:
        assert connection.execute("SELECT 1").fetchone()[0] == 1
    with pytest.raises(sqlite3.ProgrammingError):
        connection.execute("SELECT 1")
