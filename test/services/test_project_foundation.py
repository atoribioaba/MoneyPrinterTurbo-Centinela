from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from app.services.centinela.project_foundation import (
    DATABASE_SCHEMA_VERSION,
    ArtifactRef,
    ArtifactStore,
    IntegrityError,
    ProjectFoundationError,
    ProjectManifest,
    RuntimeSnapshot,
    UnsafePathError,
    capture_runtime_snapshot,
)
from app.services.centinela.project_foundation.models import utc_now_iso
from app.services.centinela.project_foundation import storage as storage_module


@pytest.fixture()
def store(tmp_path: Path) -> ArtifactStore:
    return ArtifactStore(tmp_path / "centinela")


def test_store_connection_context_closes_sqlite_handle(
    store: ArtifactStore,
):
    with store._connect() as connection:
        assert connection.execute("SELECT 1").fetchone()[0] == 1

    with pytest.raises(
        sqlite3.ProgrammingError,
        match="closed database",
    ):
        connection.execute("SELECT 1")


def test_temporary_directory_cleanup_releases_database_handle():
    with TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        store = ArtifactStore(temp_path / "centinela")
        store.create_project(
            "Windows handle smoke",
            project_id="windows-handle",
        )
        assert store.database_integrity_check() == "ok"

    assert not temp_path.exists()


def test_create_project_materializes_manifest_and_sqlite_index(store: ArtifactStore):
    manifest = store.create_project(
        "La Luna y Júpiter",
        project_id="project-001",
        observation_context={"timezone": "Europe/Madrid"},
        metadata={"account": "elcentineladeluniverso"},
    )
    assert manifest.project_id == "project-001"
    assert manifest.status == "DRAFT"
    assert (store.root / "projects/project-001/manifest.json").is_file()
    assert (store.root / "projects/project-001/artifacts").is_dir()
    assert store.db_path.is_file()
    assert [item["project_id"] for item in store.list_projects()] == ["project-001"]
    with sqlite3.connect(store.db_path) as connection:
        version = connection.execute("PRAGMA user_version").fetchone()[0]
    assert version == DATABASE_SCHEMA_VERSION == 1
    assert store.database_integrity_check() == "ok"


def test_project_ids_reject_path_traversal(store: ArtifactStore):
    for bad_id in ("../escape", "..", "a/b", r"a\b", "C:escape", ""):
        with pytest.raises((TypeError, ValueError)):
            store.create_project("Unsafe", project_id=bad_id)


def test_duplicate_project_is_rejected_without_overwrite(store: ArtifactStore):
    store.create_project("First", project_id="same")
    path = store.root / "projects/same/manifest.json"
    original = path.read_bytes()
    with pytest.raises(ProjectFoundationError):
        store.create_project("Second", project_id="same")
    assert path.read_bytes() == original


def test_json_artifact_roundtrip_hash_latest_and_list(store: ArtifactStore):
    store.create_project("Project", project_id="p1")
    ref = store.put_json(
        "p1",
        "astronomy_plan",
        {"target": "Jupiter", "verified": True},
        producer="test-suite",
        provenance={"source": "unit-test"},
    )
    assert store.read_json("p1", ref.artifact_id) == {
        "target": "Jupiter",
        "verified": True,
    }
    manifest = store.load_project("p1")
    assert manifest.artifacts[ref.artifact_id] == ref
    assert manifest.latest_by_type["astronomy_plan"] == ref.artifact_id
    assert store.get_latest_artifact("p1", "astronomy_plan") == ref
    assert store.list_artifacts("p1", artifact_type="astronomy_plan") == [ref]
    assert len(ref.sha256) == 64
    assert store.audit_project("p1")["ok"] is True


def test_json_artifact_media_type_cannot_be_overridden(
    store: ArtifactStore,
):
    store.create_project(
        "Project",
        project_id="p1",
    )
    ref = store.put_json(
        "p1",
        "script",
        {"text": "hello"},
        producer="test-suite",
        metadata={
            "media_type": "application/octet-stream",
        },
    )
    assert ref.metadata["media_type"] == "application/json"


def test_artifact_dependency_requires_registered_inputs(store: ArtifactStore):
    store.create_project("Project", project_id="p1")
    with pytest.raises(ValueError, match="not registered"):
        store.put_json(
            "p1",
            "scene_plan",
            {"scene": 1},
            producer="test-suite",
            input_artifact_ids=("missing",),
        )
    first = store.put_json(
        "p1",
        "script",
        {"text": "hello"},
        producer="test-suite",
    )
    second = store.put_json(
        "p1",
        "scene_plan",
        {"scene": 1},
        producer="test-suite",
        input_artifact_ids=(first.artifact_id,),
    )
    assert second.input_artifact_ids == (first.artifact_id,)
    assert store.audit_project("p1")["ok"] is True


def test_sqlite_indexes_artifact_dependency_edges(store: ArtifactStore):
    store.create_project("Project", project_id="p1")
    first = store.put_json("p1", "script", {"x": 1}, producer="test")
    second = store.put_json(
        "p1",
        "scene_plan",
        {"x": 2},
        producer="test",
        input_artifact_ids=(first.artifact_id,),
    )
    with sqlite3.connect(store.db_path) as connection:
        row = connection.execute(
            "SELECT artifact_id, input_artifact_id, ordinal FROM artifact_inputs"
        ).fetchone()
    assert row == (second.artifact_id, first.artifact_id, 0)


def test_artifact_is_immutable_by_id(store: ArtifactStore):
    store.create_project("Project", project_id="p1")
    ref = store.put_bytes(
        "p1",
        "binary",
        b"first",
        producer="test-suite",
        artifact_id="fixed-artifact",
    )
    with pytest.raises(ProjectFoundationError):
        store.put_bytes(
            "p1",
            "binary",
            b"second",
            producer="test-suite",
            artifact_id="fixed-artifact",
        )
    assert store.read_bytes("p1", ref.artifact_id) == b"first"


def test_tampering_is_detected_by_read_and_audit(store: ArtifactStore):
    store.create_project("Project", project_id="p1")
    ref = store.put_bytes(
        "p1", "video_base", b"original", producer="test-suite", suffix=".mp4"
    )
    path = store.resolve_artifact_path("p1", ref.artifact_id)
    path.write_bytes(b"tampered")
    with pytest.raises(IntegrityError):
        store.read_bytes("p1", ref.artifact_id)
    audit = store.audit_project("p1")
    assert audit["ok"] is False
    assert f"{ref.artifact_id}:sha256" in audit["errors"]


def test_ingest_file_preserves_source_and_records_provenance(
    store: ArtifactStore, tmp_path: Path
):
    store.create_project("Project", project_id="p1")
    source = tmp_path / "legacy-plan.json"
    source.write_text('{"legacy": true}', encoding="utf-8")
    before = source.read_bytes()
    ref = store.ingest_file(
        "p1",
        "legacy_evidence",
        source,
        producer="centinela.import",
        provenance={"phase": "F5"},
    )
    assert source.read_bytes() == before
    assert ref.provenance["ingested_from"] == str(source.resolve())
    assert ref.provenance["source_sha256"] == ref.sha256
    assert ref.provenance["phase"] == "F5"
    assert store.read_bytes("p1", ref.artifact_id) == before


def test_ingest_reserved_provenance_fields_cannot_be_spoofed(
    store: ArtifactStore,
    tmp_path: Path,
):
    store.create_project(
        "Project",
        project_id="p1",
    )
    source = tmp_path / "legacy.json"
    source.write_text(
        '{"legacy": true}',
        encoding="utf-8",
    )
    ref = store.ingest_file(
        "p1",
        "legacy_evidence",
        source,
        producer="centinela.import",
        provenance={
            "ingested_from": "spoofed",
            "source_sha256": "0" * 64,
            "phase": "F5",
        },
        metadata={
            "source_name": "spoofed.json",
        },
    )
    assert ref.provenance["ingested_from"] == str(source.resolve())
    assert ref.provenance["source_sha256"] == ref.sha256
    assert ref.provenance["phase"] == "F5"
    assert ref.metadata["source_name"] == source.name


def test_manifest_rejects_mismatched_latest_reference():
    now = utc_now_iso()
    ref = ArtifactRef(
        artifact_id="a1",
        project_id="p1",
        artifact_type="script",
        relative_path="projects/p1/artifacts/a1.json",
        sha256="0" * 64,
        size_bytes=0,
        created_at=now,
        producer="test",
    )
    with pytest.raises(ValueError, match="latest_by_type"):
        ProjectManifest(
            project_id="p1",
            title="Project",
            created_at=now,
            updated_at=now,
            artifacts={"a1": ref},
            latest_by_type={"scene_plan": "a1"},
        )


def test_runtime_snapshot_is_stored_and_linked(store: ArtifactStore):
    store.create_project("Project", project_id="p1")
    snapshot = RuntimeSnapshot(
        snapshot_id="runtime-001",
        created_at=utc_now_iso(),
        git_commit="e2e2650e38ee4a2426e66e54eb9edeb8d6b225c1",
        git_branch="centinela-foundation/project-artifacts-v0.1",
        app_version="1.3.4",
        python_version="3.11.9",
        platform="Windows-11",
        ffmpeg_path=r"C:\ffmpeg\bin\ffmpeg.exe",
        ffmpeg_version="ffmpeg version test",
        encoder="h264_nvenc",
        llm={"provider": "ollama", "model": "qwen3.5:4b-q4_K_M"},
        tts={"provider": "qwen3-tts", "mode": "local"},
        media_providers=[{"id": "astromedia", "active": True}],
        render={"master": "2160x3840", "fps": 30},
        environment={"gpu": "RTX 2060 6GB"},
    )
    ref = store.put_runtime_snapshot("p1", snapshot)
    manifest = store.load_project("p1")
    assert manifest.runtime_snapshot_artifact_id == ref.artifact_id
    assert manifest.latest_by_type["runtime_snapshot"] == ref.artifact_id
    assert store.read_json("p1", ref.artifact_id)["encoder"] == "h264_nvenc"
    assert store.audit_project("p1")["ok"] is True


def test_runtime_snapshot_rejects_secret_like_keys():
    with pytest.raises(ValueError, match="secret-like key"):
        RuntimeSnapshot(
            snapshot_id="runtime-001",
            created_at=utc_now_iso(),
            git_commit="abc",
            git_branch="main",
            app_version="1.0",
            python_version="3.11",
            platform="Windows",
            llm={"API Key": "must-not-be-recorded"},
        )


def test_capture_runtime_snapshot_does_not_need_config_or_secrets(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "pyproject.toml").write_text(
        '[project]\nname="x"\nversion="9.9.9"\n',
        encoding="utf-8",
    )
    snapshot = capture_runtime_snapshot(
        repo,
        encoder="libx264",
        llm={"provider": "ollama"},
        tts={"provider": "local"},
        media_providers=[{"id": "owned"}],
        render={"fps": 30},
        ffmpeg_path=None,
    )
    assert snapshot.app_version == "9.9.9"
    assert snapshot.encoder == "libx264"
    serialized = json.dumps(snapshot.to_dict()).lower()
    assert "api_key" not in serialized
    assert "password" not in serialized


def test_reindex_repairs_derived_sqlite_index(store: ArtifactStore):
    store.create_project("Project", project_id="p1")
    ref = store.put_json("p1", "script", {"text": "hello"}, producer="test")
    with sqlite3.connect(store.db_path) as connection:
        connection.execute(
            "DELETE FROM artifacts WHERE project_id=? AND artifact_id=?",
            ("p1", ref.artifact_id),
        )
    assert store.audit_project("p1")["ok"] is False
    store.reindex_project("p1")
    assert store.audit_project("p1")["ok"] is True


def test_manifest_index_hash_detects_manual_manifest_edit(store: ArtifactStore):
    store.create_project("Project", project_id="p1")
    path = store.root / "projects/p1/manifest.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["metadata"]["manual_edit"] = True
    path.write_text(json.dumps(payload), encoding="utf-8")
    audit = store.audit_project("p1")
    assert audit["ok"] is False
    assert "index:manifest_sha256" in audit["errors"]


def test_artifact_relative_path_cannot_escape_store(store: ArtifactStore):
    with pytest.raises(UnsafePathError):
        store._artifact_path("../../outside.bin")


def test_existing_symlink_component_is_rejected(store: ArtifactStore, monkeypatch):
    project = store.root / "projects" / "p1"
    project.mkdir()
    original = Path.is_symlink

    def fake_is_symlink(path: Path) -> bool:
        if path == project:
            return True
        return original(path)

    monkeypatch.setattr(Path, "is_symlink", fake_is_symlink)
    with pytest.raises(UnsafePathError, match="symlinked storage component"):
        store._within_root(project / "manifest.json")


def test_atomic_operations_leave_no_temp_files(store: ArtifactStore):
    store.create_project("Project", project_id="p1")
    store.put_json("p1", "script", {"text": "hello"}, producer="test-suite")
    assert list(store.root.rglob("*.tmp")) == []


def test_empty_v0_database_migrates_to_v1_idempotently(tmp_path: Path):
    root = tmp_path / "centinela"
    root.mkdir()
    db = root / "centinela.db"
    with sqlite3.connect(db) as connection:
        connection.execute("PRAGMA user_version=0")

    migrated = ArtifactStore(root)
    assert migrated.database_integrity_check() == "ok"

    reopened = ArtifactStore(root)
    assert reopened.database_integrity_check() == "ok"

    with sqlite3.connect(db) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 1


def test_nonempty_unversioned_database_is_refused_without_data_loss(
    tmp_path: Path,
):
    root = tmp_path / "centinela"
    root.mkdir()
    db = root / "centinela.db"

    with sqlite3.connect(db) as connection:
        connection.execute("CREATE TABLE legacy_index(value TEXT)")
        connection.execute(
            "INSERT INTO legacy_index(value) VALUES (?)",
            ("preserve-me",),
        )
        connection.execute("PRAGMA user_version=0")

    with pytest.raises(
        ProjectFoundationError,
        match="refusing destructive migration",
    ):
        ArtifactStore(root)

    with sqlite3.connect(db) as connection:
        value = connection.execute(
            "SELECT value FROM legacy_index"
        ).fetchone()[0]
        version = connection.execute(
            "PRAGMA user_version"
        ).fetchone()[0]

    assert value == "preserve-me"
    assert version == 0


def test_newer_database_schema_is_refused(tmp_path: Path):
    root = tmp_path / "centinela"
    root.mkdir()
    db = root / "centinela.db"
    with sqlite3.connect(db) as connection:
        connection.execute("PRAGMA user_version=99")
    with pytest.raises(ProjectFoundationError, match="newer than supported"):
        ArtifactStore(root)


def test_artifact_ref_rejects_cross_project_relative_path():
    with pytest.raises(ValueError, match="owning project's artifacts"):
        ArtifactRef(
            artifact_id="a1",
            project_id="p1",
            artifact_type="script",
            relative_path="projects/p2/artifacts/a1.json",
            sha256="0" * 64,
            size_bytes=0,
            created_at=utc_now_iso(),
            producer="test",
        )


def test_manifest_rejects_dependency_cycles():
    now = utc_now_iso()
    a = ArtifactRef(
        artifact_id="a",
        project_id="p1",
        artifact_type="script",
        relative_path="projects/p1/artifacts/a.json",
        sha256="0" * 64,
        size_bytes=0,
        created_at=now,
        producer="test",
        input_artifact_ids=("b",),
    )
    b = ArtifactRef(
        artifact_id="b",
        project_id="p1",
        artifact_type="scene_plan",
        relative_path="projects/p1/artifacts/b.json",
        sha256="1" * 64,
        size_bytes=0,
        created_at=now,
        producer="test",
        input_artifact_ids=("a",),
    )
    with pytest.raises(ValueError, match="cycle"):
        ProjectManifest(
            project_id="p1",
            title="Project",
            created_at=now,
            updated_at=now,
            artifacts={"a": a, "b": b},
        )


def test_default_store_root_uses_existing_storage_dir_contract(tmp_path: Path, monkeypatch):
    storage_base = tmp_path / "storage"

    def fake_storage_dir(sub_dir: str = "", create: bool = False) -> str:
        path = storage_base / sub_dir if sub_dir else storage_base
        if create:
            path.mkdir(parents=True, exist_ok=True)
        return str(path)

    monkeypatch.setattr(storage_module.utils, "storage_dir", fake_storage_dir)
    default_store = ArtifactStore()
    assert default_store.root == (storage_base / "centinela").resolve()
    assert default_store.db_path.is_file()
