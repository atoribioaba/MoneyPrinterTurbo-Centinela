from __future__ import annotations
from datetime import datetime
from enum import Enum
from pydantic import BaseModel, ConfigDict, Field, model_validator
from app.models.finalization_e2e import FinalizationE2EPlan
from app.models.operational_hardening import OperationalHardeningPlan
from app.models.video_base_e2e import VideoBaseE2EPlan
GOLDEN_E2E_CERTIFICATION_VERSION="golden-e2e-certification-v0.1"
class StrictGoldenModel(BaseModel):
    model_config=ConfigDict(extra="forbid",validate_assignment=True)
class GoldenScenarioId(str,Enum):
    SOL_TO_MOON="SOL_TO_MOON"
    LUNAR="LUNAR"
    PLANETARY="PLANETARY"
    ECLIPSE="ECLIPSE"
    CONSTELLATION="CONSTELLATION"
    DEEP_SKY="DEEP_SKY"
    INSUFFICIENT_MEDIA="INSUFFICIENT_MEDIA"
    VISUAL_RECREATION="VISUAL_RECREATION"
class GoldenCertificationStatus(str,Enum):
    WAITING_FOR_REAL_E2E="WAITING_FOR_REAL_E2E"
    WAITING_FOR_GOLDEN_EVIDENCE="WAITING_FOR_GOLDEN_EVIDENCE"
    CERTIFICATION_FAIL="CERTIFICATION_FAIL"
    CERTIFICATION_PASS="CERTIFICATION_PASS"
class GoldenScenarioEvidence(StrictGoldenModel):
    scenario_id:GoldenScenarioId
    scientific_pass:bool
    visual_relevance_pass:bool
    provenance_pass:bool
    render_pass:bool
    no_irrelevant_broll:bool
    recovery_pass:bool
    notes:str=""
class PerformanceEvidence(StrictGoldenModel):
    oom_events:int=Field(ge=0)
    unrecovered_failures:int=Field(ge=0)
    nvenc_path_tested:bool
    libx264_fallback_tested:bool
    max_ram_gb:float|None=Field(default=None,ge=0)
    max_vram_gb:float|None=Field(default=None,ge=0)
class GoldenE2ECertificationRequest(StrictGoldenModel):
    video_base:VideoBaseE2EPlan
    finalization:FinalizationE2EPlan
    hardening:OperationalHardeningPlan
    scenarios:list[GoldenScenarioEvidence]=Field(default_factory=list)
    performance:PerformanceEvidence|None=None
class GoldenE2ECertificationPlan(StrictGoldenModel):
    version:str=GOLDEN_E2E_CERTIFICATION_VERSION
    deterministic:bool=True
    certification_only:bool=True
    real_video_required:bool=True
    synthetic_only_not_accepted:bool=True
    resource_class:str="LIGHT"
    renders_video:bool=False
    network_calls:int=0
    uses_llm:bool=False
    auto_publication:bool=False
    status:GoldenCertificationStatus
    required_scenario_count:int=8
    scenario_count:int=Field(ge=0)
    passed_scenario_count:int=Field(ge=0)
    missing_scenarios:list[GoldenScenarioId]
    performance_present:bool
    golden_e2e_hash:str
    generated_at_utc:datetime
    @model_validator(mode="after")
    def validate_plan(self):
        if self.scenario_count + len(self.missing_scenarios) < self.required_scenario_count:
            pass
        if not self.certification_only or not self.real_video_required or not self.synthetic_only_not_accepted or self.renders_video or self.network_calls or self.uses_llm or self.auto_publication:
            raise ValueError("F57 guardrail violation")
        return self
