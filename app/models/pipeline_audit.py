from __future__ import annotations

import re
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


_SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")
_GIT_SHA_RE = re.compile(r"^[0-9a-fA-F]{40}$")


class StrictAuditModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class OpenSourceClassification(str, Enum):
    OPEN_SOURCE_FREE = "OPEN SOURCE + 100 % GRATUITA"
    OSS_WITH_PAID_SERVICE = "OSS CON SERVICIO DE PAGO"
    OPEN_WEIGHTS = "PESOS ABIERTOS"
    SOURCE_AVAILABLE = "SOURCE AVAILABLE"
    FREEMIUM = "FREEMIUM"
    COMMERCIAL = "COMERCIAL"
    LICENSE_UNVERIFIED = "LICENCIA NO VERIFICADA"


class PipelineDecision(str, Enum):
    KEEP = "MANTENER"
    OSS_ALTERNATIVE_RECOMMENDED = "ALTERNATIVA OSS RECOMENDADA"
    NOT_WORTH_IT = "NO COMPENSA"
    AB_TEST = "PRUEBA A/B"
    NO_BETTER_VERIFIED_ALTERNATIVE = "NO HAY ALTERNATIVA MEJOR VERIFICADA"


class PipelineComponentAudit(StrictAuditModel):
    function_id: str
    component: str
    classification: OpenSourceClassification
    decision: PipelineDecision
    license_id_or_status: str
    source_url: str
    selected_for_rc: bool = False
    version_or_commit: str | None = None
    artifact_sha256: str | None = None
    weights_or_binary_artifact: bool = False
    physical_validation_required: bool = False
    physical_evidence_ids: list[str] = Field(default_factory=list)
    expected_vram_gb: float | None = Field(default=None, ge=0.0)
    expected_ram_gb: float | None = Field(default=None, ge=0.0)
    notes: str = ""

    @field_validator("function_id", "component", "license_id_or_status", "source_url")
    @classmethod
    def non_empty_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("audit text fields cannot be empty")
        return value

    @field_validator("artifact_sha256")
    @classmethod
    def validate_artifact_sha(cls, value: str | None) -> str | None:
        if value is not None and not _SHA256_RE.fullmatch(value):
            raise ValueError("artifact_sha256 must be 64 hexadecimal characters")
        return value.lower() if value is not None else None


class PipelineAuditManifest(StrictAuditModel):
    project_sha: str
    created_at: datetime
    components: list[PipelineComponentAudit]
    auto_publication: bool = False

    @field_validator("project_sha")
    @classmethod
    def validate_project_sha(cls, value: str) -> str:
        value = value.strip().lower()
        if not _GIT_SHA_RE.fullmatch(value):
            raise ValueError("project_sha must be a full 40-character Git SHA")
        return value

    @model_validator(mode="after")
    def validate_manifest(self):
        if self.created_at.tzinfo is None or self.created_at.utcoffset() is None:
            raise ValueError("created_at must be timezone-aware")
        if self.auto_publication:
            raise ValueError("AUTO_PUBLICATION must remain false")
        function_ids = [item.function_id for item in self.components]
        if len(function_ids) != len(set(function_ids)):
            raise ValueError("pipeline audit cannot contain duplicate function_id values")
        return self


class PipelineAuditResult(StrictAuditModel):
    pass_gate: bool
    blockers: list[str]
    warnings: list[str]
    selected_components: int = Field(ge=0)
    audited_components: int = Field(ge=0)
