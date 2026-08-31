from __future__ import annotations
from datetime import datetime
from enum import Enum
from pydantic import BaseModel, ConfigDict, Field, model_validator
OPERATIONAL_HARDENING_VERSION="operational-hardening-v0.1"
class StrictOperationalHardeningModel(BaseModel):
    model_config=ConfigDict(extra="forbid",validate_assignment=True)
class FindingSeverity(str,Enum):
    INFO="INFO"
    WARN="WARN"
    BLOCK="BLOCK"
class OperationalHardeningStatus(str,Enum):
    HARDENING_PASS="HARDENING_PASS"
    HARDENING_WARN="HARDENING_WARN"
    HARDENING_BLOCKED="HARDENING_BLOCKED"
class OperationalEnvironmentSnapshot(StrictOperationalHardeningModel):
    repo_exists:bool
    venv_python_exists:bool
    git_present:bool
    ffmpeg_present:bool
    gitleaks_present:bool
    certifier_present:bool
    backup_root_exists:bool
    resource_governor_available:bool
    free_space_gb:float=Field(ge=0)
    backup_bundle_count:int=Field(ge=0)
    ram_target_gb:float=16.0
    vram_target_gb:float=6.0
    git_network_workaround_required:bool=False
    plaintext_secret_config_count:int=Field(default=0,ge=0)
class OperationalFinding(StrictOperationalHardeningModel):
    finding_id:str
    severity:FindingSeverity
    detail:str
class OperationalHardeningRequest(StrictOperationalHardeningModel):
    snapshot:OperationalEnvironmentSnapshot
class OperationalHardeningPlan(StrictOperationalHardeningModel):
    version:str=OPERATIONAL_HARDENING_VERSION
    deterministic:bool=True
    audit_only:bool=True
    resource_class:str="LIGHT"
    modifies_config:bool=False
    resets_network:bool=False
    deletes_files:bool=False
    downloads_dependencies:bool=False
    network_calls:int=0
    status:OperationalHardeningStatus
    safe_to_run_pipeline:bool
    finding_count:int=Field(ge=0)
    block_count:int=Field(ge=0)
    warning_count:int=Field(ge=0)
    findings:list[OperationalFinding]
    snapshot:OperationalEnvironmentSnapshot
    operational_hardening_hash:str
    generated_at_utc:datetime
    @model_validator(mode="after")
    def validate_plan(self):
        if self.finding_count!=len(self.findings):
            raise ValueError("finding_count mismatch")
        if self.block_count!=sum(x.severity==FindingSeverity.BLOCK for x in self.findings):
            raise ValueError("block_count mismatch")
        if self.warning_count!=sum(x.severity==FindingSeverity.WARN for x in self.findings):
            raise ValueError("warning_count mismatch")
        if self.safe_to_run_pipeline!=(self.block_count==0):
            raise ValueError("safe_to_run_pipeline mismatch")
        if not self.audit_only or self.modifies_config or self.resets_network or self.deletes_files or self.downloads_dependencies or self.network_calls:
            raise ValueError("F56 guardrail violation")
        return self
