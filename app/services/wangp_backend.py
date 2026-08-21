from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.models.wangp_backend import (
    WANGP_BACKEND_VERSION,
    WanGPAdapterMode,
    WanGPGPUProbe,
    WanGPLicenseClassification,
    WanGPLocalAudit,
    WanGPModelInventory,
    WanGPPythonEnvironment,
    WanGPReadiness,
)


_MODEL_EXTENSIONS = {
    ".safetensors",
    ".gguf",
    ".pt",
    ".pth",
    ".bin",
    ".ckpt",
}

_MODEL_DIR_NAMES = {
    "ckpts",
    "models",
    "checkpoints",
    "loras",
}

_ENV_CANDIDATES = (
    r"env_uv\Scripts\python.exe",
    r".venv\Scripts\python.exe",
    r"venv\Scripts\python.exe",
    r"env\Scripts\python.exe",
)


class WanGPBackendAuditError(RuntimeError):
    pass


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _hash_json(value: Any) -> str:
    return hashlib.sha256(
        _canonical_json(value).encode("utf-8")
    ).hexdigest().upper()


def _run(
    args: list[str],
    *,
    cwd: Path | None = None,
    timeout: float = 20.0,
) -> tuple[int, str, str]:
    try:
        result = subprocess.run(
            args,
            cwd=str(cwd) if cwd else None,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            timeout=timeout,
            check=False,
        )
        return (
            int(result.returncode),
            result.stdout.strip(),
            result.stderr.strip(),
        )
    except Exception as exc:
        return 999, "", f"{type(exc).__name__}: {exc}"


def _git(root: Path, *args: str) -> str | None:
    code, out, _ = _run(
        ["git", *args],
        cwd=root,
        timeout=10.0,
    )
    if code != 0 or not out:
        return None
    return out.splitlines()[0].strip()


def _detect_python(root: Path) -> WanGPPythonEnvironment:
    python_path: Path | None = None

    for relative in _ENV_CANDIDATES:
        candidate = root / relative
        if candidate.is_file():
            python_path = candidate
            break

    if python_path is None:
        return WanGPPythonEnvironment(
            diagnostics_error="NO_LOCAL_PYTHON_ENVIRONMENT_FOUND"
        )

    probe = r"""
import json
import platform
import sys

data = {
    "python_version": platform.python_version(),
    "torch_available": False,
    "torch_version": None,
    "torch_cuda_available": False,
    "torch_cuda_version": None,
    "torch_device_name": None,
    "torch_vram_bytes": None,
    "diagnostics_error": None,
}

try:
    import torch
    data["torch_available"] = True
    data["torch_version"] = str(torch.__version__)
    data["torch_cuda_available"] = bool(torch.cuda.is_available())
    data["torch_cuda_version"] = (
        str(torch.version.cuda) if torch.version.cuda is not None else None
    )
    if data["torch_cuda_available"]:
        data["torch_device_name"] = str(torch.cuda.get_device_name(0))
        props = torch.cuda.get_device_properties(0)
        data["torch_vram_bytes"] = int(props.total_memory)
except Exception as exc:
    data["diagnostics_error"] = type(exc).__name__ + ": " + str(exc)

print(json.dumps(data))
"""

    code, out, err = _run(
        [str(python_path), "-c", probe],
        cwd=root,
        timeout=45.0,
    )

    if code != 0:
        return WanGPPythonEnvironment(
            python_path=str(python_path),
            diagnostics_error=(
                f"PYTHON_PROBE_FAILED code={code}: {err or out}"
            ),
        )

    try:
        data = json.loads(out.splitlines()[-1])
    except Exception as exc:
        return WanGPPythonEnvironment(
            python_path=str(python_path),
            diagnostics_error=(
                f"PYTHON_PROBE_JSON_FAILED: {type(exc).__name__}: {exc}"
            ),
        )

    return WanGPPythonEnvironment(
        python_path=str(python_path),
        **data,
    )


def _probe_gpu() -> WanGPGPUProbe:
    code, out, err = _run(
        [
            "nvidia-smi",
            "--query-gpu=name,memory.total,driver_version",
            "--format=csv,noheader,nounits",
        ],
        timeout=10.0,
    )

    if code != 0 or not out:
        return WanGPGPUProbe(
            nvidia_smi_available=False,
            error=err or out or "nvidia-smi failed",
        )

    first = out.splitlines()[0]
    parts = [item.strip() for item in first.split(",")]

    try:
        memory_mib = int(float(parts[1]))
    except Exception:
        memory_mib = None

    return WanGPGPUProbe(
        nvidia_smi_available=True,
        gpu_name=parts[0] if parts else None,
        memory_total_mib=memory_mib,
        driver_version=parts[2] if len(parts) > 2 else None,
    )


def _model_inventory(root: Path) -> WanGPModelInventory:
    paths: list[Path] = []

    for name in _MODEL_DIR_NAMES:
        directory = root / name
        if not directory.is_dir():
            continue
        try:
            for path in directory.rglob("*"):
                if (
                    path.is_file()
                    and path.suffix.casefold() in _MODEL_EXTENSIONS
                ):
                    paths.append(path)
        except OSError:
            continue

    total = 0
    extensions: dict[str, int] = {}
    samples: list[str] = []

    for path in paths:
        try:
            total += path.stat().st_size
        except OSError:
            pass

        ext = path.suffix.casefold()
        extensions[ext] = extensions.get(ext, 0) + 1

        if len(samples) < 25:
            try:
                samples.append(str(path.relative_to(root)))
            except ValueError:
                samples.append(str(path))

    return WanGPModelInventory(
        file_count=len(paths),
        total_bytes=total,
        extensions=dict(sorted(extensions.items())),
        sample_paths=sorted(samples),
    )


def _license(
    root: Path,
) -> tuple[
    bool,
    str | None,
    WanGPLicenseClassification,
    list[str],
]:
    candidates = [
        root / "LICENSE.txt",
        root / "LICENSE",
        root / "LICENSE.md",
    ]
    license_path = next(
        (path for path in candidates if path.is_file()),
        None,
    )

    if license_path is None:
        return (
            False,
            None,
            WanGPLicenseClassification.LICENSE_NOT_VERIFIED,
            ["LOCAL_LICENSE_FILE_NOT_FOUND"],
        )

    try:
        text = license_path.read_text(
            encoding="utf-8",
            errors="replace",
        )
    except OSError:
        return (
            True,
            license_path.name,
            WanGPLicenseClassification.LICENSE_NOT_VERIFIED,
            ["LOCAL_LICENSE_FILE_UNREADABLE"],
        )

    lower = text.casefold()

    if (
        "wangp community license" in lower
        or "restricted commercialization" in lower
        or "commercial license" in lower
    ):
        return (
            True,
            license_path.name,
            WanGPLicenseClassification.SOURCE_AVAILABLE,
            [
                "CUSTOM_WANGP_LICENSE_DETECTED",
                "NOT_CLASSIFIED_AS_OSI_OPEN_SOURCE",
                "THIRD_PARTY_MODEL_LICENSES_MUST_BE_REVIEWED_SEPARATELY",
            ],
        )

    if (
        "apache license" in lower
        or "mit license" in lower
        or "gnu general public license" in lower
    ):
        return (
            True,
            license_path.name,
            WanGPLicenseClassification.OPEN_SOURCE,
            [
                "RECOGNIZED_OPEN_SOURCE_LICENSE_TEXT_DETECTED",
                "MODEL_WEIGHTS_STILL_REQUIRE_SEPARATE_LICENSE_REVIEW",
            ],
        )

    return (
        True,
        license_path.name,
        WanGPLicenseClassification.LICENSE_NOT_VERIFIED,
        [
            "LOCAL_LICENSE_PRESENT_BUT_CLASSIFICATION_NOT_AUTOMATICALLY_VERIFIED",
            "MODEL_WEIGHTS_REQUIRE_SEPARATE_LICENSE_REVIEW",
        ],
    )


class WanGPBackendAuditor:
    version = WANGP_BACKEND_VERSION

    def audit(
        self,
        install_path: str | Path = r"E:\IA\WanGP",
    ) -> WanGPLocalAudit:
        root = Path(install_path)
        exists = root.is_dir()

        if not exists:
            stable = {
                "version": self.version,
                "install_path": str(root),
                "install_exists": False,
            }
            return WanGPLocalAudit(
                install_path=str(root),
                install_exists=False,
                wgp_entrypoint_exists=False,
                git_repo=False,
                api_source_exists=False,
                api_docs_exists=False,
                headless_cli_docs_exists=False,
                headless_process_contract_found=False,
                dry_run_contract_found=False,
                config_exists=False,
                local_license_exists=False,
                license_classification=(
                    WanGPLicenseClassification.LICENSE_NOT_VERIFIED
                ),
                license_notes=["WANGP_INSTALLATION_NOT_FOUND"],
                environment=WanGPPythonEnvironment(
                    diagnostics_error="WANGP_INSTALLATION_NOT_FOUND"
                ),
                gpu=_probe_gpu(),
                model_inventory=WanGPModelInventory(
                    file_count=0,
                    total_bytes=0,
                ),
                adapter_mode=WanGPAdapterMode.UNAVAILABLE,
                readiness=WanGPReadiness.NOT_INSTALLED,
                audit_hash=_hash_json(stable),
                generated_at_utc=datetime.now(timezone.utc),
            )

        wgp_entry = root / "wgp.py"
        api_source = root / "shared" / "api.py"
        api_docs = root / "docs" / "API.md"
        cli_docs = root / "docs" / "CLI.md"
        config = root / "wgp_config.json"

        text_sources = []
        for path in (cli_docs, wgp_entry):
            if not path.is_file():
                continue
            try:
                text_sources.append(
                    path.read_text(
                        encoding="utf-8",
                        errors="replace",
                    )
                )
            except OSError:
                pass

        combined = "\n".join(text_sources)
        process_found = "--process" in combined
        dry_run_found = "--dry-run" in combined

        git_repo = (root / ".git").exists()
        git_head = _git(root, "rev-parse", "HEAD") if git_repo else None
        git_branch = (
            _git(root, "branch", "--show-current")
            if git_repo
            else None
        )
        git_remote = (
            _git(root, "remote", "get-url", "origin")
            if git_repo
            else None
        )
        git_dirty = None
        if git_repo:
            code, out, _ = _run(
                ["git", "status", "--porcelain"],
                cwd=root,
                timeout=10.0,
            )
            if code == 0:
                git_dirty = bool(out.strip())

        (
            license_exists,
            license_name,
            license_class,
            license_notes,
        ) = _license(root)

        environment = _detect_python(root)
        gpu = _probe_gpu()
        inventory = _model_inventory(root)

        if api_source.is_file():
            adapter = WanGPAdapterMode.PYTHON_API
        elif process_found:
            adapter = WanGPAdapterMode.HEADLESS_CLI
        elif wgp_entry.is_file():
            adapter = WanGPAdapterMode.WEBUI_ONLY
        else:
            adapter = WanGPAdapterMode.UNAVAILABLE

        if (
            wgp_entry.is_file()
            and environment.python_path
            and environment.torch_available
            and environment.torch_cuda_available
            and adapter
            in {
                WanGPAdapterMode.PYTHON_API,
                WanGPAdapterMode.HEADLESS_CLI,
            }
        ):
            readiness = WanGPReadiness.READY_FOR_ADAPTER
        else:
            readiness = WanGPReadiness.PARTIAL

        stable = {
            "version": self.version,
            "install_path": str(root),
            "install_exists": True,
            "wgp_entrypoint_exists": wgp_entry.is_file(),
            "git_repo": git_repo,
            "git_head": git_head,
            "git_branch": git_branch,
            "git_remote": git_remote,
            "git_dirty": git_dirty,
            "api_source_exists": api_source.is_file(),
            "api_docs_exists": api_docs.is_file(),
            "headless_cli_docs_exists": cli_docs.is_file(),
            "headless_process_contract_found": process_found,
            "dry_run_contract_found": dry_run_found,
            "config_exists": config.is_file(),
            "license_classification": license_class.value,
            "python_path": environment.python_path,
            "python_version": environment.python_version,
            "torch_version": environment.torch_version,
            "torch_cuda_available": environment.torch_cuda_available,
            "torch_cuda_version": environment.torch_cuda_version,
            "torch_device_name": environment.torch_device_name,
            "gpu_name": gpu.gpu_name,
            "gpu_memory_total_mib": gpu.memory_total_mib,
            "driver_version": gpu.driver_version,
            "model_file_count": inventory.file_count,
            "model_total_bytes": inventory.total_bytes,
            "adapter_mode": adapter.value,
            "readiness": readiness.value,
        }

        return WanGPLocalAudit(
            install_path=str(root),
            install_exists=True,
            wgp_entrypoint_exists=wgp_entry.is_file(),
            git_repo=git_repo,
            git_head=git_head,
            git_branch=git_branch,
            git_remote=git_remote,
            git_dirty=git_dirty,
            api_source_exists=api_source.is_file(),
            api_docs_exists=api_docs.is_file(),
            headless_cli_docs_exists=cli_docs.is_file(),
            headless_process_contract_found=process_found,
            dry_run_contract_found=dry_run_found,
            config_exists=config.is_file(),
            local_license_exists=license_exists,
            local_license_name=license_name,
            license_classification=license_class,
            license_notes=license_notes,
            environment=environment,
            gpu=gpu,
            model_inventory=inventory,
            adapter_mode=adapter,
            readiness=readiness,
            audit_hash=_hash_json(stable),
            generated_at_utc=datetime.now(timezone.utc),
        )
