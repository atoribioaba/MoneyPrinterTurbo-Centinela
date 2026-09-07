from __future__ import annotations

import os
from pathlib import Path, PureWindowsPath

import pytest

import app.services.astromedia as astromedia_service
from app.models.astromedia import HashMode, IndexRequest
from app.models.windows_path_contract import (
    CANONICAL_MEDIA_ROOT,
    CANONICAL_REPOSITORY_ROOT,
    WINDOWS_LEGACY_PATH_LIMIT,
    CentinelaWindowsPathContract,
    StorageEvidence,
    StorageMedium,
    WindowsPathContractError,
    WindowsPathRole,
    WindowsRootBinding,
    validate_absolute_windows_path,
)
from app.services.astromedia import AstroMediaCatalog
from app.services.centinela.control_center.media_policy import DEFAULT_MEDIA_ROOT
from app.services.centinela.project_foundation.models import validate_id
from app.services.centinela.project_foundation.storage import ArtifactStore


ROOT = Path(__file__).resolve().parents[2]
PREFLIGHT = ROOT / "scripts" / "centinela_pc_return_readonly_preflight.ps1"
WINDOWS_ONLY = pytest.mark.skipif(os.name != "nt", reason="requires Windows paths")


def test_c20_canonical_roots_preserve_drive_unicode_and_pending_pc_boundary():
    contract = CentinelaWindowsPathContract.canonical_pending_pc()

    assert contract.repository.path == CANONICAL_REPOSITORY_ROOT
    assert contract.repository.drive == "E:"
    assert contract.repository.role is WindowsPathRole.REPOSITORY
    assert contract.media_library.path == CANONICAL_MEDIA_ROOT
    assert contract.media_library.drive == "D:"
    assert "ASTRONOMÍA" in contract.media_library.path
    assert contract.media_library.role is WindowsPathRole.MEDIA_LIBRARY
    assert contract.repository.storage.medium is StorageMedium.PENDING_PC
    assert contract.media_library.storage.medium is StorageMedium.PENDING_PC
    assert str(DEFAULT_MEDIA_ROOT) == CANONICAL_MEDIA_ROOT


def test_c20_unicode_accents_spaces_and_long_paths_are_not_corrupted():
    root = WindowsRootBinding(
        role=WindowsPathRole.MEDIA_LIBRARY,
        path=CANONICAL_MEDIA_ROOT,
    )
    relative = "\\".join(
        ["Archivo científico con espacios y acentos"] * 7
        + ["Vía Láctea — cúmulo número 01.mp4"]
    )

    joined = root.join(relative)

    assert len(joined) >= WINDOWS_LEGACY_PATH_LIMIT
    assert PureWindowsPath(joined).is_absolute()
    assert joined.startswith(CANONICAL_MEDIA_ROOT + "\\")
    assert joined.endswith("Vía Láctea — cúmulo número 01.mp4")
    assert WindowsRootBinding(
        role=WindowsPathRole.MEDIA_LIBRARY,
        path=joined,
    ).requires_long_path_support is True


@pytest.mark.parametrize(
    "relative",
    [
        "CON",
        "con.txt",
        "subdir\\AUX.json",
        "NUL.mp4",
        "COM1",
        "com¹.log",
        "LPT9.txt",
        "nombre.",
        "nombre ",
        "alternate:stream.mp4",
    ],
)
def test_c20_reserved_or_win32_unsafe_names_fail_closed(relative: str):
    root = WindowsRootBinding(
        role=WindowsPathRole.MEDIA_LIBRARY,
        path=CANONICAL_MEDIA_ROOT,
    )

    with pytest.raises(WindowsPathContractError):
        root.join(relative)


@pytest.mark.parametrize(
    "candidate",
    [
        "..\\outside.mp4",
        "safe\\..\\outside.mp4",
        r"C:\outside.mp4",
        r"\rooted\outside.mp4",
        r"\\server\share\outside.mp4",
        r"\\?\D:\ASTRONOMÍA\Medios\outside.mp4",
    ],
)
def test_c20_traversal_and_root_override_fail_closed(candidate: str):
    root = WindowsRootBinding(
        role=WindowsPathRole.MEDIA_LIBRARY,
        path=CANONICAL_MEDIA_ROOT,
    )

    with pytest.raises(WindowsPathContractError):
        root.join(candidate)


@pytest.mark.parametrize(
    "candidate",
    [
        r"Github\MoneyPrinterTurbo",
        r"E:Github\MoneyPrinterTurbo",
        r"\\server\share\MoneyPrinterTurbo",
        r"\\?\E:\Github\MoneyPrinterTurbo",
    ],
)
def test_c20_repository_root_requires_plain_local_drive_absolute_path(candidate: str):
    with pytest.raises(WindowsPathContractError):
        validate_absolute_windows_path(candidate)


def test_c20_storage_medium_is_evidence_driven_not_inferred_from_drive_letter():
    contract = CentinelaWindowsPathContract.canonical_pending_pc()

    repo_on_hdd = contract.repository.with_observed_storage(
        StorageMedium.HDD,
        evidence_ref="preflight:Get-Disk:E:MediaType",
    )
    media_on_ssd = contract.media_library.with_observed_storage(
        StorageMedium.SSD,
        evidence_ref="preflight:Get-Disk:D:MediaType",
    )

    assert repo_on_hdd.drive == "E:"
    assert repo_on_hdd.storage.medium is StorageMedium.HDD
    assert media_on_ssd.drive == "D:"
    assert media_on_ssd.storage.medium is StorageMedium.SSD
    assert repo_on_hdd.storage.observed_on_physical_pc is True
    assert media_on_ssd.storage.observed_on_physical_pc is True

    with pytest.raises(ValueError, match="physical-PC evidence"):
        StorageEvidence(medium=StorageMedium.SSD)


@pytest.mark.parametrize("reserved_id", ["CON", "nul.json", "COM1", "LPT9.txt"])
def test_c20_project_artifact_ids_reject_windows_device_names(reserved_id: str):
    with pytest.raises(WindowsPathContractError):
        validate_id(reserved_id, "artifact_id")


def test_c20_preflight_uses_literal_canonical_roots_and_observes_storage_type():
    content = PREFLIGHT.read_text(encoding="utf-8")

    assert "'E:\\Github\\MoneyPrinterTurbo'" in content
    assert "'D:\\ASTRONOMÍA\\Medios'" in content
    assert "Get-Partition -DriveLetter $DriveLetter" in content
    assert "Select-Object Number, FriendlyName, BusType, MediaType" in content
    assert "Set-Volume" not in content
    assert "Format-Volume" not in content


@WINDOWS_ONLY
def test_c20_windows_artifact_store_round_trips_unicode_root_and_title(tmp_path: Path):
    store = ArtifactStore(tmp_path / "Álvaro" / "Proyecto con espacios")
    manifest = store.create_project(
        "Vía Láctea — observación número 1",
        project_id="via-lactea-01",
    )
    artifact = store.put_json(
        manifest.project_id,
        "guion-cientifico",
        {"título": "Órbita y cúmulo", "auto_publication": False},
        producer="c20-windows-path-contract",
    )

    assert store.read_json(manifest.project_id, artifact.artifact_id) == {
        "título": "Órbita y cúmulo",
        "auto_publication": False,
    }
    assert store.audit_project(manifest.project_id)["ok"] is True


@WINDOWS_ONLY
def test_c20_windows_astromedia_indexes_accented_spaced_path(
    tmp_path: Path,
    monkeypatch,
):
    media_root = tmp_path / "ASTRONOMÍA" / "Medios con espacios"
    media_root.mkdir(parents=True)
    tasks_root = tmp_path / "Tareas"
    tasks_root.mkdir()
    source = media_root / "Vía Láctea — toma número 01.mp4"
    source.write_bytes(b"c20-media")

    monkeypatch.setattr(
        astromedia_service,
        "_ffprobe",
        lambda path, media_type: {
            "width": 1920,
            "height": 1080,
            "rotation_deg": 0,
            "fps": 30.0,
            "duration_seconds": 5.0,
            "codec_name": "h264",
        },
    )
    catalog = AstroMediaCatalog(
        db_path=tmp_path / "Índice" / "catálogo.sqlite3",
        json_path=tmp_path / "Índice" / "catálogo.json",
        allowed_roots=[media_root, tasks_root],
        tasks_root=tasks_root,
    )

    report = catalog.index_library(
        IndexRequest(
            root=str(media_root),
            recursive=True,
            hash_mode=HashMode.FULL,
            import_task_artifacts=False,
        )
    )

    assert report.indexed_items == 1
    assert Path(catalog.list_items()[0].local_path) == source.resolve()
