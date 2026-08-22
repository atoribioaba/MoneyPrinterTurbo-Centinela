from __future__ import annotations
from datetime import datetime
from enum import Enum
from pydantic import BaseModel, ConfigDict, Field, model_validator
from app.models.video_base_e2e import VideoBaseE2EPlan, VideoBaseE2EStatus

FINALIZATION_E2E_VERSION="finalization-e2e-v0.1"

class StrictFinalizationModel(BaseModel):
    model_config=ConfigDict(extra="forbid",validate_assignment=True)

class HumanFinalReviewDecision(str,Enum):
    APPROVE="APPROVE"; REJECT="REJECT"

class FinalizationE2EStatus(str,Enum):
    WAITING_FOR_VIDEO_BASE_E2E="WAITING_FOR_VIDEO_BASE_E2E"
    WAITING_FOR_HUMAN_REVIEW="WAITING_FOR_HUMAN_REVIEW"
    HUMAN_REVIEW_REJECTED="HUMAN_REVIEW_REJECTED"
    WAITING_FOR_FINAL_RENDERS="WAITING_FOR_FINAL_RENDERS"
    FINALIZATION_E2E_PASS="FINALIZATION_E2E_PASS"
    FINALIZATION_E2E_FAIL="FINALIZATION_E2E_FAIL"

class HumanFinalReviewRecord(StrictFinalizationModel):
    decision: HumanFinalReviewDecision
    reviewer_ref: str = Field(min_length=1,max_length=128)
    rationale: str = Field(min_length=1,max_length=1500)
    decided_at_utc: datetime

class FinalVideoArtifactProbe(StrictFinalizationModel):
    profile_id: str
    file_path: str
    exists: bool
    sha256: str | None=None
    width:int=Field(ge=0); height:int=Field(ge=0); fps:float=Field(ge=0)
    codec:str|None=None; audio_stream_count:int=Field(default=0,ge=0)
    subtitles_ready: bool=False
    publication_rights_ready: bool=False

class FinalizationE2ERequest(StrictFinalizationModel):
    video_base: VideoBaseE2EPlan
    human_review: HumanFinalReviewRecord|None=None
    artifacts:list[FinalVideoArtifactProbe]=Field(default_factory=list)

class FinalizationCheck(StrictFinalizationModel):
    check_id:str; passed:bool; detail:str

class FinalizationE2EPlan(StrictFinalizationModel):
    version:str=FINALIZATION_E2E_VERSION
    source_video_base_e2e_hash:str
    deterministic:bool=True; verification_only:bool=True; resource_class:str="LIGHT"
    renders_video:bool=False; modifies_media:bool=False; network_calls:int=0; uses_llm:bool=False; auto_publication:bool=False
    status:FinalizationE2EStatus
    human_review_recorded:bool
    required_profile_count:int=2
    artifact_count:int=Field(ge=0)
    check_count:int=Field(ge=0); passed_count:int=Field(ge=0); failed_count:int=Field(ge=0)
    checks:list[FinalizationCheck]
    artifacts:list[FinalVideoArtifactProbe]
    finalization_e2e_hash:str
    generated_at_utc:datetime
    @model_validator(mode="after")
    def validate_plan(self):
        if self.artifact_count!=len(self.artifacts): raise ValueError("artifact_count mismatch")
        if self.check_count!=len(self.checks): raise ValueError("check_count mismatch")
        if self.passed_count!=sum(x.passed for x in self.checks): raise ValueError("passed_count mismatch")
        if self.failed_count!=sum(not x.passed for x in self.checks): raise ValueError("failed_count mismatch")
        if not self.verification_only or self.renders_video or self.modifies_media or self.network_calls or self.uses_llm or self.auto_publication: raise ValueError("F53 guardrail violation")
        return self
