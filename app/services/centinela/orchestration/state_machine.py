from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any
from uuid import uuid4

from app.services.centinela.project_foundation import ArtifactStore, ProjectManifest
from app.services.centinela.project_foundation.models import utc_now_iso

from .models import (
    PROGRESSION_STATES,
    SIDE_STATES,
    TERMINAL_PROJECT_STATES,
    ProjectState,
    StateTransition,
    clean_text,
    json_safe,
)
from .persistence import OrchestrationDB


class StateMachineError(RuntimeError):
    pass


class InvalidTransitionError(StateMachineError):
    pass


class StateConflictError(StateMachineError):
    pass


class TransitionRecoveryRequired(StateMachineError):
    pass


class StateIntegrityError(StateMachineError):
    pass


Guard = Callable[
    [ProjectManifest, ProjectState, ProjectState, dict[str, Any]],
    None,
]


class ProjectStateMachine:
    def __init__(
        self,
        store: ArtifactStore,
        *,
        guards: dict[ProjectState | str, list[Guard]] | None = None,
    ) -> None:
        self.store = store
        self.db = OrchestrationDB(store)
        self.guards: dict[ProjectState, list[Guard]] = {}
        for state, callbacks in (guards or {}).items():
            normalized = ProjectState(state)
            self.guards[normalized] = list(callbacks)

    @staticmethod
    def _manifest_state(manifest: ProjectManifest) -> ProjectState:
        try:
            return ProjectState(manifest.status)
        except ValueError as exc:
            raise StateIntegrityError(
                f"project manifest contains unknown state={manifest.status}"
            ) from exc

    def _ensure_head(
        self,
        project_id: str,
        manifest: ProjectManifest | None = None,
    ) -> tuple[ProjectState, int, str | None]:
        if manifest is None:
            manifest = self.store.load_project(project_id)
        manifest_state = self._manifest_state(manifest)
        now = utc_now_iso()

        with self.db.immediate() as connection:
            row = connection.execute(
                """
                SELECT state, revision, pending_transition_id
                FROM project_state_heads
                WHERE project_id=?
                """,
                (project_id,),
            ).fetchone()

            if row is None:
                connection.execute(
                    """
                    INSERT INTO project_state_heads(
                        project_id,
                        state,
                        revision,
                        pending_transition_id,
                        updated_at
                    ) VALUES (?, ?, 0, NULL, ?)
                    """,
                    (
                        project_id,
                        manifest_state.value,
                        now,
                    ),
                )
                return manifest_state, 0, None

            db_state = ProjectState(row["state"])
            revision = int(row["revision"])
            pending = row["pending_transition_id"]

            if pending is None and db_state != manifest_state:
                raise StateIntegrityError(
                    "project manifest state and orchestration state head disagree"
                )

            return db_state, revision, pending

    def current_state(self, project_id: str) -> ProjectState:
        manifest = self.store.load_project(project_id)
        state, _, pending = self._ensure_head(project_id, manifest)
        if pending is not None:
            raise TransitionRecoveryRequired(
                f"project {project_id} has pending transition {pending}"
            )
        manifest_state = self._manifest_state(manifest)
        if state != manifest_state:
            raise StateIntegrityError(
                "project manifest state and state head disagree"
            )
        return state

    @staticmethod
    def _next_progression_state(state: ProjectState) -> ProjectState | None:
        try:
            index = PROGRESSION_STATES.index(state)
        except ValueError:
            return None
        if index + 1 >= len(PROGRESSION_STATES):
            return None
        return PROGRESSION_STATES[index + 1]

    def _resume_target(
        self,
        project_id: str,
        current: ProjectState,
    ) -> ProjectState:
        with self.db.connect() as connection:
            row = connection.execute(
                """
                SELECT from_state
                FROM project_state_transitions
                WHERE project_id=? AND to_state=?
                ORDER BY revision DESC
                LIMIT 1
                """,
                (
                    project_id,
                    current.value,
                ),
            ).fetchone()
        if row is None:
            raise InvalidTransitionError(
                f"cannot resume {current.value}: no applied entry transition exists"
            )
        return ProjectState(row["from_state"])

    def _validate_transition(
        self,
        project_id: str,
        current: ProjectState,
        target: ProjectState,
    ) -> None:
        if current == target:
            raise InvalidTransitionError(
                "state transition must change state"
            )

        if current in TERMINAL_PROJECT_STATES:
            raise InvalidTransitionError(
                f"{current.value} is terminal"
            )

        if current in {ProjectState.BLOCKED, ProjectState.NEEDS_INPUT}:
            if target in {ProjectState.FAILED, ProjectState.CANCELLED}:
                return
            expected_resume = self._resume_target(project_id, current)
            if target != expected_resume:
                raise InvalidTransitionError(
                    f"{current.value} may only resume to "
                    f"{expected_resume.value}, FAILED or CANCELLED"
                )
            return

        if target in SIDE_STATES:
            return

        expected = self._next_progression_state(current)
        if expected is None or target != expected:
            raise InvalidTransitionError(
                f"invalid progression {current.value} -> {target.value}; "
                f"expected {expected.value if expected else 'no forward state'}"
            )

    def _run_guards(
        self,
        manifest: ProjectManifest,
        current: ProjectState,
        target: ProjectState,
        metadata: dict[str, Any],
    ) -> None:
        for guard in self.guards.get(target, []):
            guard(manifest, current, target, metadata)

    def add_guard(
        self,
        target: ProjectState | str,
        guard: Guard,
    ) -> None:
        if not callable(guard):
            raise TypeError("guard must be callable")
        normalized = ProjectState(target)
        self.guards.setdefault(normalized, []).append(guard)

    def transition(
        self,
        project_id: str,
        target: ProjectState | str,
        *,
        reason: str,
        actor: str,
        metadata: dict[str, Any] | None = None,
        expected_state: ProjectState | str | None = None,
    ) -> StateTransition:
        target_state = ProjectState(target)
        reason = clean_text(reason, "reason", maximum=1000)
        actor = clean_text(actor, "actor", maximum=128)
        safe_metadata = json_safe(metadata or {}, "transition_metadata")

        manifest = self.store.load_project(project_id)
        current = self._manifest_state(manifest)

        if expected_state is not None:
            expected = ProjectState(expected_state)
            if current != expected:
                raise StateConflictError(
                    f"expected state {expected.value}, found {current.value}"
                )

        head_state, revision, pending = self._ensure_head(
            project_id,
            manifest,
        )

        if pending is not None:
            raise TransitionRecoveryRequired(
                f"project {project_id} has pending transition {pending}"
            )

        if head_state != current:
            raise StateIntegrityError(
                "project manifest state and state head disagree"
            )

        self._validate_transition(
            project_id,
            current,
            target_state,
        )
        self._run_guards(
            manifest,
            current,
            target_state,
            safe_metadata,
        )

        transition_id = uuid4().hex
        created_at = utc_now_iso()

        with self.db.immediate() as connection:
            head = connection.execute(
                """
                SELECT state, revision, pending_transition_id
                FROM project_state_heads
                WHERE project_id=?
                """,
                (project_id,),
            ).fetchone()

            if head is None:
                raise StateIntegrityError(
                    "project state head disappeared"
                )
            if head["pending_transition_id"] is not None:
                raise TransitionRecoveryRequired(
                    f"project {project_id} acquired a pending transition"
                )
            if ProjectState(head["state"]) != current:
                raise StateConflictError(
                    "project state changed concurrently"
                )
            if int(head["revision"]) != revision:
                raise StateConflictError(
                    "project state revision changed concurrently"
                )

            connection.execute(
                """
                INSERT INTO project_transition_intents(
                    transition_id,
                    project_id,
                    from_state,
                    to_state,
                    reason,
                    actor,
                    metadata_json,
                    created_at,
                    status,
                    resolved_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'PENDING', NULL)
                """,
                (
                    transition_id,
                    project_id,
                    current.value,
                    target_state.value,
                    reason,
                    actor,
                    json.dumps(
                        safe_metadata,
                        ensure_ascii=False,
                        sort_keys=True,
                        allow_nan=False,
                    ),
                    created_at,
                ),
            )

            updated = connection.execute(
                """
                UPDATE project_state_heads
                SET pending_transition_id=?, updated_at=?
                WHERE project_id=?
                  AND pending_transition_id IS NULL
                  AND state=?
                  AND revision=?
                """,
                (
                    transition_id,
                    created_at,
                    project_id,
                    current.value,
                    revision,
                ),
            )
            if updated.rowcount != 1:
                raise StateConflictError(
                    "failed to reserve project state transition"
                )

        manifest.status = target_state.value
        manifest.updated_at = utc_now_iso()

        try:
            self.store.save_project(manifest)
        except Exception as exc:
            try:
                persisted = self.store.load_project(project_id)
                persisted_state = self._manifest_state(persisted)
            except Exception:
                raise TransitionRecoveryRequired(
                    f"transition {transition_id} reserved; manifest outcome unknown"
                ) from exc

            if persisted_state == current:
                self._abort_intent(
                    project_id,
                    transition_id,
                )
            elif persisted_state == target_state:
                raise TransitionRecoveryRequired(
                    f"transition {transition_id} wrote manifest but was not finalized"
                ) from exc
            else:
                raise StateIntegrityError(
                    f"transition {transition_id} left unexpected manifest state "
                    f"{persisted_state.value}"
                ) from exc
            raise

        try:
            return self._finalize_intent(
                project_id,
                transition_id,
            )
        except Exception as exc:
            raise TransitionRecoveryRequired(
                f"transition {transition_id} wrote manifest but finalization failed"
            ) from exc

    def _abort_intent(
        self,
        project_id: str,
        transition_id: str,
    ) -> None:
        now = utc_now_iso()
        with self.db.immediate() as connection:
            connection.execute(
                """
                UPDATE project_transition_intents
                SET status='ABORTED', resolved_at=?
                WHERE transition_id=?
                  AND project_id=?
                  AND status='PENDING'
                """,
                (
                    now,
                    transition_id,
                    project_id,
                ),
            )
            connection.execute(
                """
                UPDATE project_state_heads
                SET pending_transition_id=NULL, updated_at=?
                WHERE project_id=?
                  AND pending_transition_id=?
                """,
                (
                    now,
                    project_id,
                    transition_id,
                ),
            )

    def _finalize_intent(
        self,
        project_id: str,
        transition_id: str,
    ) -> StateTransition:
        resolved_at = utc_now_iso()

        with self.db.immediate() as connection:
            intent = connection.execute(
                """
                SELECT *
                FROM project_transition_intents
                WHERE transition_id=? AND project_id=?
                """,
                (
                    transition_id,
                    project_id,
                ),
            ).fetchone()
            if intent is None:
                raise StateIntegrityError(
                    f"transition intent missing: {transition_id}"
                )
            if intent["status"] == "APPLIED":
                row = connection.execute(
                    """
                    SELECT *
                    FROM project_state_transitions
                    WHERE transition_id=?
                    """,
                    (transition_id,),
                ).fetchone()
                if row is None:
                    raise StateIntegrityError(
                        "applied transition has no history row"
                    )
                return self._transition_from_row(row)
            if intent["status"] != "PENDING":
                raise StateIntegrityError(
                    f"transition intent is {intent['status']}, not PENDING"
                )

            head = connection.execute(
                """
                SELECT state, revision, pending_transition_id
                FROM project_state_heads
                WHERE project_id=?
                """,
                (project_id,),
            ).fetchone()
            if head is None:
                raise StateIntegrityError(
                    "project state head missing during finalization"
                )
            if head["pending_transition_id"] != transition_id:
                raise StateIntegrityError(
                    "project state head points to a different pending transition"
                )

            manifest = self.store.load_project(project_id)
            manifest_state = self._manifest_state(manifest)
            target_state = ProjectState(intent["to_state"])
            if manifest_state != target_state:
                raise StateIntegrityError(
                    "cannot finalize: manifest has not reached target state"
                )

            next_revision = int(head["revision"]) + 1

            connection.execute(
                """
                INSERT INTO project_state_transitions(
                    transition_id,
                    project_id,
                    revision,
                    from_state,
                    to_state,
                    reason,
                    actor,
                    metadata_json,
                    created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    transition_id,
                    project_id,
                    next_revision,
                    intent["from_state"],
                    intent["to_state"],
                    intent["reason"],
                    intent["actor"],
                    intent["metadata_json"],
                    intent["created_at"],
                ),
            )
            connection.execute(
                """
                UPDATE project_state_heads
                SET
                    state=?,
                    revision=?,
                    pending_transition_id=NULL,
                    updated_at=?
                WHERE project_id=?
                  AND pending_transition_id=?
                """,
                (
                    target_state.value,
                    next_revision,
                    resolved_at,
                    project_id,
                    transition_id,
                ),
            )
            connection.execute(
                """
                UPDATE project_transition_intents
                SET status='APPLIED', resolved_at=?
                WHERE transition_id=?
                """,
                (
                    resolved_at,
                    transition_id,
                ),
            )

            row = connection.execute(
                """
                SELECT *
                FROM project_state_transitions
                WHERE transition_id=?
                """,
                (transition_id,),
            ).fetchone()

        if row is None:
            raise StateIntegrityError(
                "transition history row missing after finalization"
            )
        return self._transition_from_row(row)

    @staticmethod
    def _transition_from_row(row: Any) -> StateTransition:
        return StateTransition(
            transition_id=row["transition_id"],
            project_id=row["project_id"],
            revision=int(row["revision"]),
            from_state=ProjectState(row["from_state"]),
            to_state=ProjectState(row["to_state"]),
            reason=row["reason"],
            actor=row["actor"],
            created_at=row["created_at"],
            metadata=json.loads(row["metadata_json"]),
        )

    def history(
        self,
        project_id: str,
    ) -> list[StateTransition]:
        self.store.load_project(project_id)
        with self.db.connect() as connection:
            rows = connection.execute(
                """
                SELECT *
                FROM project_state_transitions
                WHERE project_id=?
                ORDER BY revision ASC
                """,
                (project_id,),
            ).fetchall()
        return [
            self._transition_from_row(row)
            for row in rows
        ]

    def recover_pending_transitions(
        self,
        project_id: str | None = None,
    ) -> list[dict[str, str]]:
        parameters: tuple[Any, ...] = ()
        where = "WHERE status='PENDING'"
        if project_id is not None:
            self.store.load_project(project_id)
            where += " AND project_id=?"
            parameters = (project_id,)

        with self.db.connect() as connection:
            rows = connection.execute(
                f"""
                SELECT *
                FROM project_transition_intents
                {where}
                ORDER BY created_at ASC, transition_id ASC
                """,
                parameters,
            ).fetchall()

        outcomes: list[dict[str, str]] = []

        for row in rows:
            pid = row["project_id"]
            transition_id = row["transition_id"]
            from_state = ProjectState(row["from_state"])
            to_state = ProjectState(row["to_state"])
            manifest_state = self._manifest_state(
                self.store.load_project(pid)
            )

            if manifest_state == to_state:
                self._finalize_intent(
                    pid,
                    transition_id,
                )
                outcome = "FINALIZED"
            elif manifest_state == from_state:
                self._abort_intent(
                    pid,
                    transition_id,
                )
                outcome = "ABORTED"
            else:
                raise StateIntegrityError(
                    f"pending transition {transition_id} cannot be recovered: "
                    f"manifest={manifest_state.value}, "
                    f"from={from_state.value}, to={to_state.value}"
                )

            outcomes.append(
                {
                    "project_id": pid,
                    "transition_id": transition_id,
                    "outcome": outcome,
                }
            )

        return outcomes
