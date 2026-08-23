from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from app.services.centinela.project_foundation import ArtifactStore, ProjectFoundationError

from .models import ORCHESTRATION_SCHEMA_VERSION


class OrchestrationPersistenceError(RuntimeError):
    pass


class _ClosingConnection(sqlite3.Connection):
    def __exit__(self, exc_type, exc_value, traceback) -> bool | None:
        try:
            return super().__exit__(exc_type, exc_value, traceback)
        finally:
            self.close()


class OrchestrationDB:
    def __init__(self, store: ArtifactStore) -> None:
        if not isinstance(store, ArtifactStore):
            raise TypeError("store must be ArtifactStore")
        self.store = store
        self.db_path = Path(store.db_path)
        self._init_schema()

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(
            self.db_path,
            timeout=30,
            factory=_ClosingConnection,
            isolation_level=None,
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=30000")
        return connection

    @contextmanager
    def immediate(self) -> Iterator[sqlite3.Connection]:
        connection = self.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            yield connection
            connection.execute("COMMIT")
        except Exception:
            try:
                connection.execute("ROLLBACK")
            except sqlite3.Error:
                pass
            raise
        finally:
            connection.close()

    def _init_schema(self) -> None:
        with self.connect() as connection:
            project_table = connection.execute(
                """
                SELECT 1
                FROM sqlite_master
                WHERE type='table' AND name='projects'
                """
            ).fetchone()
            if project_table is None:
                raise ProjectFoundationError(
                    "R1 project foundation database must exist before R2 orchestration"
                )

            known = {
                row[0]
                for row in connection.execute(
                    """
                    SELECT name
                    FROM sqlite_master
                    WHERE type='table'
                      AND name IN (
                        'orchestration_meta',
                        'project_state_heads',
                        'project_transition_intents',
                        'project_state_transitions',
                        'jobs',
                        'job_events'
                      )
                    """
                ).fetchall()
            }

            meta_exists = "orchestration_meta" in known
            if known and not meta_exists:
                raise OrchestrationPersistenceError(
                    "unversioned orchestration tables already exist; refusing migration guess"
                )

            if not known:
                connection.executescript(
                        """
                        BEGIN IMMEDIATE;
                        CREATE TABLE orchestration_meta (
                            key TEXT PRIMARY KEY,
                            value TEXT NOT NULL
                        );

                        CREATE TABLE project_state_heads (
                            project_id TEXT PRIMARY KEY,
                            state TEXT NOT NULL,
                            revision INTEGER NOT NULL CHECK(revision >= 0),
                            pending_transition_id TEXT,
                            updated_at TEXT NOT NULL,
                            FOREIGN KEY(project_id)
                                REFERENCES projects(project_id)
                                ON DELETE CASCADE
                        );

                        CREATE TABLE project_transition_intents (
                            transition_id TEXT PRIMARY KEY,
                            project_id TEXT NOT NULL,
                            from_state TEXT NOT NULL,
                            to_state TEXT NOT NULL,
                            reason TEXT NOT NULL,
                            actor TEXT NOT NULL,
                            metadata_json TEXT NOT NULL,
                            created_at TEXT NOT NULL,
                            status TEXT NOT NULL,
                            resolved_at TEXT,
                            FOREIGN KEY(project_id)
                                REFERENCES projects(project_id)
                                ON DELETE CASCADE
                        );

                        CREATE INDEX idx_transition_intents_project_status
                            ON project_transition_intents(project_id, status);

                        CREATE TABLE project_state_transitions (
                            transition_id TEXT PRIMARY KEY,
                            project_id TEXT NOT NULL,
                            revision INTEGER NOT NULL CHECK(revision > 0),
                            from_state TEXT NOT NULL,
                            to_state TEXT NOT NULL,
                            reason TEXT NOT NULL,
                            actor TEXT NOT NULL,
                            metadata_json TEXT NOT NULL,
                            created_at TEXT NOT NULL,
                            UNIQUE(project_id, revision),
                            FOREIGN KEY(project_id)
                                REFERENCES projects(project_id)
                                ON DELETE CASCADE
                        );

                        CREATE INDEX idx_project_transitions_project_revision
                            ON project_state_transitions(project_id, revision);

                        CREATE TABLE jobs (
                            job_id TEXT PRIMARY KEY,
                            project_id TEXT NOT NULL,
                            job_type TEXT NOT NULL,
                            status TEXT NOT NULL,
                            progress INTEGER NOT NULL CHECK(progress BETWEEN 0 AND 100),
                            message TEXT,
                            resource_class TEXT NOT NULL,
                            payload_json TEXT NOT NULL,
                            result_json TEXT,
                            error_type TEXT,
                            error_message TEXT,
                            created_at TEXT NOT NULL,
                            started_at TEXT,
                            finished_at TEXT,
                            updated_at TEXT NOT NULL,
                            owner_id TEXT,
                            retry_of_job_id TEXT,
                            attempt INTEGER NOT NULL CHECK(attempt > 0),
                            FOREIGN KEY(project_id)
                                REFERENCES projects(project_id)
                                ON DELETE CASCADE,
                            FOREIGN KEY(retry_of_job_id)
                                REFERENCES jobs(job_id)
                                ON DELETE RESTRICT
                        );

                        CREATE INDEX idx_jobs_project_created
                            ON jobs(project_id, created_at);

                        CREATE INDEX idx_jobs_status
                            ON jobs(status);

                        CREATE TABLE job_events (
                            event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                            job_id TEXT NOT NULL,
                            sequence INTEGER NOT NULL CHECK(sequence > 0),
                            status TEXT NOT NULL,
                            progress INTEGER NOT NULL CHECK(progress BETWEEN 0 AND 100),
                            message TEXT,
                            created_at TEXT NOT NULL,
                            UNIQUE(job_id, sequence),
                            FOREIGN KEY(job_id)
                                REFERENCES jobs(job_id)
                                ON DELETE CASCADE
                        );

                        CREATE INDEX idx_job_events_job_sequence
                            ON job_events(job_id, sequence);

                        INSERT INTO orchestration_meta(key, value)
                        VALUES('schema_version', '1');

                        COMMIT;
                        """
                )

            self._assert_schema(connection)

    @staticmethod
    def _assert_schema(connection: sqlite3.Connection) -> None:
        row = connection.execute(
            """
            SELECT value
            FROM orchestration_meta
            WHERE key='schema_version'
            """
        ).fetchone()
        if row is None:
            raise OrchestrationPersistenceError(
                "orchestration schema version is missing"
            )
        version = int(row[0])
        if version > ORCHESTRATION_SCHEMA_VERSION:
            raise OrchestrationPersistenceError(
                f"orchestration schema {version} is newer than supported "
                f"{ORCHESTRATION_SCHEMA_VERSION}"
            )
        if version != ORCHESTRATION_SCHEMA_VERSION:
            raise OrchestrationPersistenceError(
                f"unsupported orchestration schema version={version}"
            )

        expected = {
            "orchestration_meta": {"key", "value"},
            "project_state_heads": {
                "project_id",
                "state",
                "revision",
                "pending_transition_id",
                "updated_at",
            },
            "project_transition_intents": {
                "transition_id",
                "project_id",
                "from_state",
                "to_state",
                "reason",
                "actor",
                "metadata_json",
                "created_at",
                "status",
                "resolved_at",
            },
            "project_state_transitions": {
                "transition_id",
                "project_id",
                "revision",
                "from_state",
                "to_state",
                "reason",
                "actor",
                "metadata_json",
                "created_at",
            },
            "jobs": {
                "job_id",
                "project_id",
                "job_type",
                "status",
                "progress",
                "message",
                "resource_class",
                "payload_json",
                "result_json",
                "error_type",
                "error_message",
                "created_at",
                "started_at",
                "finished_at",
                "updated_at",
                "owner_id",
                "retry_of_job_id",
                "attempt",
            },
            "job_events": {
                "event_id",
                "job_id",
                "sequence",
                "status",
                "progress",
                "message",
                "created_at",
            },
        }

        for table, columns in expected.items():
            actual = {
                row[1]
                for row in connection.execute(
                    f"PRAGMA table_info({table})"
                ).fetchall()
            }
            if actual != columns:
                raise OrchestrationPersistenceError(
                    f"orchestration table {table} columns mismatch"
                )

    def integrity_check(self) -> str:
        with self.connect() as connection:
            row = connection.execute(
                "PRAGMA integrity_check"
            ).fetchone()
        return str(row[0]) if row else "missing"
