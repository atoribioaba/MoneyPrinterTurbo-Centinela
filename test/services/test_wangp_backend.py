from __future__ import annotations

from pathlib import Path

from app.models.wangp_backend import (
    WanGPAdapterMode,
    WanGPLicenseClassification,
    WanGPReadiness,
)
from app.services.wangp_backend import WanGPBackendAuditor


def make_install(tmp_path: Path):
    root = tmp_path / "WanGP"
    (root / "shared").mkdir(parents=True)
    (root / "docs").mkdir(parents=True)
    (root / "models").mkdir(parents=True)
    (root / "env_uv" / "Scripts").mkdir(parents=True)

    (root / "wgp.py").write_text(
        "parser.add_argument('--process')\n"
        "parser.add_argument('--dry-run')\n",
        encoding="utf-8",
    )
    (root / "shared" / "api.py").write_text(
        "class WanGPSession: pass\n",
        encoding="utf-8",
    )
    (root / "docs" / "API.md").write_text(
        "WanGP Python API",
        encoding="utf-8",
    )
    (root / "docs" / "CLI.md").write_text(
        "python wgp.py --process queue.json --dry-run",
        encoding="utf-8",
    )
    (root / "LICENSE.txt").write_text(
        "WanGP Community License 2.0\n"
        "Restricted Commercialization\n",
        encoding="utf-8",
    )
    (root / "models" / "fixture.gguf").write_bytes(b"1234")
    return root


def test_missing_install_is_safe(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "app.services.wangp_backend._probe_gpu",
        lambda: __import__(
            "app.models.wangp_backend",
            fromlist=["WanGPGPUProbe"],
        ).WanGPGPUProbe(nvidia_smi_available=False),
    )
    result = WanGPBackendAuditor().audit(tmp_path / "missing")

    assert result.readiness == WanGPReadiness.NOT_INSTALLED
    assert result.adapter_mode == WanGPAdapterMode.UNAVAILABLE
    assert result.downloads_models is False
    assert result.modifies_wangp is False


def test_api_contract_is_preferred(tmp_path, monkeypatch):
    root = make_install(tmp_path)

    monkeypatch.setattr(
        "app.services.wangp_backend._detect_python",
        lambda _: __import__(
            "app.models.wangp_backend",
            fromlist=["WanGPPythonEnvironment"],
        ).WanGPPythonEnvironment(
            python_path="python.exe",
            python_version="3.11",
            torch_available=True,
            torch_version="2.x",
            torch_cuda_available=True,
            torch_device_name="RTX 2060",
        ),
    )
    monkeypatch.setattr(
        "app.services.wangp_backend._probe_gpu",
        lambda: __import__(
            "app.models.wangp_backend",
            fromlist=["WanGPGPUProbe"],
        ).WanGPGPUProbe(
            nvidia_smi_available=True,
            gpu_name="RTX 2060",
            memory_total_mib=6144,
            driver_version="fixture",
        ),
    )

    result = WanGPBackendAuditor().audit(root)

    assert result.adapter_mode == WanGPAdapterMode.PYTHON_API
    assert result.readiness == WanGPReadiness.READY_FOR_ADAPTER
    assert result.api_source_exists is True
    assert result.headless_process_contract_found is True
    assert result.dry_run_contract_found is True


def test_custom_license_is_source_available(tmp_path, monkeypatch):
    root = make_install(tmp_path)
    monkeypatch.setattr(
        "app.services.wangp_backend._probe_gpu",
        lambda: __import__(
            "app.models.wangp_backend",
            fromlist=["WanGPGPUProbe"],
        ).WanGPGPUProbe(nvidia_smi_available=False),
    )
    result = WanGPBackendAuditor().audit(root)

    assert (
        result.license_classification
        == WanGPLicenseClassification.SOURCE_AVAILABLE
    )


def test_model_inventory_does_not_hash_or_download(tmp_path, monkeypatch):
    root = make_install(tmp_path)
    monkeypatch.setattr(
        "app.services.wangp_backend._probe_gpu",
        lambda: __import__(
            "app.models.wangp_backend",
            fromlist=["WanGPGPUProbe"],
        ).WanGPGPUProbe(nvidia_smi_available=False),
    )
    result = WanGPBackendAuditor().audit(root)

    assert result.model_inventory.file_count == 1
    assert result.model_inventory.total_bytes == 4
    assert result.network_access_used is False
    assert result.downloads_models is False
    assert result.large_download_authorized is False


def test_audit_hash_is_stable_for_same_fixture(tmp_path, monkeypatch):
    root = make_install(tmp_path)
    monkeypatch.setattr(
        "app.services.wangp_backend._detect_python",
        lambda _: __import__(
            "app.models.wangp_backend",
            fromlist=["WanGPPythonEnvironment"],
        ).WanGPPythonEnvironment(
            python_path="python.exe",
            python_version="3.11",
        ),
    )
    monkeypatch.setattr(
        "app.services.wangp_backend._probe_gpu",
        lambda: __import__(
            "app.models.wangp_backend",
            fromlist=["WanGPGPUProbe"],
        ).WanGPGPUProbe(nvidia_smi_available=False),
    )

    first = WanGPBackendAuditor().audit(root)
    second = WanGPBackendAuditor().audit(root)

    assert first.audit_hash == second.audit_hash
