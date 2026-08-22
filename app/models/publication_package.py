from __future__ import annotations
from datetime import datetime
from enum import Enum
from pydantic import BaseModel, ConfigDict, Field, model_validator
from app.models.finalization_e2e import FinalizationE2EPlan, FinalizationE2EStatus
PUBLICATION_PACKAGE_VERSION="publication-package-v0.1"
class StrictPublicationPackageModel(BaseModel): model_config=ConfigDict(extra="forbid",validate_assignment=True)
class PublicationPackageStatus(str,Enum):
    WAITING_FOR_FINALIZATION="WAITING_FOR_FINALIZATION"; WAITING_FOR_METADATA="WAITING_FOR_METADATA"; READY_FOR_MANUAL_PACKAGE="READY_FOR_MANUAL_PACKAGE"
class PublicationMetadata(StrictPublicationPackageModel):
    title:str=Field(min_length=1,max_length=200); caption:str=Field(min_length=1,max_length=5000); hashtags:list[str]=Field(default_factory=list,max_length=50); youtube_description:str|None=Field(default=None,max_length=5000)
class PackageAsset(StrictPublicationPackageModel):
    asset_id:str; source_path:str|None=None; target_filename:str; required:bool=True; present:bool=False
class PublicationPackageRequest(StrictPublicationPackageModel):
    finalization:FinalizationE2EPlan; metadata:PublicationMetadata|None=None
class PublicationPackagePlan(StrictPublicationPackageModel):
    version:str=PUBLICATION_PACKAGE_VERSION; source_finalization_e2e_hash:str
    deterministic:bool=True; planning_only:bool=True; manual_publication_only:bool=True; resource_class:str="LIGHT"
    writes_files:bool=False; uploads_files:bool=False; network_calls:int=0; auto_publication:bool=False
    status:PublicationPackageStatus; asset_count:int=Field(ge=0); assets:list[PackageAsset]; metadata_present:bool
    publication_package_hash:str; generated_at_utc:datetime
    @model_validator(mode="after")
    def validate_plan(self):
        if self.asset_count!=len(self.assets): raise ValueError("asset_count mismatch")
        if not self.planning_only or not self.manual_publication_only or self.writes_files or self.uploads_files or self.network_calls or self.auto_publication: raise ValueError("F54 guardrail violation")
        return self
