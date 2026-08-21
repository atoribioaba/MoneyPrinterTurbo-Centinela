from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator


WANGP_BACKEND_VERSION = "wangp-backend-v0.1"


class StrictWanGPModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class WanGPAdapterMode(str, Enum):
    PYTHON_API = "PYTHON_API"
    HEADLESS_CLI = "HEADLESS_CLI"
    WEBUI_ONLY = "WEBUI_ONLY"
    UNAVAILABLE = "UNAVAILABLE"


class WanGPLicenseClassification(str, Enum):
    SOURCE_AVAILABLE = "SOURCE_AVAILABLE"
    OPEN_SOURCE = "OPEN_SOURCE"
    LICENSE_NOT_VERIFIED = "LICENSE_NOT_VERIFIED"


class WanGPReadiness(str, Enum):
    READY_FOR_ADAPTER = "READY_FOR_ADAPTER"
    PARTIAL = "PARTIAL"
    NOT_INSTALLED = "NOT_INSTALLED"


class WanGPModelInventory(StrictWanGPModel):
    file_count: int = Field(ge=0)
    total_bytes: int = Field(ge=0)
    extensions: dict[str, int] = Field(default_factory=dict)
    sample_paths: list[str] = Field(default_factory=list, max_length=25)


class WanGPPythonEnvironment(StrictWanGPModel):
    python_path: str | None = None
    python_version: str | None = None
    torch_available: bool = False
    torch_version: str | None = None
    torch_cuda_available: bool = False
    torch_cuda_version: str | None = None
    torch_device_name: str | None = None
    torch_vram_bytes: int | None = Field(default=None, ge=0)
    diagnostics_error: str | None = None


class WanGPGPUProbe(StrictWanGPModel):
    nvidia_smi_available: bool
    gpu_name: str | None = None
    memory_total_mib: int | None = Field(default=None, ge=0)
    driver_version: str | None = None
    error: str | None = None


class WanGPLocalAudit(StrictWanGPModel):
    version: str = WANGP_BACKEND_VERSION
    install_path: str

    install_exists: bool
    wgp_entrypoint_exists: bool
    git_repo: bool
    git_head: str | None = None
    git_branch: str | None = None
    git_remote: str | None = None
    git_dirty: bool | None = None

    api_source_exists: bool
    api_docs_exists: bool
    headless_cli_docs_exists: bool
    headless_process_contract_found: bool
    dry_run_contract_found: bool

    config_exists: bool
    local_license_exists: bool
    local_license_name: str | None = None
    license_classification: WanGPLicenseClassification
    license_notes: list[str] = Field(default_factory=list)

    environment: WanGPPythonEnvironment
    gpu: WanGPGPUProbe
    model_inventory: WanGPModelInventory

    adapter_mode: WanGPAdapterMode
    readiness: WanGPReadiness

    low_vram_target_mib: int = 6144
    model_selection_required: bool = True
    large_download_authorized: bool = False

    modifies_wangp: bool = False
    network_access_used: bool = False
    downloads_models: bool = False
    imports_wangp_runtime: bool = False
    launches_wangp: bool = False

    audit_hash: str
    generated_at_utc: datetime

    @model_validator(mode="after")
    def validate_guardrails(self):
        if (
            self.large_download_authorized
            or self.modifies_wangp
            or self.network_access_used
            or self.downloads_models
            or self.imports_wangp_runtime
            or self.launches_wangp
        ):
            raise ValueError("F15 audit guardrail violation")

        if not self.install_exists:
            if self.readiness != WanGPReadiness.NOT_INSTALLED:
                raise ValueError("missing installation must be NOT_INSTALLED")
            if self.adapter_mode != WanGPAdapterMode.UNAVAILABLE:
                raise ValueError("missing installation cannot expose adapter")

        if self.adapter_mode == WanGPAdapterMode.PYTHON_API:
            if not self.api_source_exists:
                raise ValueError("PYTHON_API requires shared/api.py")

        if self.adapter_mode == WanGPAdapterMode.HEADLESS_CLI:
            if not self.headless_process_contract_found:
                raise ValueError("HEADLESS_CLI requires --process contract")

        return self
