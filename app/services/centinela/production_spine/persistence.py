from __future__ import annotations

import sqlite3

from app.services.centinela.orchestration import OrchestrationDB
from app.services.centinela.project_foundation import ArtifactStore

PRODUCTION_SPINE_SCHEMA_VERSION = 1


class ProductionSpinePersistenceError(RuntimeError):
    pass


class ProductionSpineDB:
    """Namespaced R3 additions on the rebuildable Centinela SQLite index."""

    def __init__(self, store: ArtifactStore) -> None:
        self.orchestration = OrchestrationDB(store)
        self._init_schema()

    def _init_schema(self) -> None:
        try:
            with self.orchestration.immediate() as connection:
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS production_spine_meta (
                        key TEXT PRIMARY KEY,
                        value TEXT NOT NULL
                    )
                    """
                )
                row = connection.execute(
                    "SELECT value FROM production_spine_meta WHERE key='schema_version'"
                ).fetchone()
                if row is None:
                    connection.execute(
                        "INSERT INTO production_spine_meta(key, value) VALUES('schema_version', ?)",
                        (str(PRODUCTION_SPINE_SCHEMA_VERSION),),
                    )
                elif int(row[0]) != PRODUCTION_SPINE_SCHEMA_VERSION:
                    raise ProductionSpinePersistenceError(
                        f"unsupported production spine schema version={row[0]}"
                    )

                # Cross-process invariant: only one active job of the same spine stage
                # may exist for a project. R2 schema validation ignores indexes, so this
                # is a non-destructive, backwards-compatible strengthening.
                connection.execute(
                    """
                    CREATE UNIQUE INDEX IF NOT EXISTS idx_spine_one_active_stage_job
                    ON jobs(project_id, job_type)
                    WHERE job_type GLOB 'centinela.spine.*'
                      AND status IN ('QUEUED', 'RUNNING', 'CANCEL_REQUESTED')
                    """
                )
        except sqlite3.IntegrityError as exc:
            raise ProductionSpinePersistenceError(
                "active duplicate production-spine jobs already exist; refusing unsafe index creation"
            ) from exc

    def integrity_check(self) -> str:
        return self.orchestration.integrity_check()
