from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from app.services.centinela.orchestration import JobStatus, ProjectState, ResourceClass
from app.services.centinela.production_spine import SpineStage

CONTROL_CENTER_VERSION = "control-center-v0.1"
CENTINELA_EDITION_LABEL = "pre-V1"
AUTO_PIPELINE_JOB_TYPE = "centinela.product.pipeline"


class PipelineDisposition(StrEnum):
    RUNNING = "RUNNING"
    CAPABILITY_PENDING = "CAPABILITY_PENDING"
    NEEDS_INPUT = "NEEDS_INPUT"
    BLOCKED = "BLOCKED"
    WAITING_HUMAN_REVIEW = "WAITING_HUMAN_REVIEW"
    FINAL_APPROVED = "FINAL_APPROVED"
    PUBLICATION_PACKAGE_READY = "PUBLICATION_PACKAGE_READY"
    TERMINAL = "TERMINAL"
    STAGE_JOB_FAILED = "STAGE_JOB_FAILED"
    NO_NEXT_ACTION = "NO_NEXT_ACTION"


@dataclass(frozen=True, slots=True)
class MediaRefreshDecision:
    refresh_catalog: bool
    reason: str
    root: str
    root_exists: bool
    supported_file_count: int
    catalog_root_item_count: int
    active_catalog_item_count: int
    changed_path_count: int = 0
    sample_changed_paths: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "refresh_catalog": self.refresh_catalog,
            "reason": self.reason,
            "root": self.root,
            "root_exists": self.root_exists,
            "supported_file_count": self.supported_file_count,
            "catalog_root_item_count": self.catalog_root_item_count,
            "active_catalog_item_count": self.active_catalog_item_count,
            "changed_path_count": self.changed_path_count,
            "sample_changed_paths": list(self.sample_changed_paths),
        }


@dataclass(frozen=True, slots=True)
class CapabilityView:
    stage: SpineStage
    label: str
    resource_class: ResourceClass
    connected: bool
    backend_status: str
    roadmap_owner: str


@dataclass(frozen=True, slots=True)
class JobView:
    job_id: str
    job_type: str
    status: JobStatus
    progress: int
    message: str | None
    resource_class: ResourceClass
    created_at: str
    updated_at: str
    error_type: str | None = None
    error_message: str | None = None


@dataclass(frozen=True, slots=True)
class ProjectView:
    project_id: str
    title: str
    state: ProjectState
    state_label: str
    next_stage: SpineStage | None
    next_action: str
    capability_pending: bool
    active_job_id: str | None
    artifact_count: int
    artifact_type_counts: dict[str, int] = field(default_factory=dict)
    created_at: str = ""
    updated_at: str = ""
    observation_context: dict[str, Any] = field(default_factory=dict)
    latest_jobs: tuple[JobView, ...] = ()
    architecture_freeze: bool = False
    auto_publication: bool = False


@dataclass(frozen=True, slots=True)
class PipelineStart:
    project_id: str
    job_id: str
    existing: bool
    status: JobStatus


@dataclass(frozen=True, slots=True)
class LibraryView:
    active_items: int
    publication_eligible_items: int
    provider_counts: dict[str, int]
    rights_counts: dict[str, int]
    refresh: MediaRefreshDecision
