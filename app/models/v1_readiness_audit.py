from __future__ import annotations
from datetime import datetime
from enum import Enum
from pydantic import BaseModel, ConfigDict, Field, model_validator
from app.models.analytics_import_adapter import AnalyticsImportPlan
from app.models.golden_e2e_certification import GoldenE2ECertificationPlan, GoldenCertificationStatus
from app.models.operational_hardening import OperationalHardeningPlan, OperationalHardeningStatus
from app.models.production_orchestrator import ProductionOrchestratorPlan
from app.models.publication_package import PublicationPackagePlan, PublicationPackageStatus
V1_READINESS_AUDIT_VERSION="v1-readiness-audit-v0.1"
class StrictV1AuditModel(BaseModel): model_config=ConfigDict(extra="forbid",validate_assignment=True)
class V1ReadinessStatus(str,Enum): NOT_READY_FOR_ARCHITECTURE_FREEZE="NOT_READY_FOR_ARCHITECTURE_FREEZE"; READY_FOR_HUMAN_FREEZE_APPROVAL="READY_FOR_HUMAN_FREEZE_APPROVAL"; ARCHITECTURE_FREEZE_AUTHORIZED="ARCHITECTURE_FREEZE_AUTHORIZED"
class OSSAuditEntry(StrictV1AuditModel):
    function:str; current_component:str; classification:str; free:bool|None=None; license:str; decision:str; verified:bool=False
class V1ReadinessRequest(StrictV1AuditModel):
    orchestrator:ProductionOrchestratorPlan; publication:PublicationPackagePlan; analytics_import:AnalyticsImportPlan; hardening:OperationalHardeningPlan; golden:GoldenE2ECertificationPlan; oss_audit:list[OSSAuditEntry]=Field(default_factory=list); human_freeze_approval:bool=False
class V1ReadinessCheck(StrictV1AuditModel): check_id:str; passed:bool; blocking:bool=True; detail:str
class V1ReadinessAuditPlan(StrictV1AuditModel):
    version:str=V1_READINESS_AUDIT_VERSION; deterministic:bool=True; audit_only:bool=True; final_phase:bool=True; resource_class:str="LIGHT"
    architecture_v1_frozen:bool=False; freeze_authorized:bool=False; freeze_executed:bool=False; auto_publication:bool=False; auto_activation:bool=False; writes_runtime_config:bool=False
    status:V1ReadinessStatus; check_count:int=Field(ge=0); passed_count:int=Field(ge=0); failed_count:int=Field(ge=0); checks:list[V1ReadinessCheck]
    oss_audit_count:int=Field(ge=0); oss_audit_verified_count:int=Field(ge=0); oss_audit:list[OSSAuditEntry]
    v1_readiness_hash:str; generated_at_utc:datetime
    @model_validator(mode="after")
    def validate_plan(self):
        if self.check_count!=len(self.checks): raise ValueError("check_count mismatch")
        if self.passed_count!=sum(x.passed for x in self.checks): raise ValueError("passed_count mismatch")
        if self.failed_count!=sum(not x.passed for x in self.checks): raise ValueError("failed_count mismatch")
        if self.oss_audit_count!=len(self.oss_audit) or self.oss_audit_verified_count!=sum(x.verified for x in self.oss_audit): raise ValueError("OSS audit count mismatch")
        if self.architecture_v1_frozen or self.freeze_executed: raise ValueError("F58 may authorize freeze but never execute it")
        if not self.audit_only or not self.final_phase or self.auto_publication or self.auto_activation or self.writes_runtime_config: raise ValueError("F58 guardrail violation")
        return self
