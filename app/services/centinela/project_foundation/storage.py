from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
from pathlib import Path
from typing import Any, Iterable
from uuid import uuid4

from app.utils import utils

from .models import ArtifactRef, ProjectManifest, RuntimeSnapshot, utc_now_iso, validate_id

DATABASE_SCHEMA_VERSION = 1
_SUFFIX_RE = re.compile(r"^\.[A-Za-z0-9][A-Za-z0-9._-]{0,31}$")


class ProjectFoundationError(RuntimeError):
    pass


class ProjectNotFoundError(ProjectFoundationError):
    pass


class ArtifactNotFoundError(ProjectFoundationError):
    pass


class IntegrityError(ProjectFoundationError):
    pass


class UnsafePathError(ProjectFoundationError):
    pass


class _ClosingConnection(sqlite3.Connection):
    """SQLite connection whose context manager also releases the OS file handle."""

    def __exit__(self, exc_type, exc_value, traceback) -> bool | None:
        try:
            return super().__exit__(exc_type, exc_value, traceback)
        finally:
            self.close()


def _json_bytes(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def _sha_file(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.parent / f".{path.name}.{uuid4().hex}.tmp"
    try:
        with temp.open("xb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, path)
    finally:
        try:
            temp.unlink(missing_ok=True)
        except OSError:
            pass


def _atomic_copy(source: Path, destination: Path) -> tuple[str, int]:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp = destination.parent / f".{destination.name}.{uuid4().hex}.tmp"
    digest = hashlib.sha256()
    size = 0
    try:
        with source.open("rb") as src, temp.open("xb") as dst:
            for chunk in iter(lambda: src.read(1024 * 1024), b""):
                dst.write(chunk)
                digest.update(chunk)
                size += len(chunk)
            dst.flush()
            os.fsync(dst.fileno())
        os.replace(temp, destination)
    finally:
        try:
            temp.unlink(missing_ok=True)
        except OSError:
            pass
    return digest.hexdigest(), size


class ArtifactStore:
    """Filesystem-canonical project store with a rebuildable SQLite index."""

    def __init__(self, root: str | Path | None = None) -> None:
        configured = (
            Path(root)
            if root is not None
            else Path(utils.storage_dir("centinela", create=True))
        )
        if configured.exists() and configured.is_symlink():
            raise UnsafePathError("Centinela storage root must not be a symlink")
        configured.mkdir(parents=True, exist_ok=True)
        self.root = configured.resolve()
        self.projects_root = self.root / "projects"
        self.projects_root.mkdir(parents=True, exist_ok=True)
        self.db_path = self.root / "centinela.db"
        self._init_database()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path, timeout=30, factory=_ClosingConnection)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=30000")
        return connection

    def _init_database(self) -> None:
        with self._connect() as connection:
            version = int(connection.execute("PRAGMA user_version").fetchone()[0])
            if version > DATABASE_SCHEMA_VERSION:
                raise ProjectFoundationError(
                    f"database schema {version} is newer than supported {DATABASE_SCHEMA_VERSION}"
                )
            if version == 0:
                existing_tables = {
                    row[0]
                    for row in connection.execute(
                        """
                        SELECT name
                        FROM sqlite_master
                        WHERE type='table'
                          AND name NOT LIKE 'sqlite_%'
                        """
                    ).fetchall()
                }
                if existing_tables:
                    raise ProjectFoundationError(
                        "unversioned database contains existing tables; "
                        "refusing destructive migration"
                    )
                connection.executescript(
                    """
                    CREATE TABLE schema_meta (
                        key TEXT PRIMARY KEY,
                        value TEXT NOT NULL
                    );

                    CREATE TABLE projects (
                        project_id TEXT PRIMARY KEY,
                        title TEXT NOT NULL,
                        status TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        manifest_relpath TEXT NOT NULL UNIQUE,
                        manifest_sha256 TEXT NOT NULL
                    );

                    CREATE TABLE artifacts (
                        artifact_id TEXT NOT NULL,
                        project_id TEXT NOT NULL,
                        artifact_type TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        relative_path TEXT NOT NULL UNIQUE,
                        sha256 TEXT NOT NULL,
                        size_bytes INTEGER NOT NULL CHECK(size_bytes >= 0),
                        producer TEXT NOT NULL,
                        producer_version TEXT,
                        PRIMARY KEY(project_id, artifact_id),
                        FOREIGN KEY(project_id)
                            REFERENCES projects(project_id)
                            ON DELETE CASCADE
                    );

                    CREATE TABLE artifact_inputs (
                        project_id TEXT NOT NULL,
                        artifact_id TEXT NOT NULL,
                        input_artifact_id TEXT NOT NULL,
                        ordinal INTEGER NOT NULL CHECK(ordinal >= 0),
                        PRIMARY KEY(project_id, artifact_id, input_artifact_id),
                        UNIQUE(project_id, artifact_id, ordinal),
                        FOREIGN KEY(project_id, artifact_id)
                            REFERENCES artifacts(project_id, artifact_id)
                            ON DELETE CASCADE,
                        FOREIGN KEY(project_id, input_artifact_id)
                            REFERENCES artifacts(project_id, artifact_id)
                            ON DELETE RESTRICT
                    );

                    CREATE INDEX idx_artifacts_project_type
                        ON artifacts(project_id, artifact_type);

                    CREATE INDEX idx_artifact_inputs_input
                        ON artifact_inputs(project_id, input_artifact_id);
                    """
                )
                connection.execute(
                    "INSERT INTO schema_meta(key, value) VALUES('schema_version', ?)",
                    (str(DATABASE_SCHEMA_VERSION),),
                )
                connection.execute(f"PRAGMA user_version={DATABASE_SCHEMA_VERSION}")
            self._assert_schema(connection)

    @staticmethod
    def _assert_schema(connection: sqlite3.Connection) -> None:
        expected_columns = {
            "schema_meta": {"key", "value"},
            "projects": {
                "project_id",
                "title",
                "status",
                "created_at",
                "updated_at",
                "manifest_relpath",
                "manifest_sha256",
            },
            "artifacts": {
                "artifact_id",
                "project_id",
                "artifact_type",
                "created_at",
                "relative_path",
                "sha256",
                "size_bytes",
                "producer",
                "producer_version",
            },
            "artifact_inputs": {
                "project_id",
                "artifact_id",
                "input_artifact_id",
                "ordinal",
            },
        }
        for table, expected in expected_columns.items():
            actual = {
                row[1]
                for row in connection.execute(f"PRAGMA table_info({table})").fetchall()
            }
            if actual != expected:
                raise ProjectFoundationError(f"database table {table} columns mismatch")
        row = connection.execute(
            "SELECT value FROM schema_meta WHERE key='schema_version'"
        ).fetchone()
        if row is None or int(row[0]) != DATABASE_SCHEMA_VERSION:
            raise ProjectFoundationError("database schema version mismatch")

    def database_integrity_check(self) -> str:
        with self._connect() as connection:
            row = connection.execute("PRAGMA integrity_check").fetchone()
        return str(row[0]) if row else "missing"

    def _within_root(self, path: Path) -> Path:
        lexical = Path(os.path.abspath(path))
        try:
            relative = lexical.relative_to(self.root)
        except ValueError as exc:
            raise UnsafePathError(f"path escapes Centinela root: {path}") from exc

        cursor = self.root
        for part in relative.parts:
            cursor /= part
            if cursor.exists() and cursor.is_symlink():
                raise UnsafePathError(f"symlinked storage component is forbidden: {cursor}")

        resolved = lexical.resolve(strict=False)
        try:
            resolved.relative_to(self.root)
        except ValueError as exc:
            raise UnsafePathError(f"resolved path escapes Centinela root: {path}") from exc
        return resolved

    def _project_dir(self, project_id: str) -> Path:
        return self._within_root(
            self.projects_root / validate_id(project_id, "project_id")
        )

    def _manifest_path(self, project_id: str) -> Path:
        return self._within_root(self._project_dir(project_id) / "manifest.json")

    def _artifact_path(self, relative_path: str) -> Path:
        normalized = relative_path.replace("\\", "/")
        candidate = Path(normalized)
        if candidate.is_absolute() or ".." in candidate.parts:
            raise UnsafePathError("artifact relative path is unsafe")
        return self._within_root(self.root / candidate)

    @staticmethod
    def _normalize_suffix(value: str) -> str:
        if value == "":
            return ""
        if not isinstance(value, str) or not _SUFFIX_RE.fullmatch(value):
            raise ValueError("unsafe artifact suffix")
        return value.lower()

    def _destination(
        self,
        project_id: str,
        artifact_id: str,
        suffix: str,
    ) -> tuple[Path, str]:
        project_dir = self._project_dir(project_id)
        if not project_dir.is_dir():
            raise ProjectNotFoundError(project_id)
        artifact_id = validate_id(artifact_id, "artifact_id")
        path = self._within_root(
            project_dir / "artifacts" / f"{artifact_id}{self._normalize_suffix(suffix)}"
        )
        if path.exists():
            raise ProjectFoundationError(f"artifact already exists: {artifact_id}")
        return path, path.relative_to(self.root).as_posix()

    def create_project(
        self,
        title: str,
        *,
        project_id: str | None = None,
        observation_context: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ProjectManifest:
        manifest = ProjectManifest.new(
            title,
            project_id=project_id,
            observation_context=observation_context,
            metadata=metadata,
        )
        project_dir = self._project_dir(manifest.project_id)
        if project_dir.exists():
            raise ProjectFoundationError(f"project already exists: {manifest.project_id}")
        project_dir.mkdir(parents=True, exist_ok=False)
        (project_dir / "artifacts").mkdir(exist_ok=False)
        _atomic_write(self._manifest_path(manifest.project_id), _json_bytes(manifest.to_dict()))
        self.reindex_project(manifest.project_id)
        return manifest

    def _read_manifest(self, project_id: str) -> ProjectManifest:
        project_id = validate_id(project_id, "project_id")
        path = self._manifest_path(project_id)
        if not path.is_file():
            raise ProjectNotFoundError(project_id)
        try:
            manifest = ProjectManifest.from_dict(
                json.loads(path.read_text(encoding="utf-8"))
            )
        except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            raise IntegrityError(f"invalid project manifest: {project_id}") from exc
        if manifest.project_id != project_id:
            raise IntegrityError("manifest project_id mismatch")
        return manifest

    def load_project(self, project_id: str) -> ProjectManifest:
        return self._read_manifest(project_id)

    def save_project(self, manifest: ProjectManifest) -> None:
        normalized = ProjectManifest.from_dict(manifest.to_dict())
        project_dir = self._project_dir(normalized.project_id)
        if not project_dir.is_dir():
            raise ProjectNotFoundError(normalized.project_id)
        _atomic_write(self._manifest_path(normalized.project_id), _json_bytes(normalized.to_dict()))
        self.reindex_project(normalized.project_id)

    def list_projects(self) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT project_id, title, status, created_at, updated_at,
                       manifest_relpath, manifest_sha256
                FROM projects
                ORDER BY updated_at DESC, project_id ASC
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def reindex_project(self, project_id: str) -> None:
        project_id = validate_id(project_id, "project_id")
        manifest = self._read_manifest(project_id)
        manifest_path = self._manifest_path(project_id)
        manifest_sha, _ = _sha_file(manifest_path)

        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO projects(
                    project_id, title, status, created_at, updated_at,
                    manifest_relpath, manifest_sha256
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(project_id) DO UPDATE SET
                    title=excluded.title,
                    status=excluded.status,
                    created_at=excluded.created_at,
                    updated_at=excluded.updated_at,
                    manifest_relpath=excluded.manifest_relpath,
                    manifest_sha256=excluded.manifest_sha256
                """,
                (
                    manifest.project_id,
                    manifest.title,
                    manifest.status,
                    manifest.created_at,
                    manifest.updated_at,
                    manifest_path.relative_to(self.root).as_posix(),
                    manifest_sha,
                ),
            )
            connection.execute("DELETE FROM artifact_inputs WHERE project_id=?", (project_id,))
            connection.execute("DELETE FROM artifacts WHERE project_id=?", (project_id,))
            for ref in manifest.artifacts.values():
                connection.execute(
                    """
                    INSERT INTO artifacts(
                        artifact_id, project_id, artifact_type, created_at,
                        relative_path, sha256, size_bytes, producer, producer_version
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        ref.artifact_id,
                        ref.project_id,
                        ref.artifact_type,
                        ref.created_at,
                        ref.relative_path,
                        ref.sha256,
                        ref.size_bytes,
                        ref.producer,
                        ref.producer_version,
                    ),
                )
            for ref in manifest.artifacts.values():
                for ordinal, input_id in enumerate(ref.input_artifact_ids):
                    connection.execute(
                        """
                        INSERT INTO artifact_inputs(
                            project_id, artifact_id, input_artifact_id, ordinal
                        ) VALUES (?, ?, ?, ?)
                        """,
                        (project_id, ref.artifact_id, input_id, ordinal),
                    )

    @staticmethod
    def _validate_inputs(
        manifest: ProjectManifest,
        values: Iterable[str],
    ) -> tuple[str, ...]:
        normalized = tuple(validate_id(value, "input_artifact_id") for value in values)
        if len(normalized) != len(set(normalized)):
            raise ValueError("input_artifact_ids must be unique")
        missing = [item for item in normalized if item not in manifest.artifacts]
        if missing:
            raise ValueError(f"input artifacts are not registered: {missing}")
        return normalized

    def _register_artifact(self, manifest: ProjectManifest, ref: ArtifactRef) -> ArtifactRef:
        manifest.add_artifact(ref)
        self.save_project(manifest)
        return ref

    def _cleanup_unregistered_file(
        self,
        project_id: str,
        artifact_id: str,
        path: Path,
    ) -> None:
        """Remove an orphan only when the canonical manifest proves it was not registered."""
        try:
            persisted = self._read_manifest(project_id)
        except ProjectFoundationError:
            return
        if artifact_id in persisted.artifacts:
            return
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass

    def put_bytes(
        self,
        project_id: str,
        artifact_type: str,
        data: bytes,
        *,
        producer: str,
        suffix: str = ".bin",
        artifact_id: str | None = None,
        producer_version: str | None = None,
        input_artifact_ids: Iterable[str] = (),
        provenance: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ArtifactRef:
        if not isinstance(data, bytes):
            raise TypeError("data must be bytes")
        artifact_type = validate_id(artifact_type, "artifact_type")
        if not isinstance(producer, str) or not producer.strip():
            raise ValueError("producer must be non-empty")
        producer = producer.strip()
        if len(producer) > 256:
            raise ValueError("producer is too long")
        if producer_version is not None:
            if not isinstance(producer_version, str) or not producer_version.strip():
                raise ValueError("producer_version must be non-empty when supplied")
            producer_version = producer_version.strip()
            if len(producer_version) > 128:
                raise ValueError("producer_version is too long")
        provenance = dict(provenance or {})
        metadata = dict(metadata or {})
        json.dumps(provenance, ensure_ascii=False, allow_nan=False)
        json.dumps(metadata, ensure_ascii=False, allow_nan=False)

        manifest = self.load_project(project_id)
        inputs = self._validate_inputs(manifest, input_artifact_ids)
        artifact_id = validate_id(artifact_id or uuid4().hex, "artifact_id")
        if artifact_id in manifest.artifacts:
            raise ProjectFoundationError(f"artifact already registered: {artifact_id}")
        path, relative = self._destination(manifest.project_id, artifact_id, suffix)
        _atomic_write(path, data)
        sha, size = _sha_file(path)
        ref = ArtifactRef(
            artifact_id=artifact_id,
            project_id=manifest.project_id,
            artifact_type=artifact_type,
            relative_path=relative,
            sha256=sha,
            size_bytes=size,
            created_at=utc_now_iso(),
            producer=producer,
            producer_version=producer_version,
            input_artifact_ids=inputs,
            provenance=provenance,
            metadata=metadata,
        )
        try:
            return self._register_artifact(manifest, ref)
        except Exception:
            self._cleanup_unregistered_file(
                manifest.project_id,
                artifact_id,
                path,
            )
            raise

    def put_json(
        self,
        project_id: str,
        artifact_type: str,
        payload: Any,
        *,
        producer: str,
        artifact_id: str | None = None,
        producer_version: str | None = None,
        input_artifact_ids: Iterable[str] = (),
        provenance: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ArtifactRef:
        return self.put_bytes(
            project_id,
            artifact_type,
            _json_bytes(payload),
            producer=producer,
            suffix=".json",
            artifact_id=artifact_id,
            producer_version=producer_version,
            input_artifact_ids=input_artifact_ids,
            provenance=provenance,
            metadata={**(metadata or {}), "media_type": "application/json"},
        )

    def ingest_file(
        self,
        project_id: str,
        artifact_type: str,
        source: str | Path,
        *,
        producer: str,
        artifact_id: str | None = None,
        producer_version: str | None = None,
        input_artifact_ids: Iterable[str] = (),
        provenance: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ArtifactRef:
        source_path = Path(source)
        if not source_path.is_file():
            raise FileNotFoundError(source_path)
        if source_path.is_symlink():
            raise UnsafePathError("symlinked source files are forbidden")

        manifest = self.load_project(project_id)
        inputs = self._validate_inputs(manifest, input_artifact_ids)
        artifact_id = validate_id(artifact_id or uuid4().hex, "artifact_id")
        if artifact_id in manifest.artifacts:
            raise ProjectFoundationError(f"artifact already registered: {artifact_id}")

        suffix = source_path.suffix.lower()
        if suffix and not _SUFFIX_RE.fullmatch(suffix):
            suffix = ".bin"
        path, relative = self._destination(manifest.project_id, artifact_id, suffix)
        sha, size = _atomic_copy(source_path, path)

        user_provenance = dict(provenance or {})
        user_metadata = dict(metadata or {})
        json.dumps(user_provenance, ensure_ascii=False, allow_nan=False)
        json.dumps(user_metadata, ensure_ascii=False, allow_nan=False)
        merged_provenance = {
            **user_provenance,
            "ingested_from": str(source_path.resolve()),
            "source_sha256": sha,
        }
        merged_metadata = {
            **user_metadata,
            "source_name": source_path.name,
        }

        ref = ArtifactRef(
            artifact_id=artifact_id,
            project_id=manifest.project_id,
            artifact_type=validate_id(artifact_type, "artifact_type"),
            relative_path=relative,
            sha256=sha,
            size_bytes=size,
            created_at=utc_now_iso(),
            producer=producer,
            producer_version=producer_version,
            input_artifact_ids=inputs,
            provenance=merged_provenance,
            metadata=merged_metadata,
        )
        try:
            return self._register_artifact(manifest, ref)
        except Exception:
            self._cleanup_unregistered_file(
                manifest.project_id,
                artifact_id,
                path,
            )
            raise

    def put_runtime_snapshot(
        self,
        project_id: str,
        snapshot: RuntimeSnapshot,
        *,
        producer: str = "centinela.runtime",
        producer_version: str | None = None,
    ) -> ArtifactRef:
        if not isinstance(snapshot, RuntimeSnapshot):
            raise TypeError("snapshot must be RuntimeSnapshot")
        ref = self.put_json(
            project_id,
            "runtime_snapshot",
            snapshot.to_dict(),
            producer=producer,
            producer_version=producer_version,
            metadata={"snapshot_id": snapshot.snapshot_id},
        )
        manifest = self.load_project(project_id)
        manifest.set_runtime_snapshot(ref.artifact_id)
        self.save_project(manifest)
        return ref

    def get_artifact(self, project_id: str, artifact_id: str) -> ArtifactRef:
        manifest = self.load_project(project_id)
        artifact_id = validate_id(artifact_id, "artifact_id")
        try:
            return manifest.artifacts[artifact_id]
        except KeyError as exc:
            raise ArtifactNotFoundError(artifact_id) from exc

    def get_latest_artifact(self, project_id: str, artifact_type: str) -> ArtifactRef:
        manifest = self.load_project(project_id)
        artifact_type = validate_id(artifact_type, "artifact_type")
        artifact_id = manifest.latest_by_type.get(artifact_type)
        if artifact_id is None:
            raise ArtifactNotFoundError(f"no artifact of type {artifact_type}")
        return manifest.artifacts[artifact_id]

    def resolve_artifact_path(self, project_id: str, artifact_id: str) -> Path:
        ref = self.get_artifact(project_id, artifact_id)
        return self._artifact_path(ref.relative_path)

    def read_bytes(
        self,
        project_id: str,
        artifact_id: str,
        *,
        verify_integrity: bool = True,
    ) -> bytes:
        ref = self.get_artifact(project_id, artifact_id)
        path = self._artifact_path(ref.relative_path)
        if not path.is_file():
            raise IntegrityError(f"artifact file missing: {artifact_id}")
        data = path.read_bytes()
        if verify_integrity:
            actual_sha = hashlib.sha256(data).hexdigest()
            if actual_sha != ref.sha256 or len(data) != ref.size_bytes:
                raise IntegrityError(f"artifact integrity mismatch: {artifact_id}")
        return data

    def read_json(
        self,
        project_id: str,
        artifact_id: str,
        *,
        verify_integrity: bool = True,
    ) -> Any:
        try:
            return json.loads(
                self.read_bytes(
                    project_id,
                    artifact_id,
                    verify_integrity=verify_integrity,
                ).decode("utf-8")
            )
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise IntegrityError(f"artifact is not valid JSON: {artifact_id}") from exc

    def list_artifacts(
        self,
        project_id: str,
        *,
        artifact_type: str | None = None,
    ) -> list[ArtifactRef]:
        manifest = self.load_project(project_id)
        values = list(manifest.artifacts.values())
        if artifact_type is not None:
            artifact_type = validate_id(artifact_type, "artifact_type")
            values = [ref for ref in values if ref.artifact_type == artifact_type]
        return sorted(values, key=lambda ref: (ref.created_at, ref.artifact_id))

    def audit_project(self, project_id: str) -> dict[str, Any]:
        manifest = self.load_project(project_id)
        errors: list[str] = []
        manifest_path = self._manifest_path(project_id)
        manifest_sha, _ = _sha_file(manifest_path)

        for artifact_id, ref in manifest.artifacts.items():
            try:
                path = self._artifact_path(ref.relative_path)
                if not path.is_file():
                    errors.append(f"{artifact_id}:missing")
                    continue
                sha, size = _sha_file(path)
                if sha != ref.sha256:
                    errors.append(f"{artifact_id}:sha256")
                if size != ref.size_bytes:
                    errors.append(f"{artifact_id}:size")
            except (OSError, UnsafePathError) as exc:
                errors.append(f"{artifact_id}:path:{type(exc).__name__}")

        with self._connect() as connection:
            project_row = connection.execute(
                "SELECT manifest_sha256 FROM projects WHERE project_id=?",
                (project_id,),
            ).fetchone()
            artifact_rows = connection.execute(
                """
                SELECT artifact_id, sha256, size_bytes
                FROM artifacts
                WHERE project_id=?
                """,
                (project_id,),
            ).fetchall()
            input_rows = connection.execute(
                """
                SELECT artifact_id, input_artifact_id, ordinal
                FROM artifact_inputs
                WHERE project_id=?
                ORDER BY artifact_id, ordinal
                """,
                (project_id,),
            ).fetchall()

        if project_row is None:
            errors.append("index:project_missing")
        elif project_row["manifest_sha256"] != manifest_sha:
            errors.append("index:manifest_sha256")

        indexed_artifacts = {
            row["artifact_id"]: (row["sha256"], row["size_bytes"])
            for row in artifact_rows
        }
        if set(indexed_artifacts) != set(manifest.artifacts):
            errors.append("index:artifact_set")
        else:
            for artifact_id, ref in manifest.artifacts.items():
                if indexed_artifacts[artifact_id] != (ref.sha256, ref.size_bytes):
                    errors.append(f"index:{artifact_id}:metadata")

        indexed_inputs: dict[str, list[str]] = {}
        for row in input_rows:
            indexed_inputs.setdefault(row["artifact_id"], []).append(row["input_artifact_id"])
        expected_inputs = {
            artifact_id: list(ref.input_artifact_ids)
            for artifact_id, ref in manifest.artifacts.items()
            if ref.input_artifact_ids
        }
        if indexed_inputs != expected_inputs:
            errors.append("index:artifact_inputs")

        database_integrity = self.database_integrity_check()
        if database_integrity != "ok":
            errors.append("index:sqlite_integrity")

        return {
            "project_id": project_id,
            "schema_version": manifest.schema_version,
            "database_schema_version": DATABASE_SCHEMA_VERSION,
            "artifact_count": len(manifest.artifacts),
            "manifest_sha256": manifest_sha,
            "database_integrity": database_integrity,
            "ok": not errors,
            "errors": errors,
        }
